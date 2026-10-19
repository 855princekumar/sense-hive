# Quick start: Docker, pip or Home Assistant

Three ways to run SenseHive, each from nothing to live data in a few minutes.
Every command and every output on this page is real: CI runs the same steps on
every change (the pip wheel, the Docker image and the Home Assistant add-on,
each with a real MQTT broker, an emulated fleet and a browser).

| | Docker | pip | Home Assistant add-on |
| --- | --- | --- | --- |
| For | a server, a Raspberry Pi (64-bit), a NAS | any machine with Python 3.9+ | Home Assistant OS or Supervised |
| Install | `docker run ...` | `pip install sensehive-iot` | the add-on store |
| Broker | any (yours, or a public one) | any | the Mosquitto add-on, found by itself |
| Sign-in | SenseHive's own | SenseHive's own | Home Assistant's (no second sign-in) |

Contents: [Docker](#1-docker) · [pip](#2-pip) · [Home Assistant](#3-home-assistant-add-on) ·
[Your own devices](#4-your-own-devices) · [Troubleshooting](#5-troubleshooting) · [How this is tested](#6-how-this-is-tested)

No broker yet? For trying SenseHive on one machine, run a local one:

```bash
docker run -d --name mosquitto -p 1883:1883 eclipse-mosquitto:2 mosquitto -c /mosquitto-no-auth.conf
```

(that broker accepts anyone: keep it on your own machine or network).

---

## 1. Docker

One image for x86 and 64-bit Raspberry Pi (`amd64` and `arm64`):

```bash
docker run -d --name sensehive --restart unless-stopped -p 5000:5000 \
  -v sensehive-data:/app/data \
  -e SENSEHIVE_ADMIN_PASSWORD='choose-a-strong-password' \
  -e DEFAULT_BROKER_HOST=192.168.1.10 -e SENSEHIVE_FORCE_BROKER=true \
  devprincekumar/sense-hive:1.8
```

- `-v sensehive-data:/app/data` keeps the database (SQLite) when the container is replaced.
- `DEFAULT_BROKER_HOST` is your broker (`host.docker.internal` for one on the same machine,
  with `--add-host host.docker.internal:host-gateway` on Linux). Leave both broker variables
  out to choose the broker later in **Settings**.
- `:1.8` follows the 1.8 releases; pin one (`:1.8.2`) to change only when you choose; `:latest` follows every release.

Open **http://localhost:5000**, sign in as `admin` with your password.

<p align="center"><img src="../assets/login.png" width="70%" alt="Sign-in page" /></p>

**Try it with the emulated fleet** (in the image since 1.8.2):

```bash
docker exec sensehive python demo_fleet.py --broker 192.168.1.10 \
  --register http://127.0.0.1:5000 --password 'choose-a-strong-password'
```

The dashboard fills in by itself; stop the fleet with Ctrl+C and every device turns
Inactive (its last will).

---

## 2. pip

```bash
python3 -m venv ~/sensehive && . ~/sensehive/bin/activate
pip install sensehive-iot
```

```text
$ pip show sensehive-iot
Name: sensehive-iot
Version: 1.8.1
Requires: cryptography, Flask, paho-mqtt, pytz

$ sensehive --version
sensehive 1.8.1
```

Start it with your broker:

```bash
sensehive --port 5000 --broker localhost
```

```text
🚀 Starting IoT Dashboard v1.8.1
📁 Database path: /home/you/.sensehive/iot_dashboard.db
🌐 Listening on: 0.0.0.0:5000
============================================================
MQTT LOGGING: Runs 24/7 without GUI/Login
GUI ACCESS: Requires login (change the admin password after the first sign-in)
============================================================
✅ Default user created: admin/admin123
✅ Initialized with default broker: localhost:1883
🔌 Connecting to MQTT broker: localhost:1883
✅ Connected to MQTT broker
📡 Subscribed to: sensehive/secure/#
```

Is it up?

```text
$ curl http://localhost:5000/api/health
{"mqtt_connected":true,"status":"healthy","timestamp":"2026-10-19T20:07:19.850545"}
```

More options: `sensehive --help` (`--broker-port`, `--broker-username`, `--broker-password`,
`--timezone`, `--data-dir`; data goes to `~/.sensehive` by default). Sign in at
**http://localhost:5000** as `admin` / `admin123`, then change the password in **Settings**.

**Try it with the emulated fleet** (`sensehive-demo` comes with the package): devices
with their own last will and live JSON readings. `--register` signs in and adds them as nodes.

```text
$ sensehive-demo --broker localhost --register http://localhost:5000
5 of 5 devices are nodes in http://localhost:5000
5 devices online on localhost:1883, a reading every 5s (Ctrl+C to stop)
```

<p align="center">
  <img src="../assets/quickstart-laptop.png" width="70%" alt="The dashboard filled by sensehive-demo after pip install" />
  <img src="../assets/quickstart-phone.png" width="22%" alt="The same on a phone" />
</p>

That is a real `pip install sensehive-iot` from PyPI with the emulated fleet running:
every device has its card, live readings, and **Active** from its last will. `sensehive-demo --help`
for more (`--devices`, `--interval`, `--count`, `--offline`, `--prefix`).

As a service that starts at boot (systemd, on Linux):

```ini
# /etc/systemd/system/sensehive.service
[Unit]
Description=SenseHive MQTT dashboard
After=network-online.target
Wants=network-online.target

[Service]
User=sensehive
ExecStart=/home/sensehive/sensehive/bin/sensehive --port 5000 --broker localhost
Environment=SENSEHIVE_ADMIN_PASSWORD=choose-a-strong-password
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now sensehive
```

---

## 3. Home Assistant add-on

[![Add repository to Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2F855princekumar%2Fsensehive-ha-addon)

1. **Add the repository**: the button above, or **Settings, Apps, Install app** (older Home Assistant: **Settings, Add-ons, Add-on Store**), the menu
   (top right), **Repositories**: `https://github.com/855princekumar/sensehive-ha-addon`
2. **Install** SenseHive, then **Start**.
3. Turn on **Show in sidebar**.
4. Open **SenseHive** from the sidebar. Home Assistant has already signed you in, and if the
   **Mosquitto broker** add-on is installed, SenseHive is connected to it by itself.

<p align="center">
  <img src="https://raw.githubusercontent.com/855princekumar/sensehive-ha-addon/main/docs/screenshots/ha-panel-laptop.png" width="72%" alt="SenseHive in the Home Assistant sidebar" />
  <img src="https://raw.githubusercontent.com/855princekumar/sensehive-ha-addon/main/docs/screenshots/ha-panel-phone.png" width="20%" alt="SenseHive in the Home Assistant app on a phone" />
</p>
<p align="center">
  <img src="https://raw.githubusercontent.com/855princekumar/sensehive-ha-addon/main/docs/screenshots/ha-addon-info.png" width="45%" alt="The add-on's page in Home Assistant: Start, Show in sidebar, Open Web UI" />
  <img src="https://raw.githubusercontent.com/855princekumar/sensehive-ha-addon/main/docs/screenshots/ha-addon-config.png" width="45%" alt="The add-on's options in Home Assistant" />
</p>

The data lives in the add-on's folder, so it is in Home Assistant backups. Direct access on
port 5000 is off unless you set a port in the add-on's **Network** settings. Full guide and
screenshots: [the add-on documentation](https://github.com/855princekumar/sensehive-ha-addon/blob/main/sensehive/DOCS.md).

---

## 4. Your own devices

**Add Node** (top right): the MQTT topic (wildcards work: `sensors/#`, `home/+/temp`), a node id
(the device), a tag, and optionally the device's last-will topic for online and offline status.

<p align="center"><img src="../assets/add-node.png" width="80%" alt="Add Node: topic, node id, tag, last will" /></p>

Then publish. Any payload works: JSON is shown field by field, anything else as text.

```bash
# Mosquitto's command line tools
mosquitto_pub -h localhost -t greenhouse/zone-1/climate -m '{"temperature": 23.4, "humidity": 61}'
mosquitto_pub -h localhost -t greenhouse/status -m online -r     # last will topic: retained online
```

```python
# Python (pip install paho-mqtt)
import json, time
import paho.mqtt.client as mqtt

c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='greenhouse-esp32')
c.will_set('greenhouse/status', 'offline', qos=1, retain=True)   # SenseHive shows Inactive when it drops
c.connect('localhost', 1883)
c.loop_start()
c.publish('greenhouse/status', 'online', qos=1, retain=True)
while True:
    c.publish('greenhouse/zone-1/climate', json.dumps({'temperature': 23.4, 'humidity': 61}))
    time.sleep(10)
```

```cpp
// ESP32 / ESP8266 (Arduino, PubSubClient)
client.connect("greenhouse-esp32", "greenhouse/status", 1, true, "offline");   // the last will
client.publish("greenhouse/status", "online", true);
client.publish("greenhouse/zone-1/climate", "{\"temperature\": 23.4, \"humidity\": 61}");
```

Encrypted and signed device data that SenseHive finds by itself: [secure topics](SECURE-TOPICS.md).
Edge nodes (Raspberry Pi, gateways) with a heartbeat: [heartbeats](HEARTBEAT.md).

<p align="center">
  <img src="../assets/dashboard.png" width="90%" alt="The dashboard with an example site" />
</p>
<p align="center">
  <img src="../assets/history.png" width="45%" alt="A topic's history, chart and CSV" />
  <img src="../assets/dashboard-dark.png" width="45%" alt="Dark theme" />
</p>

---

## 5. Troubleshooting

| What you see | What to check |
| --- | --- |
| **Disconnected** in the header | **Settings**: the broker's host, port, username and password; **Test Connection** checks them, then **Save All**. From Docker, `localhost` is the container itself: use the host's address or `host.docker.internal` |
| A card says **Waiting for data** | Nothing published on that topic yet. Check the exact topic (case matters) with `mosquitto_sub -h HOST -t '#' -v` |
| Status **Unknown** | The last-will topic has not said `online` or `offline` yet. Publish a retained `online` when the device connects |
| Status **No LWT** | No last-will topic set for that node (Edit, the gear on the card) |
| `pip install` fails to build cryptography | Upgrade pip first (`pip install -U pip`); old pips cannot use the prebuilt wheels |
| Port 5000 in use | `sensehive --port 5055`, or `-p 5055:5000` with Docker |
| Forgot the admin password | `SENSEHIVE_ADMIN_PASSWORD` sets the password of a **new** database only. Signed in, change it in **Settings**; locked out, starting over means a new data folder (the logged data stays in the old one) |

`GET /api/health` answers without signing in: `{"mqtt_connected": true, "status": "healthy"}`.

---

## 6. How this is tested

| What | In CI on every change |
| --- | --- |
| pip | the built wheel installed in a clean venv, `sensehive --broker ...`, a real Mosquitto broker, `sensehive-demo --register`, and a browser on phone, tablet, laptop and desktop (cards, live values, last-will status, details, dark mode, no layout or console errors): 25 checks |
| Docker | the image, `docker run`, the same broker, fleet and browser checks: 25 checks |
| The pages | every page and dialog on phone, tablet, laptop and desktop, zoom 67 to 200%, light and dark, plus interactions: 568 checks |
| Home Assistant | a real Home Assistant (Supervisor and Core), the Mosquitto add-on, SenseHive in the sidebar; ingress, data, restart, backup, security rating (21 checks) and a browser in the panel (30 checks) |
| Screenshots | `tools/screenshots.py` takes the pictures in this repository from a real SenseHive (CI keeps them as an artifact) |
