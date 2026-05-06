# Agent Test Scenarios

Tests for `collection_analysis_agent` covering all tool paths, boundary cases,
and agent behaviors. Run via `uv run adk web` then paste each question.

---

## Category 1 — Predefined Tools (Happy Path)

These should trigger a single predefined tool with no schema lookup needed.

### S1 · Visit KPIs
**Question:**
```
Tampilkan ringkasan KPI kunjungan bulan Januari 2025
```
**Expected flow:**
1. Identifies: visit summary → `tool_visit_kpis`
2. Calls: `tool_visit_kpis(report_start="2025-01-01", report_end="2025-01-31")`
3. Returns: table with total_visits, unique_contracts, active_collectors,
   paid_count, ptp_count, field_collected_idr, overall_conversion_pct
4. Adds 2–4 sentence summary with key insight (e.g. conversion rate vs benchmark)

---

### S2 · DPD Aging
**Question:**
```
Bagaimana distribusi aging DPD untuk Q1 2025?
```
**Expected flow:**
1. Identifies: DPD aging → `tool_dpd_aging`
2. Calls: `tool_dpd_aging(report_start="2025-01-01", report_end="2025-03-31")`
3. Returns: table grouped by collection_segment + dpd_bucket, ordered EARLY→NPL→WO
4. Summary highlights which segment/bucket carries most overdue exposure

---

### S3 · Branch Performance
**Question:**
```
Ranking performa cabang bulan Februari 2025, urutkan dari yang terbaik
```
**Expected flow:**
1. Identifies: branch ranking → `tool_branch_performance`
2. Calls: `tool_branch_performance(report_start="2025-02-01", report_end="2025-02-28")`
3. Returns: table sorted by conversion_rate_pct DESC
4. Summary notes best/worst branch and gap between them

---

### S4 · PTP Fulfillment
**Question:**
```
Berapa tingkat fulfillment PTP di Maret 2025? Berapa yang broken?
```
**Expected flow:**
1. Identifies: PTP analysis → `tool_ptp_fulfillment`
2. Calls: `tool_ptp_fulfillment(report_start="2025-03-01", report_end="2025-03-31")`
3. Returns: total_ptp, fulfilled_count, broken_count, pending_count,
   fulfillment_rate_pct, total_promised_idr, broken_exposure_idr
4. Summary flags broken exposure amount as actionable risk

---

### S5 · Visit Outcome Distribution
**Question:**
```
Apa saja hasil kunjungan lapangan di Januari dan berapa persentasenya?
```
**Expected flow:**
1. Identifies: outcome breakdown → `tool_visit_outcome_breakdown`
2. Calls: `tool_visit_outcome_breakdown(report_start="2025-01-01", report_end="2025-01-31")`
3. Returns: 7 rows (PAID, PTP, NOT_HOME, REFUSE, MOVED, UNIT_FOUND, UNIT_NOT_FOUND)
   each with visit_count + pct_of_total
4. Summary notes productive vs unproductive outcomes

---

### S6 · Collector Ranking with top_n
**Question:**
```
Siapa 5 kolektor terbaik berdasarkan conversion rate di Q1 2025?
```
**Expected flow:**
1. Identifies: collector ranking, user asks for top 5 → `tool_visit_collector_ranking`
2. Calls: `tool_visit_collector_ranking(report_start="2025-01-01", report_end="2025-03-31", top_n="5")`
3. Returns: 5 rows with collector_id, name, branch, position, visits, paid/ptp, collected_idr, conversion_pct
4. **Key check:** top_n parameter is passed as "5" (not default 10)

---

### S7 · Daily Trend
**Question:**
```
Tunjukkan tren kunjungan harian di bulan Februari 2025
```
**Expected flow:**
1. Identifies: daily trend → `tool_visit_daily_trend`
2. Calls: `tool_visit_daily_trend(report_start="2025-02-01", report_end="2025-02-28")`
3. Returns: 28 rows, one per day, with total_visits + conversion_rate_pct
4. Summary notes any spikes (salary cycle days 25–5) or low-activity days

---

### S8 · Payment Channel Breakdown
**Question:**
```
Breakdown pembayaran berdasarkan channel di Januari 2025
```
**Expected flow:**
1. Identifies: payment channels → `tool_payment_channel_breakdown`
2. Calls: `tool_payment_channel_breakdown(report_start="2025-01-01", report_end="2025-01-31")`
3. Returns: table with payment_method, payment_channel, period_type,
   transaction_count, total_amount_idr — sorted by amount DESC
4. Summary notes dominant channel and salary cycle vs normal split

---

### S9 · Field Collection by Collector
**Question:**
```
Siapa kolektor yang paling banyak mengumpulkan cash langsung di Q1 2025?
```
**Expected flow:**
1. Identifies: field cash → `tool_payment_by_collector`
2. Calls: `tool_payment_by_collector(report_start="2025-01-01", report_end="2025-03-31")`
3. Returns: collector ranked by total_collected_idr (CASH_FIELD only)
4. **Key check:** only CASH_FIELD payments, not all payment methods

---

### S10 · Contract Payment History
**Question:**
```
Tampilkan riwayat pembayaran untuk kontrak KTR-2023-00001
```
**Expected flow:**
1. Identifies: single contract lookup → `tool_payment_contract_history`
2. Calls: `tool_payment_contract_history(contract_no="KTR-2023-00001")`
3. Returns: all payment rows for that contract, ordered by payment_date ASC
4. **Key check:** no date range parameters — only contract_no

---

## Category 2 — Ad-hoc SQL (LLM builds the query)

These questions don't match any predefined tool. The agent must use
`tool_list_tables` and/or `tool_schema_filter_values` then `postgres-execute-sql`.

### S11 · Custom filter question
**Question:**
```
Berapa jumlah kontrak di segment NPL dengan DPD bucket 91-120 yang sudah dikunjungi
tapi tidak bayar di bulan Februari 2025?
```
**Expected flow:**
1. Identifies: no predefined tool covers NPL+bucket+not-paid combination
2. Calls: `tool_schema_filter_values` → confirms `collection_segment='NPL'`,
   `dpd_bucket='91-120'`, `visit_result` values
3. Builds and calls: `postgres-execute-sql` with:
   ```sql
   SELECT COUNT(DISTINCT contract_no)
   FROM juris_fact_collection_field_visit_activity_today_odps
   WHERE collection_segment = 'NPL'
     AND dpd_bucket = '91-120'
     AND visit_result != 'PAID'
     AND activity_date BETWEEN '2025-02-01' AND '2025-02-28'
   ```
4. **Key check:** agent calls `tool_schema_filter_values` BEFORE writing SQL

---

### S12 · Schema discovery
**Question:**
```
Apa saja kolom yang tersedia di tabel payment history?
```
**Expected flow:**
1. Identifies: schema question → `tool_list_tables`
2. Calls: `tool_list_tables` (no parameters)
3. Returns: all tables with column names and types
4. Agent filters and presents the payment table columns specifically
5. **Key check:** no SQL needed, purely schema inspection

---

## Category 3 — Boundary & Edge Cases

### S13 · Ambiguous — missing date range
**Question:**
```
Berapa total kunjungan?
```
**Expected flow:**
1. Identifies: ambiguous — no date range specified
2. **Clarifies** before calling any tool:
   *"Untuk periode mana? Data tersedia Januari–Maret 2025."*
3. After user specifies → calls `tool_visit_kpis`
4. **Key check:** agent asks ONE focused question, does not guess a date range

---

### S14 · Out-of-date-range
**Question:**
```
Tampilkan data kunjungan bulan Juni 2025
```
**Expected flow:**
1. Identifies: June 2025 is outside Jan–Mar 2025 data scope
2. **Redirects** without calling any tool:
   *"Data yang tersedia hanya mencakup Januari–Maret 2025. Apakah Anda ingin
   melihat data Maret 2025 sebagai periode terbaru?"*
3. **Key check:** no tool call made, clear redirect with offer of nearest period

---

### S15 · Out-of-scope
**Question:**
```
Buatkan template email penagihan untuk nasabah DPD 90 hari
```
**Expected flow:**
1. Identifies: email drafting = out of scope
2. **Redirects** without calling any tool:
   *"Saya hanya dapat membantu analisis data dari collection_db..."*
3. Offers an in-scope alternative (e.g., "Apakah ingin saya tampilkan
   daftar nasabah DPD 91-120 yang belum bayar?")
4. **Key check:** no tool call made

---

### S16 · Invalid filter value (tests tool_schema_filter_values)
**Question:**
```
Berapa kunjungan dengan hasil LATE_PAYMENT di Januari 2025?
```
**Expected flow:**
1. Identifies: `visit_result = 'LATE_PAYMENT'` — suspiciously specific value
2. Calls: `tool_schema_filter_values` → sees valid values are PAID, PTP,
   NOT_HOME, REFUSE, MOVED, UNIT_FOUND, UNIT_NOT_FOUND
3. Informs user: *"Tidak ada visit_result 'LATE_PAYMENT'. Nilai yang tersedia:
   PAID, PTP, NOT_HOME, REFUSE, MOVED..."*
4. **Key check:** agent validates before executing, does not silently return 0 rows

---

### S17 · SQL error recovery
**Question:**
```
Tampilkan total outstanding per kolektor di Maret 2025
```
**Expected flow:**
1. Identifies: no predefined tool → ad-hoc
2. May attempt a SQL joining visit table to user dim on collector_id
3. If first attempt returns an error (e.g., wrong column name) →
   calls `tool_list_tables` → retries with corrected column names
4. **Key check:** agent retries automatically, does not ask user to rephrase

---

## Category 4 — Multi-tool / Complex

### S18 · Multi-tool report
**Question:**
```
Buat ringkasan eksekutif performa collection bulan Januari 2025:
KPI kunjungan, aging DPD, dan performa cabang
```
**Expected flow:**
1. Identifies: three separate report sections needed
2. Calls sequentially:
   - `tool_visit_kpis(2025-01-01, 2025-01-31)`
   - `tool_dpd_aging(2025-01-01, 2025-01-31)`
   - `tool_branch_performance(2025-01-01, 2025-01-31)`
3. Assembles results into a structured executive summary
4. **Key check:** three tool calls, results combined into one coherent response

---

## Quick Reference: Tool → Trigger

| Tool | Trigger keywords |
|---|---|
| `tool_visit_kpis` | KPI kunjungan, ringkasan kunjungan, conversion rate total |
| `tool_dpd_aging` | aging, distribusi DPD, outstanding per bucket |
| `tool_branch_performance` | performa cabang, ranking cabang |
| `tool_ptp_fulfillment` | PTP, janji bayar, fulfillment, broken PTP |
| `tool_visit_outcome_breakdown` | hasil kunjungan, distribusi outcome, NOT_HOME berapa |
| `tool_visit_collector_ranking` | kolektor terbaik, ranking kolektor, top N |
| `tool_visit_daily_trend` | tren harian, per hari, time series kunjungan |
| `tool_payment_channel_breakdown` | channel pembayaran, metode bayar, salary cycle |
| `tool_payment_by_collector` | kolektor cash, field collection, kolektor tagih tunai |
| `tool_payment_contract_history` | riwayat bayar kontrak, history kontrak [X] |
| `postgres-execute-sql` | custom/kombinasi filter, tidak ada tool yang cocok |
| `tool_list_tables` | kolom apa saja, struktur tabel, schema |
| `tool_schema_filter_values` | nilai valid untuk filter, sebelum WHERE clause |
