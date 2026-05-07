---
name: visit-activity
description: Visit activity deep-dive: outcome breakdown, collector ranking, daily trend.
---

## Usage

All scripts can be executed using Node.js. Replace `<param_name>` and `<param_value>` with actual values.

**Bash:**
`node <skill_dir>/scripts/<script_name>.js '{"<param_name>": "<param_value>"}'`

**PowerShell:**
`node <skill_dir>/scripts/<script_name>.js '{\"<param_name>\": \"<param_value>\"}'`


## Scripts


### tool_visit_collector_ranking

Collector ranking by conversion rate: collector ID, name, branch, position, total visits, paid/PTP counts, collected IDR, and conversion rate. top_n controls how many rows to return (default: 10).


#### Parameters

| Name | Type | Description | Required | Default |
| :--- | :--- | :--- | :--- | :--- |
| report_start | string | Start date inclusive, format YYYY-MM-DD | Yes |  |
| report_end | string | End date inclusive, format YYYY-MM-DD | Yes |  |
| top_n | string | Number of top collectors to return (default: 10, max: 50) | Yes |  |


---

### tool_visit_daily_trend

Day-by-day visit count and conversion rate trend for a period. Useful for spotting high-activity days, salary-cycle spikes, or drops in field effort. Returns one row per day ordered chronologically.


#### Parameters

| Name | Type | Description | Required | Default |
| :--- | :--- | :--- | :--- | :--- |
| report_start | string | Start date inclusive, format YYYY-MM-DD | Yes |  |
| report_end | string | End date inclusive, format YYYY-MM-DD | Yes |  |


---

### tool_visit_outcome_breakdown

Distribution of all visit outcomes for a period: count and percentage share for each visit_result (PAID, PTP, NOT_HOME, REFUSE, MOVED, UNIT_FOUND, UNIT_NOT_FOUND). Use to understand visit effectiveness patterns.


#### Parameters

| Name | Type | Description | Required | Default |
| :--- | :--- | :--- | :--- | :--- |
| report_start | string | Start date inclusive, format YYYY-MM-DD | Yes |  |
| report_end | string | End date inclusive, format YYYY-MM-DD | Yes |  |


---

