from datetime import datetime

from google.adk.memory.memory_entry import MemoryEntry
from google.adk.tools.tool_context import ToolContext
from google.genai import types


async def remember_query_correction(
    original_query: str,
    corrected_query: str,
    correction_reason: str,
    table_or_domain: str,
    tool_context: ToolContext,
) -> dict:
    """Store a SQL query correction. Call when the user explicitly corrects generated SQL."""
    entry = MemoryEntry(
        content=types.Content(
            parts=[
                types.Part(
                    text=f"CORRECTION [{table_or_domain}]: {original_query} → {corrected_query}. Reason: {correction_reason}"
                )
            ]
        ),
        custom_metadata={
            "type": "query_correction",
            "domain": table_or_domain,
            "original_query": original_query,
            "corrected_query": corrected_query,
            "reason": correction_reason,
        },
        timestamp=datetime.now().isoformat(),
    )
    await tool_context.add_memory(memories=[entry])
    return {"status": "correction_saved", "domain": table_or_domain}


async def remember_preference(
    preference_category: str,
    preference_value: str,
    tool_context: ToolContext,
) -> dict:
    """Store a user preference (format, verbosity, language). Persists across all sessions."""
    tool_context.state[f"user:pref_{preference_category}"] = preference_value
    entry = MemoryEntry(
        content=types.Content(
            parts=[
                types.Part(
                    text=f"PREFERENCE [{preference_category}]: {preference_value}"
                )
            ]
        ),
        custom_metadata={
            "type": "preference",
            "category": preference_category,
            "value": preference_value,
        },
        timestamp=datetime.now().isoformat(),
    )
    await tool_context.add_memory(memories=[entry])
    return {"status": "preference_saved", "category": preference_category}


async def remember_schema_discovery(
    table_name: str,
    columns: list[str],
    filter_values: dict,
    tool_context: ToolContext,
) -> dict:
    """Cache a table's column list and valid filter values. Call after tool_list_tables or tool_schema_filter_values succeeds."""
    entry = MemoryEntry(
        content=types.Content(
            parts=[types.Part(text=f"SCHEMA [{table_name}]: columns={columns}")]
        ),
        custom_metadata={
            "type": "schema_discovery",
            "table_name": table_name,
            "columns": columns,
            "filter_values": filter_values,
        },
        timestamp=datetime.now().isoformat(),
    )
    await tool_context.add_memory(memories=[entry])
    return {"status": "schema_cached", "table": table_name}


async def remember_term(
    term: str,
    definition: str,
    context: str,
    tool_context: ToolContext,
) -> dict:
    """Remember a business/domain term the user has defined. Call when user explains a term or acronym."""
    entry = MemoryEntry(
        content=types.Content(
            parts=[
                types.Part(
                    text=f"VOCABULARY [{term}]: {definition}. Context: {context}"
                )
            ]
        ),
        custom_metadata={
            "type": "vocabulary",
            "term": term,
            "definition": definition,
            "context": context,
        },
        timestamp=datetime.now().isoformat(),
    )
    await tool_context.add_memory(memories=[entry])
    return {"status": "term_saved", "term": term}


async def remember_failed_pattern(
    wrong_pattern: str,
    correct_pattern: str,
    error_type: str,
    domain: str,
    tool_context: ToolContext,
) -> dict:
    """Record a SQL error pattern and its fix. Call after successfully recovering from a query error."""
    entry = MemoryEntry(
        content=types.Content(
            parts=[
                types.Part(
                    text=f"FAILED_PATTERN [{domain}] error={error_type}: {wrong_pattern} → {correct_pattern}"
                )
            ]
        ),
        custom_metadata={
            "type": "failed_pattern",
            "domain": domain,
            "error_type": error_type,
            "wrong_pattern": wrong_pattern,
            "correct_pattern": correct_pattern,
        },
        timestamp=datetime.now().isoformat(),
    )
    await tool_context.add_memory(memories=[entry])
    return {"status": "pattern_saved", "error_type": error_type}


async def recall_corrections(query_context: str, tool_context: ToolContext) -> dict:
    """Recall past SQL corrections relevant to a domain. Call before generating adhoc SQL."""
    response = await tool_context.search_memory(query_context)
    items = [
        {
            "text": (
                e.content.parts[0].text
                if e.content and e.content.parts
                else ""
            ),
            "metadata": e.custom_metadata or {},
        }
        for e in (response.memories or [])
        if (e.custom_metadata or {}).get("type") == "query_correction"
    ]
    return {
        "past_corrections": items,
        "hint": "Apply these when constructing SQL."
        if items
        else "No prior corrections found.",
    }
