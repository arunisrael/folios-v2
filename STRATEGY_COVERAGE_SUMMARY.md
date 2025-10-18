# Strategy Coverage Summary
**Date:** October 17, 2025

## Quick Stats

- **Total Strategies:** 80
- **Strategies with ZERO coverage:** 25 (31.25%) ⚠️
- **Strategies with PARTIAL coverage:** 26 (32.50%)
- **Strategies with FULL coverage:** 29 (36.25%) ✅

## Zero Coverage Strategies (Priority: CRITICAL)

These 25 strategies need immediate attention:

```
Cliff Asness Strategy
Contrarian Investing
Daniel Loeb Strategy
David Dreman Strategy
David Einhorn Strategy
David Shaw Strategy
David Tepper Strategy
Event-Driven Activism
Factor-Based Investing
George Soros Strategy
Geraldine Weiss Strategy
Global Macro Investing
Growth Investing
Growth at Reasonable Price
Low Volatility Defensive Equity Strategy
Martin Whitman Strategy
Mason Hawkins Strategy
Michael Price Strategy
Momentum Trading
Nelson Peltz Strategy
Nicolas Darvas Strategy
Pat Dorsey Strategy
Peter Lynch Small Cap Strategy
Peter Lynch Strategy
Quantitative Statistical Arbitrage
```

## Action Items

### Immediate (Today)
1. Export strategy IDs for the 25 zero-coverage strategies
2. Submit batch requests for all 3 providers (OpenAI, Gemini, Anthropic)
3. Monitor batch completion and harvest results

### This Week
1. Complete partial coverage by submitting missing providers for the 26 partial-coverage strategies
2. Implement weekday rotation to ensure ongoing coverage
3. Review and apply recommendations from batch results

### Ongoing
1. Maintain 100% coverage target (all strategies with 2-3 providers)
2. Track provider performance metrics per strategy type
3. Update coverage report weekly

## Files Generated

1. **STRATEGY_COVERAGE_REPORT.md** - Full detailed report with all strategy IDs and missing providers
2. **STRATEGY_COVERAGE.csv** - Machine-readable CSV for batch processing scripts

## Sample Commands

### Export zero-coverage strategy IDs to file:
```bash
sqlite3 folios_v2.db "SELECT id FROM strategies WHERE id NOT IN (SELECT DISTINCT strategy_id FROM orders);" > zero_coverage_strategies.txt
```

### Submit batch requests for zero-coverage strategies:
```bash
uv run python scripts/submit_batch_requests.py \
  --strategy-file zero_coverage_strategies.txt \
  --providers openai,gemini,anthropic
```

### Check batch status:
```bash
uv run python scripts/check_batch_status.py --all
```

---

**See STRATEGY_COVERAGE_REPORT.md for complete details**
