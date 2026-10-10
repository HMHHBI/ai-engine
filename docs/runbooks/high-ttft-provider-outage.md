# Runbook: High TTFT and LLM Provider Outage

## Trigger
`ChatTTFTHigh`, `ChatSSELatencyHigh`, `ChatStreamFailureRateHigh`, `LLMProviderErrorRateHigh`, or `LLMProviderFailureBudgetBurn`.

## 1. Establish Scope
Check:
- p95 TTFT and SSE duration by time window.
- Chat stream failure rate and request volume.
- Provider error rate by provider: OpenAI, Gemini, and Ollama.
- Recent deployments, API-key/configuration changes, rate limits, and upstream incidents.

## 2. Identify the Failing Layer
- High TTFT with normal provider error rate: investigate provider latency, model load, vector retrieval latency, database waits, and application concurrency.
- High provider error rate: check provider status, credentials, quota/rate limits, timeouts, and network connectivity.
- High SSE duration but normal TTFT: investigate long generations, client disconnects, and stream-duration limits.
- Failures across all providers: investigate shared application, Redis, database, or network dependencies first.

## 3. Mitigate
1. Confirm which configured providers and models are healthy.
2. Switch traffic only to a tested, configured alternative if provider/model switching is supported.
3. Validate API credentials, quotas, and timeout configuration.
4. Reduce avoidable load and pause non-urgent ingestion if it competes for constrained resources.
5. Do not change production provider defaults or secrets without an approved change.

## 4. Verify Recovery
Confirm provider error rates decline, p95 TTFT returns within the service target, and SSE failures normalize. Run a controlled test request before declaring recovery.
