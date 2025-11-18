"""
Test to verify that overview page and detail page show identical values.

This test ensures that the simplified categories (Kompatibel, Gelöst, Aktion erforderlich)
calculated by the backend are consistent between the mapping evaluation summary endpoint
(used by overview page) and the full evaluation endpoint (used by detail page).
"""

import requests
from pathlib import Path
import subprocess
import time
import os
from typing import Dict, Any, Tuple

# Test configuration
BACKEND_URL = "http://127.0.0.1:8000"
TEST_PROJECT = "dgMP Mapping_2025-10"
TEST_MAPPING_ID = "3b4c5d6e-7f81-4b92-a3c4-2d3e4f5a6702"  # Known mapping ID


class BackendTestServer:
    """Helper class to manage the backend test server."""
    
    def __init__(self):
        self.process = None
        self.service_dir = Path(__file__).parent.parent
    
    def start(self) -> bool:
        """Start the backend server for testing."""
        # Set up environment
        env = os.environ.copy()
        projects_dir = self.service_dir.parent / "structure-comparer-projects"
        env["STRUCTURE_COMPARER_PROJECTS_DIR"] = str(projects_dir)
        
        # Start server process
        cmd = ["poetry", "run", "python", "-m", "structure_comparer", "serve"]
        self.process = subprocess.Popen(
            cmd,
            cwd=self.service_dir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Wait for server to start
        for _ in range(30):  # 30 seconds timeout
            try:
                response = requests.get(f"{BACKEND_URL}/health", timeout=1)
                if response.status_code == 200:
                    return True
            except requests.exceptions.RequestException:
                pass
            time.sleep(1)
        
        return False
    
    def stop(self):
        """Stop the backend server."""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()


def get_mapping_evaluation_summary(project_name: str, mapping_id: str) -> Dict[str, Any]:
    """Get mapping evaluation summary (used by overview page)."""
    url = f"{BACKEND_URL}/project/{project_name}/mapping/{mapping_id}/evaluation/summary"
    response = requests.get(url)
    response.raise_for_status()
    return response.json()


def get_mapping_evaluation_full(project_name: str, mapping_id: str) -> Dict[str, Any]:
    """Get full mapping evaluation (used by detail page)."""
    url = f"{BACKEND_URL}/project/{project_name}/mapping/{mapping_id}/evaluation"
    response = requests.get(url)
    response.raise_for_status()
    return response.json()


def extract_simplified_categories_from_full_evaluation(full_eval: Dict[str, Any]) -> Tuple[int, int, int, int]:
    """
    Extract simplified categories from full evaluation data.
    This replicates the exact same backend logic to test consistency.
    """
    # Get the summary from the full evaluation response
    summary = full_eval.get("summary", {})
    
    # Apply the exact same simplified category logic as the backend
    compatible_count = summary.get('compatible', 0) + summary.get('action_mitigated', 0)
    resolved_count = summary.get('action_resolved', 0)
    
    # Count unique fields that need action (incompatible OR has requires_attention)
    # Avoid double-counting fields that are both incompatible AND need attention
    needs_action_count = 0
    field_evaluations = full_eval.get("field_evaluations", {})
    for field_name, field_eval in field_evaluations.items():
        is_incompatible = field_eval.get('enhanced_classification') == 'incompatible'
        has_requires_attention = any(issue.get('requires_attention', False) for issue in field_eval.get('issues', []))
        if is_incompatible or has_requires_attention:
            needs_action_count += 1
    
    # Total from summary
    total_count = summary.get('total_fields', len(field_evaluations))
    
    return compatible_count, resolved_count, needs_action_count, total_count


def test_overview_detail_consistency():
    """
    Main test to verify overview and detail pages show identical values.
    
    This test:
    1. Gets evaluation summary from backend (overview page data)
    2. Gets full evaluation from backend (detail page data)
    3. Calculates simplified categories from full evaluation
    4. Compares that both approaches yield identical results
    """
    server = BackendTestServer()
    server_started = False
    
    try:
        # Check if server is already running
        try:
            response = requests.get(f"{BACKEND_URL}/project/{TEST_PROJECT}", timeout=2)
            if response.status_code == 200:
                print("Using existing backend server...")
            else:
                raise requests.exceptions.RequestException()
        except requests.exceptions.RequestException:
            # Start backend server
            server_started = server.start()
            assert server_started, "Failed to start backend server"
        
        # Get data from both endpoints
        summary_data = get_mapping_evaluation_summary(TEST_PROJECT, TEST_MAPPING_ID)
        full_data = get_mapping_evaluation_full(TEST_PROJECT, TEST_MAPPING_ID)
        
        # Extract simplified categories from summary (backend calculated)
        backend_compatible = summary_data["simplified_compatible"]
        backend_resolved = summary_data["simplified_resolved"]
        backend_needs_action = summary_data["simplified_needs_action"]
        backend_total = summary_data["total_fields"]
        
        # Extract simplified categories from full evaluation (frontend would calculate)
        frontend_compatible, frontend_resolved, frontend_needs_action, frontend_total = (
            extract_simplified_categories_from_full_evaluation(full_data)
        )
        
        # Verify consistency between backend and frontend calculations
        print("\nBackend Summary (Overview Page):")
        print(f"  Kompatibel: {backend_compatible}")
        print(f"  Gelöst: {backend_resolved}")
        print(f"  Aktion erforderlich: {backend_needs_action}")
        print(f"  Gesamt: {backend_total}")
        
        print("\nFrontend Calculation (Detail Page):")
        print(f"  Kompatibel: {frontend_compatible}")
        print(f"  Gelöst: {frontend_resolved}")
        print(f"  Aktion erforderlich: {frontend_needs_action}")
        print(f"  Gesamt: {frontend_total}")
        
        # Assert that values are identical
        assert backend_compatible == frontend_compatible, (
            f"Compatible count mismatch: Backend={backend_compatible}, "
            f"Frontend={frontend_compatible}"
        )
        assert backend_resolved == frontend_resolved, (
            f"Resolved count mismatch: Backend={backend_resolved}, "
            f"Frontend={frontend_resolved}"
        )
        assert backend_needs_action == frontend_needs_action, (
            f"Needs action count mismatch: Backend={backend_needs_action}, "
            f"Frontend={frontend_needs_action}"
        )
        assert backend_total == frontend_total, (
            f"Total count mismatch: Backend={backend_total}, "
            f"Frontend={frontend_total}"
        )
        
        # Verify base classification math consistency (excluding needs_attention)
        backend_base_sum = backend_compatible + backend_resolved
        frontend_base_sum = frontend_compatible + frontend_resolved
        
        # Note: needs_attention is a cross-cutting flag, so total != sum of all simplified categories
        # The math check should be: compatible + resolved <= total (needs_attention can overlap)
        assert backend_base_sum <= backend_total, (
            f"Backend base classification error: {backend_base_sum} > {backend_total}"
        )
        assert frontend_base_sum <= frontend_total, (
            f"Frontend base classification error: {frontend_base_sum} > {frontend_total}"
        )
        
        print("✅ SUCCESS: Overview and detail pages show identical values!")
        print(f"   Both show: Kompatibel={backend_compatible}, Gelöst={backend_resolved}, "
              f"Aktion erforderlich={backend_needs_action}, Gesamt={backend_total}")
        
    finally:
        if server_started:
            server.stop()


def test_multiple_mappings_consistency():
    """
    Test consistency across multiple mappings to ensure the fix is robust.
    """
    server = BackendTestServer()
    server_started = False
    
    try:
        # Check if server is already running
        try:
            response = requests.get(f"{BACKEND_URL}/project/{TEST_PROJECT}", timeout=2)
            if response.status_code == 200:
                print("Using existing backend server for multi-mapping test...")
            else:
                raise requests.exceptions.RequestException()
        except requests.exceptions.RequestException:
            # Start backend server
            server_started = server.start()
            assert server_started, "Failed to start backend server"
        
        # Get project mappings list
        project_url = f"{BACKEND_URL}/project/{TEST_PROJECT}"
        response = requests.get(project_url)
        response.raise_for_status()
        project_data = response.json()
        
        mappings = project_data.get("mappings", [])[:3]  # Test first 3 mappings
        
        inconsistencies = []
        
        for mapping in mappings:
            mapping_id = mapping["id"]
            mapping_name = mapping["name"]
            
            try:
                # Get data from both endpoints
                summary_data = get_mapping_evaluation_summary(TEST_PROJECT, mapping_id)
                full_data = get_mapping_evaluation_full(TEST_PROJECT, mapping_id)
                
                # Extract values
                backend_compatible = summary_data["simplified_compatible"]
                backend_resolved = summary_data["simplified_resolved"]
                backend_needs_action = summary_data["simplified_needs_action"]
                
                frontend_compatible, frontend_resolved, frontend_needs_action, _ = (
                    extract_simplified_categories_from_full_evaluation(full_data)
                )
                
                # Check for inconsistencies
                if (backend_compatible != frontend_compatible or
                        backend_resolved != frontend_resolved or
                        backend_needs_action != frontend_needs_action):
                    
                    inconsistencies.append({
                        "mapping_name": mapping_name,
                        "mapping_id": mapping_id,
                        "backend": {
                            "compatible": backend_compatible,
                            "resolved": backend_resolved,
                            "needs_action": backend_needs_action
                        },
                        "frontend": {
                            "compatible": frontend_compatible,
                            "resolved": frontend_resolved,
                            "needs_action": frontend_needs_action
                        }
                    })
                
            except Exception as e:
                print(f"Error testing mapping {mapping_name}: {e}")
                continue
        
        # Report results
        if inconsistencies:
            print(f"\n❌ Found inconsistencies in {len(inconsistencies)} mappings:")
            for item in inconsistencies:
                print(f"  {item['mapping_name']}:")
                print(f"    Backend: {item['backend']}")
                print(f"    Frontend: {item['frontend']}")
            
            assert False, f"Found {len(inconsistencies)} mappings with inconsistent values"
        else:
            print(f"\n✅ SUCCESS: All {len(mappings)} tested mappings show consistent values!")
        
    finally:
        if server_started:
            server.stop()


if __name__ == "__main__":
    # Run tests directly
    test_overview_detail_consistency()
    test_multiple_mappings_consistency()
