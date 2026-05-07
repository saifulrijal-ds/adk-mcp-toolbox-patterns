---
name: collection-report
description: "Executive summary reports: visit KPIs, DPD aging, branch performance, PTP fulfillment."
metadata:
  adk_additional_tools:
    - tool_visit_kpis
    - tool_dpd_aging
    - tool_branch_performance
    - tool_ptp_fulfillment
---

## When to Use
- Period-level KPI summary or dashboard (visits, conversions, field-collected IDR)
- DPD aging analysis by segment or bucket (EARLY/NPL/WO)
- Branch performance comparison or ranking
- PTP commitment fulfillment rate or broken exposure

## Workflow
1. Confirm `report_start` and `report_end` (YYYY-MM-DD). If missing, ask one focused question. Must be within Jan–Mar 2025.
2. Match the question to a tool:
   - Overall KPIs → `tool_visit_kpis`
   - DPD aging by segment/bucket → `tool_dpd_aging`
   - Branch ranking → `tool_branch_performance`
   - PTP commitment tracking → `tool_ptp_fulfillment`
3. Call the tool with `report_start` and `report_end`.
4. Present as a formatted table + 2–4 sentence summary. Currency: "Rp X,XXX,XXX".

## Tools

### tool_visit_kpis

Visit KPIs for a reporting period: total visits, unique contracts, active collectors,
paid count, PTP count, field-collected IDR, and overall conversion rate.

#### Parameters

| Name | Type | Description | Required |
| :--- | :--- | :--- | :--- |
| report_start | string | Start date inclusive, format YYYY-MM-DD (e.g. '2025-01-01') | Yes |
| report_end | string | End date inclusive, format YYYY-MM-DD (e.g. '2025-01-31') | Yes |

---

### tool_dpd_aging

DPD aging snapshot: unique contracts, average DPD, total outstanding IDR, and total
overdue IDR — grouped by collection_segment and dpd_bucket, ordered by severity
(EARLY → NPL → WO, shortest to longest bucket).

#### Parameters

| Name | Type | Description | Required |
| :--- | :--- | :--- | :--- |
| report_start | string | Start date inclusive, format YYYY-MM-DD | Yes |
| report_end | string | End date inclusive, format YYYY-MM-DD | Yes |

---

### tool_branch_performance

Branch performance table: visits, unique contracts, paid/PTP counts, collected IDR,
and conversion rate — sorted best to worst.

#### Parameters

| Name | Type | Description | Required |
| :--- | :--- | :--- | :--- |
| report_start | string | Start date inclusive, format YYYY-MM-DD | Yes |
| report_end | string | End date inclusive, format YYYY-MM-DD | Yes |

---

### tool_ptp_fulfillment

PTP fulfillment analysis: total PTPs made, fulfilled/broken/pending counts, fulfillment
rate %, total promised IDR, fulfilled IDR, and broken exposure IDR. A PTP is fulfilled
if payment is received within 7 days of the promise date.

#### Parameters

| Name | Type | Description | Required |
| :--- | :--- | :--- | :--- |
| report_start | string | Start date inclusive, format YYYY-MM-DD | Yes |
| report_end | string | End date inclusive, format YYYY-MM-DD | Yes |
