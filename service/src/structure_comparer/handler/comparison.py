from uuid import uuid4

from ..data.config import ComparisonConfig
from ..data.config import ComparisonProfileConfig as ComparisonProfileConfigModel
from ..data.config import ComparisonProfilesConfig
from ..model.comparison import ComparisonCreate as ComparisonCreateModel
from ..model.comparison import ComparisonList as ComparisonListModel
from .project import ProjectsHandler


class ComparisonHandler:
    def __init__(self, project_handler: ProjectsHandler):
        self.project_handler: ProjectsHandler = project_handler

    def get_list(self, project_key) -> ComparisonListModel:
        p = self.project_handler._get(project_key)
        cs = [c.to_overview_model() for c in p.comparisons.values()]
        return ComparisonListModel(comparisons=cs)

    def get(self, project_key, comparison_id):
        pass

    def create(self, project_key, input: ComparisonCreateModel):
        p = self.project_handler._get(project_key)

        pc = ComparisonProfilesConfig(
            sourceprofiles=[_to_profiles_config(id) for id in input.source_ids],
            targetprofile=_to_profiles_config(input.target_id),
        )
        cc = ComparisonConfig(id=str(uuid4()), comparison=pc)

        # Workaround for appending existing list is interpreted as unset
        if not p.config.comparisons:
            p.config.comparisons = []

        p.config.comparisons.append(cc)
        p.config.write()

        p.load_comparisons()

        return p.comparisons[cc.id].to_overview_model()

    def update(self, project_key, comparison_id, input):
        pass

    def delete(self, project_key, comparison_id):
        pass


def _to_profiles_config(url: str) -> ComparisonProfileConfigModel:
    url, version = url.split("|")
    return ComparisonProfileConfigModel(url=url, version=version)
