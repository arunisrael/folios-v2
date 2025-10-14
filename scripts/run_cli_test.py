#!/usr/bin/env python3
"""
Execute 5 random strategies across Gemini CLI, OpenAI, and Anthropic providers.
"""

import asyncio
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

# Selected strategies
STRATEGIES = [
    "strategy_bd6b5423",  # All Weather Risk Parity
    "strategy_451efef4",  # Howard Marks Strategy
    "strategy_a815f2cd",  # Joel Greenblatt Strategy
    "strategy_b056b849",  # Momentum Trading
    "strategy_be45b8b0",  # Jim Chanos Strategy
]

DB_PATH = Path(__file__).parent.parent / "folios_v2.db"
ARTIFACTS_DIR = Path(__file__).parent.parent / "artifacts"


def get_strategy(strategy_id: str) -> dict[str, Any]:
    """Fetch strategy from database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT id, name, status, payload FROM strategies WHERE id = ?", (strategy_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise ValueError(f"Strategy {strategy_id} not found")

    strategy = dict(row)
    strategy["payload"] = json.loads(strategy["payload"])
    return strategy


async def run_gemini_cli(strategy: dict[str, Any]) -> dict[str, Any]:
    """Execute strategy via Gemini CLI."""
    strategy_id = strategy["id"]
    base_prompt = strategy["payload"]["prompt"]
    tickers = strategy["payload"].get("tickers", [])

    # Limit to first 10 tickers for reasonable execution time
    tickers_to_analyze = tickers[:10] if len(tickers) > 10 else tickers
    ticker_list = ", ".join(tickers_to_analyze)

    # Create a complete research request
    prompt = f"""{base_prompt}

RESEARCH REQUEST:
Analyze the following stocks and provide your top 3-5 recommendations with specific entry/exit prices and position sizes.

Tickers to analyze: {ticker_list}

Please provide your analysis in JSON format with this structure:
```json
{{
  "recommendations": [
    {{
      "ticker": "AAPL",
      "action": "BUY" | "SELL" | "HOLD",
      "entry_price": 150.00,
      "target_price": 180.00,
      "stop_loss": 140.00,
      "position_size_pct": 5.0,
      "rationale": "Brief explanation"
    }}
  ]
}}
```
"""

    # Create artifact directory
    run_id = f"gemini_{strategy_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    artifact_dir = ARTIFACTS_DIR / run_id
    artifact_dir.mkdir(parents=True, exist_ok=True)

    # Save prompt
    prompt_path = artifact_dir / "prompt.txt"
    prompt_path.write_text(prompt, encoding="utf-8")

    # Execute Gemini CLI
    command = ["gemini", "--output-format", "json", "-y", prompt]

    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await process.communicate()
    exit_code = process.returncode or 0

    stdout_text = stdout.decode("utf-8", errors="replace") if stdout else ""
    stderr_text = stderr.decode("utf-8", errors="replace") if stderr else ""

    # Parse response
    response_payload: dict[str, Any] = {
        "provider": "gemini",
        "strategy_id": strategy_id,
        "strategy_name": strategy["name"],
        "run_id": run_id,
        "exit_code": exit_code,
        "timestamp": datetime.now().isoformat(),
    }

    if stdout_text:
        try:
            cli_output = json.loads(stdout_text)
            response_payload["cli_output"] = cli_output

            # Extract structured JSON from response
            response_field = cli_output.get("response", "")
            if isinstance(response_field, str):
                structured = _extract_json_block(response_field)
                if structured:
                    response_payload["structured"] = structured
        except json.JSONDecodeError:
            response_payload["raw_stdout"] = stdout_text

    if stderr_text:
        response_payload["stderr"] = stderr_text
        (artifact_dir / "stderr.txt").write_text(stderr_text, encoding="utf-8")

    # Save response
    response_path = artifact_dir / "response.json"
    response_path.write_text(json.dumps(response_payload, indent=2), encoding="utf-8")

    if "structured" in response_payload:
        structured_path = artifact_dir / "structured.json"
        structured_path.write_text(
            json.dumps(response_payload["structured"], indent=2), encoding="utf-8"
        )

    return response_payload


async def run_openai_cli(strategy: dict[str, Any]) -> dict[str, Any]:
    """Execute strategy via OpenAI Codex CLI."""
    strategy_id = strategy["id"]
    base_prompt = strategy["payload"]["prompt"]
    tickers = strategy["payload"].get("tickers", [])

    # Limit to first 10 tickers for reasonable execution time
    tickers_to_analyze = tickers[:10] if len(tickers) > 10 else tickers
    ticker_list = ", ".join(tickers_to_analyze)

    # Create a complete research request
    prompt = f"""{base_prompt}

RESEARCH REQUEST:
Analyze the following stocks and provide your top 3-5 recommendations with specific entry/exit prices and position sizes.

Tickers to analyze: {ticker_list}

Please provide your analysis in JSON format with this structure:
```json
{{
  "recommendations": [
    {{
      "ticker": "AAPL",
      "action": "BUY" | "SELL" | "HOLD",
      "entry_price": 150.00,
      "target_price": 180.00,
      "stop_loss": 140.00,
      "position_size_pct": 5.0,
      "rationale": "Brief explanation"
    }}
  ]
}}
```
"""

    # Create artifact directory
    run_id = f"openai_{strategy_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    artifact_dir = ARTIFACTS_DIR / run_id
    artifact_dir.mkdir(parents=True, exist_ok=True)

    # Save prompt
    prompt_path = artifact_dir / "prompt.txt"
    prompt_path.write_text(prompt, encoding="utf-8")

    # Execute OpenAI Codex CLI
    command = ["codex", "--search", "exec", "--json", "--skip-git-repo-check", prompt]

    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await process.communicate()
    exit_code = process.returncode or 0

    stdout_text = stdout.decode("utf-8", errors="replace") if stdout else ""
    stderr_text = stderr.decode("utf-8", errors="replace") if stderr else ""

    # Parse response
    response_payload: dict[str, Any] = {
        "provider": "openai",
        "strategy_id": strategy_id,
        "strategy_name": strategy["name"],
        "run_id": run_id,
        "exit_code": exit_code,
        "timestamp": datetime.now().isoformat(),
    }

    if stdout_text:
        (artifact_dir / "stdout.txt").write_text(stdout_text, encoding="utf-8")

        # Parse event stream
        events = _parse_event_stream(stdout_text)
        if events:
            response_payload["events"] = events

            # Extract agent text
            agent_text = _extract_agent_text(events)
            if agent_text:
                response_payload["agent_text"] = agent_text
                try:
                    structured = json.loads(agent_text)
                    response_payload["structured"] = structured
                except json.JSONDecodeError:
                    structured = _extract_json_block(agent_text)
                    if structured:
                        response_payload["structured"] = structured

    if stderr_text:
        response_payload["stderr"] = stderr_text
        (artifact_dir / "stderr.txt").write_text(stderr_text, encoding="utf-8")

    # Save response
    response_path = artifact_dir / "response.json"
    response_path.write_text(json.dumps(response_payload, indent=2), encoding="utf-8")

    if "structured" in response_payload:
        structured_path = artifact_dir / "structured.json"
        structured_path.write_text(
            json.dumps(response_payload["structured"], indent=2), encoding="utf-8"
        )

    return response_payload


async def run_anthropic_cli(strategy: dict[str, Any]) -> dict[str, Any]:
    """Execute strategy via Anthropic Claude CLI."""
    strategy_id = strategy["id"]
    base_prompt = strategy["payload"]["prompt"]
    tickers = strategy["payload"].get("tickers", [])

    # Limit to first 10 tickers for reasonable execution time
    tickers_to_analyze = tickers[:10] if len(tickers) > 10 else tickers
    ticker_list = ", ".join(tickers_to_analyze)

    # Create a complete research request
    prompt = f"""{base_prompt}

RESEARCH REQUEST:
Analyze the following stocks and provide your top 3-5 recommendations with specific entry/exit prices and position sizes.

Tickers to analyze: {ticker_list}

Please provide your analysis in JSON format with this structure:
```json
{{
  "recommendations": [
    {{
      "ticker": "AAPL",
      "action": "BUY" | "SELL" | "HOLD",
      "entry_price": 150.00,
      "target_price": 180.00,
      "stop_loss": 140.00,
      "position_size_pct": 5.0,
      "rationale": "Brief explanation"
    }}
  ]
}}
```
"""

    # Create artifact directory
    run_id = f"anthropic_{strategy_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    artifact_dir = ARTIFACTS_DIR / run_id
    artifact_dir.mkdir(parents=True, exist_ok=True)

    # Save prompt
    prompt_path = artifact_dir / "prompt.txt"
    prompt_path.write_text(prompt, encoding="utf-8")

    # Execute Claude CLI
    command = [
        "/Users/arun/.claude/local/claude",
        "-p",
        "--output-format", "json",
        "--dangerously-skip-permissions",
        prompt
    ]

    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await process.communicate()
    exit_code = process.returncode or 0

    stdout_text = stdout.decode("utf-8", errors="replace") if stdout else ""
    stderr_text = stderr.decode("utf-8", errors="replace") if stderr else ""

    # Parse response
    response_payload: dict[str, Any] = {
        "provider": "anthropic",
        "strategy_id": strategy_id,
        "strategy_name": strategy["name"],
        "run_id": run_id,
        "exit_code": exit_code,
        "timestamp": datetime.now().isoformat(),
    }

    if stdout_text:
        try:
            cli_output = json.loads(stdout_text)
            response_payload["cli_output"] = cli_output

            # Extract result field
            result_text = cli_output.get("result")
            if isinstance(result_text, str):
                response_payload["result"] = result_text
                try:
                    structured = json.loads(result_text)
                    response_payload["structured"] = structured
                except json.JSONDecodeError:
                    structured = _extract_json_block(result_text)
                    if structured:
                        response_payload["structured"] = structured
        except json.JSONDecodeError:
            response_payload["raw_stdout"] = stdout_text

    if stderr_text:
        response_payload["stderr"] = stderr_text
        (artifact_dir / "stderr.txt").write_text(stderr_text, encoding="utf-8")

    # Save response
    response_path = artifact_dir / "response.json"
    response_path.write_text(json.dumps(response_payload, indent=2), encoding="utf-8")

    if "structured" in response_payload:
        structured_path = artifact_dir / "structured.json"
        structured_path.write_text(
            json.dumps(response_payload["structured"], indent=2), encoding="utf-8"
        )

    return response_payload


def _extract_json_block(text: str) -> dict[str, Any] | None:
    """Extract JSON from markdown code blocks."""
    marker = "```json"
    start = text.find(marker)
    if start == -1:
        return None
    start = text.find("\n", start)
    if start == -1:
        return None
    start += 1
    end = text.find("```", start)
    if end == -1:
        return None
    raw_block = text[start:end].strip()
    try:
        return json.loads(raw_block)
    except json.JSONDecodeError:
        return None


def _parse_event_stream(output: str) -> list[dict[str, Any]]:
    """Parse event stream from OpenAI CLI."""
    events: list[dict[str, Any]] = []
    for line in output.splitlines():
        candidate = line.strip()
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                events.append(parsed)
        except json.JSONDecodeError:
            continue
    return events


def _extract_agent_text(events: list[dict[str, Any]]) -> str | None:
    """Extract agent text from event stream."""
    for event in reversed(events):
        if event.get("type") != "item.completed":
            continue
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        if item.get("type") != "agent_message":
            continue
        text = item.get("text")
        if isinstance(text, str):
            return text
        content = item.get("content")
        if isinstance(content, list):
            parts: list[str] = []
            for part in content:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    parts.append(part["text"])
            if parts:
                return "".join(parts)
    return None


async def main() -> None:
    """Run all 5 strategies across all 3 providers."""
    print("=" * 80)
    print("Strategy Execution: Testing 5 Strategies Across 3 Providers")
    print("=" * 80)
    print(f"Database: {DB_PATH}")
    print(f"Artifacts: {ARTIFACTS_DIR}")
    print(f"Strategies: {len(STRATEGIES)}")
    print("=" * 80)
    print()

    # Create artifacts directory
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    all_results: list[dict[str, Any]] = []

    for strategy_id in STRATEGIES:
        print(f"\n{'='*80}")
        print(f"Processing: {strategy_id}")
        print(f"{'='*80}")

        try:
            strategy = get_strategy(strategy_id)
            print(f"Strategy Name: {strategy['name']}")
            print(f"Status: {strategy['status']}")

            # Run across all providers
            print("\n  [1/3] Running Gemini CLI...")
            gemini_result = await run_gemini_cli(strategy)
            print(f"        Exit Code: {gemini_result['exit_code']}")
            print(f"        Artifact: {gemini_result['run_id']}")
            all_results.append(gemini_result)

            print("\n  [2/3] Running OpenAI CLI...")
            openai_result = await run_openai_cli(strategy)
            print(f"        Exit Code: {openai_result['exit_code']}")
            print(f"        Artifact: {openai_result['run_id']}")
            all_results.append(openai_result)

            print("\n  [3/3] Running Anthropic CLI...")
            anthropic_result = await run_anthropic_cli(strategy)
            print(f"        Exit Code: {anthropic_result['exit_code']}")
            print(f"        Artifact: {anthropic_result['run_id']}")
            all_results.append(anthropic_result)

        except Exception as e:
            print(f"  ❌ Error: {e}")
            continue

    # Summary
    print(f"\n{'='*80}")
    print("Execution Summary")
    print(f"{'='*80}")

    summary_path = ARTIFACTS_DIR / f"summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    summary = {
        "timestamp": datetime.now().isoformat(),
        "total_executions": len(all_results),
        "strategies_processed": len(STRATEGIES),
        "results": all_results,
    }

    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Summary saved to: {summary_path}")

    # Count successes
    successes = sum(1 for r in all_results if r.get("exit_code") == 0)
    print(f"Successful executions: {successes}/{len(all_results)}")
    print(f"Failed executions: {len(all_results) - successes}/{len(all_results)}")

    # Group by provider
    by_provider: dict[str, list[dict[str, Any]]] = {}
    for result in all_results:
        provider = result.get("provider", "unknown")
        by_provider.setdefault(provider, []).append(result)

    for provider, results in sorted(by_provider.items()):
        provider_successes = sum(1 for r in results if r.get("exit_code") == 0)
        print(f"  {provider}: {provider_successes}/{len(results)} successful")


if __name__ == "__main__":
    asyncio.run(main())
