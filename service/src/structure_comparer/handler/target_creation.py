"""
Target Creation Handler - CRUD operations for Target Creation entities.

Target Creations are a third entity type alongside Mappings and Transformations.
Unlike Mappings, they have no source profiles and only support 'manual' and 'fixed' actions.

=== IMPLEMENTATION STATUS ===
Phase 4, Step 4.1: TargetCreationHandler erstellen ✅
Created: 2025-12-03

This handler provides:
- CRUD operations for Target Creations
- Field-level operations (get/set)
- Evaluation summary generation

Future phases will add:
- Phase 5: API Router integration
- Phase 11: Transformation integration (linking)
"""
import logging
from datetime import datetime
from typing import List
from uuid import uuid4

from ..data.project import Project
from ..data.target_creation import TargetCreation as TargetCreationModel
from ..data.config import TargetCreationConfig, ComparisonProfileConfig
from ..errors import (
    FieldNotFound,
    MappingValueMissing,
    ProjectNotFound,
)
from ..model.manual_entries import ManualEntriesTargetCreation
from ..model.target_creation import (
    TargetCreationBase as TargetCreationBaseModel,
    TargetCreationCreate as TargetCreationCreateModel,
    TargetCreationDetails as TargetCreationDetailsModel,
    TargetCreationField as TargetCreationFieldModel,
    TargetCreationFieldBase as TargetCreationFieldBaseModel,
    TargetCreationFieldMinimal as TargetCreationFieldMinimalModel,
    TargetCreationFieldsOutput as TargetCreationFieldsOutputModel,
    TargetCreationUpdate as TargetCreationUpdateModel,
    TargetCreationEvaluationSummary,
    TargetCreationAction,
)
from ..evaluation.target_creation_evaluation import TargetCreationStatusAggregator
from .project import ProjectsHandler


logger = logging.getLogger(__name__)


class TargetCreationNotFound(Exception):
    """Exception raised when a Target Creation is not found."""
    def __init__(self, msg="Target Creation not found", *args, **kwargs):
        super().__init__(msg, *args, **kwargs)


class TargetCreationHandler:
    """Handler for Target Creation CRUD operations.
    
    Simplified compared to MappingHandler:
    - No source profiles
    - No inheritance/classification logic
    - Only manual/fixed actions
    - Status based on required fields having actions
    """

    def __init__(self, project_handler: ProjectsHandler):
        self.project_handler: ProjectsHandler = project_handler

    def get_list(self, project_key: str) -> List[TargetCreationBaseModel]:
        """Get all Target Creations for a project.
        
        Returns:
            List of TargetCreationBase models with summary info
        """
        proj = self.project_handler._get(project_key)
        result = []
        for tc in proj.target_creations.values():
            try:
                result.append(tc.to_base_model())
            except ValueError:
                # Skip target creations with missing profiles
                pass
        return result

    def get(self, project_key: str, target_creation_id: str) -> TargetCreationDetailsModel:
        """Get a specific Target Creation with full details.
        
        Args:
            project_key: Project identifier
            target_creation_id: Target Creation ID
            
        Returns:
            TargetCreationDetails model with all fields
            
        Raises:
            ProjectNotFound: If project doesn't exist
            TargetCreationNotFound: If Target Creation doesn't exist
        """
        target_creation = self.__get(project_key, target_creation_id)
        return target_creation.to_details_model()

    def get_field_list(
        self, project_key: str, target_creation_id: str
    ) -> TargetCreationFieldsOutputModel:
        """Get all fields for a Target Creation.
        
        Args:
            project_key: Project identifier
            target_creation_id: Target Creation ID
            
        Returns:
            TargetCreationFieldsOutput with list of fields
        """
        target_creation = self.__get(project_key, target_creation_id)
        fields = [f.to_model() for f in target_creation.fields.values()]
        return TargetCreationFieldsOutputModel(id=target_creation_id, fields=fields)

    def get_field(
        self, project_key: str, target_creation_id: str, field_name: str
    ) -> TargetCreationFieldModel:
        """Get a specific field from a Target Creation.
        
        Args:
            project_key: Project identifier
            target_creation_id: Target Creation ID
            field_name: Field name (can include dots for nested fields)
            
        Returns:
            TargetCreationField model
            
        Raises:
            FieldNotFound: If field doesn't exist
        """
        target_creation = self.__get(project_key, target_creation_id)
        field = target_creation.fields.get(field_name)
        
        if field is None:
            raise FieldNotFound()
        
        return field.to_model()

    def set_field(
        self,
        project_key: str,
        target_creation_id: str,
        field_name: str,
        input: TargetCreationFieldMinimalModel,
    ) -> TargetCreationFieldBaseModel:
        """Set or update a field's action in a Target Creation.
        
        Args:
            project_key: Project identifier
            target_creation_id: Target Creation ID
            field_name: Field name to update
            input: New field data (action, fixed value, remark)
            
        Returns:
            Updated TargetCreationFieldBase model
            
        Raises:
            FieldNotFound: If field doesn't exist
            MappingValueMissing: If action=fixed but no fixed value provided
        """
        logger.debug(
            f"set_field: project={project_key}, target_creation={target_creation_id}, "
            f"field={field_name}, action={input.action}"
        )
        
        proj = self.project_handler._get(project_key)
        target_creation = self.__get(project_key, target_creation_id, proj)
        
        field = target_creation.fields.get(field_name)
        if field is None:
            raise FieldNotFound()
        
        # Get or create manual entries for this Target Creation
        manual_entries = proj.manual_entries.get_target_creation(target_creation_id)
        logger.debug(f"Got manual_entries for target_creation {target_creation_id}: {manual_entries is not None}")
        
        if manual_entries is None:
            manual_entries = ManualEntriesTargetCreation(id=target_creation_id)
            proj.manual_entries.set_target_creation(manual_entries)
            logger.debug(f"Created new ManualEntriesTargetCreation for {target_creation_id}")
        
        # If action is None, remove the entry
        if input.action is None:
            logger.debug(f"Action is None - removing field {field.name} from manual_entries")
            
            # Remove this field from manual entries
            manual_entries.fields = [
                f for f in manual_entries.fields if f.name != field.name
            ]
            
            proj.manual_entries.write()
            logger.debug("Finished writing manual_entries")
            
            # IMPORTANT: Clear the action on the in-memory field object
            field.action = None
            field.fixed = None
            field.remark = None
            
            # Return a response indicating removal
            return TargetCreationFieldBaseModel(name=field.name, action=None)
        
        # Validate action type
        if input.action not in field.actions_allowed:
            allowed = ", ".join(str(a) for a in field.actions_allowed)
            raise ValueError(
                f"Action '{input.action}' not allowed for this field, allowed: {allowed}"
            )
        
        # Build the entry that should be created/updated
        new_entry = TargetCreationFieldBaseModel(name=field.name, action=input.action)
        
        # Handle action-specific fields
        if new_entry.action == TargetCreationAction.FIXED:
            if fixed := input.fixed:
                new_entry.fixed = fixed
            else:
                raise MappingValueMissing("Fixed value required when action=fixed")
        
        if input.remark:
            new_entry.remark = input.remark
        
        # Update or add the entry
        # Remove existing entry for this field if present
        manual_entries.fields = [
            f for f in manual_entries.fields if f.name != field.name
        ]
        # Add the new entry
        manual_entries.fields.append(new_entry)
        
        # Write to disk
        proj.manual_entries.write()
        
        # IMPORTANT: Apply the manual entry to the in-memory field object
        # so that subsequent API calls see the updated action without requiring a server restart
        field.apply_manual_entry(new_entry)
        
        return new_entry

    def update(
        self, project_key: str, target_creation_id: str, update_data: TargetCreationUpdateModel
    ) -> TargetCreationDetailsModel:
        """Update Target Creation metadata (status, version, target profile info).
        
        Args:
            project_key: Project identifier
            target_creation_id: Target Creation ID
            update_data: Fields to update
            
        Returns:
            Updated TargetCreationDetails model
        """
        proj = self.project_handler._get(project_key)
        if proj is None:
            raise ProjectNotFound()
        
        # Find the Target Creation config
        tc_config = None
        for config in proj.config.target_creations:
            if config.id == target_creation_id:
                tc_config = config
                break
        
        if tc_config is None:
            raise TargetCreationNotFound()
        
        # Update basic fields if provided
        if update_data.status is not None:
            tc_config.status = update_data.status
        if update_data.version is not None:
            tc_config.version = update_data.version
        
        # Update target profile if provided
        if update_data.target is not None:
            target_config = tc_config.targetprofile
            if update_data.target.url is not None:
                target_config.url = update_data.target.url
            if update_data.target.version is not None:
                target_config.version = update_data.target.version
            if update_data.target.webUrl is not None:
                target_config.webUrl = update_data.target.webUrl
            if update_data.target.package is not None:
                target_config.package = update_data.target.package
        
        # Update last_updated timestamp
        tc_config.last_updated = datetime.now().isoformat()
        
        # Save config
        proj.config.write()
        
        # Get the current target creation before reload to preserve its state
        current_tc = proj.target_creations.get(target_creation_id)
        
        # Reload only the config, not all target creations
        from ..data.config import ProjectConfig
        proj.config = ProjectConfig.from_json(proj.dir / "config.json")
        
        # Update just this target creation's metadata without full reload
        if current_tc:
            # Update the config reference
            for config in proj.config.target_creations:
                if config.id == target_creation_id:
                    current_tc._config = config
                    break
            
            return current_tc.to_details_model()
        
        # Fallback: return the target creation data directly
        return self.get(project_key, target_creation_id)

    def create(
        self, project_key: str, input_data: TargetCreationCreateModel
    ) -> TargetCreationDetailsModel:
        """Create a new Target Creation.
        
        Args:
            project_key: Project identifier
            input_data: Target Creation creation data (target profile ID)
            
        Returns:
            Created TargetCreationDetails model
        """
        proj = self.project_handler._get(project_key)
        if proj is None:
            raise ProjectNotFound()
        
        # Parse target profile ID (format: "url|version")
        new_tc_config = TargetCreationConfig(
            id=str(uuid4()),
            version="1.0",
            last_updated=datetime.now().isoformat(),
            status="draft",
            targetprofile=self._to_profile_config(input_data.target_id),
        )
        
        # Create the Target Creation model
        new_tc = TargetCreationModel(new_tc_config, proj)
        new_tc.init_ext()
        
        # Initialize config list if needed
        if not proj.config.target_creations:
            proj.config.target_creations = []
        
        proj.config.target_creations.append(new_tc_config)
        proj.config.write()
        
        # Reload target creations
        proj.load_target_creations()
        
        target_creation = proj.target_creations.get(new_tc.id)
        return target_creation.to_details_model()

    def delete(self, project_key: str, target_creation_id: str) -> None:
        """Delete a Target Creation.
        
        Args:
            project_key: Project identifier
            target_creation_id: Target Creation ID to delete
        """
        proj = self.project_handler._get(project_key)
        if proj is None:
            raise ProjectNotFound()
        
        # Remove from config
        original_count = len(proj.config.target_creations)
        proj.config.target_creations = [
            tc for tc in proj.config.target_creations if tc.id != target_creation_id
        ]
        
        if len(proj.config.target_creations) == original_count:
            raise TargetCreationNotFound()
        
        proj.config.write()
        
        # Remove from manual entries
        proj.manual_entries.remove_target_creation(target_creation_id)
        
        # Reload target creations
        proj.load_target_creations()

    def get_evaluation_summary(
        self, project_key: str, target_creation_id: str
    ) -> TargetCreationEvaluationSummary:
        """Get evaluation summary for a Target Creation.
        
        Args:
            project_key: Project identifier
            target_creation_id: Target Creation ID
            
        Returns:
            TargetCreationEvaluationSummary with status counts
        """
        target_creation = self.__get(project_key, target_creation_id)
        return TargetCreationStatusAggregator.build_evaluation_summary(target_creation)

    def _to_profile_config(self, profile_id: str) -> ComparisonProfileConfig:
        """Convert a profile ID string to ComparisonProfileConfig.
        
        Args:
            profile_id: Format "url|version"
            
        Returns:
            ComparisonProfileConfig object
        """
        url, version = profile_id.split("|")
        return ComparisonProfileConfig(url=url, version=version)

    def __get(
        self, 
        project_key: str, 
        target_creation_id: str, 
        proj: Project | None = None
    ) -> TargetCreationModel:
        """Internal method to get a Target Creation.
        
        Args:
            project_key: Project identifier
            target_creation_id: Target Creation ID
            proj: Optional pre-fetched Project instance
            
        Returns:
            TargetCreation data model
            
        Raises:
            ProjectNotFound: If project doesn't exist
            TargetCreationNotFound: If Target Creation doesn't exist
        """
        if proj is None:
            proj = self.project_handler._get(project_key)
        
        if proj is None:
            raise ProjectNotFound()
        
        target_creation = proj.target_creations.get(target_creation_id)
        
        if not target_creation:
            raise TargetCreationNotFound()
        
        return target_creation
