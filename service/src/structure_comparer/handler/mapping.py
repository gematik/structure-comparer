from datetime import datetime
from typing import List, Optional
from uuid import uuid4

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
from ..model.mapping import MappingCreate as MappingCreateModel
from ..model.mapping import MappingDetails as MappingDetailsModel
from ..model.mapping import MappingField as MappingFieldModel
from ..model.mapping import MappingFieldBase as MappingFieldBaseModel
from ..model.mapping import MappingFieldMinimal as MappingFieldMinimalModel
from ..model.mapping import MappingFieldsOutput as MappingFieldsOutputModel
from ..model.mapping import MappingUpdate as MappingUpdateModel
from ..data.config import MappingConfig as MappingConfigModel
from ..data.config import ComparisonProfilesConfig as ComparisonProfilesConfigModel
from ..data.config import ComparisonProfileConfig as ComparisonProfileConfigModel
from ..data.mapping import Mapping as MappingModel
from .project import ProjectsHandler
from ..results_html import create_results_html


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

    def get_html(
        self,
        project_key: str,
        mapping_id: str,
        show_remarks: bool,
        show_warnings: bool,
        html_output_dir: Optional[str] = None,
    ) -> str:
        mapping = self.get(project_key, mapping_id)
        mappingDict = {mapping.name: mapping}

        if html_output_dir is None:
            html_output_dir = self.project_handler._get(
                project_key
            ).config.html_output_dir

        return create_results_html(
            mappingDict, html_output_dir, show_remarks, show_warnings
        )
        # return mapping

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
            allowed_actions = ", ".join(action.value for action in field.actions_allowed)
            raise MappingNotFound(
                f"action '{input.action.value}' not allowed for this field, allowed: {allowed_actions}"
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
        
        if input.remark:
            new_entry.remark = input.remark

        # Clean up possible manual entry this was copied from before
        manual_entries = proj.manual_entries.get(mapping_id)

        if manual_entries is None:
            manual_entries = ManualEntriesMapping(id=mapping_id)
            proj.manual_entries[mapping_id] = manual_entries

        if (manual_entry := manual_entries.get(field.name)) and (
            manual_entry.action in [Action.COPY_FROM, Action.COPY_TO]
        ):
            other_name = manual_entry.other
            if other_name:
                try:
                    existing_partner = manual_entries[other_name]
                    if existing_partner.other == field.name:
                        del manual_entries[other_name]
                except (KeyError, AttributeError, StopIteration):
                    pass
            del manual_entries[field.name]

        # Apply the manual entry
        manual_entries[field.name] = new_entry
        proj.manual_entries.write()

        return new_entry

    def update(
        self, project_key: str, mapping_id: str, update_data: MappingUpdateModel
    ) -> MappingDetailsModel:
        """Update mapping metadata (status, version, profile information)."""
        proj = self.project_handler._get(project_key)
        if proj is None:
            raise ProjectNotFound()

        # Find the mapping config
        mapping_config = None
        for config in proj.config.mappings:
            if config.id == mapping_id:
                mapping_config = config
                break

        if mapping_config is None:
            raise MappingNotFound()

        # Update basic fields if provided
        if update_data.status is not None:
            mapping_config.status = update_data.status
        if update_data.version is not None:
            mapping_config.version = update_data.version

        # Update source profiles if provided
        if update_data.sources is not None:
            for i, source_update in enumerate(update_data.sources):
                if i < len(mapping_config.mappings.sourceprofiles):
                    source_config = mapping_config.mappings.sourceprofiles[i]
                    if source_update.url is not None:
                        source_config.url = source_update.url
                    if source_update.version is not None:
                        source_config.version = source_update.version
                    if source_update.webUrl is not None:
                        source_config.webUrl = source_update.webUrl
                    if source_update.package is not None:
                        source_config.package = source_update.package

        # Update target profile if provided
        if update_data.target is not None:
            target_config = mapping_config.mappings.targetprofile
            if update_data.target.url is not None:
                target_config.url = update_data.target.url
            if update_data.target.version is not None:
                target_config.version = update_data.target.version
            if update_data.target.webUrl is not None:
                target_config.webUrl = update_data.target.webUrl
            if update_data.target.package is not None:
                target_config.package = update_data.target.package

        # Update last_updated timestamp
        mapping_config.last_updated = datetime.now().isoformat()

        # Save config
        proj.config.write()

        # Get the current mapping before reload to preserve its state
        current_mapping = proj.mappings.get(mapping_id)
        
        # Reload only the config, not all mappings
        # This avoids re-initializing all mappings
        from ..data.config import ProjectConfig
        proj.config = ProjectConfig.from_json(proj.dir / "config.json")
        
        # Update just this mapping's metadata without full reload
        if current_mapping:
            # Update the config reference
            for config in proj.config.mappings:
                if config.id == mapping_id:
                    current_mapping._config = config
                    break
            
            return current_mapping.to_details_model()
        
        # Fallback: return the mapping data directly from config
        return self.get(project_key, mapping_id)

    def create_new(
        self, project_key, mapping: MappingCreateModel
    ) -> MappingDetailsModel:
        proj = self.project_handler._get(project_key)
        if proj is None:
            raise ProjectNotFound()

        new_mappingConfig = MappingConfigModel(
            id=str(uuid4()),
            version="1.0",
            last_updated=datetime.now().isoformat(),
            status="active",
            mappings=ComparisonProfilesConfigModel(
                sourceprofiles=[
                    self._to_profiles_config(id) for id in mapping.source_ids
                ],
                targetprofile=self._to_profiles_config(mapping.target_id),
            ),
        )
        new_mapping = MappingModel(new_mappingConfig, proj)
        new_mapping.fill_action_remark(proj.manual_entries)

        # --- FIX 1: Liste initialisieren, falls None/leer (analog zu Comparisons) ---
        if not proj.config.mappings:
            proj.config.mappings = []

        proj.config.mappings.append(new_mappingConfig)

        # --- FIX 2: Konsistent die Config selbst schreiben lassen ---
        proj.config.write()

        # Neu laden, damit proj.mappings den frischen Eintrag enthält
        proj.load_mappings()

        mapping = proj.mappings.get(new_mapping.id)
        return mapping.to_details_model()

    def _to_profiles_config(self, url: str) -> ComparisonProfileConfigModel:
        url, version = url.split("|")
        return ComparisonProfileConfigModel(url=url, version=version)

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
