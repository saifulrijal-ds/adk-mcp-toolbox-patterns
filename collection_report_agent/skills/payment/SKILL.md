---
name: payment
description: "Payment analysis: channel breakdown, field collection by collector, contract history."
metadata:
  adk_additional_tools:
    - tool_payment_channel_breakdown
    - tool_payment_by_collector
    - tool_payment_contract_history
---

## When to Use
- Payment method/channel breakdown (CASH, TRANSFER, salary-cycle detection)
- Field cash ranking by collector (CASH_FIELD payments only)
- Full payment history for a specific contract number

## Workflow
1. Identify the sub-question:
   - Channel/method breakdown → `tool_payment_channel_breakdown` (needs date range)
   - Field cash by collector → `tool_payment_by_collector` (needs date range)
   - Single contract history → `tool_payment_contract_history` (needs `contract_no`, no date range)
2. For date-range tools: confirm range within Jan–Mar 2025.
3. For `tool_payment_contract_history`: extract the contract number from the user's message; ask if missing.
4. Call the tool.
5. Present as a formatted table + 2–4 sentence summary. Currency: "Rp X,XXX,XXX".

## Tools

### tool_payment_channel_breakdown

Payment breakdown by method, channel, and period type (Salary Cycle = day 25–5 of
month, Normal otherwise). Returns transaction count and total IDR sorted by amount
descending.

#### Parameters

| Name | Type | Description | Required |
| :--- | :--- | :--- | :--- |
| report_start | string | Start date inclusive, format YYYY-MM-DD | Yes |
| report_end | string | End date inclusive, format YYYY-MM-DD | Yes |

---

### tool_payment_by_collector

Field cash collected per collector (CASH_FIELD payments only), ranked by total amount.
Shows collector name, branch, transaction count, and total IDR.

#### Parameters

| Name | Type | Description | Required |
| :--- | :--- | :--- | :--- |
| report_start | string | Start date inclusive, format YYYY-MM-DD | Yes |
| report_end | string | End date inclusive, format YYYY-MM-DD | Yes |

---

### tool_payment_contract_history

Full payment timeline for a single contract: all payments ordered by date, showing
amount, method, channel, collector, and receipt number. Use when ops teams need to
check a specific customer's payment record.

#### Parameters

| Name | Type | Description | Required |
| :--- | :--- | :--- | :--- |
| contract_no | string | Contract number to look up (e.g. 'KTR-2023-00001') | Yes |
