"""
Transformation data class.

A Transformation represents a higher-level mapping that bundles multiple
Mappings together to describe how a complete FHIR Bundle is transformed
into another structure (e.g., KBV_PR_ERP_Bundle -> ePA Parameters).

Architecture:
- Transformation extends Comparison (like Mapping does)
- TransformationField has a 'map' property that references a Mapping ID
- Transformation tracks linked_mappings for quick access
"""

import logging
from collections import OrderedDict
from typing import TYPE_CHECKING, List

from pydantic import ValidationError

from ..action import Action
from ..errors import NotInitialized
from ..model.transformation import (
    MappingReference,
    TransformationBase as TransformationBaseModel,
    TransformationDetails as TransformationDetailsModel,
    TransformationField as TransformationFieldModel,
)
from ..model.transformation import TransformationFieldBase
from ..model.profile import Profile as ProfileModel
from ..model.mapping_action_models import ActionInfo, EvaluationResult
from ..model.comparison import ComparisonClassification
from .comparison import Comparison, ComparisonField
from .config import TransformationConfig

if TYPE_CHECKING:
    from .mapping import Mapping
    from .project import Project

logger = logging.getLogger(__name__)


class TransformationField(ComparisonField):
    """A field within a Transformation.

    TransformationFields can reference child Mappings via the 'map' property.
    The action for transformation fields is typically 'transform' when
    linking to a Mapping.
    """

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.action: Action | None = None
        self.other: str | None = None
        self.fixed: str | None = None
        self.remark: str | None = None
        self.map: str | None = None  # Reference to Mapping ID
        self.map_name: str | None = None  # Resolved Mapping name
        self.actions_allowed: List[Action] = []
        self.action_info: ActionInfo | None = None
        self.evaluation: EvaluationResult | None = None
        self.recommendations: List[ActionInfo] = []

    def fill_allowed_actions(
        self, source_profiles: List[str], target_profile: str
    ) -> None:
        """Set baseline actions_allowed for transformation fields."""
        allowed = set([c for c in Action])

        # Add TRANSFORM action for transformation fields
        # Note: TRANSFORM is not in base Action enum, will be added as extension

        any_source_present = any(
            [self.profiles[profile] is not None for profile in source_profiles]
        )
        target_present = self.profiles[target_profile] is not None

        if not any_source_present:
            allowed -= set([Action.USE, Action.NOT_USE, Action.COPY_FROM])
        else:
            allowed -= set([Action.EMPTY])
        if not target_present:
            allowed -= set([Action.USE, Action.EMPTY, Action.COPY_TO])

        self.actions_allowed = list(allowed)

    def apply_manual_entry(self, entry: TransformationFieldBase) -> None:
        """Apply a manual entry to this field."""
        self.action = entry.action
        self.other = entry.other
        self.fixed = entry.fixed
        self.remark = entry.remark
        self.map = entry.map

    def to_model(self) -> TransformationFieldModel:
        """Convert to Pydantic model for API response."""
        profiles = {}
        for k, p in self.profiles.items():
            if p is not None:
                profile_obj = self._profile_objects.get(k)
                all_fields = profile_obj.fields if profile_obj else None
                profiles[k] = p.to_model(all_fields)

        # Get source/target field info
        source_min = None
        source_max = None
        target_min = None
        target_max = None

        for key, field in self.profiles.items():
            if field is not None:
                # Last profile is target
                if key == list(self.profiles.keys())[-1]:
                    target_min = field.min
                    target_max = field.max
                else:
                    # Use first source with data
                    if source_min is None:
                        source_min = field.min
                        source_max = field.max

        return TransformationFieldModel(
            name=self.name,
            path=self.name,
            action=self.action,
            other=self.other,
            fixed=self.fixed,
            remark=self.remark,
            map=self.map,
            map_name=self.map_name,
            actions_allowed=self.actions_allowed,
            action_info=self.action_info,
            evaluation=self.evaluation,
            recommendations=self.recommendations,
            source_min=source_min,
            source_max=source_max,
            target_min=target_min,
            target_max=target_max,
        )


class Transformation(Comparison):
    """A Transformation bundles multiple Mappings together.

    It describes how a complete FHIR Bundle is transformed into another
    structure, with each TransformationField potentially referencing a
    child Mapping via the 'map' property.
    """

    def __init__(self, config: TransformationConfig, project: "Project") -> None:
        # Note: TransformationConfig uses 'transformations' instead of 'comparison'
        super().__init__(config, project)

        self.fields: OrderedDict[str, TransformationField] = OrderedDict()
        self._linked_mapping_ids: set[str] = set()

    def init_ext(self) -> "Transformation":
        """Initialize the transformation with profiles and fields."""
        self._get_sources(self._config.transformations.sourceprofiles)
        self._get_target(self._config.transformations.targetprofile)
        self._gen_fields()
        self._apply_manual_entries()
        return self

    @property
    def version(self) -> str:
        return self._config.version

    @property
    def last_updated(self) -> str:
        return self._config.last_updated

    @property
    def status(self) -> str:
        return self._config.status

    @property
    def url(self) -> str:
        return f"/project/{self._project.key}/transformation/{self.id}"

    @property
    def linked_mapping_ids(self) -> set[str]:
        """Returns the set of Mapping IDs linked to this Transformation."""
        return self._linked_mapping_ids

    def _gen_fields(self) -> None:
        """Generate fields from source and target profiles."""
        super()._gen_fields(TransformationField)

        if self.sources is None or self.target is None:
            raise NotInitialized()

        all_profiles = [self.target] + self.sources
        all_profiles_keys = [profile.key for profile in all_profiles]

        for field in self.fields.values():
            field.fill_allowed_actions(all_profiles_keys[:-1], all_profiles_keys[-1])

    def _apply_manual_entries(self) -> None:
        """Apply manual transformation entries from the project."""
        manual_entries = self._project.manual_entries
        transformation_entry = manual_entries.get_transformation(self.id)

        if transformation_entry is None:
            return

        for manual_field in transformation_entry.fields:
            field = self.fields.get(manual_field.name)
            if field:
                field.apply_manual_entry(manual_field)
                if manual_field.map:
                    self._linked_mapping_ids.add(manual_field.map)
                    # Resolve mapping name
                    mapping = self._project.mappings.get(manual_field.map)
                    if mapping:
                        field.map_name = mapping.name

    def get_linked_mappings(self) -> List["Mapping"]:
        """Returns all Mapping objects linked to this Transformation."""
        result = []
        for mapping_id in self._linked_mapping_ids:
            mapping = self._project.mappings.get(mapping_id)
            if mapping:
                result.append(mapping)
        return result

    def _build_mapping_reference(self, mapping: "Mapping") -> MappingReference:
        """Create a MappingReference from a Mapping object."""
        return MappingReference(
            id=mapping.id,
            name=mapping.name,
            url=mapping.url,
            version=mapping.version,
            status=mapping.status,
        )

    def to_base_model(self) -> TransformationBaseModel:
        """Convert to base Pydantic model for list views."""
        if self.sources is None or self.target is None:
            raise NotInitialized()

        # Create source models with metadata from configs
        sources = []
        for i, source_profile in enumerate(self.sources):
            metadata = self.get_profile_metadata(source_profile)
            source_dict = {
                "id": source_profile.id,
                "url": source_profile.url,
                "key": source_profile.key,
                "name": source_profile.name,
                "version": source_profile.version,
                "webUrl": metadata.get("webUrl"),
                "package": metadata.get("package"),
            }
            sources.append(ProfileModel(**source_dict))

        # Create target model with metadata from config
        target_metadata = self.get_profile_metadata(self.target)
        target_dict = {
            "id": self.target.id,
            "url": self.target.url,
            "key": self.target.key,
            "name": self.target.name,
            "version": self.target.version,
            "webUrl": target_metadata.get("webUrl"),
            "package": target_metadata.get("package"),
        }
        target = ProfileModel(**target_dict)

        # Calculate status counts
        status_counts = self._calculate_status_counts()

        try:
            model = TransformationBaseModel(
                id=self.id,
                name=self.name,
                version=self.version,
                last_updated=self.last_updated,
                status=self.status,
                sources=sources,
                target=target,
                url=self.url,
                linked_mappings_count=len(self._linked_mapping_ids),
                **status_counts,
            )

        except ValidationError as e:
            logger.error(e.errors())
            raise e

        return model

    def to_details_model(self) -> TransformationDetailsModel:
        """Convert to detailed Pydantic model including fields."""
        if self.sources is None or self.target is None:
            raise NotInitialized()

        # Create source models
        sources = []
        for source_profile in self.sources:
            metadata = self.get_profile_metadata(source_profile)
            source_dict = {
                "id": source_profile.id,
                "url": source_profile.url,
                "key": source_profile.key,
                "name": source_profile.name,
                "version": source_profile.version,
                "webUrl": metadata.get("webUrl"),
                "package": metadata.get("package"),
            }
            sources.append(ProfileModel(**source_dict))

        # Create target model
        target_metadata = self.get_profile_metadata(self.target)
        target_dict = {
            "id": self.target.id,
            "url": self.target.url,
            "key": self.target.key,
            "name": self.target.name,
            "version": self.target.version,
            "webUrl": target_metadata.get("webUrl"),
            "package": target_metadata.get("package"),
        }
        target = ProfileModel(**target_dict)

        # Convert fields
        fields = [f.to_model() for f in self.fields.values()]

        # Get linked mappings
        linked_mappings = [
            self._build_mapping_reference(m) for m in self.get_linked_mappings()
        ]

        # Calculate status counts
        status_counts = self._calculate_status_counts()

        try:
            model = TransformationDetailsModel(
                id=self.id,
                name=self.name,
                version=self.version,
                last_updated=self.last_updated,
                status=self.status,
                sources=sources,
                target=target,
                url=self.url,
                fields=fields,
                linked_mappings=linked_mappings,
                linked_mappings_count=len(self._linked_mapping_ids),
                **status_counts,
            )

        except ValidationError as e:
            logger.error(e.errors())
            raise e

        return model

    def _calculate_status_counts(self) -> dict:
        """Calculate status counts for the transformation."""
        status_counts = {
            "total": len(self.fields),
            "incompatible": 0,
            "warning": 0,
            "solved": 0,
            "compatible": 0,
        }

        for field in self.fields.values():
            classification = field.classification
            if classification == ComparisonClassification.INCOMPAT:
                # Check if field has an action (solved) or not (incompatible)
                if field.action is not None:
                    status_counts["solved"] += 1
                else:
                    status_counts["incompatible"] += 1
            elif classification == ComparisonClassification.WARN:
                if field.action is not None:
                    status_counts["solved"] += 1
                else:
                    status_counts["warning"] += 1
            else:
                status_counts["compatible"] += 1

        return status_counts
