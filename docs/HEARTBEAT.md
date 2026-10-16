# Heartbeats and EdgeShell

SenseHive can receive **encrypted, authenticated heartbeats** from edge nodes
and tell another system, such as [EdgeShell](https://github.com/855princekumar/edgeshell),
whether each node is up, without that system needing a VPN path to the node.

```
 edge node                          public MQTT broker (TLS)               SenseHive
 ┌───────────────────────┐          ┌───────────────────┐          ┌──────────────────────┐
 │ heartbeat agent        │──AES-GCM─▶ rotating topics    │──────────▶ receiver: verify,     │
 │ (systemd, own user)    │  every   │ (change every      │          │ track, store         │
 │ last will on drop      │  10 s    │  10 minutes)       │          │ /heartbeats  /api/.. │
 └───────────────────────┘          └───────────────────┘          └──────────┬───────────┘
                                                                               │ read-only API
                                                                     ┌─────────▼───────────┐
                                                                     │ EdgeShell: badges,   │
                                                                     │ uptime, SLA          │
                                                                     └─────────────────────┘
```

## What travels and what does not

- Each message carries only the node's short ID, a counter, a session number,
  the time and the agent version, sealed with **AES-256-GCM** under that node's
  own key. No hostnames, addresses, credentials or sensor data.
- Topics are derived from the fleet key and change every ten minutes, so a
  stranger on the public broker cannot find or follow a fleet.
- SenseHive drops (and counts) anything it cannot verify: unknown nodes,
  replays, old or future timestamps, and messages sealed with another key.

The protocol is shared by the agent, SenseHive and EdgeShell
(`heartbeat_protocol.py`) and pinned by the same test vectors in all three.

## Turning it on

1. Generate a fleet master key and an API token (see
   [Configuration](CONFIGURATION.md#heartbeat-receiver)).
2. Give SenseHive both, in `.env`:

   ```bash
   HEARTBEAT_MASTER_KEY=<64 hex characters>
   HEARTBEAT_API_TOKEN=<32+ characters>
   ```

3. Restart. The log says `Heartbeat receiver on`; **Heartbeats** shows
   `connected to the heartbeat broker`.

## Installing the agent on nodes

The agent lives in
[mqtt-heartbeat-service](https://github.com/855princekumar/mqtt-heartbeat-service).
It installs to `/opt/edgeshell-heartbeat`, runs as its own unprivileged user
under systemd, and holds only that node's derived key (not the master key).
EdgeShell installs and updates it for you from **Fleet Setup**; by hand:

```bash
sudo bash install.sh agent.env      # install or update (agent.env: the node's identity and key)
sudo bash install.sh --uninstall    # remove everything
```

See the agent's README for the contents of `agent.env` and the hot-reloaded
`config.yaml`.

## Node states

| State | Meaning |
| ----- | ------- |
| `online` | A verified heartbeat in the last `HEARTBEAT_STALE_SECONDS` (35) |
| `offline` | The node's last will arrived: its connection dropped |
| `silent` | Neither: usually the broker or the internet path, not the node |

Every change is kept as an event; per-minute presence is kept for
`HEARTBEAT_KEEP_DAYS` (30) for uptime and SLA figures.

## Read-only API

`GET` only, with `Authorization: Bearer <HEARTBEAT_API_TOKEN>` or a signed-in
session.

| Endpoint | Returns |
| -------- | ------- |
| `/api/heartbeat/status` | receiver on, broker connected, nodes seen, rejected messages |
| `/api/heartbeat/nodes` | per node: status, last heartbeat, since, last will time, agent version |
| `/api/heartbeat/minutes?since=<unix>` | per node, the minutes with a verified heartbeat |
| `/api/heartbeat/events?since=<unix>` | status changes, oldest first |

## With EdgeShell

EdgeShell runs SenseHive next to itself and:

- polls the API with the token and shows heartbeat badges, uptime and SLA on
  its node cards;
- installs the agent on nodes (**Fleet Setup**), giving each its own key;
- links admins to SenseHive under `/sensehive/` behind its own sign-in gate:
  a click from the EdgeShell admin panel opens it; a direct visit asks for a
  fresh 2FA code first. SenseHive keeps its own password and lockout on top.

For that setup SenseHive runs with the cookie settings shown in
[Configuration](CONFIGURATION.md#example-env-behind-https-on-a-sub-path).
