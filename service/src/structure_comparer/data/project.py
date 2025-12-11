from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging

from ..manual_entries import ManualEntries
from ..model.project import Project as ProjectModel
from ..model.project import ProjectOverview as ProjectOverviewModel
from ..model.package import PackageStatus
from .comparison import Comparison
from .config import PackageConfig, ProjectConfig
from .mapping import Mapping
from .package import Package
from .transformation import Transformation
from .target_creation import TargetCreation


logger = logging.getLogger(__name__)


class Project:
    def __init__(self, path: Path):
        self.dir = path
        self.config = ProjectConfig.from_json(path / "config.json")

        self.mappings: Dict[str, Mapping]
        self.comparisons: Dict[str, Comparison]
        self.transformations: Dict[str, Transformation]
        self.target_creations: Dict[str, TargetCreation]
        self.manual_entries: ManualEntries

        self.pkgs: list[Package]

        # Sicherstellen, dass die benötigte Struktur vorhanden ist
        self._ensure_structure()

        self.__load_packages()
        self.load_comparisons()
        self.load_mappings()
        self.__read_manual_entries()
        self.load_transformations()
        self.load_target_creations()

    def _ensure_structure(self) -> None:
        """
        Stellt sicher, dass das Projektverzeichnis und der data-Ordner existieren.
        """
        self.dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def __safe_parse_pkg_dirname(self, dirname: str) -> Optional[Tuple[str, str]]:
        """
        Erwartet <name>#<version>. Gibt (name, version) zurück oder None, wenn das Format nicht passt.
        """
        if "#" not in dirname:
            return None
        parts = dirname.split("#", 1)
        if len(parts) != 2 or not parts[0] or not parts[1]:
            return None
        return parts[0], parts[1]

    def __load_packages(self) -> None:
        """
        Load packages from config.json and auto-migrate orphaned packages.
        
        This method implements a hybrid approach for backwards compatibility:
        1. Load packages defined in config.json
        2. Auto-adopt orphaned packages (in data folder but not in config)
        
        Each package gets a status:
        - AVAILABLE: Package is in config AND downloaded in data folder
        - MISSING: Package is in config but NOT downloaded yet
        
        During migration phase, orphaned packages are automatically added to config.
        """
        self.pkgs = []
        config_keys = {f"{p.name}#{p.version}" for p in self.config.packages}
        
        # Step 1: Load packages from config
        for pkg_config in self.config.packages:
            pkg_key = f"{pkg_config.name}#{pkg_config.version}"
            pkg_dir = self.data_dir / pkg_key
            
            # Check if package is actually downloaded
            if pkg_dir.exists() and (pkg_dir / "package" / "package.json").exists():
                # Package is available - load from disk
                self.pkgs.append(Package(pkg_dir, self, pkg_config, PackageStatus.AVAILABLE))
                logger.debug(f"Package {pkg_key} loaded (available)")
            else:
                # Package is in config but not downloaded - create placeholder
                self.pkgs.append(Package.from_config_only(pkg_config, self))
                logger.debug(f"Package {pkg_key} registered (missing)")
        
        # Step 2: Auto-migrate orphaned packages (backwards compatibility)
        # This ensures existing projects continue to work without manual migration
        if self.data_dir.exists():
            migrated_count = 0
            for dir in self.data_dir.iterdir():
                if not dir.is_dir():
                    continue
                
                parsed = self.__safe_parse_pkg_dirname(dir.name)
                if parsed is None:
                    continue
                
                name, version = parsed
                pkg_key = f"{name}#{version}"
                
                # Skip if already in config
                if pkg_key in config_keys:
                    continue
                
                # Check if it's a valid FHIR package
                if not (dir / "package" / "package.json").exists():
                    continue
                
                # Auto-adopt: Add to config and load
                pkg_config = PackageConfig(name=name, version=version)
                self.config.packages.append(pkg_config)
                config_keys.add(pkg_key)
                
                self.pkgs.append(Package(dir, self, pkg_config, PackageStatus.AVAILABLE))
                logger.info(f"Auto-migrated orphaned package {pkg_key} into config")
                migrated_count += 1
            
            # Save config if we migrated any packages
            if migrated_count > 0:
                self.config.write()
                logger.info(f"Auto-migrated {migrated_count} orphaned packages into config")

    def get_orphaned_packages(self) -> List[str]:
        """
        Find packages in data folder that are NOT in config.
        
        These are packages that were downloaded but later removed from config,
        or packages that were manually placed in the data folder.
        
        Returns:
            List of package keys (name#version) that are orphaned.
        """
        orphaned = []
        config_keys = {f"{p.name}#{p.version}" for p in self.config.packages}
        
        if not self.data_dir.exists():
            return orphaned
        
        for dir in self.data_dir.iterdir():
            if not dir.is_dir():
                continue
            
            parsed = self.__safe_parse_pkg_dirname(dir.name)
            if parsed is None:
                # Unknown directory format in data folder - skip
                continue
            
            # Check if this package is NOT in config
            if dir.name not in config_keys:
                # Only count as orphaned if it has a valid package.json
                if (dir / "package" / "package.json").exists():
                    orphaned.append(dir.name)
                    logger.debug(f"Found orphaned package: {dir.name}")
        
        return orphaned

    def load_comparisons(self):
        self.comparisons = {
            c.id: Comparison(c, self).init_ext() for c in self.config.comparisons
        }

    def load_mappings(self):
        self.mappings = {
            m.id: Mapping(m, self).init_ext() for m in self.config.mappings
        }

    def load_transformations(self):
        """Load all transformations from config."""
        if not self.config.transformations:
            self.transformations = {}
            return

        self.transformations = {
            t.id: Transformation(t, self).init_ext()
            for t in self.config.transformations
        }

    def load_target_creations(self):
        """Load all target creations from config."""
        if not self.config.target_creations:
            self.target_creations = {}
            return

        self.target_creations = {
            tc.id: TargetCreation(tc, self).init_ext()
            for tc in self.config.target_creations
        }

    def __read_manual_entries(self):
        manual_entries_file = self.dir / self.config.manual_entries_file

        if not manual_entries_file.exists():
            manual_entries_file.touch()

        self.manual_entries = ManualEntries()
        self.manual_entries.read(manual_entries_file)
        self.manual_entries.write()

    @staticmethod
    def create(path: Path, project_name: str) -> "Project":
        path.mkdir(parents=True, exist_ok=True)

        # Default-Konfiguration vorbereiten (liefert u. a. data_dir-Name)
        config_data = ProjectConfig(name=project_name)

        # data-Verzeichnis gemäß Config sicherstellen
        data_dir = path / config_data.data_dir
        data_dir.mkdir(parents=True, exist_ok=True)

        # Leere manual_entries.yaml anlegen
        manual_entries_file = path / config_data.manual_entries_file
        manual_entries_file.touch()

        # config.json schreiben
        config_data._file_path = path / "config.json"
        config_data.write()

        return Project(path)

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def key(self) -> str:
        return self.dir.name

    @property
    def url(self) -> str:
        return "/project/" + self.key

    @name.setter
    def name(self, value: str):
        self.config.name = value
        self.config.write()

    @property
    def data_dir(self) -> Path:
        return self.dir / self.config.data_dir

    def write_config(self):
        self.config.write()

    def get_package(self, id: str) -> Package | None:
        for pkg in self.pkgs:
            if pkg.id == id:
                return pkg
        return None

    def get_mapping(self, mapping_id: str) -> 'Mapping':
        """Get mapping by ID from loaded mappings"""
        return self.mappings.get(mapping_id)

    def get_profile(self, id: str, url: str, version: str):
        for pkg in self.pkgs:
            for profile in pkg.profiles:
                if (
                    profile.id == id or profile.url == url
                ) and profile.version == version:
                    return profile
        return None

    def __has_pkg(self, name: str, version: str) -> bool:
        return any([p.name == name and p.version == version for p in self.pkgs])

    def to_model(self) -> ProjectModel:
        mappings = [m.to_base_model() for m in self.mappings.values()]
        pkgs = [p.to_model() for p in self.pkgs]
        comparisons = [c.to_overview_model() for c in self.comparisons.values()]
        transformations = [t.to_base_model() for t in self.transformations.values()]
        target_creations = [tc.to_base_model() for tc in self.target_creations.values()]

        return ProjectModel(
            name=self.name,
            version=self.config.version,
            status=self.config.status,
            mappings=mappings,
            comparisons=comparisons,
            transformations=transformations,
            target_creations=target_creations,
            packages=pkgs
        )

    def to_overview_model(self) -> ProjectOverviewModel:
        return ProjectOverviewModel(
            name=self.name,
            url=self.url,
            version=self.config.version,
            status=self.config.status
        )
