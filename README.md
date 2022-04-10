# Toshiba-AC-mqtt
Toshiba AC to MQTT bridge

**Work in progress: Expect some work to make it work.**

# Usage
- Clone repository.
- Recommended: Prepare a Python venv.
- Install requirements: `pip install azure-iot-device aiohttp asyncio-mqtt`
- Change the configuration section in `toshiba_ac_to_mqtt.py` (lines 32 to 39) to whatever makes sense for your setup.
- Run the bridge: `python toshiba_ac_to_mqtt.py`
- If you want, use the container file to make a container. It will probably only work in podman, but you can try Docker.
- If you want, use the systemd service unit file to start a auto-restarting service. This will work only in podman, not in Docker.

# MQTT (if defaults are not changed)
## Publishes
- `ac/status`: Publishes `online` when everything is connected, otherwise `offline`.
- `ac/[dev_name]/status`: Published whenever the status changed or once per hour.
  - Updates contain only the changed values.
  - Regular status update contains all values.
- `ac/[dev_name]/power`: Published every 10 minutes. Average power during the last 10 minutes in W.

## Subscribes (listens)
- `ac/[dev_name]/cmd`: Send commands to the ACs. Uses same format as the status updates.
  - TODO: Full documentation of all values.

# Under the hood
- Status is updated every 5 minutes and whenever it is send by the server.
- Power is updated every 10 minutes.

# Problem Handling
This bridge has only very limited error handling: Whenever something goes wrong, it will crash.
It will crash gracefully, closing all connections that did not fail before.
It will also dump a lot of exceptions (all it could find and most of them more then once) to help you debug the problem.
If you expect problems (you should) you need to wrap the file in something (container, systemd service, or both) that auto-restarts it as needed.
A container file (podman) and a sample systemd service unit file (also podman) are included.

# Limitations
- Hardcoded MQTT server name.
- Supports only MQTT servers without authentication.
- Hardcode Toshiba username and password.
- Sample systemd works only for rootless podman, probably not for Docker.