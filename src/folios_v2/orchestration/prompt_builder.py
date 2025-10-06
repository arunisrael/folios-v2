"""Utilities for constructing provider-ready research prompts."""

from __future__ import annotations

from folios_v2.domain import ExecutionMode, RiskControls, Strategy

RECENCY_BLOCK = (
    "\n\nRecency requirements (must follow):\n"
    "- Prioritize data, filings, news, and price action from 2025 Q2 onward, with extra weight "
    "on the latest quarter (Q3 2025).\n"
    "- If your toolset supports web search or retrieval, run a fresh search before forming "
    "conclusions and cite the 2025 sources consulted.\n"
    "- Treat pandemic-era demand shifts as historical context only; never cite them as current "
    "catalysts unless corroborated by 2025 data.\n"
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
    "        \"action\": one of [\"BUY\", \"SELL\", \"HOLD\"],\n"
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


def build_research_prompt(
    strategy: Strategy,
    *,
    mode: ExecutionMode,
    market_context: str | None = None,
) -> str:
    """Compose the full research prompt for a strategy and execution mode."""

    base_prompt = strategy.prompt.strip()
    if market_context:
        trimmed = market_context.strip()
        if trimmed:
            base_prompt = f"{trimmed}\n\n{base_prompt}"

    prompt = (
        base_prompt
        + RECENCY_BLOCK
        + COMPLIANCE_BLOCK
        + _risk_constraints_block(strategy.risk_controls)
    )

    if mode is ExecutionMode.CLI:
        prompt += _CLI_STRUCTURED_SCHEMA

    return prompt


__all__ = ["build_research_prompt"]
