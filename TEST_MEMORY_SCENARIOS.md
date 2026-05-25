# Memory System: Test Scenarios

Complete test scenarios for the query correction feedback loop and memory persistence. All scenarios are runnable in sequence within the same or across sessions.

---

## Quick Setup

Before running tests, start infrastructure:

```bash
# Start Redis + Toolbox
cd mcp-toolbox && docker compose up -d && cd ..

# Start agent with persistence
uv run adk web \
  --session_service_uri="sqlite:///./sessions.db" \
  --memory_service_uri="redis://localhost:6379" \
  .
```

Access: `http://127.0.0.1:8000`

---

## Test Scenario 1: Basic Query Correction (Indonesian)

### Use Case
User makes a query with incorrect column/value names, receives feedback, and correction is stored for future use.

### Session 1: Initial Incorrect Query → Correction

**Step 1.1 — User asks question** (same session):
```
Tampilkan kunjungan dengan status = 'aktif' tahun ini
(Show visits with status = 'aktif' this year)
```

**Expected**: Agent generates SQL:
```sql
SELECT visit_id, collector_id, collection_status, visit_date, outcome 
FROM visits 
WHERE status = 'aktif' AND YEAR(visit_date) = 2025
```

**Step 1.2 — User corrects** (same session):
```
Salah! Harusnya pakai collection_status = 'ACTIVE', bukan status = 'aktif'
(Wrong! Should use collection_status = 'ACTIVE', not status = 'aktif')
```

**Agent behavior**:
- Detects correction signal: `temp:correction_detected = True`
- Calls `remember_query_correction()`:
  ```
  original_query: "SELECT ... WHERE status = 'aktif' ..."
  corrected_query: "SELECT ... WHERE collection_status = 'ACTIVE' ..."
  reason: "Column is collection_status. Values must be uppercase (ACTIVE, not aktif)."
  domain: "visits"
  ```
- Redis stores the correction

**Verify**:
```bash
docker exec adk_redis redis-cli HGETALL "corrections:collection_analysis_agent:*"
# Should show: original_query, corrected_query, reason, domain, timestamp
```

---

### Session 2: Correction Automatically Applied (New Browser Tab)

**Step 1.3 — New session, similar question**:
```
Tampilin kunjungan status aktif bulan Maret
(Show visits with status aktif in March)
```

**Agent behavior**:
- Calls `recall_corrections(query_context="visits")`
- Finds stored correction
- Generates SQL with `collection_status = 'ACTIVE'` (no trial-and-error)

**Expected result**: Correct query on first try ✓

---

## Test Scenario 2: Aggregated Summary Pattern

### Use Case
User wants individual data, then clarifies they need aggregated summary. Agent learns the "individual → grouped" pattern.

### Session 1: Individual Query → Grouped Summary

**Step 2.1 — Vague question**:
```
Tampilkan kolektor dan kunjungan mereka hari ini
(Show collectors and their visits today)
```

**Expected**: Agent generates listing with `LIMIT 20`:
```sql
SELECT 
    v.activity_date,
    v.contract_no,
    v.customer_name,
    v.visit_result,
    v.payment_amount,
    u.collector_name
FROM juris_fact_collection_field_visit_activity_today_odps v
JOIN juris_dim_user_odps u ON v.collector_id = u.collector_id
WHERE u.is_active = TRUE
ORDER BY v.activity_date DESC
LIMIT 20;
```

**Step 2.2 — User clarifies intent**:
```
Tidak, saya butuh ringkasan per kolektor - berapa total kunjungan, total bayar, dan success rate
(No, I need summary per collector - total visits, total payment, and success rate)
```

**Agent generates improved query**:
```sql
SELECT 
    u.collector_name,
    COUNT(*) as visit_count,
    SUM(v.payment_amount) as total_collected,
    COUNT(CASE WHEN v.visit_result = 'SUCCESS' THEN 1 END) as successful_visits,
    ROUND(
        COUNT(CASE WHEN v.visit_result = 'SUCCESS' THEN 1 END)::numeric / 
        COUNT(*) * 100, 2
    ) as success_rate_pct,
    MAX(v.activity_date) as last_activity
FROM juris_fact_collection_field_visit_activity_today_odps v
JOIN juris_dim_user_odps u ON v.collector_id = u.collector_id
WHERE u.is_active = TRUE
GROUP BY u.collector_id, u.collector_name
ORDER BY total_collected DESC;
```

**Agent calls**:
```
remember_query_correction(
    original_query="SELECT ... LIMIT 20",
    corrected_query="SELECT ... GROUP BY collector_id",
    correction_reason="User wants aggregated summary per collector (visit count, total payment, success rate), not individual visits",
    table_or_domain="collector_performance",
    ...
)
```

---

### Session 2: Aggregation Pattern Applied (New Browser Tab)

**Step 2.3 — Related question**:
```
Kolektor mana yang paling banyak collect hari ini?
(Which collector collected the most today?)
```

**Agent behavior**:
- Calls `recall_corrections(query_context="collector_performance")`
- Finds stored aggregation pattern
- **Generates grouped query directly** (no individual visits listing)

**Expected result**: Aggregated summary on first try ✓

---

## Test Scenario 3: Hybrid Two-Level Query (CTE Pattern)

### Use Case
User wants both summary and detail in one result using CTE pattern. This is the most complex memory scenario.

### Session 1: Individual → Hybrid with CTE

**Step 3.1 — Initial vague question**:
```
Tampilkan kunjungan kolektor hari ini dengan nama mereka
(Show collector visits today with their names)
```

**Expected**: Agent generates individual visits listing (LIMIT 20).

**Step 3.2 — User clarifies multi-level requirement**:
```
Tidak, saya butuh dua level - ringkasan total kunjungan dan bayar per kolektor, tapi juga detail individual visits di bawahnya dalam satu hasil
(No, I need two levels - summary of total visits and payments per collector, but also individual visit details below it in one result)
```

**Agent generates hybrid CTE query**:
```sql
WITH collector_summary AS (
    SELECT 
        u.collector_id,
        u.collector_name,
        COUNT(v.id) AS total_visits,
        SUM(COALESCE(v.payment_amount, 0)) AS total_collected_idr,
        ROUND(100.0 * COUNT(CASE WHEN v.visit_result = 'PAID' THEN 1 END) / 
              NULLIF(COUNT(v.id), 0), 2) AS success_rate_percent
    FROM juris_dim_user_odps u
    LEFT JOIN juris_fact_collection_field_visit_activity_today_odps v 
        ON u.collector_id = v.collector_id
    WHERE u.is_active = TRUE
    GROUP BY u.collector_id, u.collector_name
)
SELECT 
    cs.collector_name,
    cs.total_visits,
    cs.total_collected_idr,
    cs.success_rate_percent,
    v.activity_date,
    v.contract_no,
    v.customer_name,
    v.visit_result,
    v.payment_amount
FROM collector_summary cs
LEFT JOIN juris_fact_collection_field_visit_activity_today_odps v 
    ON cs.collector_id = v.collector_id
WHERE v.id IS NOT NULL
ORDER BY cs.total_collected_idr DESC, v.activity_date DESC
LIMIT 50;
```

**Step 3.3 — User confirms and saves pattern**:
```
Sempurna! Ini pola yang benar untuk analisis kolektor - dua level dengan CTE. 
Gunakan pola ini setiap kali dibutuhkan analisis kolektor dua-level: ringkasan + detail.
(Perfect! This is the correct pattern for collector analysis - two levels with CTE. 
Use this pattern whenever two-level collector analysis is needed: summary + detail.)
```

**Agent calls**:
```
remember_query_correction(
    original_query="SELECT ... FROM ... LIMIT 20",
    corrected_query="WITH collector_summary AS (...) SELECT cs.*, v.* FROM ...",
    correction_reason="Two-level collector analysis: CTE for summary, LEFT JOIN for individual visit details",
    table_or_domain="collector_visit_hybrid",
    ...
)
```

---

### Session 2: CTE Pattern Recalled (New Browser Tab)

**Step 3.4 — New session, similar complex request**:
```
Berapa kunjungan dan bayar per kolektor minggu ini? Saya juga butuh lihat detail visit masing-masing kolektor.
(How many visits and payment per collector this week? I also need to see detail of each collector's visits.)
```

**Agent behavior**:
- Calls `recall_corrections(query_context="collector_visit_hybrid")`
- Retrieves stored CTE pattern
- **Does NOT ask for clarification**
- Generates query with CTE + JOIN structure
- Uses `DATE_TRUNC('week', ...)` for weekly filter

**Expected result**: Two-level CTE query on first try ✓

---

## Test Scenario 4: Schema Discovery Caching

### Use Case
Agent learns table structure on first query, caches it for 7 days, avoiding repeated schema lookups.

### Session 1: First Query (Schema Lookup)

**Step 4.1 — User asks a question requiring schema discovery**:
```
Berapa rata-rata hari tunggakan per kolektor?
(What's the average days overdue per collector?)
```

**Agent behavior**:
- Calls `tool_list_tables` → discovers tables
- Calls `tool_schema_filter_values` for `debtors` table → discovers columns
- Generates SQL:
```sql
SELECT 
    c.collector_id, 
    c.name, 
    AVG(d.dpd_days) as avg_dpd
FROM collectors c
JOIN debtors d ON c.collector_id = d.collector_id
GROUP BY c.collector_id, c.name
ORDER BY avg_dpd DESC
```

**Agent calls** (after successful execution):
```
remember_schema_discovery(
    table_name="debtors",
    columns=["debtor_id", "collector_id", "dpd_days", "contract_status", ...],
    filter_values={"contract_status": ["AKTIF", "CLOSED", "SUSPENDED"]},
    ...
)
```

**Redis stores** (7-day TTL):
```
schema_cache:collection_analysis_agent:{user_id}:debtors
  columns: [...]
  filter_values: {...}
```

**Verify**:
```bash
docker exec adk_redis redis-cli TTL "schema_cache:collection_analysis_agent:*debtors"
# Should show ~604800 (7 days in seconds)
```

---

### Session 1: Same Table, Later Query (Cached)

**Step 4.2 — Different query, same table**:
```
Status debtor yang DPD > 90 hari
(Status of debtors with DPD > 90 days)
```

**Agent behavior**:
- **Skips** `tool_list_tables` ✓
- **Skips** `tool_schema_filter_values` ✓
- Uses cached schema to generate:
```sql
SELECT 
    contract_status, 
    COUNT(*) as count_debtors, 
    AVG(dpd_days) as avg_dpd
FROM debtors
WHERE dpd_days > 90 AND contract_status = 'AKTIF'
GROUP BY contract_status
```

**Expected result**: 2 schema tool calls → 0 schema tool calls (faster, cheaper) ✓

---

### Session 2: Cached Across Sessions (New Browser Tab)

**Step 4.3 — New session, same table**:
```
Berapa total debtors per contract status?
(How many debtors per contract status?)
```

**Agent behavior**:
- **Skips schema tools** (uses 7-day Redis cache)
- Generates SQL directly:
```sql
SELECT 
    contract_status, 
    COUNT(*) as count
FROM debtors
GROUP BY contract_status
```

**Expected result**: Schema tools NOT called (Redis recall) ✓

---

## Test Scenario 5: Business Vocabulary Memory

### Use Case
User defines business terms. Agent remembers definitions and uses them in future queries without disambiguation.

### Session 1: Term Definition

**Step 5.1 — User explains a term**:
```
Yang dimaksud DPD itu Days Past Due, jadi hari keterlambatan pembayaran dari due date
(DPD means Days Past Due, so the number of days a payment is late from the due date)
```

**Agent calls**:
```
remember_term(
    term="DPD",
    definition="Days Past Due",
    context="Number of days a payment is late from the agreed due date. Used in collection_db debtors table.",
    ...
)
```

**Redis stores** (90-day TTL):
```
vocabulary:collection_analysis_agent:{user_id}:dpd
  definition: "Days Past Due"
  context: "Number of days a payment is late..."
  timestamp: "2026-05-15T11:00:00"
```

---

### Session 1 or 2: Vocabulary Applied

**Step 5.2 — User asks question using defined term**:
```
Ranking kolektor by highest average DPD mereka yang handle
(Rank collectors by highest average DPD they handle)
```

**Agent behavior**:
- Recalls vocabulary: DPD = "Days Past Due"
- **Does NOT ask**: "Apa itu DPD?"
- Generates SQL confidently:
```sql
SELECT 
    c.collector_id, 
    c.name, 
    AVG(d.dpd_days) as avg_dpd
FROM collectors c
JOIN debtors d ON c.collector_id = d.collector_id
GROUP BY c.collector_id, c.name
ORDER BY avg_dpd DESC
LIMIT 10
```

**Expected result**: Clear business language, no disambiguation ✓

---

## Test Scenario 6: Error Pattern Memory

### Use Case
Agent encounters SQL error, remembers the wrong pattern and correct fix for future avoidance.

### Session 1: SQL Error Triggers Memory

**Step 6.1 — User asks question triggering SQL error**:
```
Berapa % DPD aging bucket OVER_90 dari total?
(What % of DPD aging bucket OVER_90 from total?)
```

**Agent generates** (incorrect):
```sql
SELECT 
    SUM(CASE WHEN dpd_aging_bucket = 'OVER_90' THEN 1 ELSE 0 END) / COUNT(*) * 100 as pct_over_90
FROM debtors
```

**Error**: `ERROR: column "dpd_aging_bucket" does not exist`

**Agent calls**:
```
remember_failed_pattern(
    wrong_pattern="dpd_aging_bucket",
    correct_pattern="CASE WHEN dpd_days > 90 THEN 'OVER_90' ELSE ... END",
    error_type="column_not_found",
    domain="debtors",
    ...
)
```

**Redis stores** (90-day TTL):
```
failed_patterns:collection_analysis_agent:{user_id}:uuid
  wrong_pattern: "dpd_aging_bucket"
  correct_pattern: "CASE WHEN dpd_days > 90 THEN..."
  error_type: "column_not_found"
  domain: "debtors"
```

---

### Session 2: Error Pattern Avoided (New Browser Tab)

**Step 6.2 — Similar question in new session**:
```
Berapa total DPD over 90?
(What's total DPD over 90?)
```

**Agent behavior**:
- Calls `recall_corrections` → finds error pattern
- **Avoids** `dpd_aging_bucket` column
- Generates correct SQL directly:
```sql
SELECT 
    COUNT(CASE WHEN dpd_days > 90 THEN 1 END) as count_over_90,
    COUNT(*) as total_debtors,
    ROUND(COUNT(CASE WHEN dpd_days > 90 THEN 1 END)::numeric / 
          COUNT(*) * 100, 2) as pct
FROM debtors
```

**Expected result**: Correct query on first try, error avoided ✓

---

## Test Scenario 7: User Preferences Persistence

### Use Case
User states format/verbosity preferences once. Agent applies them to all future responses.

### Session 1: Set Preferences

**Step 7.1 — User states preferences**:
```
Tolong pakai Rp format dengan separator ribuan, dan summary maksimal 2 baris
(Please use Rp format with thousand separators, and summary max 2 lines)
```

**Agent calls** (twice):
```
remember_preference(
    preference_category="currency_format",
    preference_value="Rp_with_separators",
    ...
)

remember_preference(
    preference_category="verbosity",
    preference_value="max_2_lines",
    ...
)
```

**Agent also sets state** (immediate availability):
```
tool_context.state["user:pref_currency_format"] = "Rp_with_separators"
tool_context.state["user:pref_verbosity"] = "max_2_lines"
```

**Redis stores** (persists):
```
prefs:collection_analysis_agent:{user_id}
  currency_format: "Rp_with_separators"
  verbosity: "max_2_lines"
```

---

### Session 2: Preferences Applied (New Browser Tab)

**Step 7.2 — Any data query**:
```
Total pembayaran bulan ini?
(Total payment this month?)
```

**Agent response**:
```
Total Rp 12.345.678 dari 42 contracts, 78% dari target.
(Before: "Total pembayaran Rp12345678 dari 42 contracts...")
```

**Expected result**: All responses follow stated preferences ✓

---

## Verification Checklist

### After Each Test Scenario

- [ ] **Terminal logs**: Agent called correct memory tool (`remember_*`, `recall_corrections`)
- [ ] **Redis key exists**: `docker exec adk_redis redis-cli KEYS "*:*:*" | grep pattern`
- [ ] **Data structure correct**: `docker exec adk_redis redis-cli HGETALL "key_name"`
- [ ] **TTL set** (if applicable): `docker exec adk_redis redis-cli TTL "key_name"`

### Cross-Session Verification

- [ ] **New browser tab** created (simulates new session)
- [ ] **Agent calls `recall_*` tools** in new session (visible in logs)
- [ ] **No re-iteration needed** (correction applied on first try)
- [ ] **No clarification asked** (agent remembers context)

---

## Troubleshooting Guide

### Correction Not Recalled in New Session

**Check**:
1. Redis running? `docker logs adk_redis | tail -5`
2. Correction stored? `docker exec adk_redis redis-cli KEYS "corrections:*"`
3. Agent calling `recall_corrections`? Search logs for function name
4. Domain matching? Ensure `table_or_domain` in remember = `query_context` in recall

### Schema Cache Not Reused

**Check**:
1. `remember_schema_discovery` called after successful query?
2. TTL set to 7 days? `docker exec adk_redis redis-cli TTL schema_cache:*`
3. Same `user_id` and `table_name` in both calls?

### Preferences Not Persisting

**Check**:
1. Both `tool_context.state` AND Redis written?
2. State key format: `user:pref_{category}`?
3. New session reading preferences? Check logs for loading

### Redis Connection Failed

**Check**:
```bash
docker exec adk_redis redis-cli PING
# Expected: PONG

docker logs adk_redis | tail -10
# Check for errors
```

---

## Learning Outcomes

This comprehensive test suite validates:

- **Correction feedback loop**: Capture wrong → correct patterns, apply to future queries
- **Schema caching**: Cache table structure for 7 days, avoid repeated schema lookups
- **Business vocabulary**: Remember user-defined terms, eliminate disambiguation
- **Error patterns**: Learn from SQL errors, avoid repeating mistakes
- **User preferences**: Persist format/verbosity choices across sessions
- **Cross-session memory**: Redis survives agent restarts and browser tab changes
- **Keyword search**: Match past corrections by domain and content

---

## Performance Baseline

```
Before memory:
  - First query: 3.0s (includes 2 schema lookups)
  - Similar query: 2.8s (schema still slow)

After memory (same session):
  - First query: 3.0s (initial cost)
  - Similar query: 1.0s (0 schema lookups, cached)

After memory (new session, cached):
  - Query: 1.5s (0 schema lookups, 1 correction recall)
```

Expected improvement: **50% faster queries** once cache/corrections are populated.
