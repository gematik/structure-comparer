"""
Mapping Evaluator Module

This module provides enhanced evaluation capabilities for mappings by considering
the entered mapping actions and providing more accurate warnings and incompatibility assessments.
"""
import logging
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

from .action import Action
from .data.mapping import Mapping, MappingField
from .model.comparison import ComparisonClassification, ComparisonIssue
from .data.profile import Profile

logger = logging.getLogger(__name__)


class EvaluationResult(Enum):
    """Enhanced evaluation results for mapping fields"""
    COMPATIBLE = "compatible"
    WARNING = "warning"
    INCOMPATIBLE = "incompatible"
    ACTION_RESOLVED = "action_resolved"  # Issues resolved by mapping action
    ACTION_MITIGATED = "action_mitigated"  # Issues mitigated but still potential problems


@dataclass
class EvaluationIssue:
    """Detailed information about evaluation issues"""
    issue_type: ComparisonIssue
    severity: EvaluationResult
    message: str
    resolved_by_action: Optional[Action] = None
    requires_attention: bool = True


@dataclass
class FieldEvaluation:
    """Complete evaluation result for a mapping field"""
    field_name: str
    original_classification: ComparisonClassification
    enhanced_classification: EvaluationResult
    action: Action
    issues: List[EvaluationIssue]
    warnings: List[str]
    recommendations: List[str]
    processing_status: Optional[str] = None


class MappingEvaluator:
    """
    Enhanced evaluator for mappings that considers mapping actions
    when determining compatibility and warnings
    """
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Actions that can resolve incompatibilities
        self.resolving_actions = {
            Action.EXTENSION,
            Action.MANUAL,
            Action.FIXED,
            Action.COPY_FROM,
            Action.COPY_TO,
            Action.NOT_USE,
            Action.EMPTY,
            Action.MEDICATION_SERVICE
        }
        
        # Actions that require special attention even when resolving issues
        self.attention_actions = {
            Action.EXTENSION,
            Action.MANUAL,
            Action.MEDICATION_SERVICE
        }
    
    def evaluate_mapping(self, mapping: Mapping) -> Dict[str, FieldEvaluation]:
        """
        Evaluate all fields in a mapping with enhanced logic
        
        Args:
            mapping: The mapping to evaluate
            
        Returns:
            Dictionary of field evaluations keyed by field name
        """
        if not mapping.fields:
            return {}
        
        evaluations = {}
        
        for field_name, field in mapping.fields.items():
            evaluation = self.evaluate_field(field, mapping)
            evaluations[field_name] = evaluation
            
        return evaluations
    
    def evaluate_field(self, field: MappingField, mapping: Mapping) -> FieldEvaluation:
        """
        Evaluate a single mapping field with enhanced logic
        
        Args:
            field: The mapping field to evaluate
            mapping: The parent mapping for context
            
        Returns:
            FieldEvaluation with detailed assessment
        """
        issues = []
        warnings = []
        recommendations = []
        
        # Start with original classification
        original_classification = field.classification
        enhanced_classification = self._map_to_evaluation_result(original_classification)
        
        # Analyze field based on action and profiles
        if field.action == Action.USE:
            enhanced_classification, field_issues = self._evaluate_use_action(field, mapping)
        elif field.action == Action.EXTENSION:
            enhanced_classification, field_issues = self._evaluate_extension_action(field, mapping)
        elif field.action == Action.COPY_FROM:
            enhanced_classification, field_issues = self._evaluate_copy_from_action(field, mapping)
        elif field.action == Action.COPY_TO:
            enhanced_classification, field_issues = self._evaluate_copy_to_action(field, mapping)
        elif field.action == Action.FIXED:
            enhanced_classification, field_issues = self._evaluate_fixed_action(field, mapping)
        elif field.action == Action.NOT_USE:
            enhanced_classification, field_issues = self._evaluate_not_use_action(field, mapping)
        elif field.action == Action.EMPTY:
            enhanced_classification, field_issues = self._evaluate_empty_action(field, mapping)
        elif field.action == Action.MANUAL:
            enhanced_classification, field_issues = self._evaluate_manual_action(field, mapping)
        elif field.action == Action.MEDICATION_SERVICE:
            enhanced_classification, field_issues = self._evaluate_medication_service_action(field, mapping)
        else:
            field_issues = []
            
        issues.extend(field_issues)
        
        # Add cardinality warnings
        cardinality_warnings = self._check_cardinality_issues(field, mapping)
        warnings.extend(cardinality_warnings)
        
        # Generate recommendations
        field_recommendations = self._generate_recommendations(field, enhanced_classification, issues)
        recommendations.extend(field_recommendations)
        
        # Calculate processing status
        processing_status = self._calculate_processing_status(original_classification, field.action)
        
        return FieldEvaluation(
            field_name=field.name,
            original_classification=original_classification,
            enhanced_classification=enhanced_classification,
            action=field.action,
            issues=issues,
            warnings=warnings,
            recommendations=recommendations,
            processing_status=processing_status
        )
    
    def _evaluate_use_action(self, field: MappingField, mapping: Mapping) -> Tuple[EvaluationResult, List[EvaluationIssue]]:
        """Evaluate field with USE action"""
        issues = []
        
        # Check if target field exists
        target_profile = field.profiles.get(mapping.target.key)
        if target_profile is None:
            issues.append(EvaluationIssue(
                issue_type=ComparisonIssue.MIN,
                severity=EvaluationResult.INCOMPATIBLE,
                message="Cannot use field that doesn't exist in target profile",
                requires_attention=True
            ))
            return EvaluationResult.INCOMPATIBLE, issues
        
        # Check source compatibility
        for source in mapping.sources:
            source_profile = field.profiles.get(source.key)
            if source_profile is None:
                continue
                
            # Min cardinality check
            if source_profile.min < target_profile.min:
                if self._has_optional_parent_chain(field.name, source):
                    issues.append(EvaluationIssue(
                        issue_type=ComparisonIssue.MIN,
                        severity=EvaluationResult.WARNING,
                        message=f"Minimum cardinality mismatch mitigated by optional parent in {source.key}",
                        requires_attention=False
                    ))
                else:
                    issues.append(EvaluationIssue(
                        issue_type=ComparisonIssue.MIN,
                        severity=EvaluationResult.INCOMPATIBLE,
                        message=f"Source {source.key} minimum cardinality ({source_profile.min}) < target minimum ({target_profile.min})",
                        requires_attention=True
                    ))
            
            # Max cardinality check
            if source_profile.max_num > target_profile.max_num:
                issues.append(EvaluationIssue(
                    issue_type=ComparisonIssue.MAX,
                    severity=EvaluationResult.WARNING,
                    message=f"Source {source.key} maximum cardinality ({source_profile.max_num}) > target maximum ({target_profile.max_num})",
                    requires_attention=True
                ))
        
        # Determine overall result
        if any(issue.severity == EvaluationResult.INCOMPATIBLE for issue in issues):
            return EvaluationResult.INCOMPATIBLE, issues
        elif any(issue.severity == EvaluationResult.WARNING for issue in issues):
            return EvaluationResult.WARNING, issues
        else:
            return EvaluationResult.COMPATIBLE, issues
    
    def _evaluate_extension_action(self, field: MappingField, mapping: Mapping) -> Tuple[EvaluationResult, List[EvaluationIssue]]:
        """Evaluate field with EXTENSION action"""
        issues = []
        
        # Extension resolves missing target field issue
        target_profile = field.profiles.get(mapping.target.key)
        if target_profile is None:
            issues.append(EvaluationIssue(
                issue_type=ComparisonIssue.MIN,
                severity=EvaluationResult.ACTION_RESOLVED,
                message="Missing target field resolved by extension",
                resolved_by_action=Action.EXTENSION,
                requires_attention=True  # Extensions need documentation
            ))
        
        return EvaluationResult.ACTION_RESOLVED, issues
    
    def _evaluate_copy_from_action(self, field: MappingField, mapping: Mapping) -> Tuple[EvaluationResult, List[EvaluationIssue]]:
        """Evaluate field with COPY_FROM action"""
        issues = []
        
        if field.other:
            # Check if source field exists
            source_field_exists = any(
                field.other in mapping.fields for source in mapping.sources
            )
            
            if source_field_exists:
                issues.append(EvaluationIssue(
                    issue_type=ComparisonIssue.REF,
                    severity=EvaluationResult.ACTION_RESOLVED,
                    message=f"Field value copied from {field.other}",
                    resolved_by_action=Action.COPY_FROM,
                    requires_attention=False
                ))
            else:
                issues.append(EvaluationIssue(
                    issue_type=ComparisonIssue.REF,
                    severity=EvaluationResult.WARNING,
                    message=f"Copy source field {field.other} not found",
                    requires_attention=True
                ))
        
        return EvaluationResult.ACTION_RESOLVED, issues
    
    def _evaluate_copy_to_action(self, field: MappingField, mapping: Mapping) -> Tuple[EvaluationResult, List[EvaluationIssue]]:
        """Evaluate field with COPY_TO action"""
        issues = []
        
        if field.other:
            issues.append(EvaluationIssue(
                issue_type=ComparisonIssue.REF,
                severity=EvaluationResult.ACTION_RESOLVED,
                message=f"Field value copied to {field.other}",
                resolved_by_action=Action.COPY_TO,
                requires_attention=False
            ))
        
        return EvaluationResult.ACTION_RESOLVED, issues
    
    def _evaluate_fixed_action(self, field: MappingField, mapping: Mapping) -> Tuple[EvaluationResult, List[EvaluationIssue]]:
        """Evaluate field with FIXED action"""
        issues = []
        
        if field.fixed:
            issues.append(EvaluationIssue(
                issue_type=ComparisonIssue.REF,
                severity=EvaluationResult.ACTION_RESOLVED,
                message=f"Field set to fixed value: {field.fixed}",
                resolved_by_action=Action.FIXED,
                requires_attention=False
            ))
        else:
            issues.append(EvaluationIssue(
                issue_type=ComparisonIssue.REF,
                severity=EvaluationResult.WARNING,
                message="Fixed action specified but no fixed value provided",
                requires_attention=True
            ))
        
        return EvaluationResult.ACTION_RESOLVED, issues
    
    def _evaluate_not_use_action(self, field: MappingField, mapping: Mapping) -> Tuple[EvaluationResult, List[EvaluationIssue]]:
        """Evaluate field with NOT_USE action"""
        issues = []
        
        target_profile = field.profiles.get(mapping.target.key)
        if target_profile and target_profile.min > 0:
            issues.append(EvaluationIssue(
                issue_type=ComparisonIssue.MIN,
                severity=EvaluationResult.WARNING,
                message="Required target field marked as NOT_USE",
                requires_attention=True
            ))
        else:
            issues.append(EvaluationIssue(
                issue_type=ComparisonIssue.REF,
                severity=EvaluationResult.ACTION_RESOLVED,
                message="Field explicitly not used",
                resolved_by_action=Action.NOT_USE,
                requires_attention=False
            ))
        
        return EvaluationResult.ACTION_RESOLVED, issues
    
    def _evaluate_empty_action(self, field: MappingField, mapping: Mapping) -> Tuple[EvaluationResult, List[EvaluationIssue]]:
        """Evaluate field with EMPTY action"""
        issues = []
        
        target_profile = field.profiles.get(mapping.target.key)
        if target_profile and target_profile.min > 0:
            issues.append(EvaluationIssue(
                issue_type=ComparisonIssue.MIN,
                severity=EvaluationResult.WARNING,
                message="Required target field marked as EMPTY",
                requires_attention=True
            ))
        else:
            issues.append(EvaluationIssue(
                issue_type=ComparisonIssue.REF,
                severity=EvaluationResult.ACTION_RESOLVED,
                message="Field left empty",
                resolved_by_action=Action.EMPTY,
                requires_attention=False
            ))
        
        return EvaluationResult.ACTION_RESOLVED, issues
    
    def _evaluate_manual_action(self, field: MappingField, mapping: Mapping) -> Tuple[EvaluationResult, List[EvaluationIssue]]:
        """Evaluate field with MANUAL action"""
        issues = []
        
        issues.append(EvaluationIssue(
            issue_type=ComparisonIssue.REF,
            severity=EvaluationResult.ACTION_MITIGATED,
            message="Field requires manual implementation",
            resolved_by_action=Action.MANUAL,
            requires_attention=True
        ))
        
        return EvaluationResult.ACTION_MITIGATED, issues
    
    def _evaluate_medication_service_action(self, field: MappingField, mapping: Mapping) -> Tuple[EvaluationResult, List[EvaluationIssue]]:
        """Evaluate field with MEDICATION_SERVICE action"""
        issues = []
        
        issues.append(EvaluationIssue(
            issue_type=ComparisonIssue.REF,
            severity=EvaluationResult.ACTION_MITIGATED,
            message="Field handled by medication service - requires validation",
            resolved_by_action=Action.MEDICATION_SERVICE,
            requires_attention=True
        ))
        
        return EvaluationResult.ACTION_MITIGATED, issues
    
    def _check_cardinality_issues(self, field: MappingField, mapping: Mapping) -> List[str]:
        """Check for cardinality-related warnings"""
        warnings = []
        
        target_profile = field.profiles.get(mapping.target.key)
        if not target_profile:
            return warnings
        
        for source in mapping.sources:
            source_profile = field.profiles.get(source.key)
            if not source_profile:
                continue
            
            # Skip cardinality checks for actions that handle the mapping explicitly
            if field.action in {Action.EXTENSION, Action.COPY_FROM, Action.COPY_TO}:
                continue
            
            # Max cardinality warning
            if source_profile.max_num > target_profile.max_num:
                warnings.append(
                    f"Source {source.key} allows more instances ({source_profile.max_num}) "
                    f"than target ({target_profile.max_num})"
                )
            
            # Min cardinality warning for non-zero source min
            if (source_profile.max_num != 0 and 
                source_profile.min < target_profile.min and 
                field.action not in {Action.EXTENSION, Action.COPY_FROM, Action.COPY_TO}):
                warnings.append(
                    f"Source {source.key} minimum cardinality ({source_profile.min}) "
                    f"is less than target minimum ({target_profile.min})"
                )
        
        return warnings
    
    def _generate_recommendations(self, field: MappingField, classification: EvaluationResult, 
                                 issues: List[EvaluationIssue]) -> List[str]:
        """Generate recommendations for field mappings"""
        recommendations = []
        
        if classification == EvaluationResult.INCOMPATIBLE:
            if field.action == Action.USE:
                recommendations.append("Consider using EXTENSION, COPY_FROM, or FIXED action")
            
        if classification == EvaluationResult.WARNING:
            if any(issue.issue_type == ComparisonIssue.MAX for issue in issues):
                recommendations.append("Verify that extra cardinality is handled appropriately")
            
        if field.action in self.attention_actions:
            recommendations.append("Ensure proper documentation for this mapping action")
        
        if field.action == Action.COPY_FROM and not field.other:
            recommendations.append("Specify the source field for COPY_FROM action")
            
        if field.action == Action.FIXED and not field.fixed:
            recommendations.append("Specify the fixed value for FIXED action")
        
        return recommendations
    
    def _has_optional_parent_chain(self, field_path: str, profile: Profile) -> bool:
        """Check if field has optional parents in the profile"""
        parts = field_path.split('.')
        for i in range(len(parts) - 1):
            parent_path = '.'.join(parts[:i+1])
            parent_field = profile.fields.get(parent_path)
            if parent_field and parent_field.min == 0:
                return True
        return False
    
    def _map_to_evaluation_result(self, classification: ComparisonClassification) -> EvaluationResult:
        """Map comparison classification to evaluation result"""
        mapping = {
            ComparisonClassification.COMPAT: EvaluationResult.COMPATIBLE,
            ComparisonClassification.WARN: EvaluationResult.WARNING,
            ComparisonClassification.INCOMPAT: EvaluationResult.INCOMPATIBLE
        }
        return mapping.get(classification, EvaluationResult.WARNING)
    
    def _calculate_processing_status(self, original_classification: ComparisonClassification, action: Action) -> str:
        """Calculate processing status based on original classification and action"""
        # Central status logic that matches frontend expectations
        if original_classification in [ComparisonClassification.COMPAT, ComparisonClassification.WARN]:
            return 'completed'
        elif original_classification == ComparisonClassification.INCOMPAT and action != Action.USE:
            return 'resolved'
        elif original_classification == ComparisonClassification.INCOMPAT and action == Action.USE:
            return 'needs_action'
        else:
            return 'needs_action'  # fallback
    
    def get_mapping_summary(self, evaluations: Dict[str, FieldEvaluation]) -> Dict[str, int]:
        """Get summary statistics for mapping evaluations"""
        summary = {
            "total_fields": len(evaluations),
            "compatible": 0,
            "warnings": 0,
            "incompatible": 0,
            "action_resolved": 0,
            "action_mitigated": 0,
            "needs_attention": 0
        }
        
        for evaluation in evaluations.values():
            if evaluation.enhanced_classification == EvaluationResult.COMPATIBLE:
                summary["compatible"] += 1
            elif evaluation.enhanced_classification == EvaluationResult.WARNING:
                summary["warnings"] += 1
            elif evaluation.enhanced_classification == EvaluationResult.INCOMPATIBLE:
                summary["incompatible"] += 1
            elif evaluation.enhanced_classification == EvaluationResult.ACTION_RESOLVED:
                summary["action_resolved"] += 1
            elif evaluation.enhanced_classification == EvaluationResult.ACTION_MITIGATED:
                summary["action_mitigated"] += 1
            
            if any(issue.requires_attention for issue in evaluation.issues):
                summary["needs_attention"] += 1
        
        return summary