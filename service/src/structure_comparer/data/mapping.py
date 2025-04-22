import logging
from collections import OrderedDict
from dataclasses import dataclass
from typing import Dict, List

from pydantic import ValidationError

from ..action import Action
from ..consts import REMARKS
from ..manual_entries import (
    MANUAL_ENTRIES_ACTION,
    MANUAL_ENTRIES_EXTRA,
    MANUAL_ENTRIES_REMARK,
    ManualEntries,
)
from ..model.mapping import MappingBase as MappingBaseModel
from ..model.mapping import MappingDetails as MappingDetailsModel
from ..model.mapping import MappingField as MappingFieldModel
from .config import MappingConfig, MappingProfileConfig
from .profile import Profile, ProfileField

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


@dataclass(init=False)
class MappingField:
    def __init__(self) -> None:
        self.action: Action = None
        self.extension: str = None
        self.extra: str = None
        self.profiles: Dict[str, ProfileField] = {}
        self.remark = None
        self.actions_allowed: List[Action] = []

    @property
    def name(self) -> str:
        return list(self.profiles.values())[0].path_full

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
        self, comparison: "Mapping", manual_entries: Dict
    ) -> None:
        """
        Classify and get the remark for the property

        First, the manual entries and manual suffixes are checked. If neither is the case, it classifies the property
        based on the presence of the property in the KBV and ePA profiles.
        """

        action = None
        remark = None
        extra = None

        # If there is a manual entry for this property, use it
        if manual_entries is not None and (manual_entry := manual_entries[self.name]):
            action = manual_entry.get(MANUAL_ENTRIES_ACTION, Action.MANUAL)

            # If there is a remark in the manual entry, use it else use the default remark
            remark = manual_entry.get(MANUAL_ENTRIES_REMARK, REMARKS[action])

            # If the action needs extra information, generate the remark with the extra information
            if action in EXTRA_ACTIONS:
                extra = manual_entry[MANUAL_ENTRIES_EXTRA]
                remark = REMARKS[action].format(extra)

        # If the last element from the property is in the manual list, use the manual action
        elif self.name_child in MANUAL_SUFFIXES:
            action = Action.MANUAL

        # If the parent has an action that can be derived use the parent's action
        elif (
            parent_update := comparison.fields.get(self.name_parent)
        ) and parent_update.action in DERIVED_ACTIONS:
            action = parent_update.action

            # If the action needs extra information derived that information from the parent
            if action in EXTRA_ACTIONS:

                # Cut away the common part with the parent and add the remainder to the parent's extra
                extra = parent_update.extra + self.name[len(self.name_parent) :]
                remark = REMARKS[action].format(extra)

            # Else use the parent's remark
            else:
                remark = parent_update.remark

        # If present in any of the source profiles
        elif any(
            [self.profiles[profile.key] is not None for profile in comparison.sources]
        ):
            if self.profiles[comparison.target.key] is not None:
                action = Action.USE
            else:
                action = Action.EXTENSION
        else:
            action = Action.EMPTY

        if not remark:
            remark = REMARKS[action]

        self.action = action
        self.remark = remark
        self.extra = extra

    def to_model(self) -> MappingFieldModel:
        profiles = {k: p.to_model() for k, p in self.profiles.items() if p}

        return MappingFieldModel(
            name=self.name,
            action=self.action,
            other=self.extra,
            profiles=profiles,
            remark=self.remark,
            actions_allowed=self.actions_allowed,
        )


class Mapping:
    def __init__(self, config: MappingConfig, project) -> None:
        self.__config = config
        self.__project = project
        self.sources: List[Profile] | None = None
        self.target: Profile | None = None
        self.fields: OrderedDict[str, MappingField] = OrderedDict()

        self.__get_sources()
        self.__get_target()
        self.__gen_fields()

    @property
    def id(self) -> str:
        return self.__config.id

    @property
    def version(self) -> str:
        return self.__config.version

    @property
    def last_updated(self) -> str:
        return self.__config.last_updated

    @property
    def status(self) -> str:
        return self.__config.status

    @property
    def name(self) -> str:
        source_profiles = ", ".join(
            f"{profile.name}|{profile.version}" for profile in self.sources
        )
        target_profile = f"{self.target.name}|{self.target.version}"
        return f"{source_profiles} -> {target_profile}"

    @property
    def url(self) -> str:
        return f"/project/{self.__project.key}/mapping/{self.id}"

    @property
    def manual_entries(self) -> ManualEntries:
        return self.__project.manual_entries

    def fill_action_remark(self, manual_entries: ManualEntries):
        manual_entries = manual_entries.entries.get(self.id)
        for field in self.fields.values():
            field.classify_remark_field(self, manual_entries)

    def __get_sources(self) -> None:
        self.sources = []
        for source in self.__config.mappings.sourceprofiles:
            profile = self.__get_profile(source)
            if profile:
                self.sources.append(profile)

    def __get_target(self) -> None:
        profile = self.__get_profile(self.__config.mappings.targetprofile)
        if profile:
            self.target = profile

    def __get_profile(self, mapping_profile_config: MappingProfileConfig) -> Profile:
        id = mapping_profile_config.id
        version = mapping_profile_config.version
        if profile := self.__project.get_profile(id, version):
            return profile
        else:
            logger.error("source %s#%s not found", id, version)

    def __gen_fields(self) -> None:
        all_profiles = [self.target] + self.sources

        for profile in all_profiles:
            for field in profile.fields.values():
                # Check if field already exists or needs to be created
                if field.path_full not in self.fields:
                    self.fields[field.path_full] = MappingField()

                self.fields[field.path_full].profiles[profile.key] = field

            # Sort the fields by name
            self.fields = OrderedDict(sorted(self.fields.items(), key=lambda x: x[0]))

            # Fill the absent profiles
            all_profiles_keys = [profile.key for profile in all_profiles]
            for field in self.fields.values():
                for profile_key in all_profiles_keys:
                    if profile_key not in field.profiles:
                        field.profiles[profile_key] = None

            # Add remarks and actions for each field
            for field in self.fields.values():
                field.fill_allowed_actions(
                    all_profiles_keys[:-1], all_profiles_keys[-1]
                )

    def to_base_model(self) -> MappingBaseModel:
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

        else:
            return model

    def to_details_model(self) -> MappingDetailsModel:
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

        else:
            return model
