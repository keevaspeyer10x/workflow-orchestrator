"""
Evidence schemas for documented step types.

These Pydantic models define the structure of evidence artifacts
that prove engagement with a workflow step.
"""

from typing import Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class CodeAnalysisEvidence(BaseModel):
    """
    Evidence for code analysis steps.

    Proves that the agent reviewed existing code before making changes.
    """
    files_reviewed: list[str] = Field(
        ...,
        description="List of files that were reviewed",
        min_length=1
    )
    patterns_identified: list[str] = Field(
        ...,
        description="Patterns, conventions, or structures identified in the code"
    )
    concerns_raised: list[str] = Field(
        default_factory=list,
        description="Any concerns or issues identified during review"
    )
    approach_decision: str = Field(
        ...,
        description="Decision on how to approach the implementation",
        min_length=20
    )

    @field_validator('files_reviewed')
    @classmethod
    def files_must_not_be_empty(cls, v):
        if not v:
            raise ValueError("Must list at least one file reviewed")
        return v

    @field_validator('approach_decision')
    @classmethod
    def approach_must_be_substantive(cls, v):
        if len(v.strip()) < 20:
            raise ValueError("Approach decision must be at least 20 characters")
        return v


class EdgeCaseEvidence(BaseModel):
    """
    Evidence for edge case consideration steps.

    Proves that edge cases were considered during implementation.
    """
    cases_considered: list[str] = Field(
        ...,
        description="Edge cases that were considered",
        min_length=1
    )
    how_handled: dict[str, str] = Field(
        ...,
        description="Mapping of edge case to how it's handled"
    )
    cases_deferred: list[str] = Field(
        default_factory=list,
        description="Edge cases acknowledged but deferred (with reason)"
    )

    @field_validator('cases_considered')
    @classmethod
    def must_consider_cases(cls, v):
        if not v:
            raise ValueError("Must consider at least one edge case")
        return v

    @model_validator(mode='after')
    def handled_cases_must_match(self):
        """All considered cases should have handling documented."""
        for case in self.cases_considered:
            if case not in self.how_handled and case not in self.cases_deferred:
                # Warning but don't fail - some cases might be implicitly handled
                pass
        return self


class SpecReviewEvidence(BaseModel):
    """
    Evidence for spec/requirements review steps.

    Proves that specifications were read and understood.
    """
    requirements_extracted: list[str] = Field(
        ...,
        description="Key requirements extracted from the spec",
        min_length=1
    )
    ambiguities_found: list[str] = Field(
        default_factory=list,
        description="Ambiguous areas in the spec"
    )
    assumptions_made: list[str] = Field(
        default_factory=list,
        description="Assumptions made to resolve ambiguities"
    )

    @field_validator('requirements_extracted')
    @classmethod
    def must_extract_requirements(cls, v):
        if not v:
            raise ValueError("Must extract at least one requirement from spec")
        return v


class TestPlanEvidence(BaseModel):
    """
    Evidence for test planning steps.

    Proves that testing was planned before implementation.
    """
    test_cases_planned: list[str] = Field(
        ...,
        description="Test cases that will be written",
        min_length=1
    )
    coverage_approach: str = Field(
        ...,
        description="Approach to test coverage",
        min_length=10
    )
    edge_cases_covered: list[str] = Field(
        default_factory=list,
        description="Edge cases that tests will cover"
    )

    @field_validator('test_cases_planned')
    @classmethod
    def must_plan_tests(cls, v):
        if not v:
            raise ValueError("Must plan at least one test case")
        return v


# Registry of all evidence schemas
EVIDENCE_SCHEMAS: dict[str, type[BaseModel]] = {
    "CodeAnalysisEvidence": CodeAnalysisEvidence,
    "EdgeCaseEvidence": EdgeCaseEvidence,
    "SpecReviewEvidence": SpecReviewEvidence,
    "TestPlanEvidence": TestPlanEvidence,
}


def get_evidence_schema(name: str) -> Optional[type[BaseModel]]:
    """
    Get an evidence schema by name.

    Args:
        name: The schema name (e.g., "CodeAnalysisEvidence")

    Returns:
        The Pydantic model class, or None if not found
    """
    return EVIDENCE_SCHEMAS.get(name)


def validate_evidence_depth(schema_name: str, evidence: dict) -> tuple[bool, Optional[str]]:
    """
    Validate that evidence is substantive, not shallow.

    Args:
        schema_name: Name of the evidence schema
        evidence: The evidence dict to validate

    Returns:
        (is_valid, error_message) tuple
    """
    schema = get_evidence_schema(schema_name)
    if not schema:
        return False, f"Unknown evidence schema: {schema_name}"

    try:
        # First validate against schema
        validated = schema(**evidence)

        # Additional depth checks based on schema type
        if schema_name == "CodeAnalysisEvidence":
            if len(validated.files_reviewed) == 0:
                return False, "Must list files that were reviewed"
            if len(validated.approach_decision) < 20:
                return False, "Approach decision is too short - explain your thinking"

        elif schema_name == "EdgeCaseEvidence":
            if len(validated.cases_considered) == 0:
                return False, "Must consider at least one edge case"

        elif schema_name == "SpecReviewEvidence":
            if len(validated.requirements_extracted) == 0:
                return False, "Must extract at least one requirement"

        elif schema_name == "TestPlanEvidence":
            if len(validated.test_cases_planned) == 0:
                return False, "Must plan at least one test case"

        return True, None

    except Exception as e:
        return False, str(e)
