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
    """Redis-backed memory service supporting 5 memory types with different TTLs."""

    def __init__(self, uri: str = "redis://localhost:6379", **kwargs):
        """Initialize Redis connection from URI."""
        self._redis = aioredis.from_url(uri, decode_responses=True)

    async def add_session_to_memory(self, session: Session) -> None:
        """Archive session turns to Redis list (capped at 30 entries)."""
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
        """Store memory entries by type into separate Redis structures."""
        for entry in memories:
            meta = entry.custom_metadata or {}
            entry_type = meta.get("type")
            ts = entry.timestamp or datetime.now().isoformat()
            ttl = 60 * 60 * 24 * 90  # 90-day default TTL

            if entry_type == "query_correction":
                key = f"corrections:{app_name}:{user_id}:{uuid.uuid4()}"
                await self._redis.hset(
                    key,
                    mapping={
                        "original_query": meta.get("original_query", ""),
                        "corrected_query": meta.get("corrected_query", ""),
                        "reason": meta.get("reason", ""),
                        "domain": meta.get("domain", ""),
                        "timestamp": ts,
                    },
                )
                await self._redis.expire(key, ttl)

            elif entry_type == "preference":
                key = f"prefs:{app_name}:{user_id}"
                await self._redis.hset(
                    key, meta.get("category", "misc"), meta.get("value", "")
                )
                # preferences don't expire — they're user identity

            elif entry_type == "schema_discovery":
                table = meta.get("table_name", "unknown")
                key = f"schema_cache:{app_name}:{user_id}:{table}"
                await self._redis.hset(
                    key,
                    mapping={
                        "columns": json.dumps(meta.get("columns", [])),
                        "filter_values": json.dumps(meta.get("filter_values", {})),
                        "last_refreshed": ts,
                    },
                )
                await self._redis.expire(key, 60 * 60 * 24 * 7)  # 7-day TTL (schema changes)

            elif entry_type == "vocabulary":
                term = meta.get("term", "").lower().replace(" ", "_")
                key = f"vocabulary:{app_name}:{user_id}:{term}"
                await self._redis.hset(
                    key,
                    mapping={
                        "definition": meta.get("definition", ""),
                        "context": meta.get("context", ""),
                        "timestamp": ts,
                    },
                )
                await self._redis.expire(key, ttl)

            elif entry_type == "failed_pattern":
                key = f"failed_patterns:{app_name}:{user_id}:{uuid.uuid4()}"
                await self._redis.hset(
                    key,
                    mapping={
                        "wrong_pattern": meta.get("wrong_pattern", ""),
                        "correct_pattern": meta.get("correct_pattern", ""),
                        "error_type": meta.get("error_type", ""),
                        "domain": meta.get("domain", ""),
                        "timestamp": ts,
                    },
                )
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
        #  MemoryEntry(
        #      content=types.Content(parts=[types.Part(text=f"CORRECTION [{data['domain']}]: ...")]),
        #      custom_metadata={"type": "query_correction", **data},
        #      timestamp=data["timestamp"],
        #  )
    #   7. Return SearchMemoryResponse(memories=results[:8])
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
            combined_text = " ".join(
                [
                    data.get("original_query", ""),
                    data.get("corrected_query", ""),
                    data.get("reason", ""),
                ]
            )
            if any(w in combined_text.lower() for w in words):
                entry = MemoryEntry(
                    content=types.Content(
                        parts=[
                            types.Part(
                                text=f"CORRECTION [{data['domain']}]: {data['original_query']} → {data['corrected_query']}. Reason: {data['reason']}"
                            )
                        ]
                    ),
                    custom_metadata={"type": "query_correction", **data},
                    timestamp=data["timestamp"],
                )
                results.append(entry)

        # Sort by timestamp descending (newest first)
        results.sort(
            key=lambda e: e.timestamp or "",
            reverse=True,
        )
        return SearchMemoryResponse(memories=results[:8])
