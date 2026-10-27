# ==============================================================
# CCPS LAB: ULTRASONIC SENSOR + LED + TCP CLIENT/SERVER
# Standalone version: NO NODE-RED REQUIRED
#
# HARDWARE:
#   HC-SR04 TRIG -> GPIO 18 (BCM; physical pin 12)
#   HC-SR04 ECHO -> GPIO 24 (BCM; physical pin 18)
#   LED          -> GPIO 17 (BCM; physical pin 11)
#
# TCP SERVER:
#   Listens on 127.0.0.1:5001
#   Receives sensor readings and displays them.
#
# TCP CLIENT:
#   Measures distance, controls LED, sends readings to server.
#
# ==============================================================
#
# WIRING:
#   HC-SR04 VCC  -> Pi 5V (physical pin 2)
#   HC-SR04 GND  -> Pi GND (physical pin 6)
#   HC-SR04 TRIG -> GPIO 18 (physical pin 12)
#   HC-SR04 ECHO -> GPIO 24 (physical pin 18), THROUGH VOLTAGE DIVIDER
#
#   LED long leg  -> GPIO 17 through a 220-330 ohm resistor
#   LED short leg -> GND
#
# WARNING: Pi GPIO is 3.3V tolerant. Never connect the HC-SR04's
# potentially 5V ECHO output directly to GPIO 24.
#
# ==============================================================
#
# SETUP:
# 1. Open a terminal on the Raspberry Pi.
# 2. Find its IP if needed: hostname -I
#    This program uses 127.0.0.1 because client and server run
#    on the SAME Pi. No IP lookup is required.
#
# 3. Install GPIO support if available for your Pi/OS:
#       sudo apt update
#       sudo apt install -y python3-rpi.gpio
#
# 4. Save this code as:
#       ultrasonic_tcp_standalone.py
#
# 5. Run:
#       python3 ultrasonic_tcp_standalone.py
#
# 6. Stop with Ctrl+C.
#
# NOTE: RPi.GPIO is not supported natively on every Raspberry Pi
# model/OS combination, particularly some Pi 5 setups.
# ==============================================================

import socket
import threading
import time
import RPi.GPIO as GPIO

# -------------------- CONFIGURATION ----------------------------

TRIG = 18
ECHO = 24
LED = 17

THRESHOLD_CM = 20.0

SERVER_IP = "127.0.0.1"
SERVER_PORT = 5001

# Event used to stop both threads cleanly.
stop_event = threading.Event()

# ---------------------------------------------------------------


def setup_gpio():
    """Configure the Raspberry Pi GPIO pins."""

    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    GPIO.setup(TRIG, GPIO.OUT)
    GPIO.setup(ECHO, GPIO.IN)
    GPIO.setup(LED, GPIO.OUT)

    GPIO.output(TRIG, GPIO.LOW)
    GPIO.output(LED, GPIO.LOW)


def read_distance():
    """Measure distance in centimetres using the HC-SR04."""

    GPIO.output(TRIG, GPIO.LOW)
    time.sleep(0.0002)

    # Send a 10-microsecond trigger pulse.
    GPIO.output(TRIG, GPIO.HIGH)
    time.sleep(0.00001)
    GPIO.output(TRIG, GPIO.LOW)

    # Wait for the echo pulse to begin, with timeout.
    timeout = time.monotonic() + 0.03

    while GPIO.input(ECHO) == GPIO.LOW:
        if time.monotonic() > timeout:
            return None

    start = time.monotonic()

    # Wait for the echo pulse to finish, with timeout.
    timeout = time.monotonic() + 0.03

    while GPIO.input(ECHO) == GPIO.HIGH:
        if time.monotonic() > timeout:
            return None

    end = time.monotonic()

    # Distance (cm) = echo duration (seconds) * 17150.
    return round((end - start) * 17150, 2)


def tcp_server():
    """
    TCP SERVER:
    Waits for the client, receives newline-delimited sensor
    readings, and prints each reading.
    """

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((SERVER_IP, SERVER_PORT))
        server.listen(1)
        server.settimeout(1.0)

        print(f"[SERVER] Listening on {SERVER_IP}:{SERVER_PORT}")

        while not stop_event.is_set():
            try:
                conn, address = server.accept()
                break
            except socket.timeout:
                continue
        else:
            return

        with conn:
            print(f"[SERVER] Client connected: {address}")
            conn.settimeout(1.0)
            buffer = ""

            while not stop_event.is_set():
                try:
                    data = conn.recv(1024)
                    if not data:
                        print("[SERVER] Client disconnected.")
                        break

                    buffer += data.decode("utf-8")

                    # TCP is a byte stream; split complete lines.
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()

                        if line:
                            print(f"[SERVER] Received distance: {line} cm")

                except socket.timeout:
                    continue
                except (ConnectionError, OSError) as error:
                    if not stop_event.is_set():
                        print("[SERVER] Connection error:", error)
                    break


def tcp_client():
    """
    TCP CLIENT:
    Reads the ultrasonic sensor, switches the LED according
    to the 20 cm threshold, and sends each reading to the server.
    """

    # Wait briefly for the server thread to start listening.
    time.sleep(0.5)

    try:
        with socket.create_connection(
            (SERVER_IP, SERVER_PORT), timeout=5
        ) as client:

            print(f"[CLIENT] Connected to {SERVER_IP}:{SERVER_PORT}")

            while not stop_event.is_set():
                distance = read_distance()

                if distance is None:
                    print("[CLIENT] No echo received; check sensor/wiring.")
                    GPIO.output(LED, GPIO.LOW)
                    time.sleep(0.5)
                    continue

                # Turn LED ON when an object is 20 cm or closer.
                if distance <= THRESHOLD_CM:
                    GPIO.output(LED, GPIO.HIGH)
                    led_status = "ON"
                else:
                    GPIO.output(LED, GPIO.LOW)
                    led_status = "OFF"

                print(
                    f"[CLIENT] Distance: {distance:.2f} cm | "
                    f"LED: {led_status}"
                )

                # Send one newline-terminated reading.
                message = f"{distance:.2f}\n"
                client.sendall(message.encode("utf-8"))

                time.sleep(0.5)

    except ConnectionRefusedError:
        print("[CLIENT] Connection refused: is the server running?")
    except OSError as error:
        if not stop_event.is_set():
            print("[CLIENT] Socket error:", error)


def main():
    setup_gpio()

    # Run server and client concurrently.
    server_thread = threading.Thread(target=tcp_server, daemon=True)
    client_thread = threading.Thread(target=tcp_client, daemon=True)

    try:
        server_thread.start()
        client_thread.start()

        while client_thread.is_alive():
            client_thread.join(timeout=0.5)

    except KeyboardInterrupt:
        print("\nStopping experiment...")

    finally:
        stop_event.set()
        GPIO.output(LED, GPIO.LOW)
        GPIO.cleanup()
        print("GPIO cleaned up. Experiment stopped.")


if __name__ == "__main__":
    main()
