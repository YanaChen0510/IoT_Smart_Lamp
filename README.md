# IoT Smart Lamp

An IoT smart lamp project built with Arduino Nano 33 BLE Sense and Raspberry Pi.

## Features
- BLE communication between Nano 33 BLE Sense and Raspberry Pi
- Web UI with AUTO / MANUAL / RECAL / STATUS
- Sensor-based smart lamp control
- Raspberry Pi as gateway and controller

## Hardware
- Arduino Nano 33 BLE Sense
- Raspberry Pi 3B+
- LED / lamp module
- Sensors

## Project Structure
- `nano33/` firmware for Arduino Nano 33 BLE Sense
- `raspberry_pi/` BLE gateway and controller
- `web_ui/` browser-based control interface
- `docs/` diagrams and project notes

## How to Run
1. Upload firmware to Nano 33 BLE Sense
2. Start Raspberry Pi BLE service
3. Open the web UI
4. Test AUTO / MANUAL / RECAL / STATUS modes
