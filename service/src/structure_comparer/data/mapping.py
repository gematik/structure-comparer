import logging
from collections import OrderedDict
from typing import List

from pydantic import ValidationError

from ..action import Action
from ..consts import REMARKS
from ..errors import NotInitialized
from ..manual_entries import ManualEntries
from ..model.manual_entries import ManualEntriesMapping as ManualEntriesMappingModel
from ..model.mapping import MappingBase as MappingBaseModel
from ..model.mapping import MappingDetails as MappingDetailsModel
from ..model.mapping import MappingField as MappingFieldModel
from .comparison import Comparison, ComparisonField
from .config import MappingConfig
from ..model.comparison import ComparisonClassification

MANUAL_SUFFIXES = ["reference", "profile"]

# These actions generate a remark with extra information
EXTRA_ACTIONS = [
    Action.COPY_FROM,
    Action.COPY_TO,
    Action.FIXED,
]

# These actions can be derived from their parents
DERIVED_ACTIONS = [
    Action.EMPTY,
    Action.NOT_USE,
] + EXTRA_ACTIONS

logger = logging.getLogger(__name__)


class MappingField(ComparisonField):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.action: Action = Action.USE
        self.extension: str | None = None
        self.other: str | None = None
        self.fixed: str | None = None
        self.remark = None
        self.actions_allowed: List[Action] = []

    @property
    def name_child(self) -> str:
        return self.name.rsplit(".", 1)[1]

    @property
    def name_parent(self) -> str:
        return self.name.rsplit(".", 1)[0]

    def fill_allowed_actions(self, source_profiles: List[str], target_profile: str):
        allowed = set([c for c in Action])

        any_source_present = any(
            [self.profiles[profile] is not None for profile in source_profiles]
        )
        target_present = self.profiles[target_profile] is not None

        if not any_source_present:
            allowed -= set([Action.USE, Action.NOT_USE, Action.COPY_TO])
        else:
            allowed -= set([Action.EMPTY])
        if not target_present:
            allowed -= set([Action.USE, Action.EMPTY, Action.COPY_FROM])

        self.actions_allowed = list(allowed)

    def classify_remark_field(
        self, mapping: "Mapping", manual_entries: ManualEntriesMappingModel
    ) -> None:
        """
        Classify and get the remark for the property

        First, the manual entries and manual suffixes are checked. If neither is the case, it classifies the property
        based on the presence of the property in the KBV and ePA profiles.
        """

        # If there is a manual entry for this property, use it
        if manual_entries is not None and (
            manual_entry := manual_entries.get(self.name)
        ):
            self.action = manual_entry.action if manual_entry.action else Action.MANUAL

            # If there is a remark in the manual entry, use it else use the default remark
            if manual_entry.remark:
                self.remark = manual_entry.remark

            # If the action needs extra information, generate the remark with the extra information
            if self.action == Action.FIXED:
                self.fixed = manual_entry.fixed
                self.other = None
                self.remark = REMARKS[self.action].format(self.fixed)

            elif self.action == Action.COPY_FROM or self.action == Action.COPY_TO:
                self.fixed = None
                self.other = manual_entry.other
                self.remark = REMARKS[self.action].format(self.other)

        # If the last element from the property is in the manual list, use the manual action
        elif self.name_child in MANUAL_SUFFIXES:
            self.action = Action.MANUAL

        # If the parent has an action that can be derived use the parent's action
        elif (
            parent_update := mapping.fields.get(self.name_parent)
        ) and parent_update.action in DERIVED_ACTIONS:
            self.action = parent_update.action

            # If the action needs extra information derived that information from the parent
            if self.action in EXTRA_ACTIONS:

                # Cut away the common part with the parent and add the remainder to the parent's extra
                if parent_update.other is not None:
                    self.other = (
                        parent_update.other + self.name[len(self.name_parent) :]
                    )
                else:
                    raise ValueError("Error with the data: parent_update.other is None")
                self.remark = REMARKS[self.action].format(self.other)

            # Else use the parent's remark
            else:
                self.remark = parent_update.remark

        # If present in any of the source profiles
        elif any(
            [self.profiles[profile.key] is not None for profile in mapping.sources]
        ):
            if self.profiles[mapping.target.key] is not None:
                self.action = Action.USE
            else:
                self.action = Action.EXTENSION
        else:
            self.action = Action.EMPTY

        if not self.remark:
            self.remark = REMARKS[self.action]

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
            remark=self.remark,
            actions_allowed=self.actions_allowed,
            classification=self.classification,
            issues=self.issues if self.issues else None,
            show_mapping_content=show_mapping_content,
        )


class Mapping(Comparison):
    def __init__(self, config: MappingConfig, project) -> None:
        super().__init__(config, project)

        self.fields: OrderedDict[str, MappingField] = OrderedDict()

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
        manual_mappings = manual_entries.get(self.id)

        if manual_mappings is not None:
            for field in self.fields.values():
                field.classify_remark_field(self, manual_mappings)

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

        sources = [p.to_model() for p in self.sources]
        target = self.target.to_model()

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
            )

        except ValidationError as e:
            print(e.errors())
            raise e

        else:
            return model

    def to_details_model(self) -> MappingDetailsModel:
        if self.sources is None or self.target is None:
            raise NotInitialized()

        sources = [p.to_model() for p in self.sources]
        target = self.target.to_model()

        fields = [f.to_model() for f in self.fields.values()]

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
            )

        except ValidationError as e:
            print(e.errors())
            raise e

        else:
            return model
