"""Runtime execution result models."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from folios_v2.providers.models import CliResult, PollResult, SubmitResult
from folios_v2.providers.models import DownloadResult as BatchDownloadResult


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class BatchExecutionOutcome:
    """Aggregate outcome for a batch execution."""

    submit_result: SubmitResult
    download_result: BatchDownloadResult
    poll_history: Sequence[PollResult] = field(default_factory=tuple)
    started_at: datetime = field(default_factory=utc_now)
    completed_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class CliExecutionOutcome:
    """Outcome for a CLI execution."""

    result: CliResult
    started_at: datetime = field(default_factory=utc_now)
    completed_at: datetime = field(default_factory=utc_now)
