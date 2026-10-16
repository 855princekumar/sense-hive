# 0002: Encrypted heartbeat receiver on a public broker

- **Status:** Accepted (1.2)
- **Date:** 2026-10-15

## Context

EdgeShell needs to know whether each edge node is up even when its VPN path is
down, and for how long it has been up (uptime, SLA). Nodes sit behind NAT and
mobile networks; a public MQTT broker is reachable from all of them, but anyone
can read and write on it.

## Decision

- A small agent on each node publishes a heartbeat every 10 s and sets an MQTT
  **last will**. SenseHive receives them; EdgeShell reads SenseHive's read-only
  API.
- Every message is **AES-256-GCM** sealed with a per-node key derived from a
  fleet master key (HMAC); the header and topic are authenticated data.
- **Topics rotate every 10 minutes**, derived from the master key, so the fleet
  cannot be found or followed on the broker.
- The tracker refuses replays (counter and session), clock skew over 120 s and
  unknown nodes, and counts what it refuses.
- States: `online`, `offline` (last will), `silent` (neither). Events and
  per-minute presence are stored for uptime.
- **Off by default**: nothing changes unless `HEARTBEAT_MASTER_KEY` is set.
- One protocol file shared by agent, SenseHive and EdgeShell, pinned by the
  same test vectors in all three.

## Consequences

- Node status independent of the VPN, with no inbound port on nodes.
- Nothing about a node (names, addresses, credentials, data) is readable on the
  broker; a stolen node key exposes only that node.
- Depends on a broker being reachable; `silent` makes that visible instead of
  marking nodes offline.
- The master key is the root secret: kept only in SenseHive's and EdgeShell's
  environment, never on nodes.
