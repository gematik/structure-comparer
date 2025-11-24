"""Navigation and analysis of field hierarchies."""

from typing import Dict, List, Optional
from .field_utils import field_depth, parent_name, get_direct_children


class FieldHierarchyNavigator:
    """Provides navigation and analysis capabilities for field hierarchies."""
    
    def __init__(self, fields: Dict[str, any]):
        """
        Args:
            fields: Dictionary mapping field names to field objects
        """
        self.fields = fields
        self._depth_cache: Optional[Dict[str, int]] = None
        self._children_cache: Dict[str, List[str]] = {}
    
    def get_direct_children(self, parent_field_name: str) -> List[str]:
        """
        Get all direct child field names of a parent field (cached).
        
        Args:
            parent_field_name: The parent field name
            
        Returns:
            List of direct child field names
        """
        if parent_field_name not in self._children_cache:
            self._children_cache[parent_field_name] = get_direct_children(
                parent_field_name, 
                self.fields
            )
        
        return self._children_cache[parent_field_name]
    
    def get_all_descendants(self, parent_field_name: str) -> List[str]:
        """
        Get all descendant field names recursively.
        
        Args:
            parent_field_name: The parent field name
            
        Returns:
            List of all descendant field names (children, grandchildren, etc.)
        """
        descendants = []
        
        def collect_descendants(field_name: str):
            children = self.get_direct_children(field_name)
            for child in children:
                descendants.append(child)
                collect_descendants(child)
        
        collect_descendants(parent_field_name)
        return descendants
    
    def get_parent_chain(self, field_name: str) -> List[str]:
        """
        Get all parent field names from root to immediate parent.
        
        Args:
            field_name: The field name
            
        Returns:
            List of parent field names, ordered from root to immediate parent
        """
        parents = []
        current = field_name
        
        while True:
            parent = parent_name(current)
            if parent is None:
                break
            parents.insert(0, parent)  # Insert at beginning for root-to-leaf order
            current = parent
        
        return parents
    
    def get_fields_by_depth(self, reverse: bool = False) -> List[str]:
        """
        Get all field names sorted by depth.
        
        Args:
            reverse: If True, return deepest fields first (for bottom-up processing)
            
        Returns:
            List of field names sorted by depth
        """
        if self._depth_cache is None:
            self._depth_cache = {
                name: field_depth(name) 
                for name in self.fields.keys()
            }
        
        sorted_fields = sorted(
            self._depth_cache.keys(),
            key=lambda name: self._depth_cache[name],
            reverse=reverse
        )
        
        return sorted_fields
    
    def get_root_fields(self) -> List[str]:
        """Get all root-level fields (depth 0)."""
        return [name for name in self.fields.keys() if field_depth(name) == 0]
    
    def is_ancestor_of(self, potential_ancestor: str, field_name: str) -> bool:
        """
        Check if potential_ancestor is an ancestor of field_name.
        
        Args:
            potential_ancestor: Field name that might be an ancestor
            field_name: Field name to check
            
        Returns:
            True if potential_ancestor is an ancestor of field_name
        """
        return potential_ancestor in self.get_parent_chain(field_name)
