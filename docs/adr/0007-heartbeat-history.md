# 0007: Heartbeat history, charts and CSV export

- **Status:** Accepted (1.5)
- **Date:** 2026-10-16

## Context

Up to 1.4 SenseHive kept, per node, the current state, the minutes in which a
heartbeat arrived (30 days) and every change of state. That is enough for uptime
figures, but not to answer "what happened in the last minute", "how regular are
this node's heartbeats" or "when exactly was the break", and nothing of it was
visible or exportable in the UI.

## Decision

- Keep **every verified heartbeat** in `hb_beats` (node as the `hb_nodes` rowid,
  receive time, kind, delivery delay), a `WITHOUT ROWID` table keyed by
  `(node, t)`: about 0.35 MB per node per day (measured). Kept for
  `HEARTBEAT_BEATS_HOURS` (48 by default, 0 turns it off); the per-minute
  presence and events stay for `HEARTBEAT_KEEP_DAYS` (30).
- `hb_nodes` is written with an UPSERT (not `INSERT OR REPLACE`) so a node's
  rowid never changes and its beats stay attached.
- **Charts**: 1 minute, 1 hour and 1 day from every heartbeat (seconds between
  heartbeats, breaks, last wills); 7 and 30 days from online minutes (uptime per
  hour). A **break** is a gap over 2.5 times the node's usual interval (and at
  least 5 seconds over it), so each node is judged by its own rhythm.
- **CSV export** for one node, selected nodes or all: every heartbeat, online
  minutes or status changes, through `GET /api/heartbeat/export.csv`, with the
  same token or session as the rest of the read API.
- The heartbeats page becomes a **view of the dashboard**, chosen with a card
  next to "Topic logs"; `/heartbeats` redirects to `?view=heartbeats`.
- Charts are plain SVG drawn by SenseHive's own code: no chart library, nothing
  from a CDN, nothing the CSP has to allow.

## Consequences

- Long breaks and irregular nodes are visible at a glance and can be exported
  for reports.
- Storage grows with the fleet: 500 nodes keep about 350 MB of single
  heartbeats at the default 48 hours. Lower `HEARTBEAT_BEATS_HOURS` (or 0) on
  small disks; the 7- and 30-day charts do not need it.
- The per-node rate limit ([ADR 0008](0008-hostile-input.md)) keeps a stolen
  node key from filling this table.
