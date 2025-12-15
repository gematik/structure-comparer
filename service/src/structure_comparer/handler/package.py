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
from ..model.package import (
    PackageStatus,
    PackageWithStatus as PackageWithStatusModel,
    PackageListWithStatus as PackageListWithStatusModel,
    PackageAddRequest as PackageAddRequestModel,
    PackageAddResult as PackageAddResultModel,
    OrphanedCleanupResult as OrphanedCleanupResultModel,
    OrphanedAdoptResult as OrphanedAdoptResultModel,
    BatchDownloadResult as BatchDownloadResultModel,
)
from ..model.profile import ProfileList as ProfileListModel
from ..model.profile import ProfileDetails as ProfileDetailsModel
from ..model.profile import ResolvedProfileField, ResolvedProfileFieldsResponse
from .project import ProjectsHandler
from ..data.config import PackageConfig

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

    def _register_installed_package(
        self,
        proj,
        package_name: str,
        version: str,
        pkg_dir: Path,
    ) -> Package:
        """Attach a downloaded package to the project and config, replacing placeholders."""
        # Try to find existing config entry
        pkg_config = next(
            (
                cfg
                for cfg in proj.config.packages
                if cfg.name == package_name and cfg.version == version
            ),
            None,
        )

        config_added = False
        if pkg_config is None:
            pkg_config = PackageConfig(name=package_name, version=version)
            proj.config.packages.append(pkg_config)
            config_added = True

        pkg = Package(pkg_dir, proj, pkg_config, PackageStatus.AVAILABLE)

        # Replace existing placeholder or append as new package
        pkg_key = pkg.key
        for idx, existing in enumerate(proj.pkgs):
            if existing.key == pkg_key:
                proj.pkgs[idx] = pkg
                break
        else:
            proj.pkgs.append(pkg)

        if config_added:
            proj.config.write()

        return pkg

    def get_list(self, proj_key: str) -> PackageListModel:
        proj = self.project_handler._get(proj_key)
        pkgs = [p.to_model() for p in proj.pkgs]
        return PackageListModel(packages=pkgs)

    def get_list_with_status(self, proj_key: str) -> PackageListWithStatusModel:
        """
        Get all packages with their status (available/missing/orphaned).
        
        This includes:
        - Packages from config that are downloaded (AVAILABLE)
        - Packages from config that are NOT downloaded (MISSING)
        - Packages in data folder that are NOT in config (ORPHANED)
        """
        proj = self.project_handler._get(proj_key)
        
        packages = []
        
        # Add packages from config (AVAILABLE or MISSING)
        for pkg in proj.pkgs:
            packages.append(pkg.to_model_with_status())
        
        # Add orphaned packages (in data folder but not in config)
        orphaned_keys = proj.get_orphaned_packages()
        for key in orphaned_keys:
            name, version = key.split("#", 1)
            packages.append(PackageWithStatusModel(
                id=key,
                name=name,
                version=version,
                display=None,
                status=PackageStatus.ORPHANED
            ))
        
        # Calculate statistics
        available = sum(1 for p in packages if p.status == PackageStatus.AVAILABLE)
        missing = sum(1 for p in packages if p.status == PackageStatus.MISSING)
        orphaned = len(orphaned_keys)
        
        return PackageListWithStatusModel(
            packages=packages,
            total=len(packages),
            available=available,
            missing=missing,
            orphaned=orphaned
        )

    def add_to_config(
        self, proj_key: str, request: PackageAddRequestModel
    ) -> PackageAddResultModel:
        """
        Add a package to config without downloading.
        
        The package will have status MISSING until downloaded.
        """
        proj = self.project_handler._get(proj_key)
        
        # Check if package already exists in config
        pkg_key = f"{request.name}#{request.version}"
        existing_keys = {f"{p.name}#{p.version}" for p in proj.config.packages}
        
        if pkg_key in existing_keys:
            return PackageAddResultModel(
                success=False,
                package=None,
                message=f"Package {pkg_key} already exists in config"
            )
        
        # Add to config
        pkg_config = PackageConfig(
            name=request.name,
            version=request.version,
            display=request.display
        )
        proj.config.packages.append(pkg_config)
        proj.config.write()
        
        # Determine status (might already be downloaded as orphaned)
        pkg_dir = proj.data_dir / pkg_key
        if pkg_dir.exists() and (pkg_dir / "package" / "package.json").exists():
            status = PackageStatus.AVAILABLE
            # Create proper package object and add to pkgs
            pkg = Package(pkg_dir, proj, pkg_config, PackageStatus.AVAILABLE)
            proj.pkgs.append(pkg)
        else:
            status = PackageStatus.MISSING
            # Create placeholder package
            pkg = Package.from_config_only(pkg_config, proj)
            proj.pkgs.append(pkg)
        
        logger.info(f"Added package {pkg_key} to config with status {status}")
        
        return PackageAddResultModel(
            success=True,
            package=PackageWithStatusModel(
                id=pkg_key,
                name=request.name,
                version=request.version,
                display=request.display,
                status=status
            ),
            message=f"Package {pkg_key} added to config"
        )

    def remove_from_config(self, proj_key: str, package_id: str) -> bool:
        """
        Remove a package from config (files remain in data folder as orphaned).
        """
        proj = self.project_handler._get(proj_key)
        
        name, version = package_id.split("#", 1)
        
        # Find and remove from config
        original_count = len(proj.config.packages)
        proj.config.packages = [
            p for p in proj.config.packages
            if not (p.name == name and p.version == version)
        ]
        
        if len(proj.config.packages) == original_count:
            raise PackageNotFound()
        
        proj.config.write()
        
        # Remove from pkgs list
        proj.pkgs = [p for p in proj.pkgs if p.key != package_id]
        
        logger.info(f"Removed package {package_id} from config")
        return True

    def delete_files(self, proj_key: str, package_id: str) -> bool:
        """
        Delete package files from data folder.
        
        Note: This does NOT remove the package from config.
        Use remove_from_config first if you want to remove completely.
        """
        proj = self.project_handler._get(proj_key)
        pkg_dir = proj.data_dir / package_id
        
        if not pkg_dir.exists():
            raise PackageNotFound()
        
        shutil.rmtree(pkg_dir)
        logger.info(f"Deleted package files for {package_id}")
        
        # If package is in config, update its status to MISSING
        for i, pkg in enumerate(proj.pkgs):
            if pkg.key == package_id:
                # Find config entry
                for cfg in proj.config.packages:
                    if f"{cfg.name}#{cfg.version}" == package_id:
                        # Replace with missing placeholder
                        proj.pkgs[i] = Package.from_config_only(cfg, proj)
                        break
                break
        
        return True

    def cleanup_orphaned(self, proj_key: str) -> OrphanedCleanupResultModel:
        """
        Delete all orphaned packages (in data folder but not in config).
        """
        proj = self.project_handler._get(proj_key)
        orphaned_keys = proj.get_orphaned_packages()
        
        deleted = []
        for key in orphaned_keys:
            pkg_dir = proj.data_dir / key
            if pkg_dir.exists():
                shutil.rmtree(pkg_dir)
                deleted.append(key)
                logger.info(f"Deleted orphaned package {key}")
        
        return OrphanedCleanupResultModel(
            success=True,
            deleted=deleted,
            count=len(deleted)
        )

    def adopt_orphaned(self, proj_key: str) -> OrphanedAdoptResultModel:
        """
        Adopt all orphaned packages into config.
        
        This adds config entries for packages that are in data folder
        but not in config.
        """
        proj = self.project_handler._get(proj_key)
        orphaned_keys = proj.get_orphaned_packages()
        
        adopted = []
        for key in orphaned_keys:
            name, version = key.split("#", 1)
            pkg_config = PackageConfig(name=name, version=version)
            proj.config.packages.append(pkg_config)
            
            # Create package object
            pkg_dir = proj.data_dir / key
            pkg = Package(pkg_dir, proj, pkg_config, PackageStatus.AVAILABLE)
            proj.pkgs.append(pkg)
            
            adopted.append(key)
            logger.info(f"Adopted orphaned package {key} into config")
        
        proj.config.write()
        
        return OrphanedAdoptResultModel(
            success=True,
            adopted=adopted,
            count=len(adopted)
        )

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

        profs = []
        for pkg in proj.pkgs:
            for prof in pkg.profiles:
                if prof is None:
                    continue
                model = prof.to_pkg_model()
                if model is None:
                    logger.warning(
                        "Skipping profile %s in package %s due to validation error",
                        getattr(prof, "id", "<unknown>"),
                        getattr(pkg, "key", "<unknown>"),
                    )
                    continue
                profs.append(model)
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
        # Accept various content types for gzip/tarball files
        valid_content_types = {
            "application/gzip",
            "application/x-gzip",
            "application/x-tar",
            "application/x-compressed-tar",
            "application/octet-stream",  # Fallback for unknown types
        }
        
        # Check content type or file extension
        filename = file.filename or ""
        is_valid_extension = filename.endswith(".tgz") or filename.endswith(".tar.gz")
        is_valid_content_type = file.content_type in valid_content_types
        
        logger.info(f"Package upload: filename='{filename}', content_type='{file.content_type}'")
        logger.debug(f"Valid extension: {is_valid_extension}, Valid content type: {is_valid_content_type}")
        
        if not (is_valid_content_type or is_valid_extension):
            logger.error(f"Invalid file format: content_type='{file.content_type}', filename='{filename}'")
            raise InvalidFileFormat()

        # Get project
        proj = self.project_handler._get(proj_key)
        logger.info(f"Uploading package to project: {proj_key}")

        with TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)

            # Write the package file to temp dir
            tmp_pkg_file = tmp / "package.tgz"
            file_content = file.file.read()
            logger.info(f"Read {len(file_content)} bytes from uploaded file")
            tmp_pkg_file.write_bytes(file_content)

            try:
                with tarfile.open(tmp_pkg_file) as tar_file:
                    tar_file.extractall(tmp)
                logger.info(f"Extracted tarball to {tmp}")
            except Exception as e:
                logger.error(f"Failed to extract tarball: {e}")
                raise PackageCorrupted()

            pkg_info_file = tmp / "package/package.json"

            if not pkg_info_file.exists():
                logger.error(f"package.json not found at {pkg_info_file}")
                raise PackageCorrupted()

            pkg_info = json.loads(pkg_info_file.read_text(encoding="utf-8"))
            logger.info(f"Package info: name='{pkg_info.get('name')}', version='{pkg_info.get('version')}'")

            # Check StructureDefinitions for snapshots
            # We allow packages with some StructureDefinitions without snapshots (e.g., abstract models like FiveWs)
            # as long as the majority have snapshots
            with_snapshot = 0
            without_snapshot = 0
            without_snapshot_files = []
            
            for f in (tmp / "package").glob("**/*.json"):
                try:
                    content = json.loads(f.read_text(encoding="utf-8"))
                    if content.get("resourceType") == "StructureDefinition":
                        if content.get("snapshot"):
                            with_snapshot += 1
                        else:
                            without_snapshot += 1
                            without_snapshot_files.append(f.name)
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse JSON file {f}: {e}")
                    continue
            
            total = with_snapshot + without_snapshot
            logger.info(f"Found {total} StructureDefinitions: {with_snapshot} with snapshot, {without_snapshot} without")
            
            if without_snapshot_files:
                logger.warning(f"StructureDefinitions without snapshot: {', '.join(without_snapshot_files[:5])}{'...' if len(without_snapshot_files) > 5 else ''}")
            
            # Reject package only if NO StructureDefinitions have snapshots
            if total > 0 and with_snapshot == 0:
                logger.error(f"Package has no StructureDefinitions with snapshots")
                raise PackageNoSnapshots()

            # Create package directory below project directory
            pkg_dir = Path(proj.data_dir) / f"{pkg_info['name']}#{pkg_info['version']}"
            logger.info(f"Creating package directory: {pkg_dir}")

            if pkg_dir.exists():
                logger.error(f"Package directory already exists: {pkg_dir}")
                raise PackageAlreadyExists()

            pkg_dir.mkdir()

            # Move package contents to package directory
            shutil.copytree(tmp / "package", pkg_dir / "package")
            logger.info(f"Successfully copied package to {pkg_dir}")

        pkg = self._register_installed_package(
            proj,
            pkg_info["name"],
            pkg_info["version"],
            pkg_dir,
        )
        logger.info(f"Package {pkg_info.get('name')}#{pkg_info.get('version')} uploaded successfully")

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

        # Check if package already exists AND is available (downloaded)
        existing_pkg = proj.get_package(package_key)
        if existing_pkg and existing_pkg.is_available:
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
        pkg = self._register_installed_package(
            proj,
            pkg_info["name"],
            pkg_info["version"],
            pkg_dir,
        )

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
    ) -> BatchDownloadResultModel:
        """
        Download multiple packages from registries.

        Args:
            proj_key: Project key
            packages: List of (package_name, version) tuples

        Returns:
            BatchDownloadResult with aggregated results
        """
        results = []
        successful = 0
        failed = 0
        
        for package_name, version in packages:
            result = self.download_from_registry(proj_key, package_name, version)
            results.append(result)
            if result.success:
                successful += 1
            else:
                failed += 1
        
        return BatchDownloadResultModel(
            total_requested=len(packages),
            successful=successful,
            failed=failed,
            results=results
        )

