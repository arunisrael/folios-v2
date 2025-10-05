"""SQLAlchemy ORM models for Folios v2 SQLite persistence."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):  # type: ignore[misc]
    pass


class StrategyRecord(Base):
    __tablename__ = "strategies"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)


class StrategyScheduleRecord(Base):
    __tablename__ = "strategy_schedules"

    strategy_id: Mapped[str] = mapped_column(String, ForeignKey("strategies.id"), primary_key=True)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    next_research_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_research_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)


class StrategyRunRecord(Base):
    __tablename__ = "strategy_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    strategy_id: Mapped[str] = mapped_column(String, ForeignKey("strategies.id"), nullable=False)
    iso_year: Mapped[int] = mapped_column(Integer, nullable=False)
    iso_week: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)


class RequestRecord(Base):
    __tablename__ = "requests"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    strategy_id: Mapped[str] = mapped_column(String, ForeignKey("strategies.id"), nullable=False)
    provider_id: Mapped[str] = mapped_column(String, nullable=False)
    mode: Mapped[str] = mapped_column(String, nullable=False)
    request_type: Mapped[str] = mapped_column(String, nullable=False)
    priority: Mapped[str] = mapped_column(String, nullable=False)
    lifecycle_state: Mapped[str] = mapped_column(String, nullable=False)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)


class ExecutionTaskRecord(Base):
    __tablename__ = "execution_tasks"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    request_id: Mapped[str] = mapped_column(String, ForeignKey("requests.id"), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    mode: Mapped[str] = mapped_column(String, nullable=False)
    lifecycle_state: Mapped[str] = mapped_column(String, nullable=False)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)


class EmailDigestRecord(Base):
    __tablename__ = "email_digests"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    digest_type: Mapped[str] = mapped_column(String, nullable=False)
    iso_year: Mapped[int] = mapped_column(Integer, nullable=False)
    iso_week: Mapped[int] = mapped_column(Integer, nullable=False)
    week_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    delivery_state: Mapped[str] = mapped_column(String, nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)


class PositionSnapshotRecord(Base):
    __tablename__ = "position_snapshots"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)


class RequestLogRecord(Base):
    __tablename__ = "request_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String, nullable=False)
    task_id: Mapped[str | None] = mapped_column(String)
    previous_state: Mapped[str | None] = mapped_column(String)
    next_state: Mapped[str] = mapped_column(String, nullable=False)
    message: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attributes: Mapped[dict] = mapped_column(JSON, nullable=False)


class PortfolioAccountRecord(Base):
    __tablename__ = "portfolio_accounts"
    __table_args__ = (
        UniqueConstraint("strategy_id", "provider_id", name="uq_portfolio_strategy_provider"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_id: Mapped[str] = mapped_column(String, ForeignKey("strategies.id"), nullable=False)
    provider_id: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)


class PositionRecord(Base):
    __tablename__ = "positions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    strategy_id: Mapped[str] = mapped_column(String, ForeignKey("strategies.id"), nullable=False)
    provider_id: Mapped[str | None] = mapped_column(String)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="open")
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)


class OrderRecord(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    strategy_id: Mapped[str] = mapped_column(String, ForeignKey("strategies.id"), nullable=False)
    provider_id: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, nullable=False)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
