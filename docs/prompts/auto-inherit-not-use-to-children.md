# Aufgabe: Automatische NOT_USE Vererbung für direkte Kinder

## Requirement:
Wenn ein Benutzer auf einem Eltern-Feld die Aktion `not_use` wählt, sollen **automatisch alle direkten Kinder** ebenfalls die Aktion `not_use` erhalten. Dies soll keine Empfehlung sein, sondern eine tatsächliche Zuweisung der Aktion.

## Hintergrund:
Aktuell wird `NOT_USE` von Eltern auf Kinder vererbt (siehe `InheritedRecommender`), aber nur als Empfehlung. Die neue Anforderung ist, dass wenn ein Eltern-Feld `NOT_USE` hat (aus `manual_entries.yaml`), alle direkten Kinder **automatisch** `NOT_USE` bekommen sollen, als ob sie selbst annotiert worden wären.

## Zu implementieren:

### 1. Implementierung in `compute_mapping_actions()`
**Datei:** `/Users/Shared/dev/structure-comparer/service/src/structure_comparer/mapping_actions_engine.py`

- Nach dem Verarbeiten der manuellen Einträge
- Für jedes Feld mit `action = NOT_USE` und `source = MANUAL`:
  - Finde alle **direkten Kinder** (nur erste Ebene, nicht rekursiv)
  - Setze für jedes Kind, das noch keine manuelle Aktion hat:
    - `action = NOT_USE`
    - `source = INHERITED`
    - `inherited_from = <parent_field_name>`
    - `system_remark = "Automatically inherited NOT_USE from parent field <parent_field_name>"`

### 2. Wichtige Unterscheidungen:
- ✅ Nur **direkte Kinder** bearbeiten, nicht alle Nachkommen
- ✅ Nur wenn das Kind **noch keine manuelle Aktion** hat (keine Annotation)
- ✅ Nur wenn das Eltern-Feld `source = MANUAL` hat (nicht bei bereits vererbten NOT_USE)
- ✅ Vorhandene Empfehlungen (recommendations) dürfen überschrieben werden
- ❌ Vorhandene manuelle Annotationen werden NICHT überschrieben

### 3. Verwendung der FieldHierarchyNavigator
Nutze die existierende Methode `get_direct_children()` aus:
```python
from .field_hierarchy import FieldHierarchyNavigator

navigator = FieldHierarchyNavigator(mapping.fields)
direct_children = navigator.get_direct_children(parent_field_name)
```

## Beispiel:

### Input: `manual_entries.yaml`
```yaml
Patient.identifier:
  action: not_use
  remark: "Nicht benötigt in diesem Profil"
```

### Erwartetes Ergebnis:
```
Patient.identifier:
  action: NOT_USE
  source: MANUAL
  remark: "Nicht benötigt in diesem Profil"

Patient.identifier.system:
  action: NOT_USE
  source: INHERITED
  inherited_from: "Patient.identifier"
  system_remark: "Automatically inherited NOT_USE from parent field Patient.identifier"

Patient.identifier.value:
  action: NOT_USE
  source: INHERITED
  inherited_from: "Patient.identifier"
  system_remark: "Automatically inherited NOT_USE from parent field Patient.identifier"

Patient.identifier.use:
  action: NOT_USE
  source: INHERITED
  inherited_from: "Patient.identifier"
  system_remark: "Automatically inherited NOT_USE from parent field Patient.identifier"
```

### Wichtig:
Enkelkinder (z.B. `Patient.identifier.type.coding`) bekommen es **NICHT** automatisch, da sie nicht direkte Kinder sind.

## Tests zu erstellen:

**Neue Testdatei:** `/Users/Shared/dev/structure-comparer/service/tests/test_auto_inherit_not_use.py`

### Test 1: Basis-Funktionalität
```python
def test_not_use_parent_automatically_sets_not_use_on_direct_children():
    """
    Parent mit NOT_USE → alle direkten Kinder bekommen automatisch NOT_USE.
    
    Scenario:
    - Parent: Patient.identifier (NOT_USE, MANUAL)
    - Children: Patient.identifier.system, Patient.identifier.value
    
    Expected:
    - Beide Kinder haben NOT_USE mit source=INHERITED
    """
```

### Test 2: Nur direkte Kinder
```python
def test_not_use_inheritance_only_affects_direct_children():
    """
    Parent mit NOT_USE → Enkelkinder bekommen es NICHT automatisch.
    
    Scenario:
    - Parent: Patient.name (NOT_USE, MANUAL)
    - Direct children: Patient.name.family, Patient.name.given
    - Grandchildren: Patient.name.family.extension (hypothetisch)
    
    Expected:
    - Direct children haben NOT_USE (INHERITED)
    - Grandchildren haben KEIN automatisches NOT_USE
    """
```

### Test 3: Manuelle Aktionen nicht überschreiben
```python
def test_not_use_inheritance_does_not_override_manual_actions():
    """
    Kind mit eigener manueller Aktion wird NICHT überschrieben.
    
    Scenario:
    - Parent: Patient.identifier (NOT_USE, MANUAL)
    - Child 1: Patient.identifier.system (keine Annotation)
    - Child 2: Patient.identifier.value (USE, MANUAL)
    
    Expected:
    - Child 1: NOT_USE (INHERITED)
    - Child 2: USE (MANUAL) - bleibt unverändert
    """
```

### Test 4: Nur bei manueller NOT_USE Aktion
```python
def test_not_use_inheritance_only_from_manual_not_use():
    """
    Nur bei manuellem NOT_USE auf Parent, nicht bei inherited/system_default.
    
    Scenario:
    - Grandparent: Patient (NOT_USE, MANUAL)
    - Parent: Patient.identifier (NOT_USE, INHERITED from Patient)
    - Child: Patient.identifier.system
    
    Expected:
    - Patient.identifier bekommt NOT_USE von Patient
    - Patient.identifier.system bekommt KEIN automatisches NOT_USE von Patient.identifier
      (da Patient.identifier source=INHERITED hat, nicht MANUAL)
    """
```

### Test 5: Mehrere Ebenen
```python
def test_not_use_inheritance_works_at_multiple_levels():
    """
    Funktioniert mit mehreren Ebenen korrekt.
    
    Scenario:
    - Level 1: Patient.identifier (NOT_USE, MANUAL)
    - Level 2: Patient.identifier.system (gets INHERITED)
    - Level 2: Patient.identifier.value (NOT_USE, MANUAL - eigene Annotation)
    - Level 3: Patient.identifier.value.extension (should get INHERITED from Level 2)
    
    Expected:
    - Patient.identifier.system: NOT_USE (INHERITED from Patient.identifier)
    - Patient.identifier.value: NOT_USE (MANUAL)
    - Patient.identifier.value.extension: NOT_USE (INHERITED from Patient.identifier.value)
    """
```

### Test 6: System Remark korrekt gesetzt
```python
def test_not_use_inheritance_sets_correct_system_remark():
    """
    System remark enthält Hinweis auf Vererbung vom Eltern-Feld.
    
    Scenario:
    - Parent: Medication.ingredient (NOT_USE, MANUAL)
    - Child: Medication.ingredient.item
    
    Expected:
    - Child system_remark: "Automatically inherited NOT_USE from parent field Medication.ingredient"
    """
```

### Test 7: Empfehlungen dürfen überschrieben werden
```python
def test_not_use_inheritance_overrides_recommendations():
    """
    Vorhandene Empfehlungen werden überschrieben, manuelle Annotationen nicht.
    
    Scenario:
    - Parent: Patient.name (NOT_USE, MANUAL)
    - Child 1: Patient.name.family (hat USE recommendation)
    - Child 2: Patient.name.given (hat USE, MANUAL annotation)
    
    Expected:
    - Child 1: NOT_USE (INHERITED) - Empfehlung wurde überschrieben
    - Child 2: USE (MANUAL) - manuelle Annotation bleibt
    """
```

## Relevante Dateien:

### Zu modifizieren:
- `/Users/Shared/dev/structure-comparer/service/src/structure_comparer/mapping_actions_engine.py`
  - Funktion: `compute_mapping_actions()`
  - Neue Hilfsfunktion: `_propagate_not_use_to_direct_children()`

### Zu nutzen:
- `/Users/Shared/dev/structure-comparer/service/src/structure_comparer/field_hierarchy/field_navigator.py`
  - Methode: `get_direct_children(parent_field_name)`

### Neu zu erstellen:
- `/Users/Shared/dev/structure-comparer/service/tests/test_auto_inherit_not_use.py`

## Implementierungs-Hinweise:

### Pseudo-Code für die Implementierung:
```python
def _propagate_not_use_to_direct_children(
    mapping, 
    action_info_map: Dict[str, ActionInfo]
) -> None:
    """
    Automatically propagate NOT_USE action from parent to direct children.
    
    When a field has NOT_USE with source=MANUAL, all its direct children
    without manual actions receive NOT_USE with source=INHERITED.
    """
    from .field_hierarchy import FieldHierarchyNavigator
    
    navigator = FieldHierarchyNavigator(mapping.fields)
    
    # Collect all fields with manual NOT_USE
    fields_with_manual_not_use = [
        (field_name, action_info)
        for field_name, action_info in action_info_map.items()
        if action_info.action == ActionType.NOT_USE 
        and action_info.source == ActionSource.MANUAL
    ]
    
    # For each parent with manual NOT_USE
    for parent_field_name, parent_action in fields_with_manual_not_use:
        direct_children = navigator.get_direct_children(parent_field_name)
        
        for child_field_name in direct_children:
            # Check if child already has a manual action
            child_action = action_info_map.get(child_field_name)
            if child_action and child_action.source == ActionSource.MANUAL:
                # Don't override manual actions
                continue
            
            # Set NOT_USE on child
            action_info_map[child_field_name] = ActionInfo(
                action=ActionType.NOT_USE,
                source=ActionSource.INHERITED,
                inherited_from=parent_field_name,
                system_remark=f"Automatically inherited NOT_USE from parent field {parent_field_name}",
                auto_generated=True
            )
```

### Integration in `compute_mapping_actions()`:
```python
def compute_mapping_actions(mapping, manual_map: dict) -> Dict[str, ActionInfo]:
    # ... existing code to process manual entries ...
    
    # NEW: Propagate NOT_USE to direct children
    _propagate_not_use_to_direct_children(mapping, action_info_map)
    
    # ... rest of the function ...
```

## Antworten auf offene Fragen:

1. **Source:** `INHERITED` - da die Aktion vom Eltern-Feld vererbt wird
2. **System Remark:** Ja, mit folgendem Format:
   ```
   "Automatically inherited NOT_USE from parent field <parent_field_name>"
   ```
3. **Empfehlungen überschreiben:** Empfehlungen (recommendations) dürfen überschrieben werden, manuelle Annotationen (`source=MANUAL`) **NICHT**

## Akzeptanzkriterien:

✅ Wenn ein Parent-Feld `NOT_USE` mit `source=MANUAL` hat, bekommen alle direkten Kinder automatisch `NOT_USE` mit `source=INHERITED`

✅ Nur direkte Kinder werden betroffen, nicht Enkelkinder oder tiefere Ebenen

✅ Kinder mit eigenen manuellen Aktionen werden nicht überschrieben

✅ Der `system_remark` enthält einen klaren Hinweis auf die Vererbung

✅ Nur bei `source=MANUAL` am Parent, nicht bei bereits vererbten Aktionen

✅ Alle 7 Tests bestehen

✅ Bestehende Tests bleiben unverändert und bestehen weiterhin
