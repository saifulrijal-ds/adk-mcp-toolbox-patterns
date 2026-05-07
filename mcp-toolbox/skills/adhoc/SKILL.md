---
name: adhoc
description: Ad-hoc query tools: execute custom SQL, list tables/schema, and discover valid filter values.
---

## Usage

All scripts can be executed using Node.js. Replace `<param_name>` and `<param_value>` with actual values.

**Bash:**
`node <skill_dir>/scripts/<script_name>.js '{"<param_name>": "<param_value>"}'`

**PowerShell:**
`node <skill_dir>/scripts/<script_name>.js '{\"<param_name>\": \"<param_value>\"}'`


## Scripts


### postgres-execute-sql

Executes any SELECT statement against collection_db. Use when predefined tools don't cover the question.


#### Parameters

| Name | Type | Description | Required | Default |
| :--- | :--- | :--- | :--- | :--- |
| sql | string | The sql to execute. | Yes |  |


---

### tool_list_tables

Lists all tables in collection_db with their column names, data types, and nullable flags. Use this first when building a custom SQL query — it reveals the full schema without needing prior knowledge.


#### Parameters

| Name | Type | Description | Required | Default |
| :--- | :--- | :--- | :--- | :--- |
| table_names | string | Optional: A comma-separated list of table names. If empty, details for all tables will be listed. | No | `` |
| output_format | string | Optional: Use 'simple' for names only or 'detailed' for full info. | No | `detailed` |


---

### tool_schema_filter_values

Returns all valid categorical filter values across both fact tables in one call: visit_result, collection_segment, dpd_bucket, payment_method, payment_channel. Use before writing WHERE clauses to avoid invalid literals.




---

