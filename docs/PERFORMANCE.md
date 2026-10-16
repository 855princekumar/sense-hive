# Performance and resource use

SenseHive is built to run next to other services on small machines: one
container, one SQLite file, no separate database server. These numbers are
**measured**, not estimated, with the script in `tools/measure/` so you can
repeat them on your own hardware.

## At a glance

| | Measured |
| --- | --- |
| Docker image | **57 MB** (amd64 and arm64) |
| Memory, idle (heartbeat receiver on) | **28 MB** |
| Memory, 500 heartbeat nodes + 100 busy topics | **35 MB** |
| CPU, idle | **0.04 %** of one core |
| CPU, 500 heartbeat nodes (50 verified messages/s) | **8.7 %** of one core |
| CPU, 500 nodes + 100 topics at 50 messages/s | **19 %** of one core |
| API response, 500 nodes and 100 topics | **2 to 8 ms** (p50), under **10 ms** (p95) |
| Heartbeats refused during the run | **0** (all 500 nodes online) |

## Scenarios

The run uses SenseHive 1.4.2 from Docker Hub, a local Mosquitto 1.6 broker for
both the data and the heartbeats (TLS off, so the numbers show SenseHive, not
the encryption of the broker connection), and a load generator in its own
container. Each phase lasts 120 seconds; `docker stats` samples SenseHive every
5 seconds. CPU is the share of one core.

| Phase | Traffic | CPU (average) | Memory |
| ----- | ------- | ------------- | ------ |
| Idle | receiver connected, 100 topics subscribed, no messages | 0.04 % | 28 MB |
| Heartbeats | 500 nodes, each a birth then an encrypted `hb` every 10 s: 50 messages/s decrypted, verified and tracked | 8.7 % | 34 MB |
| Heartbeats and data | the above plus 50 JSON messages/s spread over 100 topics, each stored and pushed to open dashboards | 19 % | 35 MB |

Memory stays flat during a phase: state per heartbeat node is a few hundred
bytes, and messages are written to SQLite, not kept in memory.

## API response times

Measured right after the load, 20 requests each, with 500 heartbeat nodes,
100 topics and 5,869 stored entries:

| Endpoint | p50 | p95 |
| -------- | --- | --- |
| `GET /api/heartbeat/status` | 1.8 ms | 2.3 ms |
| `GET /api/heartbeat/nodes` (500 nodes) | 4.7 ms | 5.2 ms |
| `GET /api/heartbeat/minutes` (2,500 node-minutes) | 4.7 ms | 5.7 ms |
| `GET /api/stats` | 4.2 ms | 4.7 ms |
| `GET /api/nodes` (100 topics with latest values) | 7.4 ms | 8.2 ms |

## Storage

After the run the database was 1.57 MB: 5,869 data entries plus four minutes
of heartbeat state, per-minute presence and events for 500 nodes. That is at
most **about 270 bytes per stored message** including indexes (the payloads
were small JSON objects with four sensor values). Use **Retention** (by age or
entries per topic) to cap growth; heartbeat presence is pruned after
`HEARTBEAT_KEEP_DAYS` (30) by itself.

## What it means for sizing

These are estimates from the measured rates, not separate measurements:

- CPU grows roughly in line with messages per second: about **0.17 % of a
  core per verified heartbeat per second** and **0.2 % per logged message per
  second** on this machine. 1,000 nodes at the default 10-second interval are
  100 messages/s, under a fifth of one core.
- A Raspberry Pi 4 or 5 core is slower than this laptop core; expect a few
  times the CPU share there. Hundreds of nodes still fit in a fraction of one
  core.
- Memory is dominated by Python and its libraries, not by the fleet: plan
  **64 MB** for the container.
- Heartbeats are spread out by design (each node keeps its own 10-second rhythm),
  so there are no bursts to size for.

## Test machine

Intel Core i7-1185G7 (laptop, 8 threads), Docker Desktop on Windows 11 with
8 CPUs and 8 GB for containers. Numbers on servers and single-board computers
will differ; the script prints the same table for any machine.

## Run it yourself

```bash
TAG=1.4.2 PHASE=120 bash tools/measure/run.sh
```

Needs Docker and `openssl`. It starts a broker, SenseHive and the load
generator on a private Docker network with throwaway keys and password, prints
`STAT` lines (CPU and memory every 5 seconds), the phase times, API timings and
the database size, then removes everything. `NODES`, `TOPICS` and `RATE` in
`tools/measure/load.py` change the load.
