---
name: visit-activity
description: "Visit activity deep-dive: outcome breakdown, collector ranking, daily trend."
metadata:
  adk_additional_tools:
    - tool_visit_outcome_breakdown
    - tool_visit_collector_ranking
    - tool_visit_daily_trend
---

## When to Use
- Outcome distribution across visit result types (PAID, NOT_HOME, REFUSE, etc.)
- Collector performance ranking (top N by conversion rate)
- Day-by-day visit volume or conversion trend

## Workflow
1. Confirm the date range. Must be within Jan–Mar 2025.
2. Match the question:
   - Outcome distribution → `tool_visit_outcome_breakdown`
   - Collector ranking → `tool_visit_collector_ranking` (clarify `top_n` if unspecified, default 10, max 50)
   - Daily trend → `tool_visit_daily_trend`
3. Call the tool. For `tool_visit_collector_ranking`, pass `top_n` as a string integer.
4. Present as a formatted table + 2–4 sentence summary.

## Tools

### tool_visit_outcome_breakdown

Distribution of all visit outcomes for a period: count and percentage share for each
visit_result (PAID, PTP, NOT_HOME, REFUSE, MOVED, UNIT_FOUND, UNIT_NOT_FOUND).
Use to understand visit effectiveness patterns.

#### Parameters

| Name | Type | Description | Required |
| :--- | :--- | :--- | :--- |
| report_start | string | Start date inclusive, format YYYY-MM-DD | Yes |
| report_end | string | End date inclusive, format YYYY-MM-DD | Yes |

---

### tool_visit_collector_ranking

Collector ranking by conversion rate: collector ID, name, branch, position, total
visits, paid/PTP counts, collected IDR, and conversion rate.
top_n controls how many rows to return (default: 10).

#### Parameters

| Name | Type | Description | Required |
| :--- | :--- | :--- | :--- |
| report_start | string | Start date inclusive, format YYYY-MM-DD | Yes |
| report_end | string | End date inclusive, format YYYY-MM-DD | Yes |
| top_n | string | Number of top collectors to return (default: 10, max: 50) | Yes |

---

### tool_visit_daily_trend

Day-by-day visit count and conversion rate trend for a period. Useful for spotting
high-activity days, salary-cycle spikes, or drops in field effort. Returns one row
per day ordered chronologically.

#### Parameters

| Name | Type | Description | Required |
| :--- | :--- | :--- | :--- |
| report_start | string | Start date inclusive, format YYYY-MM-DD | Yes |
| report_end | string | End date inclusive, format YYYY-MM-DD | Yes |
