# Semantic Query Memory System (Improved)

Current problem: String-based corrections don't match new queries.
- User saves: `WHERE status = 'aktif'` → correct: `collection_status = 'ACTIVE'`
- Next query asks about "kolektor status" 
- Agent doesn't recognize the pattern → asks again ❌

Solution: **Semantic memory** with extracted context, not raw SQL.

---

## Improved Memory Structure

Instead of:
```python
{
    "original_query": "SELECT ... WHERE status = 'aktif'",
    "corrected_query": "SELECT ... WHERE collection_status = 'ACTIVE'",
    "reason": "column name is collection_status",
    "domain": "visits"
}
```

Store:
```python
{
    # What was wrong (semantic, not string)
    "issue": {
        "type": "column_name_error",
        "incorrect_column": "status",
        "correct_column": "collection_status",
        "table": "visits",
        "affected_tables": ["visits"],
    },
    
    # What was fixed
    "correction": {
        "pattern": "replace WHERE column with correct column name",
        "mapping": {
            "visits.status": "visits.collection_status"
        },
        "value_mapping": {
            "aktif": "ACTIVE",  # if applicable
        }
    },
    
    # Business context
    "business_context": {
        "domain": "visit_analysis",
        "concept": "visit_status",
        "description": "Whether a field visit occurred (ACTIVE/COMPLETED/CANCELLED)",
        "related_concepts": ["collector_active", "visit_outcome"],
    },
    
    # Query structure (parsed)
    "query_structure": {
        "type": "SELECT",
        "tables_involved": ["visits"],
        "joins": [],
        "where_conditions": ["status = 'aktif'"],
        "aggregations": [],
    },
    
    # Metadata
    "severity": "high",  # high = critical error, medium = optimization, low = style
    "applicability": "any_visits_query",  # when to apply this
    "timestamp": "2026-05-15T10:30:00Z",
}
```

---

## Semantic Memory Functions

### `extract_query_semantics(sql_text)`
Parse SQL to extract meaning:
```python
{
    "tables": ["visits", "collectors"],
    "columns_referenced": ["visit_date", "status", "payment"],
    "aggregations": ["COUNT", "SUM"],
    "joins": [("visits.collector_id", "collectors.collector_id")],
    "filters": [{"column": "status", "operator": "=", "value": "aktif"}],
    "groupby": ["collector_id"],
}
```

### `remember_semantic_correction(issue_type, incorrect_field, correct_field, table, business_context, ...)`
Store structured correction:
```python
await remember_semantic_correction(
    issue_type="column_name_mismatch",
    table="visits",
    incorrect_column="status",
    correct_column="collection_status",
    value_mapping={"aktif": "ACTIVE"},
    business_concept="visit_status",
    description="Field visit status (ACTIVE/COMPLETED/CANCELLED)",
    severity="high",
    applies_to="any_query_filtering_visits_by_status",
    tool_context=tool_context,
)
```

### `find_semantic_match(user_query, semantic_corrections)`
Match new query against stored corrections by **intent**, not text:
```python
# User asks: "Berapa kunjungan aktif per kolektor?"
# Agent extracts: {tables: [visits], filters: [{column: status}], ...}
#
# Searches corrections:
# - Any correction affecting "visits" table? YES
# - Any correction affecting "status" column filtering? YES
# - Does user seem to filter by visit status? YES
# 
# Returns: 1 matching correction with 95% confidence

matches = await find_semantic_match(
    extracted_query_semantics={...},
    domain="visit_analysis",
    min_confidence=0.8,
)
# Returns: [
#     {
#         "correction": {...},
#         "confidence": 0.95,
#         "reason": "Query filters visits by status → apply status column mapping"
#     }
# ]
```

---

## Storage Format (Redis)

### Before (String-based)
```
corrections:collection_analysis_agent:user_123:uuid → HASH
  original_query: "SELECT ... WHERE status = 'aktif'"
  corrected_query: "SELECT ... WHERE collection_status = 'ACTIVE'"
```

### After (Semantic)
```
semantic_corrections:collection_analysis_agent:user_123:visit_status → HASH
  issue_type: "column_name_mismatch"
  table: "visits"
  incorrect_column: "status"
  correct_column: "collection_status"
  value_mapping: '{"aktif": "ACTIVE"}'
  business_concept: "visit_status"
  description: "Field visit status..."
  severity: "high"
  applies_to: "any_visits_status_filter"

semantic_corrections:collection_analysis_agent:user_123:aggregation_pattern → HASH
  issue_type: "missing_groupby"
  table: "visits"
  pattern: "collector_visits_analysis requires GROUP BY collector"
  missing_groupby: "collector_id"
  suggested_aggregations: '["COUNT(*)", "SUM(payment)"]'
  applies_to: "collector_performance_queries"
```

---

## Recall Flow (Improved)

```
User: "Berapa kunjungan aktif per kolektor?"
         ↓
Agent extracts semantics:
  - tables: [visits]
  - filter on: status column
  - groupby requested: collector
         ↓
Agent calls: find_semantic_match(semantics, domain="visit_analysis")
         ↓
Redis searches semantic_corrections:*:visit_status, *:aggregation_pattern
  - Found: visit_status correction (95% match)
  - Found: aggregation_pattern correction (90% match)
         ↓
Agent applies corrections:
  1. Replace status → collection_status (from visit_status correction)
  2. Add GROUP BY collector (from aggregation_pattern correction)
         ↓
Generates corrected SQL:
  SELECT collector_name, COUNT(*) FROM visits 
  WHERE collection_status = 'ACTIVE' 
  GROUP BY collector_id, collector_name
```

---

## Implementation Phases

### Phase 1: Semantic Extraction (Week 1)
- [ ] Build `extract_query_semantics(sql)` → parses SQL to JSON structure
- [ ] Test on 10 real queries from the codebase
- [ ] Verify column/table extraction accuracy

### Phase 2: Structured Memory (Week 2)
- [ ] Replace `remember_query_correction()` with `remember_semantic_correction()`
- [ ] Build `find_semantic_match()` with configurable confidence threshold
- [ ] Test matching: does it find relevant corrections?

### Phase 3: Vector Memory (Optional, Week 3+)
- [ ] Add embedding-based semantic search (e.g., OpenAI embeddings)
- [ ] Store correction embeddings in Pinecone/Weaviate
- [ ] Match by cosine similarity + business context
- [ ] Handle paraphrased queries ("collector earnings" ≈ "collection amounts")

---

## Example: Two-Level Query Memory

**User saves (Session 1, Q3):**
```
"Saya butuh dua level - ringkasan per kolektor + detail visits"
```

**Extracted semantic context:**
```python
{
    "issue_type": "missing_summary_layer",
    "tables": ["visits", "collectors"],
    "problem": "User wants aggregated + detailed view, but query was listing individual rows",
    "solution_pattern": "CTE with GROUP BY for summary, then LEFT JOIN for details",
    "required_aggregations": ["COUNT(*)", "SUM(payment)", "COUNT(CASE...)"],
    "groupby_fields": ["collector_id", "collector_name"],
    "detail_join": "LEFT JOIN visits on collector_id",
    "business_concept": "collector_performance_with_detail",
    "applies_to": "any_collector_analysis_query",
}
```

**Session 2, user asks:** "Ranking kolektor minggu ini plus detail mereka?"

**Extraction:**
```python
{
    "tables": ["visits", "collectors"],
    "requested_ranking": True,
    "requested_detail": True,  # implied by "plus detail mereka"
    "timeframe": "minggu ini",
}
```

**Semantic match:**
- ✓ Same tables
- ✓ Both want ranking (aggregation) + detail
- ✓ Business concept matches: "collector_performance_with_detail"
- **Confidence: 92%** → Apply stored CTE pattern ✓

---

## Benefits

| Current | Semantic Memory |
|---------|-----------------|
| Matches: exact strings | Matches: intent + context |
| "status" ≠ "visit_status" | Both refer to same concept ✓ |
| User must phrase identically | Paraphrased queries work |
| High false negatives | Higher recall rate |
| No business context | Understands domain relationships |
| Single correction type | Multiple patterns (columns, aggregations, joins) |

---

## Next Steps

1. **Try Phase 1** — build `extract_query_semantics()` and test it
2. **Redesign memory schema** — from raw SQL to semantic structure
3. **Implement `find_semantic_match()`** — confidence-based matching
4. **Test on real scenarios** — see if two-level query pattern is recalled
