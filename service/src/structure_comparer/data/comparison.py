import logging
from collections import OrderedDict

from pydantic import ValidationError

from ..model.comparison import ComparisonClassification
from ..model.comparison import ComparisonDetail as ComparisonDetailModel
from ..model.comparison import ComparisonField as ComparisonFieldModel
from ..model.comparison import ComparisonOverview as ComparisonOverviewModel
from .config import ComparisonConfig, ComparisonProfileConfig
from .profile import Profile, ProfileField

logger = logging.getLogger(__name__)


class ComparisonField:
    def __init__(self, name: str) -> None:
        self.name = name
        self.profiles: OrderedDict[str, ProfileField] = OrderedDict()
        self.classification: ComparisonClassification = None

    def classify(self, sources: list[Profile], target: Profile) -> None:
        sp = [self.profiles[p.key] for p in sources]
        tp = self.profiles[target.key]

        # If target is not set, its incompatible
        if tp is None:
            self.classification = ComparisonClassification.INCOMPAT

        # If any source is absent and target is required
        elif any([p is None for p in sp]) and tp.min > 0:
            self.classification = ComparisonClassification.INCOMPAT

        # Incompatible if any min is lower or max is greater than target
        elif any([p.min < tp.min or p.max > tp.max for p in sp if p]):
            self.classification = ComparisonClassification.INCOMPAT

        # Potential incompatible if cards or MS not matching
        elif any([p.min > tp.min or p.max < tp.max for p in sp if p]) or any(
            [p.must_support != tp.must_support for p in sp if p]
        ):
            self.classification = ComparisonClassification.WARN

        elif any([p is None for p in sp]):
            self.classification = ComparisonClassification.WARN

        else:
            self.classification = ComparisonClassification.COMPAT

    def to_model(self) -> ComparisonFieldModel:
        profiles = {k: p.to_model() if p else None for k, p in self.profiles.items()}
        return ComparisonFieldModel(
            name=self.name, profiles=profiles, classification=self.classification
        )


class Comparison:
    def __init__(self, config: ComparisonConfig, project) -> None:
        self.__config = config
        self.__project = project
        self.sources: list[Profile] | None = None
        self.target: Profile | None = None
        self.fields: OrderedDict[str, ComparisonField] = OrderedDict()

    def init_ext(self):
        self.__get_sources(self.__config.comparison.sourceprofiles)
        self.__get_target(self.__config.comparison.targetprofile)
        self.__gen_fields()

        return self

    @property
    def id(self) -> str:
        return self.__config.id

    @property
    def name(self) -> str:
        source_profiles = ", ".join(
            f"{profile.name}|{profile.version}" for profile in self.sources
        )
        target_profile = f"{self.target.name}|{self.target.version}"
        return f"{source_profiles} -> {target_profile}"

    def __get_sources(self, profile_configs: list[ComparisonProfileConfig]) -> None:
        self.sources = [p for c in profile_configs if (p := self.__get_profile(c))]

    def __get_target(self, profile_config: ComparisonProfileConfig) -> None:
        self.target = p if (p := self.__get_profile(profile_config)) else None

    def __get_profile(self, c: ComparisonProfileConfig) -> Profile:
        if profile := self.__project.get_profile(c.id, c.url, c.version):
            return profile
        else:
            logger.error("source %s %s#%s not found", c.id, c.url, c.version)

    def __gen_fields(self) -> None:
        all_profiles = [self.target] + self.sources

        for profile in all_profiles:
            for field in profile.fields.values():
                field_name = field.path_full

                # Check if field already exists or needs to be created
                if field_name not in self.fields:
                    self.fields[field_name] = ComparisonField(field_name)

                self.fields[field_name].profiles[profile.key] = field

        # Fill the absent profiles
        all_profiles_keys = [profile.key for profile in all_profiles]
        for field in self.fields.values():
            for profile_key in all_profiles_keys:
                if profile_key not in field.profiles:
                    field.profiles[profile_key] = None

        # Classify all fields
        for field in self.fields.values():
            field.classify(self.sources, self.target)

    def to_overview_model(self) -> ComparisonOverviewModel:
        sources = [p.name for p in self.sources]
        target = self.target.name

        try:
            model = ComparisonOverviewModel(
                id=self.id,
                name=self.name,
                sources=sources,
                target=target,
            )

        except ValidationError as e:
            print(e.errors())
            raise e

        else:
            return model

    def to_detail_model(self) -> ComparisonDetailModel:
        sources = [p.to_model() for p in self.sources]
        target = self.target.to_model()
        fields = sorted(
            [f.to_model() for f in self.fields.values()], key=lambda x: x.name
        )

        try:
            model = ComparisonDetailModel(
                id=self.id,
                name=self.name,
                sources=sources,
                target=target,
                fields=fields,
            )

        except ValidationError as e:
            print(e.errors())
            raise e

        else:
            return model
