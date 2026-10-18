# 0009: Secure topics, found by themselves, one key per topic

- **Status:** Accepted (1.7)
- **Date:** 2026-10-18

## Context

Open topics are added by hand and readable by anyone on the broker. Many
devices publish to a public broker, and adding every topic by hand does not
scale to a fleet. We wanted devices that a user can flash and plug in, whose
data appears by itself and cannot be read, forged or replayed by others on the
broker. The heartbeat receiver (ADR 0002) solves this for node presence with
one fleet key; data topics need a key per device so one leaked device does not
expose the others.

The devices are small: ESP32 with the Arduino core, MicroPython builds without
AES-GCM, and Node-RED.

## Decision

- **Protocol sst1** ([SECURE-TOPICS.md](../SECURE-TOPICS.md#the-protocol-sst1)):
  AES-256-CTR, then HMAC-SHA256 over a domain tag, the topic, the key id, the
  time, the nonce and the ciphertext (encrypt then MAC, keys derived per
  purpose). Only AES, HMAC and SHA-256 are needed. Time within 5 minutes,
  nonces remembered for 11 minutes.
- **One key per topic, issued by SenseHive.** Generated in bulk (1 to 100),
  shown once, downloadable as CSV. A key is pending for 24 hours, becomes
  active and bound to its topic on its first valid message, and otherwise
  expires. Expired and revoked keys lose their secret; key ids are never
  issued again. Showing a key again needs the user's password.
- **Discovery under one root** (`sensehive/secure/#`): a valid message on a new
  topic adds the topic. Nothing else can add one.
- **Stored like open topics** (the same table per topic, history, CSV,
  retention), marked secure in the topics table. Open topics under the root
  are refused, and messages under the root never reach open topic handling.
- **Status from a signed message:** a device names its plain last will topic
  in `sensehive_lwt`; it is set once and not moved by later messages.
- **Keys encrypted at rest** with a key derived from the app's `SECRET_KEY`.
- **Errors are fixed texts by code**, never an exception's own text.

## Alternatives considered

- **AES-GCM:** missing on common MicroPython builds and awkward on small
  devices; CTR with HMAC gives the same guarantees here.
- **Broker ACLs or TLS client certificates:** protect the broker, not the data
  on a shared or public broker, and need broker access we often do not have.
- **One fleet key (as heartbeats):** one leaked device would expose the whole
  fleet's data.
- **Public key signatures (Ed25519):** better for enrollment, but not in
  MicroPython or the Arduino core without extra libraries. Planned for the
  heartbeat agent's enrollment, not for data.

## Consequences

- Flash a device with a key id and key and its topic appears by itself; one
  lost device is revoked alone.
- The broker still sees topic names, key ids, times and sizes.
- Devices need a correct clock (NTP).
- Moving SenseHive without its `SECRET_KEY` makes stored keys unreadable;
  devices keep working only if their keys are issued again.
- Tests: `tests/test_secure.py` (protocol, hostile envelopes, key life, API,
  isolation, every device example), `tests/test_integration.py` (a real
  broker), the browser UI test.
