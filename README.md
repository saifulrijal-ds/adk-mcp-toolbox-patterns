# ADK SQL Agent — Collection Operations Analyst

A Google ADK agent that answers collection operations questions by querying
`collection_db` through **MCP Toolbox**. Built as a hands-on learning project
for ADK + MCP Toolbox integration — demonstrating three distinct design patterns.

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

### Milestone 5 — ADK SkillToolset + Second Agent (Tool-Based Execution)

Created `collection_skill_agent/` — a second ADK agent that uses `SkillToolset` with
3-level progressive disclosure alongside `ToolboxToolset` for SQL execution.

**How it works:**

```python
skill_toolset = SkillToolset(
    skills=[load_skill_from_dir(_SKILLS_DIR / "collection-report"), ...],
    additional_tools=[toolbox],   # ToolboxToolset nested here, not in agent.tools
)
root_agent = Agent(tools=[skill_toolset])  # single entry point
```

Each `SKILL.md` frontmatter declares which execution tools to expose when the skill activates:

```yaml
metadata:
  adk_additional_tools:
    - tool_visit_kpis
    - tool_dpd_aging
```

**3-level progressive disclosure:**
- **L1** (~100 tokens per skill): name + description auto-injected into every LLM turn by `SkillToolset.process_llm_request` — no `list_skills` call needed
- **L2** (SKILL.md body): loaded on demand via `load_skill` — delivers `## When to Use` + `## Workflow` + tool parameter reference
- **L3** (assets/references/scripts): not used — all execution goes through `ToolboxToolset`

**Key concept:** `SkillToolset` handles discovery and workflow instructions; `ToolboxToolset`
handles SQL execution. The `adk_additional_tools` metadata field is the bridge — it scopes
which execution tools the model can see after a skill is activated, keeping tool selection
focused to the current domain.

**System prompt becomes thin:** `SkillToolset` auto-injects its own skill system instructions
(telling the model to call `load_skill` before proceeding). The agent prompt only needs
identity, mission, and boundary rules — no workflow steps or tool inventory.

| | MCP Toolbox Skills (generated) | ADK SkillToolset (this agent) |
|---|---|---|
| Execution | `npx @toolbox-sdk/server` (Node.js) | `ToolboxToolset` via HTTP |
| Runtime | Gemini CLI | ADK agent runtime |
| `SKILL.md` role | Metadata + usage docs | L2 instructions injected into LLM context |
| Scripts | `.js` scripts (not used in ADK) | Not needed — no `scripts/` directory |

---

### Milestone 6 — ADK SkillToolset + Script Execution (Third Agent)

Created `collection_script_agent/` — a third agent demonstrating the **script execution pattern**:
`SkillToolset(code_executor=UnsafeLocalCodeExecutor())`. Instead of calling `ToolboxToolset` as
additional tools, the LLM calls `run_skill_script` which executes Python scripts that call the
MCP Toolbox JSON-RPC endpoint directly.

```python
skill_toolset = SkillToolset(
    skills=[load_skill_from_dir(_SKILLS_DIR / "collection-report"), ...],
    code_executor=UnsafeLocalCodeExecutor(),   # no additional_tools
)
```

Each SKILL.md workflow references Python scripts instead of tool names:
```markdown
## Workflow
2. Match the question to a script:
   - Overall KPIs → `scripts/tool_visit_kpis.py --report_start DATE --report_end DATE`
```

**Execution path:**
```
LLM → run_skill_script("scripts/tool_visit_kpis.py", "--report_start 2025-01-01 --report_end 2025-01-31")
       ↓ UnsafeLocalCodeExecutor
       Python script (argparse → urllib → JSON-RPC POST to /mcp)
       ↓ MCP Toolbox Docker container → PostgreSQL
```

**Key concept:** `run_skill_script` passes arguments as `sys.argv`, so scripts use `argparse` for
the human-facing interface and serialize to JSON internally. Scripts run from a temp directory,
so `pathlib.Path.cwd()` and `__file__`-based path navigation are unreliable — use an env var
(`WORKSPACE`) for any absolute path lookup.

---

## Three Design Patterns: MCP Toolbox + ADK

This project implements three patterns for connecting ADK agents to MCP Toolbox, each with
different trade-offs:

| | Pattern 1 — Direct | Pattern 2 — Skills + Tools | Pattern 3 — Skills + Scripts |
|---|---|---|---|
| **Agent** | `collection_analysis_agent` | `collection_skill_agent` | `collection_script_agent` |
| **SkillToolset** | Not used | `additional_tools=[toolbox]` | `code_executor=UnsafeLocalCodeExecutor()` |
| **Execution** | LLM → tool call → HTTP | LLM → `load_skill` → tool call → HTTP | LLM → `run_skill_script` → Python → HTTP |
| **Skill scoping** | N/A | `adk_additional_tools` in frontmatter | SKILL.md workflow references scripts by name |
| **Best for** | Full tool access, no workflow overhead | Domain-scoped workflows, structured disclosure | Script-level control, post-processing, platform flexibility |

### MCP Toolbox-Generated Skills: Limitations in ADK

MCP Toolbox generates `.js` scripts in `mcp-toolbox/skills/` for use with **Gemini CLI and Claude
Code**. These scripts are not directly usable with ADK's `UnsafeLocalCodeExecutor`. Known limitations:

**1. Platform binary dependency**
`@toolbox-sdk/server@1.0.0` requires a platform-specific binary. ARM64 Linux is unsupported:
```
Unsupported platform: linux-arm64
```

**2. Argument format mismatch**
The JS scripts expect a single JSON string positional argument:
```bash
node script.js '{"report_start": "2025-01-01", "report_end": "2025-01-31"}'  # ✓ correct
node script.js --report_start 2025-01-01 --report_end 2025-01-31              # ✗ empty output
```
`run_skill_script` passes argparse-style flags — the toolbox SDK CLI silently ignores them.

**3. `sys.exit()` swallows error context**
Calling `sys.exit(returncode)` inside exec'd Python code raises `SystemExit`, which ADK catches
as an unhandled exception and formats as a traceback — hiding any stderr the script printed before it.

**4. Path resolution breaks in temp directory**
`UnsafeLocalCodeExecutor` copies scripts to `/tmp/tmpXXXXX/` and sets CWD there.
Both `pathlib.Path(__file__).resolve().parents[N]` and `pathlib.Path.cwd()` return temp paths,
not the project workspace.

**The correct pattern for ADK** is to write custom Python scripts that call the running MCP
Toolbox container via its JSON-RPC 2.0 endpoint directly:
```python
# POST http://127.0.0.1:5002/mcp
{"jsonrpc": "2.0", "method": "tools/call",
 "params": {"name": "tool_visit_kpis", "arguments": {...}}, "id": 1}
```
This reuses the already-running Docker infrastructure and eliminates the Node.js dependency entirely.

| Context | Execution layer | Script type |
|---|---|---|
| Gemini CLI / Claude Code | `npx @toolbox-sdk/server` | JS (generated by toolbox) |
| ADK `SkillToolset` | `UnsafeLocalCodeExecutor` | Python (custom, calling JSON-RPC) |

### Worth Trying: Running JS Scripts in ADK

Two alternatives that could enable the toolbox-generated JS scripts to work inside `SkillToolset` without rewriting them to Python:

- **Custom `CodeExecutor` subclass** — ADK's `BaseCodeExecutor` is extensible. A Node.js executor would invoke `node` via subprocess, translate argparse-style flags back to the JSON string the toolbox SDK expects, and return stdout as the result. The platform binary limitation (`linux-arm64`) still applies unless Node.js is installed separately from the npm package.

- **Alibaba Open Sandbox** — An open-source Docker-based code sandbox ([alibaba/open-sandbox](https://github.com/alibaba/open-sandbox)) that supports multiple runtimes including Node.js. Wrapping it as a custom `CodeExecutor` would give real process isolation, resource limits, and multi-runtime support (Python + Node.js in the same agent) — solving both the isolation concern of `UnsafeLocalCodeExecutor` and the Node.js runtime gap.

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
| Redis (memory persistence) | 6379 | `adk_redis` |
| pgAdmin | 5051 | `sql_agent_pgadmin` |

---

## Project Structure

```
adk-sql-agent/
├── shared/                         # Shared memory layer (Pattern 1 & 2)
│   ├── memory_service.py           # RedisMemoryService — 5 memory types + TTLs
│   ├── memory_tools.py             # 6 ADK tools: remember_*/recall_corrections
│   └── callbacks.py                # memory_extraction_callback (auto-archive + correction detect)
├── collection_analysis_agent/      # Pattern 1: ToolboxToolset + memory tools
│   ├── agent.py                    # App(TaskToDoPlanner + 6 memory tools + EventsCompactionConfig)
│   ├── prompts.py                  # 6-section system prompt (adds Memory Protocol)
│   ├── planners/
│   │   └── task_planner.py         # TaskToDoPlanner(BasePlanner) — <TODO>/<DONE> tags
│   ├── __init__.py
│   └── .env                        # GOOGLE_API_KEY + TOOLBOX_URL
├── collection_skill_agent/         # Pattern 2: SkillToolset + additional_tools + memory tools
│   ├── agent.py                    # App(TaskToDoPlanner + 6 memory tools + EventsCompactionConfig)
│   ├── prompts.py                  # minimal 3-section prompt
│   ├── skills/
│   │   ├── collection-report/SKILL.md   # adk_additional_tools: 4 tools
│   │   ├── visit-activity/SKILL.md      # adk_additional_tools: 3 tools
│   │   ├── payment/SKILL.md             # adk_additional_tools: 3 tools
│   │   └── adhoc/SKILL.md               # adk_additional_tools: 3 tools
│   ├── __init__.py
│   └── .env                        # GOOGLE_API_KEY + TOOLBOX_URL
├── collection_script_agent/        # Pattern 3: SkillToolset + UnsafeLocalCodeExecutor
│   ├── agent.py                    # SkillToolset(code_executor=UnsafeLocalCodeExecutor())
│   ├── prompts.py                  # minimal 3-section prompt
│   ├── skills/
│   │   ├── collection-report/
│   │   │   ├── SKILL.md            # workflow references Python scripts
│   │   │   └── scripts/            # 4 Python scripts → JSON-RPC → MCP Toolbox
│   │   ├── visit-activity/
│   │   │   ├── SKILL.md
│   │   │   └── scripts/            # 3 Python scripts
│   │   ├── payment/
│   │   │   ├── SKILL.md
│   │   │   └── scripts/            # 3 Python scripts
│   │   └── adhoc/
│   │       ├── SKILL.md
│   │       └── scripts/            # 3 Python scripts
│   ├── __init__.py
│   └── .env                        # GOOGLE_API_KEY + TOOLBOX_URL + WORKSPACE
├── mcp-toolbox/
│   ├── tools.yaml                  # 1 source, 13 tools, 4 toolsets
│   ├── docker-compose.yml
│   ├── skills/                     # Toolbox-generated skills for Gemini CLI / Claude Code
│   │   ├── collection-report/      # JS scripts + assets/tools.yaml
│   │   ├── visit-activity/
│   │   ├── payment/
│   │   └── adhoc/
│   └── .env                        # DB credentials
├── mcp-toolbox/
│   ├── tools.yaml                  # 1 source, 13 tools, 4 toolsets
│   ├── docker-compose.yml          # adk_toolbox (port 5002) + adk_redis (port 6379)
│   ├── skills/                     # Toolbox-generated skills for Gemini CLI / Claude Code
│   └── .env                        # DB credentials
├── services.yaml                   # ADK services: registers RedisMemoryService
├── TEST_SCENARIOS.md               # 18 test scenarios
├── MEMORY_IMPLEMENTATION.md        # Full persistence + memory architecture
├── QUICK_START_MEMORY.md           # 5-min memory system test
├── TEST_MEMORY_SCENARIOS.md        # 7 comprehensive memory test scenarios
├── CLAUDE.md                       # Claude Code guidance
└── pyproject.toml                  # uv dependencies
```

---

## Memory & Session Persistence

The agent has persistent query correction memory powered by Redis, plus SQLite session storage.
Users can teach the agent domain-specific patterns once; corrections apply to future queries automatically.

**For memory setup and testing**, see the three guides:

| Guide | Purpose | Read time |
|-------|---------|-----------|
| **MEMORY_IMPLEMENTATION.md** | Full architecture, API reference, services setup | 20 min |
| **QUICK_START_MEMORY.md** | Verify memory works end-to-end in 5 min | 5 min |
| **TEST_MEMORY_SCENARIOS.md** | 7 realistic test scenarios (corrections, vocabulary, error patterns, etc.) | 15 min |

**Quick start:**
```bash
# Start Redis + Toolbox
cd mcp-toolbox && docker compose up -d && cd ..

# Run agent with memory
uv run adk web \
  --session_service_uri="sqlite:///./sessions.db" \
  --memory_service_uri="redis://localhost:6379" \
  .
```

Memory types stored:
- **Query corrections** (90 days) — wrong → correct patterns learned from user feedback
- **Preferences** (persistent) — user's format/verbosity choices
- **Schema cache** (7 days) — table structures, avoiding repeated lookups
- **Vocabulary** (90 days) — business term definitions
- **Error patterns** (90 days) — failed SQL patterns to avoid

See **MEMORY_IMPLEMENTATION.md** for the full implementation walkthrough and how to extend memory to Pattern 2 & 3 agents.
