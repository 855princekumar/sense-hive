# Secure topics

Secure topics are MQTT topics whose messages are **encrypted and signed** with a
key that SenseHive issues, one key per topic. A device that holds a key just
publishes under the secure topic root: SenseHive finds the topic by itself,
checks the signature, decrypts the message and stores it like any other topic.
Nobody without the key can read the data, change it, move it to another topic or
replay it later, even on a public broker.

![Secure topics](../assets/secure-topics.png)

## Contents

- [Open topics and secure topics](#open-topics-and-secure-topics)
- [Quick start](#quick-start)
- [The life of a key](#the-life-of-a-key)
- [Online and offline for secure devices](#online-and-offline-for-secure-devices)
- [Device code](#device-code)
- [The protocol (sst1)](#the-protocol-sst1)
- [What is refused, and why](#what-is-refused-and-why)
- [Settings](#settings)
- [Security notes and limits](#security-notes-and-limits)
- [Troubleshooting](#troubleshooting)

## Open topics and secure topics

The **Topic logs** view has two cards: **Open topics** and **Secure topics**.
Each has an **(i)** guide.

| | Open topics | Secure topics |
| --- | --- | --- |
| How a topic is added | By hand: **Add Node**, any topic or wildcard | By itself: the first valid message under the root adds it |
| What the device sends | Anything (JSON or text) | A sealed JSON envelope (below) |
| Who can read the data on the broker | Anyone subscribed | Only holders of the key |
| Who can add data | Anyone who can publish | Only holders of the key, on the key's own topic |
| Online and offline | Last will topic, set when adding | Last will topic, named by the device in its message (optional) |
| History, CSV export, retention | Yes | Yes, the same |

The two never mix. An open topic under the secure root is refused, and an open
wildcard such as `#` never logs secure messages: they are only stored after
their signature checks out.

## Quick start

1. Open **Topic logs**, then the **Secure topics** card.
2. **Generate keys**: how many (1 to 100), an optional label (the name shown on
   the card) and, for a single key, an optional fixed topic.

   ![Generate keys](../assets/secure-generate.png)

3. The keys are shown **once**. **Download CSV** (key id, key, label, topic,
   the root to publish under, when an unused key expires) and keep it safe.

   ![New keys](../assets/secure-keys.png)

4. Put the key id and key on the device, set its clock by NTP, and publish
   under the root, for example `sensehive/secure/site-a/pump-1`.
5. The topic appears on the Secure topics card within a second of the first
   valid message. The key is now **active** and bound to that topic.

With the Python example (from `examples/secure-topics/python`):

```bash
pip install paho-mqtt cryptography
python secure_publish.py --broker 192.168.1.10 --kid <key id> --key <64 hex> \
    --topic sensehive/secure/site-a/pump-1 --payload '{"flow": 12.5}'
```

## The life of a key

| Status | Meaning |
| ------ | ------- |
| **pending** | Just generated. Waits up to 24 hours for its first valid message |
| **active** | Its first valid message arrived; bound to that topic for good |
| **expired** | Pending for 24 hours with no message. Its secret is erased |
| **revoked** | Turned off by a user. Its secret is erased; messages are refused |

- A key id is **never issued again**, even after it expired or was revoked, so
  an old device can never collide with a new one.
- The list never shows a key's secret. **Show key** shows it again after you
  enter your own password (and is rate limited like sign-in).
- **Revoke** a key when a device is lost, retired or its key may have leaked;
  the topic and its history stay. Generate a new key for the replacement.
- One key per topic: a key bound to one topic is refused on any other.
- Keys are stored encrypted with the app's secret key (`SECRET_KEY`, see
  [notes](#security-notes-and-limits)).

## Online and offline for secure devices

An MQTT last will is sent by the broker, not by the device, so it cannot be
signed. A secure device may instead **name its status topic inside a signed
message**, in a field called `sensehive_lwt`:

```json
{"flow": 12.5, "sensehive_lwt": "site-a/pump-1/status"}
```

SenseHive then follows that plain topic for online and offline, the same way it
does for open topics (`online`, `on`, `connected`, `up`, `true`, `1` are
online; `offline`, `off`, `disconnected`, `down`, `false`, `0` are offline;
a JSON payload with a `status` field works too, e.g. `{"status":"OFF"}`).

- It is set once, from a signed message; a later message cannot move it.
- It must be a plain topic outside the secure root, with no wildcards.
- Only the status is read from it: nothing on it is stored as data.

## Device code

Working examples, each tested by SenseHive's CI against the server:

| Platform | File | Notes |
| -------- | ---- | ----- |
| Python 3 | [`examples/secure-topics/python/secure_publish.py`](../examples/secure-topics/python/secure_publish.py) | paho-mqtt and cryptography; also a command line tool |
| MicroPython (ESP32, Pico W) | [`examples/secure-topics/micropython/sensehive_secure.py`](../examples/secure-topics/micropython/sensehive_secure.py) | Needs `cryptolib` with AES CTR (most ESP32 builds) and NTP time |
| Node.js and Node-RED | [`examples/secure-topics/node/sensehive-secure.js`](../examples/secure-topics/node/sensehive-secure.js) | Built-in `crypto` only; paste `seal()` into a function node |
| ESP32 Arduino | [`examples/secure-topics/arduino/sensehive_secure.ino`](../examples/secure-topics/arduino/sensehive_secure.ino) | mbedTLS (built in) and PubSubClient |

For a complete ESP32 device with a Wi-Fi setup portal, see
[PowerPulse](https://github.com/855princekumar/powerpulse), which comes in an
auto-discovery (secure) and a manual (open topic) build.

## The protocol (sst1)

A device holds a **key id** (16 hex characters) and a **key** (32 bytes, 64 hex
characters). For each message:

```text
enc_key = HMAC-SHA256(key, "sst1 enc")
mac_key = HMAC-SHA256(key, "sst1 mac")
nonce   = 16 random bytes
t       = Unix time in seconds (UTC)
c       = AES-256-CTR(enc_key, counter block = nonce, payload)
m       = first 16 bytes of HMAC-SHA256(mac_key, "sst1" 0x00 topic 0x00 key_id 0x00 t 0x00 nonce c)
```

`t` is written in decimal ASCII. The message published on `topic` is this JSON:

```json
{"v":1,"k":"<key id>","t":1760000000,"i":"<nonce, base64>","c":"<c, base64>","m":"<m, base64>"}
```

SenseHive accepts it when, in this order: it is valid JSON of this shape
(version 1, sizes right), the key id is known and pending or active, an active
key is bound to this very topic, `t` is within 5 minutes of the server's clock,
the tag matches (compared in constant time), and the nonce was not seen before
in the last 11 minutes. Then it decrypts `c`. The payload inside may be JSON or
text, like any topic.

Why these choices:

- **AES-CTR with HMAC-SHA256** (encrypt, then sign everything) instead of
  AES-GCM: MicroPython's `cryptolib` and small microcontrollers have AES and
  SHA-256 but often no GCM. Encrypt-then-MAC with separate derived keys is a
  well understood construction.
- **The topic, key id and time are signed**, so a message cannot be moved to
  another topic, attributed to another key or replayed later.
- **A random 16-byte nonce** for every message: the same payload never looks
  the same twice on the broker.

## What is refused, and why

Refused messages are dropped quietly (nothing is stored, nothing is sent back)
and counted. The count shows on the Secure topics card (hover it for the reasons) and at
`GET /api/secure/status` (signed in).

| Reason | Meaning |
| ------ | ------- |
| `format` | Not a sst1 envelope (bad JSON, version, sizes, base64) |
| `unknown_key` | No such key id |
| `inactive_key` | The key expired or was revoked |
| `wrong_topic` | The key is bound to another topic |
| `stale` | Time more than 5 minutes off: set the device clock (NTP) |
| `signature` | The tag does not match: wrong key, or the message was changed |
| `replay` | The same message (nonce) again |

## Settings

| Variable | Default | Purpose |
| -------- | ------- | ------- |
| `SENSEHIVE_SECURE_TOPICS` | `true` | `false` turns secure topics off (no subscription under the root) |
| `SENSEHIVE_SECURE_ROOT` | `sensehive/secure` | The root devices publish under; SenseHive subscribes to `<root>/#` |
| `SECRET_KEY` | random, saved next to the database | Also encrypts the stored keys: keep it, and back it up with the database |

The secure root uses the same broker as open topics (**Settings** > MQTT
Broker).

## Security notes and limits

- **Keep `SECRET_KEY` with the database.** Stored keys are encrypted with it.
  If it changes (a new file, a new value), stored keys can no longer be shown
  again and devices must get new keys. The default secret file next to the
  database is kept by the normal backup of the data folder.
- **The broker still sees metadata:** topic names, key ids, times and message
  sizes. Choose topic names that do not give away more than you want.
- **Clocks matter:** messages more than 5 minutes off are refused. Devices need
  NTP; SenseHive's host needs a correct clock too.
- **Replays are remembered in memory** for 11 minutes. Right after a restart, a
  message captured less than 5 minutes earlier could be accepted once more
  (its data is genuine, it would just be stored twice).
- **Broker access is separate.** Secure topics protect the data, not the
  broker; on your own broker, still use credentials and TLS where you can.
- **A key on a device is only as safe as the device.** If a device is stolen,
  revoke its key.

## Troubleshooting

| Symptom | Check |
| ------- | ----- |
| The topic never appears | Published under the root shown on the Secure topics card? Key pending (not expired)? Look at the refused count and reason |
| `stale` refusals | Device clock: NTP reachable? MicroPython: `ntptime.settime()` after Wi-Fi is up |
| `signature` refusals | Key id and key from the same CSV row? Topic in the signature exactly the topic published to? |
| `wrong_topic` | One key per topic: generate another key for a second topic |
| Shows *No LWT* | Send `sensehive_lwt` in a signed message (it is set by the first message that names one) |
| Keys cannot be shown again after a move | `SECRET_KEY` (or its file) was not moved with the database |
