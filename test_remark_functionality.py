#!/usr/bin/env python3
"""
Test script to debug remark functionality in the Structure Comparer API
"""
import requests
import json
import yaml
from pathlib import Path

API_BASE = "http://127.0.0.1:8000"
PROJECT_KEY = "dgMP Mapping_2026-07-forwards"
MAPPING_ID = "3a1c8837-fb39-429f-a35f-08746e9c0bfb"
FIELD_NAME = "MedicationDispense.partOf"
MANUAL_ENTRIES_PATH = "/Users/Shared/dev/structure-comparer/structure-comparer-projects/dgMP Mapping_2026-07-forwards/manual_entries.yaml"

def test_api_call():
    """Test the API call with remark"""
    url = f"{API_BASE}/project/{PROJECT_KEY}/mapping/{MAPPING_ID}/field/{FIELD_NAME}"
    
    payload = {
        "action": "manual",
        "remark": "Test Remark via Script"
    }
    
    print(f"🔧 Testing API: {url}")
    print(f"📤 Payload: {json.dumps(payload, indent=2)}")
    
    response = requests.post(url, json=payload)
    
    print(f"📥 Status Code: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ API Response:")
        print(f"   - Action: {result.get('action')}")
        print(f"   - Remark: {result.get('remark')}")
        return result
    else:
        print(f"❌ API Error: {response.text}")
        return None

def check_file_content():
    """Check the manual_entries.yaml file content"""
    try:
        with open(MANUAL_ENTRIES_PATH, 'r') as f:
            content = yaml.safe_load(f)
        
        print(f"📁 File Content ({MANUAL_ENTRIES_PATH}):")
        print(yaml.dump(content, indent=2))
        
        # Find the specific entry
        for entry in content.get('entries', []):
            if entry.get('id') == MAPPING_ID:
                for field in entry.get('fields', []):
                    if field.get('name') == FIELD_NAME:
                        print(f"🎯 Found field:")
                        print(f"   - Name: {field.get('name')}")
                        print(f"   - Action: {field.get('action')}")
                        print(f"   - Remark: {field.get('remark')}")
                        return field
        
        print(f"❌ Field {FIELD_NAME} not found in file")
        return None
        
    except Exception as e:
        print(f"❌ Error reading file: {e}")
        return None

def main():
    print("🚀 Starting Remark Functionality Debug Test")
    print("=" * 50)
    
    # Test 1: Check current file state
    print("\n1️⃣ BEFORE API CALL - Current File State:")
    check_file_content()
    
    # Test 2: Make API call
    print("\n2️⃣ API CALL:")
    api_result = test_api_call()
    
    # Test 3: Check file state after API call
    print("\n3️⃣ AFTER API CALL - Updated File State:")
    file_result = check_file_content()
    
    # Test 4: Analysis
    print("\n4️⃣ ANALYSIS:")
    if api_result and file_result:
        api_remark = api_result.get('remark')
        file_remark = file_result.get('remark')
        
        print(f"   API Remark: '{api_remark}'")
        print(f"   File Remark: '{file_remark}'")
        
        if api_remark and api_remark == file_remark:
            print("   ✅ SUCCESS: Remark matches in API and file!")
        elif api_remark and not file_remark:
            print("   ❌ PROBLEM: API returns remark, but file still has null/None")
        elif not api_remark:
            print("   ❌ PROBLEM: API doesn't return remark")
        else:
            print("   ❓ UNCLEAR: Mixed results")
    
    print("\n" + "=" * 50)

if __name__ == "__main__":
    main()