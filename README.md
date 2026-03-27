<p align="center">
  <img src="assets/banner.svg" alt="SenseHive Banner"/>
</p>

![Release](https://img.shields.io/badge/release-v1.0-blue.svg) ![Status](https://img.shields.io/badge/status-stable-success.svg) ![License](https://img.shields.io/badge/license-MIT-green.svg) ![Docker](https://img.shields.io/badge/docker-amd64%20%7C%20arm64-2496ED.svg?logo=docker&logoColor=white) ![Lightweight](https://img.shields.io/badge/lightweight-yes-brightgreen.svg) ![Self Hosted](https://img.shields.io/badge/self--hosted-true-orange.svg) ![IoT](https://img.shields.io/badge/iot-MQTT%20Dashboard-blueviolet.svg)![Home Assistant](https://img.shields.io/badge/home--assistant-compatible-41BDF5.svg?logo=home-assistant&logoColor=white)

> Debug, log, and visualize your MQTT data instantly, like uptime-kuma, but built for MQTT and IoT data.

**Run → Add Topic → Publish → See Data in under 30 seconds.**

---

## Index

- [Quick Start (30 seconds)](#quick-start-30-seconds)
- [Dashboard Preview](#dashboard-preview)
- [Key Features](#key-features)
- [Overview](#overview)
- [Example Use Cases](#example-use-cases)
- [Why SenseHive Was Built](#why-sensehive-was-built)
- [Design Principles](#design-principles)
- [System Architecture](#system-architecture)
- [Data Flow](#data-flow)
- [Folder Structure](#folder-structure)
- [Deployment](#deployment)
- [Home Assistant Integration](#home-assistant-integration)
- [Default Access](#default-access)
- [Data Persistence](#data-persistence)
- [Configuration](#configuration)
- [Test Setup (Quick Validation)](#test-setup-quick-validation)
- [Example Payload](#example-payload)
- [Performance Benchmarks](#performance-benchmarks)
- [Comparison with Existing Solutions](#comparison-with-existing-solutions)
- [Positioning](#positioning)
- [When to Use SenseHive](#when-to-use-sensehive)
- [When NOT to Use SenseHive](#when-not-to-use-sensehive)
- [Current Limitations](#current-limitations)
- [Versioning and Release Status](#versioning-and-release-status)
- [Stability Statement](#stability-statement)
- [Community Release](#community-release)
- [License](#license)
- [Closing Note](#closing-note)
- [Support & Feedback](#support--feedback)

---

## Quick Start (30 seconds)

Get SenseHive running and visualize MQTT data instantly.

### 1. Run the Container

```bash
docker run -d -p 5000:5000 devprincekumar/sense-hive:latest
```

---

### 2. Open the Dashboard

```
http://localhost:5000
```

Login with default credentials and access the dashboard.

---

### 3. Add Any MQTT Topic

* Click **“+ Add Node”**
* Enter a topic (example):

  ```
  test/topic
  ```
* Save

> Example Topics You Can Try
- home/livingroom/temp
- sensor/temperature
- test/topic

No setup required, just Subscribe and watch.

---

### 4. Publish Data (From Anywhere)

Publish a message using any MQTT client:

```bash
mosquitto_pub -h broker.hivemq.com -t test/topic -m "hello world"
```

That’s it, your data will appear **instantly** on the dashboard, no scripts, no setup.

> Run → Add Topic → Publish → See Data

---

### Try Other Public Brokers (Optional)

You can switch brokers anytime:

* `broker.hivemq.com` (default)
* `test.mosquitto.org`
* `broker.emqx.io`

| Broker             | Host                 | Port | Notes                   |
| ------------------ | -------------------- | ---- | ----------------------- |
| Eclipse Mosquitto  | `test.mosquitto.org` | 1883 | Very popular, stable    |
| EMQX Public Broker | `broker.emqx.io`     | 1883 | Good global performance |
| HiveMQ EU          | `broker.hivemq.com`  | 1883 | Default used            |

Example:

```bash
mosquitto_pub -h test.mosquitto.org -t test/topic -m "hello again"
```
---

### Tip
Use a unique topic if testing on public brokers:
```
yourname/test/topic1
```
You can also use the included test script for automated data simulation if needed.

### Not Seeing Data?

* Topic must match exactly
* Use a unique topic (shared brokers)
* Check host/port (1883)
* Wait a few seconds

---
## Dashboard Preview

<p align="center">
  <img src="assets/login.png" width="60%" style="margin:5px;" />
  <img src="assets/Main_Dashboard.png" width="60%" style="margin:5px;" />
</p>
<p align="center">
  <img src="assets/settings.png" width="60%" style="margin:5px;" />
</p>
<p align="center">
  <img src="assets/test-topic.png" width="45%" style="margin:5px;" />
  <img src="assets/test-script-output.png" width="45%" style="margin:5px;" />
</p>

---

## Key Features

| Category                   | Highlights                                                                         |
| -------------------------- | ---------------------------------------------------------------------------------- |
| **MQTT Data Ingestion**    | Compatible with any MQTT device · Public broker support · Topic-based subscription |
| **Dynamic Data Storage**   | Auto topic-to-table mapping · SQLite persistence · Timestamped entries             |
| **Real-Time Dashboard**    | Live updates (SSE) · Latest 50 entries per topic · Topic-based visualization cards |
| **Data Export**            | CSV export per topic · Easy data extraction                                        |
| **Deployment Flexibility** | Docker one-click run · AMD64 & ARM support · Runs without Docker                   |
---

## Overview

SenseHive is a self-hosted MQTT data ingestion and visualization system designed for **rapid deployment, minimal overhead, and reliable local operation**.

It enables engineers and teams to:

* Ingest MQTT data streams
* Persist data locally
* Visualize real-time telemetry
* Export structured datasets

The system is optimized for **edge environments, internal infrastructure, and low-resource devices**, where traditional IoT platforms are unnecessarily complex or resource-intensive.

## Example Use Cases

- Monitoring environmental sensors (temperature, humidity, AQI)
- Collecting telemetry from distributed IoT nodes
- Rapid prototyping of MQTT-based systems
- Internal dashboards for lab or field deployments
  
---

## Why SenseHive Was Built

In practical IoT deployments involving weather monitoring systems, DAQ nodes, and distributed sensor networks, existing solutions were evaluated but did not meet the need for:

* Fast setup
* Lightweight execution
* Direct data visibility

Most available tools required:

* Complex configuration
* Multiple dependent services
* Higher system resources

The requirement was clear:

> A simple, plug-and-play system that can be deployed instantly and start logging MQTT data without setup overhead.

SenseHive was built to meet that need.

The experience aimed to replicate the simplicity of tools that offer immediate usability with minimal configuration - but for MQTT-based data systems.

---

## Design Principles

* Simplicity over complexity
* Edge-first deployment
* Minimal dependencies
* One-command startup
* Reliable local operation

---

## System Architecture

```mermaid
graph TD
    A[IoT Devices / DAQ Systems] -->|MQTT| B[MQTT Broker]
    B --> C[SenseHive MQTT Client]

    C --> D[Processing Layer]
    D --> E[SQLite Database]

    E --> F[Flask Backend]
    F --> G[SSE Stream Engine]

    G --> H[Web Dashboard]
    F --> I[CSV Export API]
```

---

## Data Flow

```mermaid
sequenceDiagram
    participant Device
    participant Broker
    participant SenseHive
    participant DB
    participant UI

    Device->>Broker: Publish MQTT Payload
    Broker->>SenseHive: Forward Message
    SenseHive->>DB: Store Data
    SenseHive->>UI: Stream Updates (SSE)
    UI->>User: Display Latest Data
```
---

## Folder Structure

```
.
├── version-1.0/
│   ├── app.py
│   ├── Dockerfile
│   └── application files
│
├── docker-compose/
│   ├── docker-compose-amd.yml
│   └── docker-compose-arm.yml
│
├── test-sensehive/
│   └── test publisher script
│
├── README.md
└── LICENSE
```

---

## Deployment

### Option 1: Docker (Recommended)

#### Pull Images

```bash
docker pull devprincekumar/sense-hive:latest
```

* For AMD64 / x86 systems

```bash
docker pull devprincekumar/sense-hive:arm-pi-5
```

* For ARM systems (Raspberry Pi 5 optimized)

---

#### Run Container

```bash
docker run -d \
  -p 5000:5000 \
  -v $(pwd)/data:/app/data \
  devprincekumar/sense-hive:latest
```

---

### Option 2: Docker Compose

Use the provided compose files:

* `docker-compose-amd.yml`
* `docker-compose-arm.yml`

---

### Option 3: Local Run (Without Docker)

```bash
cd version-1.0
python app.py
```

Access the dashboard:

```
http://localhost:5000
```
---

## Home Assistant Integration

SenseHive can be used alongside Home Assistant by connecting to the same MQTT broker (e.g., Mosquitto add-on).

This setup is useful for:

- Inspecting raw MQTT topics  
- Logging data independently of Home Assistant  
- Exporting MQTT data for analysis  

---

### Quick Setup (Docker Compose)

#### Standard Systems (x86 / AMD64)

```yaml
version: "3.8"

services:
  sense-hive:
    image: devprincekumar/sense-hive:latest
    container_name: sense-hive
    ports:
      - "5500:5000"
    volumes:
      - ./sensehive-data:/app/data
    restart: unless-stopped
    networks:
      - sense-hive-network
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:5000/api/status')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s

networks:
  sense-hive-network:
    driver: bridge
```

Access SenseHive at: http://localhost:5500  

---

#### Raspberry Pi (ARM)

```yaml
version: "3.8"

services:
  sense-hive:
    image: devprincekumar/sense-hive:arm-pi-5
    container_name: sense-hive
    ports:
      - "5500:5000"
    volumes:
      - /config/sensehive:/app/data
    restart: unless-stopped
    networks:
      - sense-hive-network
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:5000/api/status')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s

networks:
  sense-hive-network:
    driver: bridge
```

Access SenseHive at: http://localhost:5500  

---

### Notes for Home Assistant Users

* Use the same MQTT broker configured in Home Assistant (typically Mosquitto)

* Broker host is usually:

  * `homeassistant.local`
  * or the Home Assistant IP (e.g., `192.168.1.x`)

* Default MQTT port: `1883`

* Use the same credentials defined in Home Assistant

---

### Data Persistence

* For standard Docker setups:

  * `./sensehive-data:/app/data`

* For Home Assistant environments:

  * `/config/sensehive:/app/data`

This ensures data persists across container restarts and aligns with Home Assistant storage conventions.

---

## Default Access

```
Username: admin
Password: admin123
```

---

## Data Persistence

Database location:

```
/app/data/iot_dashboard.db
```

Note:

* Without volume mounting, data will not persist across container restarts

## Configuration

The default setup uses a public MQTT broker for quick testing.

You can modify:
- MQTT broker (local or remote)
- Credentials
- Timezone settings

Configuration is currently handled within the application code and UI, with extended configurability planned in future releases.

---

## Test Setup (Quick Validation)

A test publisher is included to simulate IoT data.

### Step 1: Start SenseHive

Run using Docker or local execution.

---

### Step 2: Run Test Script

```bash
cd test-sensehive
python test_script.py
```

---

### Step 3: Configure Dashboard

* Add topic: `test-sensehive`
* Observe live updates
* View latest 50 entries
* Export data using CSV

---

## Example Payload

```json
{
  "device_id": "sensehive_node_01",
  "timestamp": 1710000000,
  "temperature": 28.5,
  "humidity": 62,
  "status": "active"
}
```

## Performance Benchmarks

Based on internal LAN testing with Docker deployment.
Tested on: Raspberry Pi 5 (8GB) and x86 local system

| Metric                | Value / Range              |
|---------------------|---------------------------|
| Ingestion Rate       | ~1k–3k msgs/min           |
| Devices Supported    | ~20–50 devices            |
| CPU Usage            | ~5–15% (Raspberry Pi 5)   |
| Memory Usage         | ~80–150 MB                |
| Dashboard Latency    | <1 second                 |

> Note: Values are indicative and may vary depending on workload and hardware.

---

## Comparison with Existing Solutions

| Feature / Tool       | SenseHive           | ThingsBoard    | Node-RED        | Grafana + MQTT | Home Assistant |
| -------------------- | ------------------- | -------------- | --------------- | -------------- | -------------- |
| Setup Complexity     | Very Low            | High           | Medium          | High           | Medium         |
| One-Click Deployment | Yes                 | No             | Partial         | No             | Partial        |
| Resource Usage       | Low                 | High           | Medium          | High           | Medium         |
| MQTT Native Support  | Yes                 | Yes            | Yes             | Plugin-based   | Yes            |
| Built-in Storage     | Yes                 | Yes            | No              | No             | Yes            |
| Real-Time Dashboard  | Yes                 | Yes            | Limited         | Yes            | Yes            |
| Data Export          | Yes                 | Yes            | Custom          | Yes            | Limited        |
| Edge Device Friendly | Yes                 | Limited        | Yes             | Limited        | Limited        |
| Learning Curve       | Low                 | High           | Medium          | High           | Medium         |
| Intended Use Case    | Lightweight logging | Enterprise IoT | Flow automation | Observability  | Smart home     |

---

## Positioning

SenseHive is designed as:

> A lightweight, plug-and-play MQTT data logger and dashboard for quick deployment and internal use.

It is not intended to replace full-scale IoT platforms.

---

## When to Use SenseHive

- You need quick MQTT data logging without heavy setup  
- You are working with edge devices (ESP32, Raspberry Pi, DAQ systems)  
- You want a self-hosted, lightweight dashboard  
- You need fast prototyping or internal monitoring  

---

## When NOT to Use SenseHive

- You need large-scale distributed IoT infrastructure  
- You require multi-tenant SaaS architecture  
- You need advanced analytics or big data pipelines  
- You expect enterprise-grade scalability out of the box

---

## Current Limitations

* SQLite may not scale for high-throughput systems
* No data retention policy (planned)
* WAL mode not yet enabled
* Table-per-topic schema limits scalability
* No dynamic schema optimization
* No built-in migration to time-series databases
* Basic authentication system
* No alerting or automation engine

---

## Versioning and Release Status

### v1.0 (Current)

* Stable and tested
* Running in internal LAN environments
* Used for real data aggregation across multiple devices
* Verified over more than two months of continuous usage

---

### v1.1 (Upcoming)

Planned improvements:

* WAL mode for improved database performance
* Data retention policies
* Improved write efficiency
* Schema optimization groundwork

---

## Stability Statement

SenseHive is:

* Reliable for self-hosted and LAN-based deployments
* Suitable for continuous MQTT data logging
* Actively used in internal setups

However, it is still under development toward a fully scalable production-grade platform.

---

## Community Release

This project is being released as open source to:

* Enable wider testing
* Gather feedback from real-world use cases
* Improve scalability and feature set

Contributions, suggestions, and improvements are encouraged.

---

## License

MIT License

---

## Closing Note

SenseHive is built to simplify MQTT-based data logging and visualization without introducing unnecessary complexity.

It is particularly suited for:

* Edge deployments
* Rapid prototyping
* Internal monitoring systems
* Lightweight IoT infrastructures

The focus remains on usability, portability, and practical engineering needs.

---

## Support & Feedback

If you find this useful, consider starring the repository.

Feedback, issues, and contributions are welcome to help improve the project.
