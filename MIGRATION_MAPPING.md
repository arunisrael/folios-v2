# Schema Migration Mapping: folios-py → folios-v2

## OLD SCHEMA (folios-py)
```
id: "strategy_xxx" (string)
name: string
prompt: text
tickers: JSON string array
status: string
risk_controls: JSON string
metadata: JSON string
screener: JSON string
schedule: cron string (e.g., "0 0 8 * * *")
options_enabled: boolean
short_enabled: boolean
is_active: boolean
is_live: boolean
initial_capital_usd: float
portfolio_value_usd: float
performance: JSON
user_id: string
created_at: datetime
updated_at: datetime
```

## NEW SCHEMA (folios-v2)
```
id: UUID
name: string
prompt: string
tickers: array[string]
status: string
risk_controls: object | null
metadata: object | null
preferred_providers: array
active_modes: array[string]
screener: object | null
research_day: int (1-5)
research_time_utc: time | null
runtime_weight: float
created_at: datetime (ISO format)
updated_at: datetime (ISO format)
```

## FIELD MAPPINGS

### Direct Mappings (no transformation needed)
- `name` → `name`
- `prompt` → `prompt`
- `status` → `status`

### Transformations Required

#### 1. ID Mapping
- OLD: `"strategy_bd6b5423"` (string)
- NEW: Generate new UUID
- **Action**: Create UUID, maintain old ID as reference

#### 2. Tickers
- OLD: JSON string `'["AAPL", "MSFT"]'`
- NEW: Array `["AAPL", "MSFT"]`
- **Action**: Parse JSON and use as-is

#### 3. Risk Controls
- OLD: JSON string with structure:
  ```json
  {
    "max_position_size": float,
    "max_exposure": float,
    "stop_loss": float,
    "max_leverage": float,
    "max_short_exposure": float | null,
    "max_single_name_short": float | null,
    "borrow_available": bool | null
  }
  ```
- NEW: Same structure as object
- **Action**: Parse JSON, validate ranges (0-100 for percentages)

#### 4. Metadata
- OLD fields: `description`, `category`, `time_horizon`, `risk_level`, `market_conditions`, `key_metrics`, `key_signals`, `rationale`
- NEW fields: `description`, `theme`, `time_horizon`, `risk_level`, `key_metrics`, `key_signals`
- **Mapping**:
  - `description` → `description` (required)
  - `category` → `theme` (rename)
  - `time_horizon` → `time_horizon`
  - `risk_level` → `risk_level`
  - `key_metrics` (list) → `key_metrics` (tuple)
  - `key_signals` (list) → `key_signals` (tuple)
  - DROP: `market_conditions`, `rationale`

#### 5. Screener
- OLD fields: `enabled`, `provider`, `limit`, `filters`, `rationale`
- NEW fields: `enabled`, `provider`, `limit`, `filters`, `universe_cap` (optional)
- **Mapping**:
  - `enabled` → `enabled`
  - `provider` → `provider`
  - `limit` → `limit`
  - `filters` → `filters`
  - DROP: `rationale`
  - ADD: `universe_cap: null`

#### 6. Research Day
- OLD: `schedule` cron string (e.g., "0 0 8 * * *")
- NEW: `research_day` int (1-5, Monday-Friday)
- **Action**: Default to 4 (Thursday) for all

### Fields to Drop (don't exist in new schema)
- `schedule`
- `options_enabled`
- `short_enabled`
- `is_active`
- `is_live`
- `initial_capital_usd`
- `portfolio_value_usd`
- `performance`
- `user_id`

### New Required Fields (add with defaults)
- `preferred_providers`: `[]` (empty array)
- `active_modes`: `["batch"]`
- `research_time_utc`: `null`
- `runtime_weight`: `1.0`
- `created_at`: Use old `created_at` or current timestamp
- `updated_at`: Use old `updated_at` or current timestamp

## DATABASE STRUCTURE

### folios-v2 Table Structure
```sql
CREATE TABLE strategies (
    id VARCHAR NOT NULL,           -- UUID string
    name VARCHAR NOT NULL,          -- Strategy name
    status VARCHAR NOT NULL,        -- Status
    payload JSON NOT NULL,          -- Complete Strategy object as JSON
    PRIMARY KEY (id)
);
```

The `payload` column contains the ENTIRE Strategy object including `id`, `name`, and `status` again.
