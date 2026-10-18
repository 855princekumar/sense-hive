"""Publish to a SenseHive secure topic from Python (paho-mqtt and cryptography).

    pip install paho-mqtt cryptography
    python secure_publish.py --broker 192.168.1.10 --kid <key id> --key <64 hex> \\
        --topic sensehive/secure/site-a/pump-1 --payload '{"flow": 12.5}'

The key id and key come from SenseHive (Secure topics, Generate keys). The
topic must be under SenseHive's secure root (default sensehive/secure/). The
first valid message binds the key to its topic; use one key per topic.
Protocol: docs/SECURE-TOPICS.md. The device clock must be right (NTP): a
message more than 5 minutes off is refused.
"""
import argparse
import base64
import hashlib
import hmac
import json
import os
import time

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


def seal(key: bytes, kid: str, topic: str, payload: bytes, t=None) -> bytes:
    enc_key = hmac.new(key, b'sst1 enc', hashlib.sha256).digest()
    mac_key = hmac.new(key, b'sst1 mac', hashlib.sha256).digest()
    nonce = os.urandom(16)
    t = int(time.time() if t is None else t)
    enc = Cipher(algorithms.AES(enc_key), modes.CTR(nonce)).encryptor()
    ct = enc.update(payload) + enc.finalize()
    signed = b'\x00'.join((b'sst1', topic.encode(), kid.encode(), str(t).encode(), nonce)) + ct
    tag = hmac.new(mac_key, signed, hashlib.sha256).digest()[:16]
    b64 = lambda b: base64.b64encode(b).decode()   # noqa: E731
    return json.dumps({'v': 1, 'k': kid, 't': t, 'i': b64(nonce), 'c': b64(ct), 'm': b64(tag)},
                      separators=(',', ':')).encode()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--broker', required=True)
    ap.add_argument('--port', type=int, default=1883)
    ap.add_argument('--username')
    ap.add_argument('--password')
    ap.add_argument('--tls', action='store_true')
    ap.add_argument('--kid', required=True)
    ap.add_argument('--key', required=True, help='64 hex characters')
    ap.add_argument('--topic', required=True)
    ap.add_argument('--payload', required=True)
    a = ap.parse_args()
    import paho.mqtt.client as mqtt
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2) if hasattr(mqtt, 'CallbackAPIVersion') else mqtt.Client()
    if a.username:
        client.username_pw_set(a.username, a.password)
    if a.tls:
        client.tls_set()
    client.connect(a.broker, a.port, 30)
    client.loop_start()
    info = client.publish(a.topic, seal(bytes.fromhex(a.key), a.kid, a.topic, a.payload.encode()), qos=1)
    info.wait_for_publish(10)
    client.loop_stop()
    client.disconnect()
    print('sent')


if __name__ == '__main__':
    main()
