# Plan: Session Persistence + Redis Memory for ADK SQL Agents

## Context

All three agents (`collection_analysis_agent`, `collection_skill_agent`, `collection_script_agent`) are stateless today — each `adk web` restart loses conversation history and user corrections. This plan adds:

1. **Persistent sessions** — survive restarts via SQLite (built into ADK)
2. **Five memory use cases** — each illustrates a different Redis storage pattern
3. **App class** — replaces bare `root_agent` with `app`, enabling events compaction and lifecycle management

Primary target is `collection_analysis_agent`. The `shared/` module makes extending to the other two agents trivial.

## Architecture

```
adk web
  --session_service_uri=sqlite:///./sessions.db   → SqliteSessionService (built-in)
  --memory_service_uri=redis://localhost:6379      → RedisMemoryService (custom, services.yaml)

services.yaml
  scheme: redis, type: memory
  class: shared.memory_service.RedisMemoryService
    └── __init__(uri: str, **kwargs)   ← called by ADK generic factory

App("collection_analysis_agent", root_agent=root_agent, events_compaction_config=...)
  └─ root_agent = Agent(tools=[toolbox, *5 memory tools], after_agent_callback=...)

Memory Tools (5 use cases)                   Redis Key Schema
  remember_query_correction()      →  corrections:{app}:{user}:{uuid}  HASH
  remember_preference()            →  prefs:{app}:{user}               HASH
  remember_schema_discovery()      →  schema_cache:{app}:{user}:{tbl}  HASH
  remember_term()                  →  vocabulary:{app}:{user}:{term}    HASH
  remember_failed_pattern()        →  failed_patterns:{app}:{user}:{uuid} HASH
  recall_memory(query, type)       →  search across all types
```

## App Class — Why and How

`App` is a Pydantic model that wraps a root agent to provide application-level infrastructure without changing agent logic. ADK CLI detects either a `root_agent` variable or an `app` variable at module level.

```python
from google.adk.apps import App

app = App(
    name="collection_analysis_agent",
    root_agent=root_agent,
    events_compaction_config=EventsCompactionConfig(
        enable_session_compaction=True,       # auto-compress old turns
    ),
)
```

Key `App` parameters:
| Parameter | Purpose |
|---|---|
| `name` | Becomes `app_name` in session/memory keys |
| `root_agent` | The single entry-point agent |
| `plugins` | Global callbacks that apply to all agents in the app |
| `events_compaction_config` | Auto-summarizes long session histories to stay within context window |
| `context_cache_config` | Context cache for repeated system-prompt prefixes |
| `resumability_config` | Pause/resume invocations across failures |

For this plan `events_compaction_config` is the key benefit — it prevents context blowout in long analytical sessions. Import path: `from google.adk.apps import App, EventsCompactionConfig` (check actual import at implementation time; may be `from google.adk.apps.app import App`).

## Verified ADK Mechanics (ADK 1.32.0)

- `--session_service_uri="sqlite:///./sessions.db"` → built-in `SqliteSessionService`; `aiosqlite` already a transitive dep
- `--memory_service_uri="redis://localhost:6379"` → parses scheme `redis`, looks up `services.yaml`, calls `RedisMemoryService(uri="redis://localhost:6379")`
- `services.yaml` generic factory: `cls(uri=uri, **kwargs)` — constructor must accept `uri` as keyword arg
- `BaseMemoryService` abstract methods: `add_session_to_memory(session: Session)`, `search_memory(*, app_name, user_id, query)`, optional `add_memory(*, app_name, user_id, memories, custom_metadata=None)`
- `callback_context.add_session_to_memory()` — no args; uses current session from context internally
- `callback_context.add_memory(memories=[...])` → delegates to memory service with current app+user scope
- `tool_context.search_memory(query)` → delegates to memory service
- State prefixes: `temp:` = current turn only (not persisted), `user:` = persists across all sessions for that user, `app:` = persists across all users

## Alternative: `adk-redis` library

`adk-redis` (PyPI: `adk-redis[memory]`) provides `RedisLongTermMemoryService` + `RedisWorkingMemorySessionService` with semantic search via RedisVL. However it requires an **Agent Memory Server** sidecar on port 8088 and Redis 8.4+ with Query Engine. For the learning objective here, building a custom `RedisMemoryService` from scratch is the better choice — it teaches the pattern directly.

## Stable Versions

- Docker image: `redis:8-alpine` (tracks latest stable 8.x; currently 8.6.3)
- Python package: `redis>=5.0` (asyncio support built-in since 5.0; current latest is 5.2.x)

## New Files

### `mcp-toolbox/docker-compose.yml` — add Redis service

Append to `services:` block and add a top-level `volumes:` section:
```yaml
  redis:
    image: redis:8-alpine
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

volumes:
  redis_data:
```

### `pyproject.toml`

Add `"redis>=5.0"` to `dependencies`. (asyncio client is at `redis.asyncio` — no extra needed since 5.0.)

### `services.yaml` (project root)

```yaml
services:
  - scheme: redis
    type: memory
    class: shared.memory_service.RedisMemoryService
```

### `shared/__init__.py`

Empty — makes `shared` a package.

### `shared/memory_service.py`

Five memory types, each with a distinct Redis storage pattern:

```
Type               Redis structure      Key pattern
─────────────────────────────────────────────────────────────────────────────
query_correction   HASH per entry       corrections:{app}:{user}:{uuid}
preference         single HASH          prefs:{app}:{user}
schema_discovery   HASH per table       schema_cache:{app}:{user}:{table}
vocabulary         HASH per term        vocabulary:{app}:{user}:{term}
failed_pattern     HASH per entry       failed_patterns:{app}:{user}:{uuid}
session_archive    LIST (capped at 30)  session_archive:{app}:{user}
```

```python
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Mapping, Sequence

import redis.asyncio as aioredis
from google.adk.memory.base_memory_service import BaseMemoryService, SearchMemoryResponse
from google.adk.memory.memory_entry import MemoryEntry
from google.adk.sessions.session import Session
from google.genai import types


class RedisMemoryService(BaseMemoryService):
    def __init__(self, uri: str = "redis://localhost:6379", **kwargs):
        self._redis = aioredis.from_url(uri, decode_responses=True)

    async def add_session_to_memory(self, session: Session) -> None:
        key = f"session_archive:{session.app_name}:{session.user_id}"
        turns = []
        for event in session.events[-20:]:
            if event.content and event.content.parts:
                turns.append(f"[{event.author}] {event.content.parts[0].text or ''}")
        if turns:
            await self._redis.lpush(key, json.dumps(turns))
            await self._redis.ltrim(key, 0, 29)

    async def add_memory(
        self,
        *,
        app_name: str,
        user_id: str,
        memories: Sequence[MemoryEntry],
        custom_metadata: Mapping[str, Any] | None = None,
    ) -> None:
        for entry in memories:
            meta = entry.custom_metadata or {}
            entry_type = meta.get("type")
            ts = entry.timestamp or datetime.now().isoformat()
            ttl = 60 * 60 * 24 * 90  # 90-day TTL for all entries

            if entry_type == "query_correction":
                key = f"corrections:{app_name}:{user_id}:{uuid.uuid4()}"
                await self._redis.hset(key, mapping={
                    "original_query": meta.get("original_query", ""),
                    "corrected_query": meta.get("corrected_query", ""),
                    "reason": meta.get("reason", ""),
                    "domain": meta.get("domain", ""),
                    "timestamp": ts,
                })
                await self._redis.expire(key, ttl)

            elif entry_type == "preference":
                key = f"prefs:{app_name}:{user_id}"
                await self._redis.hset(key, meta.get("category", "misc"), meta.get("value", ""))
                # preferences don't expire — they're user identity

            elif entry_type == "schema_discovery":
                key = f"schema_cache:{app_name}:{user_id}:{meta.get('table_name', 'unknown')}"
                await self._redis.hset(key, mapping={
                    "columns": json.dumps(meta.get("columns", [])),
                    "filter_values": json.dumps(meta.get("filter_values", {})),
                    "last_refreshed": ts,
                })
                await self._redis.expire(key, 60 * 60 * 24 * 7)  # 7-day TTL (schema changes)

            elif entry_type == "vocabulary":
                term = meta.get("term", "").lower().replace(" ", "_")
                key = f"vocabulary:{app_name}:{user_id}:{term}"
                await self._redis.hset(key, mapping={
                    "definition": meta.get("definition", ""),
                    "context": meta.get("context", ""),
                    "timestamp": ts,
                })
                await self._redis.expire(key, ttl)

            elif entry_type == "failed_pattern":
                key = f"failed_patterns:{app_name}:{user_id}:{uuid.uuid4()}"
                await self._redis.hset(key, mapping={
                    "wrong_pattern": meta.get("wrong_pattern", ""),
                    "correct_pattern": meta.get("correct_pattern", ""),
                    "error_type": meta.get("error_type", ""),
                    "domain": meta.get("domain", ""),
                    "timestamp": ts,
                })
                await self._redis.expire(key, ttl)

    # --- TODO(human): implement search_memory ---
    # Goal: keyword-match `query` words against stored correction entries and return top 8
    #
    # Steps:
    #   1. Build a pattern: f"corrections:{app_name}:{user_id}:*"
    #   2. Use `async for key in self._redis.scan_iter(pattern):` to iterate keys
    #   3. For each key: data = await self._redis.hgetall(key)
    #   4. Keyword filter: words = query.lower().split()
    #      combined_text = " ".join([data.get("original_query",""), data.get("corrected_query",""), data.get("reason","")])
    #      if any(w in combined_text.lower() for w in words): include it
    #   5. Sort included results by data["timestamp"] descending
    #   6. Build MemoryEntry for each:
    #      MemoryEntry(
    #          content=types.Content(parts=[types.Part(text=f"CORRECTION [{data['domain']}]: ...")]),
    #          custom_metadata={"type": "query_correction", **data},
    #          timestamp=data["timestamp"],
    #      )
    #   7. Return SearchMemoryResponse(memories=results[:8])
    async def search_memory(
        self,
        *,
        app_name: str,
        user_id: str,
        query: str,
    ) -> SearchMemoryResponse:
        results: list[MemoryEntry] = []
        # --- your implementation here ---
        return SearchMemoryResponse(memories=results)
```

### `shared/memory_tools.py`

Six tool functions covering all five memory types:

```python
from datetime import datetime
from google.adk.tools.tool_context import ToolContext
from google.adk.memory.memory_entry import MemoryEntry
from google.genai import types


async def remember_query_correction(
    original_query: str, corrected_query: str,
    correction_reason: str, table_or_domain: str,
    tool_context: ToolContext,
) -> dict:
    """Store a SQL query correction. Call when the user explicitly corrects generated SQL."""
    entry = MemoryEntry(
        content=types.Content(parts=[types.Part(
            text=f"CORRECTION [{table_or_domain}]: {original_query} → {corrected_query}. Reason: {correction_reason}"
        )]),
        custom_metadata={"type": "query_correction", "domain": table_or_domain,
                         "original_query": original_query, "corrected_query": corrected_query,
                         "reason": correction_reason},
        timestamp=datetime.now().isoformat(),
    )
    await tool_context.add_memory(memories=[entry])
    return {"status": "correction_saved", "domain": table_or_domain}


async def remember_preference(
    preference_category: str, preference_value: str,
    tool_context: ToolContext,
) -> dict:
    """Store a user preference (format, verbosity, language). Persists across all sessions."""
    tool_context.state[f"user:pref_{preference_category}"] = preference_value  # user: prefix persists
    entry = MemoryEntry(
        content=types.Content(parts=[types.Part(text=f"PREFERENCE [{preference_category}]: {preference_value}")]),
        custom_metadata={"type": "preference", "category": preference_category, "value": preference_value},
        timestamp=datetime.now().isoformat(),
    )
    await tool_context.add_memory(memories=[entry])
    return {"status": "preference_saved", "category": preference_category}


async def remember_schema_discovery(
    table_name: str, columns: list[str],
    filter_values: dict, tool_context: ToolContext,
) -> dict:
    """Cache a table's column list and valid filter values. Call after tool_list_tables or tool_schema_filter_values succeeds."""
    entry = MemoryEntry(
        content=types.Content(parts=[types.Part(text=f"SCHEMA [{table_name}]: columns={columns}")]),
        custom_metadata={"type": "schema_discovery", "table_name": table_name,
                         "columns": columns, "filter_values": filter_values},
        timestamp=datetime.now().isoformat(),
    )
    await tool_context.add_memory(memories=[entry])
    return {"status": "schema_cached", "table": table_name}


async def remember_term(
    term: str, definition: str, context: str,
    tool_context: ToolContext,
) -> dict:
    """Remember a business/domain term the user has defined. Call when user explains a term or acronym."""
    entry = MemoryEntry(
        content=types.Content(parts=[types.Part(text=f"VOCABULARY [{term}]: {definition}. Context: {context}")]),
        custom_metadata={"type": "vocabulary", "term": term, "definition": definition, "context": context},
        timestamp=datetime.now().isoformat(),
    )
    await tool_context.add_memory(memories=[entry])
    return {"status": "term_saved", "term": term}


async def remember_failed_pattern(
    wrong_pattern: str, correct_pattern: str,
    error_type: str, domain: str,
    tool_context: ToolContext,
) -> dict:
    """Record a SQL error pattern and its fix. Call after successfully recovering from a query error."""
    entry = MemoryEntry(
        content=types.Content(parts=[types.Part(
            text=f"FAILED_PATTERN [{domain}] error={error_type}: {wrong_pattern} → {correct_pattern}"
        )]),
        custom_metadata={"type": "failed_pattern", "domain": domain, "error_type": error_type,
                         "wrong_pattern": wrong_pattern, "correct_pattern": correct_pattern},
        timestamp=datetime.now().isoformat(),
    )
    await tool_context.add_memory(memories=[entry])
    return {"status": "pattern_saved", "error_type": error_type}


async def recall_corrections(
    query_context: str, tool_context: ToolContext,
) -> dict:
    """Recall past SQL corrections relevant to a domain. Call before generating adhoc SQL."""
    response = await tool_context.search_memory(query_context)
    items = [
        {"text": (e.content.parts[0].text if e.content and e.content.parts else ""),
         "metadata": e.custom_metadata or {}}
        for e in (response.memories or [])
        if (e.custom_metadata or {}).get("type") == "query_correction"
    ]
    return {"past_corrections": items,
            "hint": "Apply these when constructing SQL." if items else "No prior corrections found."}
```

### `shared/callbacks.py`

```python
from google.adk.agents.callback_context import CallbackContext

CORRECTION_SIGNALS = [
    "that's wrong", "incorrect", "fix the query", "wrong query", "should be",
    "salah", "bukan", "harusnya", "seharusnya", "ubah query", "perbaiki",
]

async def memory_extraction_callback(callback_context: CallbackContext) -> None:
    await callback_context.add_session_to_memory()  # archive turn to Redis

    last_user_text = ""
    for event in reversed(callback_context.session.events):
        if event.author == "user" and event.content and event.content.parts:
            last_user_text = (event.content.parts[0].text or "").lower()
            break

    if any(signal in last_user_text for signal in CORRECTION_SIGNALS):
        callback_context.state["temp:correction_detected"] = True  # temp: = current turn only
```

## Modified Files

### `collection_analysis_agent/agent.py`

Replace `root_agent = Agent(...)` with `app = App(...)`. Add imports:

```python
from google.adk.apps import App  # check exact import at implementation time
from shared.memory_tools import (
    remember_query_correction, remember_preference, remember_schema_discovery,
    remember_term, remember_failed_pattern, recall_corrections,
)
from shared.callbacks import memory_extraction_callback

_agent = Agent(
    model='gemini-3.1-flash-lite',
    name='collection_analysis_agent',
    description='...',
    instruction=BASE_SYSTEM_PROMPT,
    tools=[
        toolbox,
        remember_query_correction,
        remember_preference,
        remember_schema_discovery,
        remember_term,
        remember_failed_pattern,
        recall_corrections,
    ],
    after_agent_callback=memory_extraction_callback,
    planner=...,
    generate_content_config=...,
)

app = App(
    name="collection_analysis_agent",
    root_agent=_agent,
    events_compaction_config=EventsCompactionConfig(enable_session_compaction=True),
)
```

ADK CLI checks for `app` variable first (when present), then falls back to `root_agent`.

### `collection_analysis_agent/prompts.py`

Append to `BASE_SYSTEM_PROMPT`:

```
## Memory Protocol

**Before generating adhoc SQL** (using postgres-execute-sql):
- Call `recall_corrections` with the table or domain name (e.g. "debtors", "visit_activity").
- Apply any returned corrections when constructing SQL.
- If you have a cached schema (`schema_cache`), use it to skip re-querying `tool_list_tables`.

**After successful schema queries** (tool_list_tables, tool_schema_filter_values):
- Call `remember_schema_discovery` to cache the result for future sessions.

**After recovering from a SQL error**:
- Call `remember_failed_pattern` with the wrong fragment, the fix, the error type, and the domain.

**When the user corrects generated SQL**:
- Call `remember_query_correction` immediately.

**When the user explains a business term or acronym**:
- Call `remember_term` to store the definition.

**When the user states a format/verbosity preference**:
- Call `remember_preference`.

**If `temp:correction_detected` is set**:
- Ask: "Apa yang salah dari query tadi?" then call `remember_query_correction`.

**Active preferences** (from user: state, auto-applied):
- Response format: {user:pref_response_format}
- Verbosity: {user:pref_verbosity}
```

## Extending to Patterns 2 and 3

After `collection_analysis_agent` works:
- `collection_skill_agent/agent.py` and `collection_script_agent/agent.py`: same imports + tools + callback + `App` wrapper
- Both `prompts.py`: append the same MEMORY PROTOCOL section
- `services.yaml` and `shared/` are at project root — no duplication

## Updated Run Commands

```bash
# Start infrastructure (Toolbox + Redis)
cd mcp-toolbox && docker compose up -d && cd ..

# Run with session persistence + Redis memory
uv run adk web \
  --session_service_uri="sqlite:///./sessions.db" \
  --memory_service_uri="redis://localhost:6379" \
  .
```

## Verification

```bash
# 1. Confirm Redis is healthy
docker logs adk_redis
redis-cli -p 6379 ping   # → PONG

# 2. Start agent
uv run adk web --session_service_uri="sqlite:///./sessions.db" \
               --memory_service_uri="redis://localhost:6379" .

# 3. Test correction loop
#    a. Ask: "Tampilkan debitur dengan status aktif"
#    b. Say: "Salah, harusnya collection_status = 'ACTIVE'"
#    c. Agent should call remember_query_correction
#    d. New session (new browser tab) → ask same question
#    e. Agent calls recall_corrections → applies fix automatically

# 4. Test schema caching
#    Ask a question that triggers tool_list_tables
#    Agent should call remember_schema_discovery after getting schema
#    Next session: agent skips re-querying schema

# 5. Test vocabulary
#    Say: "FYI, 'kolektor' di sistem kami artinya field collector yang punya target harian"
#    Agent should call remember_term
#    Next session: agent uses this definition in analysis context

# 6. Verify Redis persistence
redis-cli -p 6379 KEYS "corrections:*"
redis-cli -p 6379 KEYS "schema_cache:*"
redis-cli -p 6379 KEYS "vocabulary:*"
redis-cli -p 6379 HGETALL "prefs:collection_analysis_agent:<user_id>"

# 7. Verify SQLite sessions survive restart
ls -la sessions.db
# Stop + restart adk web — conversations should reappear
```

## File Change Summary

| File | Action |
|---|---|
| `mcp-toolbox/docker-compose.yml` | Add Redis 8-alpine service + volumes section |
| `pyproject.toml` | Add `redis>=5.0` |
| `services.yaml` | Create — register `redis://` scheme |
| `shared/__init__.py` | Create — empty package marker |
| `shared/memory_service.py` | Create — RedisMemoryService (5 types + TODO stub) |
| `shared/memory_tools.py` | Create — 6 tool functions |
| `shared/callbacks.py` | Create — after_agent_callback |
| `collection_analysis_agent/agent.py` | Add imports, tools, callback, wrap in `App` |
| `collection_analysis_agent/prompts.py` | Append MEMORY PROTOCOL section |