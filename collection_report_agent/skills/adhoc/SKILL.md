---
name: adhoc
description: "Ad-hoc query tools: execute custom SQL, list tables/schema, and discover valid filter values."
metadata:
  adk_additional_tools:
    - postgres-execute-sql
    - tool_list_tables
    - tool_schema_filter_values
---

## When to Use
- The question cannot be answered by any predefined tool in `collection-report`, `visit-activity`, or `payment` skills
- The question combines multiple tables or metrics that no single predefined tool covers
- Column names or valid categorical filter values need to be confirmed before writing a WHERE clause

## Workflow

1. **Schema lookup** — Call `tool_list_tables` to confirm table names and column names. Never guess. Pass relevant table names if already known; leave empty to list all.
2. **Filter validation** — If the query uses any categorical filter (visit_result, collection_segment, dpd_bucket, payment_method, payment_channel), call `tool_schema_filter_values` to get valid enum values before writing the WHERE clause.
3. **Clarify ambiguities** — Before writing SQL, ask the user about any unresolved scope: date range (must be within Jan–Mar 2025), row limit, top-N count, or grouping dimension. One focused question only.
4. **Write SELECT** — Compose a SELECT-only statement. Never use INSERT, UPDATE, DELETE, DROP, TRUNCATE, or DDL. Always scope dates using `BETWEEN '2025-01-01' AND '2025-03-31'` (or the user-specified range within that window).
5. **Execute** — Call `postgres-execute-sql` with the complete SQL string.
6. **Error recovery** — If the query fails, diagnose against schema (wrong column name? invalid enum? wrong table?), correct the SQL, and retry. Limit to 5 retries; if still failing, explain the error to the user.


## Tools

### postgres-execute-sql

Executes any SELECT statement against collection_db. Use when predefined tools don't
cover the question.

#### Parameters

| Name | Type | Description | Required |
| :--- | :--- | :--- | :--- |
| sql | string | The SQL SELECT statement to execute | Yes |

---

### tool_list_tables

Lists all tables in collection_db with their column names, data types, and nullable
flags. Use this first when building a custom SQL query — it reveals the full schema
without needing prior knowledge.

#### Parameters

| Name | Type | Description | Required |
| :--- | :--- | :--- | :--- |
| table_names | string | Optional comma-separated list of table names; empty returns all | No |
| output_format | string | 'simple' for names only or 'detailed' for full info (default: detailed) | No |

---

### tool_schema_filter_values

Returns all valid categorical filter values across both fact tables in one call:
visit_result, collection_segment, dpd_bucket, payment_method, payment_channel.
Use before writing WHERE clauses to avoid invalid literals.

#### Parameters

None — returns all filter values in a single call.
