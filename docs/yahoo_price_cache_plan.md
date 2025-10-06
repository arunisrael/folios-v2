# Yahoo Finance Price Cache Plan

## Background
- Current price fetcher logic in `folios/functions/src/services/price-fetcher.ts` calls the `yahoo-finance2` library on every request (live quote via `quoteSummary`, close price via `chart`).
- There is no caching layer; every execution retrieves fresh data directly from Yahoo.
- Executions occur within a 24-hour window, so quote freshness requirements can be satisfied with a TTL of "a few hours".

## Goal
Introduce a short-lived cache for Yahoo Finance quotes so we reuse price data fetched within the last few hours, reducing external calls while keeping prices fresh enough for daily execution runs.

## Requirements
- Cache storage lives in Firestore (Google Cloud Firestore already used by Cloud Functions) via a dedicated collection or table.
- Entries expire automatically after a configurable TTL (default 4 hours).
- Before hitting Yahoo, the price fetchers should check the cache.
- On cache miss/expiration, fetch from Yahoo, then store the result back in the cache.
- Support both live (`yahoo_live`) and close (`yahoo_close`) quote types.

## Proposed Data Model
Collection: `price_cache`

Document ID suggestion: `${symbol}_${source}` (e.g., `AAPL_yahoo_live`).

Fields:
- `symbol` (string)
- `source` (string enum: `yahoo_live` or `yahoo_close`)
- `price` (number)
- `timestamp` (Firestore timestamp of the quoted price)
- `fetched_at` (Firestore timestamp when we called Yahoo)
- `expires_at` (Firestore timestamp used for TTL)

Enable Firestore TTL on `expires_at` so Google automatically deletes expired documents.

## Implementation Steps
1. **Create cache utility module**
   - New file `folios/functions/src/services/price-cache.ts`.
   - Exports:
     - `async function getCachedPrice(symbol: string, source: PriceSource): Promise<PriceData | null>`
     - `async function writePrice(symbol: string, source: PriceSource, data: PriceData, ttlHours = 4): Promise<void>`
   - Internals:
     - Normalize keys (`symbol.toUpperCase()` etc.).
     - Fetch Firestore doc, verify `expires_at > now` before returning.
     - Convert stored timestamps back to JavaScript `Date`.
     - When writing, set `expires_at = fetched_at + ttlHours`.

2. **Integrate cache into price fetcher** (`price-fetcher.ts`)
   - Import the cache utilities.
   - `getYahooLivePrice` flow:
     1. Attempt to read cache (source `yahoo_live`).
     2. If hit, return cached data.
     3. On miss/expired, call Yahoo as today.
     4. Write the resulting quote to cache (use actual `timestamp` from Yahoo and `fetched_at = new Date()`).
     5. Also write close price to cache if we fall back to `getYahooClosePrice`.
   - `getYahooClosePrice` flow mirrors above with source `yahoo_close` (optional `targetDate` becomes part of cache key if needed; otherwise stick to latest close only).
   - `getBestAvailablePrice` continues to call live first then close; thanks to the cache helpers, second call will hit cache when appropriate.

3. **Optional stampede protection**
   - If concurrent executions are expected, consider a short “stale-while-revalidate” window. For an initial pass, relying on the TTL check is acceptable.

4. **Testing**
   - Use Firestore emulator or mocks to test cache reads/writes.
   - Unit tests for:
     - Cache hit returns stored data.
     - Expired entry triggers Yahoo fetch and writes new entry.
   - Update existing price fetcher tests to account for caching (mock Firestore).

5. **Operational Tasks**
   - Configure Firestore TTL on `price_cache.expires_at` via Firebase console or gcloud command.
   - Document new behavior and TTL expectation.
   - Optional metric/logging around cache hit rate for observability.

## Open Questions
- **Targeted close prices**: If we ever request historical closes for specific dates, we may need to include `targetDate` in cache keys (`${symbol}_${source}_${date}`). Current use cases appear to focus on latest prices, so initial implementation can omit this unless requirements change.
- **TTL configuration**: Encourage storing TTL hours in an env/config value (`PRICE_CACHE_TTL_HOURS`) to allow future adjustments without deploys.
- **Cold start behavior**: During first invocation (empty cache), we will still call Yahoo once per symbol; ensure rate limits are acceptable.

## Next Actions
1. Implement the `price-cache.ts` module with Firestore helpers.
2. Refactor `price-fetcher.ts` to use the cache before and after Yahoo calls.
3. Add/update tests around the new caching behavior.
4. Set up Firestore TTL and update documentation/configuration notes.
