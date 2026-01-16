# ESP32 Voice Assistant for WebAppChat

A DIY smart speaker that integrates with WebAppChat. Press a button, speak, and receive AI-generated audio responses.

## Features

- **Push-to-talk** voice interaction
- **Whisper STT** for accurate speech recognition
- **GPT-4o-mini** (or any WebAppChat model) for responses
- **OpenAI TTS** for natural-sounding audio
- **RAG integration** - ask about your Obsidian vault
- **Session continuity** - multi-turn conversations
- **Visual feedback** - LED status indicators

## Hardware Requirements

| Component | Model | Purpose |
|-----------|-------|---------|
| Microcontroller | ESP32-S3 N16R8 | Main controller (with PSRAM) |
| Microphone | INMP441 | I2S digital microphone |
| Amplifier | MAX98357A | I2S audio amplifier |
| Speaker | 3W 4Ω | Audio output |
| Button | Momentary switch | Push-to-talk |
| LED | Standard LED | Status indicator |

## Wiring Diagram

```
ESP32-S3 Pin        Component
────────────────────────────────
GPIO 2  (SCK)   --> INMP441 SCK
GPIO 15 (WS)    --> INMP441 WS
GPIO 13 (SD)    --> INMP441 SD
3.3V            --> INMP441 VDD
GND             --> INMP441 GND, L/R

GPIO 26 (BCLK)  --> MAX98357A BCLK
GPIO 25 (LRC)   --> MAX98357A LRC
GPIO 22 (DIN)   --> MAX98357A DIN
5V              --> MAX98357A VIN
GND             --> MAX98357A GND

GPIO 4          --> Button (other side to GND)
GPIO 21         --> LED anode (via 220Ω resistor)
GND             --> LED cathode

Speaker +       --> MAX98357A OUT+
Speaker -       --> MAX98357A OUT-
```

### INMP441 Notes
- L/R pin to GND selects left channel
- If no audio, try swapping SCK/WS pins

### MAX98357A Notes
- GAIN pin: float=9dB, GND=15dB
- SD pin: leave floating or tie to 3.3V (enable)
- Add 100µF capacitor across VIN-GND for stability

## Software Setup

### 1. Install PlatformIO

```bash
pip install platformio
# or install VS Code extension
```

### 2. Configure WiFi and Server

Edit `src/config.h`:

```cpp
#define WIFI_SSID "YourWiFiName"
#define WIFI_PASSWORD "YourWiFiPassword"

#define SERVER_HOST "${PROXMOX_HOST_IP}"  // Your WebAppChat server IP
#define SERVER_PORT 5000
```

### 3. Build and Upload

```bash
cd examples/esp32-voice-assistant
pio run -t upload
pio device monitor
```

## Usage

1. **Power on** - LED will blink while connecting to WiFi
2. **Wait for solid LED** - indicates ready state
3. **Press and hold button** - LED pulses, speak your question
4. **Release button** - LED changes pattern, processing
5. **Listen to response** - LED gently pulses during playback
6. **Repeat** - conversation context is maintained

## LED Patterns

| Pattern | State | Description |
|---------|-------|-------------|
| Slow blink | Connecting | Connecting to WiFi |
| Solid (dim) | Idle | Ready for input |
| Fast pulse | Recording | Button held, recording audio |
| Medium pulse | Processing | Sending to server, waiting for response |
| Gentle pulse | Playing | Audio response playing |
| Fast blink | Error | Something went wrong |

## Server Endpoints

The ESP32 communicates with these WebAppChat endpoints:

- `GET /voice/status` - Health check
- `POST /voice/process` - Full pipeline (STT → LLM → TTS)

## Troubleshooting

### No WiFi connection
- Check SSID and password in `config.h`
- Ensure ESP32 is within WiFi range
- Try increasing `WIFI_CONNECT_TIMEOUT_MS`

### No audio recording
- Check INMP441 wiring (especially SCK/WS)
- Try swapping L/R pin connection
- Verify 3.3V power supply

### No audio playback
- Check MAX98357A wiring
- Verify 5V power supply
- Add capacitor for power stability
- Check speaker connections

### Server connection fails
- Verify server IP address
- Ensure WebAppChat is running
- Check firewall rules (port 5000)
- Test with: `curl http://${PROXMOX_HOST_IP}:5000/voice/status`

### Recording too quiet
- Increase `MIC_GAIN_FACTOR` in `config.h`
- Move closer to microphone
- Check for obstructions

## Cost Estimate

Per voice interaction:
- Whisper STT: ~$0.003 (30 seconds)
- GPT-4o-mini: ~$0.0005 (500 tokens)
- TTS: ~$0.003 (200 characters)
- **Total: ~$0.007** (less than 1 cent)

At 50 interactions/day: ~$10.50/month

## Future Enhancements

- [ ] Wake word detection (hands-free activation)
- [ ] OLED display for transcription/response text
- [ ] Streaming TTS playback
- [ ] Multi-room support
- [ ] Local Whisper fallback

## License

MIT License - See main WebAppChat repository

## Credits

- [ESP32-audioI2S](https://github.com/schreibfaul1/ESP32-audioI2S) library
- [ArduinoJson](https://arduinojson.org/) library
- WebAppChat for backend services
