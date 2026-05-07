---
name: adhoc
description: "Ad-hoc query tools: execute custom SQL, list tables/schema, discover valid filter values."
---

## When to Use
- Question cannot be answered by collection-report, visit-activity, or payment skills
- Combines multiple tables or metrics no single predefined script covers
- Column names or valid categorical filter values need confirmation

## Workflow
1. **Schema lookup** — Run `scripts/tool_list_tables.py` (no required args) to confirm table/column names.
2. **Filter validation** — If query uses categorical filters, run `scripts/tool_schema_filter_values.py` (no args).
3. **Clarify ambiguities** — Ask one focused question about date range, row limit, or grouping.
4. **Write SELECT** — SELECT only. Never INSERT/UPDATE/DELETE/DDL. Scope dates to Jan–Mar 2025.
5. **Execute** — Run `scripts/postgres-execute-sql.py --sql "SELECT ..."` using `run_skill_script`.
6. **Error recovery** — If it fails, re-check schema, fix SQL, retry. Max 5 retries.
