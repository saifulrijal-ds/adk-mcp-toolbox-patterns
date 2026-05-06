# ADK SQL Agent — Collection Operations Analyst

A Google ADK agent that answers collection operations questions by querying
`collection_db` through **MCP Toolbox**. Built as a hands-on learning project
for ADK + MCP Toolbox integration.

**Domain:** Indonesian multifinance — field visits, DPD aging, PTP fulfillment,
branch performance, payment analysis.
**Data scope:** January–March 2025.

---

## Learning Milestones

This project was built sequentially through 5 milestones:

### Milestone 1 — MCP Toolbox Setup
Set up `tools.yaml`, `.env`, and `docker-compose.yml` in `mcp-toolbox/`.
Defined a PostgreSQL source and the toolset structure.
**Key concept:** `tools.yaml` is the complete server contract — source, tools,
and toolsets in one file. No code changes needed to add a new tool.

### Milestone 2 — Predefined vs Open-ended Queries
Added 10 predefined `postgres-sql` tools (fixed SQL with `$1`/`$2` parameters)
and 1 `postgres-execute-sql` tool (accepts any SELECT).
Also added `postgres-list-tables` (built-in type) and a custom
`tool_schema_filter_values` query for LLM schema discovery.
**Key concept:** Predefined tools are safer and more LLM-friendly — the agent
passes date parameters, not SQL. Open-ended SQL is the fallback for custom questions.

### Milestone 3 — ADK Integration
Wired `ToolboxToolset` into `agent.py`. The agent now discovers and calls
all 13 MCP Toolbox tools at runtime.
Updated `prompts.py` to a behavior-only system prompt (no tool listing).
**Key concept:** Tool descriptions reach the LLM through two separate channels —
the `tools[]` API parameter (automatic) and the system prompt (manual). The tool
list in the prompt is redundant; only behavioral decision logic belongs there.

### Milestone 4 — MCP Toolbox UI
Enabled `--ui` flag in `docker-compose.yml`. The Toolbox UI at
`http://127.0.0.1:5002/ui` lets you inspect and test tools interactively —
without needing an agent or writing code.
**Key concept:** Test predefined tools directly in the UI before wiring the agent.
Confirms SQL and parameters work before debugging through the agent layer.

### Milestone 5 — Agent Skills (planned)
Generate portable `SKILL.md` + scripts from toolsets using:
```bash
toolbox tools.yaml skills-generate --name collection-report --toolset collection_report
```
Generated skills can be installed into Gemini CLI. For ADK, the SKILL.md serves
as a portable description layer; execution still goes through `ToolboxToolset`.

---

## Step-by-Step Setup

### Prerequisites
- Docker (running)
- Python 3.13 + `uv`
- Google API key (Gemini)

### 1 — Clone and install

```bash
git clone <repo>
cd adk-sql-agent
uv sync
```

### 2 — Configure environment

```bash
# Agent credentials
cp collection_analysis_agent/.env.example collection_analysis_agent/.env
# Set: GOOGLE_API_KEY, TOOLBOX_URL=http://127.0.0.1:5002

# Toolbox DB credentials
cp mcp-toolbox/.env.example mcp-toolbox/.env
# Set: COLLECTION_DB_HOST, PORT, NAME, USER, PASSWORD
```

### 3 — Start MCP Toolbox

```bash
cd mcp-toolbox
docker compose up -d
docker logs adk_toolbox   # should show "Server ready to serve!"
```

Toolbox UI available at: `http://127.0.0.1:5002/ui`

### 4 — Run the agent

```bash
uv run adk web
# Open http://localhost:8000
```

### 5 — Test

Open `TEST_SCENARIOS.md` and paste the questions into the ADK web UI.
The trace panel shows every tool call and its parameters.

---

## Key Findings & Notes

### How the agent reads toolbox tools

When `ToolboxToolset(server_url=..., toolset_name=None)` is added to `tools=[]`,
ADK calls `get_tools()` lazily on the first agent invocation. The toolbox server
returns each tool's `name`, `description`, and `parameters` schema as a JSON array.
This array is sent to the LLM as the `tools[]` API parameter — **separate from the
system prompt text**. The LLM uses it to decide which tool to call and how to fill
its parameters.

```
tools.yaml → MCP server → ToolboxToolset.get_tools() → ADK runtime → Gemini tools[] → LLM
```

### Toolsets are scoping, not routing

A common misconception: toolsets don't route or execute automatically. They are
a **server-side filter** that controls which tools the client receives.

| Mental model | Reality |
|---|---|
| "Toolset = intent router" | The **LLM** routes — toolset only filters what's available |
| "All tools in a toolset must run" | Only if the prompt explicitly instructs it |
| "Different toolsets for different intents" | Valid pattern: use separate `ToolboxToolset` instances per agent |

Example — scoping different agents:
```python
# Reporting agent sees only 4 report tools
report_agent = Agent(tools=[ToolboxToolset(toolset_name="collection_report")])

# Developer agent sees only adhoc tools
dev_agent = Agent(tools=[ToolboxToolset(toolset_name="adhoc")])

# Full analyst sees all 13 tools (our setup)
analyst_agent = Agent(tools=[ToolboxToolset(toolset_name=None)])
```

### System prompt: behavior only, no tool listing

Adding a tool list to the system prompt duplicates information the LLM already
receives via the `tools[]` parameter. It adds tokens on every request and drifts
out of sync when tools change.

**Keep in the prompt:** decision logic — when to use predefined vs ad-hoc,
when to call schema discovery tools first, output format rules.

**Remove from the prompt:** tool inventory, parameter descriptions, SQL hints —
these are already in `tools.yaml` descriptions.

### Parameter types in postgres-sql tools

All parameters in `tools.yaml` use `type: string`. For `LIMIT` with a dynamic
integer, cast in SQL:

```sql
LIMIT ($3::integer)
```

This is how `tool_visit_collector_ranking` handles the `top_n` parameter.

### Built-in tool types (no SQL needed)

MCP Toolbox provides 20+ built-in postgres tool types beyond `postgres-sql`:

```yaml
kind: tool
name: tool_list_tables
type: postgres-list-tables   # no statement field needed
source: collection-db
description: Lists all tables with columns and types.
```

Useful built-ins: `postgres-list-tables`, `postgres-list-schemas`,
`postgres-list-indexes`, `postgres-list-active-queries`.

### Port layout (this environment)

| Service | Port | Container |
|---|---|---|
| PostgreSQL (collection_db) | 5433 | `sql_agent_postgres` |
| MCP Toolbox (this project) | 5002 | `adk_toolbox` |
| MCP Toolbox (reference) | 5001 | `mcp_toolbox` |
| pgAdmin | 5051 | `sql_agent_pgadmin` |

---

## Project Structure

```
adk-sql-agent/
├── collection_analysis_agent/
│   ├── agent.py          # root_agent + ToolboxToolset wiring
│   ├── prompts.py        # 5-pattern system prompt (behavior only)
│   ├── __init__.py
│   └── .env              # GOOGLE_API_KEY + TOOLBOX_URL
├── mcp-toolbox/
│   ├── tools.yaml        # 1 source, 13 tools, 4 toolsets
│   ├── docker-compose.yml
│   └── .env              # DB credentials
├── TEST_SCENARIOS.md     # 18 test scenarios
├── CLAUDE.md             # Claude Code guidance
└── pyproject.toml        # uv dependencies
```
