# Gemini Batch Processing Timeout Analysis

> **Status (2025-10-09):** Fixed. See `docs/GEMINI_BATCH_FIX_SUMMARY.md` for the
> implemented solution. This analysis is retained for historical debugging
> context.

## Issue Summary
The Gemini batch request harvesting was **failing due to HTTP timeout errors** during the batch submission phase.

## Error Details

### Primary Error
```
ReadTimeout: The read operation timed out
```

### Root Cause
The HTTP client is using an extremely short timeout of **0.3 seconds** (300ms) instead of the configured 300 seconds (5 minutes).

### Error Stack Trace Location
```
httpcore._sync.connection_pool.py:256
↓
httpx._transports.default.py:250
↓
google.genai._api_client.py:1127 (_request_once)
```

### Timeout Configuration Found in Stack Trace
```python
timeouts = {'connect': 0.3, 'read': 0.3, 'write': 0.3, 'pool': 0.3}
timeout = 0.3  # ← This is the problem!
```

## Expected vs Actual Behavior

### Expected
- `GeminiBatchExecutor` is initialized with `request_timeout=300.0` (5 minutes)
- Located in: `src/folios_v2/providers/gemini/batch.py:131-137`

### Actual (pre-fix)
- Google genai client used `timeout=0.3` seconds
- This timeout was too short for any meaningful API request to complete

## Request Being Processed

### Request Details
- **Request ID**: `56c8d4aa-ce03-464a-9c5c-5eadad682592`
- **Strategy ID**: `877be608-8547-4656-9d16-0f395df434dd`
- **Provider**: Gemini (BATCH mode)
- **Request Type**: RESEARCH
- **Lifecycle State**: PENDING

### Batch Job Details
- **Display Name**: `folios-batch-9583a605-9c86-42cd-b0ec-a52e1fb5b14d`
- **Model**: `models/gemini-2.5-pro`
- **Endpoint**: `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:batchGenerateContent`

## Failure Point

The timeout occurs during the **SUBMIT** phase of batch processing:

1. ✅ **Serialization** - Payload creation succeeds
2. ❌ **Submission** - HTTP POST to Gemini API times out after 0.3s
3. ⏸️ **Polling** - Never reached
4. ⏸️ **Download** - Never reached

### Code Flow
```python
# harvest.py:37-38
await plugin.serializer.serialize(ctx)  # ✅ Success
outcome = await container.batch_runtime.run(plugin, ctx)  # ❌ Timeout here

# batch_runtime.py:32-33
submit_result = await plugin.batch_executor.submit(ctx, payload)  # ❌ Fails here

# gemini/batch.py:143-194 (submit method)
# The _submit() function calls client.batches.create()
# This is where the timeout occurs
```

## Investigation Needed

### 1. Google genai Client Configuration
The `google.genai.Client` is initialized in `GeminiBatchExecutor._client()`:

```python
# batch.py:140-141
def _client(self) -> genai.Client:
    return genai.Client(api_key=self._api_key, http_options={"timeout": self._request_timeout})
```

**Question**: Why is `http_options={"timeout": 300.0}` being ignored or overridden to 0.3?

### 2. Possible Causes

#### Theory A: Unit Conversion Bug
- 300.0 is being interpreted as 300 milliseconds instead of seconds?
- But the stack trace shows 0.3, not 300

#### Theory B: Default Override
- The google-genai SDK might have a default timeout that overrides the http_options
- The SDK might be using 0.3s as a default read timeout

#### Theory C: HTTP Options Format
- The `http_options` parameter might need a different format
- Perhaps it should be `{"read": 300.0}` instead of `{"timeout": 300.0}`

#### Theory D: Nested Timeout Configuration
- The google-genai client might require explicit timeouts at multiple levels:
  - Transport level
  - Connection level
  - Request level

## Recommended Solutions

### Solution 1: Debug Current Configuration
Add logging to see what timeout is actually being passed:

```python
def _client(self) -> genai.Client:
    client = genai.Client(api_key=self._api_key, http_options={"timeout": self._request_timeout})
    # Log the actual httpx client configuration
    logger.debug(f"Created genai client with timeout={self._request_timeout}")
    return client
```

### Solution 2: Try Alternative Timeout Configuration
Based on httpx/httpcore patterns, try:

```python
def _client(self) -> genai.Client:
    http_options = {
        "timeout": {
            "connect": self._request_timeout,
            "read": self._request_timeout,
            "write": self._request_timeout,
            "pool": self._request_timeout,
        }
    }
    return genai.Client(api_key=self._api_key, http_options=http_options)
```

### Solution 3: Create Custom HTTP Client
If http_options doesn't work, create a custom httpx client:

```python
import httpx

def _client(self) -> genai.Client:
    custom_http_client = httpx.Client(
        timeout=httpx.Timeout(
            connect=self._request_timeout,
            read=self._request_timeout,
            write=self._request_timeout,
            pool=self._request_timeout,
        )
    )
    return genai.Client(
        api_key=self._api_key,
        http_client=custom_http_client
    )
```

### Solution 4: Increase Default Timeout
As a quick fix, try increasing the default from 300s to something larger, or check if there's a multiplier issue:

```python
def __init__(
    self,
    *,
    api_key: str,
    model: str = "gemini-2.5-pro",
    request_timeout: float = 600.0,  # Try 10 minutes instead of 5
) -> None:
```

## Impact

### Current State
- **0% success rate** for Gemini batch harvesting
- All Gemini batch requests are stuck in PENDING state
- No timeouts or failures are being recorded in the database (the error occurs before state updates)

### Batch Runtime Behavior
- The `BatchRuntime` expects to submit, then poll up to 60 times at 15-second intervals (15 minutes total)
- But it never gets past the submit phase due to the 0.3s timeout

## Next Steps

1. ✅ **Document the issue** (this file)
2. ⬜ Check google-genai SDK documentation for proper timeout configuration
3. ⬜ Test Solution 2 (structured timeout configuration)
4. ⬜ Add debug logging to see actual client configuration
5. ⬜ Verify the fix with a single harvest attempt
6. ⬜ Update all pending Gemini requests after fix is confirmed

## Related Files

- `/src/folios_v2/providers/gemini/batch.py:123-194` - GeminiBatchExecutor.submit()
- `/src/folios_v2/runtime/batch.py:22-51` - BatchRuntime.run()
- `/scripts/harvest.py:26-57` - Harvest process logic
- `/src/folios_v2/container.py:78-85` - Gemini plugin initialization

## Additional Notes

The error message shows the request made it to Google's servers:
```
https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:batchGenerateContent
```

This means:
- ✅ API key is valid
- ✅ Network connectivity is working
- ✅ Request payload is properly formatted
- ❌ The client disconnects before Google can respond

The 0.3 second timeout is simply too short to:
1. Establish HTTPS connection
2. Send the batch request payload
3. **Wait for Google to validate and queue the batch job**
4. Receive the batch job ID response

Batch job creation is not instantaneous - Google needs time to validate the payload and create the job record.
