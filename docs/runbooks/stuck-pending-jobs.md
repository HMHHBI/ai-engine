# Runbook: Stuck Document Jobs

## Trigger
`DocumentQueueLagHigh`, `DocumentWorkerStalled`, or prolonged jobs stuck in processing.

## 1. Check Queue and Consumer-Group State

```bash
redis-cli -u "$REDIS_URL" XLEN ai:document:jobs
redis-cli -u "$REDIS_URL" XINFO GROUPS ai:document:jobs
redis-cli -u "$REDIS_URL" XPENDING ai:document:jobs document-workers
redis-cli -u "$REDIS_URL" XPENDING ai:document:jobs document-workers - + 20
```

## 2. Check Worker Health
Review worker logs, container health, restarts, database connectivity, embedding provider errors, and recent deployments. Confirm whether pending messages belong to a live worker or a stale consumer.

## 3. Check Durable Job State
Inspect the corresponding DocumentJob status, attempt count, max_attempts, heartbeat, and error fields in the database.

## 4. Recover
Prefer the existing DocumentJobRecoveryService and worker recovery daemon. If a worker is unhealthy, restart it using standard deployment procedures, then verify that pending messages are reclaimed and job heartbeats resume.

Do not use `XDEL`, `XTRIM`, or `FLUSHDB` to force the backlog to zero.

## 5. Escalate
If pending messages remain idle beyond the recovery threshold, or attempts are exhausted, inspect the DLQ and follow `docs/runbooks/ingestion-dlq.md`.
