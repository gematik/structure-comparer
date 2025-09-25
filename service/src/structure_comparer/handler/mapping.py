from typing import List

from ..action import Action
from ..data.mapping import MappingField
from ..data.project import Project
from ..errors import (
    FieldNotFound,
    MappingNotFound,
    MappingTargetMissing,
    MappingTargetNotFound,
    MappingValueMissing,
    ProjectNotFound,
)
from ..helpers import get_field_by_name
from ..model.manual_entries import ManualEntriesMapping
from ..model.mapping import MappingBase as MappingBaseModel
from ..model.mapping import MappingDetails as MappingDetailsModel
from ..model.mapping import MappingField as MappingFieldModel
from ..model.mapping import MappingFieldBase as MappingFieldBaseModel
from ..model.mapping import MappingFieldMinimal as MappingFieldMinimalModel
from ..model.mapping import MappingFieldsOutput as MappingFieldsOutputModel
from .project import ProjectsHandler


class MappingHandler:
    def __init__(self, project_handler: ProjectsHandler):
        self.project_handler: ProjectsHandler = project_handler

    def get_list(self, project_key: str) -> List[MappingBaseModel]:
        proj = self.project_handler._get(project_key)
        return [comp.to_base_model() for comp in proj.mappings.values()]

    def get(self, project_key: str, mapping_id: str) -> MappingDetailsModel:
        mapping = self.__get(project_key, mapping_id)
        return mapping.to_details_model()

    def get_field_list(
        self, project_key: str, mapping_id: str
    ) -> MappingFieldsOutputModel:
        mapping = self.__get(project_key, mapping_id)

        fields = [f.to_model() for f in mapping.fields.values()]

        return MappingFieldsOutputModel(id=mapping_id, fields=fields)

    def get_field(
        self, project_key: str, mapping_id: str, field_name: str
    ) -> MappingFieldModel:
        mapping = self.__get(project_key, mapping_id)

        field = get_field_by_name(mapping, field_name)

        if field is None:
            raise FieldNotFound()

        return field.to_model()

    def delete(self, project_key: str, mapping_id: str) -> None:
        proj = self.project_handler._get(project_key)

        # Check if mapping exists
        if mapping_id not in proj.mappings:
            raise MappingNotFound()

        # delete mapping from config and write
        proj.config.mappings = [
            c for c in proj.config.mappings if c.id != mapping_id
        ]
        proj.config.write()
        # Remove mapping from project's mappings
        del proj.mappings[mapping_id]

        # Clean up manual entries for this mapping if they exist
        if mapping_id in proj.manual_entries:
            del proj.manual_entries[mapping_id]
            proj.manual_entries.write()

    def set_field(
        self,
        project_key: str,
        mapping_id: str,
        field_name: str,
        input: MappingFieldMinimalModel,
    ) -> MappingFieldBaseModel:
        proj = self.project_handler._get(project_key)

        # Easiest way to get the fields is from mapping
        mapping = self.__get(project_key, mapping_id, proj)
        field = get_field_by_name(mapping, field_name)

        if field is None:
            raise FieldNotFound()

        # Check if action is allowed for this field
        if input.action not in field.actions_allowed:
            raise MappingNotFound(
                f"action '{input.action.value}' not allowed for this field, allowed: {
                    ', '.join([field.value for field in field.actions_allowed])}"
            )

        # Build the entry that should be created/updated
        new_entry = MappingFieldBaseModel(name=field.name, action=input.action)
        target: MappingField | None = None
        if new_entry.action == Action.COPY_FROM or new_entry.action == Action.COPY_TO:
            if target_id := input.other:
                target = get_field_by_name(mapping, target_id)

                if target is None:
                    raise MappingTargetNotFound()

                new_entry.other = target.name
            else:
                raise MappingTargetMissing()
        elif new_entry.action == Action.FIXED:
            if fixed := input.fixed:
                new_entry.fixed = fixed
            else:
                raise MappingValueMissing()

        # Clean up possible manual entry this was copied from before
        manual_entries = proj.manual_entries.get(mapping_id)

        if manual_entries is None:
            manual_entries = ManualEntriesMapping(id=mapping_id)
            proj.manual_entries[mapping_id] = manual_entries

        if (manual_entry := manual_entries.get(field.name)) and (
            manual_entry.action in [Action.COPY_FROM, Action.COPY_TO]
        ):
            del manual_entries[manual_entry.other]

        # Apply the manual entry
        manual_entries[field.name] = new_entry

        # Handle the partner entry for copy actions
        if new_entry.action == Action.COPY_FROM:
            manual_entries[target.name] = MappingFieldBaseModel(
                name=target.name, action=Action.COPY_TO, other=field.name
            )
        elif new_entry.action == Action.COPY_TO:
            manual_entries[target.name] = MappingFieldBaseModel(
                name=target.name, action=Action.COPY_FROM, other=field.name
            )
        # Save the changes
        proj.manual_entries.write()

        return new_entry

    def __get(self, project_key, mapping_id, proj: Project | None = None):
        if proj is None:
            proj = self.project_handler._get(project_key)

        if proj is None:
            raise ProjectNotFound()

        mapping = proj.mappings.get(mapping_id)

        if not mapping:
            raise MappingNotFound()

        mapping.fill_action_remark(proj.manual_entries)

        return mapping
