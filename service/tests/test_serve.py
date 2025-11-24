from pathlib import Path

from structure_comparer.data.config import ProjectConfig
from structure_comparer.data.project import Project


def test_init_project():
    project_dir = Path("tests/files/project")
    assert project_dir.exists()

    project = Project(project_dir)
    assert project is not None
    assert project.dir == project_dir

    assert project.config is not None
    assert isinstance(project.config, ProjectConfig)

    assert project.data_dir == project_dir / "data"

    assert project.mappings is not None
    assert len(project.mappings) > 0

    assert project.comparisons is not None
    assert len(project.comparisons) == len(project.mappings)

    assert project.manual_entries is not None
