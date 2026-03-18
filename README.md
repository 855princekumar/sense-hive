<p align="center">
  <img src="assets/banner.svg" alt="SenseHive Banner"/>
</p>

![Release](https://img.shields.io/badge/release-v1.0-blue.svg) ![Status](https://img.shields.io/badge/status-stable-success.svg) ![License](https://img.shields.io/badge/license-MIT-green.svg) ![Docker](https://img.shields.io/badge/docker-amd64%20%7C%20arm64-2496ED.svg?logo=docker&logoColor=white) ![Lightweight](https://img.shields.io/badge/lightweight-yes-brightgreen.svg) ![Self Hosted](https://img.shields.io/badge/self--hosted-true-orange.svg) ![IoT](https://img.shields.io/badge/iot-MQTT%20Dashboard-blueviolet.svg)

---

## Overview

SenseHive is a self-hosted MQTT data ingestion and visualization system designed for **rapid deployment, minimal overhead, and reliable local operation**.

It enables engineers and teams to:

* Ingest MQTT data streams
* Persist data locally
* Visualize real-time telemetry
* Export structured datasets

The system is optimized for **edge environments, internal infrastructure, and low-resource devices**, where traditional IoT platforms are unnecessarily complex or resource-intensive.

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

## Key Features

### MQTT Data Ingestion

* Compatible with any MQTT-compliant device
* Default public broker for quick testing
* Topic-based subscription

### Dynamic Data Storage

* Automatic topic-to-table mapping
* SQLite-based persistent storage
* Timestamped entries

### Real-Time Dashboard

* Live updates via Server-Sent Events
* Displays latest 50 entries per topic
* Topic-based data visualization cards

### Data Export

* CSV export per topic
* Easy data extraction for analysis

### Deployment Flexibility

* Docker-based one-click deployment
* Multi-architecture support (AMD64 and ARM)
* Local execution without Docker

---

## Folder Structure

```
.
├── version-1.1/
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
cd version-1.1
python app.py
```

Access the dashboard:

```
http://localhost:5000
```

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
