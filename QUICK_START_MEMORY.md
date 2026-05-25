# Quick Start: Testing Memory System

Step-by-step guide to test the correction feedback loop in 5 minutes.

## Setup (2 min)

```bash
# 1. Ensure Redis + Toolbox are running
docker ps --filter "name=adk_" --format "table {{.Names}}\t{{.Status}}"
# Expected output:
#   NAMES       STATUS
#   adk_redis   Up ... (healthy)
#   adk_toolbox Up ...

# 2. Start agent with persistence flags
cd /home/ubuntu/workspace/adk-sql-agent
uv run adk web \
  --session_service_uri="sqlite:///./sessions.db" \
  --memory_service_uri="redis://localhost:6379" \
  .

# 3. Open browser
#    http://127.0.0.1:8000
```

## Test Sequence (3 min)

### Step 1: Trigger a Correction (Same Session)

In the web UI chat:

```
Q: Tampilkan data kunjungan dengan status = 'aktif'
   (Show visits with status = 'aktif')
```

Agent generates SQL with `status = 'aktif'` (likely wrong for this data).

```
Q: Salah! Harusnya pakai collection_status = 'ACTIVE'
   (Wrong! Should use collection_status = 'ACTIVE')
```

Watch the logs in terminal:
```
[Agent] temp:correction_detected = True
[Agent] Calling: remember_query_correction
[Redis] HSET corrections:collection_analysis_agent:{user_id}:...
```

Agent confirms: "Baik, saya sudah menyimpan koreksi ini."

### Step 2: New Session (Same Browser Tab)

**Refresh the page** (Ctrl+R or Cmd+R)

This creates a new session while keeping Redis corrections alive.

### Step 3: Test Recall

```
Q: Tampilin kunjungan status aktif
   (Show visits with status aktif)
```

Watch logs for:
```
[Agent] Calling: recall_corrections(query_context="visits")
[Redis] SCAN corrections:collection_analysis_agent:{user_id}:*
[Agent] Found 1 past correction
[Agent] Applying: collection_status = 'ACTIVE' (not status = 'aktif')
```

**Expected result**: Corrected SQL runs immediately, no trial-and-error ✓

---

## Verify Redis Storage (30 sec)

**In a new terminal**:

```bash
# Check correction was stored
docker exec adk_redis redis-cli
> KEYS "corrections:*"
corrections:collection_analysis_agent:USER_ID:abc123...

> HGETALL corrections:collection_analysis_agent:USER_ID:abc123...
1) "original_query"
2) "SELECT ... WHERE status = 'aktif'"
3) "corrected_query"
4) "SELECT ... WHERE collection_status = 'ACTIVE'"
5) "reason"
6) "Column name is collection_status. Values must be uppercase."
7) "domain"
8) "visits"
9) "timestamp"
10) "2026-05-15T10:30:45.123456"

> QUIT
```

---

## Alternative: Clean Test (Start Fresh)

If you want to test with a completely clean Redis:

```bash
# Flush Redis (WARNING: deletes ALL data)
docker exec adk_redis redis-cli FLUSHALL

# Follow test sequence above
```

---

## Troubleshooting

### "Address already in use" on port 8000

Another ADK instance is running. Kill it:

```bash
# Find process
lsof -i :8000

# Kill it (replace PID)
kill -9 PID
```

### Correction not recalled in new session

Check logs for:
- `recall_corrections` being called?
- Matching domain name between `remember_query_correction` and `recall_corrections`?

Example mismatch:
```python
# Stored with domain="visits"
remember_query_correction(..., table_or_domain="visits", ...)

# Recalled with domain="visit_activity" (different)
recall_corrections(query_context="visit_activity", ...)
# ✗ Won't match
```

### Redis shows no keys

1. Check Redis is healthy: `docker logs adk_redis`
2. Check correction signal was detected: Look for `temp:correction_detected = True` in terminal logs
3. Verify memory tool was called: Search logs for `remember_query_correction`

---

## What to Expect

### Session 1 (Correction Phase)
```
User:  Tampilkan kunjungan dengan status = 'aktif'
Agent: [Generates SQL with status = 'aktif']
       [Runs query, shows results]

User:  Salah! Harusnya collection_status = 'ACTIVE'
Agent: [Detects CORRECTION SIGNAL]
       [Calls remember_query_correction]
       [Shows corrected query with correct results]
       ✓ Correction stored in Redis
```

### Session 2 (Recall Phase)
```
User:  Tampilin kunjungan status aktif
Agent: [Calls recall_corrections]
       [Finds 1 past correction: status → collection_status]
       [Applies fix: collection_status = 'ACTIVE']
       [Generates SQL with correction applied]
       [Shows correct results on FIRST TRY]
       ✓ No trial-and-error needed
```

---

## Next Steps

- [ ] Run the test sequence above
- [ ] Verify logs show `recall_corrections` being called in Session 2
- [ ] Check Redis keys: `docker exec adk_redis redis-cli KEYS "*"`
- [ ] Read `TEST_MEMORY_EXAMPLES.md` for more complex scenarios
- [ ] Extend to `collection_skill_agent` and `collection_script_agent` (same imports + callback)

