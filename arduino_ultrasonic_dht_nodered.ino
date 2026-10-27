/*
===============================================================================
CCPS LAB PRACTICAL: ARDUINO + HC-SR04 + DHT11/DHT22 + LED + NODE-RED DASHBOARD
===============================================================================

WHAT THIS DOES
- Reads distance from an HC-SR04 ultrasonic sensor.
- Reads temperature and humidity from a DHT11 or DHT22 sensor.
- Turns an LED ON when distance <= 20 cm; otherwise turns it OFF.
- Sends one JSON record per line over USB serial to Node-RED.
- Node-RED can display distance, temperature, humidity, and LED status.
- No Wi-Fi, MQTT broker, or TCP connection is required for this USB-serial
  version. Arduino and Node-RED communicate through the USB cable.

PIN CONNECTIONS (Arduino Uno/Nano)
----------------------------------
HC-SR04:
  VCC  -> 5V
  GND  -> GND
  TRIG -> D9
  ECHO -> D10

DHT11 or DHT22 module:
  VCC  -> 5V (check your module's rated voltage)
  GND  -> GND
  DATA -> D4

  If you have a bare 4-pin DHT sensor rather than a module, check its pinout
  and use a 4.7k-10k pull-up resistor between DATA and VCC if required.
  Do not guess the bare sensor pin order; check its datasheet.

LED:
  D8 -> 220-330 ohm resistor -> LED long leg (anode)
  LED short leg (cathode) -> GND

All components must share GND.

LIBRARIES TO INSTALL IN ARDUINO IDE
-----------------------------------
1. Open Arduino IDE.
2. Go to Tools -> Manage Libraries.
3. Search for and install:
   - "DHT sensor library" by Adafruit
   - "Adafruit Unified Sensor" by Adafruit (install if Library Manager requests it)
4. Select your board under Tools -> Board (e.g. Arduino Uno).
5. Select the correct port under Tools -> Port.
6. Upload this sketch.

NODE-RED SETUP (USB SERIAL; NODE-RED CAN RUN ON WINDOWS OR RASPBERRY PI)
------------------------------------------------------------------------
A. Install serial nodes:
   Node-RED -> menu (top-right) -> Manage palette -> Install
   Search for: node-red-node-serialport
   Install it.

B. Build this flow:
   [Serial In] -> [JSON] -> [Function] -> [Debug]
                                  |
                                  +-> [Function: distance] -> [Distance Gauge]
                                  |
                                  +-> [Function: temperature] -> [Temperature Gauge]
                                  |
                                  +-> [Function: humidity] -> [Humidity Gauge]
                                  |
                                  +-> [Function: LED status] -> [Text widget]

   The serial input is newline-delimited JSON. The JSON node parses the line
   into a JavaScript object in msg.payload.

C. Configure Serial In:
   - Serial port: choose the Arduino's port.
       Windows: usually COM3/COM4/etc.; check Device Manager -> Ports (COM & LPT).
       Raspberry Pi/Linux: often /dev/ttyACM0 or /dev/ttyUSB0.
   - Baud rate: 9600
   - Data bits: 8
   - Parity: none
   - Stop bits: 1
   - Output: string
   - Split input on: newline (\n)
   - Deploy after configuration.
   IMPORTANT: Close Arduino IDE Serial Monitor before using Node-RED; the serial
   port is normally exclusive and cannot be opened by both at once.

D. Connect:
   Serial In -> JSON node -> Debug node.
   Deploy and open the Debug sidebar. You should see an object similar to:
   {"distance_cm":23.4,"temperature_c":25.1,"humidity_pct":60.0,"led":"OFF"}

E. Dashboard:
   Install the classic dashboard if its nodes are missing:
   Manage palette -> Install -> node-red-dashboard.
   Create/configure a Dashboard Tab and Group for each Gauge/Text widget.

   After the JSON node, create three Function nodes and one Text Function node.
   Each Function should contain one of the following snippets:

   Distance Function:
       msg.payload = Number(msg.payload.distance_cm);
       return msg;

   Temperature Function:
       msg.payload = Number(msg.payload.temperature_c);
       return msg;

   Humidity Function:
       msg.payload = Number(msg.payload.humidity_pct);
       return msg;

   LED Text Function:
       msg.payload = String(msg.payload.led);
       return msg;

   Wire each Function to its corresponding widget:
   - Distance Gauge: label "Distance", units "cm", min 0, max 400.
   - Temperature Gauge: label "Temperature", units "°C", min 0, max 80.
   - Humidity Gauge: label "Humidity", units "%", min 0, max 100.
   - Text widget: label "LED Status".

   For each widget, select a Dashboard Group, click Done, and Deploy.
   Open the classic Dashboard at http://localhost:1880/ui on the same device
   running Node-RED. If using Node-RED on the Pi, open that URL on the Pi or
   another device using http://<PI-IP-ADDRESS>:1880/ui.

F. Troubleshooting:
   - No serial node: install node-red-node-serialport and refresh/restart Node-RED.
   - Serial port busy: close Arduino IDE Serial Monitor/Plotter.
   - No readings: check board/port, 9600 baud, wiring, library installation, and
     that the Arduino has finished uploading.
   - DHT shows NaN: verify sensor type (DHT11 vs DHT22), pin, power, and wiring.
   - Dashboard gauge blank: confirm the Function node outputs a number and that
     the widget has a valid Dashboard Group.
   - If the LED is always OFF, place an object closer than 20 cm to the HC-SR04.
   - USB serial is used here. TCP/MQTT is a different architecture and is not
     required for this experiment.

===============================================================================
*/

#include <DHT.h>

// -------------------- PIN CONFIGURATION --------------------
const int TRIG_PIN = 9;
const int ECHO_PIN = 10;
const int LED_PIN  = 8;
const int DHT_PIN  = 4;

// Change DHT11 to DHT22 if that is the sensor you have.
#define DHT_TYPE DHT11

const float DISTANCE_THRESHOLD_CM = 20.0;
const unsigned long SERIAL_BAUD = 9600;

DHT dht(DHT_PIN, DHT_TYPE);

// -------------------- ULTRASONIC READING --------------------
float readDistanceCm() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);

  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  // Timeout after 30,000 microseconds to avoid blocking forever.
  unsigned long duration = pulseIn(ECHO_PIN, HIGH, 30000UL);

  if (duration == 0) {
    return -1.0; // No echo/timeout
  }

  // Sound travels to the object and back, hence divide by 2.
  return (duration * 0.0343f) / 2.0f;
}

// -------------------- SETUP --------------------
void setup() {
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  pinMode(LED_PIN, OUTPUT);

  digitalWrite(TRIG_PIN, LOW);
  digitalWrite(LED_PIN, LOW);

  Serial.begin(SERIAL_BAUD);
  dht.begin();

  // Allow the DHT sensor to settle after startup.
  delay(1500);
}

// -------------------- MAIN LOOP --------------------
void loop() {
  float distanceCm = readDistanceCm();

  // DHT sensors need time between readings; 2 seconds is safe for DHT11.
  float humidity = dht.readHumidity();
  float temperature = dht.readTemperature();

  bool validDistance = distanceCm >= 0.0f;
  bool validDht = !isnan(humidity) && !isnan(temperature);

  bool ledOn = validDistance && (distanceCm <= DISTANCE_THRESHOLD_CM);
  digitalWrite(LED_PIN, ledOn ? HIGH : LOW);

  // Send one JSON object per line so Node-RED can split on newline and
  // parse each line using a JSON node.
  Serial.print("{\"distance_cm\":");
  if (validDistance) {
    Serial.print(distanceCm, 2);
  } else {
    Serial.print("null");
  }

  Serial.print(",\"temperature_c\":");
  if (validDht) {
    Serial.print(temperature, 1);
  } else {
    Serial.print("null");
  }

  Serial.print(",\"humidity_pct\":");
  if (validDht) {
    Serial.print(humidity, 1);
  } else {
    Serial.print("null");
  }

  Serial.print(",\"led\":\"");
  Serial.print(ledOn ? "ON" : "OFF");
  Serial.println("\"}");

  delay(2000);
}
