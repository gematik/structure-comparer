import re
import shutil
from pathlib import Path
from typing import Dict, List

from jinja2 import Environment, FileSystemLoader

from .action import Action
from .model.mapping import MappingDetails as MappingDetailsModel

CSS_CLASS = {
    Action.USE: "row-use",
    Action.NOT_USE: "row-not-use",
    Action.EMPTY: "row-not-use",
    Action.EXTENSION: "row-extension",
    Action.MANUAL: "row-manual",
    Action.COPY_FROM: "row-manual",
    Action.COPY_TO: "row-manual",
    Action.FIXED: "row-manual",
    Action.MEDICATION_SERVICE: "row-not-use",
}

STYLE_FILE_NAME = "style.css"
FILES_FOLDER = Path(__file__).parent / "files"


def flatten_profiles(profiles: List[str]) -> str:
    return "_".join(profiles)


# Define the custom filter function
def format_cardinality(value):
    if value == float("inf"):
        return "*"
    return value


def create_results_html(
    structured_mapping: Dict[str, MappingDetailsModel],
    results_folder: str | Path,
    show_remarks: bool,
    show_warnings: bool,
):
    # Convert to Path object if necessary
    if isinstance(results_folder, str):
        results_folder = Path(results_folder)

    # Create the results folder if it does not exist
    if not results_folder.exists():
        results_folder.mkdir(parents=True)

    # Copy the style file to the results folder
    styles_file = FILES_FOLDER / STYLE_FILE_NAME
    shutil.copy(styles_file, results_folder / STYLE_FILE_NAME)

    env = Environment(loader=FileSystemLoader(FILES_FOLDER))
    env.filters["format_links"] = format_links
    env.filters["format_cardinality"] = format_cardinality  # Register the custom filter
    template = env.get_template("template.html.j2")

    for comp in structured_mapping.values():

        entries = {}
        number_of_warnings = 0  # Initialize the warning counter

        fields = {field.name: field for field in comp.fields}
        for entry in comp.fields:  # .items():
            # field, entry
            field = entry.name
            warnings = set()  # Use a set to collect unique warnings
            if comp.target.key not in entry.profiles:
                warnings.add(
                    "The target profile does not contain this field, so it cannot be compared"
                )
                target_min_card = 0  # _cardinality
                target_max_card = 0  # _cardinality
            else:
                target_min_card = entry.profiles[comp.target.key].min  # _cardinality
                target_max_card = entry.profiles[comp.target.key].max  # _cardinality
            if target_max_card == "*":
                target_max_card = float("inf")
            else:
                target_max_card = int(target_max_card)

            match = re.search(r"[.:](?=[^.:]*$)", field)
            if match:
                parent = field[: match.start()]
            else:
                parent = field
            # parent = field.rsplit(".", 1)[0]
            comparison_parent = fields.get(parent)

            for profile in comp.sources:
                if profile.key in entry.profiles:
                    source_min_card = entry.profiles[profile.key].min  # _cardinality
                    source_max_card = entry.profiles[profile.key].max  # _cardinality
                else:
                    source_min_card = 0
                    source_max_card = 0

                if source_max_card == "*":
                    source_max_card = float("inf")
                else:
                    source_max_card = int(source_max_card)

                if comparison_parent and comparison_parent.action in [Action.USE]:
                    # Skip the specific warning if the parent is being copied or extended
                    if target_max_card < source_max_card:
                        continue

                if source_max_card > target_max_card and entry.action not in [
                    Action.COPY_TO,
                    Action.COPY_FROM,
                    Action.EXTENSION,
                ]:
                    warnings.add(
                        "The maximum cardinality of one of the source profiles exceeds the maximum cardinality of the target profile"
                    )

                # Check if source_max_card is not 0 before considering source_min_card
                if (
                    source_max_card != 0
                    and source_min_card < target_min_card
                    and entry.action
                    not in [
                        Action.COPY_TO,
                        Action.COPY_FROM,
                        Action.EXTENSION,
                    ]
                ):
                    warnings.add(
                        "The minimum cardinality of one of the source profiles is less than the minimum cardinality of the target profile"
                    )

            number_of_warnings += len(warnings)  # Increment the warning counter

            entries[field] = {
                "classification": entry.action,
                "css_class": CSS_CLASS[entry.action],
                "extension": None,  # entry.extension,
                "extra": entry.other,
                "profiles": entry.profiles,
                "remark": entry.remark,
                "warning": list(warnings),  # Convert set back to list
            }

        inline_css = (styles_file).read_text()
        data = {
            "inline_css": inline_css,
            "target_profile": {
                "key": comp.target.key,
                "url": comp.target.url,  # simplifier_url,
                "name": comp.target.name,
                "version": comp.target.version,
            },
            "source_profiles": [
                {
                    "key": profile.key,
                    "url": profile.url,  # .simplifier_url,
                    "name": profile.name,
                    "version": profile.version,
                }
                for profile in comp.sources
            ],
            "entries": entries,
            "show_remarks": show_remarks,
            "show_warnings": show_warnings,
            "number_of_warnings": number_of_warnings,  # Add the warning count to the data
            "version": comp.version,
            "last_updated": comp.last_updated,
            "status": comp.status,
        }

        content = template.render(**data)

        # HOTFIX: prevent filenames to contain '|' but use '#' instead
        html_file = (
            results_folder
            / f"{comp.name.replace("|", "#").replace(" -> ", "_to_")}.html"
        )
        html_file.write_text(content, encoding="utf-8")

        return str(html_file)


def format_links(text: str) -> str:
    if not text:
        return text

    # Regex zum Erkennen von URLs
    url_pattern = r"(https?://[\w\.\/\-\|]+)"
    # Ersetze URLs mit einem anklickbaren Link
    return re.sub(url_pattern, r'<a href="\1" target="_blank">\1</a>', text)
