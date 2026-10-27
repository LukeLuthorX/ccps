# ==============================================================
# CCPS LAB EXPERIMENT:
# Raspberry Pi + HC-SR04 Ultrasonic Sensor + LED + TCP + Node-RED
#
# EVERYTHING runs on the Raspberry Pi. No Windows computer needed.
#
# ARCHITECTURE:
# HC-SR04 -> Python TCP CLIENT -> TCP SERVER (same Pi, port 5000)
#                                      |
#                                      v
#                                Node-RED TCP IN
#                                      |
#                                      v
#                              Function -> Dashboard Gauge
#
# GPIO PINS (BCM numbering, as in the lab cheatsheet):
#   HC-SR04 TRIG -> GPIO 18 (physical pin 12)
#   HC-SR04 ECHO -> GPIO 24 (physical pin 18, via voltage divider)
#   LED           -> GPIO 17 (physical pin 11)
#
# LED turns ON when distance <= 20 cm.
#
# ==============================================================
#
# STEP 1: WIRING
#
# HC-SR04 VCC  -> Pi 5V (physical pin 2)
# HC-SR04 GND  -> Pi GND (physical pin 6)
# HC-SR04 TRIG -> GPIO 18 (physical pin 12)
# HC-SR04 ECHO -> GPIO 24 (physical pin 18) THROUGH A VOLTAGE DIVIDER
#
# IMPORTANT: Pi GPIO is 3.3V tolerant. HC-SR04 ECHO may output 5V.
# Use a voltage divider, e.g. 1k resistor from ECHO to GPIO24 and
# 2k resistor from GPIO24 to GND. Do NOT connect ECHO directly.
#
# LED long leg (anode)  -> GPIO 17 (physical pin 11) through resistor
# LED short leg         -> GND
#
# ==============================================================
#
# STEP 2: FIND THE RASPBERRY PI IP ADDRESS (OPTIONAL)
#
# Open a terminal on the Pi and run:
#   hostname -I
#
# Example output: 192.168.1.25
#
# Since the TCP client and server both run on THIS SAME Pi,
# we use 127.0.0.1 (localhost). No IP address lookup is needed.
#
# ==============================================================
#
# STEP 3: INSTALL REQUIRED SOFTWARE
#
# On Raspberry Pi OS, run in a terminal:
#
#   sudo apt update
#   sudo apt install -y python3-gpiozero python3-rpi.gpio
#
# Depending on the Pi model/OS, GPIO backend support may differ.
# This example uses RPi.GPIO and is intended for compatible Pi setups.
#
# Save this entire file as:
#   ultrasonic_tcp.py
#
# Run with:
#   python3 ultrasonic_tcp.py
#
# ==============================================================
#
# STEP 4: CONFIGURE NODE-RED
#
# Start Node-RED:
#   node-red
#
# Open the editor on the Pi browser:
#   http://localhost:1880
#
# Build this flow:
#
#   [TCP In] ---> [Function] ---> [Gauge]
#
# TCP IN configuration:
#   Type/mode: Listen on
#   Port:      5000
#   Output:    UTF-8 string
#   Delimiter: newline (\n), so each reading is a separate message
#
# FUNCTION node code:
#
#   msg.payload = Number(msg.payload.trim());
#   return msg;
#
# GAUGE configuration:
#   Label: Distance
#   Units: cm
#   Minimum: 0
#   Maximum: 400
#   Assign it to a Dashboard tab and group.
#
# Click Done, then Deploy.
# Open the classic dashboard at:
#   http://localhost:1880/ui
#
# If node-red-dashboard is missing, install it via:
# Menu -> Manage palette -> Install -> node-red-dashboard
#
# IMPORTANT: Start Node-RED and deploy the TCP In flow BEFORE running
# this Python program, so the TCP server is listening on port 5000.
#
# ==============================================================

import socket
import time
import RPi.GPIO as GPIO

# -------------------- CONFIGURATION ----------------------------

TRIG = 18
ECHO = 24
LED = 17

THRESHOLD_CM = 20.0

# Client and server run on the same Raspberry Pi.
SERVER_IP = "127.0.0.1"
SERVER_PORT = 5000

# ---------------------------------------------------------------

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

GPIO.setup(TRIG, GPIO.OUT)
GPIO.setup(ECHO, GPIO.IN)
GPIO.setup(LED, GPIO.OUT)

GPIO.output(TRIG, GPIO.LOW)
GPIO.output(LED, GPIO.LOW)


def read_distance():
    """Measure HC-SR04 distance in centimetres; return None on timeout."""

    # Ensure the trigger starts LOW.
    GPIO.output(TRIG, GPIO.LOW)
    time.sleep(0.0002)

    # Send a 10-microsecond trigger pulse.
    GPIO.output(TRIG, GPIO.HIGH)
    time.sleep(0.00001)
    GPIO.output(TRIG, GPIO.LOW)

    # Wait for the echo pulse to start, with a timeout.
    timeout = time.monotonic() + 0.03

    while GPIO.input(ECHO) == GPIO.LOW:
        if time.monotonic() > timeout:
            return None

    pulse_start = time.monotonic()

    # Wait for the echo pulse to finish, with a timeout.
    timeout = time.monotonic() + 0.03

    while GPIO.input(ECHO) == GPIO.HIGH:
        if time.monotonic() > timeout:
            return None

    pulse_end = time.monotonic()

    # Sound travels to the object and back.
    # Distance (cm) = duration (seconds) * 17150.
    duration = pulse_end - pulse_start
    distance = duration * 17150

    return round(distance, 2)


def run_tcp_server():
    """
    TCP SERVER:
    Listens on port 5000 and prints incoming readings.
    Node-RED independently listens on its own TCP In node on port 5000,
    so those two listeners cannot use the same port simultaneously.

    To avoid that port conflict, the Python server below uses port 5001.
    The client sends data to this Python server; it prints the readings.
    For the Node-RED dashboard, configure TCP In to listen on port 5000
    and change the client to send directly to Node-RED instead.
    """
    pass


def main():
    """
    TCP CLIENT:
    Connects to Node-RED's TCP In node on port 5000.
    Node-RED is the TCP server for dashboard delivery.
    """

    print("Connecting to Node-RED TCP server...")
    print("Server IP:", SERVER_IP)
    print("Server port:", SERVER_PORT)
    print("Press Ctrl+C to stop.")

    try:
        with socket.create_connection(
            (SERVER_IP, SERVER_PORT), timeout=10
        ) as client:

            print("Connected to Node-RED TCP server.")

            while True:
                distance = read_distance()

                if distance is None:
                    print("Sensor timeout; no valid echo.")
                    GPIO.output(LED, GPIO.LOW)
                    time.sleep(0.5)
                    continue

                # LED ON if an object is 20 cm away or closer.
                if distance <= THRESHOLD_CM:
                    GPIO.output(LED, GPIO.HIGH)
                    led_status = "ON"
                else:
                    GPIO.output(LED, GPIO.LOW)
                    led_status = "OFF"

                print(
                    f"Distance: {distance:.2f} cm | "
                    f"LED: {led_status}"
                )

                # Send newline-delimited distance to Node-RED.
                # The newline lets TCP In separate individual readings.
                message = f"{distance:.2f}\n"
                client.sendall(message.encode("utf-8"))

                time.sleep(0.5)

    except ConnectionRefusedError:
        print("Connection refused.")
        print("Check that Node-RED is running and TCP In is deployed.")
    except OSError as error:
        print("Network/socket error:", error)
    finally:
        GPIO.output(LED, GPIO.LOW)
        GPIO.cleanup()
        print("GPIO cleaned up; program stopped.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopping experiment...")
    finally:
        GPIO.cleanup()
