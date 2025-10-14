"""Execute recommendations for all successful strategies."""

from __future__ import annotations

import subprocess
from pathlib import Path

# Strategies with recommendations (request_id, strategy_id, strategy_name, rec_count)
STRATEGIES_WITH_RECS = [
    ("f25fbcea-5554-437c-a5b8-5aeddf9dfb37", "4cb2546a-5aa2-4dfb-8d71-217842c6286a", "High-Dividend Investing", 3),
    ("2fdf357f-3186-4d43-bfd5-08b4b1398d1f", "e04d2c5d-0811-4441-bd0c-2807446dad1d", "Bill Ackman Strategy", 3),
    ("73b2689b-a881-4021-8f46-01113224608a", "24fecb8f-cb85-4194-8bfd-e5b087f08f45", "Joel Greenblatt Strategy", 1),
    ("64f8d327-d5a5-4377-85c0-4da4848f235c", "1b34a9b6-4cb9-4e6b-9a31-fd666f63dd6c", "Thomas Rowe Price Jr Strategy", 2),
    ("6f5bde20-4a63-4ff0-af2d-686c5ebd4776", "3cf40398-6bb5-48c4-9b24-44d0a63af703", "Event-Driven Activism", 1),
]


def execute_strategy(request_id: str, strategy_id: str, strategy_name: str, rec_count: int) -> dict:
    """Execute recommendations for a single strategy."""
    print(f"\n{'='*60}")
    print(f"Executing: {strategy_name}")
    print(f"Request ID: {request_id}")
    print(f"Recommendations: {rec_count}")
    print(f"{'='*60}")

    cmd = [
        "uv", "run", "python", "scripts/execute_recommendations.py",
        request_id,
        strategy_id,
        "--provider-id", "gemini",
        "--initial-balance", "100000",
        "--no-live-prices"
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=Path(__file__).parent.parent
        )

        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)

        return {
            "strategy_name": strategy_name,
            "request_id": request_id,
            "status": "SUCCESS" if result.returncode == 0 else "FAILED",
            "return_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        print(f"✗ Execution timed out for {strategy_name}")
        return {
            "strategy_name": strategy_name,
            "request_id": request_id,
            "status": "TIMEOUT",
            "return_code": -1,
        }
    except Exception as e:
        print(f"✗ Error executing {strategy_name}: {e}")
        return {
            "strategy_name": strategy_name,
            "request_id": request_id,
            "status": "ERROR",
            "error": str(e),
        }


def main():
    """Execute all strategies with recommendations."""
    print("\n" + "="*60)
    print("EXECUTING RECOMMENDATIONS FOR ALL STRATEGIES")
    print("="*60)
    print(f"Processing {len(STRATEGIES_WITH_RECS)} strategies with recommendations")
    print("="*60 + "\n")

    results = []
    for request_id, strategy_id, strategy_name, rec_count in STRATEGIES_WITH_RECS:
        result = execute_strategy(request_id, strategy_id, strategy_name, rec_count)
        results.append(result)

    # Print summary
    print("\n" + "="*60)
    print("EXECUTION SUMMARY")
    print("="*60)

    success_count = sum(1 for r in results if r["status"] == "SUCCESS")
    failed_count = sum(1 for r in results if r["status"] == "FAILED")
    error_count = sum(1 for r in results if r["status"] in ("TIMEOUT", "ERROR"))

    print(f"\nTotal Strategies: {len(results)}")
    print(f"Success: {success_count}")
    print(f"Failed: {failed_count}")
    print(f"Errors/Timeouts: {error_count}\n")

    for result in results:
        status_icon = "✓" if result["status"] == "SUCCESS" else "✗"
        print(f"{status_icon} {result['strategy_name']}: {result['status']}")

    print("\n" + "="*60)


if __name__ == "__main__":
    main()
