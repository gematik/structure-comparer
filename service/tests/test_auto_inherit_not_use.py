"""Tests for automatic NOT_USE inheritance from parent to direct children.

When a parent field has NOT_USE with source=MANUAL, all direct children
without manual actions should automatically receive NOT_USE with source=INHERITED.
"""

from __future__ import annotations

from structure_comparer.mapping_actions_engine import compute_mapping_actions
from structure_comparer.model.mapping_action_models import (
    ActionSource,
    ActionType,
)


class MockField:
    """Mock field object for testing."""

    def __init__(self, name: str, classification: str = "unknown"):
        self.name = name
        self.classification = classification
        self.profiles = {}
        self.actions_allowed = []


class MockMapping:
    """Mock mapping object for testing."""

    def __init__(self, fields: dict):
        self.fields = fields
        self.target = None


def test_not_use_parent_automatically_sets_not_use_on_direct_children():
    """
    Parent mit NOT_USE → alle direkten Kinder bekommen automatisch NOT_USE.

    Scenario:
    - Parent: Patient.identifier (NOT_USE, MANUAL)
    - Children: Patient.identifier.system, Patient.identifier.value

    Expected:
    - Beide Kinder haben NOT_USE mit source=INHERITED
    """
    fields = {
        "Patient.identifier": MockField("Patient.identifier"),
        "Patient.identifier.system": MockField("Patient.identifier.system"),
        "Patient.identifier.value": MockField("Patient.identifier.value"),
    }

    mapping = MockMapping(fields)

    manual_entries = {"Patient.identifier": {"action": "not_use", "remark": "Not needed"}}

    result = compute_mapping_actions(mapping, manual_entries)

    # Parent should have NOT_USE with MANUAL source
    assert result["Patient.identifier"].action == ActionType.NOT_USE
    assert result["Patient.identifier"].source == ActionSource.MANUAL

    # Direct children should have NOT_USE with INHERITED source
    assert result["Patient.identifier.system"].action == ActionType.NOT_USE
    assert result["Patient.identifier.system"].source == ActionSource.INHERITED
    assert result["Patient.identifier.system"].inherited_from == "Patient.identifier"
    assert (
        "Automatically inherited NOT_USE from parent field Patient.identifier"
        in result["Patient.identifier.system"].system_remark
    )

    assert result["Patient.identifier.value"].action == ActionType.NOT_USE
    assert result["Patient.identifier.value"].source == ActionSource.INHERITED
    assert result["Patient.identifier.value"].inherited_from == "Patient.identifier"
    assert (
        "Automatically inherited NOT_USE from parent field Patient.identifier"
        in result["Patient.identifier.value"].system_remark
    )


def test_not_use_inheritance_only_affects_direct_children():
    """
    Parent mit NOT_USE → Enkelkinder bekommen es NICHT automatisch.

    Scenario:
    - Parent: Patient.name (NOT_USE, MANUAL)
    - Direct children: Patient.name.family, Patient.name.given
    - Grandchildren: Patient.name.family.extension

    Expected:
    - Direct children haben NOT_USE (INHERITED)
    - Grandchildren haben KEIN automatisches NOT_USE von Patient.name
      (weil Patient.name.family nur INHERITED hat, nicht MANUAL)
    """
    fields = {
        "Patient.name": MockField("Patient.name"),
        "Patient.name.family": MockField("Patient.name.family"),
        "Patient.name.given": MockField("Patient.name.given"),
        "Patient.name.family.extension": MockField("Patient.name.family.extension"),
    }

    mapping = MockMapping(fields)

    manual_entries = {"Patient.name": {"action": "not_use", "remark": "Not needed"}}

    result = compute_mapping_actions(mapping, manual_entries)

    # Parent should have NOT_USE with MANUAL source
    assert result["Patient.name"].action == ActionType.NOT_USE
    assert result["Patient.name"].source == ActionSource.MANUAL

    # Direct children should have NOT_USE with INHERITED source
    assert result["Patient.name.family"].action == ActionType.NOT_USE
    assert result["Patient.name.family"].source == ActionSource.INHERITED

    assert result["Patient.name.given"].action == ActionType.NOT_USE
    assert result["Patient.name.given"].source == ActionSource.INHERITED

    # Grandchild should NOT have automatic NOT_USE from grandparent
    # because Patient.name.family has source=INHERITED, not MANUAL
    assert result["Patient.name.family.extension"].action is None
    assert result["Patient.name.family.extension"].source == ActionSource.SYSTEM_DEFAULT


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
    fields = {
        "Patient.identifier": MockField("Patient.identifier"),
        "Patient.identifier.system": MockField("Patient.identifier.system"),
        "Patient.identifier.value": MockField("Patient.identifier.value", "compatible"),
    }

    mapping = MockMapping(fields)

    manual_entries = {
        "Patient.identifier": {"action": "not_use", "remark": "Not needed"},
        "Patient.identifier.value": {"action": "use", "remark": "Keep this one"},
    }

    result = compute_mapping_actions(mapping, manual_entries)

    # Parent should have NOT_USE
    assert result["Patient.identifier"].action == ActionType.NOT_USE
    assert result["Patient.identifier"].source == ActionSource.MANUAL

    # Child 1 should have inherited NOT_USE
    assert result["Patient.identifier.system"].action == ActionType.NOT_USE
    assert result["Patient.identifier.system"].source == ActionSource.INHERITED

    # Child 2 should keep its manual USE action
    assert result["Patient.identifier.value"].action == ActionType.USE
    assert result["Patient.identifier.value"].source == ActionSource.MANUAL


def test_not_use_inheritance_only_from_manual_not_use():
    """
    Nur bei manuellem NOT_USE auf Parent, nicht bei inherited/system_default.

    Scenario:
    - Grandparent: Patient (NOT_USE, MANUAL)
    - Parent: Patient.identifier (gets NOT_USE, INHERITED from Patient)
    - Child: Patient.identifier.system

    Expected:
    - Patient.identifier bekommt NOT_USE von Patient (automatisch vererbt)
    - Patient.identifier.system bekommt KEIN automatisches NOT_USE von Patient.identifier
      (da Patient.identifier source=INHERITED hat, nicht MANUAL)
    """
    fields = {
        "Patient": MockField("Patient"),
        "Patient.identifier": MockField("Patient.identifier"),
        "Patient.identifier.system": MockField("Patient.identifier.system"),
    }

    mapping = MockMapping(fields)

    manual_entries = {"Patient": {"action": "not_use", "remark": "Not needed"}}

    result = compute_mapping_actions(mapping, manual_entries)

    # Grandparent should have NOT_USE with MANUAL source
    assert result["Patient"].action == ActionType.NOT_USE
    assert result["Patient"].source == ActionSource.MANUAL

    # Parent should have inherited NOT_USE from grandparent
    assert result["Patient.identifier"].action == ActionType.NOT_USE
    assert result["Patient.identifier"].source == ActionSource.INHERITED
    assert result["Patient.identifier"].inherited_from == "Patient"

    # Child should NOT have inherited NOT_USE because parent has source=INHERITED
    assert result["Patient.identifier.system"].action is None
    assert result["Patient.identifier.system"].source == ActionSource.SYSTEM_DEFAULT


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
    fields = {
        "Patient.identifier": MockField("Patient.identifier"),
        "Patient.identifier.system": MockField("Patient.identifier.system"),
        "Patient.identifier.value": MockField("Patient.identifier.value"),
        "Patient.identifier.value.extension": MockField("Patient.identifier.value.extension"),
    }

    mapping = MockMapping(fields)

    manual_entries = {
        "Patient.identifier": {"action": "not_use", "remark": "Not needed"},
        "Patient.identifier.value": {"action": "not_use", "remark": "Also not needed"},
    }

    result = compute_mapping_actions(mapping, manual_entries)

    # Level 1: Parent
    assert result["Patient.identifier"].action == ActionType.NOT_USE
    assert result["Patient.identifier"].source == ActionSource.MANUAL

    # Level 2: First child (inherited)
    assert result["Patient.identifier.system"].action == ActionType.NOT_USE
    assert result["Patient.identifier.system"].source == ActionSource.INHERITED
    assert result["Patient.identifier.system"].inherited_from == "Patient.identifier"

    # Level 2: Second child (manual)
    assert result["Patient.identifier.value"].action == ActionType.NOT_USE
    assert result["Patient.identifier.value"].source == ActionSource.MANUAL

    # Level 3: Grandchild (inherited from manual parent at level 2)
    assert result["Patient.identifier.value.extension"].action == ActionType.NOT_USE
    assert result["Patient.identifier.value.extension"].source == ActionSource.INHERITED
    assert result["Patient.identifier.value.extension"].inherited_from == "Patient.identifier.value"


def test_not_use_inheritance_sets_correct_system_remark():
    """
    System remark enthält Hinweis auf Vererbung vom Eltern-Feld.

    Scenario:
    - Parent: Medication.ingredient (NOT_USE, MANUAL)
    - Child: Medication.ingredient.item

    Expected:
    - Child system_remark: "Automatically inherited NOT_USE from parent field Medication.ingredient"
    """
    fields = {
        "Medication.ingredient": MockField("Medication.ingredient"),
        "Medication.ingredient.item": MockField("Medication.ingredient.item"),
    }

    mapping = MockMapping(fields)

    manual_entries = {"Medication.ingredient": {"action": "not_use", "remark": "Not needed"}}

    result = compute_mapping_actions(mapping, manual_entries)

    # Parent should have NOT_USE
    assert result["Medication.ingredient"].action == ActionType.NOT_USE
    assert result["Medication.ingredient"].source == ActionSource.MANUAL

    # Child should have correct system remark
    assert result["Medication.ingredient.item"].action == ActionType.NOT_USE
    assert result["Medication.ingredient.item"].source == ActionSource.INHERITED
    assert (
        result["Medication.ingredient.item"].system_remark
        == "Automatically inherited NOT_USE from parent field Medication.ingredient"
    )


def test_not_use_inheritance_overrides_system_defaults():
    """
    Vorhandene System-Defaults werden überschrieben, manuelle Annotationen nicht.

    Scenario:
    - Parent: Patient.name (NOT_USE, MANUAL)
    - Child 1: Patient.name.family (hat keine Aktion, würde system_default bekommen)
    - Child 2: Patient.name.given (hat USE, MANUAL annotation)

    Expected:
    - Child 1: NOT_USE (INHERITED) - System-Default wurde überschrieben
    - Child 2: USE (MANUAL) - manuelle Annotation bleibt
    """
    fields = {
        "Patient.name": MockField("Patient.name"),
        "Patient.name.family": MockField("Patient.name.family", "compatible"),
        "Patient.name.given": MockField("Patient.name.given", "compatible"),
    }

    mapping = MockMapping(fields)

    manual_entries = {
        "Patient.name": {"action": "not_use", "remark": "Not needed"},
        "Patient.name.given": {"action": "use", "remark": "Keep this"},
    }

    result = compute_mapping_actions(mapping, manual_entries)

    # Parent should have NOT_USE
    assert result["Patient.name"].action == ActionType.NOT_USE
    assert result["Patient.name"].source == ActionSource.MANUAL

    # Child 1 should have inherited NOT_USE (overriding system default)
    assert result["Patient.name.family"].action == ActionType.NOT_USE
    assert result["Patient.name.family"].source == ActionSource.INHERITED

    # Child 2 should keep its manual USE action
    assert result["Patient.name.given"].action == ActionType.USE
    assert result["Patient.name.given"].source == ActionSource.MANUAL
