import paho.mqtt.client as mqtt
import json
import time
import random

# ==============================
# MQTT CONFIG
# ==============================
BROKER = "broker.hivemq.com"
PORT = 1883
TOPIC = "test-sensehive"

# ==============================
# CALLBACKS
# ==============================
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✅ Connected to HiveMQ broker")
        client.subscribe(TOPIC)
        print(f"📡 Subscribed to topic: {TOPIC}")
    else:
        print(f"❌ Connection failed with code {rc}")

def on_message(client, userdata, msg):
    print(f"\n📥 Received Message from {msg.topic}")
    print(msg.payload.decode())

# ==============================
# CLIENT SETUP
# ==============================
client = mqtt.Client()

client.on_connect = on_connect
client.on_message = on_message

# ==============================
# CONNECT
# ==============================
client.connect(BROKER, PORT, 60)

# Start loop in background
client.loop_start()

# ==============================
# PUBLISH LOOP
# ==============================
try:
    while True:
        # Dummy IoT payload (SenseHive style)
        payload = {
            "device_id": "sensehive_node_01",
            "timestamp": int(time.time()),
            "temperature": round(random.uniform(20, 35), 2),
            "humidity": round(random.uniform(40, 80), 2),
            "status": "active"
        }

        client.publish(TOPIC, json.dumps(payload))

        print("\n📤 Published:")
        print(json.dumps(payload, indent=2))

        time.sleep(5)

except KeyboardInterrupt:
    print("\n🛑 Stopping...")
    client.loop_stop()
    client.disconnect()