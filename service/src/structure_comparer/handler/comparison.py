from ..model.comparison import ComparisonList as ComparisonListModel
from .project import ProjectsHandler


class ComparisonHandler:
    def __init__(self, project_handler: ProjectsHandler):
        self.project_handler: ProjectsHandler = project_handler

    def get_list(self, project_key) -> ComparisonListModel:
        p = self.project_handler._get(project_key)
        cs = [c.to_base_model() for c in p.comparisons.values()]
        return ComparisonListModel(comparisons=cs)

    def get(self, project_key, comparison_id):
        pass

    def create(self, project_key, input):
        pass

    def update(self, project_key, comparison_id, input):
        pass

    def delete(self, project_key, comparison_id):
        pass
