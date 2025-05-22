from pathlib import Path
from typing import Dict

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

        self.mappings: Dict[str, Mapping] = None
        self.comparisons: Dict[str, Comparison] = None
        self.manual_entries: ManualEntries = None

        self.pkgs: list[Package] = None

        self.__load_packages()
        self.load_comparisons()
        self.__load_mappings()
        self.__read_manual_entries()

    def __load_packages(self) -> None:
        # Load packages from config
        self.pkgs = [Package(self.data_dir, p, self) for p in self.config.packages]

        # Check for local packages not in config
        for dir in self.data_dir.iterdir():
            if dir.is_dir():
                name, version = dir.name.split("#")
                if not self.__has_pkg(name, version):
                    # Create new config entry
                    cfg = PackageConfig(name=name, version=version)
                    self.config.packages.append(cfg)
                    self.config.write()

                    # Create and append package
                    self.pkgs.append(Package(self.data_dir, cfg, self))

    def load_comparisons(self):
        self.comparisons = {
            c.id: Comparison(c, self).init_ext() for c in self.config.comparisons
        }

    def __load_mappings(self):
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

        # Create empty manual_entries.yaml file
        manual_entries_file = path / "manual_entries.yaml"
        manual_entries_file.touch()

        # Create default config.json file
        config_data = ProjectConfig(name=project_name)
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
