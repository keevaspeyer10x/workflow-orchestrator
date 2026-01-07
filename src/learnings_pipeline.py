"""
WF-007: Learnings to Roadmap Pipeline

Automatically suggest roadmap items based on captured learnings
during the LEARN phase.
"""

import re
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class RoadmapSuggestion:
    """A suggested roadmap item extracted from learnings."""
    description: str
    source_text: str
    prefix: Optional[str] = None
    category: Optional[str] = None


# Patterns that indicate actionable learnings
ACTIONABLE_PATTERNS = [
    # "should X" patterns
    (r"should\s+(\w+(?:\s+\w+){0,10})", "should"),
    # "next time X" patterns
    (r"next\s+time[,]?\s+(?:we\s+)?(?:should\s+)?(\w+(?:\s+\w+){0,10})", "next_time"),
    # "need to X" patterns
    (r"need\s+to\s+(\w+(?:\s+\w+){0,10})", "need_to"),
    # "could improve X" patterns
    (r"could\s+improve\s+(\w+(?:\s+\w+){0,10})", "improve"),
    # "would benefit from X" patterns
    (r"would\s+benefit\s+from\s+(\w+(?:\s+\w+){0,10})", "benefit"),
]

# Keywords for categorization
CATEGORY_KEYWORDS = {
    "CORE": ["core", "engine", "api", "model", "provider", "function", "feature"],
    "WF": ["workflow", "phase", "process", "step", "summary", "approval"],
    "ARCH": ["refactor", "extract", "duplicate", "utility", "pattern", "architecture"],
    "SEC": ["security", "auth", "permission", "credential", "secret", "encrypt"],
    "VV": ["visual", "ui", "verification", "screenshot", "display"],
}


def analyze_learnings(learnings_file: Path) -> list[RoadmapSuggestion]:
    """
    Parse a learnings file for actionable patterns.

    Args:
        learnings_file: Path to LEARNINGS.md file

    Returns:
        List of RoadmapSuggestion objects
    """
    if not learnings_file.exists():
        logger.debug(f"Learnings file not found: {learnings_file}")
        return []

    try:
        content = learnings_file.read_text()
    except Exception as e:
        logger.warning(f"Failed to read learnings file: {e}")
        return []

    if not content.strip():
        return []

    suggestions = []
    seen_descriptions = set()

    # Process each line
    lines = content.split("\n")
    for line in lines:
        line_lower = line.lower()

        # Check each actionable pattern
        for pattern, pattern_type in ACTIONABLE_PATTERNS:
            matches = re.finditer(pattern, line_lower)
            for match in matches:
                # Extract the action/description
                action = match.group(1).strip()

                # Skip very short matches
                if len(action) < 5:
                    continue

                # Create description
                description = _create_description(action, pattern_type)

                # Deduplicate
                desc_key = description.lower()[:50]
                if desc_key in seen_descriptions:
                    continue
                seen_descriptions.add(desc_key)

                suggestion = RoadmapSuggestion(
                    description=description,
                    source_text=line.strip(),
                )

                suggestions.append(suggestion)

    return suggestions


def _create_description(action: str, pattern_type: str) -> str:
    """Create a description from the extracted action."""
    # Capitalize first letter
    action = action.strip()
    if action:
        action = action[0].upper() + action[1:]

    # Add context based on pattern type
    if pattern_type == "should":
        return f"{action}"
    elif pattern_type == "next_time":
        return f"{action}"
    elif pattern_type == "need_to":
        return f"{action}"
    elif pattern_type == "improve":
        return f"Improve {action}"
    elif pattern_type == "benefit":
        return f"Add {action}"

    return action


def categorize_suggestion(suggestion: RoadmapSuggestion) -> RoadmapSuggestion:
    """
    Assign a category prefix to a suggestion.

    Args:
        suggestion: The suggestion to categorize

    Returns:
        The suggestion with prefix set
    """
    text_to_check = f"{suggestion.description} {suggestion.source_text}".lower()

    # Find matching category
    best_match = None
    best_score = 0

    for prefix, keywords in CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_to_check)
        if score > best_score:
            best_score = score
            best_match = prefix

    # Default to CORE if no match
    suggestion.prefix = best_match or "CORE"
    return suggestion


def format_roadmap_entry(suggestion: RoadmapSuggestion, id_number: int) -> str:
    """
    Format a suggestion as a markdown roadmap entry.

    Args:
        suggestion: The suggestion to format
        id_number: The ID number for this entry

    Returns:
        Markdown formatted roadmap entry
    """
    prefix = suggestion.prefix or "CORE"
    id_str = f"{prefix}-{id_number:03d}"

    entry = f"""### {id_str}: {suggestion.description}
**Status:** Suggested
**Complexity:** TBD
**Priority:** TBD
**Source:** LEARNINGS.md

> {suggestion.source_text}

**Description:** {suggestion.description}

**Tasks:**
- [ ] Review and refine this suggestion
- [ ] Estimate complexity
- [ ] Prioritize against other items
"""
    return entry


def suggest_from_learnings(
    learnings_file: Path,
    roadmap_file: Path,
    auto_add: bool = False,
) -> list[RoadmapSuggestion]:
    """
    Analyze learnings and optionally add suggestions to roadmap.

    Args:
        learnings_file: Path to LEARNINGS.md
        roadmap_file: Path to ROADMAP.md
        auto_add: If True, append suggestions to roadmap

    Returns:
        List of suggestions found
    """
    suggestions = analyze_learnings(learnings_file)

    if not suggestions:
        return []

    # Categorize all suggestions
    for suggestion in suggestions:
        categorize_suggestion(suggestion)

    if auto_add and roadmap_file.exists():
        # Find the next available ID
        roadmap_content = roadmap_file.read_text()
        next_id = _find_next_id(roadmap_content)

        # Format and append suggestions
        new_entries = []
        for i, suggestion in enumerate(suggestions):
            entry = format_roadmap_entry(suggestion, next_id + i)
            new_entries.append(entry)

        if new_entries:
            separator = "\n\n## Suggested from Learnings\n\n"
            if "## Suggested from Learnings" not in roadmap_content:
                roadmap_content += separator

            roadmap_content += "\n---\n\n".join(new_entries)

            roadmap_file.write_text(roadmap_content)
            logger.info(f"Added {len(new_entries)} suggestions to roadmap")

    return suggestions


def _find_next_id(roadmap_content: str) -> int:
    """Find the next available ID number in the roadmap."""
    # Find all existing IDs like CORE-001, WF-005, etc.
    pattern = r"[A-Z]+-(\d{3})"
    matches = re.findall(pattern, roadmap_content)

    if matches:
        max_id = max(int(m) for m in matches)
        return max_id + 1

    return 1


def format_suggestions_prompt(suggestions: list[RoadmapSuggestion]) -> str:
    """Format suggestions for interactive user prompt."""
    lines = [
        "=" * 60,
        "LEARNINGS CAPTURED",
        "=" * 60,
        "",
    ]

    for i, suggestion in enumerate(suggestions, 1):
        lines.append(f"{i}. \"{suggestion.source_text}\"")
        lines.append(f"   -> Suggested: {suggestion.prefix}-XXX: {suggestion.description}")
        lines.append("")

    lines.extend([
        "Add these to ROADMAP.md? [y/N/edit]",
        "=" * 60,
    ])

    return "\n".join(lines)
