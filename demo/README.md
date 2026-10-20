# The public demo

A SenseHive anyone can open, with something real to look at: one container,
nothing shared with any other installation.

| What | How |
| ---- | --- |
| SenseHive | from this repository, unchanged, behind a small guard (`serve.py`) |
| A broker | Mosquitto on `127.0.0.1` inside the container, a new random login at every start |
| An emulated fleet | `sensehive-demo`: six devices with telemetry and a last will |
| Heartbeats | four real [heartbeat agents](https://github.com/855princekumar/mqtt-heartbeat-service) (v1.3.0, set up with join tokens); `pi-node-02` crashes now and then and comes back |
| PowerPulse | an emulated PowerPulse node: retained status, last will, and its beacon sealed on a secure topic, so SenseHive finds it by itself; the plug is pulled every few minutes |

Sign in as `admin` / `admin123` (shown on the sign-in page). Visitors may look
at everything, add a few topics and make join tokens. The guard refuses what
would spoil the demo for the next visitor: the password, the broker, retention,
editing or deleting nodes, the recycle bin and the secure keys. Wrong passwords
never reach the sign-in limiter, so nobody can lock the demo for everyone.

Every start is fresh: a new database, heartbeat master key, secure key and
broker login. Nothing is kept, and no credential of any real installation is in
the image.

## Run it

```bash
docker run -p 10000:10000 -e PORT=10000 devprincekumar/sense-hive:demo
```

Open http://localhost:10000. It is ready in about 20 seconds and uses about
150 MB of memory, so a 512 MB free host is enough.

## Build and test it

```bash
docker build -f demo/Dockerfile -t sensehive-demo .
docker run -d --name demo -p 10000:10000 -e PORT=10000 --memory 512m sensehive-demo
python tools/demo_e2e.py --url http://127.0.0.1:10000
```

CI builds and checks it on every change (the guard, the fleet, the four
agents, PowerPulse on its secure topic, a browser on a laptop and a phone).
Every push to `main` publishes `devprincekumar/sense-hive:demo`, and calls the
host's deploy hook when the `DEMO_DEPLOY_HOOK` secret is set.
