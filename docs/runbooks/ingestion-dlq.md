# Runbook: Document Ingestion DLQ

## Trigger
`DocumentDLQNotEmpty`, `DocumentDLQBacklogCritical`, or repeated document ingestion failures.

## 1. Inspect the Backlog
Run Redis commands from an environment with access to the configured Redis instance.

```bash
redis-cli -u "$REDIS_URL" XLEN ingestion:dlq
redis-cli -u "$REDIS_URL" XRANGE ingestion:dlq - + COUNT 20
```

Inspect `job_id`, `original_message_id`, `attempt`, `max_attempts`, `error_message`, and `forwarded_at`. Treat tracebacks and payloads as potentially sensitive.

## 2. Inspect the Underlying Job
Check application logs for the job ID and error. Verify database connectivity, provider availability, document ownership, and storage access before replaying. Do not redrive a large backlog while the underlying failure is still active.

## 3. Redrive One Message
Use the exact Redis Stream message ID returned by `XRANGE`.

```bash
cd backend
python -m app.scripts.dlq_admin redrive "<DLQ_MESSAGE_ID>"
```

Confirm that the command reports a new active queue message ID. Verify that the job progresses and the DLQ count decreases.

## 4. Drain Carefully
Redrive one message at a time. After each small batch, inspect DLQ depth, worker logs, ingestion failures, and database job statuses. Pause if errors repeat or queue lag rises.

## 5. Discard Only When Approved
Discard permanently invalid or explicitly abandoned messages only after confirming the associated job and document state.

```bash
cd backend
python -m app.scripts.dlq_admin discard "<DLQ_MESSAGE_ID>"
```

Record the message ID, reason, operator, and incident reference.

## Safety Notes
- Do not flush Redis or delete the entire stream to clear an alert.
- Preserve the DLQ entry until a redrive or discard decision has been made.
- Use `XRANGE` for inspection.
