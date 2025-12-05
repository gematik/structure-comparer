
Extension Action - Kompatibilität und Vererbung implementieren

## STATUS: ✅ IMPLEMENTIERT (04.12.2025)

Die neue extension Action wurde erfolgreich implementiert und die folgenden Features wurden hinzugefügt:

1. ✅ **Kompatibilitäts-Status:** Felder mit `action: extension` werden als **SOLVED** markiert
2. ✅ **Vererbung an Kind-Felder:** Kind-Felder bekommen automatisch **Empfehlungen** (recommendations) mit angepasstem `other` Wert

## Quick Summary

**Was wurde implementiert:**
- Extension Actions werden jetzt wie copy_from/copy_to behandelt
- Parent-Felder mit extension Action bekommen Status **SOLVED**
- Kind-Felder bekommen automatisch **extension Recommendations** mit korrektem other_value
- Die Empfehlungen sind nicht automatisch aktiv - User muss sie explizit akzeptieren
- **Bug Fix:** Parent-Felder mit manueller Action werden NICHT mehr als "Inkompatibel (vererbt)" markiert

**Gelöstes Problem:**
- ❌ **Vorher:** Parent mit EXTENSION Action wurde als "↓ Inkompatibel (vererbt)" angezeigt
- ✅ **Nachher:** Parent mit EXTENSION Action wird korrekt als "✓ Gelöst" angezeigt
- **Root Cause:** `StatusPropagator` hat nicht geprüft, ob ein Feld eine manuelle Action hat
- **Lösung:** Felder mit `ActionSource.MANUAL` werden von der Status-Propagierung ausgenommen

**Beispiel:**
```yaml
# Manual Entry
- action: extension
  name: Organization.address:Strassenanschrift.line.extension
  other: Organization.address.line

# Ergebnis:
# Parent: Status = SOLVED ✅ (nicht mehr "Inkompatibel vererbt")
# Kind (.extension:Hausnummer): Bekommt Recommendation mit other = "Organization.address.line:Hausnummer"
```

---

## Erkenntnisse aus der Code-Analyse

### 1. Mapping Evaluation Engine
**Datei:** `mapping_evaluation_engine.py`

**Funktion:** `_evaluate_field(field, action_info: ActionInfo)`
- Diese Funktion bewertet ein Feld basierend auf dessen Klassifikation und zugehöriger Action
- Felder mit `classification="incompatible"` werden als **RESOLVED** markiert, wenn sie eine Action haben
- Actions können von drei Quellen kommen:
  - `ActionSource.MANUAL` (vom Benutzer gesetzt)
  - `ActionSource.INHERITED` (von Parent-Feld vererbt)
  - `ActionSource.SYSTEM_DEFAULT` (System-generiert, z.B. FIXED)

**Funktion:** `derive_mapping_status(field_evaluation, action_info)`
- Konvertiert den Evaluation-Status in einen Mapping-Status
- `has_explicit_action = True` wenn:
  - Action ist MANUAL oder INHERITED, ODER
  - Action ist SYSTEM_DEFAULT und auto_generated=True
- Felder mit expliziter Action und Status RESOLVED/ACTION_REQUIRED bekommen `MappingStatus.SOLVED`

**Änderung durchgeführt:**
- ✅ Keine Änderung nötig - Extension Actions werden bereits korrekt als "resolved" erkannt
- Der Code prüft nur, ob eine Action vorhanden ist und die Quelle MANUAL/INHERITED/SYSTEM_DEFAULT ist
- Da Extension Actions als MANUAL gesetzt werden, funktioniert die Logik bereits

---

### 2. Inheritance Engine
**Datei:** `inheritance_engine.py`

**Funktion:** `can_inherit_action(action_type)`
- Prüft, welche Action-Types vererbt werden können
- Original nur: EMPTY, USE_RECURSIVE, COPY_FROM, COPY_TO
- **Änderung:** ✅ ActionType.EXTENSION hinzugefügt

**Funktion:** `is_copy_action(action_type)`
- Prüft, ob eine Action vom Typ "copy" ist (copy_from, copy_to)
- Wird für die Vererbungslogik verwendet
- **Änderung:** ✅ ActionType.EXTENSION hinzugefügt (behandelt wie copy Actions)

**Funktion:** `create_inherited_recommendation(field_name, parent_field_name, parent_action)`
- Erstellt inherited recommendations für copy_from/copy_to Actions
- Berechnet den inherited other_value durch Anhängen des Kind-Suffixes
- **Änderung:** ✅ Funktioniert jetzt auch für EXTENSION Actions

**Funktion:** `calculate_inherited_other_value(field_name, parent_field_name, parent_other_value)`
- Berechnet den other_value für Kind-Felder
- Beispiel: Parent "Medication.extension:A" -> "Medication.extension:B"
           Kind "Medication.extension:A.url" -> "Medication.extension:B.url"
- Unterstützt auch sliced fields mit Fallback zum Base-Feld
- Kennzeichnet implizite Slices (is_implicit_slice=True) wenn Ziel-Feld nicht explizit existiert
- **Keine Änderung nötig** - funktioniert bereits für alle copy-ähnlichen Actions

---

### 3. Mapping Actions Engine
**Datei:** `mapping_actions_engine.py`

**Konstante:** `_INHERITABLE_ACTIONS`
- Definiert, welche Actions an Kind-Felder vererbt werden können
- Original: EMPTY, USE_RECURSIVE, COPY_FROM, COPY_TO
- **Änderung:** ✅ ActionType.EXTENSION hinzugefügt

**Funktion:** `_inherit_or_default(field_name, field, result, all_fields, target_key)`
- Entscheidet, ob ein Feld eine vererbte Action bekommt oder den Default
- Behandelt copy_from/copy_to NICHT als aktive vererbte Actions
- Diese werden stattdessen als Empfehlungen (recommendations) behandelt
- **Änderung:** ✅ EXTENSION ebenfalls als Empfehlung behandeln (nicht als aktive Action)

---

### 4. Recommendation Engine & Copy Recommender
**Datei:** `recommendations/recommendation_engine.py` & `recommendations/copy_recommender.py`

**Mechanismus:**
1. `RecommendationEngine.compute_all_recommendations()` ruft verschiedene Recommenders auf
2. `CopyRecommender.compute_recommendations()` erstellt Empfehlungen für copy_from/copy_to
3. Verwendet `InheritedRecommender.compute_inherited_recommendations()` mit einer Factory-Funktion
4. Factory erstellt Recommendations nur wenn:
   - Ziel-Feld existiert (oder implizit valide ist)
   - Keine Type-Inkompatibilität vorliegt
   - Keine Konflikte mit dem Ziel-Feld bestehen (für copy_to)

**Änderung durchgeführt:**
- ✅ `CopyRecommender` erweitert um EXTENSION zu unterstützen
- ✅ `action_types` Set um `ActionType.EXTENSION` erweitert
- ✅ Docstrings aktualisiert

---

### 5. Inherited Recommender
**Datei:** `recommendations/inherited_recommender.py`

**Funktion:** `compute_inherited_recommendations(action_types, recommendation_factory)`
- Generische Methode für vererbte Empfehlungen
- GREEDY BEHAVIOR: Alle Nachfahren-Felder bekommen Empfehlungen
- Sucht rekursiv nach Parent-Feldern mit Actions aus `action_types`
- Verwendet `recommendation_factory` um konkrete Empfehlung zu erstellen

**Keine Änderung nötig** - arbeitet bereits generisch mit action_types Set

---

## Durchgeführte Änderungen

### 1. mapping_actions_engine.py
```python
_INHERITABLE_ACTIONS = {
    ActionType.EMPTY,
    ActionType.USE_RECURSIVE,
    ActionType.COPY_FROM,
    ActionType.COPY_TO,
    ActionType.EXTENSION,  # ✅ NEU: Extension actions should be inherited to child fields
}
```

```python
# In _inherit_or_default():
is_copy_action = parent_info.action in {
    ActionType.COPY_FROM,
    ActionType.COPY_TO,
    ActionType.EXTENSION,  # ✅ NEU: Extension actions also handled as recommendations
}
```

### 2. inheritance_engine.py
```python
# In can_inherit_action():
inheritable_actions = {
    ActionType.EMPTY,
    ActionType.USE_RECURSIVE,
    ActionType.COPY_FROM,
    ActionType.COPY_TO,
    ActionType.EXTENSION,  # ✅ NEU
}
```

```python
# In is_copy_action():
def is_copy_action(self, action_type: Optional[ActionType]) -> bool:
    """Check if an action type is a copy action (copy_from, copy_to, or extension)."""
    if action_type is None:
        return False
    return action_type in {ActionType.COPY_FROM, ActionType.COPY_TO, ActionType.EXTENSION}
```

```python
# In create_inherited_recommendation():
"""Create an inherited recommendation for copy_from/copy_to/extension actions."""
# ✅ Docstring erweitert, Funktionalität bereits vorhanden
```

### 3. mapping_evaluation_engine.py
```python
# In _evaluate_field() für incompatible classification:
# EXTENSION actions are also considered as resolving incompatibility
has_action = (
    action_info.action is not None
    and action_info.source in (
        ActionSource.MANUAL,
        ActionSource.INHERITED,
        ActionSource.SYSTEM_DEFAULT
    )
)
# ✅ Kommentar hinzugefügt - Code funktioniert bereits korrekt
```

### 4. recommendations/copy_recommender.py
```python
class CopyRecommender:
    """Generates inherited copy_from/copy_to/extension recommendations."""
    # ✅ Docstring erweitert
```

```python
def compute_recommendations(self) -> Dict[str, list[ActionInfo]]:
    """Compute inherited recommendations for copy_from/copy_to/extension actions."""
    # ✅ Docstring erweitert
```

```python
return self.inherited_recommender.compute_inherited_recommendations(
    action_types={ActionType.COPY_FROM, ActionType.COPY_TO, ActionType.EXTENSION},
    # ✅ ActionType.EXTENSION zum Set hinzugefügt
    recommendation_factory=recommendation_factory_with_conflict_check
)
```

---

## Test-Szenario

Das folgende Szenario sollte jetzt funktionieren:

```yaml
# Input in manual_entries.yaml
- action: extension
  name: Organization.address:Strassenanschrift.line.extension
  other: Organization.address.line
```

**Erwartetes Verhalten:**

1. **Parent-Feld:** `Organization.address:Strassenanschrift.line.extension`
   - Hat manuelle Action: `extension`
   - Status: **SOLVED** ✅
   - `other`: `Organization.address.line`

2. **Kind-Felder:** z.B. `Organization.address:Strassenanschrift.line.extension:Hausnummer`
   - Haben **Recommendation** (nicht aktive Action)
   - Recommendation: `action: extension`
   - Recommendation `other`: `Organization.address.line.extension:Hausnummer`
   - Status: bleibt **COMPATIBLE** oder **WARNING** (je nach Klassifikation)
   - User kann Recommendation akzeptieren → dann Status **SOLVED**

---

## Zusammenfassung der Architektur

### Action Flow:
1. **Manual Entry** → `compute_mapping_actions()` → ActionInfo mit source=MANUAL
2. **Inheritance Check** → `_inherit_or_default()` → Für EXTENSION: KEINE aktive Vererbung
3. **Recommendation Engine** → `CopyRecommender` → Erstellt Empfehlungen für Kind-Felder
4. **Evaluation** → `_evaluate_field()` → Parent mit EXTENSION = SOLVED

### Warum Recommendations statt aktive Actions?
- **Copy Actions (copy_from, copy_to, extension)** werden nicht automatisch vererbt
- Stattdessen bekommen Kind-Felder **Empfehlungen**
- User muss Empfehlung explizit akzeptieren
- Verhindert ungewollte automatische Mappings
- Gibt User volle Kontrolle über jedes einzelne Feld

### Code-Pfad für Extension-Vererbung:
```
manual_entries.yaml → extension action
↓
compute_mapping_actions() → ActionInfo(action=EXTENSION, source=MANUAL)
↓
evaluate_mapping() → Parent field = SOLVED ✅
↓
compute_recommendations() → RecommendationEngine
↓
CopyRecommender.compute_recommendations()
  action_types = {COPY_FROM, COPY_TO, EXTENSION}
↓
InheritedRecommender.compute_inherited_recommendations()
  Für jedes Kind-Feld:
    - Sucht Parent mit EXTENSION
    - Ruft InheritanceEngine.create_inherited_recommendation()
    - Berechnet other_value (Parent.suffix → other.suffix)
↓
Kind-Felder bekommen Recommendation mit angepasstem other_value
```

---

## Nächste Schritte (optional)

### Testing
- [x] Unit-Test schreiben analog zu `test_inherited_copy_recommendations.py`
- [x] Test für extension Action auf Parent-Feld
- [x] Test für Empfehlungen auf Kind-Feldern
- [x] Test für korrekten other_value in Recommendations
- **Status:** ✅ Alle Tests bestehen (6/6 in test_extension_inheritance.py)

### Integration Testing
- [ ] Realen Use-Case mit Organization.address:Strassenanschrift testen
- [ ] Frontend-Darstellung der Empfehlungen prüfen
- [ ] Akzeptieren der Empfehlung und Überprüfung des Status

---

## Änderungslog

**04.12.2025 - Fix: Parent mit manueller Action wird nicht mehr als "inherited incompatible" markiert**
- ✅ StatusPropagator erweitert um `actions` Parameter zu akzeptieren
- ✅ Prüfung hinzugefügt: Felder mit `ActionSource.MANUAL` werden NICHT als inherited incompatible markiert
- ✅ Bug behoben: Parent-Felder mit extension Action werden nicht mehr als "Inkompatibel (vererbt)" angezeigt
- ✅ Unit-Tests erstellt (3/3 neu)
- **Problem:** Parent-Feld hatte manuelle EXTENSION Action, wurde aber trotzdem als "Inkompatibel (vererbt)" markiert
- **Lösung:** StatusPropagator prüft jetzt, ob ein Feld eine manuelle Action hat, bevor es als inherited incompatible markiert wird

**04.12.2025 - Initiale Implementierung**
- ✅ ActionType.EXTENSION zu _INHERITABLE_ACTIONS hinzugefügt
- ✅ InheritanceEngine.can_inherit_action() um EXTENSION erweitert
- ✅ InheritanceEngine.is_copy_action() um EXTENSION erweitert
- ✅ mapping_actions_engine._inherit_or_default() um EXTENSION erweitert
- ✅ CopyRecommender um EXTENSION Support erweitert
- ✅ Alle relevanten Docstrings aktualisiert
- ✅ Kommentare in mapping_evaluation_engine hinzugefügt (Code bereits korrekt)
- ✅ Unit-Tests erstellt und alle Tests bestehen (6/6 neu, 36/36 bestehende)

**Geänderte Dateien:**
1. `service/src/structure_comparer/mapping_actions_engine.py`
2. `service/src/structure_comparer/inheritance_engine.py`
3. `service/src/structure_comparer/mapping_evaluation_engine.py`
4. `service/src/structure_comparer/recommendations/copy_recommender.py`
5. `service/src/structure_comparer/evaluation/status_propagator.py` ⭐ NEU
6. `service/src/structure_comparer/data/mapping.py` ⭐ NEU
7. `service/tests/test_extension_inheritance.py` (neu)
8. `service/tests/test_status_propagator_with_manual_actions.py` ⭐ NEU
9. `docs/Extension_compatibily.md` (dieses Dokument)

**Test-Ergebnisse:**
```
tests/test_extension_inheritance.py
✅ test_parent_extension_action_marked_as_solved
✅ test_parent_extension_creates_child_recommendation
✅ test_multiple_children_get_extension_recommendations
✅ test_child_with_manual_action_no_extension_recommendation
✅ test_extension_action_is_inheritable
✅ test_extension_in_inheritable_actions

tests/test_status_propagator_with_manual_actions.py
✅ test_parent_with_manual_action_not_marked_as_inherited_incompatible
✅ test_parent_without_manual_action_marked_as_inherited_incompatible
✅ test_parent_with_inherited_action_still_marked_as_inherited_incompatible

Bestehende Tests (keine Regression):
✅ tests/test_inherited_copy_recommendations.py (8/8)
✅ tests/test_mapping_actions_engine.py (18/18)
✅ tests/test_mapping_evaluation_engine.py (10/10)
```

---

Dateien zum Untersuchen:

mapping_evaluation_engine.py
inheritance_engine.py
recommendation_engine.py
mapping_actions_engine.py
test_inherited_copy_recommendations.py (als Referenz)
Analysiere zuerst den aktuellen Code, erkläre die Mechanismen und implementiere dann die Änderungen Schritt für Schritt mit ausführlichen Erklärungen.