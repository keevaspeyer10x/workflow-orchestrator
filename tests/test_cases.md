# V4.2 Phase 2: Token Budget System - Test Cases

## TokenCounter Tests

### ClaudeTokenCounter
| ID | Test Case | Expected Result |
|----|-----------|-----------------|
| TC-01 | count() with valid text | Returns accurate token count via API |
| TC-02 | count() when API unavailable | Falls back to EstimationTokenCounter |
| TC-03 | count_messages() with message array | Returns count including overhead |
| TC-04 | count() with empty string | Returns 0 |

### OpenAITokenCounter
| ID | Test Case | Expected Result |
|----|-----------|-----------------|
| TC-05 | count() matches tiktoken | Token count matches direct tiktoken call |
| TC-06 | count_messages() includes overhead | Count includes 3 tokens/msg + 3 reply |
| TC-07 | count() with unicode | Handles unicode correctly |

### EstimationTokenCounter
| ID | Test Case | Expected Result |
|----|-----------|-----------------|
| TC-08 | count() uses ~4 chars/token | len(text) / 4 rounded |
| TC-09 | count_messages() with overhead | Includes message overhead estimate |

## AtomicBudgetTracker Tests

### Reserve Operations
| ID | Test Case | Expected Result |
|----|-----------|-----------------|
| TC-10 | reserve() within budget | Returns success with reservation_id |
| TC-11 | reserve() exceeding budget | Returns failure with reason |
| TC-12 | reserve() at exact limit | Returns success |
| TC-13 | Multiple reserves totaling over limit | Last reserve fails |

### Commit Operations
| ID | Test Case | Expected Result |
|----|-----------|-----------------|
| TC-14 | commit() valid reservation | Updates used, clears reservation |
| TC-15 | commit() invalid reservation | Raises ValueError |
| TC-16 | commit() with different actual tokens | Uses actual, not reserved |

### Rollback Operations
| ID | Test Case | Expected Result |
|----|-----------|-----------------|
| TC-17 | rollback() valid reservation | Releases reserved tokens |
| TC-18 | rollback() invalid reservation | No error (idempotent) |

### Concurrency Tests
| ID | Test Case | Expected Result |
|----|-----------|-----------------|
| TC-19 | Concurrent reserves same budget | All succeed or fail atomically |
| TC-20 | Concurrent reserves different budgets | All succeed independently |
| TC-21 | Reserve during commit | No race condition |

## Budget Events Tests

| ID | Test Case | Expected Result |
|----|-----------|-----------------|
| TC-22 | BUDGET_CREATED on init | Event recorded with limit |
| TC-23 | TOKENS_RESERVED on reserve | Event includes reservation_id |
| TC-24 | TOKENS_COMMITTED on commit | Event includes actual_tokens |
| TC-25 | TOKENS_RELEASED on rollback | Event includes released_tokens |
| TC-26 | BUDGET_EXHAUSTED at limit | Event when budget exhausted |

## Integration Tests

| ID | Test Case | Expected Result |
|----|-----------|-----------------|
| TC-27 | Full reserve -> commit cycle | Tokens moved to used |
| TC-28 | Full reserve -> rollback cycle | Tokens returned to available |
| TC-29 | Reservation timeout | Reserved tokens released after timeout |
| TC-30 | Budget status accuracy | Status reflects all operations |
| TC-31 | Persist across restart | Budget survives process restart |

## Acceptance Criteria Mapping

| Criterion | Test Cases |
|-----------|------------|
| Token counting accurate within 5% per provider | TC-01, TC-05, TC-08 |
| Concurrent updates don't cause overdraft | TC-19, TC-20, TC-21 |
| Reservation timeout releases tokens | TC-29 |
| Budget events recorded | TC-22 through TC-26 |
