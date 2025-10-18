"""Utilities for constructing provider-ready research prompts."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Iterable

from folios_v2.domain import ExecutionMode, RiskControls, Strategy
from folios_v2.orchestration.portfolio_snapshot import PortfolioSnapshot

RECENCY_BLOCK = (
    "\n\nRecency requirements (must follow):\n"
    "- CRITICAL: Determine the current date first, then prioritize data, filings, news, and price "
    "action from the past 3 months. Focus especially on the most recent 30 days.\n"
    "- If your toolset supports web search or retrieval, run a fresh search before forming "
    "conclusions and cite the recent sources consulted with their dates.\n"
    "- Clearly state the date range you analyzed (e.g., 'Analysis based on data from [start date] "
    "to [end date]').\n"
    "- Historical trends older than 6 months should be treated as context only; never cite them as "
    "current catalysts unless corroborated by recent data from the past 3 months.\n"
)

COMPLIANCE_BLOCK = (
    "\n\nCompliance constraints (must follow):\n"
    "- Only recommend currently listed, tradeable U.S. stock tickers on NYSE, Nasdaq, or "
    "NYSE American.\n"
    "- Exclude OTC/pink sheet and delisted symbols.\n"
    "- Do not use placeholder or generic tickers (e.g., ABC, TEST).\n"
    "- Company name must correctly correspond to the ticker; do not mismatch.\n"
    '- If no valid symbols qualify, return an empty recommendations array ("recommendations": []).'
)

_CLI_STRUCTURED_SCHEMA = (
    "\n\nCLI execution requirements (must follow):\n"
    "- Run the Stock Screener API available in your toolset first to refresh candidate "
    "tickers. Document the filters used and key results in the analysis.\n"
    "- Invoke web-search or retrieval tools before final recommendations and cite the "
    "sources consulted.\n"
    "- Return the final output as JSON matching this structure exactly (no extra prose):\n"
    "  {\n"
    "    \"analysis_summary\": string,\n"
    "    \"overall_sentiment\": one of [\"bullish\", \"bearish\", \"neutral\"],\n"
    "    \"overall_confidence\": integer 0-100,\n"
    "    \"recommendations\": [\n"
    "      {\n"
    "        \"ticker\": string,\n"
    "        \"company_name\": string,\n"
    "        \"action\": one of [\"BUY\", \"SELL\", \"SELL_SHORT\", \"HOLD\"],\n"
    "        \"current_price\": number,\n"
    "        \"target_price\": number,\n"
    "        \"confidence\": integer 0-100,\n"
    "        \"investment_thesis\": string (2-3 sentences),\n"
    "        \"key_metrics\": { optional numeric metrics like \"pe_ratio\", \"roe\", "
    "\"debt_to_equity\" },\n"
    "        \"position_size_pct\": number (0-100),\n"
    "        \"risk_factors\": [string],\n"
    "        \"catalysts\": [string]\n"
    "      }, ...\n"
    "    ],\n"
    "    \"market_context\": { optional fields \"market_regime\", \"key_themes\", "
    "\"macro_risks\" },\n"
    "    \"portfolio_considerations\": { optional fields \"total_allocation\", "
    "\"diversification_notes\", \"rebalancing_guidance\" }\n"
    "  }\n"
    "- IMPORTANT: Use \"SELL_SHORT\" action for short selling positions (not \"SELL\").\n"
    "- If information is unavailable, use nulls or empty arrays; never invent data or "
    "change the schema.\n"
)


def _risk_constraints_block(risk_controls: RiskControls | None) -> str:
    if risk_controls is None:
        return (
            "\n\nRisk constraints (must follow):\n"
            "- Default to conservative allocations (<=10% per position, <=95% total "
            "exposure) when limits are unspecified.\n"
            "- If the strategy is already near these limits, propose SELL or reduced "
            "allocations to free capital before adding new positions."
        )

    lines: list[str] = []
    if getattr(risk_controls, "max_exposure", None) is not None:
        lines.append(
            f"- Keep total BUY allocations within {risk_controls.max_exposure:.1f}% of "
            "portfolio capital."
        )
    if getattr(risk_controls, "max_position_size", None) is not None:
        lines.append(
            f"- Any individual position must stay at or below "
            f"{risk_controls.max_position_size:.1f}% allocation."
        )
    if getattr(risk_controls, "stop_loss", None) is not None:
        lines.append(
            f"- Respect stop loss thresholds at {risk_controls.stop_loss:.1f}% drawdown."
        )
    if getattr(risk_controls, "max_leverage", None) is not None:
        lines.append(
            f"- Never exceed {risk_controls.max_leverage:.1f}x leverage when sizing trades."
        )
        lines.append(
            "- If the strategy is already near these limits, propose SELL or reduced "
            "allocations to free capital before adding new positions."
        )
    joined = "\n".join(lines)
    return "\n\nRisk constraints (must follow):\n" + joined


def _candidates_block(candidates: tuple[str, ...] | None) -> str:
    if not candidates:
        return ""
    formatted = "\n".join(f"- {ticker}" for ticker in candidates)
    return "\n\nScreened ticker candidates (latest refresh):\n" + formatted


def _fmt_money(value: Decimal | None) -> str:
    if value is None:
        return "n/a"
    return f"${value:,.2f}"


def _fmt_decimal(value: Decimal | None, *, digits: int = 2, suffix: str = "") -> str:
    if value is None:
        return "n/a"
    return f"{value:,.{digits}f}{suffix}"


def _fmt_datetime(value: datetime | None) -> str:
    if value is None:
        return "n/a"
    return value.isoformat(timespec="seconds")


def _format_positions(positions: Iterable) -> str:
    positions = list(positions)
    if not positions:
        return "- No open positions."

    header = "Ticker | Side | Qty | Avg Price | Market Price | Value | P/L | Weight"
    lines = [header]
    for pos in positions:
        lines.append(
            " | ".join(
                [
                    pos.symbol,
                    pos.side,
                    f"{pos.quantity:,.4f}",
                    _fmt_money(pos.average_price),
                    _fmt_money(pos.market_price),
                    _fmt_money(pos.market_value),
                    _fmt_money(pos.unrealized_pl),
                    _fmt_decimal(pos.weight_pct, digits=1, suffix="%"),
                ]
            )
        )
    return "\n".join(lines)


def _format_recent_orders(orders: Iterable) -> str:
    orders = list(orders)
    if not orders:
        return ""

    lines = ["Recent filled orders (most recent first):"]
    for order in orders:
        lines.append(
            f"- {order.filled_at.isoformat(timespec='seconds') if order.filled_at else 'n/a'}: "
            f"{order.action} {order.quantity:,.4f} {order.symbol} @ {_fmt_money(order.price)}"
        )
    return "\n".join(lines)


def _portfolio_snapshot_block(snapshot: PortfolioSnapshot) -> str:
    gross = _fmt_decimal(snapshot.gross_exposure_pct, digits=1, suffix="%")
    net = _fmt_decimal(snapshot.net_exposure_pct, digits=1, suffix="%")
    leverage_raw = _fmt_decimal(snapshot.leverage, digits=2)
    leverage = f"{leverage_raw}x" if leverage_raw != "n/a" else "n/a"
    exposures = f"Gross exposure: {gross}   Net exposure: {net}   Leverage: {leverage}"

    block_lines = [
        f"Current Portfolio Snapshot — {snapshot.provider_id.value.upper()}",
        f"Updated at: {_fmt_datetime(snapshot.updated_at)}",
        f"Cash: {_fmt_money(snapshot.cash)}",
        f"Positions value: {_fmt_money(snapshot.positions_value)}",
        f"Total portfolio value: {_fmt_money(snapshot.total_value)}",
        exposures,
        "",
        _format_positions(snapshot.positions),
    ]

    recent_orders_block = _format_recent_orders(snapshot.recent_orders)
    if recent_orders_block:
        block_lines.extend(["", recent_orders_block])

    return "\n".join(block_lines)


def build_research_prompt(
    strategy: Strategy,
    *,
    mode: ExecutionMode,
    market_context: str | None = None,
    screener_candidates: tuple[str, ...] | None = None,
    portfolio_snapshot: PortfolioSnapshot | None = None,
) -> str:
    """Compose the full research prompt for a strategy and execution mode."""

    base_prompt = strategy.prompt.strip()
    if market_context:
        trimmed = market_context.strip()
        if trimmed:
            base_prompt = f"{trimmed}\n\n{base_prompt}"

    prompt_sections: list[str] = []

    if portfolio_snapshot is not None:
        prompt_sections.append(_portfolio_snapshot_block(portfolio_snapshot))

    prompt_sections.append(base_prompt)

    prompt = (
        "\n\n".join(prompt_sections)
        + RECENCY_BLOCK
        + COMPLIANCE_BLOCK
        + _risk_constraints_block(strategy.risk_controls)
        + _candidates_block(screener_candidates)
    )

    if mode is ExecutionMode.CLI:
        prompt += _CLI_STRUCTURED_SCHEMA

    return prompt


__all__ = ["build_research_prompt"]
