# Redis Integration with Google ADK
### Persistent Memory, Sessions, and Semantic Search — Fully Local

> **Context:** This document covers `adk-redis`, the official Redis integration library for Google ADK. It elaborates on architecture, local Docker setup, two-tier memory, semantic search tools, and semantic caching — all runnable without any cloud dependency.

---

## Table of Contents

1. [Why Redis over ChromaDB or InMemory?](#1-why-redis-over-chromadb-or-inmemory)
2. [Architecture Overview](#2-architecture-overview)
3. [Local Setup with Docker Compose](#3-local-setup-with-docker-compose)
4. [Installation](#4-installation)
5. [Working Memory — `RedisWorkingMemorySessionService`](#5-working-memory--redisworkingmemorysessionservice)
6. [Long-Term Memory — `RedisLongTermMemoryService`](#6-long-term-memory--redislongtermemoryservice)
7. [Integration Patterns (Framework vs Tools vs MCP)](#7-integration-patterns-framework-vs-tools-vs-mcp)
8. [Semantic Search Tools via RedisVL](#8-semantic-search-tools-via-redisvl)
9. [Semantic Caching](#9-semantic-caching)
10. [Wiring Everything: Full Agent Example](#10-wiring-everything-full-agent-example)
11. [Monitoring with RedisInsight](#11-monitoring-with-redisinsight)
12. [Local vs Cloud Comparison](#12-local-vs-cloud-comparison)
13. [References](#13-references)

---

## 1. Why Redis over ChromaDB or InMemory?

| Capability | InMemory | ChromaDB | **Redis (adk-redis)** |
|---|---|---|---|
| Persistence across restarts | ❌ | ✅ | ✅ |
| Session storage (BaseSessionService) | ✅ | ❌ | ✅ |
| Memory storage (BaseMemoryService) | ✅ | ✅ (custom) | ✅ |
| Auto-summarization when context too long | ❌ | ❌ | ✅ |
| Recency-boosted search | ❌ | ❌ | ✅ |
| Semantic (vector) search | ❌ | ✅ | ✅ |
| Full-text + hybrid search | ❌ | ❌ | ✅ |
| Semantic LLM response caching | ❌ | ❌ | ✅ |
| MCP tool exposure of memory | ❌ | ❌ | ✅ |
| Runs fully local (no cloud) | ✅ | ✅ | ✅ |
| Single infra for sessions + memory + search | ❌ | ❌ | ✅ |

The key differentiator is that Redis becomes **one unified infrastructure layer** for sessions, long-term memory, vector search, and caching — instead of running separate stores for each.

> Reference: [Build Google ADK Agents with persistent, real-time memory on Redis (Redis Blog)](https://redis.io/blog/build-google-adk-agents-with-persistent-real-time-memory-on-redis/)

---

## 2. Architecture Overview

`adk-redis` connects three backend systems to the ADK framework:

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          ADK AGENT (Google ADK)                          │
│                                                                          │
│   Runner                                                                 │
│   ├── session_service  → RedisWorkingMemorySessionService   ─────────┐  │
│   └── memory_service   → RedisLongTermMemoryService         ────────┐│  │
│                                                                      ││  │
│   Tools                                                              ││  │
│   ├── RedisVectorSearchTool  ───────────────────────────────────┐   ││  │
│   ├── RedisTextSearchTool    ───────────────────────────────────┤   ││  │
│   └── RedisHybridSearchTool  ───────────────────────────────────┤   ││  │
│                                                                  │   ││  │
│   Caching                                                        │   ││  │
│   └── LLMResponseCache / ToolCache ─────────────────────────┐   │   ││  │
└─────────────────────────────────────────────────────────────────────────┘
          │                   │                   │       │   │   ││
          ▼                   ▼                   │       ▼   ▼   ▼▼
┌──────────────────┐ ┌──────────────────┐         │  ┌─────────────────┐
│ Redis Agent      │ │ Redis Agent      │         │  │   Redis 8.4+    │
│ Memory Server    │ │ Memory Server    │         │  │                 │
│ (port 8088)      │ │ (port 8088)      │         └─►│ RedisVL         │
│                  │ │                  │            │ Vector Index     │
│ - Working memory │ │ - Long-term mem  │            │ (HNSW / cosine) │
│ - Auto-summary   │ │ - Fact extract.  │            │                 │
│ - Context window │ │ - Recency boost  │            │ Full-text Index │
│   management    │ │ - Semantic search│            │ Hybrid search   │
└────────┬─────────┘ └────────┬─────────┘            └────────┬────────┘
         │                    │                                │
         └────────────────────┴────────────────────────────────┘
                                        │
                              ┌─────────▼──────────┐
                              │     Redis 8.4+      │
                              │  (port 6379)        │
                              │                     │
                              │  - Hashes (session) │
                              │  - Vectors (memory) │
                              │  - JSON (state)     │
                              │  - Streams (events) │
                              └─────────────────────┘
```

### Two-Tier Memory Model

Redis Agent Memory gives ADK agents two tiers of persistent memory:

- **Working memory** (`RedisWorkingMemorySessionService`) — session-scoped storage for the current conversation, with automatic summarization when the context window is approached.
- **Long-term memory** (`RedisLongTermMemoryService`) — facts extracted from past conversations, stored as vectors and searchable by semantic similarity with optional recency boosting.

### Component Responsibilities

| Component | Role |
|---|---|
| **Redis Agent Memory Server** | Working memory, long-term memory, auto-summarization, memory search API |
| **RedisVL** | Vector indexing, semantic search tools, hybrid search, semantic cache provider |
| **LangCache** | Managed semantic caching with server-side embeddings (cloud only) |

> Reference: [Redis with Google ADK — Official Docs](https://redis.io/docs/latest/integrate/google-adk/)

---

## 3. Local Setup with Docker Compose

Everything runs locally. **Redis 8.4+** is required because it ships with the Redis Query Engine (vector search, full-text, JSON) natively.

### 3.1 Minimal Setup (Memory + Sessions only)

```yaml
# docker-compose.yml
version: "3.9"

services:
  redis:
    image: redis:8.4-alpine
    container_name: redis
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

  agent-memory-server:
    image: redislabs/agent-memory-server:latest
    container_name: agent-memory-server
    ports:
      - "8088:8088"
    environment:
      REDIS_URL: redis://redis:6379
      GEMINI_API_KEY: ${GEMINI_API_KEY}
      GENERATION_MODEL: gemini/gemini-2.0-flash
      EMBEDDING_MODEL: gemini/text-embedding-004
    depends_on:
      redis:
        condition: service_healthy
    command: >
      agent-memory api
      --host 0.0.0.0
      --port 8088
      --task-backend=asyncio
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8088/health"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  redis_data:
```

> ⚠️ The `Agent Memory Server` uses an LLM (Gemini/OpenAI) to **extract** facts from sessions. This is the only cloud call — the Redis store itself is fully local.  
> If you want **zero cloud calls** even for extraction, skip `RedisLongTermMemoryService` and use only `RedisWorkingMemorySessionService` + your own `BaseMemoryService` for writes.

### 3.2 Full Setup (with RedisInsight UI + OpenAI option)

```yaml
# docker-compose.full.yml
version: "3.9"

services:
  redis:
    image: redis:8.4-alpine
    container_name: redis
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

  agent-memory-server:
    image: redislabs/agent-memory-server:latest
    container_name: agent-memory-server
    ports:
      - "8088:8088"
    environment:
      REDIS_URL: redis://redis:6379
      # Choose ONE model provider:
      GEMINI_API_KEY: ${GEMINI_API_KEY}
      GENERATION_MODEL: gemini/gemini-2.0-flash
      EMBEDDING_MODEL: gemini/text-embedding-004
      # --- OR use OpenAI: ---
      # OPENAI_API_KEY: ${OPENAI_API_KEY}
      # GENERATION_MODEL: gpt-4o-mini
      # EMBEDDING_MODEL: text-embedding-3-small
    depends_on:
      redis:
        condition: service_healthy
    command: >
      agent-memory api
      --host 0.0.0.0
      --port 8088
      --task-backend=asyncio

  redisinsight:
    image: redis/redisinsight:latest
    container_name: redisinsight
    ports:
      - "5540:5540"
    depends_on:
      - redis

volumes:
  redis_data:
```

### 3.3 Startup Commands

```bash
# Start services
docker compose up -d

# Verify Redis is up
redis-cli -p 6379 ping            # → PONG

# Verify Agent Memory Server
curl http://localhost:8088/health  # → {"status": "ok"}

# View logs
docker compose logs -f agent-memory-server

# Stop
docker compose down

# Stop + remove all data (full reset)
docker compose down -v
```

### 3.4 Environment File

```bash
# .env
GEMINI_API_KEY=your_gemini_api_key
# OR
OPENAI_API_KEY=your_openai_api_key
```

---

## 4. Installation

```bash
# Session + memory services (requires Agent Memory Server)
pip install "adk-redis[memory]"

# Semantic search tools via RedisVL
pip install "adk-redis[search]"

# Managed semantic caching via LangCache (cloud)
pip install "adk-redis[langcache]"

# Everything
pip install "adk-redis[all]"

# Or install from GitHub (latest)
pip install git+https://github.com/redis-developer/adk-redis.git@main
```

Full dependencies pulled in by each extra:

| Extra | Installs |
|---|---|
| `memory` | `redis`, `redis-agent-memory-client`, `google-adk` |
| `search` | `redisvl`, `google-adk` |
| `langcache` | `redisvl`, `langcache-client` |
| `all` | Everything above |

---

## 5. Working Memory — `RedisWorkingMemorySessionService`

Replaces `InMemorySessionService` or `DatabaseSessionService`. Stores the active conversation in Redis with **automatic context window management** — when the session grows too long, it summarizes older turns using an LLM and compresses them into a shorter history.

```python
from adk_redis.sessions import (
    RedisWorkingMemorySessionService,
    RedisWorkingMemorySessionServiceConfig,
)

session_service = RedisWorkingMemorySessionService(
    config=RedisWorkingMemorySessionServiceConfig(
        api_base_url="http://localhost:8088",   # Agent Memory Server
        default_namespace="sql_agent",
        model_name="gemini-2.0-flash",          # for auto-summarization
        context_window_max=8000,                # tokens before summarization kicks in
    )
)
```

### Configuration Parameters

| Parameter | Description | Default |
|---|---|---|
| `api_base_url` | Agent Memory Server URL | required |
| `default_namespace` | Namespace prefix for session keys | `"default"` |
| `model_name` | LLM for auto-summarization | required |
| `context_window_max` | Token threshold before summary | `8000` |

### What Happens at `context_window_max`

```
Turn 1:  user → agent → tool → response     [stored raw]
Turn 2:  user → agent → tool → response     [stored raw]
...
Turn N:  [context approaches 8000 tokens]
         → Agent Memory Server calls LLM
         → Older turns condensed into summary
         → Summary stored; raw old turns dropped
Turn N+1: agent receives summary + recent raw turns
```

This prevents context overflow in long SQL investigation sessions without losing the conceptual thread.

---

## 6. Long-Term Memory — `RedisLongTermMemoryService`

Replaces `InMemoryMemoryService` or a custom `BaseMemoryService`. At the end of a session (via `after_agent_callback`), the Agent Memory Server uses an LLM to **extract key facts** from the conversation and stores them as vectors in Redis. Future sessions can retrieve relevant facts via semantic search.

```python
from adk_redis.memory import (
    RedisLongTermMemoryService,
    RedisLongTermMemoryServiceConfig,
)

memory_service = RedisLongTermMemoryService(
    config=RedisLongTermMemoryServiceConfig(
        api_base_url="http://localhost:8088",
        default_namespace="sql_agent",
        top_k=5,             # max facts retrieved per search
        distance_threshold=0.7,
        recency_boost=True,  # recent memories score higher
    )
)
```

### Recency Boost

When `recency_boost=True`, the search score is:

```
final_score = semantic_similarity * (1 + recency_weight * age_decay)
```

This means a memory from last week about a wrong column name will rank higher than a semantically similar but 6-month-old correction — which is the correct behavior for SQL correction workflows.

### `after_agent_callback` for Auto-Extraction

```python
from google.adk.agents.callback_context import CallbackContext

async def commit_to_long_term_memory(callback_context: CallbackContext):
    """Commit session to long-term memory at end of each agent turn."""
    await callback_context.add_session_to_memory()
    return None

agent = Agent(
    model="gemini-2.5-flash",
    name="sql_collection_agent",
    instruction="...",
    tools=[...],
    after_agent_callback=commit_to_long_term_memory,
)
```

### Memory Retrieval via `search_memory` Tool

```python
from google.adk.tools import ToolContext

async def search_past_memory(query: str, tool_context: ToolContext) -> dict:
    """Search long-term memory for relevant past context."""
    response = await tool_context.search_memory(query)
    return {
        "results": [
            part.text
            for entry in response.memories
            for part in (entry.content.parts or [])
            if part.text
        ]
    }
```

Or use `PreloadMemoryTool` for automatic injection at prompt construction time (no tool call needed):

```python
from google.adk.tools.preload_memory_tool import PreloadMemoryTool

agent = Agent(
    model="gemini-2.5-flash",
    tools=[
        PreloadMemoryTool(),   # auto-injects relevant memories into context
        ...other_tools,
    ]
)
```

---

## 7. Integration Patterns (Framework vs Tools vs MCP)

`adk-redis` supports three ways to expose memory to the agent:

```
┌──────────────────────────────────────────────────────────────────┐
│  PATTERN 1: Framework Services (Invisible Infrastructure)        │
│                                                                  │
│  runner = Runner(                                                │
│      session_service = RedisWorkingMemorySessionService(...),    │
│      memory_service  = RedisLongTermMemoryService(...),          │
│  )                                                               │
│                                                                  │
│  ✅ Memory managed automatically by ADK runner                   │
│  ✅ Agent doesn't "know" about memory — it just uses it          │
│  ❌ Agent has no control over when/what to store                 │
├──────────────────────────────────────────────────────────────────┤
│  PATTERN 2: REST Tools (LLM Explicit Control)                    │
│                                                                  │
│  from adk_redis import create_memory_rest_toolset                │
│  memory_tools = create_memory_rest_toolset(                      │
│      server_url="http://localhost:8088"                          │
│  )                                                               │
│  # Exposes: search_memory, create_memory, update_memory,        │
│  #          delete_memory tools                                  │
│                                                                  │
│  ✅ Agent decides when to recall or store                        │
│  ✅ Good for agents that need explicit memory management          │
│  ❌ Requires good prompting so LLM uses tools correctly           │
├──────────────────────────────────────────────────────────────────┤
│  PATTERN 3: MCP Tools (Portable, Standardized)                   │
│                                                                  │
│  from adk_redis import create_memory_mcp_toolset                 │
│  memory_tools = create_memory_mcp_toolset(                       │
│      server_url="http://localhost:8088"                          │
│  )                                                               │
│                                                                  │
│  ✅ Standard MCP protocol — works with any MCP-compatible agent  │
│  ✅ Can reuse same memory server across different agent stacks    │
│  ❌ Slightly more overhead vs direct REST                         │
└──────────────────────────────────────────────────────────────────┘
```

Pattern 1 is recommended as the starting point. Add Pattern 2 tools when the agent needs explicit control (e.g., `remember_query_correction`).

> Reference: [Redis ADK Integration Patterns Docs](https://redis.io/docs/latest/integrate/google-adk/integration-patterns/)

---

## 8. Semantic Search Tools via RedisVL

RedisVL provides three search tool types that can be added directly to your agent's `tools` list:

### 8.1 Vector (Semantic) Search

Best for: "find past queries similar to this one", "search schema documentation by meaning"

```python
from redisvl.index import SearchIndex
from redisvl.utils.vectorize import HFTextVectorizer
from adk_redis.tools import RedisVectorSearchTool, RedisVectorQueryConfig

# Local HuggingFace embeddings (fully offline after first download)
vectorizer = HFTextVectorizer(model="sentence-transformers/all-MiniLM-L6-v2")

# Create or connect to an index
index = SearchIndex.from_existing("sql_corrections", redis_url="redis://localhost:6379")

correction_search = RedisVectorSearchTool(
    index=index,
    vectorizer=vectorizer,
    config=RedisVectorQueryConfig(
        vector_field_name="embedding",
        return_fields=["original_query", "corrected_query", "domain"],
        num_results=5,
    ),
    name="search_query_corrections",
    description="Search past SQL query corrections by semantic similarity. "
                "Use before generating adhoc SQL for a table you've worked with before.",
)
```

### 8.2 Full-Text Search

Best for: exact term matching, table names, column names, error codes

```python
from adk_redis.tools import RedisTextSearchTool

schema_search = RedisTextSearchTool(
    index=schema_index,
    name="search_schema_docs",
    description="Search database schema documentation by keyword. "
                "Use to find table names, column names, and field descriptions.",
)
```

### 8.3 Hybrid Search (Recommended for SQL Agents)

Combines semantic similarity with keyword matching — best for mixed queries where you want both "similar meaning" and "exact table/column name" matching:

```python
from adk_redis.tools import RedisHybridSearchTool

hybrid_search = RedisHybridSearchTool(
    index=corrections_index,
    vectorizer=vectorizer,
    name="search_corrections_hybrid",
    description="Search SQL corrections using both semantic similarity and keyword matching. "
                "Provide the table name and query intent.",
)
```

### Available Vectorizers

```python
from redisvl.utils.vectorize import (
    HFTextVectorizer,        # Local HuggingFace — fully offline
    OpenAITextVectorizer,    # OpenAI embeddings
    CohereTextVectorizer,    # Cohere embeddings
    MistralTextVectorizer,   # Mistral embeddings
    GeminiTextVectorizer,    # Gemini text-embedding-004
)

# Fully local (no API key needed after model download)
vectorizer = HFTextVectorizer(model="sentence-transformers/all-MiniLM-L6-v2")
```

> Reference: [Redis ADK Search Tools Docs](https://redis.io/docs/latest/integrate/google-adk/search-tools/)

---

## 9. Semantic Caching

LLM calls are expensive and often repetitive. Semantic caching intercepts calls and returns cached responses when a semantically similar prompt has been answered before.

### Two Cache Providers

| Provider | Embeddings | Requires | Best for |
|---|---|---|---|
| `RedisVLCacheProvider` | Local (HuggingFace etc.) | Redis + vectorizer | On-prem, cost-sensitive |
| `LangCacheProvider` | Server-side | LangCache API key | Managed, simplest setup |

### `RedisVLCacheProvider` (Fully Local)

```python
from adk_redis import RedisVLCacheProvider, RedisVLCacheProviderConfig, LLMResponseCache

cache_provider = RedisVLCacheProvider(
    config=RedisVLCacheProviderConfig(
        redis_url="redis://localhost:6379",
        vectorizer=HFTextVectorizer(model="sentence-transformers/all-MiniLM-L6-v2"),
        similarity_threshold=0.92,  # 0.0–1.0; higher = stricter match
        ttl=3600,                   # seconds; None = no expiry
    )
)

llm_cache = LLMResponseCache(provider=cache_provider)

runner = Runner(
    agent=agent,
    app_name="sql_collection_agent",
    session_service=session_service,
    memory_service=memory_service,
    llm_cache=llm_cache,   # attach to runner
)
```

### What Gets Cached

```
User: "Show me all active debtors in branch JKT-01"
→ LLM generates SQL + response
→ Response cached with embedding of prompt

User (next session): "List active debtors for JKT-01 branch"
→ Semantic similarity = 0.97 > 0.92 threshold
→ Cached response returned immediately (no LLM call)
```

Especially useful for SQL agents where:
- The same report is requested repeatedly with slight rephrasing
- Predefined MCP Toolbox queries get asked the same way by multiple users

> Reference: [Redis ADK Semantic Caching Docs](https://redis.io/docs/latest/integrate/google-adk/semantic-caching/)

---

## 10. Wiring Everything: Full Agent Example

```python
import asyncio
import os
from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.genai import types

from adk_redis.sessions import (
    RedisWorkingMemorySessionService,
    RedisWorkingMemorySessionServiceConfig,
)
from adk_redis.memory import (
    RedisLongTermMemoryService,
    RedisLongTermMemoryServiceConfig,
)
from adk_redis import RedisVLCacheProvider, RedisVLCacheProviderConfig, LLMResponseCache
from redisvl.utils.vectorize import HFTextVectorizer
from google.adk.agents.callback_context import CallbackContext

# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------
REDIS_URL = "redis://localhost:6379"
MEMORY_SERVER_URL = "http://localhost:8088"
APP_NAME = "sql_collection_agent"

# --------------------------------------------------------------------------
# Services
# --------------------------------------------------------------------------
session_service = RedisWorkingMemorySessionService(
    config=RedisWorkingMemorySessionServiceConfig(
        api_base_url=MEMORY_SERVER_URL,
        default_namespace=APP_NAME,
        model_name="gemini-2.0-flash",
        context_window_max=8000,
    )
)

memory_service = RedisLongTermMemoryService(
    config=RedisLongTermMemoryServiceConfig(
        api_base_url=MEMORY_SERVER_URL,
        default_namespace=APP_NAME,
        top_k=5,
        recency_boost=True,
    )
)

# --------------------------------------------------------------------------
# Semantic Cache (fully local)
# --------------------------------------------------------------------------
vectorizer = HFTextVectorizer(model="sentence-transformers/all-MiniLM-L6-v2")

cache_provider = RedisVLCacheProvider(
    config=RedisVLCacheProviderConfig(
        redis_url=REDIS_URL,
        vectorizer=vectorizer,
        similarity_threshold=0.92,
        ttl=3600,
    )
)
llm_cache = LLMResponseCache(provider=cache_provider)

# --------------------------------------------------------------------------
# Callback: commit to long-term memory after each turn
# --------------------------------------------------------------------------
async def commit_memory_callback(callback_context: CallbackContext):
    await callback_context.add_session_to_memory()
    return None

# --------------------------------------------------------------------------
# Agent
# --------------------------------------------------------------------------
agent = Agent(
    model="gemini-2.5-flash",
    name=APP_NAME,
    instruction="""You are a SQL agent connected to a collection activity database.

Active user preferences:
- Response format: {user:pref_response_format}
- Verbosity: {user:pref_verbosity}

MEMORY PROTOCOL:
- Before generating adhoc SQL: use the preloaded memories to check for past corrections.
- When the user corrects a query: call remember_query_correction.
- When the user states a preference: call remember_preference.
""",
    tools=[
        PreloadMemoryTool(),  # auto-injects relevant long-term memories into context
        # ... your MCP Toolbox tools here
    ],
    after_agent_callback=commit_memory_callback,
)

# --------------------------------------------------------------------------
# Runner
# --------------------------------------------------------------------------
runner = Runner(
    agent=agent,
    app_name=APP_NAME,
    session_service=session_service,
    memory_service=memory_service,
    llm_cache=llm_cache,
)

# --------------------------------------------------------------------------
# Run
# --------------------------------------------------------------------------
async def main():
    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id="analyst_001",
    )

    async for event in runner.run_async(
        user_id="analyst_001",
        session_id=session.id,
        new_message=types.Content(
            parts=[types.Part(text="Show active debtors in branch JKT-01")]
        )
    ):
        if event.is_final_response() and event.content:
            print(event.content.parts[0].text)

asyncio.run(main())
```

---

## 11. Monitoring with RedisInsight

RedisInsight (included in the full Docker Compose above) gives you a GUI to inspect everything Redis is storing:

```
http://localhost:5540
```

Connect with:
- Host: `localhost`
- Port: `6379`
- No password (local dev)

What you can inspect:

| Key Pattern | Contains |
|---|---|
| `sql_agent:session:*` | Working memory sessions |
| `sql_agent:memory:*` | Long-term extracted facts (vectors) |
| `llm_cache:*` | Cached LLM responses |
| `tool_cache:*` | Cached tool responses |

You can also run raw commands from the RedisInsight terminal:

```bash
# List all session keys
KEYS sql_agent:session:*

# Inspect a session
JSON.GET sql_agent:session:analyst_001:session_abc123

# Count long-term memories
DBSIZE

# Vector search test (requires FT module)
FT.SEARCH sql_agent:memory:idx "@user_id:{analyst_001}" LIMIT 0 10
```

---

## 12. Local vs Cloud Comparison

| | Fully Local | Hybrid (Redis local + LLM cloud) | Redis Cloud |
|---|---|---|---|
| Redis | Docker (local) | Docker (local) | Redis Cloud managed |
| Agent Memory Server | Docker (local) | Docker (local) | Docker / any host |
| Embeddings | HuggingFace local | HuggingFace local OR Gemini API | Gemini / OpenAI API |
| Fact extraction LLM | ❌ Required cloud | Gemini / OpenAI API | Gemini / OpenAI API |
| Semantic cache | `RedisVLCacheProvider` | `RedisVLCacheProvider` | `LangCacheProvider` |
| Data leaves machine | No (except LLM calls) | No (except LLM calls) | Yes |
| Best for | Dev/air-gapped | Dev + production-like | Production |

**Bottom line:** You can run everything locally with Docker Compose. The only component that requires an external API call is the **fact extraction LLM** in `RedisLongTermMemoryService` (and optionally the embedding model). If you use `HFTextVectorizer` for embeddings, vectors are generated locally.

---

## 13. References

### Official `adk-redis` Resources
- [adk-redis GitHub Repository](https://github.com/redis-developer/adk-redis) — Source code, examples, setup scripts
- [Redis with Google ADK — Official Docs](https://redis.io/docs/latest/integrate/google-adk/) — Architecture, prerequisites, quickstart
- [Redis ADK: Agent Memory Docs](https://redis.io/docs/latest/integrate/google-adk/redis-agent-memory/) — `RedisWorkingMemorySessionService` and `RedisLongTermMemoryService` reference
- [Redis ADK: Integration Patterns Docs](https://redis.io/docs/latest/integrate/google-adk/integration-patterns/) — Framework vs REST vs MCP pattern comparison
- [Redis ADK: Search Tools Docs](https://redis.io/docs/latest/integrate/google-adk/search-tools/) — Vector, text, and hybrid search tool reference
- [Redis ADK: Semantic Caching Docs](https://redis.io/docs/latest/integrate/google-adk/semantic-caching/) — `RedisVLCacheProvider` and `LangCacheProvider` reference
- [Redis ADK Examples](https://redis.io/docs/latest/integrate/google-adk/examples/) — Full working examples

### Blog Posts & Tutorials
- [Build Google ADK Agents with persistent, real-time memory on Redis (Redis Blog)](https://redis.io/blog/build-google-adk-agents-with-persistent-real-time-memory-on-redis/) — Two-tier memory model walkthrough, component overview, cache providers
- [Build an AI agent with persistent memory using Google ADK and Redis (Redis Tutorial)](https://redis.io/tutorials/build-a-car-dealership-agent-with-google-adk-and-redis-agent-memory/) — Car dealership agent tutorial with Docker Compose, end-to-end

### Demo & Reference Implementation
- [google_adk_redis_memory_demo (GitHub)](https://github.com/redis-developer/google_adk_redis_memory_demo) — Full demo with React frontend, ADK backend, Redis Agent Memory, Docker Compose

### Dependencies
- [Redis Agent Memory Server (GitHub)](https://github.com/redis/agent-memory-server) — The REST API server that backs working and long-term memory
- [RedisVL Documentation](https://redis.io/docs/latest/develop/ai/redisvl/) — Vector library powering search tools and local cache provider
- [Redis 8.4 Release Notes](https://redis.io/blog/redis-8-4-release-notes/) — Vector search, JSON, and full-text built-in (no separate module needed)

---

*Last updated: May 2026*
