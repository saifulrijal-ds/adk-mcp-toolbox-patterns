---
name: collection-report
description: "Executive summary reports: visit KPIs, DPD aging, branch performance, PTP fulfillment."
---

## When to Use
- Period-level KPI summary or dashboard (visits, conversions, field-collected IDR)
- DPD aging analysis by segment or bucket (EARLY/NPL/WO)
- Branch performance comparison or ranking
- PTP commitment fulfillment rate or broken exposure

## Workflow
1. Confirm `report_start` and `report_end` (YYYY-MM-DD). Must be within Jan–Mar 2025.
2. Match the question to a script:
   - Overall KPIs → `scripts/tool_visit_kpis.py --report_start DATE --report_end DATE`
   - DPD aging → `scripts/tool_dpd_aging.py --report_start DATE --report_end DATE`
   - Branch ranking → `scripts/tool_branch_performance.py --report_start DATE --report_end DATE`
   - PTP tracking → `scripts/tool_ptp_fulfillment.py --report_start DATE --report_end DATE`
3. Run the script using `run_skill_script`.
4. Present output as a formatted table + 2–4 sentence summary. Currency: "Rp X,XXX,XXX".
