"""
Feedback Capture Module for WF-034 Phase 3

Provides structured feedback collection for workflow adherence and experience.
Supports both interactive and automated feedback capture modes.
"""

import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, List


class FeedbackCapture:
    """
    Captures structured feedback about workflow adherence and experience.

    Feedback is saved to .workflow_feedback.jsonl in JSONL format for
    easy aggregation across workflows and repositories.
    """

    def __init__(self, feedback_file: Optional[Path] = None):
        """
        Initialize FeedbackCapture.

        Args:
            feedback_file: Path to feedback file (default: .workflow_feedback.jsonl)
        """
        if feedback_file is None:
            feedback_file = Path('.workflow_feedback.jsonl')

        self.feedback_file = Path(feedback_file)

    def get_interactive_questions(self) -> List[Dict[str, str]]:
        """
        Get structured interactive questions for feedback capture.

        Returns:
            List of question dictionaries with 'prompt' and 'field' keys
        """
        return [
            {
                'field': 'multi_agents_used',
                'prompt': 'Did you use multi-agents / parallel execution? (yes/no/not-recommended)',
                'type': 'choice',
                'choices': ['yes', 'no', 'not-recommended']
            },
            {
                'field': 'what_went_well',
                'prompt': 'What went well during this workflow? (1-2 sentences)',
                'type': 'text'
            },
            {
                'field': 'challenges',
                'prompt': 'What challenges did you encounter? (1-2 sentences)',
                'type': 'text'
            },
            {
                'field': 'improvements',
                'prompt': 'What could be improved for future workflows? (1-2 sentences)',
                'type': 'text'
            },
            {
                'field': 'reviews_performed',
                'prompt': 'Did you run third-party model reviews? (yes/no/deferred)',
                'type': 'choice',
                'choices': ['yes', 'no', 'deferred']
            },
            {
                'field': 'notes',
                'prompt': 'Additional notes (optional)',
                'type': 'text'
            }
        ]

    def create_feedback(
        self,
        workflow_id: str,
        task: str,
        multi_agents_used: bool,
        what_went_well: str,
        challenges: str,
        improvements: str,
        reviews_performed: bool,
        notes: str = ""
    ) -> Dict:
        """
        Create a feedback dictionary with all required fields.

        Args:
            workflow_id: Workflow ID
            task: Task description
            multi_agents_used: Whether multiple agents were used
            what_went_well: What went well during workflow
            challenges: Challenges encountered
            improvements: Suggested improvements
            reviews_performed: Whether third-party reviews were performed
            notes: Additional notes

        Returns:
            Dictionary with feedback data matching schema
        """
        return {
            'workflow_id': workflow_id,
            'task': task,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'multi_agents_used': multi_agents_used,
            'what_went_well': what_went_well,
            'challenges': challenges,
            'improvements': improvements,
            'reviews_performed': reviews_performed,
            'notes': notes
        }

    def capture_feedback(
        self,
        workflow_id: str,
        task: str,
        multi_agents_used: bool,
        what_went_well: str,
        challenges: str,
        improvements: str,
        reviews_performed: bool,
        notes: str = ""
    ) -> None:
        """
        Capture feedback and write to JSONL file.

        Args:
            workflow_id: Workflow ID
            task: Task description
            multi_agents_used: Whether multiple agents were used
            what_went_well: What went well during workflow
            challenges: Challenges encountered
            improvements: Suggested improvements
            reviews_performed: Whether third-party reviews were performed
            notes: Additional notes
        """
        feedback = self.create_feedback(
            workflow_id=workflow_id,
            task=task,
            multi_agents_used=multi_agents_used,
            what_went_well=what_went_well,
            challenges=challenges,
            improvements=improvements,
            reviews_performed=reviews_performed,
            notes=notes
        )

        # Append to JSONL file
        with open(self.feedback_file, 'a') as f:
            json.dump(feedback, f)
            f.write('\n')

    def capture_feedback_interactive(self) -> Optional[Dict]:
        """
        Capture feedback interactively by prompting user for answers.

        Returns:
            Feedback dictionary or None if user cancels
        """
        print("\n" + "=" * 60)
        print("Workflow Feedback Collection")
        print("=" * 60)
        print("Please answer the following questions about your workflow experience.")
        print("Press Ctrl+C to cancel.\n")

        answers = {}
        questions = self.get_interactive_questions()

        try:
            for question in questions:
                field = question['field']
                prompt = question['prompt']
                q_type = question.get('type', 'text')

                if q_type == 'choice':
                    choices = question.get('choices', [])
                    prompt_with_choices = f"{prompt} [{'/'.join(choices)}]: "
                    while True:
                        answer = input(prompt_with_choices).strip().lower()
                        if answer in choices or answer == '':
                            if answer == '':
                                # Use sensible defaults
                                if field == 'multi_agents_used':
                                    answer = 'no'
                                elif field == 'reviews_performed':
                                    answer = 'no'
                            break
                        print(f"Please enter one of: {', '.join(choices)}")

                    # Convert to boolean for boolean fields
                    if field == 'multi_agents_used':
                        answers[field] = (answer == 'yes')
                    elif field == 'reviews_performed':
                        answers[field] = (answer == 'yes')
                    else:
                        answers[field] = answer
                else:
                    answer = input(f"{prompt}: ").strip()
                    answers[field] = answer

            print("\n" + "=" * 60)
            print("Feedback collected successfully!")
            print("=" * 60 + "\n")

            return answers

        except KeyboardInterrupt:
            print("\n\nFeedback collection cancelled.")
            return None

    def load_all_feedback(self) -> List[Dict]:
        """
        Load all feedback entries from the JSONL file.

        Returns:
            List of feedback dictionaries
        """
        if not self.feedback_file.exists():
            return []

        feedback_entries = []
        with open(self.feedback_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        feedback_entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        # Skip malformed lines
                        continue

        return feedback_entries
