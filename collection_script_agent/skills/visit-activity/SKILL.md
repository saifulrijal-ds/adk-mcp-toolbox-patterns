---
name: visit-activity
description: "Visit activity deep-dive: outcome breakdown, collector ranking, daily trend."
---

## When to Use
- Outcome distribution across visit result types (PAID, NOT_HOME, REFUSE, etc.)
- Collector performance ranking (top N by conversion rate)
- Day-by-day visit volume or conversion trend

## Workflow
1. Confirm the date range. Must be within Jan–Mar 2025.
2. Match the question:
   - Outcome distribution → `scripts/tool_visit_outcome_breakdown.py --report_start DATE --report_end DATE`
   - Collector ranking → `scripts/tool_visit_collector_ranking.py --report_start DATE --report_end DATE --top_n N`
     (clarify top_n if not specified; default 10, max 50)
   - Daily trend → `scripts/tool_visit_daily_trend.py --report_start DATE --report_end DATE`
3. Run the script using `run_skill_script`.
4. Present as a formatted table + 2–4 sentence summary.
