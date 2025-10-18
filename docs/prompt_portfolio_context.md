# Prompt Portfolio Context Design

## Goal
When we ask an AI provider for updated trade recommendations, the prompt should
include the provider’s current portfolio so the model can decide whether to
adjust, trim, or close existing positions rather than always proposing new
entries. Today the request pipeline only forwards the static strategy prompt,
so the provider lacks awareness of real positions or cash balance.

## Required Context Fields

For each `(strategy, provider)` tuple included in a prompt we will supply:

1. **Cash balance** — remaining available buying power in USD.
2. **Total equity value** — sum of open positions valued at current market
   prices.
3. **Open positions table**, containing for each holding:
   - Ticker symbol and side (`long` / `short`)
   - Quantity (shares)
   - Average entry price
   - Latest market price (from `folios_v2.market_data.get_current_prices`)
   - Current market value (quantity × latest price)
   - Unrealised P/L both absolute and percentage
   - Position weight as a percent of total portfolio value
4. **Exposure summary** — totals for gross exposure, net exposure, and leverage
   (derived from the equity and cash data above).
5. **Recent trades (optional)** — last N filled orders with timestamp, action,
   ticker, quantity, and price. Including this is optional in the initial
   rollout, but the data access layer will expose it for prompt rendering if we
   decide to surface it.

## Rendering Plan

The prompt builder will insert a “Current Portfolio Snapshot” section for each
provider. The section will include:

```
Current Portfolio Snapshot — {provider}
- Cash: ${cash_balance:,}
- Total positions value: ${equity_value:,}
- Net exposure: {net_pct:.1f}%   Gross exposure: {gross_pct:.1f}%   Leverage: {leverage:.2f}x

Ticker  Side   Qty   Avg Cost   Mkt Price   Value   P/L   Weight
```

Amounts will be rounded to sensible precision (two decimals for USD, two
decimals for percentages). Negative values will be prefixed with `-` but left
otherwise raw so the provider can parse them without extra adornment.

## Data Access Changes

To build this context, orchestration will:

1. Load `portfolio_accounts` for the target `(strategy, provider)` and derive
   cash/equity balances.
2. Pull open positions from the `positions` table, decode quantities/average
   prices from the JSON payload, and fetch latest prices for the symbols
   involved.
3. Optionally fetch the latest filled orders for context.
4. Package the results in a new `PortfolioSnapshot` dataclass so the prompt
   builder receives a clean, provider-agnostic structure.

## Prompt Integration

`build_research_prompt` will gain an optional `portfolio_snapshot` parameter.
When provided, the builder will prepend the snapshot section before the existing
recency and compliance instructions. The default behaviour (no snapshot) will
match today’s output so we can roll out the change strategy by strategy.

## Future Enhancements

- Include performance history (e.g., week-to-date P/L) once we have a reliable
  analytics feed.
- Surface pending orders separately from filled holdings so the provider is
  aware of queued trades.
- Add guardrails that flag when leverage or exposure limits are already maxed
  before passing the prompt downstream.
