"""HTML template rendering functions."""

from __future__ import annotations

from datetime import datetime
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


def base_css() -> str:
    """Return base CSS styles."""
    return """
    body {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
        max-width: 1200px;
        margin: 0 auto;
        padding: 20px;
        line-height: 1.6;
        color: #24292e;
    }
    h1 {
        border-bottom: 1px solid #e1e4e8;
        padding-bottom: 10px;
    }
    h2 {
        margin-top: 24px;
        color: #0366d6;
    }
    table {
        border-collapse: collapse;
        width: 100%;
        margin: 20px 0;
    }
    th, td {
        text-align: left;
        padding: 12px;
        border-bottom: 1px solid #e1e4e8;
    }
    th {
        background-color: #f6f8fa;
        font-weight: 600;
    }
    tr:hover {
        background-color: #f6f8fa;
    }
    .positive {
        color: #22863a;
    }
    .negative {
        color: #d73a49;
    }
    .strategy-link {
        color: #0366d6;
        text-decoration: none;
    }
    .strategy-link:hover {
        text-decoration: underline;
    }
    .date-group {
        margin-top: 32px;
        padding-top: 16px;
        border-top: 2px solid #e1e4e8;
    }
    .meta {
        color: #586069;
        font-size: 14px;
    }
    .rationale {
        font-style: italic;
        color: #586069;
        margin-top: 4px;
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
    portfolio_accounts: dict[str, list[dict[str, Any]]]
) -> str:
    """Render leaderboard HTML (index.html).

    Args:
        strategies: List of strategy dicts
        portfolio_accounts: Dict mapping strategy_id to list of portfolio accounts

    Returns:
        Complete HTML page
    """
    # Calculate returns for each strategy
    strategy_stats = []
    for strategy in strategies:
        sid = strategy["id"]
        name = strategy["name"]
        payload = strategy.get("payload", {})
        initial_capital = Decimal(str(payload.get("initial_capital_usd", 100000)))

        accounts = portfolio_accounts.get(sid, [])
        total_value = Decimal("0")
        for acc in accounts:
            cash = Decimal(str(acc.get("cash_balance", 0)))
            equity = Decimal(str(acc.get("equity_value", 0)))
            total_value += cash + equity

        if initial_capital > 0:
            return_pct = ((total_value - initial_capital) / initial_capital) * 100
        else:
            return_pct = Decimal("0")

        strategy_stats.append({
            "id": sid,
            "name": name,
            "total_value": total_value,
            "initial_capital": initial_capital,
            "return_pct": return_pct,
            "num_providers": len(accounts),
        })

    # Sort by return percentage (descending)
    strategy_stats.sort(key=lambda x: x["return_pct"], reverse=True)

    # Build table rows
    rows = []
    for i, stat in enumerate(strategy_stats, 1):
        return_class = "positive" if stat["return_pct"] >= 0 else "negative"
        return_sign = "+" if stat["return_pct"] >= 0 else ""

        rows.append(f"""
        <tr>
            <td>{i}</td>
            <td><a href="strategy-{html_escape(stat['id'])}.html" class="strategy-link">{html_escape(stat['name'])}</a></td>
            <td>${stat['total_value']:,.2f}</td>
            <td>${stat['initial_capital']:,.2f}</td>
            <td class="{return_class}">{return_sign}{stat['return_pct']:.2f}%</td>
            <td>{stat['num_providers']}</td>
        </tr>
        """)

    table_html = f"""
    <table>
        <thead>
            <tr>
                <th>Rank</th>
                <th>Strategy</th>
                <th>Total Value</th>
                <th>Initial Capital</th>
                <th>Return %</th>
                <th>Providers</th>
            </tr>
        </thead>
        <tbody>
            {"".join(rows)}
        </tbody>
    </table>
    """

    body = f"""
    <h1>Strategy Leaderboard</h1>
    <p class="meta">Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</p>
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
    payload = strategy.get("payload", {})
    initial_capital = Decimal(str(payload.get("initial_capital_usd", 100000)))

    # Build provider sections
    provider_sections = []
    for acc in portfolio_accounts:
        provider_id = acc["provider_id"]
        provider_name = PROVIDER_NAMES.get(provider_id, provider_id)

        cash = Decimal(str(acc.get("cash_balance", 0)))
        equity = Decimal(str(acc.get("equity_value", 0)))
        total_value = cash + equity

        positions = positions_by_provider.get(provider_id, [])
        trades = trade_history_by_provider.get(provider_id, [])

        # Positions table
        position_rows = []
        for pos in positions:
            symbol = pos["symbol"]
            qty = Decimal(str(pos.get("quantity", 0)))
            price = prices.get(symbol, Decimal("0"))
            market_value = qty * price
            avg_entry = pos.get("avg_entry_price")

            if avg_entry:
                unrealized_pl = (price - Decimal(str(avg_entry))) * qty
                pl_class = "positive" if unrealized_pl >= 0 else "negative"
                pl_sign = "+" if unrealized_pl >= 0 else ""
                pl_str = f'<span class="{pl_class}">{pl_sign}${unrealized_pl:,.2f}</span>'
            else:
                pl_str = "N/A"

            position_rows.append(f"""
            <tr>
                <td>{html_escape(symbol)}</td>
                <td>{qty:.2f}</td>
                <td>${price:,.2f}</td>
                <td>${market_value:,.2f}</td>
                <td>{pl_str}</td>
            </tr>
            """)

        positions_table = f"""
        <table>
            <thead>
                <tr>
                    <th>Symbol</th>
                    <th>Quantity</th>
                    <th>Price</th>
                    <th>Market Value</th>
                    <th>Unrealized P/L</th>
                </tr>
            </thead>
            <tbody>
                {"".join(position_rows) if position_rows else "<tr><td colspan='5'>No open positions</td></tr>"}
            </tbody>
        </table>
        """

        # Trade history (last 20)
        trade_rows = []
        for trade in trades[:20]:
            action = trade.get("action", "")
            symbol = trade.get("symbol", "")
            qty = trade.get("quantity", 0)
            price = trade.get("price", 0)
            timestamp = trade.get("timestamp")
            rationale = trade.get("rationale", "")

            if timestamp:
                if isinstance(timestamp, str):
                    timestamp_str = timestamp[:16].replace('T', ' ')  # ISO format to readable
                else:
                    timestamp_str = timestamp.strftime('%Y-%m-%d %H:%M')
            else:
                timestamp_str = ""

            trade_rows.append(f"""
            <tr>
                <td>{timestamp_str}</td>
                <td>{html_escape(action)}</td>
                <td>{html_escape(symbol)}</td>
                <td>{qty:.2f}</td>
                <td>${price:,.2f}</td>
                <td class="rationale">{html_escape(rationale)}</td>
            </tr>
            """)

        trades_table = f"""
        <table>
            <thead>
                <tr>
                    <th>Time</th>
                    <th>Action</th>
                    <th>Symbol</th>
                    <th>Quantity</th>
                    <th>Price</th>
                    <th>Rationale</th>
                </tr>
            </thead>
            <tbody>
                {"".join(trade_rows) if trade_rows else "<tr><td colspan='6'>No trades yet</td></tr>"}
            </tbody>
        </table>
        """

        provider_sections.append(f"""
        <div class="provider-section">
            <h2>{provider_name}</h2>
            <p><strong>Cash:</strong> ${cash:,.2f} | <strong>Equity:</strong> ${equity:,.2f} | <strong>Total:</strong> ${total_value:,.2f}</p>

            <h3>Open Positions</h3>
            {positions_table}

            <h3>Recent Trades</h3>
            {trades_table}
        </div>
        """)

    body = f"""
    <h1>{html_escape(name)}</h1>
    <p class="meta">
        <a href="index.html">← Back to Leaderboard</a> |
        <a href="feed.html">Activity Feed</a>
    </p>
    <p><strong>Initial Capital:</strong> ${initial_capital:,.2f}</p>

    {"".join(provider_sections)}
    """

    return render_html_page(f"{name} - Strategy Details", body)


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
            strategy_name = strategy_id_to_name.get(order.get("strategy_id", ""), "Unknown")
            provider_name = PROVIDER_NAMES.get(order.get("provider_id", ""), order.get("provider_id", ""))
            action = order.get("action", "")
            symbol = order.get("symbol", "")
            qty = float(order.get("quantity", 0))
            price_val = order.get("price")
            price = float(price_val) if price_val is not None else 0.0
            rationale = order.get("rationale", "")
            timestamp = order.get("placed_at")

            if timestamp:
                if isinstance(timestamp, str):
                    time_str = timestamp[11:16]  # Extract HH:MM from ISO
                else:
                    time_str = timestamp.strftime('%H:%M')
            else:
                time_str = ""

            rows.append(f"""
            <tr>
                <td>{time_str}</td>
                <td>{html_escape(strategy_name)}</td>
                <td>{html_escape(provider_name)}</td>
                <td>{html_escape(action)}</td>
                <td>{html_escape(symbol)}</td>
                <td>{qty:.2f}</td>
                <td>${price:,.2f}</td>
            </tr>
            <tr>
                <td colspan="7" class="rationale">{html_escape(rationale)}</td>
            </tr>
            """)

        date_sections.append(f"""
        <div class="date-group">
            <h2>{date_key}</h2>
            <table>
                <thead>
                    <tr>
                        <th>Time</th>
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
