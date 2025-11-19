from pathlib import Path
from typing import Dict, Optional, Tuple

from ..manual_entries import ManualEntries
from ..model.project import Project as ProjectModel
from ..model.project import ProjectOverview as ProjectOverviewModel
from .comparison import Comparison
from .config import PackageConfig, ProjectConfig
from .mapping import Mapping
from .package import Package


class Project:
    def __init__(self, path: Path):
        self.dir = path
        self.config = ProjectConfig.from_json(path / "config.json")

        self.mappings: Dict[str, Mapping]
        self.comparisons: Dict[str, Comparison]
        self.manual_entries: ManualEntries

        self.pkgs: list[Package]

        # Sicherstellen, dass die benötigte Struktur vorhanden ist
        self._ensure_structure()

        self.__load_packages()
        self.load_comparisons()
        self.load_mappings()
        self.__read_manual_entries()

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
        # Load packages from config
        self.pkgs = [Package(self.data_dir, self, p) for p in self.config.packages]

        # Defensiv: falls data_dir nicht existierte, wurde es in _ensure_structure() erstellt
        # Check for local packages not in config
        for dir in self.data_dir.iterdir():
            if not dir.is_dir():
                continue

            parsed = self.__safe_parse_pkg_dirname(dir.name)
            if parsed is None:
                # Unbekanntes Verzeichnisformat im data-Ordner -> überspringen
                continue

            name, version = parsed
            if not self.__has_pkg(name, version):
                # FHIR package bringt eigene Infos mit
                if (dir / "package" / "package.json").exists():
                    self.pkgs.append(Package(dir, self))
                else:
                    # neuen Config-Eintrag erzeugen
                    cfg = PackageConfig(name=name, version=version)
                    self.config.packages.append(cfg)
                    self.config.write()

                    # Package anlegen/anhängen
                    self.pkgs.append(Package(dir, self, cfg))

    def load_comparisons(self):
        self.comparisons = {
            c.id: Comparison(c, self).init_ext() for c in self.config.comparisons
        }

    def load_mappings(self):
        self.mappings = {
            m.id: Mapping(m, self).init_ext() for m in self.config.mappings
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

        return ProjectModel(
            name=self.name, mappings=mappings, comparisons=comparisons, packages=pkgs
        )

    def to_overview_model(self) -> ProjectOverviewModel:
        return ProjectOverviewModel(name=self.name, url=self.url)
