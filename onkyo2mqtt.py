#!/usr/bin/env python3
"""
Onkyo to MQTT Bridge
Bridges Onkyo receivers to MQTT using the onkyo-eiscp library
Based on onkyo2mqtt by Oliver Wagner
"""

import os
import sys
import time
import json
import logging
import threading
import paho.mqtt.client as mqtt
import eiscp
import eiscp.core

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('onkyo2mqtt')

# Configuration from environment variables
MQTT_HOST = os.getenv('MQTT_HOST', 'localhost')
MQTT_PORT = int(os.getenv('MQTT_PORT', '1883'))
MQTT_USER = os.getenv('MQTT_USER', None)
MQTT_PASS = os.getenv('MQTT_PASS', None)
MQTT_TOPIC = os.getenv('MQTT_TOPIC', 'onkyo')
ONKYO_HOST = os.getenv('ONKYO_HOST', 'auto')
ONKYO_PORT = int(os.getenv('ONKYO_PORT', '60128'))
RECONNECT_DELAY = int(os.getenv('RECONNECT_DELAY', '5'))

# Ensure topic ends with /
topic = MQTT_TOPIC
if not topic.endswith("/"):
    topic += "/"

lastSend = 0
receiver = None
mqc = None

# Guards access to the shared `receiver` object across the MQTT network
# thread (sendavr, via msghandler) and the main thread (the receiver read
# loop), since a reconnect can happen while either side is touching it.
receiver_lock = threading.Lock()


def connect_receiver():
    """
    (Re)connect to the Onkyo receiver.

    Retries forever with a fixed delay instead of giving up, so that a
    receiver that is powered off, unplugged, or unreachable (e.g. during a
    power outage while this container stays up on a UPS) is picked back up
    automatically as soon as it's reachable again, with no container
    restart required.
    """
    global receiver
    while True:
        try:
            if ONKYO_HOST != 'auto':
                logger.info(f'Connecting to Onkyo at {ONKYO_HOST}:{ONKYO_PORT}')
                new_receiver = eiscp.eISCP(ONKYO_HOST, ONKYO_PORT)
            else:
                logger.info('Starting auto-discovery of Onkyo AVRs')
                receivers = eiscp.eISCP.discover()
                for r in receivers:
                    logger.info(f"Discovered {r.info['model_name']} at {r.host}:{r.port}")
                if len(receivers) == 0:
                    raise RuntimeError("No AVRs discovered")
                if len(receivers) != 1:
                    logger.warning("More than one AVR discovered, using first one")
                new_receiver = receivers[0]
                logger.info(f'Using AVR at {new_receiver.host}:{new_receiver.port}')

            with receiver_lock:
                receiver = new_receiver
            logger.info("Receiver connection established")
            return
        except Exception as e:
            logger.error(f"Failed to connect to receiver, retrying in {RECONNECT_DELAY}s: {e}")
            with receiver_lock:
                receiver = None
            time.sleep(RECONNECT_DELAY)


def disconnect_receiver():
    """Tear down a dead receiver connection so it can be cleanly reopened."""
    global receiver
    with receiver_lock:
        old = receiver
        receiver = None
    if old is not None:
        try:
            old.disconnect()
        except Exception:
            pass


def query_initial_status():
    """Ask the receiver for its current power/volume/input state."""
    for icmd in ("PWRQSTN", "MVLQSTN", "SLIQSTN"):
        try:
            sendavr(icmd)
            time.sleep(0.1)
        except Exception:
            pass


def sendavr(cmd):
    """Send command to AVR with rate limiting. Fails safe if disconnected."""
    global lastSend
    with receiver_lock:
        r = receiver
    if r is None:
        logger.warning(f"Receiver not connected, dropping command: {cmd}")
        return
    now = time.time()
    if now - lastSend < 0.05:
        time.sleep(0.05 - (now - lastSend))
    try:
        r.send(cmd)
        lastSend = time.time()
        logger.info(f"Sent command: {cmd}")
    except Exception as e:
        logger.error(f"Failed to send command '{cmd}': {e}")
        disconnect_receiver()


def msghandler(client, userdata, msg):
    """Handle incoming MQTT messages"""
    try:
        global topic
        if msg.retain:
            return

        mytopic = msg.topic[len(topic):]
        payload = msg.payload.decode('utf-8')

        if mytopic == "command":
            # Raw command mode
            sendavr(payload)
        elif mytopic.startswith("set/"):
            # Friendly command mode - convert to ISCP
            command_name = mytopic[4:]
            llcmd = eiscp.core.command_to_iscp(f"{command_name} {payload}")
            sendavr(llcmd)
        elif mytopic.startswith("command/"):
            # Alternative friendly command mode
            command_name = mytopic[8:]
            llcmd = eiscp.core.command_to_iscp(f"{command_name} {payload}")
            sendavr(llcmd)
    except Exception as e:
        logger.error(f"Error processing message: {e}")


def connecthandler(client, userdata, flags, rc, properties=None):
    """Handle MQTT connection (paho-mqtt v2 callback signature)"""
    logger.info(f"Connected to MQTT broker with rc={rc}")
    client.subscribe(topic + "set/#", qos=0)
    client.subscribe(topic + "command", qos=0)
    client.subscribe(topic + "command/#", qos=0)
    client.publish(topic + "connected", 2, qos=1, retain=True)


def disconnecthandler(client, userdata, disconnect_flags, reason_code, properties=None):
    """
    Handle MQTT disconnection.

    paho-mqtt 2.x's CallbackAPIVersion.VERSION2 calls on_disconnect with
    5 positional arguments (client, userdata, disconnect_flags,
    reason_code, properties) - the old 3-arg (client, userdata, rc)
    signature raises a TypeError as soon as a real disconnect happens.
    """
    logger.warning(f"Disconnected from MQTT broker: {reason_code}")


def publish(suffix, val, raw):
    """Publish status to MQTT"""
    global topic, mqc
    mqc.publish(topic + "status/" + suffix, str(val), qos=0, retain=True)
    logger.info(f"Published to MQTT: {topic}status/{suffix} = {val}")


# Setup MQTT client
logger.info(f'Starting onkyo2mqtt with topic prefix "{topic}"')
mqc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
mqc.on_message = msghandler
mqc.on_connect = connecthandler
mqc.on_disconnect = disconnecthandler

if MQTT_USER and MQTT_PASS:
    mqc.username_pw_set(MQTT_USER, MQTT_PASS)

mqc.will_set(topic + "connected", 0, qos=2, retain=True)
mqc.connect(MQTT_HOST, MQTT_PORT, 60)
mqc.publish(topic + "connected", 1, qos=1, retain=True)

# Connect to Onkyo receiver (retries forever until it succeeds)
connect_receiver()

# Query initial values
logger.info('Querying initial status')
query_initial_status()

# Start MQTT loop
mqc.loop_start()

# Main loop - continuously check for messages from receiver
logger.info('Starting main loop - listening for receiver messages')
while True:
    with receiver_lock:
        r = receiver

    if r is None:
        # Connection was dropped (by sendavr, or by a previous iteration
        # of this loop) - reconnect before doing anything else. This
        # blocks/retries internally, so once it returns we have a live
        # connection again.
        connect_receiver()
        query_initial_status()
        continue

    try:
        # Get message from receiver with 1 second timeout
        msg = r.get(1)
        if msg is not None:
            try:
                # Parse the ISCP message to friendly format
                parsed = eiscp.core.iscp_to_command(msg)

                # Handle the parsed command
                # Either part of the parsed command can be a list
                if isinstance(parsed[1], str) or isinstance(parsed[1], int):
                    val = parsed[1]
                else:
                    val = parsed[1][0]

                if isinstance(parsed[0], str):
                    publish(parsed[0], val, msg)
                else:
                    # Multiple command names (aliases)
                    for pp in parsed[0]:
                        publish(pp, val, msg)
            except Exception as e:
                # Fallback - publish raw message
                logger.debug(f"Could not parse message, publishing raw: {e}")
                if len(msg) >= 3:
                    publish(msg[:3], msg[3:], msg)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        mqc.publish(topic + "connected", 0, qos=1, retain=True)
        mqc.disconnect()
        disconnect_receiver()
        break
    except Exception as e:
        logger.error(f"Receiver connection lost, will attempt to reconnect: {e}")
        disconnect_receiver()
        # Loop back around - the `r is None` branch above will handle
        # reconnecting before we touch the receiver again.
