# syntax=docker/dockerfile:1
# The public SenseHive demo: SenseHive from this repository, a private broker,
# real heartbeat agents, an emulated PowerPulse node and the emulated fleet.
# Build from the repository root:  docker build -f demo/Dockerfile -t sensehive-demo .
FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends mosquitto \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --system --no-create-home --shell /usr/sbin/nologin demo

WORKDIR /app
COPY version-1.0/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt "PyYAML>=6,<7"

COPY version-1.0/app.py version-1.0/heartbeat.py version-1.0/heartbeat_protocol.py version-1.0/secure.py \
     version-1.0/security.py version-1.0/demo_fleet.py ./
COPY version-1.0/templates/ templates/
COPY version-1.0/static/ static/

# The heartbeat agent, unchanged, from its own repository
ARG AGENT_REF=v1.3.0
ADD https://github.com/855princekumar/mqtt-heartbeat-service.git#${AGENT_REF} /demo/agent

COPY demo/run.py demo/serve.py demo/powerpulse.py /demo/

EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('PORT', '5000'))" || exit 1

CMD ["python", "/demo/run.py"]
