# Session Persistence + Redis Memory Implementation

## Overview

This document summarizes the complete implementation of persistent sessions and memory for ADK SQL agents, enabling query correction feedback loops and user preference persistence.

## Architecture

### Services Layer
- **Session Service**: SQLite (built-in ADK `SqliteSessionService`)
  - Path: `sqlite:///./sessions.db`
  - Persists conversation history across restarts
  - Auto-creates on first session

- **Memory Service**: Redis (custom `RedisMemoryService`)
  - Schema: `redis://localhost:6379`
  - Stores 5 memory types with domain-specific TTLs
  - Integrated via `services.yaml` registration

### Memory Types

| Type | Key Pattern | TTL | Use Case |
|------|------------|-----|----------|
| `query_correction` | `corrections:{app}:{user}:{uuid}` | 90 days | SQL corrections after user feedback |
| `preference` | `prefs:{app}:{user}` | None (persists) | User format/verbosity/language choices |
| `schema_discovery` | `schema_cache:{app}:{user}:{table}` | 7 days | Cached column names and filter values |
| `vocabulary` | `vocabulary:{app}:{user}:{term}` | 90 days | Business term definitions |
| `failed_pattern` | `failed_patterns:{app}:{user}:{uuid}` | 90 days | SQL error patterns and fixes |

## Files Created

### Infrastructure

**`mcp-toolbox/docker-compose.yml`** — Added Redis 8-alpine service
```yaml
redis:
  image: redis:8.4-alpine
  container_name: adk_redis
  ports:
    - "6379:6379"
  volumes:
    - redis_data:/data
  command: redis-server --save 60 1 --loglevel warning
  healthcheck:
    test: ["CMD", "redis-cli", "ping"]
    interval: 5s
    timeout: 3s
    retries: 5
```

**`pyproject.toml`** — Added dependency
```toml
"redis>=5.0"
```

**`services.yaml`** — ADK service registry
```yaml
services:
  - scheme: redis
    type: memory
    class: shared.memory_service.RedisMemoryService
```

### Shared Modules

**`shared/__init__.py`** — Package marker (empty)

**`shared/memory_service.py`** — `RedisMemoryService(BaseMemoryService)`

Three methods:
- `add_session_to_memory(session)` — Archives last 20 turns to Redis list (capped at 30)
- `add_memory(*, app_name, user_id, memories, custom_metadata)` — Stores 5 memory types by category
- `search_memory(*, app_name, user_id, query) -> SearchMemoryResponse` — Keyword-matches corrections

**`shared/memory_tools.py`** — Six ADK tools

```python
async def remember_query_correction(
    original_query: str,
    corrected_query: str,
    correction_reason: str,
    table_or_domain: str,
    tool_context: ToolContext,
) -> dict

async def remember_preference(
    preference_category: str,
    preference_value: str,
    tool_context: ToolContext,
) -> dict

async def remember_schema_discovery(
    table_name: str,
    columns: list[str],
    filter_values: dict[str, list],
    tool_context: ToolContext,
) -> dict

async def remember_term(
    term: str,
    definition: str,
    context: str,
    tool_context: ToolContext,
) -> dict

async def remember_failed_pattern(
    wrong_pattern: str,
    correct_pattern: str,
    error_type: str,
    domain: str,
    tool_context: ToolContext,
) -> dict

async def recall_corrections(
    query_context: str,
    tool_context: ToolContext,
) -> dict
```

**`shared/callbacks.py`** — Auto-memory extraction

- `memory_extraction_callback()` — Called after each agent turn
- Archives session to Redis
- Detects correction signals (English: "wrong", "incorrect", "fix the query"; Indonesian: "salah", "bukan", "harusnya")
- Sets `temp:correction_detected = True` for downstream handling

## Files Modified

### `collection_analysis_agent/agent.py`

Changes:
- Import `App` from `google.adk.apps`
- Import `EventsCompactionConfig` from `google.adk.agents.invocation_context`
- Import 6 memory tools from `shared.memory_tools`
- Import `memory_extraction_callback` from `shared.callbacks`
- Rename `Agent` → `_agent` (wrap in `App`)
- Add `tools=[toolbox, ...6 memory tools...]` to Agent
- Add `after_agent_callback=memory_extraction_callback` to Agent
- Wrap Agent in `App` with `events_compaction_config` to prevent context blowout
- Export `root_agent = _agent` for ADK discovery

**EventsCompactionConfig parameters**:
- `compaction_interval=10` — Compact every 10 turns
- `overlap_size=2` — Keep last 2 turns before compacting  
- `token_threshold=4000` — Trigger compaction at 4k tokens (optional, requires `event_retention_size`)
- `event_retention_size=1000` — Max events to retain (optional, required with `token_threshold`)

**Key insight**: The `App` wrapper enables session compaction for long analytical conversations, reducing token overhead over time while `EventsCompactionConfig` maintains message history intelligently.

### `collection_analysis_agent/prompts.py`

Appended **Memory Protocol** section to `BASE_SYSTEM_PROMPT`:
- 8 specific conditions for calling memory tools
- Examples: "Before generating adhoc SQL: call `recall_corrections`"
- Active preference placeholders: `{user:pref_response_format}`, `{user:pref_verbosity}`

## Run Commands

### Start Infrastructure
```bash
cd mcp-toolbox && docker compose up -d && cd ..
```

### Start Agent with Persistence
```bash
uv run adk web \
  --session_service_uri="sqlite:///./sessions.db" \
  --memory_service_uri="redis://localhost:6379" \
  .
```

Access: `http://127.0.0.1:8000`

## Correction Feedback Loop

**Scenario**: User asks a collection data question, agent generates SQL, user says "that's wrong".

1. **User message**: "Salah, harusnya collection_status = 'ACTIVE'" (detected by callback)
2. **Agent detects correction signal** → `temp:correction_detected = True`
3. **Agent asks**: "Apa yang salah dari query tadi?" (clarify the error)
4. **Agent calls `remember_query_correction`** with original/corrected/reason/domain
5. **Redis stores** the correction with timestamp
6. **Next session** or **next domain question**:
   - Agent calls `recall_corrections(domain)` before generating SQL
   - Returns past corrections for that domain (sorted by recency)
   - Agent applies corrections when writing the new query
   - User sees corrected SQL on first try (no re-iteration)

## Verification

### Check Services

```bash
# Redis health
docker logs adk_redis | tail -3

# Toolbox health
curl -s http://127.0.0.1:5002/mcp | jq .

# Session database
ls -lh sessions.db  # Created on first session
```

### Check Redis Keys

```bash
docker exec adk_redis redis-cli
> KEYS "corrections:*"        # Past corrections
> KEYS "prefs:*"               # User preferences
> KEYS "session_archive:*"     # Session archives
> KEYS "schema_cache:*"        # Schema caches
```

### Verify Correction Loop

1. Start agent with flags above
2. Ask: "Tampilkan kunjungan dengan status = 'aktif'"
3. Agent generates SQL (may fail or return wrong data)
4. Say: "Salah, harusnya collection_status = 'ACTIVE'"
5. Agent stores correction in Redis
6. Start new session (new browser tab)
7. Ask same question
8. Agent calls `recall_corrections` → applies fix automatically
9. Verify with: `docker exec adk_redis redis-cli KEYS "corrections:*"`

## Extending to Patterns 2 & 3

Once `collection_analysis_agent` is tested:

**`collection_skill_agent/agent.py`** and **`collection_script_agent/agent.py`**:
```python
# Same imports as collection_analysis_agent
from google.adk.apps import App, EventsCompactionConfig
from shared.memory_tools import (...)
from shared.callbacks import memory_extraction_callback

# Wrap existing SkillToolset in App
_agent = SkillToolset(...)
app = App(
    name="collection_skill_agent",
    root_agent=_agent,
    events_compaction_config=EventsCompactionConfig(enable_session_compaction=True),
)
root_agent = _agent
```

**Both `prompts.py` files**: Append the Memory Protocol section (same as Pattern 1)

**`services.yaml` and `shared/` modules**: Already shared — no duplication needed

## Technical Details

### Key Design Decisions

1. **Redis over Vector DB**: Corrections are short texts; keyword matching is sufficient for domain-specific recall. No semantic embeddings needed.

2. **AsyncIO throughout**: `redis.asyncio` client for non-blocking I/O during long-running sessions.

3. **State prefixes** for memory scope:
   - `temp:` — current turn only (correction detection)
   - `user:` — persists across sessions (preferences)
   - `app:` — global (unused in this MVP, reserved for future)

4. **Dual-write for preferences**: Both `tool_context.state` (instant availability in current turn) and Redis (persistence across sessions).

5. **Top-8 limit on correction recall**: Prevents overwhelming the LLM with outdated corrections; recency-sorted ensures freshest fixes first.

### `search_memory()` Implementation Notes

```python
async def search_memory(
    self,
    *,
    app_name: str,
    user_id: str,
    query: str,
) -> SearchMemoryResponse:
    """Search corrections by keyword matching."""
    results: list[MemoryEntry] = []
    pattern = f"corrections:{app_name}:{user_id}:*"
    async for key in self._redis.scan_iter(pattern):
        data = await self._redis.hgetall(key)
        words = query.lower().split()
        combined_text = " ".join([
            data.get("original_query", ""),
            data.get("corrected_query", ""),
            data.get("reason", ""),
        ])
        if any(w in combined_text.lower() for w in words):
            entry = MemoryEntry(
                content=types.Content(parts=[
                    types.Part(
                        text=f"CORRECTION [{data['domain']}]: {data['original_query']} → {data['corrected_query']}. Reason: {data['reason']}"
                    )
                ]),
                custom_metadata={"type": "query_correction", **data},
                timestamp=data["timestamp"],
            )
            results.append(entry)

    results.sort(key=lambda e: e.timestamp or "", reverse=True)
    return SearchMemoryResponse(memories=results[:8])
```

**Why this works**:
- `scan_iter` is async-safe and doesn't block Redis
- Keyword matching is case-insensitive and word-boundary aware
- Sorting by timestamp descending ensures freshest corrections first
- Top-8 limit prevents context overflow

## Next Steps

1. **Test the full correction loop** in the web UI
2. **Extend to Pattern 2** (`collection_skill_agent`)
3. **Extend to Pattern 3** (`collection_script_agent`)
4. **Optional: Add UI dashboard** to visualize stored corrections and preferences

## Learning Outcomes

This implementation demonstrates:
- **Google ADK memory protocol**: Custom `BaseMemoryService` subclasses
- **Redis async patterns**: Non-blocking key iteration and data retrieval
- **Session persistence**: `SqliteSessionService` built-in, custom services via URI scheme
- **Agent callback patterns**: Post-turn processing for automatic memory extraction
- **Feedback loop design**: State variables (`temp:`, `user:`) for turn/session scope
- **Keyword search at scale**: Efficient Redis scanning and text matching
