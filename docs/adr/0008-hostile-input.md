# 0008: Treat every input as hostile

- **Status:** Accepted (1.5)
- **Date:** 2026-10-16

## Context

SenseHive listens to brokers anyone may publish to (a public data broker, the
public heartbeat broker), serves an API that tools call with a token, and
writes files people open in spreadsheets. A strict review in 1.5 asked what a
hostile publisher, a rogue or compromised node agent, a bot hammering the API,
or a booby-trapped value could do. It found nothing that runs code, but several
ways to exhaust resources or mislead an operator.

## Decision

| Threat | Answer |
| ------ | ------ |
| A publisher fills the disk with huge messages | Messages over `MQTT_MAX_PAYLOAD_BYTES` (64 KB) are dropped and counted |
| Deeply nested JSON overflows the parser | Kept as text instead of crashing the handler |
| A stolen node key floods heartbeats (they are authentic) | Heartbeats from one node closer than `HEARTBEAT_MIN_SPACING` (2 s) are dropped and counted (`flooded`) |
| Guessing the API token | 20 wrong tokens from one address in 15 minutes lock that address out; the failure table is bounded |
| Forged log lines through topic names or payloads | Line breaks and control characters removed, length capped |
| Spreadsheet formulas in CSV exports (payloads, node names) | Cells starting with `=`, `+`, `-`, `@`, tab or CR escaped; numbers kept |
| Huge request bodies | Refused over 1 MB |
| Many open live streams exhausting threads | Capped by `SENSEHIVE_MAX_STREAMS` (50) |
| `nan`/`inf` in query numbers | Rejected, defaults used |
| Version fingerprinting | Version in `/api/health` only for signed-in users and token holders |
| Browser features and cross-origin tricks | `Permissions-Policy`, `Cross-Origin-Opener-Policy`, `Cross-Origin-Resource-Policy` added to the existing CSP and headers |
| The session secret file | Created readable by its owner only |
| Supply chain of the CI | GitHub Actions pinned to commit SHAs (a moved tag cannot change what runs) |

Each item has a regression test (`tests/test_security.py`,
`tests/test_heartbeat_history.py`).

## Consequences

- A hostile publisher or node can cost a little CPU, but cannot fill the disk,
  crash the logger, flood the history or plant formulas in exports.
- Payloads over 64 KB need `MQTT_MAX_PAYLOAD_BYTES` raised on purpose.
- Updating a pinned action is a reviewed change (Dependabot proposes it).
