import logging
from collections import OrderedDict

from pydantic import ValidationError

from ..errors import NotInitialized
from ..model.comparison import ComparisonClassification
from ..model.comparison import ComparisonDetail as ComparisonDetailModel
from ..model.comparison import ComparisonField as ComparisonFieldModel
from ..model.comparison import ComparisonIssue
from ..model.comparison import ComparisonOverview as ComparisonOverviewModel
from .config import ComparisonConfig, ComparisonProfileConfig
from .profile import Profile, ProfileField

logger = logging.getLogger(__name__)


class ComparisonField:
    def __init__(self, name: str) -> None:
        self.name = name
        self.profiles: OrderedDict[str, ProfileField | None] = OrderedDict()
        self._classification: ComparisonClassification = ComparisonClassification.COMPAT
        self.issues: list[ComparisonIssue] = []
        self._profile_objects: dict[str, Profile] = {}  # Maps profile key to Profile object

    # --- NEW: Eltern-Optionalität prüfen ------------------------------------
    def _parent_path(self, path: str) -> str | None:
        if "." not in path:
            return None
        return path.rsplit(".", 1)[0]

    def _is_parent_optional_in_source(self, source_profile: Profile) -> bool:
        """
        True, wenn entlang der Elternkette ein Elternknoten existiert, der optional ist:
        - min == 0 und kein mustSupport == True
        Sobald ein Elternknoten min>0 oder mustSupport==True ist, ist das Feld effektiv „aktivierbar“ -> False.
        Falls kein Elternknoten gefunden wird, gilt: False.
        """
        parent = self._parent_path(self.name)
        while parent:
            pf = source_profile.fields.get(parent)
            if pf is not None:
                # Harte Aktivierung -> Eltern ist nicht optional
                if pf.min > 0 or getattr(pf, "must_support", False) is True:
                    return False
                # Optionaler Elternknoten gefunden
                if pf.min == 0 and getattr(pf, "must_support", False) is False:
                    return True
            parent = self._parent_path(parent)
        return False

    def _all_sources_have_optional_parent(self, sources: list[Profile]) -> bool:
        # nur Profile betrachten, in denen das aktuelle Feld überhaupt existiert
        candidates = [s for s in sources if self.profiles.get(s.key) is not None]
        if not candidates:
            return False
        return all(self._is_parent_optional_in_source(s) for s in candidates)
    # ------------------------------------------------------------------------

    @property
    def classification(self) -> ComparisonClassification:
        return self._classification

    @classification.setter
    def classification(self, value: ComparisonClassification) -> None:
        if self._classification < value:
            self._classification = value

    def classify(self, sources: list[Profile], target: Profile) -> None:
        sp = [self.profiles[p.key] for p in sources]
        tp = self.profiles[target.key]

        self.classification = ComparisonClassification.COMPAT

        if tp is None:
            # Target-Feld existiert nicht.
            # Bisher: INCOMPAT, sobald irgendein Source das Feld potentiell tragen kann.
            # Neu: Wenn alle Sources für dieses Feld einen OPTIONALEN Elternknoten haben,
            #      dann nur WARN (nicht INCOMPAT).
            any_source_carries_potential_value = any(
                p is not None
                and (
                    p.min > 0
                    or p.max_num != 0  # None (=unbounded) zählt als != 0
                    or getattr(p, "must_support", False) is True
                )
                for p in sp
            )

            if any_source_carries_potential_value:
                if self._all_sources_have_optional_parent(sources):
                    # Downgrade auf WARN, da das Feld nur dann „fehlt“,
                    # wenn der optionale Elternknoten überhaupt instanziiert wird.
                    self.classification = ComparisonClassification.WARN
                    # Issue-Typ beibehalten: MIN zeigt „Anforderung im Source“ an.
                    if ComparisonIssue.MIN not in self.issues:
                        self.issues.append(ComparisonIssue.MIN)
                else:
                    self.classification = ComparisonClassification.INCOMPAT
                    if ComparisonIssue.MIN not in self.issues:
                        self.issues.append(ComparisonIssue.MIN)
            # Falls kein Source das Feld tragen kann, bleibt COMPAT.
            return

        # (Restliche bestehende Prüfungen, wenn tp vorhanden ist)
        if any([p is None for p in sp]) and tp.min > 0:
            self.classification = ComparisonClassification.INCOMPAT
            self.issues.append(ComparisonIssue.MIN)

        if any([p and p.min < tp.min for p in sp]):
            # Optionaler Elternknoten in allen Sources? -> Downgrade auf WARN
            if self._all_sources_have_optional_parent(sources):
                self.classification = max(self.classification, ComparisonClassification.WARN)
                self.issues.append(ComparisonIssue.MIN)
            else:
                self.classification = ComparisonClassification.INCOMPAT
                self.issues.append(ComparisonIssue.MIN)

        if any([p and p.max_num > tp.max_num for p in sp]):
            self.classification = ComparisonClassification.INCOMPAT
            self.issues.append(ComparisonIssue.MAX)

        if any([p and p.ref_types != tp.ref_types for p in sp]):
            self.classification = max(self.classification, ComparisonClassification.WARN)
            self.issues.append(ComparisonIssue.REF)

    def to_model(self) -> ComparisonFieldModel:
        profiles = {}
        for k, p in self.profiles.items():
            if p is None:
                profiles[k] = None
            else:
                # Get the Profile object for this profile key
                profile_obj = self._profile_objects.get(k)
                all_fields = profile_obj.fields if profile_obj else None
                profiles[k] = p.to_model(all_fields)
        
        return ComparisonFieldModel(
            name=self.name,
            profiles=profiles,
            classification=self.classification,
            issues=self.issues if self.issues else None,
        )


class Comparison:
    def __init__(self, config: ComparisonConfig, project) -> None:
        self._config = config
        self._project = project
        self.sources: list[Profile] | None = None
        self.target: Profile | None = None
        self.fields: OrderedDict[str, ComparisonField] = OrderedDict()
        # Store profile configs for metadata access
        self._source_configs: list[ComparisonProfileConfig] = []
        self._target_config: ComparisonProfileConfig | None = None

    def init_ext(self) -> "Comparison":
        self._get_sources(self._config.comparison.sourceprofiles)
        self._get_target(self._config.comparison.targetprofile)
        self._gen_fields(ComparisonField)

        return self

    @property
    def id(self) -> str:
        return self._config.id

    @property
    def name(self) -> str:
        if self.sources is None or self.target is None:
            return ""

        source_profiles = ", ".join(
            f"{profile.name}|{profile.version}" for profile in self.sources
        )
        target_profile = f"{self.target.name}|{self.target.version}"
        return f"{source_profiles} -> {target_profile}"

    def _get_sources(self, profile_configs: list[ComparisonProfileConfig]) -> None:
        self._source_configs = profile_configs
        self.sources = []
        for c in profile_configs:
            p = self._get_profile(c)
            if p:
                self.sources.append(p)

    def _get_target(self, profile_config: ComparisonProfileConfig) -> None:
        self._target_config = profile_config
        self.target = self._get_profile(profile_config)

    def _get_profile(self, c: ComparisonProfileConfig) -> Profile:
        # Use url (canonical URL) for profile lookup
        profile = None
        
        if c.url:
            profile = self._project.get_profile(c.id, c.url, c.version)
        
        if not profile:
            logger.error("source %s url=%s version %s not found", c.id, c.url, c.version)
        
        return profile
    
    def get_profile_metadata(self, profile: Profile) -> dict:
        """Get metadata (webUrl, package) for a profile from its config."""
        # Check if this is a source profile
        for i, src_profile in enumerate(self.sources or []):
            if src_profile is profile and i < len(self._source_configs):
                config = self._source_configs[i]
                return {
                    "webUrl": config.webUrl,
                    "package": config.package
                }
        
        # Check if this is the target profile
        if self.target is profile and self._target_config:
            return {
                "webUrl": self._target_config.webUrl,
                "package": self._target_config.package
            }
        
        return {"webUrl": None, "package": None}

    def _gen_fields(self, FieldType: type) -> None:
        if self.sources is None or self.target is None:
            raise NotInitialized()

        all_profiles = [self.target] + self.sources

        for profile in all_profiles:
            for field in profile.fields.values():
                field_name = field.path_full

                # Check if field already exists or needs to be created
                if field_name not in self.fields:
                    self.fields[field_name] = FieldType(field_name)

                self.fields[field_name].profiles[profile.key] = field
                # Store reference to the Profile object
                self.fields[field_name]._profile_objects[profile.key] = profile

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
        if self.sources is None or self.target is None:
            raise NotInitialized()

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
        if self.sources is None or self.target is None:
            raise NotInitialized()

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
