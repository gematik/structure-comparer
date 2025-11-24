"""Unit tests for fixed_value_extractor module."""

import unittest
from unittest.mock import Mock

from structure_comparer.fixed_value_extractor import FixedValueExtractor


class TestFixedValueExtractor(unittest.TestCase):
    """Test cases for FixedValueExtractor class."""

    def test_extract_fixed_uri(self):
        """Test extraction of fixedUri value."""
        element = Mock()
        element.fixedUri = "https://example.com/fhir/StructureDefinition/example"
        element.fixedString = None
        element.fixedCode = None
        
        result = FixedValueExtractor.extract_fixed_value(element)
        self.assertEqual(result, "https://example.com/fhir/StructureDefinition/example")

    def test_extract_fixed_string(self):
        """Test extraction of fixedString value."""
        element = Mock()
        element.fixedUri = None
        element.fixedUrl = None
        element.fixedCanonical = None
        element.fixedString = "test-value"
        element.fixedCode = None
        
        result = FixedValueExtractor.extract_fixed_value(element)
        self.assertEqual(result, "test-value")

    def test_extract_fixed_code(self):
        """Test extraction of fixedCode value."""
        element = Mock()
        element.fixedUri = None
        element.fixedUrl = None
        element.fixedCanonical = None
        element.fixedString = None
        element.fixedCode = "test-code"
        element.fixedOid = None
        
        result = FixedValueExtractor.extract_fixed_value(element)
        self.assertEqual(result, "test-code")

    def test_extract_fixed_integer(self):
        """Test extraction of fixedInteger value."""
        element = Mock()
        element.fixedUri = None
        element.fixedUrl = None
        element.fixedCanonical = None
        element.fixedString = None
        element.fixedCode = None
        element.fixedOid = None
        element.fixedId = None
        element.fixedUuid = None
        element.fixedInteger = 42
        
        result = FixedValueExtractor.extract_fixed_value(element)
        self.assertEqual(result, 42)

    def test_extract_fixed_decimal(self):
        """Test extraction of fixedDecimal value."""
        element = Mock()
        # Mock all attributes before fixedDecimal
        for attr in FixedValueExtractor.FIXED_VALUE_ATTRS:
            setattr(element, attr, None)
        element.fixedDecimal = 3.14
        
        result = FixedValueExtractor.extract_fixed_value(element)
        self.assertEqual(result, 3.14)

    def test_extract_fixed_boolean(self):
        """Test extraction of fixedBoolean value."""
        element = Mock()
        for attr in FixedValueExtractor.FIXED_VALUE_ATTRS:
            setattr(element, attr, None)
        element.fixedBoolean = True
        
        result = FixedValueExtractor.extract_fixed_value(element)
        self.assertEqual(result, True)

    def test_extract_no_fixed_value(self):
        """Test extraction when no fixed value is present."""
        element = Mock()
        for attr in FixedValueExtractor.FIXED_VALUE_ATTRS:
            setattr(element, attr, None)
        
        result = FixedValueExtractor.extract_fixed_value(element)
        self.assertIsNone(result)

    def test_extract_pattern_coding_system(self):
        """Test extraction of system from patternCoding."""
        element = Mock()
        pattern_coding = Mock()
        pattern_coding.system = "http://example.com/codesystem"
        element.patternCoding = pattern_coding
        
        result = FixedValueExtractor.extract_pattern_coding_system(element)
        self.assertEqual(result, "http://example.com/codesystem")

    def test_extract_pattern_coding_system_none(self):
        """Test extraction when no patternCoding is present."""
        element = Mock()
        element.patternCoding = None
        
        result = FixedValueExtractor.extract_pattern_coding_system(element)
        self.assertIsNone(result)

    def test_get_fixed_value_type(self):
        """Test getting the type of fixed value."""
        element = Mock()
        for attr in FixedValueExtractor.FIXED_VALUE_ATTRS:
            setattr(element, attr, None)
        element.fixedUri = "https://example.com"
        
        result = FixedValueExtractor.get_fixed_value_type(element)
        self.assertEqual(result, "fixedUri")

    def test_has_fixed_or_pattern_value_with_fixed(self):
        """Test has_fixed_or_pattern_value returns True for fixed value."""
        element = Mock()
        for attr in FixedValueExtractor.FIXED_VALUE_ATTRS:
            setattr(element, attr, None)
        element.fixedString = "test"
        element.patternCoding = None
        
        result = FixedValueExtractor.has_fixed_or_pattern_value(element)
        self.assertTrue(result)

    def test_has_fixed_or_pattern_value_with_pattern(self):
        """Test has_fixed_or_pattern_value returns True for pattern value."""
        element = Mock()
        for attr in FixedValueExtractor.FIXED_VALUE_ATTRS:
            setattr(element, attr, None)
        pattern_coding = Mock()
        pattern_coding.system = "http://example.com"
        element.patternCoding = pattern_coding
        
        result = FixedValueExtractor.has_fixed_or_pattern_value(element)
        self.assertTrue(result)

    def test_has_fixed_or_pattern_value_none(self):
        """Test has_fixed_or_pattern_value returns False when no value."""
        element = Mock()
        for attr in FixedValueExtractor.FIXED_VALUE_ATTRS:
            setattr(element, attr, None)
        element.patternCoding = None
        
        result = FixedValueExtractor.has_fixed_or_pattern_value(element)
        self.assertFalse(result)

    def test_format_fixed_value_string(self):
        """Test formatting of string values."""
        result = FixedValueExtractor.format_fixed_value_for_display("test-value")
        self.assertEqual(result, "test-value")

    def test_format_fixed_value_boolean_true(self):
        """Test formatting of boolean True value."""
        result = FixedValueExtractor.format_fixed_value_for_display(True)
        self.assertEqual(result, "true")

    def test_format_fixed_value_boolean_false(self):
        """Test formatting of boolean False value."""
        result = FixedValueExtractor.format_fixed_value_for_display(False)
        self.assertEqual(result, "false")

    def test_format_fixed_value_integer(self):
        """Test formatting of integer value."""
        result = FixedValueExtractor.format_fixed_value_for_display(42)
        self.assertEqual(result, "42")

    def test_format_fixed_value_decimal(self):
        """Test formatting of decimal value."""
        result = FixedValueExtractor.format_fixed_value_for_display(3.14)
        self.assertEqual(result, "3.14")

    def test_format_fixed_value_none(self):
        """Test formatting of None value."""
        result = FixedValueExtractor.format_fixed_value_for_display(None)
        self.assertEqual(result, "")

    def test_extract_none_element(self):
        """Test extraction when element is None."""
        result = FixedValueExtractor.extract_fixed_value(None)
        self.assertIsNone(result)

    def test_priority_order(self):
        """Test that fixedUri has priority over fixedString."""
        element = Mock()
        for attr in FixedValueExtractor.FIXED_VALUE_ATTRS:
            setattr(element, attr, None)
        element.fixedUri = "https://example.com"
        element.fixedString = "should-be-ignored"
        
        result = FixedValueExtractor.extract_fixed_value(element)
        self.assertEqual(result, "https://example.com")


if __name__ == "__main__":
    unittest.main()
