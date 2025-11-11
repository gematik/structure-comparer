import logging
from collections import OrderedDict
from math import isinf
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
    # Fehlende Eltern als optional annehmen (FHIR-Default min=0)
    _ASSUME_OPTIONAL_IF_ABSENT = True

    def __init__(self, name: str) -> None:
        self.name = name
        self.profiles: OrderedDict[str, ProfileField | None] = OrderedDict()
        self._classification: ComparisonClassification = ComparisonClassification.COMPAT
        self.issues: list[ComparisonIssue] = []
        self.explanations: list[str] = []

    # ----------------- Ahnen-/Elternprüfung -----------------
    def _parent_path(self, path: str) -> str | None:
        if "." not in path:
            return None
        return path.rsplit(".", 1)[0]

    def _exists_optional_ancestor_in_source(self, source_profile: Profile) -> bool:
        """
        True, wenn IRGENDEIN Ahnenknoten nicht verpflichtend ist:
          - explizit min == 0  ODER
          - fehlt im Profil (wir nehmen optional an, wenn _ASSUME_OPTIONAL_IF_ABSENT=True)
        """
        parent = self._parent_path(self.name)
        while parent:
            pf = source_profile.fields.get(parent)
            if pf is None:
                if self._ASSUME_OPTIONAL_IF_ABSENT:
                    return True
            else:
                if getattr(pf, "min", 0) == 0:
                    return True
            parent = self._parent_path(parent)
        return False

    def _all_sources_have_optional_ancestor(self, sources: list[Profile]) -> bool:
        # Nur die Sources betrachten, in denen das Feld existiert
        candidates = [s for s in sources if self.profiles.get(s.key) is not None]
        if not candidates:
            return False
        return all(self._exists_optional_ancestor_in_source(s) for s in candidates)

    # ----------------- Utils -----------------
    @staticmethod
    def _norm_max(x) -> tuple[bool, int | None]:
        """
        Normalisiert max:
          - (True, None)  -> unbounded (∞)
          - (False, n)    -> endlich mit Wert n
        Akzeptiert: None, int, float(∞), Strings wie "*", "inf", "infinity", "unbounded".
        """
        if x is None:
            return True, None
        if isinstance(x, int):
            return False, x
        if isinstance(x, float):
            if isinf(x):
                return True, None
            return False, int(x)
        if isinstance(x, str):
            s = x.strip().lower()
            if s in {"*", "inf", "infinity", "unbounded"}:
                return True, None
            if s.isdigit():
                return False, int(s)
            return True, None
        return True, None

    @staticmethod
    def _fmt_max(x) -> str:
        unb, val = ComparisonField._norm_max(x)
        return "∞" if unb else str(val if val is not None else 0)

    def _add_issue(self, issue: ComparisonIssue, explanation: str | None = None) -> None:
        if issue not in self.issues:
            self.issues.append(issue)
        if explanation:
            self.explanations.append(explanation)

    @classmethod
    def _max_gt(cls, source_max, target_max) -> bool:
        s_unb, s_val = cls._norm_max(source_max)
        t_unb, t_val = cls._norm_max(target_max)
        if s_unb and t_unb:
            return False
        if s_unb and not t_unb:
            return True
        if not s_unb and t_unb:
            return False
        return (s_val or 0) > (t_val or 0)

    # ----------------- Klassifikation -----------------
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
        self.explanations = []  # pro Lauf neu füllen

        # Target-Feld fehlt komplett
        if tp is None:
            any_source_carries_potential_value = any(
                p is not None and (
                    p.min > 0
                    or p.max_num != 0  # None/∞ zählen als != 0 -> potenziell werthaltig
                    or getattr(p, "must_support", False) is True
                )
                for p in sp
            )

            if any_source_carries_potential_value:
                if self._all_sources_have_optional_ancestor(sources):
                    self.classification = ComparisonClassification.WARN
                    self._add_issue(
                        ComparisonIssue.MIN,
                        f"{self.name}: Ziel-Feld fehlt. Quellen könnten Werte liefern; "
                        f"weiche Warnung, da in allen Quellen ein optionaler Vorfahr die Auslassung zulässt."
                    )
                else:
                    self.classification = ComparisonClassification.INCOMPAT
                    self._add_issue(
                        ComparisonIssue.MIN,
                        f"{self.name}: Ziel-Feld fehlt, obwohl Quellen Werte verlangen/liefern können; "
                        f"keine optionalen Vorfahren → nicht kompatibel."
                    )
            return

        # Target-Feld existiert: Detailprüfungen
        if any((p is None) for p in sp) and tp.min > 0:
            self.classification = ComparisonClassification.INCOMPAT
            self._add_issue(
                ComparisonIssue.MIN,
                f"{self.name}: In mindestens einer Quelle fehlt das Feld, Ziel verlangt min={tp.min} > 0 → nicht kompatibel."
            )

        if any((p and p.min < tp.min) for p in sp):
            if self._all_sources_have_optional_ancestor(sources):
                self.classification = max(self.classification, ComparisonClassification.WARN)
                self._add_issue(
                    ComparisonIssue.MIN,
                    f"{self.name}: min-Anforderung der Quelle ist geringer als im Ziel (Quelle < Ziel). "
                    f"Optionaler Vorfahr erlaubt Auslassung → Warnung."
                )
            else:
                self.classification = ComparisonClassification.INCOMPAT
                self._add_issue(
                    ComparisonIssue.MIN,
                    f"{self.name}: min-Anforderung der Quelle ist geringer als im Ziel (Quelle < Ziel) "
                    f"ohne optionalen Vorfahr → nicht kompatibel."
                )

        if any((p and self._max_gt(p.max_num, tp.max_num)) for p in sp):
            self.classification = ComparisonClassification.INCOMPAT
            self._add_issue(
                ComparisonIssue.MAX,
                f"{self.name}: max der Quelle ({self._fmt_max(next(p.max_num for p in sp if p and self._max_gt(p.max_num, tp.max_num)))}) "
                f"überschreitet max des Ziels ({self._fmt_max(tp.max_num)}) → nicht kompatibel."
            )

        if any((p and p.ref_types != tp.ref_types) for p in sp):
            self.classification = max(self.classification, ComparisonClassification.WARN)
            self._add_issue(
                ComparisonIssue.REF,
                f"{self.name}: Referenztypen in Quelle(n) und Ziel unterscheiden sich → Warnung."
            )

    # ----------------- Mapping ins API-Modell -----------------
    def to_model(self) -> ComparisonFieldModel:
        profiles = {k: p.to_model() if p else None for k, p in self.profiles.items()}
        return ComparisonFieldModel(
            name=self.name,
            profiles=profiles,
            classification=self.classification,
            issues=self.issues if self.issues else None,
            explanations=self.explanations if self.explanations else None,
        )


class Comparison:
    def __init__(self, config: ComparisonConfig, project) -> None:
        self._config = config
        self._project = project
        self.sources: list[Profile] | None = None
        self.target: Profile | None = None
        self.fields: OrderedDict[str, ComparisonField] = OrderedDict()

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
        self.sources = [p for c in profile_configs if (p := self._get_profile(c))]

    def _get_target(self, profile_config: ComparisonProfileConfig) -> None:
        self.target = p if (p := self._get_profile(profile_config)) else None

    def _get_profile(self, c: ComparisonProfileConfig) -> Profile:
        if profile := self._project.get_profile(c.id, c.url, c.version):
            return profile
        else:
            logger.error("source %s %s#%s not found", c.id, c.url, c.version)

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
