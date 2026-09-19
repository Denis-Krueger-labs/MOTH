# Current Limitations

This document records known limitations of the current MOTH implementation.

It is intentionally conservative. A limitation being listed here does not mean the system is currently failing. It means the behavior is development-only, intentionally scoped, not yet hardened for a broader deployment model, or not yet tested beyond the stated conditions.

## Frontend Authentication Is Development-Oriented

The current frontend uses the Vite development proxy to inject:

```text
Authorization: Bearer <MOTH_API_TOKEN>
```

This keeps the token out of browser JavaScript during local development.

It is not the final production deployment model.

A production frontend will need an explicit authentication and deployment design rather than relying on Vite dev-server behavior.

## Frontend Uses Polling

The dashboard currently refreshes by polling.

Approximate intervals:

```text
health        2 s
stats         2 s
recent        2 s
connectivity  6 s
```

This is simple and has behaved well during current testing, but it is not real-time push delivery.

Possible future alternatives include:

- Server-Sent Events
- WebSockets
- a dedicated event stream

Polling is currently preferred because it is operationally simple and failure-tolerant.

## Recent Activity Is Intentionally Bounded

The frontend currently requests:

```text
/api/dashboard/recent?limit=20
```

The terminal is therefore an operational snapshot, not a complete event-log viewer.

Historical search, filtering, pagination, and export are not currently implemented in the frontend.

## No Frontend Rate Limiting

The dashboard does not currently enforce its own client-side submission rate limit.

The backend remains responsible for:

- validation
- submission capacity
- duplicate protection
- authorization
- retry behavior

The frontend must not be treated as a security boundary.

## No Multi-User Frontend Session Model

The current dashboard is designed as a small operational control surface.

It does not currently provide:

- named frontend users
- per-user sessions
- frontend roles
- per-user audit views
- collaborative operator presence

Backend authorization is token-based.

## SQLite Is Still the Operational Database

MOTH currently uses SQLite.

Current stress and chaos testing has shown good behavior for the tested single-node development configuration, including concurrent submissions, dashboard reads, retry activity, and upstream outages.

However, the current results do not establish that SQLite is appropriate for every future deployment shape.

Areas that would need separate validation include:

- multiple application processes
- multiple hosts
- distributed workers
- networked storage
- significantly larger long-running datasets

## Submission Capacity Is Process-Local

The current submission capacity limiter is meaningful within the running application process.

A future multi-process deployment would need a shared capacity or coordination mechanism if a global submission limit is required.

Current tests were performed against the existing local development deployment.

## Retry Lease Timing Is Configuration-Sensitive

Retry correctness depends on lease timing being appropriate relative to:

- connection timeout
- response timeout
- scheduler timing
- expected gameserver behavior

Current chaos tests produced:

```text
stale_retry_results = 0
```

That is strong evidence for the current tested configuration, but lease duration should still be reviewed if network timeouts or retry timing are changed substantially.

## Dashboard Reads Can Become Slow Under Heavy Synthetic Load

During mixed stress testing with:

```text
64 concurrent submission workers
16 concurrent dashboard workers
```

dashboard reads remained successful, but latency increased.

Observed dashboard latency:

```text
p50  1065.68 ms
p95  1531.14 ms
p99  1629.27 ms
max  1745.35 ms
```

This test deliberately generated much more dashboard traffic than a single normal browser session.

No dashboard request failures were observed in that run.

## Throughput Drops Under Mixed Workload

Pure submission stress and mixed workload stress produced different throughput.

Observed:

```text
1000 submissions / 64 workers
55.67 req/s
```

versus:

```text
2000 submissions / 64 submission workers
+ 16 dashboard workers
42.04 req/s
```

This is expected contention under additional reads and connectivity probes, but the current implementation has not been optimized for maximum benchmark throughput.

Correctness is currently prioritized over raw request rate.

## No Production Reverse-Proxy Limits Are Documented Yet

A production deployment should explicitly define limits for:

- request body size
- connection count
- request timeout
- upstream timeout
- TLS
- trusted proxy behavior
- logging
- rate limiting

These are not currently part of the local Vite + Uvicorn development stack.

## Service and Source Metadata Need Explicit Production Bounds

The API accepts optional operational metadata such as:

```text
service
source
```

These values should remain bounded and validated appropriately if they become operator-controlled at scale.

The current frontend uses known fixed source values.

## No Long-Duration Soak Test Yet

Current testing has included:

- high concurrency
- thousands of submissions
- duplicate races
- gameserver outage
- retry recovery
- mixed dashboard reads and writes
- upstream failure during active load
- React polling during chaos

A multi-hour or multi-day soak test has not yet been recorded.

Useful future soak-test targets include:

- database growth
- event-table growth
- scheduler drift
- memory growth
- file descriptor stability
- long-term polling behavior
- recovery after repeated outages

## No Formal Browser Matrix Yet

The frontend has been validated in the active local development browser setup.

A formal compatibility matrix has not yet been recorded for:

- Firefox
- Chromium / Chrome
- Edge
- Safari
- mobile browsers

The CSS includes responsive behavior and reduced-motion handling, but a complete browser matrix is still pending.

## Frontend Automated Coverage Is Still Initial

The frontend now has an automated Vitest + React Testing Library suite.

The current suite contains 9 tests across 2 test files and covers:

- initial dashboard state rendering
- manual flag submission
- local rejection of an empty manual offering
- dashboard refresh after submission
- continued polling after the initial load
- gameserver failure rendering without losing unrelated dashboard state
- recent activity rendering
- activity-terminal error rendering
- empty activity-terminal rendering

The frontend has also been exercised manually during live polling, gameserver outage, retry recovery, and submission stress.

Coverage is still intentionally small. Areas not yet formally covered include:

- polling cleanup during component unmount
- stale or out-of-order response handling
- broader API error combinations
- accessibility beyond the currently exercised semantic selectors
- responsive layout behavior
- formal browser compatibility
- long-duration frontend soak behavior

## Security Scope

MOTH is built for authorized CTF use.

It is not intended to be exposed as a public internet submission service without additional deployment hardening.

The current development environment should be treated as a controlled operational environment.