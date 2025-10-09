# Gemini Batch Processing Fix - Complete Summary

## Problem Solved

The Gemini batch API requests were **failing with a 0.3 second timeout error**. The root cause was that the Google genai SDK expects timeout values in **milliseconds**, but we were passing them in **seconds**.

## What Was Fixed

### 1. Timeout Configuration Fix (`src/folios_v2/providers/gemini/batch.py`)

**Problem**:
```python
# Before - timeout of 300 seconds was interpreted as 300 milliseconds = 0.3 seconds
def _client(self) -> genai.Client:
    return genai.Client(api_key=self._api_key, http_options={"timeout": self._request_timeout})
```

**Solution**:
```python
# After - convert seconds to milliseconds
def _client(self) -> genai.Client:
    # Google genai SDK expects timeout in milliseconds, not seconds
    timeout_ms = int(self._request_timeout * 1000)
    return genai.Client(api_key=self._api_key, http_options={"timeout": timeout_ms})
```

**Also increased default timeout from 300s to 600s** (10 minutes) to give batch submission more time.

## New Scripts Created

### 1. **test_gemini_submit.py** - Submit Individual Batch Jobs
```bash
uv run python scripts/test_gemini_submit.py
```

This script:
- ✅ Takes one pending Gemini request
- ✅ Submits it to Gemini Batch API
- ✅ Stores the provider job ID immediately (no waiting for completion)
- ✅ Updates request/task status to RUNNING

**Output Example**:
```
Processing Gemini request: 56c8d4aa-ce03-464a-9c5c-5eadad682592
[1/3] Serializing...
✓ Payload created

[2/3] Submitting batch...
✓ Batch submitted successfully!
  Provider Job ID: batches/8s0ts89fd2d15ixi7nnyl9wjffbikf20ozkk

[3/3] Storing job ID...
✓ Job ID and status stored successfully!
```

### 2. **check_gemini_batch.py** - Check Status of Batch Jobs
```bash
# Show all local Gemini batch tasks
uv run python scripts/check_gemini_batch.py local

# Check status of all running jobs (queries Gemini API)
uv run python scripts/check_gemini_batch.py status

# Check specific job
uv run python scripts/check_gemini_batch.py status batches/8s0ts89fd2d15ixi7nnyl9wjffbikf20ozkk

# Get detailed job info
uv run python scripts/check_gemini_batch.py details batches/8s0ts89fd2d15ixi7nnyl9wjffbikf20ozkk
```

### 3. **harvest_gemini_batches.py** - Harvest Completed Batches
```bash
uv run python scripts/harvest_gemini_batches.py
```

This script:
- ✅ Finds all RUNNING Gemini batch jobs
- ✅ Polls their status via Gemini API
- ✅ For completed jobs:
  - Downloads results
  - Parses JSON responses
  - Saves parsed.json
  - Updates task/request to SUCCEEDED
- ✅ Shows summary of completed vs still-running jobs

## Workflow for Gemini Batches

### Step 1: Submit Batches
```bash
# Submit one request
uv run python scripts/test_gemini_submit.py

# Or submit multiple (modify script to loop through pending requests)
```

### Step 2: Wait (Gemini batches take 24+ hours)
During this time, the batch jobs are processing in Google's infrastructure.

### Step 3: Check Status (Optional)
```bash
# Check what's running
uv run python scripts/check_gemini_batch.py status
```

Example output:
```
┏━━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━┳━━━━━━┳━━━━━━━━┓
┃ Local ID    ┃ Provider    ┃ Local State ┃ Remote     ┃ Total ┃ Done ┃ Failed ┃
┃             ┃ Job ID      ┃             ┃ State      ┃       ┃      ┃        ┃
┡━━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━╇━━━━━━╇━━━━━━━━┩
│ 9583a605-9… │ batches/8s… │ running     │ JOB_STATE… │ 0     │ 0    │ 0      │
└─────────────┴─────────────┴─────────────┴────────────┴───────┴──────┴────────┘
```

### Step 4: Harvest Results (After 24+ hours)
```bash
# Run daily to collect completed batches
uv run python scripts/harvest_gemini_batches.py
```

Example output when job completes:
```
  • Task 9583a605-9c86-42cd-b0ec-
    Job ID: batches/8s0ts89fd2d15ixi7nnyl9wjffbikf20ozkk
    Status: completed
    Progress: 1/1
    ✓ Job completed! Downloading results...
    ✓ Downloaded to: artifacts/.../gemini_batch_results.jsonl
    ✓ Parsed results saved to: artifacts/.../parsed.json
    ✓ Task marked as SUCCEEDED

Harvest Summary:
  Completed: 1
  Still Running: 0
```

## Testing Results

### ✅ Successful Test Run

**Date**: October 9, 2025
**Request ID**: `56c8d4aa-ce03-464a-9c5c-5eadad682592`
**Task ID**: `9583a605-9c86-42cd-b0ec-a52e1fb5b14d`
**Provider Job ID**: `batches/8s0ts89fd2d15ixi7nnyl9wjffbikf20ozkk`

1. **Submission**: ✅ SUCCESS (previously failed with timeout)
2. **Job ID Storage**: ✅ Stored in database
3. **Status Polling**: ✅ Working (job is processing)
4. **Harvest Script**: ✅ Ready to collect results when job completes

## Key Differences from OpenAI Batches

| Aspect | OpenAI | Gemini |
|--------|--------|--------|
| **Completion Time** | Minutes to hours | 24+ hours |
| **Timeout Setting** | Seconds | Milliseconds ⚠️ |
| **Workflow** | Synchronous polling OK | Async (submit → poll later) |
| **Status Check** | `check_batch_status.py` | `check_gemini_batch.py` |
| **Harvesting** | `harvest.py` (all providers) | `harvest_gemini_batches.py` (Gemini-specific) |

## Automation Setup

### Option 1: Cron Job (Run Daily)
```bash
# Add to crontab
0 6 * * * cd /Users/arun/apps/folios-v2 && uv run python scripts/harvest_gemini_batches.py >> logs/gemini_harvest.log 2>&1
```

### Option 2: Manual Check
```bash
# Check status before harvesting
uv run python scripts/check_gemini_batch.py status

# If completed jobs exist, harvest them
uv run python scripts/harvest_gemini_batches.py
```

## File Locations

### Scripts
- `/scripts/test_gemini_submit.py` - Submit individual batches
- `/scripts/check_gemini_batch.py` - Check batch status
- `/scripts/harvest_gemini_batches.py` - Harvest completed batches

### Source Code Fix
- `/src/folios_v2/providers/gemini/batch.py` - Fixed timeout conversion

### Documentation
- `/docs/GEMINI_BATCH_FIX_SUMMARY.md` - This file
- `/GEMINI_BATCH_TIMEOUT_ANALYSIS.md` - Detailed technical analysis

### Artifacts (Per Request/Task)
- `artifacts/{request_id}/{task_id}/gemini_payload.json` - Input payload
- `artifacts/{request_id}/{task_id}/gemini_batch_results.jsonl` - Raw results from Gemini
- `artifacts/{request_id}/{task_id}/parsed.json` - Parsed investment analysis

## Troubleshooting

### Issue: "ReadTimeout: The read operation timed out"
**Cause**: Old code before the fix
**Solution**: Ensure the fix in `batch.py` is applied (converts timeout to milliseconds)

### Issue: Job stuck in PENDING state
**Possible Causes**:
1. Job was submitted before the fix → Resubmit using `test_gemini_submit.py`
2. Gemini API is slow → Normal, wait 24-48 hours
3. Actual error in Gemini → Check with `check_gemini_batch.py details <job_id>`

### Issue: Can't find provider_job_id
**Cause**: Looking at wrong database column
**Solution**: Job ID is stored in `execution_tasks.payload` JSON column at path `$.provider_job_id`

## Next Steps

1. **Submit remaining pending Gemini requests**
   - Run `test_gemini_submit.py` for each pending request
   - Or modify script to loop through all pending requests

2. **Set up daily harvesting**
   - Add cron job or scheduler
   - Harvest at least once per day to collect completed batches

3. **Monitor results**
   - Check `scripts/check_gemini_batch.py status` daily
   - Review harvested results in `artifacts/*/parsed.json`

## Summary

✅ **Fixed**: Timeout configuration (0.3s → 600s)
✅ **Created**: Batch submission script
✅ **Created**: Status checking script
✅ **Created**: Harvesting script for completed jobs
✅ **Tested**: Successfully submitted and tracking one batch job

**Current Status**: Batch job `batches/8s0ts89fd2d15ixi7nnyl9wjffbikf20ozkk` is processing in Gemini's infrastructure. Results will be available in ~24 hours.
