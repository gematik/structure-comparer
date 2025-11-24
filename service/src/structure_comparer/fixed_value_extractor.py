"""Fixed value extraction from FHIR ElementDefinition objects.

This module provides utilities to extract fixed and pattern values from
FHIR StructureDefinition elements. It handles all common fixed value types
used in FHIR profiles.
"""

from typing import Any, Optional
from fhir.resources.R4B.elementdefinition import ElementDefinition


class FixedValueExtractor:
    """Extracts fixed and pattern values from FHIR ElementDefinition.
    
    Supports the following fixed value types:
    - fixedUri
    - fixedUrl
    - fixedCanonical
    - fixedString
    - fixedCode
    - fixedOid
    - fixedId
    - fixedUuid
    - fixedInteger
    - fixedDecimal
    - fixedBoolean
    - fixedDate
    - fixedDateTime
    - fixedTime
    - fixedInstant
    
    Also supports pattern values:
    - patternCoding (extracts system)
    """
    
    # List of fixed value attribute names in order of priority
    FIXED_VALUE_ATTRS = [
        'fixedUri',
        'fixedUrl',
        'fixedCanonical',
        'fixedString',
        'fixedCode',
        'fixedOid',
        'fixedId',
        'fixedUuid',
        'fixedInteger',
        'fixedDecimal',
        'fixedBoolean',
        'fixedDate',
        'fixedDateTime',
        'fixedTime',
        'fixedInstant',
    ]
    
    @classmethod
    def extract_fixed_value(cls, element: ElementDefinition) -> Optional[Any]:
        """Extract any fixed value from an ElementDefinition.
        
        Args:
            element: The FHIR ElementDefinition to extract from
            
        Returns:
            The fixed value if found, None otherwise
        """
        if element is None:
            return None
            
        for attr_name in cls.FIXED_VALUE_ATTRS:
            value = getattr(element, attr_name, None)
            if value is not None:
                return value
                
        return None
    
    @classmethod
    def get_fixed_value_type(cls, element: ElementDefinition) -> Optional[str]:
        """Get the type of fixed value present in an ElementDefinition.
        
        Args:
            element: The FHIR ElementDefinition to check
            
        Returns:
            The attribute name (e.g., 'fixedUri', 'fixedString') if found, None otherwise
        """
        if element is None:
            return None
            
        for attr_name in cls.FIXED_VALUE_ATTRS:
            value = getattr(element, attr_name, None)
            if value is not None:
                return attr_name
                
        return None
    
    @classmethod
    def extract_pattern_coding_system(cls, element: ElementDefinition) -> Optional[str]:
        """Extract system value from patternCoding if present.
        
        Args:
            element: The FHIR ElementDefinition to extract from
            
        Returns:
            The system URL from patternCoding if found, None otherwise
        """
        if element is None:
            return None
            
        pattern_coding = getattr(element, "patternCoding", None)
        if pattern_coding is None:
            return None
            
        return getattr(pattern_coding, "system", None)
    
    @classmethod
    def has_fixed_or_pattern_value(cls, element: ElementDefinition) -> bool:
        """Check if an ElementDefinition has any fixed or pattern value.
        
        Args:
            element: The FHIR ElementDefinition to check
            
        Returns:
            True if any fixed or pattern value is present, False otherwise
        """
        if element is None:
            return False
            
        return (cls.extract_fixed_value(element) is not None or 
                cls.extract_pattern_coding_system(element) is not None)
    
    @classmethod
    def format_fixed_value_for_display(cls, value: Any, value_type: Optional[str] = None) -> str:
        """Format a fixed value for display in UI or output.
        
        Args:
            value: The fixed value to format
            value_type: Optional type name (e.g., 'fixedUri') for context
            
        Returns:
            Formatted string representation of the value
        """
        if value is None:
            return ""
            
        # Convert to string representation
        if isinstance(value, bool):
            return "true" if value else "false"
        elif isinstance(value, (int, float)):
            return str(value)
        else:
            return str(value)
