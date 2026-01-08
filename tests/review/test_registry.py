"""
Tests for review type registry (ARCH-003).

Ensures the single source of truth for review types is consistent
and that validation catches misconfigurations.
"""

import pytest
from src.review.registry import (
    REVIEW_TYPES,
    ReviewTypeDefinition,
    get_review_item_mapping,
    get_all_review_types,
    get_review_type,
    get_model_for_review,
    get_workflow_item_ids,
    validate_review_configuration,
    get_configuration_status,
    ReviewConfigurationError,
    LEGACY_ITEM_MAPPINGS,
)


class TestReviewTypeDefinition:
    """Tests for ReviewTypeDefinition dataclass."""

    def test_frozen(self):
        """Should be immutable."""
        defn = ReviewTypeDefinition(
            name="test",
            workflow_item_id="test_review",
            model="codex",
            description="Test review",
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            defn.name = "changed"

    def test_prompt_key_defaults_to_name(self):
        """Should default prompt_key to name."""
        defn = ReviewTypeDefinition(
            name="test",
            workflow_item_id="test_review",
            model="codex",
            description="Test review",
        )
        assert defn.prompt_key == "test"

    def test_prompt_key_can_be_overridden(self):
        """Should allow custom prompt_key."""
        defn = ReviewTypeDefinition(
            name="test",
            workflow_item_id="test_review",
            model="codex",
            description="Test review",
            prompt_key="custom_key",
        )
        assert defn.prompt_key == "custom_key"


class TestReviewTypes:
    """Tests for REVIEW_TYPES constant."""

    def test_has_all_five_types(self):
        """Should have exactly 5 review types."""
        expected = {"security", "quality", "consistency", "holistic", "vibe_coding"}
        assert set(REVIEW_TYPES.keys()) == expected

    def test_security_review(self):
        """Security review should be configured correctly."""
        defn = REVIEW_TYPES["security"]
        assert defn.name == "security"
        assert defn.workflow_item_id == "security_review"
        assert defn.model == "codex"
        assert "OWASP" in defn.description or "injection" in defn.description

    def test_vibe_coding_review(self):
        """Vibe coding review should be configured correctly."""
        defn = REVIEW_TYPES["vibe_coding"]
        assert defn.name == "vibe_coding"
        assert defn.workflow_item_id == "vibe_coding_review"
        assert defn.model == "grok"
        assert "AI" in defn.description or "hallucin" in defn.description

    def test_all_have_required_fields(self):
        """All review types should have required fields."""
        for name, defn in REVIEW_TYPES.items():
            assert defn.name == name
            assert defn.workflow_item_id.endswith("_review")
            assert defn.model in ("codex", "gemini", "grok")
            assert len(defn.description) > 10


class TestGetReviewItemMapping:
    """Tests for get_review_item_mapping()."""

    def test_returns_dict(self):
        """Should return a dictionary."""
        mapping = get_review_item_mapping()
        assert isinstance(mapping, dict)

    def test_has_all_canonical_items(self):
        """Should have all canonical workflow item IDs."""
        mapping = get_review_item_mapping()
        for defn in REVIEW_TYPES.values():
            assert defn.workflow_item_id in mapping
            assert mapping[defn.workflow_item_id] == defn.name

    def test_includes_legacy_mappings(self):
        """Should include legacy mappings for backwards compatibility."""
        mapping = get_review_item_mapping()
        for legacy_item, review_type in LEGACY_ITEM_MAPPINGS.items():
            assert legacy_item in mapping
            assert mapping[legacy_item] == review_type

    def test_architecture_maps_to_holistic(self):
        """Legacy architecture_review should map to holistic."""
        mapping = get_review_item_mapping()
        assert "architecture_review" in mapping
        assert mapping["architecture_review"] == "holistic"


class TestGetAllReviewTypes:
    """Tests for get_all_review_types()."""

    def test_returns_list(self):
        """Should return a list."""
        types = get_all_review_types()
        assert isinstance(types, list)

    def test_has_all_types(self):
        """Should have all 5 types."""
        types = get_all_review_types()
        assert len(types) == 5
        assert set(types) == {"security", "quality", "consistency", "holistic", "vibe_coding"}


class TestGetReviewType:
    """Tests for get_review_type()."""

    def test_returns_definition(self):
        """Should return ReviewTypeDefinition for valid type."""
        defn = get_review_type("security")
        assert isinstance(defn, ReviewTypeDefinition)
        assert defn.name == "security"

    def test_returns_none_for_unknown(self):
        """Should return None for unknown type."""
        assert get_review_type("unknown") is None


class TestGetModelForReview:
    """Tests for get_model_for_review()."""

    def test_codex_reviews(self):
        """Security and quality should use codex."""
        assert get_model_for_review("security") == "codex"
        assert get_model_for_review("quality") == "codex"

    def test_gemini_reviews(self):
        """Consistency and holistic should use gemini."""
        assert get_model_for_review("consistency") == "gemini"
        assert get_model_for_review("holistic") == "gemini"

    def test_grok_reviews(self):
        """Vibe coding should use grok."""
        assert get_model_for_review("vibe_coding") == "grok"

    def test_unknown_defaults_to_gemini(self):
        """Unknown types should default to gemini."""
        assert get_model_for_review("unknown") == "gemini"


class TestGetWorkflowItemIds:
    """Tests for get_workflow_item_ids()."""

    def test_returns_list(self):
        """Should return a list."""
        items = get_workflow_item_ids()
        assert isinstance(items, list)

    def test_has_all_items(self):
        """Should have all workflow item IDs."""
        items = get_workflow_item_ids()
        expected = {
            "security_review",
            "quality_review",
            "consistency_review",
            "holistic_review",
            "vibe_coding_review",
        }
        assert set(items) == expected


class TestValidateReviewConfiguration:
    """Tests for validate_review_configuration()."""

    def test_valid_with_all_items(self):
        """Should pass with all canonical items."""
        workflow_items = [
            "security_review",
            "quality_review",
            "consistency_review",
            "holistic_review",
            "vibe_coding_review",
            "collect_review_results",  # Extra item is OK
        ]
        errors = validate_review_configuration(workflow_items, raise_on_error=False)
        assert len(errors) == 0

    def test_warns_on_missing_items(self):
        """Should warn when workflow is missing items."""
        workflow_items = ["security_review", "quality_review"]  # Missing 3
        errors = validate_review_configuration(workflow_items, raise_on_error=False)
        assert len(errors) > 0
        assert any("missing" in e.lower() for e in errors)

    def test_warns_on_unknown_items(self):
        """Should warn on unknown items in workflow."""
        workflow_items = [
            "security_review",
            "quality_review",
            "consistency_review",
            "holistic_review",
            "vibe_coding_review",
            "unknown_review",  # Unknown
        ]
        errors = validate_review_configuration(workflow_items, raise_on_error=False)
        assert len(errors) > 0
        assert any("unknown" in e.lower() for e in errors)

    def test_allows_legacy_items(self):
        """Should allow legacy items without warning."""
        workflow_items = [
            "security_review",
            "quality_review",
            "consistency_review",
            "holistic_review",
            "vibe_coding_review",
            "architecture_review",  # Legacy
        ]
        errors = validate_review_configuration(workflow_items, raise_on_error=False)
        # Should not warn about architecture_review as unknown
        assert not any("architecture_review" in e for e in errors)

    def test_raises_on_error_when_requested(self):
        """Should raise ReviewConfigurationError when raise_on_error=True."""
        workflow_items = ["security_review"]  # Missing most items
        with pytest.raises(ReviewConfigurationError):
            validate_review_configuration(workflow_items, raise_on_error=True)

    def test_skips_workflow_validation_when_none(self):
        """Should skip workflow validation when items is None."""
        # Should not raise even though no items provided
        errors = validate_review_configuration(None, raise_on_error=False)
        # May still have prompt-related warnings, but no workflow errors
        assert not any("workflow" in e.lower() for e in errors)


class TestGetConfigurationStatus:
    """Tests for get_configuration_status()."""

    def test_returns_dict(self):
        """Should return a dictionary."""
        status = get_configuration_status()
        assert isinstance(status, dict)

    def test_has_required_keys(self):
        """Should have all required status keys."""
        status = get_configuration_status()
        assert "review_types" in status
        assert "workflow_item_ids" in status
        assert "item_mapping" in status
        assert "legacy_mappings" in status
        assert "models" in status

    def test_review_types_match(self):
        """Status review_types should match REVIEW_TYPES."""
        status = get_configuration_status()
        assert set(status["review_types"]) == set(REVIEW_TYPES.keys())


class TestIntegration:
    """Integration tests ensuring cli.py and router.py use registry."""

    def test_cli_uses_registry(self):
        """cli.py REVIEW_ITEM_MAPPING should come from registry."""
        from src.cli import REVIEW_ITEM_MAPPING
        registry_mapping = get_review_item_mapping()

        # Should have same content
        assert REVIEW_ITEM_MAPPING == registry_mapping

    def test_router_uses_registry(self):
        """router.py execute_all_reviews should use registry types."""
        from src.review.router import get_all_review_types as router_get_types

        # Should be the same function
        assert router_get_types == get_all_review_types

    def test_all_types_have_prompts(self):
        """All review types should have corresponding prompts."""
        from src.review.prompts import REVIEW_PROMPTS

        for review_type in get_all_review_types():
            # Prompts may use the type name or type_review format
            has_prompt = (
                review_type in REVIEW_PROMPTS or
                f"{review_type}_review" in REVIEW_PROMPTS
            )
            assert has_prompt, f"Missing prompt for {review_type}"
