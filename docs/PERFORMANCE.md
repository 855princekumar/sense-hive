# Performance and resource use

SenseHive is built to run next to other services on small machines: one
container, one SQLite file, no separate database server. These numbers are
**measured**, not estimated, with the script in `tools/measure/` so you can
repeat them on your own hardware.

## At a glance

SenseHive 1.8.1, measured 2026-10-20 (the [1.4.2 measurement](#earlier-measurement-142) is kept
below for comparison).

| | Measured |
| --- | --- |
| Docker image | **55 MB** (amd64 and arm64) |
| Memory, idle (heartbeat receiver on) | **34.5 MB** |
| Memory, 500 heartbeat nodes + 100 busy topics | **37.4 MB** |
| CPU, idle | **0.03 %** of one core |
| CPU, 500 heartbeat nodes (50 verified messages/s) | **10.2 %** of one core |
| CPU, 500 nodes + 100 topics at 50 messages/s | **26.6 %** of one core |
| API response, 500 nodes and 100 topics | **4 to 16 ms** (p50), under **20 ms** (p95) |
| Heartbeats refused during the run | **0** (all 500 nodes online) |

Figures are medians of 5-second `docker stats` samples within each phase. Compared with 1.4.2,
1.8 keeps more per message (secure topics, more state for the heartbeat history and the
recycle bin): about 6 MB more memory and a little more CPU, still under 40 MB.

## Scenarios

The run uses SenseHive 1.8.1 from Docker Hub, a local Mosquitto 1.6 broker for
both the data and the heartbeats (TLS off, so the numbers show SenseHive, not
the encryption of the broker connection), and a load generator in its own
container. Each phase lasts 120 seconds; `docker stats` samples SenseHive every
5 seconds. CPU is the share of one core.

| Phase | Traffic | CPU (average) | Memory |
| ----- | ------- | ------------- | ------ |
| Idle | receiver connected, 100 topics subscribed, no messages | 0.03 % | 34.5 MB |
| Heartbeats | 500 nodes, each a birth then an encrypted `hb` every 10 s: 50 messages/s decrypted, verified and tracked | 10.2 % | 36.0 MB |
| Heartbeats and data | the above plus 50 JSON messages/s spread over 100 topics, each stored and pushed to open dashboards | 26.6 % | 37.4 MB |

Memory stays flat during a phase: state per heartbeat node is a few hundred
bytes, and messages are written to SQLite, not kept in memory.

## API response times

Measured right after the load, 20 requests each, with 500 heartbeat nodes,
100 topics and 5,867 stored entries:

| Endpoint | p50 | p95 |
| -------- | --- | --- |
| `GET /api/heartbeat/status` | 4.3 ms | 4.8 ms |
| `GET /api/heartbeat/nodes` (500 nodes) | 10.0 ms | 11.8 ms |
| `GET /api/heartbeat/minutes` (2,500 node-minutes) | 9.7 ms | 13.7 ms |
| `GET /api/stats` | 9.6 ms | 11.3 ms |
| `GET /api/nodes` (100 topics with latest values) | 15.7 ms | 19.8 ms |

## Storage

After the run the database was 2.16 MB: 5,867 data entries plus four minutes
of heartbeat state, per-minute presence and events for 500 nodes. That is at
most **about 370 bytes per stored message** including indexes (the payloads
were small JSON objects with four sensor values). Use **Retention** (by age or
entries per topic) to cap growth; heartbeat presence is pruned after
`HEARTBEAT_KEEP_DAYS` (30) by itself.

## What it means for sizing

These are estimates from the measured rates, not separate measurements:

- CPU grows roughly in line with messages per second: about **0.2 % of a
  core per verified heartbeat per second** and **0.33 % per logged message per
  second** on this machine. 1,000 nodes at the default 10-second interval are
  100 messages/s, about a fifth of one core.
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
TAG=1.8.1 PHASE=120 bash tools/measure/run.sh
```

Needs Docker and `openssl`. It starts a broker, SenseHive and the load
generator on a private Docker network with throwaway keys and password, prints
`STAT` lines (CPU and memory every 5 seconds), the phase times, API timings and
the database size, then removes everything. `NODES`, `TOPICS` and `RATE` in
`tools/measure/load.py` change the load.

## Earlier measurement (1.4.2)

The same script and machine, SenseHive 1.4.2:

| Phase | CPU (average) | Memory |
| ----- | ------------- | ------ |
| Idle | 0.04 % | 28 MB |
| Heartbeats (500 nodes) | 8.7 % | 34 MB |
| Heartbeats and data (plus 100 topics) | 19 % | 35 MB |

API p50 2 to 8 ms, p95 under 10 ms; image 57 MB.
