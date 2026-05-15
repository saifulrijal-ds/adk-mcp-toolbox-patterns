# Google ADK Agent Memory Architecture
### Specialized Memory for SQL Agents with MCP Toolbox

> **Context:** This document covers extending a Google ADK-based SQL agent (connected to collection activity databases via MCP Toolbox) beyond standard `InMemorySessionService` — adding typed long-term memory for query corrections, user preferences, and behavioral patterns.

---

## Table of Contents

1. [ADK Memory Taxonomy](#1-adk-memory-taxonomy)
2. [Layer 1 — Persistent Session & `user:` State Prefix](#2-layer-1--persistent-session--user-state-prefix)
3. [Layer 2 — Custom `BaseMemoryService`](#3-layer-2--custom-basememoryservice)
4. [Layer 3 — `after_agent_callback` for Auto-Extraction](#4-layer-3--after_agent_callback-for-auto-extraction)
5. [Explicit Memory Write Tools](#5-explicit-memory-write-tools)
6. [Alternative: Mem0 as Drop-In `BaseMemoryService`](#6-alternative-mem0-as-drop-in-basememoryservice)
7. [Wiring Everything Together](#7-wiring-everything-together)
8. [Decision Guide](#8-decision-guide)
9. [References](#9-references)

---

## 1. ADK Memory Taxonomy

ADK has **three independent memory mechanisms** that serve different purposes and scopes. Confusing them is the most common source of incorrect implementations.

```
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 1: SESSION STATE  (session.state["key"])                 │
│                                                                 │
│  Key prefix     │ Scope                   │ Requires            │
│  ─────────────────────────────────────────────────────         │
│  [no prefix]    │ Current session only    │ Any SessionService  │
│  user:key       │ All sessions per user   │ Persistent Session  │  ← !!
│  app:key        │ All users, all sessions │ Persistent Session  │
│  temp:key       │ Current invocation only │ Any SessionService  │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 2: SESSION EVENTS (chat history)                         │
│                                                                 │
│  Managed by SessionService:                                     │
│  - InMemorySessionService    → dev only, lost on restart        │
│  - DatabaseSessionService    → SQLite/PostgreSQL, persistent    │
│  - VertexAiSessionService    → GCP managed                      │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 3: MEMORY SERVICE (long-term knowledge store)            │
│                                                                 │
│  Managed by BaseMemoryService:                                  │
│  - InMemoryMemoryService     → dev only, keyword search         │
│  - VertexAiMemoryBankService → GCP managed, LLM extraction      │
│  - Custom (ChromaDB, Mem0, Redis) → self-hosted, vector search  │
└─────────────────────────────────────────────────────────────────┘
```

> **Key distinction:**
> - `Session / State` → *current interaction* — what's happening now
> - `MemoryService` → *searchable archive* — what happened across all past conversations
>
> Source: [ADK Sessions Overview](https://google.github.io/adk-docs/sessions/)

### `BaseMemoryService` Interface

The interface supports four operations ([ADK Memory Docs](https://google.github.io/adk-docs/sessions/memory/)):

| Method | Description | Optional? |
|--------|-------------|-----------|
| `add_session_to_memory(session)` | Ingest a completed session into long-term store | No |
| `add_events_to_memory(events)` | Append a delta of events mid-session | **Yes** |
| `add_memory(entry)` | Direct write of a pre-built `MemoryEntry` | **Yes** |
| `search_memory(app_name, user_id, query)` | Query the knowledge store | No |

> ⚠️ Operations 2 and 3 raise `NotImplementedError` in the base class. Verify your concrete implementation supports them before relying on direct writes.

---

## 2. Layer 1 — Persistent Session & `user:` State Prefix

### 2.1 Replace `InMemorySessionService`

`InMemorySessionService` is development-only. All session data (including `user:` prefixed keys) is lost on restart.

```python
from google.adk.sessions import DatabaseSessionService

# Development
session_service = DatabaseSessionService(
    db_url="sqlite+aiosqlite:///./agent_sessions.db"
)

# Production
session_service = DatabaseSessionService(
    db_url="postgresql+asyncpg://user:password@host/dbname"
)
```

> Reference: [Building Persistent AI Agents with ADK and CloudSQL (Google Codelabs)](https://codelabs.developers.google.com/persistent-adk-cloudsql)

### 2.2 `user:` Prefix for Simple Cross-Session Preferences

Once backed by `DatabaseSessionService`, any key prefixed with `user:` automatically persists across all sessions for the same `user_id`:

```python
async def save_preference(
    category: str,
    value: str,
    tool_context: ToolContext
) -> dict:
    """Persist a user preference across all future sessions."""
    tool_context.state[f"user:pref_{category}"] = value
    return {"status": "saved", "key": f"user:pref_{category}"}
```

Inject state values directly into the agent instruction via ADK's `{}` templating:

```python
agent = Agent(
    model="gemini-2.5-flash",
    instruction="""You are a SQL agent connected to a collection activity database.

Active user preferences:
- Response format: {user:pref_response_format}
- Output verbosity: {user:pref_verbosity}
- Preferred time filter: {user:pref_time_range}

Always apply these preferences before formatting your response.
""",
    tools=[...]
)
```

> Reference: [ADK State Docs — Prefixes](https://google.github.io/adk-docs/sessions/state/)  
> Reference: [Remember This: Agent State and Memory with ADK (Google Cloud Blog)](https://cloud.google.com/blog/topics/developers-practitioners/remember-this-agent-state-and-memory-with-adk)

### 2.3 State Prefix Decision Table

```python
# Session-scoped (reset each conversation)
tool_context.state["current_query_domain"] = "debtors"
tool_context.state["active_filter"] = {"branch": "JKT-01"}

# User-scoped (persists across ALL sessions for this user)
tool_context.state["user:response_format"] = "table"
tool_context.state["user:preferred_language"] = "id"
tool_context.state["user:last_known_role"] = "credit_analyst"

# App-scoped (global, all users)
tool_context.state["app:db_schema_version"] = "2.1"
tool_context.state["app:maintenance_mode"] = False

# Temp (current invocation only, not persisted)
tool_context.state["temp:raw_sql_result"] = query_output
tool_context.state["temp:correction_detected"] = True
```

---

## 3. Layer 2 — Custom `BaseMemoryService`

For typed, searchable, semantic memory (query corrections, behavioral patterns), implement a custom `BaseMemoryService`.

### 3.1 ChromaDB-Backed Implementation

```python
# pip install chromadb google-adk

from google.adk.memory.base_memory_service import BaseMemoryService, SearchMemoryResponse
from google.adk.memory.memory_entry import MemoryEntry
from google.adk.sessions import Session
from google.genai import types
import chromadb
from datetime import datetime

MEMORY_TYPES = ["query_correction", "preference", "flow_pattern", "context"]


class AgentMemoryService(BaseMemoryService):
    """
    Typed, persistent memory service backed by ChromaDB.
    Supports direct writes (add_memory) and semantic search (search_memory).
    """

    def __init__(self, chroma_path: str = "./agent_memory"):
        super().__init__()
        self._client = chromadb.PersistentClient(path=chroma_path)
        # Separate collection per memory type for precision retrieval
        self._collections = {
            mtype: self._client.get_or_create_collection(
                name=f"agent_{mtype}",
                metadata={"hnsw:space": "cosine"}
            )
            for mtype in MEMORY_TYPES
        }

    async def add_session_to_memory(self, session: Session) -> None:
        """Ingest a completed session as a context memory."""
        text = self._session_to_text(session)
        if not text:
            return
        self._collections["context"].upsert(
            documents=[text],
            metadatas=[{
                "user_id": session.user_id,
                "session_id": session.id,
                "type": "context",
                "timestamp": datetime.now().isoformat()
            }],
            ids=[f"{session.id}_summary"]
        )

    async def add_memory(
        self, *, app_name: str, user_id: str, memory: MemoryEntry
    ) -> None:
        """Directly write a typed MemoryEntry (query corrections, preferences, etc.)."""
        metadata = dict(memory.custom_metadata or {})
        memory_type = metadata.get("type", "context")
        if memory_type not in MEMORY_TYPES:
            memory_type = "context"

        text = " ".join(
            part.text
            for part in (memory.content.parts or [])
            if part.text
        )
        if not text:
            return

        mem_id = f"{user_id}_{memory_type}_{datetime.now().timestamp()}"
        metadata.update({
            "user_id": user_id,
            "app_name": app_name,
            "timestamp": datetime.now().isoformat()
        })

        self._collections[memory_type].add(
            documents=[text],
            metadatas=[metadata],
            ids=[mem_id]
        )

    async def search_memory(
        self, *, app_name: str, user_id: str, query: str
    ) -> SearchMemoryResponse:
        """Semantic search across all memory types, scoped to user_id."""
        memories = []
        for mtype, collection in self._collections.items():
            try:
                results = collection.query(
                    query_texts=[query],
                    n_results=3,
                    where={"user_id": user_id}
                )
                for doc, meta in zip(
                    results["documents"][0],
                    results["metadatas"][0]
                ):
                    memories.append(MemoryEntry(
                        content=types.Content(parts=[types.Part(text=doc)]),
                        custom_metadata=meta
                    ))
            except Exception:
                continue  # collection may be empty

        # Sort by recency
        memories.sort(
            key=lambda m: m.custom_metadata.get("timestamp", ""),
            reverse=True
        )
        return SearchMemoryResponse(memories=memories[:8])

    def _session_to_text(self, session: Session) -> str:
        parts = []
        for event in session.events:
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        parts.append(f"{event.author}: {part.text}")
        return "\n".join(parts[-20:])  # last 20 turns
```

### 3.2 `MemoryEntry` and `custom_metadata` Schema

Use `custom_metadata` as a type tag so you can filter searches by memory kind:

```python
from google.adk.memory.memory_entry import MemoryEntry
from google.genai import types

# Query correction
MemoryEntry(
    content=types.Content(parts=[types.Part(
        text="QUERY CORRECTION\n"
             "Wrong: SELECT * FROM debtors WHERE status = 'aktif'\n"
             "Correct: SELECT * FROM debtors WHERE collection_status = 'ACTIVE'\n"
             "Reason: Column name is collection_status not status"
    )]),
    custom_metadata={
        "type": "query_correction",
        "domain": "debtors",
        "table": "debtors",
        "correction_reason": "wrong column name"
    }
)

# User preference
MemoryEntry(
    content=types.Content(parts=[types.Part(
        text="USER PREFERENCE [response_format]: Always show results as markdown table with summary row"
    )]),
    custom_metadata={
        "type": "preference",
        "category": "response_format"
    }
)
```

### 3.3 Multiple Memory Services (Advanced)

ADK allows instantiating a second `BaseMemoryService` directly inside a tool for specialized knowledge bases — the framework-configured one and a manually instantiated one coexist:

```python
# Agent gets framework-configured service for conversation memory
# Manually instantiate a second service for a domain knowledge base

from google.adk.memory import InMemoryMemoryService
from google.adk.tools import ToolContext

domain_kb = AgentMemoryService(chroma_path="./domain_knowledge")

async def search_domain_knowledge(query: str, tool_context: ToolContext) -> dict:
    """Search a separate domain knowledge base (schema docs, business rules)."""
    response = await domain_kb.search_memory(
        app_name="sql_agent",
        user_id=tool_context.invocation_context.session.user_id,
        query=query
    )
    return {
        "results": [
            part.text
            for entry in response.memories
            for part in (entry.content.parts or [])
            if part.text
        ]
    }
```

> Reference: [ADK Memory Docs — Multiple Services](https://google.github.io/adk-docs/sessions/memory/)

---

## 4. Layer 3 — `after_agent_callback` for Auto-Extraction

Automatically commit session data to long-term memory at the end of each agent turn.

```python
from google.adk.agents.callback_context import CallbackContext

CORRECTION_SIGNALS = [
    # English
    "that's wrong", "incorrect", "fix the query", "wrong query",
    "should be", "not that",
    # Indonesian
    "salah", "bukan", "harusnya", "seharusnya", "ubah query",
    "query nya salah", "perbaiki"
]

async def memory_extraction_callback(callback_context: CallbackContext):
    """
    After each agent turn:
    1. Commit session to long-term memory.
    2. Detect implicit correction signals and flag for explicit write.
    """
    # Commit session to MemoryService
    await callback_context.add_session_to_memory()

    # Detect correction signals in last user message
    events = callback_context.session.events
    last_user_event = next(
        (e for e in reversed(events) if e.author == "user"), None
    )
    if last_user_event and last_user_event.content:
        user_text = " ".join(
            p.text for p in last_user_event.content.parts if p.text
        ).lower()
        if any(sig in user_text for sig in CORRECTION_SIGNALS):
            callback_context.state["temp:correction_detected"] = True

    return None


agent = Agent(
    model="gemini-2.5-flash",
    name="sql_collection_agent",
    instruction="...",
    tools=[...],
    after_agent_callback=memory_extraction_callback
)
```

> Reference: [Agent Platform Memory Bank Quickstart with ADK (Google Cloud)](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank/adk-quickstart)

---

## 5. Explicit Memory Write Tools

Expose memory write capabilities as tools so the LLM can deliberately store corrections and preferences when it detects them:

```python
from google.adk.tools import ToolContext
from google.adk.memory.memory_entry import MemoryEntry
from google.genai import types
from datetime import datetime

async def remember_query_correction(
    original_query: str,
    corrected_query: str,
    correction_reason: str,
    table_or_domain: str,
    tool_context: ToolContext
) -> dict:
    """
    Store a SQL query correction for future reference.
    Call this when the user explicitly corrects a query you generated.
    """
    memory_text = (
        f"QUERY CORRECTION [{table_or_domain}]\n"
        f"Wrong:   {original_query}\n"
        f"Correct: {corrected_query}\n"
        f"Reason:  {correction_reason}"
    )
    entry = MemoryEntry(
        content=types.Content(parts=[types.Part(text=memory_text)]),
        custom_metadata={
            "type": "query_correction",
            "domain": table_or_domain,
            "correction_reason": correction_reason,
            "timestamp": datetime.now().isoformat()
        }
    )
    # Access memory service via invocation context
    session = tool_context.invocation_context.session
    await tool_context.invocation_context.memory_service.add_memory(
        app_name=session.app_name,
        user_id=session.user_id,
        memory=entry
    )
    return {
        "status": "correction_saved",
        "domain": table_or_domain,
        "message": f"I'll remember this correction for '{table_or_domain}' queries."
    }


async def remember_preference(
    preference_category: str,
    preference_value: str,
    tool_context: ToolContext
) -> dict:
    """
    Save a user preference that persists across sessions.
    Use for: response format, verbosity, output structure, language, etc.
    """
    # Dual-write: fast user: state for in-context injection + MemoryService for search
    tool_context.state[f"user:pref_{preference_category}"] = preference_value

    memory_text = f"USER PREFERENCE [{preference_category}]: {preference_value}"
    entry = MemoryEntry(
        content=types.Content(parts=[types.Part(text=memory_text)]),
        custom_metadata={
            "type": "preference",
            "category": preference_category,
            "timestamp": datetime.now().isoformat()
        }
    )
    session = tool_context.invocation_context.session
    await tool_context.invocation_context.memory_service.add_memory(
        app_name=session.app_name,
        user_id=session.user_id,
        memory=entry
    )
    return {"status": "preference_saved", "category": preference_category}


async def recall_corrections(
    query_context: str,
    tool_context: ToolContext
) -> dict:
    """
    Search past query corrections relevant to the current query context.
    Call this before generating adhoc SQL to avoid known mistakes.
    """
    response = await tool_context.search_memory(query_context)
    corrections = [
        part.text
        for entry in response.memories
        for part in (entry.content.parts or [])
        if part.text
        and entry.custom_metadata.get("type") == "query_correction"
    ]
    return {
        "past_corrections": corrections,
        "count": len(corrections),
        "hint": "Apply these corrections when constructing your SQL."
    }
```

**Add to agent instruction** to guide when these tools should be used:

```python
instruction = """You are a SQL agent connected to a collection activity database.

MEMORY PROTOCOL:
- Before generating adhoc SQL: call recall_corrections with the relevant table/domain.
- When a user says a query is wrong or corrects your SQL: call remember_query_correction.
- When a user states a format/output preference: call remember_preference.
- If temp:correction_detected is True in state, actively ask the user what was wrong
  and call remember_query_correction before proceeding.

User preferences (auto-injected):
- Response format: {user:pref_response_format}
- Verbosity: {user:pref_verbosity}
"""
```

---

## 6. Alternative: Mem0 as Drop-In `BaseMemoryService`

[Mem0](https://mem0.ai) provides a managed memory layer with LLM-based extraction, deduplication, and contradiction resolution. It has a native `BaseMemoryService` implementation for ADK.

```python
# pip install mem0ai google-adk

import os
from typing import Optional, override
from google.adk.memory.base_memory_service import BaseMemoryService, SearchMemoryResponse
from google.adk.memory.memory_entry import MemoryEntry
from google.adk.sessions import Session
from google.genai import types
from mem0 import MemoryClient


class Mem0MemoryService(BaseMemoryService):
    """ADK-native Mem0 memory service implementation."""

    def __init__(self, api_key: Optional[str] = None):
        super().__init__()
        api_key = api_key or os.environ.get("MEM0_API_KEY")
        self._client = MemoryClient(api_key=api_key) if api_key else None

    @override
    async def add_session_to_memory(self, session: Session) -> None:
        if not self._client:
            return
        messages = [
            {"role": event.author, "content": self._event_text(event)}
            for event in session.events
            if self._event_text(event)
        ]
        if messages:
            self._client.add(messages, user_id=session.user_id)

    @override
    async def search_memory(
        self, *, app_name: str, user_id: str, query: str
    ) -> SearchMemoryResponse:
        if not self._client:
            return SearchMemoryResponse(memories=[])
        results = self._client.search(
            query, filters={"user_id": user_id}, limit=5
        )
        entries = [
            MemoryEntry(
                content=types.Content(
                    parts=[types.Part(text=mem.get("memory", ""))]
                ),
                custom_metadata={"source": "mem0", "user_id": user_id}
            )
            for mem in results.get("results", [])
        ]
        return SearchMemoryResponse(memories=entries)

    def _event_text(self, event) -> str:
        if event.content and event.content.parts:
            return " ".join(p.text for p in event.content.parts if p.text)
        return ""
```

Pass it to the `Runner` exactly like any other `BaseMemoryService`:

```python
memory_service = Mem0MemoryService(api_key=os.getenv("MEM0_API_KEY"))
runner = Runner(
    agent=agent,
    app_name="sql_collection_agent",
    session_service=session_service,
    memory_service=memory_service,
)
```

### Mem0 vs. Custom ChromaDB

| | Mem0 (Managed) | Custom ChromaDB |
|---|---|---|
| Setup | API key only | Self-hosted, infra required |
| Extraction | LLM-based auto-extraction | Manual / callback |
| Deduplication | Built-in | Manual |
| Contradiction resolution | Built-in | Manual |
| Cost | API calls | Compute + storage |
| Privacy | Data leaves your infra | Fully on-prem |
| Offline support | No | Yes |

> Reference: [Mem0 + ADK MemoryService Integration (GitHub Issue #3999)](https://github.com/mem0ai/mem0/issues/3999)

---

## 7. Wiring Everything Together

```python
import asyncio
from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from google_adk_toolbox import ToolboxClient  # MCP Toolbox

# --- Services ---
session_service = DatabaseSessionService(
    db_url="postgresql+asyncpg://user:pass@localhost/agent_db"
)
memory_service = AgentMemoryService(chroma_path="./agent_memory")

# --- MCP Toolbox (predefined + adhoc query tools) ---
toolbox = ToolboxClient("http://localhost:5000")
toolbox_tools = toolbox.load_toolset("collection_activity")

# --- Agent ---
agent = Agent(
    model="gemini-2.5-flash",
    name="sql_collection_agent",
    instruction="""...""",
    tools=[
        *toolbox_tools,
        remember_query_correction,
        remember_preference,
        recall_corrections,
    ],
    after_agent_callback=memory_extraction_callback,
)

# --- Runner ---
runner = Runner(
    agent=agent,
    app_name="sql_collection_agent",
    session_service=session_service,
    memory_service=memory_service,
)

# --- Run ---
async def main():
    session = await session_service.create_session(
        app_name="sql_collection_agent",
        user_id="analyst_001",
    )
    async for event in runner.run_async(
        user_id="analyst_001",
        session_id=session.id,
        new_message=types.Content(parts=[types.Part(text="Show active debtors in JKT-01")])
    ):
        if event.is_final_response():
            print(event.content.parts[0].text)

asyncio.run(main())
```

---

## 8. Decision Guide

```
USE CASE                                  SOLUTION
─────────────────────────────────────────────────────────────────────
Simple prefs: format, language,           user: state prefix
verbosity, time range                     DatabaseSessionService

Cross-session recall without GCP          Custom BaseMemoryService
                                          + ChromaDB backend

SQL/query correction feedback loop        Custom MemoryService
                                          + typed MemoryEntry
                                          + explicit write tool (remember_query_correction)

Semantic recall from past sessions        MemoryService
("remember when we discussed X")          + search_memory via tool

Fully managed + on GCP                    VertexAiMemoryBankService
                                          (Preview, requires Agent Runtime)

Best ecosystem support, managed           Mem0 BaseMemoryService
extraction, deduplication                 (simplest, SaaS)

Auto-extract memories from sessions       after_agent_callback
without explicit tool calls               + add_session_to_memory()

Multiple specialized knowledge bases     Multiple BaseMemoryService instances
(user memory + domain KB)                 (1 via Runner, rest instantiated in tools)
```

---

## 9. References

### Official Google ADK Documentation
- [ADK Sessions Overview](https://google.github.io/adk-docs/sessions/) — Session, State, and Memory concept introduction
- [ADK State Docs](https://google.github.io/adk-docs/sessions/state/) — Full prefix reference (`user:`, `app:`, `temp:`)
- [ADK Memory Docs](https://google.github.io/adk-docs/sessions/memory/) — `BaseMemoryService`, implementations, search patterns
- [ADK Session Docs](https://google.github.io/adk-docs/sessions/session/) — `SessionService` implementations and lifecycle

### Google Cloud Guides
- [Remember This: Agent State and Memory with ADK](https://cloud.google.com/blog/topics/developers-practitioners/remember-this-agent-state-and-memory-with-adk) — Google Cloud Blog, Aug 2025. Practical walkthrough of short-term vs long-term memory, `VertexAiMemoryBankService`, and `user:` prefix patterns.
- [Agent Platform Memory Bank Quickstart with ADK](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank/adk-quickstart) — Official quickstart for `VertexAiMemoryBankService` and callback-based memory generation.
- [Building Persistent AI Agents with ADK and CloudSQL (Google Codelabs)](https://codelabs.developers.google.com/persistent-adk-cloudsql) — Hands-on lab: `DatabaseSessionService` with PostgreSQL on Cloud SQL, session vs user-scoped state.

### Community & Ecosystem
- [State and Memory Management in Google ADK: A Practical Tutorial](https://medium.com/@juanc.olamendy/state-and-memory-management-in-google-adk-a-practical-tutorial-4ebcc9e73d3a) — Medium, Oct 2025. Code-heavy tutorial on all four state scopes with examples.
- [Building Persistent Sessions with Google ADK](https://medium.com/@juanc.olamendy/building-persistent-sessions-with-google-adk-a-comprehensive-guide-c3bab191269d) — Medium, Dec 2025. `DatabaseSessionService` patterns, tool design, state schema design.
- [Google ADK Masterclass Part 5: Session and Memory Management](https://saptak.in/writing/2025/05/10/google-adk-masterclass-part5) — Series covering `InMemorySessionService` with initial state injection.
- [Summary: Google's Context Engineering — Sessions & Memory](https://vanducng.dev/2026/01/12/Google-Context-Engineering-Sessions-Memory-Summary/) — Summary of Google's Context Engineering whitepaper (Milam & Gulli, Nov 2025). Covers memory-as-a-tool pattern, async extraction, confidence scoring.

### Integrations & Third-Party
- [Mem0 + ADK MemoryService Integration (GitHub Issue #3999)](https://github.com/mem0ai/mem0/issues/3999) — Native `BaseMemoryService` implementation wrapping Mem0 platform. Recommends `PreloadMemoryTool` over function-tool approach.
- [adk-redis: Redis Integration for Google ADK](https://github.com/redis-developer/adk-redis) — Redis-backed SessionService, MemoryService, and vector search tools for ADK.
- [Mem0 Documentation](https://docs.mem0.ai) — Official Mem0 docs for the managed memory platform.
- [ChromaDB Documentation](https://docs.trychroma.com) — Self-hosted vector store used in the custom `BaseMemoryService` implementation above.

---

*Last updated: May 2026*
