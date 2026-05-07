---
name: payment
description: "Payment analysis: channel breakdown, field collection by collector, contract history."
---

## When to Use
- Payment method/channel breakdown (CASH, TRANSFER, salary-cycle detection)
- Field cash ranking by collector (CASH_FIELD payments only)
- Full payment history for a specific contract number

## Workflow
1. Identify the sub-question:
   - Channel breakdown → `scripts/tool_payment_channel_breakdown.py --report_start DATE --report_end DATE`
   - By collector → `scripts/tool_payment_by_collector.py --report_start DATE --report_end DATE`
   - Contract history → `scripts/tool_payment_contract_history.py --contract_no CONTRACT`
2. For date-range scripts: confirm range within Jan–Mar 2025.
3. For contract history: extract contract number from user's message; ask if missing.
4. Run the script using `run_skill_script`.
5. Present as a formatted table + 2–4 sentence summary. Currency: "Rp X,XXX,XXX".
