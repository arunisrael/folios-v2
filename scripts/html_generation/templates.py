"""HTML template rendering functions."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any


# Define html_escape function to avoid naming conflict with scripts/html package
def html_escape(text: str) -> str:
    """Escape HTML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )

# Provider display name mapping
PROVIDER_NAMES = {
    "openai": "OpenAI",
    "gemini": "Gemini",
    "anthropic": "Anthropic",
}


def format_timestamp(value: datetime | str | None) -> str:
    """Format timestamps for display."""
    if not value:
        return "-"

    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)

    return value.strftime("%Y-%m-%d %H:%M UTC")


def base_css() -> str:
    """Return base CSS styles."""
    return """
    body {
        font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif;
        margin: 24px;
    }
    h1, h2, h3 {
        margin: 0.8em 0 0.4em;
    }
    table {
        border-collapse: collapse;
        width: 100%;
        margin: 12px 0 24px;
    }
    th, td {
        border: 1px solid #e5e7eb;
        padding: 8px 10px;
        text-align: left;
    }
    th {
        background: #f9fafb;
    }
    tbody tr:nth-child(even) {
        background: #fafafa;
    }
    .muted {
        color: #6b7280;
    }
    .right {
        text-align: right;
    }
    .small {
        font-size: 0.9em;
    }
    .pill {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 999px;
        background: #eef2ff;
        color: #4338ca;
    }
    pre {
        white-space: pre-wrap;
        background: #f9fafb;
        padding: 12px;
        border: 1px solid #e5e7eb;
        border-radius: 6px;
    }
    a {
        color: #2563eb;
        text-decoration: none;
    }
    a:hover {
        text-decoration: underline;
    }
    .positive {
        color: #22863a;
    }
    .negative {
        color: #d73a49;
    }
    details {
        margin: 16px 0;
        border: 1px solid #e5e7eb;
        border-radius: 6px;
        background: #f9fafb;
    }
    details summary {
        cursor: pointer;
        padding: 12px 16px;
        font-weight: 600;
        color: #374151;
        user-select: none;
        list-style: none;
    }
    details summary::-webkit-details-marker {
        display: none;
    }
    details summary::before {
        content: '▶';
        display: inline-block;
        margin-right: 8px;
        transition: transform 0.2s;
        font-size: 0.8em;
    }
    details[open] summary::before {
        transform: rotate(90deg);
    }
    details summary:hover {
        background: #f3f4f6;
    }
    details[open] summary {
        border-bottom: 1px solid #e5e7eb;
    }
    details .details-content {
        padding: 16px;
        background: #ffffff;
    }
    """


def render_html_page(title: str, body_html: str) -> str:
    """Wrap body in full HTML document with meta tags.

    Args:
        title: Page title
        body_html: HTML content for body

    Returns:
        Complete HTML document
    """
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html_escape(title)}</title>
    <style>
    {base_css()}
    </style>
</head>
<body>
    {body_html}
</body>
</html>
"""


def render_leaderboard(
    strategies: list[dict[str, Any]],
    portfolio_accounts: dict[str, list[dict[str, Any]]],
    all_strategy_provider_pairs: list[tuple[str, str]],
    positions_by_strategy: dict[str, dict[str | None, list[dict[str, Any]]]] | None = None,
    prices: dict[str, Decimal] | None = None
) -> str:
    """Render leaderboard HTML (index.html).

    Args:
        strategies: List of strategy dicts
        portfolio_accounts: Dict mapping strategy_id to list of portfolio accounts
        all_strategy_provider_pairs: List of all (strategy_id, provider_id) tuples with requests
        positions_by_strategy: Dict mapping strategy_id to provider_id to positions (for accurate valuation)
        prices: Dict mapping symbol to current price (for accurate valuation)

    Returns:
        Complete HTML page
    """
    # Create a mapping of strategy IDs to names for quick lookup
    strategy_map = {s["id"]: s for s in strategies}

    # Create portfolio account lookup for quick access
    account_lookup: dict[tuple[str, str], dict[str, Any]] = {}
    for sid, accounts in portfolio_accounts.items():
        for acc in accounts:
            provider_id = acc.get("provider_id", "unknown")
            account_lookup[(sid, provider_id)] = acc

    # Calculate returns for each strategy+provider combination that has been requested
    portfolio_stats = []
    for sid, provider_id in all_strategy_provider_pairs:
        strategy = strategy_map.get(sid)
        if not strategy:
            continue

        name = strategy["name"]
        payload = strategy.get("payload", {})
        initial_capital = Decimal(str(payload.get("initial_capital_usd", 100000)))
        provider_name = PROVIDER_NAMES.get(provider_id, provider_id)

        # Check if this strategy+provider has an account with actual portfolio data
        acc = account_lookup.get((sid, provider_id))
        if acc:
            cash = Decimal(str(acc.get("cash_balance", 0)))

            # Calculate equity value using current market prices if available
            equity = Decimal("0")
            if positions_by_strategy and prices and sid in positions_by_strategy:
                positions = positions_by_strategy[sid].get(provider_id, [])
                for pos in positions:
                    symbol = pos["symbol"]
                    side = pos.get("side", "long")
                    qty = Decimal(str(pos.get("quantity", 0)))
                    price = prices.get(symbol, Decimal("0"))
                    # For short positions, equity is negative (it's a liability)
                    if side == "short":
                        equity -= qty * price
                    else:
                        equity += qty * price
            else:
                # Fall back to stored equity value if prices not available
                equity = Decimal(str(acc.get("equity_value", 0)))

            total_value = cash + equity
        else:
            # Strategy was requested but no trades executed yet
            total_value = initial_capital

        if initial_capital > 0:
            return_pct = ((total_value - initial_capital) / initial_capital) * 100
        else:
            return_pct = Decimal("0")

        portfolio_stats.append({
            "id": sid,
            "name": name,
            "provider_id": provider_id,
            "provider_name": provider_name,
            "total_value": total_value,
            "initial_capital": initial_capital,
            "return_pct": return_pct,
        })

    # Sort by return percentage (descending)
    portfolio_stats.sort(key=lambda x: x["return_pct"], reverse=True)

    # Build table rows
    rows = []
    for i, stat in enumerate(portfolio_stats, 1):
        return_class = "positive" if stat["return_pct"] >= 0 else "negative"
        return_sign = "+" if stat["return_pct"] >= 0 else ""

        rows.append(f"""
        <tr>
            <td>{i}</td>
            <td><a href="strategy-{html_escape(stat['id'])}.html" class="strategy-link">{html_escape(stat['name'])}</a></td>
            <td><span class="pill">{stat['provider_name']}</span></td>
            <td class="right">${stat['total_value']:,.2f}</td>
            <td class="right">${stat['initial_capital']:,.2f}</td>
            <td class="right {return_class}">{return_sign}{stat['return_pct']:.2f}%</td>
        </tr>
        """)

    table_html = f"""
    <table>
        <thead>
            <tr>
                <th>Rank</th>
                <th>Strategy</th>
                <th>Provider</th>
                <th class="right">Portfolio Value</th>
                <th class="right">Initial Capital</th>
                <th class="right">Return %</th>
            </tr>
        </thead>
        <tbody>
            {"".join(rows)}
        </tbody>
    </table>
    """

    body = f"""
    <h1>Strategy Leaderboard</h1>
    <p class="meta">Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</p>
    <p><a href="feed.html">View Activity Feed</a></p>
    {table_html}
    """

    return render_html_page("Strategy Leaderboard", body)


def render_strategy_detail(
    strategy: dict[str, Any],
    portfolio_accounts: list[dict[str, Any]],
    positions_by_provider: dict[str | None, list[dict[str, Any]]],
    trade_history_by_provider: dict[str | None, list[dict[str, Any]]],
    prices: dict[str, Decimal]
) -> str:
    """Render strategy detail page.

    Args:
        strategy: Strategy dict
        portfolio_accounts: List of portfolio accounts for this strategy
        positions_by_provider: Positions grouped by provider
        trade_history_by_provider: Trade history grouped by provider
        prices: Current prices by symbol

    Returns:
        Complete HTML page
    """
    name = strategy["name"]
    strategy_id = strategy["id"]
    payload = strategy.get("payload", {})
    initial_capital = Decimal(str(payload.get("initial_capital_usd", 100000)))

    # Get strategy prompt if available
    strategy_prompt = payload.get("prompt", "")

    # Build provider sections and calculate accurate portfolio values
    provider_sections = []
    provider_summary_rows: list[str] = []
    for acc in portfolio_accounts:
        provider_id = acc["provider_id"]
        provider_name = PROVIDER_NAMES.get(provider_id, provider_id)

        cash = Decimal(str(acc.get("cash_balance", 0)))

        positions = positions_by_provider.get(provider_id, [])
        trades = trade_history_by_provider.get(provider_id, [])

        # Positions table with enhanced columns
        position_rows = []
        total_position_value = Decimal("0")
        for pos in positions:
            symbol = pos["symbol"]
            side = pos.get("side", "long")  # Get position side
            qty = Decimal(str(pos.get("quantity", 0)))
            price = prices.get(symbol, Decimal("0"))
            # For short positions, market value is negative (it's a liability)
            if side == "short":
                market_value = -(qty * price)
            else:
                market_value = qty * price
            total_position_value += market_value
            avg_entry = pos.get("avg_entry_price")

            # Format dates
            opened_at = pos.get("opened_at")
            if opened_at:
                if isinstance(opened_at, str):
                    opened_str = opened_at[:10]
                else:
                    opened_str = opened_at.strftime('%Y-%m-%d')
            else:
                opened_str = "-"

            closed_at = pos.get("closed_at")
            closed_str = closed_at[:10] if closed_at else "-"

            if avg_entry:
                avg_entry_dec = Decimal(str(avg_entry))
                # For short positions, P/L is inverted (profit when price goes down)
                if side == "short":
                    unrealized_pl = (avg_entry_dec - price) * qty
                else:
                    unrealized_pl = (price - avg_entry_dec) * qty
                pl_class = "positive" if unrealized_pl >= 0 else "negative"
                pl_str = f'${unrealized_pl:,.2f}'
            else:
                avg_entry_dec = Decimal("0")
                pl_str = "$0.00"
                pl_class = ""

            position_rows.append(f"""
            <tr>
                <td>{html_escape(symbol)}</td>
                <td>{html_escape(side)}</td>
                <td>{opened_str}</td>
                <td>{closed_str}</td>
                <td class="right">{qty:.4f}</td>
                <td class="right">${avg_entry_dec:,.2f}</td>
                <td class="right">${price:,.2f}</td>
                <td class="right">${market_value:,.2f}</td>
                <td class="right {pl_class}">{pl_str}</td>
            </tr>
            """)

        # Calculate total value using current prices
        total_value = cash + total_position_value
        if initial_capital > 0:
            provider_return_pct = ((total_value - initial_capital) / initial_capital) * 100
        else:
            provider_return_pct = Decimal("0")

        updated_display_raw = format_timestamp(acc.get("updated_at"))
        updated_display = html_escape(updated_display_raw) if updated_display_raw != "-" else "-"
        heading_suffix = f" (updated {updated_display})" if updated_display_raw != "-" else ""

        # Add CASH row
        cash_row = f"""
            <tr>
                <td>CASH</td>
                <td>-</td>
                <td>-</td>
                <td>-</td>
                <td class="right">-</td>
                <td class="right">-</td>
                <td class="right">-</td>
                <td class="right">${cash:,.2f}</td>
                <td class="right">-</td>
            </tr>
            """

        positions_table = f"""
        <table>
            <thead>
                <tr>
                    <th>Symbol</th>
                    <th>Side</th>
                    <th>Opened</th>
                    <th>Closed</th>
                    <th class="right">Qty</th>
                    <th class="right">Avg Price</th>
                    <th class="right">Market Price</th>
                    <th class="right">Market Value</th>
                    <th class="right">P/L</th>
                </tr>
            </thead>
            <tbody>
                {cash_row}
                {"".join(position_rows) if position_rows else ""}
            </tbody>
        </table>
        """

        # Summary table
        summary_table = f"""
        <table>
            <thead>
                <tr>
                    <th>Summary</th>
                    <th class="right">Amount</th>
                </tr>
            </thead>
            <tbody>
                <tr><td>Positions Market Value</td><td class="right">${total_position_value:,.2f}</td></tr>
                <tr><td>Cash</td><td class="right">${cash:,.2f}</td></tr>
                <tr><td><strong>Net (Cash + Positions)</strong></td><td class="right"><strong>${total_value:,.2f}</strong></td></tr>
                <tr><td>Reported Provider Value</td><td class="right">${total_value:,.2f}</td></tr>
            </tbody>
        </table>
        """

        provider_summary_rows.append(
            f'<tr><td><span class="pill">{html_escape(provider_id)}</span></td>'
            f'<td class="right">${total_value:,.2f}</td>'
            f'<td class="right">{provider_return_pct:.2f}%</td>'
            f'<td class="small">{updated_display}</td></tr>'
        )

        # Trade history with essential columns only
        trade_rows = []
        for trade in trades[:20]:
            action = trade.get("action", "")
            symbol = trade.get("symbol", "")
            qty = float(trade.get("quantity", 0))
            price = float(trade.get("price", 0) or 0)
            timestamp = trade.get("timestamp")  # Portfolio engine uses "timestamp"

            if timestamp:
                if isinstance(timestamp, str):
                    timestamp_str = timestamp[:19].replace('T', ' ')
                else:
                    timestamp_str = timestamp.strftime('%Y-%m-%d %H:%M:%S')
            else:
                timestamp_str = ""

            cash_delta = -qty * price if action == "BUY" else qty * price

            trade_rows.append(f"""
            <tr>
                <td>{timestamp_str}</td>
                <td>{html_escape(action)}</td>
                <td>{html_escape(symbol)}</td>
                <td class="right">{qty:.4f}</td>
                <td class="right">${price:,.2f}</td>
                <td class="right">${cash_delta:,.2f}</td>
            </tr>
            """)

        trades_table = f"""
        <h4>Trade History — {html_escape(provider_name)}</h4>
        <table>
            <thead>
                <tr>
                    <th>Timestamp</th>
                    <th>Action</th>
                    <th>Symbol</th>
                    <th class="right">Qty</th>
                    <th class="right">Price</th>
                    <th class="right">Cash Δ</th>
                </tr>
            </thead>
            <tbody>
                {"".join(trade_rows) if trade_rows else "<tr><td colspan='6'>No trades yet</td></tr>"}
            </tbody>
        </table>
        """

        provider_sections.append(f"""
        <h3>Positions — {html_escape(provider_name)}{heading_suffix}</h3>
        {positions_table}

        {summary_table}

        {trades_table}
        """)

    # Strategy prompt section (collapsible)
    prompt_section = ""
    if strategy_prompt:
        prompt_section = f"""
    <details>
        <summary>Strategy Prompt</summary>
        <div class="details-content">
            <pre>{html_escape(strategy_prompt)}</pre>
        </div>
    </details>
    """

    body = f"""
    <p class="small"><a href="index.html">← Back to Leaderboard</a></p>
    <h1>{html_escape(name)}</h1>
    <p class="muted small">Strategy ID: {html_escape(strategy_id)}</p>

    {prompt_section}

    <h2>Provider Portfolios</h2>
    <table>
      <thead>
        <tr>
          <th>Provider</th>
          <th class="right">Portfolio Value</th>
          <th class="right">Return</th>
          <th>Updated</th>
        </tr>
      </thead>
      <tbody>
        {"".join(provider_summary_rows) if provider_summary_rows else '<tr><td colspan="4" class="muted">No provider portfolios yet</td></tr>'}
      </tbody>
    </table>

    {"".join(provider_sections)}

    <p class="small"><a href="index.html">← Back to Leaderboard</a></p>
    """

    return render_html_page(f"{name}", body)


def render_activity_feed(
    orders: list[dict[str, Any]],
    strategy_id_to_name: dict[str, str]
) -> str:
    """Render activity feed grouped by date.

    Args:
        orders: List of recent orders
        strategy_id_to_name: Mapping of strategy IDs to names

    Returns:
        Complete HTML page
    """
    # Group by date
    by_date: dict[str, list[dict[str, Any]]] = {}
    for order in orders:
        placed_at = order.get("placed_at")
        if placed_at:
            if isinstance(placed_at, str):
                date_key = placed_at[:10]  # Extract YYYY-MM-DD from ISO
            else:
                date_key = placed_at.strftime('%Y-%m-%d')
            if date_key not in by_date:
                by_date[date_key] = []
            by_date[date_key].append(order)

    # Sort dates descending
    sorted_dates = sorted(by_date.keys(), reverse=True)

    # Build date groups
    date_sections = []
    for date_key in sorted_dates[:30]:  # Last 30 days
        orders_for_date = by_date[date_key]

        rows = []
        for order in orders_for_date:
            strategy_id = order.get("strategy_id", "")
            strategy_name = strategy_id_to_name.get(strategy_id, "Unknown")
            provider_name = PROVIDER_NAMES.get(order.get("provider_id", ""), order.get("provider_id", ""))
            action = order.get("action", "")
            symbol = order.get("symbol", "")
            qty = float(order.get("quantity", 0))
            price_val = order.get("price")
            price = float(price_val) if price_val is not None else 0.0
            rationale = order.get("rationale", "")

            # Make strategy name a clickable link to the strategy detail page
            if strategy_id:
                strategy_link = f'<a href="strategy-{html_escape(strategy_id)}.html">{html_escape(strategy_name)}</a>'
            else:
                strategy_link = html_escape(strategy_name)

            rows.append(f"""
            <tr>
                <td>{strategy_link}</td>
                <td>{html_escape(provider_name)}</td>
                <td>{html_escape(action)}</td>
                <td>{html_escape(symbol)}</td>
                <td>{qty:.2f}</td>
                <td>${price:,.2f}</td>
            </tr>
            <tr>
                <td colspan="6" class="rationale">{html_escape(rationale)}</td>
            </tr>
            """)

        date_sections.append(f"""
        <div class="date-group">
            <h2>{date_key}</h2>
            <table>
                <thead>
                    <tr>
                        <th>Strategy</th>
                        <th>Provider</th>
                        <th>Action</th>
                        <th>Symbol</th>
                        <th>Qty</th>
                        <th>Price</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(rows)}
                </tbody>
            </table>
        </div>
        """)

    body = f"""
    <h1>Activity Feed</h1>
    <p class="meta">
        <a href="index.html">← Back to Leaderboard</a>
    </p>

    {"".join(date_sections) if date_sections else "<p>No recent activity</p>"}
    """

    return render_html_page("Activity Feed", body)


def render_weekly_email(
    title: str,
    hero_text: str,
    sections: list[tuple[str, str]],
    generated_at: datetime
) -> str:
    """Render email-optimized HTML with inline styles.

    Args:
        title: Email title
        hero_text: Hero summary text
        sections: List of (section_title, section_html) tuples
        generated_at: Generation timestamp

    Returns:
        Complete HTML email
    """
    section_html = []
    for section_title, section_content in sections:
        section_html.append(f"""
        <div style="margin: 32px 0;">
            <h2 style="color: #0366d6; border-bottom: 1px solid #e1e4e8; padding-bottom: 8px;">
                {html_escape(section_title)}
            </h2>
            {section_content}
        </div>
        """)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html_escape(title)}</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif; max-width: 640px; margin: 0 auto; padding: 20px; line-height: 1.6; color: #24292e;">
    <div style="background-color: #f6f8fa; padding: 24px; border-radius: 6px; margin-bottom: 24px;">
        <h1 style="margin: 0 0 12px 0; color: #24292e;">{html_escape(title)}</h1>
        <p style="margin: 0; font-size: 16px; color: #586069;">{html_escape(hero_text)}</p>
    </div>

    {"".join(section_html)}

    <div style="margin-top: 48px; padding-top: 24px; border-top: 1px solid #e1e4e8; color: #586069; font-size: 14px;">
        <p>Generated: {generated_at.strftime('%Y-%m-%d %H:%M UTC')}</p>
    </div>
</body>
</html>
"""


__all__ = [
    "PROVIDER_NAMES",
    "base_css",
    "render_activity_feed",
    "render_html_page",
    "render_leaderboard",
    "render_strategy_detail",
    "render_weekly_email",
]
