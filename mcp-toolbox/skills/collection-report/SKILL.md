---
name: collection-report
description: Executive summary reports: visit KPIs, DPD aging, branch performance, PTP fulfillment.
---

## Usage

All scripts can be executed using Node.js. Replace `<param_name>` and `<param_value>` with actual values.

**Bash:**
`node <skill_dir>/scripts/<script_name>.js '{"<param_name>": "<param_value>"}'`

**PowerShell:**
`node <skill_dir>/scripts/<script_name>.js '{\"<param_name>\": \"<param_value>\"}'`


## Scripts


### tool_branch_performance

Branch performance table: visits, unique contracts, paid/PTP counts, collected IDR, and conversion rate — sorted best to worst.


#### Parameters

| Name | Type | Description | Required | Default |
| :--- | :--- | :--- | :--- | :--- |
| report_start | string | Start date inclusive, format YYYY-MM-DD | Yes |  |
| report_end | string | End date inclusive, format YYYY-MM-DD | Yes |  |


---

### tool_dpd_aging

DPD aging snapshot: unique contracts, average DPD, total outstanding IDR, and total overdue IDR — grouped by collection_segment and dpd_bucket, ordered by severity (EARLY → NPL → WO, shortest to longest bucket).


#### Parameters

| Name | Type | Description | Required | Default |
| :--- | :--- | :--- | :--- | :--- |
| report_start | string | Start date inclusive, format YYYY-MM-DD | Yes |  |
| report_end | string | End date inclusive, format YYYY-MM-DD | Yes |  |


---

### tool_ptp_fulfillment

PTP fulfillment analysis: total PTPs made, fulfilled/broken/pending counts, fulfillment rate %, total promised IDR, fulfilled IDR, and broken exposure IDR. A PTP is fulfilled if payment is received within 7 days of the promise date.


#### Parameters

| Name | Type | Description | Required | Default |
| :--- | :--- | :--- | :--- | :--- |
| report_start | string | Start date inclusive, format YYYY-MM-DD | Yes |  |
| report_end | string | End date inclusive, format YYYY-MM-DD | Yes |  |


---

### tool_visit_kpis

Visit KPIs for a reporting period: total visits, unique contracts, active collectors, paid count, PTP count, field-collected IDR, and overall conversion rate.


#### Parameters

| Name | Type | Description | Required | Default |
| :--- | :--- | :--- | :--- | :--- |
| report_start | string | Start date inclusive, format YYYY-MM-DD (e.g. '2025-01-01') | Yes |  |
| report_end | string | End date inclusive, format YYYY-MM-DD (e.g. '2025-01-31') | Yes |  |


---

