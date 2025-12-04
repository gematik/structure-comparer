"""
Handler for Transformation CRUD operations.

Transformations are higher-level mappings that bundle multiple
child Mappings together. This handler provides all operations
for managing Transformations and their fields.
"""

import logging
from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from ..action import Action
from ..data.project import Project
from ..data.transformation import Transformation, TransformationField
from ..data.config import (
    TransformationConfig,
    ComparisonProfilesConfig,
    ComparisonProfileConfig,
)
from ..errors import (
    FieldNotFound,
    MappingNotFound,
    MappingTargetMissing,
    MappingTargetNotFound,
    MappingValueMissing,
    ProjectNotFound,
)
from .target_creation import TargetCreationNotFound
from ..model.manual_entries import ManualEntriesTransformation
from ..model.transformation import (
    TransformationBase as TransformationBaseModel,
    TransformationCreate as TransformationCreateModel,
    TransformationDetails as TransformationDetailsModel,
    TransformationField as TransformationFieldModel,
    TransformationFieldBase as TransformationFieldBaseModel,
    TransformationFieldMinimal as TransformationFieldMinimalModel,
    TransformationFieldsOutput as TransformationFieldsOutputModel,
    TransformationUpdate as TransformationUpdateModel,
    TransformationMappingLink as TransformationMappingLinkModel,
)
from .project import ProjectsHandler


logger = logging.getLogger(__name__)


class TransformationNotFound(Exception):
    """Raised when a transformation is not found."""

    def __init__(self, message: str = "Transformation not found"):
        self.message = message
        super().__init__(self.message)


class TransformationHandler:
    """Handler for Transformation CRUD operations."""

    def __init__(self, project_handler: ProjectsHandler):
        self.project_handler: ProjectsHandler = project_handler

    def get_list(self, project_key: str) -> List[TransformationBaseModel]:
        """Get list of all transformations for a project."""
        proj = self.project_handler._get(project_key)
        if proj is None:
            raise ProjectNotFound()

        if not hasattr(proj, "transformations") or proj.transformations is None:
            return []

        return [trans.to_base_model() for trans in proj.transformations.values()]

    def get(self, project_key: str, transformation_id: str) -> TransformationDetailsModel:
        """Get detailed information about a specific transformation."""
        transformation = self._get_transformation(project_key, transformation_id)
        return transformation.to_details_model()

    def get_field_list(
        self, project_key: str, transformation_id: str
    ) -> TransformationFieldsOutputModel:
        """Get list of all fields for a transformation."""
        transformation = self._get_transformation(project_key, transformation_id)
        fields = [f.to_model() for f in transformation.fields.values()]
        return TransformationFieldsOutputModel(id=transformation_id, fields=fields)

    def get_field(
        self, project_key: str, transformation_id: str, field_name: str
    ) -> TransformationFieldModel:
        """Get a specific field from a transformation."""
        transformation = self._get_transformation(project_key, transformation_id)
        field = self._get_field_by_name(transformation, field_name)

        if field is None:
            raise FieldNotFound()

        return field.to_model()

    def set_field(
        self,
        project_key: str,
        transformation_id: str,
        field_name: str,
        input: TransformationFieldMinimalModel,
    ) -> TransformationFieldBaseModel:
        """Set or update a field in a transformation."""
        logger.debug(
            f"set_field: project={project_key}, transformation={transformation_id}, "
            f"field={field_name}, action={input.action}"
        )

        proj = self.project_handler._get(project_key)
        if proj is None:
            raise ProjectNotFound()

        transformation = self._get_transformation(project_key, transformation_id, proj)
        field = self._get_field_by_name(transformation, field_name)

        if field is None:
            raise FieldNotFound()

        # Check if action is allowed for this field (allow None to remove action)
        if input.action is not None and input.action not in field.actions_allowed:
            allowed_actions = ", ".join(action.value for action in field.actions_allowed)
            raise TransformationNotFound(
                f"action '{input.action.value}' not allowed for this field, "
                f"allowed: {allowed_actions}"
            )

        # Get or create manual entries for this transformation
        manual_entries = proj.manual_entries.get_transformation(transformation_id)
        logger.debug(
            f"Got manual_entries for transformation {transformation_id}: "
            f"{manual_entries is not None}"
        )

        if manual_entries is None:
            manual_entries = ManualEntriesTransformation(id=transformation_id)
            proj.manual_entries.set_transformation(manual_entries)
            logger.debug(f"Created new ManualEntriesTransformation for {transformation_id}")

        # If action is None, remove the entry completely
        if input.action is None:
            return self._remove_field_entry(
                proj, transformation, field, manual_entries
            )

        # Build the entry that should be created/updated
        new_entry = TransformationFieldBaseModel(
            name=field.name,
            action=input.action
        )

        # Handle COPY_FROM/COPY_TO actions - validate target field exists
        if input.action in [Action.COPY_FROM, Action.COPY_TO]:
            if target_id := input.other:
                target = self._get_field_by_name(transformation, target_id)
                if target is None:
                    raise MappingTargetNotFound()
                new_entry.other = target.name
            else:
                raise MappingTargetMissing()
        # For other actions, just pass through the 'other' field value (target profile field path)
        elif input.other:
            new_entry.other = input.other

        # Handle FIXED action
        if input.action == Action.FIXED:
            if fixed := input.fixed:
                new_entry.fixed = fixed
            else:
                raise MappingValueMissing()

        # Handle map reference (linking to a child mapping)
        if input.map:
            # Verify that the mapping exists
            mapping = proj.mappings.get(input.map)
            if mapping is None:
                raise MappingNotFound(f"Referenced mapping '{input.map}' not found")
            new_entry.map = input.map

        if input.remark:
            new_entry.remark = input.remark

        # Clean up existing COPY_FROM/COPY_TO partners when changing action
        existing_entry = manual_entries.get_field(field.name)
        if existing_entry and existing_entry.action in [Action.COPY_FROM, Action.COPY_TO]:
            if other_name := existing_entry.other:
                partner_entry = manual_entries.get_field(other_name)
                if partner_entry and partner_entry.other == field.name:
                    manual_entries.remove_field(other_name)

        # Apply the manual entry
        manual_entries.set_field(new_entry)
        proj.manual_entries.write()

        # Reload transformations to apply the updated manual entries
        proj.load_transformations()

        return new_entry

    def _remove_field_entry(
        self,
        proj: Project,
        transformation: Transformation,
        field: TransformationField,
        manual_entries: ManualEntriesTransformation,
    ) -> TransformationFieldBaseModel:
        """Remove a field entry from manual entries."""
        logger.debug(f"Action is None - removing field {field.name} from manual_entries")

        fields_to_delete = set()
        existing_entry = manual_entries.get_field(field.name)

        if existing_entry:
            fields_to_delete.add(field.name)

            # Clean up COPY partners
            if existing_entry.action in [Action.COPY_FROM, Action.COPY_TO]:
                if other_name := existing_entry.other:
                    partner_entry = manual_entries.get_field(other_name)
                    if partner_entry and partner_entry.other == field.name:
                        fields_to_delete.add(other_name)

        # Delete all found fields
        for field_name in fields_to_delete:
            manual_entries.remove_field(field_name)

        proj.manual_entries.write()
        return TransformationFieldBaseModel(name=field.name, action=None)

    def link_mapping(
        self,
        project_key: str,
        transformation_id: str,
        field_name: str,
        link_data: TransformationMappingLinkModel,
    ) -> TransformationFieldModel:
        """Link a mapping to a transformation field."""
        proj = self.project_handler._get(project_key)
        if proj is None:
            raise ProjectNotFound()

        transformation = self._get_transformation(project_key, transformation_id, proj)
        field = self._get_field_by_name(transformation, field_name)

        if field is None:
            raise FieldNotFound()

        # Verify mapping exists
        mapping = proj.mappings.get(link_data.mapping_id)
        if mapping is None:
            raise MappingNotFound(f"Mapping '{link_data.mapping_id}' not found")

        # Get or create manual entries
        manual_entries = proj.manual_entries.get_transformation(transformation_id)
        if manual_entries is None:
            manual_entries = ManualEntriesTransformation(id=transformation_id)
            proj.manual_entries.set_transformation(manual_entries)

        # Create or update the field entry with the mapping link
        existing_entry = manual_entries.get_field(field_name)
        if existing_entry:
            existing_entry.map = link_data.mapping_id
            if link_data.other:
                existing_entry.other = link_data.other
            manual_entries.set_field(existing_entry)
        else:
            new_entry = TransformationFieldBaseModel(
                name=field_name,
                action=link_data.action or Action.USE,
                map=link_data.mapping_id,
                other=link_data.other,
            )
            manual_entries.set_field(new_entry)

        proj.manual_entries.write()

        # Reload transformations to apply the updated manual entries
        proj.load_transformations()

        # Return the updated field
        transformation = self._get_transformation(project_key, transformation_id, proj)
        updated_field = self._get_field_by_name(transformation, field_name)
        return updated_field.to_model()

    def unlink_mapping(
        self,
        project_key: str,
        transformation_id: str,
        field_name: str,
    ) -> TransformationFieldModel:
        """Remove a mapping link from a transformation field."""
        proj = self.project_handler._get(project_key)
        if proj is None:
            raise ProjectNotFound()

        transformation = self._get_transformation(project_key, transformation_id, proj)
        field = self._get_field_by_name(transformation, field_name)

        if field is None:
            raise FieldNotFound()

        # Get manual entries and remove the field entry completely
        manual_entries = proj.manual_entries.get_transformation(transformation_id)
        if manual_entries:
            existing_entry = manual_entries.get_field(field_name)
            if existing_entry:
                # Remove the entry completely instead of just clearing the map
                manual_entries.remove_field(field_name)
                proj.manual_entries.write()

        # Reload transformations to apply the updated manual entries
        proj.load_transformations()

        # Return the updated field
        transformation = self._get_transformation(project_key, transformation_id, proj)
        updated_field = self._get_field_by_name(transformation, field_name)
        return updated_field.to_model()

    def link_target_creation(
        self,
        project_key: str,
        transformation_id: str,
        field_name: str,
        target_creation_id: str,
    ) -> TransformationFieldModel:
        """Link a target creation to a transformation field."""
        proj = self.project_handler._get(project_key)
        if proj is None:
            raise ProjectNotFound()

        transformation = self._get_transformation(project_key, transformation_id, proj)
        field = self._get_field_by_name(transformation, field_name)

        if field is None:
            raise FieldNotFound()

        # Verify target creation exists
        target_creation = proj.target_creations.get(target_creation_id)
        if target_creation is None:
            raise TargetCreationNotFound(f"Target Creation '{target_creation_id}' not found")

        # Get or create manual entries
        manual_entries = proj.manual_entries.get_transformation(transformation_id)
        if manual_entries is None:
            manual_entries = ManualEntriesTransformation(id=transformation_id)
            proj.manual_entries.set_transformation(manual_entries)

        # Create or update the field entry with the target creation link
        existing_entry = manual_entries.get_field(field_name)
        if existing_entry:
            existing_entry.target_creation = target_creation_id
            manual_entries.set_field(existing_entry)
        else:
            new_entry = TransformationFieldBaseModel(
                name=field_name,
                action=Action.USE,
                target_creation=target_creation_id,
            )
            manual_entries.set_field(new_entry)

        proj.manual_entries.write()

        # Reload transformations to apply the updated manual entries
        proj.load_transformations()

        # Return the updated field
        transformation = self._get_transformation(project_key, transformation_id, proj)
        updated_field = self._get_field_by_name(transformation, field_name)
        return updated_field.to_model()

    def unlink_target_creation(
        self,
        project_key: str,
        transformation_id: str,
        field_name: str,
    ) -> TransformationFieldModel:
        """Remove a target creation link from a transformation field."""
        proj = self.project_handler._get(project_key)
        if proj is None:
            raise ProjectNotFound()

        transformation = self._get_transformation(project_key, transformation_id, proj)
        field = self._get_field_by_name(transformation, field_name)

        if field is None:
            raise FieldNotFound()

        # Get manual entries and remove the target_creation reference
        manual_entries = proj.manual_entries.get_transformation(transformation_id)
        if manual_entries:
            existing_entry = manual_entries.get_field(field_name)
            if existing_entry and existing_entry.target_creation:
                # If there's nothing else in the entry, remove it completely
                if not existing_entry.map and not existing_entry.fixed and not existing_entry.other:
                    manual_entries.remove_field(field_name)
                else:
                    # Otherwise just clear the target_creation
                    existing_entry.target_creation = None
                    manual_entries.set_field(existing_entry)
                proj.manual_entries.write()

        # Reload transformations to apply the updated manual entries
        proj.load_transformations()

        # Return the updated field
        transformation = self._get_transformation(project_key, transformation_id, proj)
        updated_field = self._get_field_by_name(transformation, field_name)
        return updated_field.to_model()

    def update(
        self,
        project_key: str,
        transformation_id: str,
        update_data: TransformationUpdateModel,
    ) -> TransformationDetailsModel:
        """Update transformation metadata (status, version, profile information)."""
        proj = self.project_handler._get(project_key)
        if proj is None:
            raise ProjectNotFound()

        # Find the transformation config
        trans_config = None
        for config in proj.config.transformations:
            if config.id == transformation_id:
                trans_config = config
                break

        if trans_config is None:
            raise TransformationNotFound()

        # Update basic fields if provided
        if update_data.status is not None:
            trans_config.status = update_data.status
        if update_data.version is not None:
            trans_config.version = update_data.version

        # Update source profiles if provided
        if update_data.sources is not None:
            for i, source_update in enumerate(update_data.sources):
                if i < len(trans_config.transformations.sourceprofiles):
                    source_config = trans_config.transformations.sourceprofiles[i]
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
            target_config = trans_config.transformations.targetprofile
            if update_data.target.url is not None:
                target_config.url = update_data.target.url
            if update_data.target.version is not None:
                target_config.version = update_data.target.version
            if update_data.target.webUrl is not None:
                target_config.webUrl = update_data.target.webUrl
            if update_data.target.package is not None:
                target_config.package = update_data.target.package

        # Update last_updated timestamp
        trans_config.last_updated = datetime.now().isoformat()

        # Save config
        proj.config.write()

        # Reload config
        from ..data.config import ProjectConfig
        proj.config = ProjectConfig.from_json(proj.dir / "config.json")

        # Return updated transformation
        return self.get(project_key, transformation_id)

    def create(
        self,
        project_key: str,
        transformation: TransformationCreateModel,
    ) -> TransformationDetailsModel:
        """Create a new transformation."""
        proj = self.project_handler._get(project_key)
        if proj is None:
            raise ProjectNotFound()

        new_config = TransformationConfig(
            id=str(uuid4()),
            version="1.0",
            last_updated=datetime.now().isoformat(),
            status="draft",
            transformations=ComparisonProfilesConfig(
                sourceprofiles=[
                    self._to_profile_config(url) for url in transformation.source_ids
                ],
                targetprofile=self._to_profile_config(transformation.target_id),
            ),
        )

        # Initialize transformations list if not exists
        if not proj.config.transformations:
            proj.config.transformations = []

        proj.config.transformations.append(new_config)
        proj.config.write()

        # Reload transformations
        proj.load_transformations()

        # Get and return the new transformation
        new_trans = proj.transformations.get(new_config.id)
        if new_trans is None:
            raise TransformationNotFound("Failed to create transformation")

        return new_trans.to_details_model()

    def delete(self, project_key: str, transformation_id: str) -> bool:
        """Delete a transformation."""
        proj = self.project_handler._get(project_key)
        if proj is None:
            raise ProjectNotFound()

        # Find and remove the transformation config
        found = False
        for i, config in enumerate(proj.config.transformations):
            if config.id == transformation_id:
                proj.config.transformations.pop(i)
                found = True
                break

        if not found:
            raise TransformationNotFound()

        proj.config.write()

        # Remove manual entries for this transformation
        proj.manual_entries.remove_transformation(transformation_id)
        proj.manual_entries.write()

        # Reload transformations
        proj.load_transformations()

        return True

    def _to_profile_config(self, url: str) -> ComparisonProfileConfig:
        """Convert a profile URL to a ComparisonProfileConfig."""
        parts = url.split("|")
        if len(parts) == 2:
            return ComparisonProfileConfig(url=parts[0], version=parts[1])
        return ComparisonProfileConfig(url=url, version="1.0.0")

    def _get_transformation(
        self,
        project_key: str,
        transformation_id: str,
        proj: Optional[Project] = None,
    ) -> Transformation:
        """Get a transformation by project key and transformation ID."""
        if proj is None:
            proj = self.project_handler._get(project_key)

        if proj is None:
            raise ProjectNotFound()

        if not hasattr(proj, "transformations") or proj.transformations is None:
            raise TransformationNotFound("Project has no transformations")

        transformation = proj.transformations.get(transformation_id)
        if transformation is None:
            raise TransformationNotFound()

        return transformation

    def _get_field_by_name(
        self,
        transformation: Transformation,
        field_name: str,
    ) -> Optional[TransformationField]:
        """Get a field from a transformation by name."""
        return transformation.fields.get(field_name)
