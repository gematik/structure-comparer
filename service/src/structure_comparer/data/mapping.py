import logging
from collections import OrderedDict
from typing import Dict, List

from pydantic import ValidationError

from ..action import Action
from ..errors import NotInitialized
from ..manual_entries import ManualEntries
from ..mapping_actions_engine import compute_mapping_actions, compute_recommendations
from ..mapping_evaluation_engine import evaluate_mapping
from ..model.mapping import MappingBase as MappingBaseModel
from ..model.mapping import MappingDetails as MappingDetailsModel
from ..model.mapping import MappingField as MappingFieldModel
from ..model.mapping_action_models import ActionInfo, ActionSource, ActionType, EvaluationResult
from ..model.profile import Profile as ProfileModel
from .comparison import Comparison, ComparisonField
from .config import MappingConfig
from ..model.comparison import ComparisonClassification

logger = logging.getLogger(__name__)


_ACTIONTYPE_TO_LEGACY: dict[ActionType, Action] = {
    ActionType.USE: Action.USE,
    ActionType.USE_RECURSIVE: Action.USE_RECURSIVE,
    ActionType.NOT_USE: Action.NOT_USE,
    ActionType.EMPTY: Action.EMPTY,
    ActionType.COPY_FROM: Action.COPY_FROM,
    ActionType.COPY_TO: Action.COPY_TO,
    ActionType.FIXED: Action.FIXED,
    ActionType.MANUAL: Action.MANUAL,
    # Note: action=None indicates no action has been selected yet (user must decide)
}


class MappingField(ComparisonField):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.action: Action | None = None  # None until action is determined
        self.other: str | None = None
        self.fixed: str | None = None
        self.actions_allowed: List[Action] = []
        self.action_info: ActionInfo | None = None
        self.evaluation = None
        self.recommendations: List[ActionInfo] = []  # List of suggested actions, not yet applied

    @property
    def name_child(self) -> str:
        return self.name.rsplit(".", 1)[1]

    @property
    def name_parent(self) -> str:
        return self.name.rsplit(".", 1)[0]

    def fill_allowed_actions(self, source_profiles: List[str], target_profile: str):
        """Set baseline actions_allowed based on source/target presence.
        
        Note: use_recursive filtering based on descendants is handled separately
        by adjust_use_recursive_actions_allowed() after evaluation is computed.
        """
        allowed = set([c for c in Action])

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

    def apply_action_info(self, info: ActionInfo) -> None:
        """Apply action info from the mapping actions engine.

        Convention:
        - If info.action is None: Field has no action selected yet -> set self.action to None
        - If info.action is an ActionType: Map to legacy Action enum
        - Legacy Action.MANUAL is only used when explicitly set in manual_entries.yaml
          (which is parsed before this method is called)
        """
        self.action_info = info

        if info.action is None:
            # No action selected yet - user must make a decision
            self.action = None
        else:
            # Map ActionType to legacy Action enum
            self.action = _ACTIONTYPE_TO_LEGACY.get(info.action, Action.MANUAL)

        self.other = info.other_value if isinstance(info.other_value, str) else None
        self.fixed = info.fixed_value if isinstance(info.fixed_value, str) else None

    def to_model(self) -> MappingFieldModel:
        profiles = {k: p.to_model() for k, p in self.profiles.items() if p}

        # Calculate show_mapping_content based on processing status logic
        # If the field has needs_action status (incompatible + use action), hide mapping content
        show_mapping_content = True
        if (self.classification == ComparisonClassification.INCOMPAT and
                self.action == Action.USE):
            show_mapping_content = False

        return MappingFieldModel(
            name=self.name,
            action=self.action,
            other=self.other,
            fixed=self.fixed,
            profiles=profiles,
            actions_allowed=self.actions_allowed,
            classification=self.classification,
            issues=self.issues if self.issues else None,
            show_mapping_content=show_mapping_content,
            action_info=self.action_info,
            evaluation=self.evaluation,
            recommendations=self.recommendations,
        )


class Mapping(Comparison):
    def __init__(self, config: MappingConfig, project) -> None:
        super().__init__(config, project)

        self.fields: OrderedDict[str, MappingField] = OrderedDict()
        self._action_info_map: Dict[str, ActionInfo] = {}
        self._evaluation_map: Dict[str, EvaluationResult] = {}

    def init_ext(self) -> "Mapping":
        self._get_sources(self._config.mappings.sourceprofiles)
        self._get_target(self._config.mappings.targetprofile)
        self._gen_fields()

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
        return f"/project/{self._project.key}/mapping/{self.id}"

    @property
    def manual_entries(self) -> ManualEntries:
        return self._project.manual_entries

    def fill_action_remark(self, manual_entries: ManualEntries):
        manual_mappings = manual_entries.get(self.id) if manual_entries else None

        action_info_map = compute_mapping_actions(self, manual_mappings)
        self._action_info_map = action_info_map
        
        # Compute recommendations separately - returns dict[field_name, list[ActionInfo]]
        recommendations_map = compute_recommendations(self, manual_mappings)
        
        # Original evaluation
        evaluation_map = evaluate_mapping(self, action_info_map)
        
        # NEW: Propagate incompatible status from children to parents
        from ..evaluation import StatusPropagator
        propagator = StatusPropagator(self.fields, evaluation_map)
        evaluation_map = propagator.propagate_incompatible_to_parents()
        
        self._evaluation_map = evaluation_map
        
        # Adjust use_recursive in actions_allowed based on evaluation results
        from ..mapping_actions_engine import adjust_use_recursive_actions_allowed
        adjust_use_recursive_actions_allowed(self, evaluation_map, action_info_map)

        for field_name, field in self.fields.items():
            info = action_info_map.get(field_name)
            if info is not None:
                field.apply_action_info(info)
            else:
                # No manual entry and no automatic action - leave as None (user must decide)
                fallback = ActionInfo(action=None, source=ActionSource.SYSTEM_DEFAULT)
                field.apply_action_info(fallback)

            field.evaluation = evaluation_map.get(field_name)
            
            # Set recommendations list if available
            recommendations = recommendations_map.get(field_name, [])
            field.recommendations = recommendations

    def get_action_info_map(self) -> Dict[str, ActionInfo]:
        return self._action_info_map

    def get_evaluation_map(self) -> Dict[str, EvaluationResult]:
        return self._evaluation_map

    def _gen_fields(self) -> None:
        super()._gen_fields(MappingField)

        if self.sources is None or self.target is None:
            raise NotInitialized()

        all_profiles = [self.target] + self.sources
        all_profiles_keys = [profile.key for profile in all_profiles]
        # Add remarks and actions for each field
        for field in self.fields.values():
            field.fill_allowed_actions(all_profiles_keys[:-1], all_profiles_keys[-1])

    def to_base_model(self) -> MappingBaseModel:
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

        # Calculate status counts based on evaluation results using StatusAggregator
        from ..evaluation import StatusAggregator
        evaluations = self.get_evaluation_map()
        status_counts = StatusAggregator.build_status_summary(evaluations)

        try:
            model = MappingBaseModel(
                id=self.id,
                name=self.name,
                version=self.version,
                last_updated=self.last_updated,
                status=self.status,
                sources=sources,
                target=target,
                url=self.url,
                **status_counts,
            )

        except ValidationError as e:
            print(e.errors())
            raise e

        else:
            return model

    def to_details_model(self) -> MappingDetailsModel:
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

        fields = [f.to_model() for f in self.fields.values()]

        # Calculate status counts based on evaluation results (same as to_base_model)
        evaluations = self.get_evaluation_map()
        status_counts = {
            "total": len(evaluations),
            "incompatible": 0,
            "warning": 0,
            "solved": 0,
            "compatible": 0,
        }

        for result in evaluations.values():
            status = result.mapping_status
            if status.value in status_counts:
                status_counts[status.value] += 1

        try:
            model = MappingDetailsModel(
                id=self.id,
                name=self.name,
                version=self.version,
                last_updated=self.last_updated,
                status=self.status,
                sources=sources,
                target=target,
                url=self.url,
                fields=fields,
                **status_counts,
            )

        except ValidationError as e:
            print(e.errors())
            raise e

        else:
            return model
