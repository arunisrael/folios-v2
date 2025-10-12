# Test Coverage Analysis

## Summary
- **Total Coverage**: 61% (3132 statements, 1022 missed)
- **Tests Passing**: 44 passed, 1 skipped
- **All test failures fixed**: ✅

## Critical Business Logic Not Covered by Tests

### 1. Market Data Service (0% coverage)
**File**: `src/folios_v2/market_data.py`
**Coverage**: 0% (41/41 statements missed)
**Business Logic**:
- Yahoo Finance integration for fetching current prices
- Price caching mechanism
- Batch price fetching
- Error handling for market data failures

**Risk**: High - This is critical for portfolio valuation and trade execution

### 2. Unified Parser (0% coverage)
**File**: `src/folios_v2/providers/unified_parser.py`
**Coverage**: 0% (74/74 statements missed)
**Business Logic**:
- Parses structured JSON responses from multiple providers
- Extracts buy/sell recommendations
- Validates recommendation schema
- Handles different provider response formats

**Risk**: High - Critical for converting LLM responses to actionable trades

### 3. Anthropic Direct Executor (14% coverage)
**File**: `src/folios_v2/providers/anthropic/direct_executor.py`
**Coverage**: 14% (68/82 statements missed)
**Business Logic**:
- Direct API integration with Anthropic
- Streaming response handling
- JSON extraction from markdown blocks
- Error handling for API failures

**Risk**: Medium - Alternative to CLI executor, but less tested

### 4. Screener Providers (16% coverage)
**Files**:
- `src/folios_v2/screeners/providers/finnhub.py` (16% coverage, 112/139 missed)
- `src/folios_v2/screeners/providers/fmp.py` (16% coverage, 77/99 missed)

**Business Logic**:
- Stock screening based on market cap, volume, sector filters
- API integration with Finnhub and FMP
- Screen result pagination
- Filter composition and validation

**Risk**: Medium - Important for strategy stock universe generation

### 5. OpenAI Batch Executor (41% coverage)
**File**: `src/folios_v2/providers/openai/batch.py`
**Coverage**: 41% (73/133 statements missed)
**Business Logic**:
- Batch request creation and submission
- Batch status polling
- Result harvesting
- Error handling for batch failures
- JSONL file generation

**Risk**: Medium - Used for async batch processing

### 6. Gemini Batch Executor (38% coverage)
**File**: `src/folios_v2/providers/gemini/batch.py`
**Coverage**: 38% (93/162 statements missed)
**Business Logic**:
- Similar to OpenAI batch but for Gemini API
- Long-running batch job management (24+ hour processing)
- State persistence across restarts

**Risk**: Medium - Alternative batch processing path

### 7. Prompt Builder (46% coverage)
**File**: `src/folios_v2/orchestration/prompt_builder.py`
**Coverage**: 46% (16/36 statements missed)
**Business Logic**:
- Constructs investment analysis prompts
- Includes market context and strategy details
- Formats screener results for LLM consumption

**Risk**: Medium - Affects quality of LLM inputs

### 8. Scheduling Calendar (50% coverage)
**File**: `src/folios_v2/scheduling/calendar.py`
**Coverage**: 50% (12/28 statements missed)
**Business Logic**:
- Determines if current time is within trading hours
- Handles market holiday detection
- Timezone conversions

**Risk**: Low - Nice to have, but not critical

### 9. SQLite Repositories (55% coverage)
**File**: `src/folios_v2/persistence/sqlite/repositories.py`
**Coverage**: 55% (109/276 statements missed)
**Business Logic**:
- CRUD operations for strategies, requests, orders, positions
- Complex query logic with filters
- Transaction management
- Cascading deletes

**Risk**: Medium - Database operations are critical, but many paths may be defensive

### 10. Memory Persistence (64% coverage)
**File**: `src/folios_v2/persistence/memory.py`
**Coverage**: 64% (55/185 statements missed)
**Business Logic**:
- In-memory repository implementation
- Used for testing
- Less critical for production

**Risk**: Low - Primarily for testing

## Recommendations

### High Priority (Should add tests)
1. **Market Data Service** - Add tests for:
   - Price fetching from Yahoo Finance
   - Caching behavior
   - Error handling for API failures
   - Batch price requests

2. **Unified Parser** - Add tests for:
   - Parsing responses from each provider (OpenAI, Gemini, Anthropic)
   - Extracting buy/sell recommendations
   - Handling malformed responses
   - Schema validation

### Medium Priority (Should consider adding tests)
3. **Screener Providers** - Add tests for:
   - Basic filtering logic
   - API response parsing
   - Error handling

4. **Batch Executors** - Add tests for:
   - Batch submission logic
   - Status polling behavior
   - Error recovery

5. **Prompt Builder** - Add tests for:
   - Prompt construction for different strategy types
   - Market context inclusion

### Low Priority (Can defer)
6. **CLI Integration Tests** - Current coverage is acceptable
7. **Scheduling Calendar** - Current coverage is acceptable
8. **In-memory Repositories** - Used for testing only

## Test Infrastructure Strengths
- Good test coverage for:
  - Domain models (complete coverage in many files)
  - Core orchestration logic (75%+)
  - Provider plugins and registry
  - HTML generation utilities
  - Unit of work pattern implementation

## Next Steps
1. Add integration tests for market data fetching
2. Add unit tests for unified parser with sample provider responses
3. Add tests for screener filter logic
4. Consider adding end-to-end tests for complete workflows
