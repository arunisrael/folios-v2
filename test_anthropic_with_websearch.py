"""Test Anthropic CLI with WebSearch enabled."""

import asyncio
from uuid import UUID, uuid4

from folios_v2.cli.deps import get_container
from folios_v2.domain import (
    ExecutionMode,
    ExecutionTask,
    LifecycleState,
    ProviderId,
    Request,
    RequestPriority,
    RequestType,
)


async def create_anthropic_websearch_request():
    """Create Anthropic CLI request with WebSearch enabled."""
    container = get_container()

    # Use an existing strategy
    strategy_id = UUID("877be608-8547-4656-9d16-0f395df434dd")

    # Investment analysis prompt
    test_prompt = """Analyze AAPL and MSFT for investment potential. Focus on:
1. Recent earnings and revenue growth (Q3-Q4 2024)
2. Market position and competitive advantages
3. Valuation metrics (P/E, P/S, PEG ratios)
4. Technical indicators and momentum

Provide a JSON response with your analysis and recommendation in this format:
{
  "recommendations": [
    {
      "ticker": "AAPL",
      "company_name": "Apple Inc.",
      "action": "BUY|SELL|HOLD",
      "allocation_percent": 8.0,
      "rationale": "...",
      "confidence": 0.85,
      "valuation": {
        "pe_ratio": 28.5,
        "ps_ratio": 7.2
      },
      "technicals": {
        "momentum": "bullish|bearish|neutral",
        "rsi": 62
      }
    }
  ],
  "market_context": "...",
  "risk_factors": ["..."]
}"""

    async with container.unit_of_work_factory() as uow:
        # Create Anthropic CLI request with WebSearch
        request_id = uuid4()
        request = Request(
            id=request_id,
            strategy_id=strategy_id,
            provider_id=ProviderId.ANTHROPIC,
            mode=ExecutionMode.CLI,
            request_type=RequestType.RESEARCH,
            priority=RequestPriority.NORMAL,
            lifecycle_state=LifecycleState.PENDING,
            metadata={"strategy_prompt": test_prompt},
        )
        await uow.request_repository.add(request)
        print(f"✅ Created Anthropic CLI request (with WebSearch): {request_id}")

        # Create execution task
        task_id = uuid4()
        task = ExecutionTask(
            id=task_id,
            request_id=request_id,
            sequence=1,
            mode=ExecutionMode.CLI,
            lifecycle_state=LifecycleState.PENDING,
        )
        await uow.task_repository.add(task)
        print(f"✅ Created task: {task_id}")

        await uow.commit()

    print("\n" + "=" * 70)
    print("🔍 Anthropic CLI Request with WebSearch Created!")
    print("=" * 70)
    print(f"\nRequest ID: {request_id}")
    print(f"Task ID:    {task_id}")
    print("\nCommand will use: --dangerously-skip-permissions")
    print("\nRun 'make harvest' to process this request")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(create_anthropic_websearch_request())
