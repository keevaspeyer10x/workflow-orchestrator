# PRD Task: task-1-pattern-schema

## Instructions
# PRD Task: task-1-pattern-schema

## Description
Create the data models for conflict pattern memory in src/learning/pattern_schema.py

Models to create:
- ConflictPattern: Records a conflict pattern with hash, type, files, resolution
- PatternMatch: Result of matching a conflict to known patterns
- ResolutionOutcome: Success/failure record for a pattern application

Key fields for ConflictPattern:
- pattern_hash: str (computed from conflict characteristics)
- conflict_type: str (textual, semantic, dependency, etc.)
- files_involved: list[str]
- intent_categories: list[str]
- resolution_strategy: str (agent1_primary, merge, etc.)
- success_rate: float (0.0 to 1.0)
- last_used: datetime
- use_count: int

Write tests in tests/learning/test_pattern_schema.py


## Branch
Create your work on branch: `claude/task-1-pattern-schema-{worker_id}`

## Requirements
1. Implement the feature/fix described above
2. Write tests for your changes
3. Ensure all tests pass
4. Commit with clear messages

## When Complete
- Commit all changes
- Push your branch
- The orchestrator will handle merging

## PRD Context
This task is part of PRD: phase7-learning-optimization
Dependencies: None


## Important
- Create a new branch for this work: `claude/task-1-pattern-schema-local-6421b204`
- Commit your changes with clear messages
- Run tests before completing
- Output the branch name and commit SHA when done
