# onkyo2mqtt-py3

A Python 3 MQTT bridge for Onkyo AV receivers, allowing control and status monitoring via MQTT.

Inspired by [onkyo2mqtt](https://github.com/owagner/onkyo2mqtt) by Oliver Wagner. Rewritten for Python 3 and updated to use the modern paho-mqtt API.

Uses the [onkyo-eiscp](https://github.com/kskok68/onkyo-eiscp) library (forked from [mitchcapper/onkyo-eiscp](https://github.com/mitchcapper/onkyo-eiscp)) for communication with Onkyo receivers.

## Features

- Automatic discovery of Onkyo receivers on the local network, or connect directly via IP
- Control your receiver via MQTT commands
- Receiver status published to MQTT topics automatically
- Configurable via environment variables
- Docker support with pre-built images on GitHub Container Registry

## Quick Start

Pull the pre-built image from GitHub Container Registry:

```bash
docker pull ghcr.io/kskok68/onkyo2mqtt-py3:latest
```

Run the container:

```bash
docker run -d \
  --name onkyo2mqtt \
  --network host \
  -e MQTT_HOST=192.168.0.x \
  -e MQTT_PORT=1883 \
  -e MQTT_TOPIC=onkyo \
  -e ONKYO_HOST=auto \
  ghcr.io/kskok68/onkyo2mqtt-py3:latest
```

## Configuration

All configuration is via environment variables:

| Variable | Default | Description |
|---|---|---|
| `MQTT_HOST` | `localhost` | MQTT broker IP address |
| `MQTT_PORT` | `1883` | MQTT broker port |
| `MQTT_USER` | _(none)_ | MQTT username (optional) |
| `MQTT_PASS` | _(none)_ | MQTT password (optional) |
| `MQTT_TOPIC` | `onkyo` | MQTT topic prefix |
| `ONKYO_HOST` | `auto` | Receiver IP, or `auto` for discovery |
| `ONKYO_PORT` | `60128` | Receiver port |

> **Note:** `--network host` is required when using `ONKYO_HOST=auto` for receiver discovery. If you specify a static IP for `ONKYO_HOST` this is not strictly required.

## MQTT Topics

### Status (published by the bridge)

```
onkyo/status/power
onkyo/status/master-volume
onkyo/status/input-selector
onkyo/connected
```

### Commands (send to the bridge)

Raw ISCP command:
```
onkyo/command  →  PWR01
```

Friendly command:
```
onkyo/set/power  →  on
onkyo/set/master-volume  →  45
onkyo/set/input-selector  →  hdmi1
```

## Building from Source

```bash
git clone https://github.com/kskok68/onkyo2mqtt.git
cd onkyo2mqtt
docker build -t onkyo2mqtt .
```

## Unraid

This container works well on Unraid. Set the network type to **Host** to allow receiver auto-discovery, and set `MQTT_HOST` to your Unraid server's LAN IP address if your MQTT broker is running as another container.

## License

MIT
