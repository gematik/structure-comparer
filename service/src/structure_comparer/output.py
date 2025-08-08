from .errors import (
    MappingNotFound,
    ProjectNotFound,
)

from .model.error import Error as ErrorModel
from structure_comparer.data.config import ProjectConfig
from .handler.mapping import MappingHandler, ProjectsHandler


def output(project_dir: str, output_format: str = "html", mapping_id: str = None):
    print("Generating output files...")

    try:
        config = ProjectConfig.from_json(project_dir / "config.json")

        project_key = config.name
        show_remarks = config.show_remarks
        show_warnings = config.show_warnings

        for mapping in config.mappings:
            if mapping.id == mapping_id or mapping_id is None:
                print(f"Processing mapping: {mapping.id}")
                project_handler = ProjectsHandler(project_dir)
                project_handler.load()
                mapping_handler = MappingHandler(project_handler)

                html_output_dir = project_dir / config.html_output_dir
                if not html_output_dir.exists():
                    html_output_dir.mkdir(parents=True, exist_ok=True)

                if output_format == "html":
                    print(f"Generating HTML for mapping: {mapping.id}")
                    mapping_handler.get_html(
                        project_key,
                        mapping.id,
                        show_remarks,
                        show_warnings,
                        html_output_dir,
                    ),
                elif output_format == "json":
                    raise NotImplementedError("JSON not implemented yet")

    except (ProjectNotFound, MappingNotFound, NotImplementedError) as e:
        return ErrorModel.from_except(e)

    print("Output files generated successfully.")


if __name__ == "__main__":
    output()
