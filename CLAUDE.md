# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Google ADK SQL agent (`collection_analysis_agent`) that connects to `collection_db` via **MCP Toolbox**. It answers collection operations questions — field visits, payments, DPD aging, PTP fulfillment, branch performance — for an Indonesian multifinance context. Data scope is January–March 2025.

## Commands

This project uses `uv` for dependency management (Python 3.13). Always use `uv run` and `uv add`, never bare `python` or `pip`.

```bash
# Install dependencies
uv sync

# Start MCP Toolbox server (required before running the agent)
cd mcp-toolbox && docker compose up -d && cd ..

# Run the ADK web UI (primary development interface)
uv run adk web

# Run the ADK CLI
uv run adk run collection_analysis_agent

# Run the ADK API server
uv run adk api_server

# Verify toolbox is running
docker logs adk_toolbox
curl -s http://127.0.0.1:5002/mcp
```

> `adk web` auto-discovers agents by scanning for `agent.py` files in subdirectories. The agent module must expose a `root_agent` variable.

## Architecture

```
adk-sql-agent/
├── collection_analysis_agent/
│   ├── agent.py          # root_agent: LlmAgent + BuiltInPlanner + ToolboxToolset
│   ├── prompts.py        # BASE_SYSTEM_PROMPT (5-pattern: identity/mission/workflow/boundaries/examples)
│   ├── __init__.py       # re-exports agent module (required by ADK discovery)
│   └── .env              # GOOGLE_API_KEY + TOOLBOX_URL (not committed)
├── mcp-toolbox/
│   ├── tools.yaml        # MCP Toolbox config: source + 13 tools + 4 toolsets
│   ├── docker-compose.yml # toolbox container on port 5002 with --ui flag
│   └── .env              # DB credentials for toolbox (not committed)
├── TEST_SCENARIOS.md     # 18 test scenarios covering all tool paths and boundary cases
└── main.py               # placeholder, not used by ADK
```

## MCP Toolbox

The toolbox server (`adk_toolbox`) runs on `http://127.0.0.1:5002` and exposes:

| Toolset | Tools | Purpose |
|---|---|---|
| `collection_report` | 4 tools | Executive summary: visit KPIs, DPD aging, branch performance, PTP fulfillment |
| `visit_activity` | 3 tools | Deep-dive visits: outcome breakdown, collector ranking (top N), daily trend |
| `payment` | 3 tools | Payment analysis: channel breakdown, by collector, contract history |
| `adhoc` | 3 tools | LLM query building: `postgres-execute-sql`, `tool_list_tables`, `tool_schema_filter_values` |

**Toolbox UI:** `http://127.0.0.1:5002/ui` — inspect and test tools interactively.

### tools.yaml structure

```yaml
kind: source   # PostgreSQL connection (reads from .env)
kind: tool     # type: postgres-sql (fixed SQL, $1/$2 params) or postgres-execute-sql (open SQL)
kind: toolset  # named group of tools — used to scope what the agent loads
```

## Agent Design

- `ToolboxToolset(server_url=..., toolset_name=None)` loads all 13 tools at invocation time — no eager connection at import.
- `BuiltInPlanner` with `ThinkingLevel.LOW` adds lightweight pre-reasoning before tool calls.
- Retry config: 4 attempts, 2s initial delay.
- The agent is **read-only**: the system prompt forbids non-SELECT SQL.

### System prompt pattern (5-section)
1. **Identity** — domain expertise (Indonesian multifinance collection ops)
2. **Mission** — data analyst role, read-only, language-adaptive
3. **Workflow** — 6 steps: Identify → Clarify → Match → Prepare → Execute → Present
4. **Boundaries** — scope (Jan–Mar 2025), response quality rules, data integrity
5. **Few-shot** — 4 edge case examples (out-of-range, out-of-scope, ambiguous, error recovery)

### Tool selection logic (in prompt)
- **Predefined tools** — for known report patterns (fast, no schema lookup needed)
- **`postgres-execute-sql`** — for custom/combined questions no predefined tool covers
- **`tool_schema_filter_values`** — call before writing WHERE clauses on categorical columns
- **`tool_list_tables`** — call when column names are uncertain

> The system prompt does **not** list tool names — the LLM receives tool descriptions automatically via the `tools[]` API parameter (separate from the system prompt text). The prompt only contains behavioral decision logic.

## Environment

`collection_analysis_agent/.env`:
```
GOOGLE_API_KEY=<your-key>
TOOLBOX_URL=http://127.0.0.1:5002
```

`mcp-toolbox/.env`:
```
COLLECTION_DB_HOST=localhost
COLLECTION_DB_PORT=5433
COLLECTION_DB_NAME=collection_db
COLLECTION_DB_USER=collection_user
COLLECTION_DB_PASSWORD=collection_pass_2024
```

The PostgreSQL database runs in Docker as `sql_agent_postgres` on port 5433.
