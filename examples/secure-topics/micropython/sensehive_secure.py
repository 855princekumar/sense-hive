# Publish to a SenseHive secure topic from MicroPython (ESP32, Raspberry Pi Pico W).
#
# Needs a MicroPython build with cryptolib AES CTR mode (most ESP32 builds),
# umqtt.simple, and the clock set by NTP (ntptime.settime()): a message more
# than 5 minutes off is refused. Protocol: docs/SECURE-TOPICS.md.
#
#   from sensehive_secure import seal
#   msg = seal(KEY, KID, TOPIC, b'{"temp": 21.5}')
#   mqtt.publish(TOPIC, msg)
#
# KEY is the 32-byte key (bytes.fromhex("...64 hex...")), KID the 16-hex key id.
import binascii
import hashlib
import json
import os
import time

import cryptolib

MODE_CTR = 6
EPOCH_OFFSET = 946684800 if time.gmtime(0)[0] == 2000 else 0   # MicroPython ports that count from 2000


def _hmac_sha256(key, msg):
    if len(key) > 64:
        key = hashlib.sha256(key).digest()
    key = key + b'\x00' * (64 - len(key))
    inner = hashlib.sha256(bytes(b ^ 0x36 for b in key) + msg).digest()
    return hashlib.sha256(bytes(b ^ 0x5C for b in key) + inner).digest()


def _b64(b):
    return binascii.b2a_base64(b).decode().strip()


def seal(key, kid, topic, payload, t=None):
    enc_key = _hmac_sha256(key, b'sst1 enc')
    mac_key = _hmac_sha256(key, b'sst1 mac')
    nonce = os.urandom(16)
    if t is None:
        t = int(time.time()) + EPOCH_OFFSET
    ct = cryptolib.aes(enc_key, MODE_CTR, nonce).encrypt(payload)
    signed = b'sst1\x00' + topic.encode() + b'\x00' + kid.encode() + b'\x00' + str(t).encode() + b'\x00' + nonce + ct
    tag = _hmac_sha256(mac_key, signed)[:16]
    return json.dumps({'v': 1, 'k': kid, 't': t, 'i': _b64(nonce), 'c': _b64(ct), 'm': _b64(tag)})
