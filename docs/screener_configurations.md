# Strategy Screener Configurations

## Overview

This document describes the customized FMP screener configurations for all 76 investment strategies. Each strategy has been analyzed and assigned appropriate screener filters based on its investment philosophy and target universe.

## FMP Screener Capabilities

### Supported Filters

The FMP screener supports the following parameters:

- `market_cap_min` / `market_cap_max`: Market capitalization range (in dollars)
- `price_min` / `price_max`: Stock price range
- `avg_vol_min` / `avg_vol_max`: Average trading volume range
- `pe_min` / `pe_max`: Price-to-Earnings ratio range
- `sector`: Specific sector (e.g., "Technology", "Financial Services", "Healthcare")
- `industry`: Specific industry within a sector
- `exchange`: Stock exchange (e.g., "NASDAQ", "NYSE")

### API Limits

Testing confirmed that FMP supports limits up to at least 1,000 results per query. We use conservative limits optimized for each strategy category:

- **Deep Value**: 300 (needs large candidate pool for further AI filtering on P/B, D/E ratios)
- **Value**: 300 (similar to deep value)
- **Dividend**: 200 (moderate pool for yield-focused selection)
- **Quality**: 150 (fewer but higher-quality candidates)
- **Growth**: 100 (specific criteria already narrows universe significantly)
- **Momentum**: 150 (high volume filters + AI momentum analysis)

## Strategy Categories

### Deep Value (3 strategies)

**Philosophy**: Seek extremely undervalued stocks, often small-cap, trading below book value or liquidation value.

**Template**:
```json
{
  "market_cap_min": 300000000,
  "price_min": 3,
  "avg_vol_min": 50000,
  "pe_max": 15
}
```

**Strategies**:
1. Benjamin Graham Cigar Butt Strategy
2. Cigar-Butt Deep Value
3. Walter Schloss Strategy

**Rationale**: Lower market cap and price minimums to capture smaller, potentially overlooked companies. Strict P/E limit to focus on deep discounts. Higher limit (300) provides AI with enough candidates to apply additional value metrics (P/B, debt ratios, etc.).

---

### Growth (13 strategies)

**Philosophy**: Invest in companies with strong revenue/earnings growth potential, often in technology and innovation sectors.

**Template**:
```json
{
  "market_cap_min": 10000000000,
  "price_min": 10,
  "avg_vol_min": 500000,
  "sector": "Technology" (when applicable)
}
```

**Strategies**:
1. Cathie Wood Strategy
2. Growth Investing
3. Growth at Reasonable Price
4. High-Dividend Investing (note: miscategorized, should be dividend)
5. Jesse Livermore Strategy
6. Momentum Trading
7. Nicolas Darvas Strategy
8. Pat Dorsey Strategy
9. Peter Lynch Small Cap Strategy
10. Peter Lynch Strategy
11. Philip Fisher Strategy
12. Terry Smith Strategy
13. Thomas Rowe Price Jr Strategy

**Rationale**: Large-cap focus ($10B+) for established growth companies. No P/E limit as growth stocks typically trade at higher multiples. Technology sector filter for relevant strategies. Lower limit (100) since criteria are already selective.

---

### Dividend (4 strategies)

**Philosophy**: Focus on income generation through companies with strong dividend yields and consistent payment history.

**Template**:
```json
{
  "market_cap_min": 1000000000,
  "price_min": 10,
  "avg_vol_min": 200000,
  "pe_max": 25
}
```

**Strategies**:
1. Carl Icahn Corporate Raider Strategy (focuses on dividend recapitalizations)
2. Geraldine Weiss Strategy
3. Income
4. Joel Greenblatt Strategy (Magic Formula - considers earnings yield)

**Rationale**: Mid/large-cap companies ($1B+) for stability. Moderate P/E limit to avoid overvalued dividend traps. Medium limit (200) to allow AI to further filter by dividend yield, payout ratio, and dividend growth.

---

### Momentum (4 strategies)

**Philosophy**: Capitalize on price trends and trading volume patterns.

**Template**:
```json
{
  "market_cap_min": 1000000000,
  "price_min": 5,
  "avg_vol_min": 1000000
}
```

**Strategies**:
1. Cliff Asness Strategy (quantitative factor-based)
2. Factor-Based Investing
3. Momentum
4. William O'Neil Strategy (CAN SLIM)

**Rationale**: High volume requirement (1M+) ensures liquid stocks suitable for momentum trading. No P/E restrictions as momentum strategies focus on price action. Technology sector filter for William O'Neil (NASDAQ-focused).

---

### Quality (49 strategies)

**Philosophy**: Invest in high-quality companies with strong moats, consistent profitability, and excellent management.

**Template**:
```json
{
  "market_cap_min": 2000000000,
  "price_min": 10,
  "avg_vol_min": 300000
}
```

**Sample Strategies**:
- Warren Buffett Strategy & Warren Buffett Quality Growth Strategy
- Charlie Munger Strategy
- Seth Klarman Strategy
- Howard Marks Strategy
- Ray Dalio Strategy
- All activist investor strategies (Bill Ackman, Carl Icahn, Daniel Loeb, etc.)
- Most value-oriented hedge fund managers
- (Full list in data/strategy_screener_mapping.json)

**Rationale**: Mid/large-cap focus ($2B+) for established businesses with moats. Higher price and volume minimums ensure quality and liquidity. No P/E limit as quality stocks may trade at premiums. Moderate limit (150) for comprehensive analysis.

**Sector Customizations**:
- Financial Services: Buffett, Munger, Ackman, Ray Dalio, George Soros, Quant strategies
- Technology: Bill Miller, Disruptive Innovation Growth
- Consumer Cyclical: Warren Buffett Quality Growth

---

### Value (3 strategies)

**Philosophy**: Traditional value investing seeking undervalued stocks based on fundamentals, but not as extreme as deep value.

**Template**:
```json
{
  "market_cap_min": 500000000,
  "price_min": 5,
  "avg_vol_min": 100000,
  "pe_max": 20
}
```

**Strategies**:
1. Jacob Little Strategy
2. Martin Whitman Strategy
3. Value (generic value strategy)

**Rationale**: Broader market cap range (500M+) than deep value but still focused on smaller opportunities. P/E limit of 20 for value focus. Higher limit (300) provides AI with candidates to apply additional fundamental metrics.

---

## Special Cases and Customizations

### Sector-Specific Strategies

Several strategies have been assigned sector filters based on their known focus areas:

- **Technology**: Cathie Wood, Bill Miller, Growth strategies, William O'Neil
- **Financial Services**: Buffett/Munger, Ray Dalio, Soros, Ackman, quant strategies
- **Consumer Cyclical**: Buffett Quality Growth (consumer brands focus)

### Exchange-Specific

Currently no exchange-specific filters are applied, but this could be added for:
- William O'Neil Strategy → NASDAQ (CAN SLIM methodology)

### Longevity & Healthspan Innovators (Finnhub Screener)

- **Provider**: Finnhub
- **Filters**:
  ```json
  {
    "country": "US",
    "market_cap_min": 5000000000,
    "price_min": 20,
    "avg_vol_min": 500000,
    "roe_min": 10,
    "beta_max": 1.4,
    "debt_to_equity_max": 2.0
  }
  ```
- **Limit**: 100 symbols (universe cap set to 500)
- **Purpose**: Surfaces profitable, liquid U.S. healthcare names with strong returns on equity, manageable leverage, and moderate volatility—aligned with the strategy’s focus on commercially validated longevity solutions.

### Strategies Without Current Screeners

Three strategies had no previous screener configuration:
1. Income
2. Momentum
3. Value

These have been configured with appropriate category templates.

---

## Migration Summary

### Changes by Strategy

**Increased Limits** (from 50 to 100-300):
- All strategies previously at limit=50 have been increased based on category

**Added P/E Filters**:
- Deep value strategies: pe_max=15
- Value strategies: pe_max=20
- Dividend strategies: pe_max=25

**Added Sector Filters**:
- 20+ strategies now have sector-specific filters

**Increased Market Cap Minimums**:
- Quality strategies: 500M → 2B (focus on established companies)
- Growth strategies: 500M → 10B (large-cap growth)
- Dividend strategies: 500M → 1B (stable dividend payers)

**Increased Volume Minimums**:
- Growth strategies: 100K → 500K (liquid large-caps)
- Quality strategies: 100K → 300K (established liquidity)
- Momentum strategies: 100K → 1M (highly liquid for trading)

### Expected Benefits

1. **Better Candidate Quality**: Filters now match investment philosophy
2. **Reduced AI Workload**: More relevant candidates mean less filtering needed
3. **Token Cost Savings**: Analyzing fewer irrelevant stocks
4. **Improved Recommendations**: AI focuses on appropriate universe for each strategy
5. **Clearer Strategy Differentiation**: Deep value gets small-caps, growth gets large-caps, etc.

---

## Usage

### View Current Configuration

```bash
python3 scripts/analyze_strategies_for_screeners.py
```

### Update Database (Dry Run)

```bash
python3 scripts/update_strategy_screeners.py
```

### Execute Update

```bash
python3 scripts/update_strategy_screeners.py --execute
```

### Test API Limits

```bash
uv run python scripts/test_fmp_limit.py
```

---

## Maintenance

### Adding New Strategies

When adding a new strategy, the analysis script (`analyze_strategies_for_screeners.py`) will automatically categorize it based on keywords in the strategy name and prompt. Categories are determined by:

1. Strategy name analysis
2. Prompt content analysis
3. Metadata theme analysis

The script uses priority ordering to ensure specific categories (like "deep value") are matched before broader categories (like "value").

### Updating Categories

To update how strategies are categorized, modify the `analyze_strategy()` function in `scripts/analyze_strategies_for_screeners.py`. The logic uses keyword matching with priority ordering.

### Modifying Templates

Screener templates are defined in the `SCREENER_TEMPLATES` and `LIMIT_BY_CATEGORY` dictionaries in `analyze_strategies_for_screeners.py`.

---

## Data Files

- `data/strategy_screener_mapping.json`: Complete mapping of strategies to screener configs
- `scripts/analyze_strategies_for_screeners.py`: Analysis and categorization logic
- `scripts/update_strategy_screeners.py`: Database update script
- `scripts/test_fmp_limit.py`: FMP API limit testing script

---

## Category Distribution

- Quality: 49 strategies (64%)
- Growth: 13 strategies (17%)
- Dividend: 4 strategies (5%)
- Momentum: 4 strategies (5%)
- Deep Value: 3 strategies (4%)
- Value: 3 strategies (4%)

**Total: 76 strategies**
