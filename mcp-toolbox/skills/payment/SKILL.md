---
name: payment
description: Payment analysis: channel breakdown, field collection by collector, contract history.
---

## Usage

All scripts can be executed using Node.js. Replace `<param_name>` and `<param_value>` with actual values.

**Bash:**
`node <skill_dir>/scripts/<script_name>.js '{"<param_name>": "<param_value>"}'`

**PowerShell:**
`node <skill_dir>/scripts/<script_name>.js '{\"<param_name>\": \"<param_value>\"}'`


## Scripts


### tool_payment_by_collector

Field cash collected per collector (CASH_FIELD payments only), ranked by total amount. Shows collector name, branch, transaction count, and total IDR.


#### Parameters

| Name | Type | Description | Required | Default |
| :--- | :--- | :--- | :--- | :--- |
| report_start | string | Start date inclusive, format YYYY-MM-DD | Yes |  |
| report_end | string | End date inclusive, format YYYY-MM-DD | Yes |  |


---

### tool_payment_channel_breakdown

Payment breakdown by method, channel, and period type (Salary Cycle = day 25–5 of month, Normal otherwise). Returns transaction count and total IDR sorted by amount descending.


#### Parameters

| Name | Type | Description | Required | Default |
| :--- | :--- | :--- | :--- | :--- |
| report_start | string | Start date inclusive, format YYYY-MM-DD | Yes |  |
| report_end | string | End date inclusive, format YYYY-MM-DD | Yes |  |


---

### tool_payment_contract_history

Full payment timeline for a single contract: all payments ordered by date, showing amount, method, channel, collector, and receipt number. Use when ops teams need to check a specific customer's payment record.


#### Parameters

| Name | Type | Description | Required | Default |
| :--- | :--- | :--- | :--- | :--- |
| contract_no | string | Contract number to look up (e.g. 'FIN-00123') | Yes |  |


---

