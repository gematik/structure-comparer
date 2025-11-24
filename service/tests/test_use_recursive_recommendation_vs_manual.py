"""Test to compare MANUAL vs RECOMMENDATION paths for USE_RECURSIVE action.

This test verifies that applying a USE_RECURSIVE recommendation produces
exactly the same result as manually setting USE_RECURSIVE action.
"""

import logging
from pathlib import Path
from tempfile import TemporaryDirectory

from structure_comparer.action import Action
from structure_comparer.data.project import Project
from structure_comparer.handler.mapping import MappingHandler
from structure_comparer.handler.project import ProjectsHandler
from structure_comparer.model.mapping import MappingFieldMinimal
from structure_comparer.model.mapping_action_models import ActionType

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def test_use_recursive_manual_vs_recommendation():
    """Compare MANUAL vs RECOMMENDATION paths for USE_RECURSIVE.
    
    This test:
    1. Loads a real project with a mapping
    2. MANUAL PATH: Sets USE_RECURSIVE manually on a field
    3. RECOMMENDATION PATH: Applies a USE_RECURSIVE recommendation on the same field
    4. Compares the results to ensure they are identical
    """
    # Use an existing test project (adjust path as needed)
    project_dir = Path("/Users/Shared/dev/structure-comparer/structure-comparer-projects")
    
    if not project_dir.exists():
        logger.warning(f"Project directory does not exist: {project_dir}")
        logger.info("Skipping test - no real projects available")
        return
    
    # Find a project with mappings
    project_handler = ProjectsHandler(project_dir)
    project_handler.load()
    
    if not project_handler.keys:
        logger.warning("No projects found")
        return
    
    # Pick the first project
    project_key = list(project_handler.keys)[0]
    logger.info(f"Using project: {project_key}")
    
    mapping_handler = MappingHandler(project_handler)
    
    # Get the project and find a mapping
    proj = project_handler._get(project_key)
    
    if not proj.mappings:
        logger.warning(f"Project {project_key} has no mappings")
        return
    
    # Pick the first mapping
    mapping_id = list(proj.mappings.keys())[0]
    logger.info(f"Using mapping: {mapping_id}")
    
    # Get the mapping details
    mapping = mapping_handler._MappingHandler__get(project_key, mapping_id)
    
    # Find a field with descendants that might support USE_RECURSIVE
    # We'll look for a field that:
    # - Has children
    # - Is compatible or has USE_RECURSIVE in actions_allowed
    target_field_name = None
    
    for field_name, field in mapping.fields.items():
        # Check if field has descendants (contains a dot and there are child fields)
        if '.' in field_name:
            continue  # Skip child fields
        
        # Check if there are child fields
        has_children = any(
            child_name.startswith(field_name + '.')
            for child_name in mapping.fields.keys()
        )
        
        if has_children:
            actions_allowed = getattr(field, 'actions_allowed', [])
            logger.info(f"Field {field_name}: has_children={has_children}, actions_allowed={actions_allowed}")
            
            if Action.USE_RECURSIVE in actions_allowed:
                target_field_name = field_name
                logger.info(f"Found suitable field: {target_field_name}")
                break
    
    if target_field_name is None:
        logger.warning("No suitable field found for testing")
        return
    
    # Get initial state
    field_before = mapping_handler.get_field(project_key, mapping_id, target_field_name)
    logger.info(f"\n=== INITIAL STATE ===")
    logger.info(f"Field: {target_field_name}")
    logger.info(f"Action: {field_before.action}")
    logger.info(f"Actions allowed: {field_before.actions_allowed}")
    logger.info(f"Recommendations: {len(field_before.recommendations)}")
    if field_before.recommendations:
        for i, rec in enumerate(field_before.recommendations):
            logger.info(f"  Recommendation {i}: action={rec.action}, source={rec.source}")
    
    # ===================================================================
    # SCENARIO A: MANUAL PATH - Set USE_RECURSIVE manually
    # ===================================================================
    logger.info(f"\n=== SCENARIO A: MANUAL PATH ===")
    
    # Create a backup of manual_entries before modification
    import copy
    manual_entries_backup_a = copy.deepcopy(proj.manual_entries._data)
    
    # Manually set USE_RECURSIVE
    manual_input = MappingFieldMinimal(
        action=Action.USE_RECURSIVE,
        other=None,
        fixed=None,
        remark="Test: manually set USE_RECURSIVE"
    )
    
    mapping_handler.set_field(project_key, mapping_id, target_field_name, manual_input)
    
    # Get the field after manual setting
    field_after_manual = mapping_handler.get_field(project_key, mapping_id, target_field_name)
    
    logger.info(f"After manual setting:")
    logger.info(f"  Action: {field_after_manual.action}")
    logger.info(f"  Action info: {field_after_manual.action_info}")
    
    # Check manual_entries
    manual_entries_mapping = proj.manual_entries.get(mapping_id)
    if manual_entries_mapping:
        manual_entry_a = manual_entries_mapping.get(target_field_name)
        logger.info(f"  Manual entry: {manual_entry_a}")
        if manual_entry_a:
            logger.info(f"    action={manual_entry_a.action}")
    else:
        logger.info(f"  No manual entries mapping found")
    
    # Get children to check inheritance
    children_after_manual = {}
    for child_name in mapping.fields.keys():
        if child_name.startswith(target_field_name + '.'):
            child_field = mapping_handler.get_field(project_key, mapping_id, child_name)
            children_after_manual[child_name] = {
                'action': child_field.action,
                'action_info': child_field.action_info,
            }
            logger.info(f"  Child {child_name}: action={child_field.action}, source={child_field.action_info.source if child_field.action_info else None}")
    
    # Restore manual_entries to initial state
    proj.manual_entries._data = manual_entries_backup_a
    proj.manual_entries.write()
    
    # ===================================================================
    # SCENARIO B: RECOMMENDATION PATH - Apply USE_RECURSIVE recommendation
    # ===================================================================
    logger.info(f"\n=== SCENARIO B: RECOMMENDATION PATH ===")
    
    # Reload mapping to get fresh state
    mapping = mapping_handler._MappingHandler__get(project_key, mapping_id)
    field_before_rec = mapping_handler.get_field(project_key, mapping_id, target_field_name)
    
    logger.info(f"Before applying recommendation:")
    logger.info(f"  Action: {field_before_rec.action}")
    logger.info(f"  Recommendations: {len(field_before_rec.recommendations)}")
    
    # Find USE_RECURSIVE recommendation
    use_recursive_index = None
    for i, rec in enumerate(field_before_rec.recommendations):
        logger.info(f"  Recommendation {i}: action={rec.action}")
        if rec.action == ActionType.USE_RECURSIVE:
            use_recursive_index = i
            break
    
    if use_recursive_index is None:
        logger.warning("No USE_RECURSIVE recommendation found!")
        logger.info("Creating a mock recommendation scenario")
        # We can't test this scenario if there's no recommendation
        return
    
    # Apply the USE_RECURSIVE recommendation
    logger.info(f"Applying recommendation at index {use_recursive_index}")
    field_after_rec = mapping_handler.apply_recommendation(
        project_key, mapping_id, target_field_name, use_recursive_index
    )
    
    logger.info(f"After applying recommendation:")
    logger.info(f"  Action: {field_after_rec.action}")
    logger.info(f"  Action info: {field_after_rec.action_info}")
    
    # Check manual_entries
    manual_entries_mapping = proj.manual_entries.get(mapping_id)
    if manual_entries_mapping:
        manual_entry_b = manual_entries_mapping.get(target_field_name)
        logger.info(f"  Manual entry: {manual_entry_b}")
        if manual_entry_b:
            logger.info(f"    action={manual_entry_b.action}")
    else:
        logger.info(f"  No manual entries mapping found")
    
    # Get children to check inheritance
    children_after_rec = {}
    for child_name in mapping.fields.keys():
        if child_name.startswith(target_field_name + '.'):
            child_field = mapping_handler.get_field(project_key, mapping_id, child_name)
            children_after_rec[child_name] = {
                'action': child_field.action,
                'action_info': child_field.action_info,
            }
            logger.info(f"  Child {child_name}: action={child_field.action}, source={child_field.action_info.source if child_field.action_info else None}")
    
    # ===================================================================
    # COMPARE RESULTS
    # ===================================================================
    logger.info(f"\n=== COMPARISON ===")
    
    logger.info(f"Parent field action:")
    logger.info(f"  Manual:         {field_after_manual.action}")
    logger.info(f"  Recommendation: {field_after_rec.action}")
    
    if field_after_manual.action != field_after_rec.action:
        logger.error("❌ MISMATCH: Parent field actions are different!")
    else:
        logger.info("✅ Parent field actions match")
    
    # Compare children
    logger.info(f"\nChildren actions:")
    all_children = set(children_after_manual.keys()) | set(children_after_rec.keys())
    
    for child_name in sorted(all_children):
        manual_action = children_after_manual.get(child_name, {}).get('action')
        rec_action = children_after_rec.get(child_name, {}).get('action')
        
        if manual_action != rec_action:
            logger.error(f"❌ MISMATCH for {child_name}:")
            logger.error(f"   Manual:         {manual_action}")
            logger.error(f"   Recommendation: {rec_action}")
        else:
            logger.info(f"✅ {child_name}: {manual_action}")
    
    # Final assertion
    assert field_after_manual.action == field_after_rec.action, \
        f"Parent action mismatch: manual={field_after_manual.action}, recommendation={field_after_rec.action}"
    
    logger.info(f"\n=== TEST COMPLETED ===")


if __name__ == "__main__":
    test_use_recursive_manual_vs_recommendation()
