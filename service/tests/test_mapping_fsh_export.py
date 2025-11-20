"""Tests for FSH export functionality."""
from __future__ import annotations

from unittest.mock import Mock
from collections import OrderedDict


from service.src.structure_comparer.fshMappingGenerator.fsh_mapping_main import build_structuremap
from service.src.structure_comparer.model.mapping_action_models import (
    ActionInfo,
    ActionSource,
    ActionType,
)


def test_build_structuremap_fsh_single_field():
    """Test FSH generation with a single USE action field."""
    # Create a mock mapping
    mapping = Mock()
    mapping.name = "TestMapping"
    mapping.id = "test-mapping-id"
    
    # Create a mock field
    mock_field = Mock()
    mock_field.name = "MedicationDispense.medication"
    
    mapping.fields = OrderedDict()
    mapping.fields["MedicationDispense.medication"] = mock_field
    
    # Create actions with a single USE action
    actions = {
        "MedicationDispense.medication": ActionInfo(
            action=ActionType.USE,
            source=ActionSource.SYSTEM_DEFAULT,
            system_remark="Default action applied",
        )
    }
    
    # Generate FSH
    result = build_structuremap(
        mapping=mapping,
        actions=actions,
        source_alias="sourceDispense",
        target_alias="targetDispense",
        ruleset_name="test-mapping-ruleset",
    )
    
    # Verify structure
    assert "RuleSet: test-mapping-ruleset" in result
    assert "Auto-generated from structure-comparer mapping" in result
    assert "TestMapping" in result
    assert "* group[+]" in result
    assert '* name = "TestMapping"' in result
    assert "* typeMode = #none" in result
    assert "* insert sd_input(sourceDispense, source)" in result
    assert "* insert sd_input(targetDispense, target)" in result
    
    # Verify rule
    assert "* rule[+]" in result
    assert '* source.context = "sourceDispense"' in result
    assert '* source.element = "medication"' in result
    assert "* insert targetCopyVariable(targetDispense, medication)" in result
    assert "* documentation = " in result


def test_build_structuremap_fsh_multiple_fields():
    """Test FSH generation with multiple USE action fields."""
    # Create a mock mapping
    mapping = Mock()
    mapping.name = "MultiFieldMapping"
    mapping.id = "multi-field-id"
    
    # Create mock fields
    field1 = Mock()
    field1.name = "MedicationDispense.medication"
    field2 = Mock()
    field2.name = "MedicationDispense.status"
    field3 = Mock()
    field3.name = "MedicationDispense.subject"
    
    mapping.fields = OrderedDict()
    mapping.fields["MedicationDispense.medication"] = field1
    mapping.fields["MedicationDispense.status"] = field2
    mapping.fields["MedicationDispense.subject"] = field3
    
    # Create actions
    actions = {
        "MedicationDispense.medication": ActionInfo(
            action=ActionType.USE,
            source=ActionSource.MANUAL,
        ),
        "MedicationDispense.status": ActionInfo(
            action=ActionType.USE,
            source=ActionSource.SYSTEM_DEFAULT,
        ),
        "MedicationDispense.subject": ActionInfo(
            action=ActionType.USE,
            source=ActionSource.MANUAL,
            user_remark="Map patient reference",
        ),
    }
    
    # Generate FSH
    result = build_structuremap(
        mapping=mapping,
        actions=actions,
        source_alias="src",
        target_alias="tgt",
        ruleset_name="multi-field-test",
    )
    
    # Should have 3 rules
    assert result.count("* rule[+]") == 3
    assert "medication" in result
    assert "status" in result
    assert "subject" in result
    assert "Map patient reference" in result


def test_build_structuremap_fsh_non_use_actions():
    """Test that non-USE actions generate TODO comments."""
    # Create a mock mapping
    mapping = Mock()
    mapping.name = "NonUseMapping"
    mapping.id = "non-use-id"
    
    # Create mock fields
    field1 = Mock()
    field1.name = "MedicationDispense.medication"
    field2 = Mock()
    field2.name = "MedicationDispense.extension"
    
    mapping.fields = OrderedDict()
    mapping.fields["MedicationDispense.medication"] = field1
    mapping.fields["MedicationDispense.extension"] = field2
    
    # Create actions with different types
    actions = {
        "MedicationDispense.medication": ActionInfo(
            action=ActionType.USE,
            source=ActionSource.MANUAL,
        ),
        "MedicationDispense.extension": ActionInfo(
            action=ActionType.EXTENSION,
            source=ActionSource.MANUAL,
        ),
    }
    
    # Generate FSH
    result = build_structuremap(
        mapping=mapping,
        actions=actions,
        source_alias="src",
        target_alias="tgt",
        ruleset_name="non-use-test",
    )
    
    # Should have 1 rule for USE action
    assert result.count("* rule[+]") == 1
    # Should have TODO comment for EXTENSION action
    assert "TODO: Handle extension action" in result
    assert "MedicationDispense.extension" in result


def test_build_structuremap_fsh_inherited_action():
    """Test that inherited actions are not included in FSH export."""
    # Create a mock mapping
    mapping = Mock()
    mapping.name = "InheritedMapping"
    mapping.id = "inherited-id"
    
    # Create mock fields
    field1 = Mock()
    field1.name = "MedicationDispense.medication"
    field2 = Mock()
    field2.name = "MedicationDispense.status"
    
    mapping.fields = OrderedDict()
    mapping.fields["MedicationDispense.medication"] = field1
    mapping.fields["MedicationDispense.status"] = field2
    
    # Create actions
    actions = {
        "MedicationDispense.medication": ActionInfo(
            action=ActionType.USE,
            source=ActionSource.MANUAL,
        ),
        "MedicationDispense.status": ActionInfo(
            action=ActionType.USE,
            source=ActionSource.INHERITED,  # Inherited, should be skipped
            inherited_from="MedicationDispense",
        ),
    }
    
    # Generate FSH
    result = build_structuremap(
        mapping=mapping,
        actions=actions,
        source_alias="src",
        target_alias="tgt",
        ruleset_name="inherited-test",
    )
    
    # Should only have 1 rule (for MANUAL action)
    assert result.count("* rule[+]") == 1
    assert "medication" in result
    # Status should not generate a rule (it's inherited)
    # Count how many times 'status' appears - should only be in potential TODO or not at all
    # Since inherited USE actions aren't TODO-worthy, status shouldn't appear in rules
    assert result.count('source.element = "status"') == 0


def test_build_structuremap_fsh_nested_field():
    """Test FSH generation with nested field paths."""
    # Create a mock mapping
    mapping = Mock()
    mapping.name = "NestedMapping"
    mapping.id = "nested-id"
    
    # Create mock field with nested path
    field1 = Mock()
    field1.name = "MedicationDispense.medication.reference"
    
    mapping.fields = OrderedDict()
    mapping.fields["MedicationDispense.medication.reference"] = field1
    
    # Create action
    actions = {
        "MedicationDispense.medication.reference": ActionInfo(
            action=ActionType.USE,
            source=ActionSource.MANUAL,
        ),
    }
    
    # Generate FSH
    result = build_structuremap(
        mapping=mapping,
        actions=actions,
        source_alias="src",
        target_alias="tgt",
        ruleset_name="nested-test",
    )
    
    # Should extract "medication.reference" as element name
    assert '* source.element = "medication.reference"' in result
    assert "* insert targetCopyVariable(tgt, medication.reference)" in result


def test_build_structuremap_fsh_special_characters_in_name():
    """Test FSH generation handles special characters in mapping name."""
    # Create a mock mapping with special characters
    mapping = Mock()
    mapping.name = "Test-Mapping_v1.2.3 (beta)"
    mapping.id = "special-id"
    
    mapping.fields = OrderedDict()
    
    # Create action (empty for this test)
    actions = {}
    
    # Generate FSH
    result = build_structuremap(
        mapping=mapping,
        actions=actions,
        source_alias="src",
        target_alias="tgt",
        ruleset_name="special-chars-test",
    )
    
    # Should sanitize the name properly
    assert "RuleSet: special-chars-test" in result
    # Group name should be sanitized but readable
    assert '* name = "Test-Mapping_v123 beta"' in result


def test_build_structuremap_fsh_user_remark():
    """Test that user remarks are included in documentation."""
    # Create a mock mapping
    mapping = Mock()
    mapping.name = "RemarkMapping"
    mapping.id = "remark-id"
    
    # Create mock field
    field1 = Mock()
    field1.name = "MedicationDispense.medication"
    
    mapping.fields = OrderedDict()
    mapping.fields["MedicationDispense.medication"] = field1
    
    # Create action with user remark
    actions = {
        "MedicationDispense.medication": ActionInfo(
            action=ActionType.USE,
            source=ActionSource.MANUAL,
            user_remark="Custom mapping instruction",
        ),
    }
    
    # Generate FSH
    result = build_structuremap(
        mapping=mapping,
        actions=actions,
        source_alias="src",
        target_alias="tgt",
        ruleset_name="remark-test",
    )
    
    # Should include user remark in documentation
    assert "Custom mapping instruction" in result
    assert '* documentation = "Custom mapping instruction"' in result


def test_build_structuremap_fsh_empty_mapping():
    """Test FSH generation with no fields."""
    # Create a mock mapping with no fields
    mapping = Mock()
    mapping.name = "EmptyMapping"
    mapping.id = "empty-id"
    mapping.fields = OrderedDict()
    
    # No actions
    actions = {}
    
    # Generate FSH
    result = build_structuremap(
        mapping=mapping,
        actions=actions,
        source_alias="src",
        target_alias="tgt",
        ruleset_name="empty-test",
    )
    
    # Should still have header structure
    assert "RuleSet: empty-test" in result
    assert "* group[+]" in result
    assert "* insert sd_input(src, source)" in result
    assert "* insert sd_input(tgt, target)" in result
    # Should not have any rules
    assert result.count("* rule[+]") == 0
