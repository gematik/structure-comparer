"""Debug test to check what gets written to manual_entries when applying USE_RECURSIVE."""

import logging
from pathlib import Path

from structure_comparer.action import Action
from structure_comparer.handler.mapping import MappingHandler
from structure_comparer.handler.project import ProjectsHandler
from structure_comparer.model.mapping import MappingFieldMinimal
from structure_comparer.model.mapping_action_models import ActionInfo, ActionSource, ActionType

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def test_debug_recommendation_action_storage():
    """Debug test to see what action value is stored in manual_entries.
    
    This test directly simulates what happens when:
    1. A USE_RECURSIVE recommendation is created
    2. It is converted to a manual action in apply_recommendation
    3. The action is stored in manual_entries
    """
    
    logger.info("\n=== TESTING ACTION CONVERSION ===")
    
    # Create a mock recommendation with USE_RECURSIVE
    recommendation = ActionInfo(
        action=ActionType.USE_RECURSIVE,
        source=ActionSource.SYSTEM_DEFAULT,
        auto_generated=True,
        system_remark="Test recommendation"
    )
    
    logger.info(f"Recommendation created:")
    logger.info(f"  recommendation.action = {recommendation.action}")
    logger.info(f"  type(recommendation.action) = {type(recommendation.action)}")
    logger.info(f"  recommendation.action.value = {recommendation.action.value}")
    
    # This is what apply_recommendation does:
    logger.info(f"\n=== CONVERSION IN apply_recommendation ===")
    
    converted_action = Action(recommendation.action.value) if recommendation.action else None
    
    logger.info(f"Converted action:")
    logger.info(f"  converted_action = {converted_action}")
    logger.info(f"  type(converted_action) = {type(converted_action)}")
    logger.info(f"  converted_action == Action.USE_RECURSIVE: {converted_action == Action.USE_RECURSIVE}")
    
    # Compare with manual setting
    logger.info(f"\n=== COMPARISON WITH MANUAL SETTING ===")
    
    manual_action = Action.USE_RECURSIVE
    
    logger.info(f"Manual action:")
    logger.info(f"  manual_action = {manual_action}")
    logger.info(f"  type(manual_action) = {type(manual_action)}")
    
    logger.info(f"\nAre they equal?")
    logger.info(f"  converted_action == manual_action: {converted_action == manual_action}")
    logger.info(f"  str(converted_action) == str(manual_action): {str(converted_action) == str(manual_action)}")
    
    # Check string representation (what gets written to YAML)
    logger.info(f"\n=== STRING REPRESENTATION (YAML) ===")
    logger.info(f"  str(converted_action) = '{str(converted_action)}'")
    logger.info(f"  str(manual_action) = '{str(manual_action)}'")
    logger.info(f"  converted_action.value = '{converted_action.value}'")
    logger.info(f"  manual_action.value = '{manual_action.value}'")
    
    # Test with MappingFieldBase
    from structure_comparer.model.mapping import MappingFieldBase
    
    logger.info(f"\n=== TESTING WITH MappingFieldBase ===")
    
    # Recommendation path
    entry_from_recommendation = MappingFieldBase(
        name="test.field",
        action=Action(recommendation.action.value) if recommendation.action else None,
    )
    
    # Manual path
    entry_from_manual = MappingFieldBase(
        name="test.field",
        action=Action.USE_RECURSIVE,
    )
    
    logger.info(f"Entry from recommendation:")
    logger.info(f"  action = {entry_from_recommendation.action}")
    logger.info(f"  type = {type(entry_from_recommendation.action)}")
    
    logger.info(f"Entry from manual:")
    logger.info(f"  action = {entry_from_manual.action}")
    logger.info(f"  type = {type(entry_from_manual.action)}")
    
    logger.info(f"\nAre they equal?")
    logger.info(f"  entry_from_recommendation.action == entry_from_manual.action: {entry_from_recommendation.action == entry_from_manual.action}")
    
    # Serialize to dict (like what happens before writing to YAML)
    logger.info(f"\n=== SERIALIZATION TO DICT ===")
    
    rec_dict = entry_from_recommendation.model_dump()
    manual_dict = entry_from_manual.model_dump()
    
    logger.info(f"Recommendation dict: {rec_dict}")
    logger.info(f"Manual dict: {manual_dict}")
    
    logger.info(f"\nDicts equal? {rec_dict == manual_dict}")
    
    assert converted_action == manual_action, "Actions should be equal!"
    assert entry_from_recommendation.action == entry_from_manual.action, "Model actions should be equal!"
    
    logger.info(f"\n✅ All assertions passed - conversion is correct!")


if __name__ == "__main__":
    test_debug_recommendation_action_storage()
