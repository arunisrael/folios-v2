"""Test script to create CLI requests for Anthropic and Gemini providers."""

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


async def create_test_requests():
    """Create test requests for Anthropic and Gemini CLI execution."""
    container = get_container()

    # Use an existing strategy
    strategy_id = UUID("877be608-8547-4656-9d16-0f395df434dd")

    # Better test prompt
    test_prompt = """Analyze AAPL and MSFT for investment potential. Focus on:
1. Recent earnings and revenue growth
2. Market position and competitive advantages
3. Valuation metrics (P/E, P/S, etc.)
4. Technical indicators and momentum

Provide a JSON response with your analysis and recommendation."""

    async with container.unit_of_work_factory() as uow:
        # Create Anthropic CLI request
        anthropic_request_id = uuid4()
        anthropic_request = Request(
            id=anthropic_request_id,
            strategy_id=strategy_id,
            provider_id=ProviderId.ANTHROPIC,
            mode=ExecutionMode.CLI,
            request_type=RequestType.RESEARCH,
            priority=RequestPriority.NORMAL,
            lifecycle_state=LifecycleState.PENDING,
            metadata={"strategy_prompt": test_prompt},
        )
        await uow.request_repository.add(anthropic_request)
        print(f"✅ Created Anthropic CLI request: {anthropic_request_id}")

        # Create Anthropic execution task
        anthropic_task_id = uuid4()
        anthropic_task = ExecutionTask(
            id=anthropic_task_id,
            request_id=anthropic_request_id,
            sequence=1,
            mode=ExecutionMode.CLI,
            lifecycle_state=LifecycleState.PENDING,
        )
        await uow.task_repository.add(anthropic_task)
        print(f"✅ Created Anthropic task: {anthropic_task_id}")

        # Create Gemini CLI request
        gemini_request_id = uuid4()
        gemini_request = Request(
            id=gemini_request_id,
            strategy_id=strategy_id,
            provider_id=ProviderId.GEMINI,
            mode=ExecutionMode.CLI,
            request_type=RequestType.RESEARCH,
            priority=RequestPriority.NORMAL,
            lifecycle_state=LifecycleState.PENDING,
            metadata={"strategy_prompt": test_prompt},
        )
        await uow.request_repository.add(gemini_request)
        print(f"✅ Created Gemini CLI request: {gemini_request_id}")

        # Create Gemini execution task
        gemini_task_id = uuid4()
        gemini_task = ExecutionTask(
            id=gemini_task_id,
            request_id=gemini_request_id,
            sequence=1,
            mode=ExecutionMode.CLI,
            lifecycle_state=LifecycleState.PENDING,
        )
        await uow.task_repository.add(gemini_task)
        print(f"✅ Created Gemini task: {gemini_task_id}")

        await uow.commit()

    print("\n" + "=" * 70)
    print("Test requests created successfully!")
    print("=" * 70)
    print(f"\nAnthropic Request ID: {anthropic_request_id}")
    print(f"Anthropic Task ID:    {anthropic_task_id}")
    print(f"\nGemini Request ID:    {gemini_request_id}")
    print(f"Gemini Task ID:       {gemini_task_id}")
    print("\nRun 'make harvest' to process these requests")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(create_test_requests())
