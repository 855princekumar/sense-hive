# 0001: SQLite, one table per topic, WAL mode

- **Status:** Accepted (table per topic since 1.0; WAL mode and retention since 1.1)
- **Date:** 2026-10-13

## Context

SenseHive logs MQTT messages from a handful to a few hundred topics on small
machines (Raspberry Pi, Home Assistant boxes, a VM). It must install in one
step, keep running for months without care, and be backed up by copying a file.
Dashboards read the latest value and the last 50 values of each topic many
times a second while messages keep arriving.

## Decision

- **SQLite**, one file, no separate database server.
- **One table per topic** (`timestamp`, `payload`), named from the topic
  (`/` to `_`, `#` to `wildcard`, `+` to `plus`, `"` doubled). The latest value,
  history, count, export and delete of a topic touch only its own table.
- **WAL mode** (`SQLITE_WAL=true`) with `synchronous=NORMAL`, so readers never
  block the writer; off for network filesystems where WAL is unsafe.
- **Retention** by age and/or count per topic, run by a background job.

## Consequences

- Zero setup and trivially portable: the state is one file (plus `-wal`/`-shm`).
- Table names come from user input, so they are always quoted with quotes
  doubled, and topics with quotes or control characters are refused (see
  [ADR 0003](0003-sign-in-hardening.md) and the SQL tests).
- Cross-topic queries need one query per table; acceptable at this scale.
- Very large fleets (thousands of topics, high rates) would want a server
  database; out of scope for SenseHive.
