"""List Gemini batch jobs."""

import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai

# Load .env file
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
if not api_key:
    print("Error: GEMINI_API_KEY or GOOGLE_API_KEY not found in environment")
    exit(1)

client = genai.Client(api_key=api_key, http_options={"timeout": 60.0})

print("Fetching Gemini batch jobs...")
try:
    batches = list(client.batches.list())

    if not batches:
        print("No batch jobs found")
    else:
        print(f"\nFound {len(batches)} batch job(s):\n")
        for job in batches:
            print(f"Name: {job.name}")
            print(f"  Display Name: {getattr(job, 'display_name', 'N/A')}")
            print(f"  State: {getattr(getattr(job, 'state', None), 'name', 'UNKNOWN')}")
            print(f"  Create Time: {getattr(job, 'create_time', 'N/A')}")

            counts = getattr(job, 'batch_stats', None)
            if counts:
                print(f"  Requests: {getattr(counts, 'total_requests', 0)} total, "
                      f"{getattr(counts, 'completed_requests', 0)} completed, "
                      f"{getattr(counts, 'failed_requests', 0)} failed")
            print()

except Exception as e:
    print(f"Error listing batches: {e}")
    import traceback
    traceback.print_exc()
