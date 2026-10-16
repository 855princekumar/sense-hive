# Using SenseHive

![Dashboard](../assets/dashboard.png)

## Topics, node IDs and tags

Every card is one MQTT topic. **Add Node** asks for:

| Field | Required | Meaning |
| ----- | -------- | ------- |
| MQTT Topic | yes | What to subscribe to. Wildcards work: `sensors/#`, `home/+/temp` |
| Node ID | yes | The device the topic belongs to; topics with the same node ID are grouped |
| Tag | yes | Any label (site, room, purpose), used by the tag filter |
| LWT / status topic | no | The device's last-will topic, for online/offline status |

Each topic gets its own table. Every message is stored with a timestamp in your
timezone; JSON payloads are kept as JSON, anything else as text. A topic cannot
contain double quotes or control characters and is at most 512 characters long.

## The dashboard

Two cards at the top choose what you see, with a short fade between them:

- **Topic logs**: the MQTT topics you add, with topic and entry counts and how
  many are active.
- **Heartbeats**: edge nodes running the heartbeat agent, found by themselves,
  with online, silent and offline counts. See [Heartbeats](HEARTBEAT.md#heartbeat-history-charts-and-csv-export).

The address follows the choice (`?view=heartbeats`), so a bookmark opens the
right view.

- **Top bar:** broker connection, online/offline counts of nodes and topics
  (wide screens), **Add Node**, **Settings**, light/dark theme
  (remembered in this browser) and **Sign out**. On a phone the buttons become
  icons and wrap onto a second line.
- **Summary bar:** topics, nodes, stored entries and database size; filter by
  tag, sort (newest, name, tag, status, last update, entries, size) and
  **Group by node**.
- **Cards:** the latest value (objects as key/value rows, arrays and nested
  objects as formatted JSON, long values wrapped inside the card), LWT status,
  entry count and size, and the actions **Details** (last 50 values), edit
  (tag, node ID, LWT), **Export CSV** and **Delete** (offers an export first).

Values arrive live over a server-sent event stream; every open tab updates.

![Grouped by node](../assets/dashboard-grouped.png)

## LWT status

Give a topic its device's last-will topic and SenseHive shows **Active** or
**Inactive** from the last payload on it. `online`, `connected`, `up`, `true`
and `1` count as active; `offline`, `disconnected`, `down`, `false` and `0` as
inactive. Other words can be set per topic (LWT online/offline values).
Topics without an LWT topic show **No LWT**.

## History and export

**Details** shows the last 50 values with their times. **Export CSV** downloads
every stored entry of the topic.

![History](../assets/history.png)

## Settings

![Settings](../assets/settings.png)

- **MQTT Broker:** host, port, username, password; **Test Connection** before
  saving.
- **Timezone** used for new entries.
- **Data Retention:** keep entries for N days and/or at most N per topic;
  **Run cleanup now**.
- **Change Password.**

## Heartbeats view

The **Heartbeats** card lists every node running the
[heartbeat agent](https://github.com/855princekumar/mqtt-heartbeat-service):
`online`, `offline` (its last will arrived) or `silent` (nothing heard), with
the last heartbeat, how long it has been in that state, the last will time and
the agent version, with a history chart per node (1 minute to 30 days) and
CSV export for one, the selected or all nodes. See
[Heartbeats](HEARTBEAT.md#heartbeat-history-charts-and-csv-export).

![Heartbeats](../assets/heartbeats.png)

## On a phone

![Phone](../assets/phone.png)
