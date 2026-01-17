# V4.2 Phase 3: LLM Call Interceptor - Test Cases

## 1. LLMCallWrapper Tests

### 1.1 Successful Call with Budget Tracking
- **Setup:** Create budget with 10,000 tokens, mock LLM to return 500 tokens used
- **Action:** Call wrapper with request
- **Assert:**
  - Budget reserved before call
  - LLM called with correct request
  - Budget committed with actual usage (500)
  - Response returned correctly

### 1.2 Budget Exhaustion Blocks Call
- **Setup:** Create budget with 100 tokens, request estimated at 500 tokens
- **Action:** Call wrapper
- **Assert:**
  - BudgetExhaustedError raised
  - No LLM call made
  - No budget changes

### 1.3 Rollback on API Error
- **Setup:** Create budget with 10,000 tokens, mock LLM to raise APIError
- **Action:** Call wrapper
- **Assert:**
  - Reservation created
  - LLM called and failed
  - Reservation rolled back
  - Budget unchanged

### 1.4 Retry with Same Reservation
- **Setup:** Create budget, mock LLM to fail first call, succeed second
- **Action:** Call wrapper with retries enabled
- **Assert:**
  - Single reservation created
  - Two LLM calls made (retry)
  - Reservation committed on success
  - Budget reflects single usage

### 1.5 Streaming Call Budget Tracking
- **Setup:** Create budget, mock streaming LLM response
- **Action:** Call streaming wrapper, consume all chunks
- **Assert:**
  - Budget reserved before stream starts
  - All chunks received
  - Budget committed at stream end

## 2. Provider Adapter Tests

### 2.1 Anthropic Token Extraction
- **Setup:** Mock Anthropic response with usage object
- **Action:** Call adapter.extract_usage()
- **Assert:**
  - Returns correct input_tokens
  - Returns correct output_tokens

### 2.2 OpenAI Token Extraction
- **Setup:** Mock OpenAI response with usage object
- **Action:** Call adapter.extract_usage()
- **Assert:**
  - Returns correct prompt_tokens as input
  - Returns correct completion_tokens as output

### 2.3 Missing Usage Fallback
- **Setup:** Mock response without usage field
- **Action:** Call adapter.extract_usage()
- **Assert:**
  - Falls back to estimation
  - Warning logged

### 2.4 Streaming Response Handling
- **Setup:** Mock streaming response with chunks
- **Action:** Iterate adapter.call_streaming()
- **Assert:**
  - All chunks yielded
  - Final chunk includes usage

## 3. Integration Tests

### 3.1 End-to-End with Mocked LLM
- **Setup:** Full interceptor stack with mocked adapter
- **Action:** Execute multiple calls
- **Assert:**
  - Budget tracks correctly across calls
  - Reservation IDs unique
  - Usage events recorded

### 3.2 Budget Depletion Over Multiple Calls
- **Setup:** Budget of 1000 tokens, calls using ~300 each
- **Action:** Make 4 calls
- **Assert:**
  - First 3 calls succeed
  - 4th call blocked (budget exhausted)

### 3.3 Concurrent Calls
- **Setup:** Budget of 1000 tokens
- **Action:** Launch 3 concurrent calls (~400 tokens each)
- **Assert:**
  - At most 2 calls succeed
  - Third blocked or succeeds based on timing
  - No budget overrun

## 4. Retry Logic Tests

### 4.1 Exponential Backoff
- **Setup:** Mock LLM to fail 2 times then succeed
- **Action:** Call with retry
- **Assert:**
  - Delays increase exponentially
  - Success on 3rd attempt

### 4.2 Max Retries Exceeded
- **Setup:** Mock LLM to always fail
- **Action:** Call with max_retries=3
- **Assert:**
  - 3 attempts made
  - Final error raised
  - Budget rolled back
