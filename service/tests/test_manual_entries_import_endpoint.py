"""
Test cases for manual entries import endpoint.
"""

import pytest
import tempfile
import yaml
from io import BytesIO
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
from structure_comparer.serve import app


class TestManualEntriesImportEndpoint:
    """Test cases for the manual entries import endpoint."""
    
    def setup_method(self):
        """Set up test client and mock data."""
        self.client = TestClient(app)
        
        # Mock project structure
        self.mock_project = Mock()
        self.mock_project.key = "test-project"
        
        # Mock mapping
        self.mock_mapping = Mock()
        self.mock_source = Mock()
        self.mock_source.name = "KBV_PR_ERP_Medication_PZN"
        self.mock_mapping.sources = [self.mock_source]
        self.mock_target = Mock()
        self.mock_target.name = "EPAMedication"
        self.mock_mapping.target = self.mock_target
        
        self.mock_project.mappings = {"current-mapping-id": self.mock_mapping}
    
    def create_test_yaml_file(self, content_dict):
        """Create a temporary YAML file with the given content."""
        yaml_content = yaml.dump(content_dict, default_flow_style=False)
        file_content = BytesIO(yaml_content.encode('utf-8'))
        return file_content
    
    @patch('structure_comparer.serve.get_project_by_key')
    def test_import_manual_entries_success(self, mock_get_project):
        """Test successful import of manual entries."""
        mock_get_project.return_value = self.mock_project
        
        # Create test YAML content (legacy format)
        legacy_data = {
            "legacy-mapping-id": {
                "Medication.code": {
                    "classification": "use"
                },
                "Medication.ingredient.strength": {
                    "classification": "fixed",
                    "extra": "test-value"
                }
            }
        }
        
        yaml_file = self.create_test_yaml_file(legacy_data)
        
        # Make the request
        response = self.client.post(
            "/project/test-project/manual-entries/import",
            files={"file": ("test.yaml", yaml_file, "application/x-yaml")}
        )
        
        # Verify response
        assert response.status_code == 200
        result = response.json()
        
        assert result["status"] == "ok"
        assert result["message"] == "Manual entries imported successfully"
        assert result["imported_entries"] == 1
        assert result["imported_fields"] == 2
        assert result["filename"] == "test.yaml"
        
        # Check ID mapping info
        id_mapping = result["id_mapping"]
        assert id_mapping["total_legacy_entries"] == 1
        assert id_mapping["mapped_entries"] == 1
        assert id_mapping["unmapped_entries"] == 0
    
    @patch('structure_comparer.serve.get_project_by_key')
    def test_import_manual_entries_project_not_found(self, mock_get_project):
        """Test import with non-existent project."""
        mock_get_project.return_value = None
        
        legacy_data = {"test": {"field": {"classification": "use"}}}
        yaml_file = self.create_test_yaml_file(legacy_data)
        
        response = self.client.post(
            "/project/nonexistent/manual-entries/import",
            files={"file": ("test.yaml", yaml_file, "application/x-yaml")}
        )
        
        assert response.status_code == 404
        result = response.json()
        assert "Project not found" in result["detail"]
    
    @patch('structure_comparer.serve.get_project_by_key')
    def test_import_manual_entries_invalid_yaml(self, mock_get_project):
        """Test import with invalid YAML file."""
        mock_get_project.return_value = self.mock_project
        
        # Create invalid YAML content
        invalid_content = BytesIO(b"invalid: yaml: content: [unclosed")
        
        response = self.client.post(
            "/project/test-project/manual-entries/import",
            files={"file": ("invalid.yaml", invalid_content, "application/x-yaml")}
        )
        
        assert response.status_code == 400
        result = response.json()
        assert "Failed to parse YAML file" in result["detail"]
    
    @patch('structure_comparer.serve.get_project_by_key')
    def test_import_manual_entries_no_file(self, mock_get_project):
        """Test import without providing a file."""
        mock_get_project.return_value = self.mock_project
        
        response = self.client.post(
            "/project/test-project/manual-entries/import"
        )
        
        assert response.status_code == 422  # Unprocessable Entity
    
    @patch('structure_comparer.serve.get_project_by_key')
    def test_import_manual_entries_migration_error(self, mock_get_project):
        """Test import with migration error."""
        mock_get_project.return_value = self.mock_project
        
        # Create YAML with invalid structure that will cause migration error
        invalid_data = "not a dictionary"
        yaml_content = yaml.dump(invalid_data, default_flow_style=False)
        yaml_file = BytesIO(yaml_content.encode('utf-8'))
        
        response = self.client.post(
            "/project/test-project/manual-entries/import",
            files={"file": ("test.yaml", yaml_file, "application/x-yaml")}
        )
        
        assert response.status_code == 400
        result = response.json()
        assert "Failed to migrate manual entries" in result["detail"]
    
    @patch('structure_comparer.serve.get_project_by_key')
    @patch('structure_comparer.serve.save_manual_entries_to_project')
    def test_import_manual_entries_save_error(self, mock_save, mock_get_project):
        """Test import with save error."""
        mock_get_project.return_value = self.mock_project
        mock_save.side_effect = Exception("Failed to save")
        
        legacy_data = {"test": {"field": {"classification": "use"}}}
        yaml_file = self.create_test_yaml_file(legacy_data)
        
        response = self.client.post(
            "/project/test-project/manual-entries/import",
            files={"file": ("test.yaml", yaml_file, "application/x-yaml")}
        )
        
        assert response.status_code == 500
        result = response.json()
        assert "Failed to save manual entries" in result["detail"]


def test_import_endpoint_integration():
    """Integration test that can be run manually."""
    # This test requires a real server setup and is mainly for manual testing
    print("Integration test placeholder - requires real server setup")
    # In a real integration test environment, you would:
    # 1. Start the server
    # 2. Create a test project
    # 3. Upload a real YAML file
    # 4. Verify the results
    pass


if __name__ == "__main__":
    # Run basic tests
    test_instance = TestManualEntriesImportEndpoint()
    test_instance.setup_method()
    
    print("Manual entries import endpoint tests ready to run with pytest")
    print("Run: pytest tests/test_manual_entries_import_endpoint.py -v")