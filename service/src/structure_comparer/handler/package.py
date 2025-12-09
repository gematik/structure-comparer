import json
import logging
import shutil
import tarfile
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Dict, List, Set, Any, Tuple
from io import BytesIO

import httpx
from fastapi import UploadFile

from ..data.package import Package
from ..data.profile import Profile
from ..errors import (
    InvalidFileFormat,
    PackageAlreadyExists,
    PackageCorrupted,
    PackageNoSnapshots,
    PackageNotFound,
    PackageDownloadFailed,
    PackageNotFoundInRegistry,
)
from ..model.package import Package as PackageModel
from ..model.package import PackageInput as PackageInputModel
from ..model.package import PackageList as PackageListModel
from ..model.package import PackageDownloadResult as PackageDownloadResultModel
from ..model.profile import ProfileList as ProfileListModel
from ..model.profile import ProfileDetails as ProfileDetailsModel
from ..model.profile import ResolvedProfileField, ResolvedProfileFieldsResponse
from .project import ProjectsHandler

logger = logging.getLogger(__name__)

# FHIR Package Registries - order matters (first successful wins)
FHIR_REGISTRIES = [
    "https://packages.fhir.org",
    "https://packages2.fhir.org", 
    "https://packages.simplifier.net",
]

# Non-recursive FHIR resource types that don't have fields to load
NON_RECURSIVE_PATTERNS = [
    '/NamingSystem/',
    '/CodeSystem/',
    '/ValueSet/',
    '/ConceptMap/',
    '/SearchParameter/',
    '/OperationDefinition/',
    '/CapabilityStatement/',
    '/ImplementationGuide/',
    'NamingSystem',
    'CodeSystem',
    'ValueSet'
]


class PackageHandler:
    def __init__(self, project_handler: ProjectsHandler):
        self.project_handler: ProjectsHandler = project_handler

    def get_list(self, proj_key: str) -> PackageListModel:
        proj = self.project_handler._get(proj_key)
        pkgs = [p.to_model() for p in proj.pkgs]
        return PackageListModel(packages=pkgs)

    def update(
        self, proj_key: str, package_id: str, package_input: PackageInputModel
    ) -> PackageModel:
        proj = self.project_handler._get(proj_key)
        pkg = proj.get_package(package_id)

        if pkg is None:
            raise PackageNotFound()

        # Update package information
        pkg.display = package_input.display

        return pkg.to_model()

    def get_profiles(self, proj_key: str) -> ProfileListModel:
        proj = self.project_handler._get(proj_key)

        profs = [prof.to_pkg_model() for pkg in proj.pkgs for prof in pkg.profiles]
        return ProfileListModel(profiles=profs)

    def get_profile(self, proj_key: str, profile_id: str) -> ProfileDetailsModel:
        """Get a single profile with all its fields."""
        proj = self.project_handler._get(proj_key)

        for pkg in proj.pkgs:
            for prof in pkg.profiles:
                if prof.id == profile_id:
                    return prof.to_details_model()

        raise PackageNotFound()  # TODO: Create ProfileNotFound error

    def get_resolved_profile_fields(
        self, proj_key: str, profile_ids: list[str]
    ) -> ResolvedProfileFieldsResponse:
        """
        Get fields from profiles with recursive resolution of fixedUri/fixedCanonical references.
        
        This method:
        1. Loads all profiles in the project for URL-based lookups
        2. For each requested profile, loads its fields
        3. Recursively follows fixedUri/fixedCanonical references to StructureDefinitions
        4. Categorizes fields into resource fields and value fields
        5. Reports any unresolved references
        
        Args:
            proj_key: Project key
            profile_ids: List of profile IDs to load (typically source profiles)
            
        Returns:
            ResolvedProfileFieldsResponse with categorized fields and unresolved references
        """
        proj = self.project_handler._get(proj_key)
        
        # Build lookup maps for all profiles
        profile_by_id: dict[str, Profile] = {}
        profile_by_url: dict[str, Profile] = {}
        
        for pkg in proj.pkgs:
            for prof in pkg.profiles:
                profile_by_id[prof.id] = prof
                if prof.url:
                    profile_by_url[prof.url] = prof
                    # Also without version
                    url_without_version = prof.url.split('|')[0]
                    if url_without_version not in profile_by_url:
                        profile_by_url[url_without_version] = prof
        
        resource_fields: list[ResolvedProfileField] = []
        value_fields: list[ResolvedProfileField] = []
        unresolved_references: list[str] = []
        visited: set[str] = set()
        
        # Sort profile_ids to process Bundle profiles first
        sorted_profile_ids = sorted(profile_ids, key=lambda x: (
            0 if 'bundle' in x.lower() else 1
        ))
        
        for profile_id in sorted_profile_ids:
            if profile_id not in profile_by_id:
                logger.warning(f"Profile not found: {profile_id}")
                continue
                
            profile = profile_by_id[profile_id]
            root_resource_type = self._extract_root_resource_type(profile_id)
            
            self._load_fields_recursive(
                profile=profile,
                profile_key=profile.key,
                path_prefix='',
                root_resource_type=root_resource_type,
                visited=visited,
                profile_by_id=profile_by_id,
                profile_by_url=profile_by_url,
                resource_fields=resource_fields,
                value_fields=value_fields,
                unresolved_references=unresolved_references
            )
        
        # Remove duplicates while preserving order
        seen_resource = set()
        unique_resource = []
        for f in resource_fields:
            if f.full_path not in seen_resource:
                seen_resource.add(f.full_path)
                unique_resource.append(f)
        
        seen_value = set()
        unique_value = []
        for f in value_fields:
            if f.full_path not in seen_value:
                seen_value.add(f.full_path)
                unique_value.append(f)
        
        return ResolvedProfileFieldsResponse(
            resource_fields=unique_resource,
            value_fields=unique_value,
            unresolved_references=list(set(unresolved_references))
        )

    def _extract_root_resource_type(self, profile_id: str) -> str:
        """Extract root resource type from profile ID (e.g., 'Bundle', 'Composition')."""
        import re
        pattern = r'-(Bundle|Composition|MedicationRequest|Medication|' \
                  r'Patient|Organization|Practitioner|Coverage)'
        match = re.search(pattern, profile_id)
        if match:
            return match.group(1)
        return ''

    def _is_non_recursive_reference(self, url: str) -> bool:
        """Check if URL refers to a non-recursive FHIR type."""
        return any(pattern in url for pattern in NON_RECURSIVE_PATTERNS)

    def _resolve_profile_by_url(
        self,
        url: str,
        profile_by_id: dict[str, Profile],
        profile_by_url: dict[str, Profile]
    ) -> Profile | None:
        """Resolve a fixedUri/fixedCanonical to a Profile."""
        # Direct URL lookup
        if url in profile_by_url:
            return profile_by_url[url]

        # Try without version
        url_without_version = url.split('|')[0]
        if url_without_version in profile_by_url:
            return profile_by_url[url_without_version]

        # Extract last path segment for name-based lookup
        url_parts = url.split('/')
        last_part = url_parts[-1] if url_parts else ''
        if last_part and last_part in profile_by_id:
            return profile_by_id[last_part]

        # Try partial name match
        for prof in profile_by_id.values():
            if prof.name and prof.name in url:
                return prof
            if prof.id and prof.id in url:
                return prof
        
        return None
    
    def _load_fields_recursive(
        self,
        profile: Profile,
        profile_key: str,
        path_prefix: str,
        root_resource_type: str,
        visited: set[str],
        profile_by_id: dict[str, Profile],
        profile_by_url: dict[str, Profile],
        resource_fields: list[ResolvedProfileField],
        value_fields: list[ResolvedProfileField],
        unresolved_references: list[str]
    ) -> None:
        """Recursively load profile fields and follow references."""
        if profile.id in visited:
            return
        visited.add(profile.id)
        
        # Determine root resource type if not set
        if not root_resource_type:
            root_resource_type = self._extract_root_resource_type(profile.id)
        
        for field_id, field in profile.fields.items():
            field_path = field.path
            if not field_path:
                continue
            
            types = field.types
            fixed_value = field.fixed_value
            fixed_value_type = field.fixed_value_type
            
            # Build full path
            full_path = path_prefix + field_path if path_prefix else field_path
            if full_path.startswith('.'):
                full_path = full_path[1:]
            if root_resource_type and not full_path.startswith(root_resource_type + '.'):
                full_path = root_resource_type + '.' + full_path
            
            is_resource_field = field_path.lower().endswith('.resource')
            
            # Check for fixedUri/fixedCanonical references to other profiles
            unresolved_ref = None
            if fixed_value and fixed_value_type in ('fixedUri', 'fixedCanonical'):
                fixed_url = str(fixed_value)

                # Only resolve StructureDefinition references
                is_structure_def_ref = (
                    'StructureDefinition' in fixed_url or
                    ('/fhir/' in fixed_url and
                     not self._is_non_recursive_reference(fixed_url))
                )

                if is_structure_def_ref and fixed_url.startswith(('http://', 'https://')):
                    referenced_profile = self._resolve_profile_by_url(
                        fixed_url, profile_by_id, profile_by_url
                    )
                    
                    if referenced_profile:
                        # Recursively load referenced profile
                        self._load_fields_recursive(
                            profile=referenced_profile,
                            profile_key=profile_key,
                            path_prefix=full_path,
                            root_resource_type=root_resource_type,
                            visited=visited,
                            profile_by_id=profile_by_id,
                            profile_by_url=profile_by_url,
                            resource_fields=resource_fields,
                            value_fields=value_fields,
                            unresolved_references=unresolved_references
                        )
                    else:
                        unresolved_ref = fixed_url
                        if fixed_url not in unresolved_references:
                            unresolved_references.append(fixed_url)
                            logger.warning(f"Could not resolve profile reference: {fixed_url}")
            
            # Create resolved field
            resolved_field = ResolvedProfileField(
                min=field.min,
                max=field.max,
                must_support=field.must_support,
                types=types,
                ref_types=field.ref_types,
                cardinality_note=None,
                fixed_value=fixed_value,
                fixed_value_type=fixed_value_type,
                full_path=full_path,
                source_profile_id=profile.id,
                source_profile_key=profile.key,
                unresolved_reference=unresolved_ref,
                is_resource_field=is_resource_field
            )
            
            # Categorize field
            if is_resource_field:
                resource_fields.append(resolved_field)
                
                # Try to load referenced profile from type_profiles (primary mechanism)
                type_profiles = field.type_profiles
                if type_profiles:
                    for profile_url in type_profiles:
                        # Skip non-StructureDefinition references
                        if self._is_non_recursive_reference(profile_url):
                            continue
                        
                        ref_profile = self._resolve_profile_by_url(
                            profile_url, profile_by_id, profile_by_url
                        )
                        if ref_profile:
                            # Reset visited for the new profile's context
                            # (each resource entry can independently reference the same profile)
                            local_visited = visited.copy()
                            self._load_fields_recursive(
                                profile=ref_profile,
                                profile_key=profile_key,
                                path_prefix=full_path,
                                root_resource_type=root_resource_type,
                                visited=local_visited,
                                profile_by_id=profile_by_id,
                                profile_by_url=profile_by_url,
                                resource_fields=resource_fields,
                                value_fields=value_fields,
                                unresolved_references=unresolved_references
                            )
                        else:
                            if profile_url not in unresolved_references:
                                unresolved_references.append(profile_url)
                                logger.warning(f"Could not resolve type profile reference: {profile_url}")
                elif types:
                    # Fallback: try to resolve using type code (legacy behavior)
                    resource_type = types[0]
                    ref_profile = profile_by_id.get(resource_type) or self._resolve_profile_by_url(
                        resource_type, profile_by_id, profile_by_url
                    )
                    if ref_profile:
                        self._load_fields_recursive(
                            profile=ref_profile,
                            profile_key=profile_key,
                            path_prefix=full_path,
                            root_resource_type=root_resource_type,
                            visited=visited,
                            profile_by_id=profile_by_id,
                            profile_by_url=profile_by_url,
                            resource_fields=resource_fields,
                            value_fields=value_fields,
                            unresolved_references=unresolved_references
                        )
            else:
                value_fields.append(resolved_field)

    def new_from_file_upload(self, proj_key: str, file: UploadFile) -> PackageModel:
        if file.content_type != "application/gzip":
            raise InvalidFileFormat()

        # Get project
        proj = self.project_handler._get(proj_key)

        with TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)

            # Write the package file to temp dir
            tmp_pkg_file = tmp / "package.tgz"
            tmp_pkg_file.write_bytes(file.file.read())

            with tarfile.open(tmp_pkg_file) as tar_file:
                tar_file.extractall(tmp)

            pkg_info_file = tmp / "package/package.json"

            if not pkg_info_file.exists():
                raise PackageCorrupted()

            pkg_info = json.loads(pkg_info_file.read_text(encoding="utf-8"))

            # try to find first StructureDefintion to determine if package has snapshots
            for f in (tmp / "package").glob("**/*.json"):
                content = json.loads(f.read_text(encoding="utf-8"))
                if content.get(
                    "resourceType"
                ) == "StructureDefinition" and not content.get("snapshot"):
                    raise PackageNoSnapshots()

            # Create package directory below project directory
            pkg_dir = Path(proj.data_dir) / f"{pkg_info['name']}#{pkg_info['version']}"

            if pkg_dir.exists():
                raise PackageAlreadyExists()

            pkg_dir.mkdir()

            # Move package contents to package directory
            shutil.copytree(tmp / "package", pkg_dir / "package")

        pkg = Package(pkg_dir, proj)
        proj.pkgs.append(pkg)

        return pkg.to_model()

    def download_from_registry(
        self, proj_key: str, package_name: str, version: str
    ) -> PackageDownloadResultModel:
        """
        Download a FHIR package from official registries and add it to the project.

        Tries multiple registries in order until one succeeds.
        The package must contain snapshots for StructureDefinitions.

        Args:
            proj_key: Project key to add the package to
            package_name: FHIR package name (e.g., "kbv.basis")
            version: Package version (e.g., "1.7.0")

        Returns:
            PackageDownloadResult with success status and details
        """
        package_key = f"{package_name}#{version}"
        proj = self.project_handler._get(proj_key)

        # Check if package already exists
        existing_pkg = proj.get_package(package_key)
        if existing_pkg:
            return PackageDownloadResultModel(
                success=False,
                package_key=package_key,
                message=f"Package {package_key} already exists in project",
                registry_url=None,
                package=existing_pkg.to_model(),
            )

        # Try each registry until one succeeds
        last_error = None
        for registry_url in FHIR_REGISTRIES:
            try:
                result = self._download_from_single_registry(
                    proj, package_name, version, registry_url
                )
                if result.success:
                    return result
            except Exception as e:
                last_error = e
                logger.warning(
                    f"Failed to download {package_key} from {registry_url}: {e}"
                )
                continue

        # All registries failed
        error_msg = f"Package {package_key} not found in any registry"
        if last_error:
            error_msg += f": {last_error}"

        return PackageDownloadResultModel(
            success=False,
            package_key=package_key,
            message=error_msg,
            registry_url=None,
            package=None,
        )

    def _download_from_single_registry(
        self,
        proj,
        package_name: str,
        version: str,
        registry_url: str,
    ) -> PackageDownloadResultModel:
        """
        Download a package from a single registry.

        Args:
            proj: Project to add the package to
            package_name: Package name
            version: Package version
            registry_url: Registry base URL

        Returns:
            PackageDownloadResult
        """
        package_key = f"{package_name}#{version}"
        download_url = f"{registry_url}/{package_name}/{version}"

        logger.info(f"Attempting to download {package_key} from {download_url}")

        # Download the package tarball
        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            response = client.get(download_url)

            if response.status_code == 404:
                return PackageDownloadResultModel(
                    success=False,
                    package_key=package_key,
                    message=f"Package not found at {registry_url}",
                    registry_url=registry_url,
                    package=None,
                )

            if response.status_code != 200:
                return PackageDownloadResultModel(
                    success=False,
                    package_key=package_key,
                    message=f"HTTP {response.status_code} from {registry_url}",
                    registry_url=registry_url,
                    package=None,
                )

            package_data = response.content

        # Process the downloaded tarball
        with TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            tmp_pkg_file = tmp / "package.tgz"
            tmp_pkg_file.write_bytes(package_data)

            try:
                with tarfile.open(tmp_pkg_file) as tar_file:
                    tar_file.extractall(tmp)
            except tarfile.TarError as e:
                return PackageDownloadResultModel(
                    success=False,
                    package_key=package_key,
                    message=f"Failed to extract package: {e}",
                    registry_url=registry_url,
                    package=None,
                )

            pkg_info_file = tmp / "package/package.json"
            if not pkg_info_file.exists():
                return PackageDownloadResultModel(
                    success=False,
                    package_key=package_key,
                    message="Package is corrupted (missing package.json)",
                    registry_url=registry_url,
                    package=None,
                )

            pkg_info = json.loads(pkg_info_file.read_text(encoding="utf-8"))

            # Check for snapshots in StructureDefinitions
            has_structure_definitions = False
            missing_snapshots = False
            for f in (tmp / "package").glob("**/*.json"):
                try:
                    content = json.loads(f.read_text(encoding="utf-8"))
                    if content.get("resourceType") == "StructureDefinition":
                        has_structure_definitions = True
                        if not content.get("snapshot"):
                            missing_snapshots = True
                            break
                except json.JSONDecodeError:
                    continue

            if has_structure_definitions and missing_snapshots:
                return PackageDownloadResultModel(
                    success=False,
                    package_key=package_key,
                    message="Package does not contain snapshots for StructureDefinitions",
                    registry_url=registry_url,
                    package=None,
                )

            # Create package directory
            pkg_dir = Path(proj.data_dir) / f"{pkg_info['name']}#{pkg_info['version']}"

            if pkg_dir.exists():
                return PackageDownloadResultModel(
                    success=False,
                    package_key=package_key,
                    message="Package directory already exists",
                    registry_url=registry_url,
                    package=None,
                )

            pkg_dir.mkdir()
            shutil.copytree(tmp / "package", pkg_dir / "package")

        # Create Package object and add to project
        pkg = Package(pkg_dir, proj)
        proj.pkgs.append(pkg)

        logger.info(f"Successfully downloaded and installed {package_key} from {registry_url}")

        return PackageDownloadResultModel(
            success=True,
            package_key=package_key,
            message=f"Successfully downloaded from {registry_url}",
            registry_url=registry_url,
            package=pkg.to_model(),
        )

    def download_multiple_from_registry(
        self, proj_key: str, packages: list[tuple[str, str]]
    ) -> list[PackageDownloadResultModel]:
        """
        Download multiple packages from registries.

        Args:
            proj_key: Project key
            packages: List of (package_name, version) tuples

        Returns:
            List of download results
        """
        results = []
        for package_name, version in packages:
            result = self.download_from_registry(proj_key, package_name, version)
            results.append(result)
        return results

