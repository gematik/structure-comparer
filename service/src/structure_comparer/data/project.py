from pathlib import Path
from typing import Dict, Optional

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

        self.mappings: Dict[str, Mapping] = {}
        self.comparisons: Dict[str, Comparison] = {}
        self.manual_entries: ManualEntries = ManualEntries()
        self.pkgs: list[Package] = []

        self._load_packages()
        self._load_comparisons()
        self._load_mappings()
        self._read_manual_entries()

    def _load_packages(self) -> None:
        # Trigger creation of data_dir via property
        data_dir = self.data_dir  # <- erstellt Verzeichnis dank Property

        # Load packages from config
        self.pkgs = [Package(data_dir, self, cfg) for cfg in self.config.packages]

        # Add any local packages not yet in config
        for dir in self.data_dir.iterdir():
            if dir.is_dir():
                try:
                    name, version = dir.name.split("#", maxsplit=1)
                except ValueError:
                    continue  # skip invalid folder names

                if not self._has_package(name, version):
                    if (dir / "package/package.json").exists():
                        self.pkgs.append(Package(dir, self))
                    else:
                        new_cfg = PackageConfig(name=name, version=version)
                        self.config.packages.append(new_cfg)
                        self.config.write()
                        self.pkgs.append(Package(dir, self, new_cfg))

    def _load_comparisons(self) -> None:
        self.comparisons = {
            cmp.id: Comparison(cmp, self).init_ext() for cmp in self.config.comparisons
        }

    def _load_mappings(self) -> None:
        self.mappings = {
            mp.id: Mapping(mp, self).init_ext() for mp in self.config.mappings
        }

    def _read_manual_entries(self) -> None:
        manual_file = self.dir / self.config.manual_entries_file
        manual_file.touch(exist_ok=True)

        self.manual_entries.read(manual_file)
        self.manual_entries.write()

    @staticmethod
    def create(path: Path, project_name: str) -> "Project":
        path.mkdir(parents=True, exist_ok=True)

        (path / "manual_entries.yaml").touch()

        config = ProjectConfig(name=project_name)
        config._file_path = path / "config.json"
        config.write()

        return Project(path)

    @property
    def name(self) -> str:
        return self.config.name

    @name.setter
    def name(self, value: str) -> None:
        self.config.name = value
        self.config.write()

    @property
    def key(self) -> str:
        return self.dir.name

    @property
    def url(self) -> str:
        return f"/project/{self.key}"

    @property
    def data_dir(self) -> Path:
        data_path = self.dir / self.config.data_dir
        data_path.mkdir(parents=True, exist_ok=True)
        return data_path

    def write_config(self) -> None:
        self.config.write()

    def get_package(self, id: str) -> Optional[Package]:
        return next((pkg for pkg in self.pkgs if pkg.id == id), None)

    def get_profile(self, id: str, url: str, version: str):
        for pkg in self.pkgs:
            for profile in pkg.profiles:
                if (
                    profile.id == id or profile.url == url
                ) and profile.version == version:
                    return profile
        return None

    def _has_package(self, name: str, version: str) -> bool:
        return any(p.name == name and p.version == version for p in self.pkgs)

    def to_model(self) -> ProjectModel:
        return ProjectModel(
            name=self.name,
            mappings=[m.to_base_model() for m in self.mappings.values()],
            comparisons=[c.to_overview_model() for c in self.comparisons.values()],
            packages=[p.to_model() for p in self.pkgs],
        )

    def to_overview_model(self) -> ProjectOverviewModel:
        return ProjectOverviewModel(name=self.name, url=self.url)
