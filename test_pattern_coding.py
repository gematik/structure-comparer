#!/usr/bin/env python3
"""
Test script to verify patternCoding.system detection
"""
import sys
from pathlib import Path

# Add service src to path
service_src = Path(__file__).parent / "service" / "src"
sys.path.insert(0, str(service_src))

from structure_comparer.data.profile import Profile

# Load the EPA Medication profile
profile_path = Path("/Users/Shared/dev/structure-comparer/structure-comparer-projects/dgMP Mapping_2025-10/data/de.gematik.epa.medication#1.0.6-2/package/StructureDefinition-epa-medication.json")

print(f"Loading profile from: {profile_path}")
profile = Profile.from_json(profile_path)

print(f"Profile: {profile.name} | {profile.version}")
print(f"Total fields: {len(profile.fields)}")
print()

# Test specific field
test_field = "Medication.code.coding:atc-de.system"
if test_field in profile.fields:
    field = profile.fields[test_field]
    print(f"Field: {test_field}")
    print(f"  path_full: {field.path_full}")
    print(f"  min: {field.min}, max: {field.max}")
    print(f"  pattern_coding_system: {field.pattern_coding_system}")
else:
    print(f"Field {test_field} not found!")

print()
print("All fields with patternCoding.system:")
for field_id, field in profile.fields.items():
    if field.pattern_coding_system:
        print(f"  {field_id}: {field.pattern_coding_system}")
