"""
Summary Validator for V4.2 Chat Mode.

Validates that summaries preserve critical information from original messages.
Uses regex-based extraction for deterministic validation (no LLM calls).
"""
import re
from typing import List, Set

from .models import Message, ValidationResult


class SummaryValidator:
    """
    Validates summaries preserve critical information.

    Uses regex patterns to extract:
    - File paths
    - Function/method names
    - URLs
    - Decision keywords

    Validation is deterministic (no LLM calls).
    """

    # Regex patterns for entity extraction
    FILE_PATH_PATTERN = re.compile(
        r'(?:^|[\s\'"(])([./][\w./\-]+\.[a-zA-Z0-9]+)(?=[\s\'").,;:]|$)|'  # /path/to/file.ext
        r'(?:^|[\s\'"(])(\./[\w./\-]+)(?=[\s\'").,;:]|$)|'  # ./relative/path
        r'(?:^|[\s\'"(])(\.\.[\w./\-]+)(?=[\s\'").,;:]|$)'  # ../parent/path
    )

    FUNCTION_PATTERN = re.compile(
        r'(\w+\.\w+\(\))|'  # Class.method()
        r'(?<![.\w])(\w+\(\))'  # function()
    )

    URL_PATTERN = re.compile(
        r'(https?://[^\s<>"\']+?)(?=[.,;:]?\s|[.,;:]?$)'  # URLs, stop at whitespace or end
    )

    DECISION_KEYWORDS = [
        "decided", "chose", "chosen", "selected", "picked",
        "approved", "rejected", "accepted", "declined",
        "agreed", "confirmed", "determined",
    ]

    DECISION_PATTERN = re.compile(
        r'([^.!?]*\b(?:' + '|'.join(DECISION_KEYWORDS) + r')\b[^.!?]*[.!?])',
        re.IGNORECASE
    )

    def extract_entities(self, text: str) -> Set[str]:
        """
        Extract entities from text.

        Returns set of:
        - File paths
        - Function names
        - URLs
        """
        entities = set()

        # Extract file paths
        for match in self.FILE_PATH_PATTERN.finditer(text):
            for group in match.groups():
                if group:
                    entities.add(group.strip())

        # Extract function names
        for match in self.FUNCTION_PATTERN.finditer(text):
            for group in match.groups():
                if group:
                    entities.add(group.strip())

        # Extract URLs
        for match in self.URL_PATTERN.finditer(text):
            entities.add(match.group(1).strip())

        return entities

    def extract_decisions(self, text: str) -> List[str]:
        """
        Extract decision statements from text.

        Returns list of sentences containing decision keywords.
        """
        decisions = []

        for match in self.DECISION_PATTERN.finditer(text):
            decision = match.group(1).strip()
            if decision and len(decision) > 10:  # Skip very short matches
                decisions.append(decision)

        return decisions

    def validate(
        self,
        messages: List[Message],
        summary: str,
    ) -> ValidationResult:
        """
        Validate that summary contains all critical information from messages.

        Args:
            messages: Original messages being summarized
            summary: The proposed summary

        Returns:
            ValidationResult indicating if summary is valid
        """
        if not messages:
            return ValidationResult(is_valid=True)

        # Combine all message content
        original_text = "\n".join(m.content for m in messages)

        # Extract entities and decisions from original
        original_entities = self.extract_entities(original_text)
        original_decisions = self.extract_decisions(original_text)

        # Extract from summary
        summary_entities = self.extract_entities(summary)
        summary_lower = summary.lower()

        # Check for missing entities
        missing_entities = []
        for entity in original_entities:
            # Check if entity appears in summary (case-insensitive for paths)
            if entity not in summary and entity.lower() not in summary_lower:
                missing_entities.append(entity)

        # Check for missing decisions
        missing_decisions = []
        for decision in original_decisions:
            # Check if key decision concept appears in summary
            decision_words = set(word.lower() for word in re.findall(r'\w+', decision))
            decision_keywords = decision_words & set(self.DECISION_KEYWORDS)

            # At least one decision keyword and some context should be present
            if decision_keywords:
                found = False
                for keyword in decision_keywords:
                    if keyword in summary_lower:
                        # Check if related context is also present
                        context_words = decision_words - set(self.DECISION_KEYWORDS)
                        significant_context = [w for w in context_words if len(w) > 4]
                        if any(w in summary_lower for w in significant_context):
                            found = True
                            break
                        elif not significant_context:
                            # No significant context to check
                            found = True
                            break

                if not found:
                    missing_decisions.append(decision)

        is_valid = len(missing_entities) == 0 and len(missing_decisions) == 0

        return ValidationResult(
            is_valid=is_valid,
            missing_entities=missing_entities,
            missing_decisions=missing_decisions,
        )
