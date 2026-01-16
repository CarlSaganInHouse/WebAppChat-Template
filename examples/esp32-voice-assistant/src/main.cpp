/**
 * ESP32 Voice Assistant for WebAppChat
 *
 * A push-to-talk voice assistant that:
 * 1. Records audio from INMP441 I2S microphone
 * 2. Sends WAV audio to WebAppChat server
 * 3. Server transcribes (Whisper), processes (LLM), synthesizes (TTS)
 * 4. Plays MP3 response through MAX98357A I2S amplifier
 *
 * Hardware:
 * - ESP32-S3 N16R8 (with PSRAM)
 * - INMP441 I2S Microphone
 * - MAX98357A I2S Amplifier
 * - Push button (GPIO 4)
 * - Status LED (GPIO 21)
 */

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <driver/i2s.h>
#include <SPIFFS.h>
#include "config.h"
#include "Audio.h"

// Response audio file path in SPIFFS
#define AUDIO_RESPONSE_PATH "/response.mp3"

// ============================================================================
// Global State
// ============================================================================

enum SystemState {
    STATE_INIT,
    STATE_CONNECTING,
    STATE_IDLE,
    STATE_RECORDING,
    STATE_PROCESSING,
    STATE_PLAYING,
    STATE_ERROR
};

SystemState currentState = STATE_INIT;
Preferences preferences;
String sessionId = "";
Audio audio;

// Button handling
volatile bool buttonPressed = false;
volatile unsigned long buttonPressStart = 0;
unsigned long lastDebounceTime = 0;

// Audio buffers (allocated in PSRAM)
uint8_t* recordBuffer = nullptr;
size_t recordedBytes = 0;

// LED state
int ledBrightness = 0;
int ledDirection = 1;
unsigned long lastLedUpdate = 0;

// ============================================================================
// Function Prototypes
// ============================================================================

void setupWiFi();
void setupI2SMicrophone();
void setupI2SAmp();
void setupButton();
void setupLED();
void setupSPIFFS();

void handleButton();
void processVoiceInteraction();
bool sendVoiceRequest(uint8_t* wavData, size_t wavSize, String& responseSessionId);
bool playAudioResponse();

size_t recordAudio(uint8_t* buffer, size_t maxSize);
size_t createWavHeader(uint8_t* header, size_t dataSize);

void ledSetState(SystemState state);
void ledUpdate();

String loadSessionId();
void saveSessionId(const String& sid);

bool checkServerStatus();

// ============================================================================
// Interrupt Handler
// ============================================================================

void IRAM_ATTR buttonISR() {
    buttonPressed = true;
    buttonPressStart = millis();
}

// ============================================================================
// Setup
// ============================================================================

void setup() {
    Serial.begin(SERIAL_BAUD);
    delay(1000);

    Serial.println("\n========================================");
    Serial.println("   ESP32 Voice Assistant for WebAppChat");
    Serial.println("========================================\n");

    // Initialize LED first for visual feedback
    setupLED();
    ledSetState(STATE_INIT);

    // Allocate audio buffer in PSRAM
    Serial.println("[Memory] Allocating audio buffer in PSRAM...");
    recordBuffer = (uint8_t*)ps_malloc(RECORD_BUFFER_SIZE + 44);  // +44 for WAV header
    if (!recordBuffer) {
        Serial.println("[ERROR] Failed to allocate audio buffer!");
        Serial.printf("  Free PSRAM: %d bytes\n", ESP.getFreePsram());
        ledSetState(STATE_ERROR);
        while (true) {
            ledUpdate();
            delay(10);
        }
    }
    Serial.printf("[Memory] Allocated %d bytes for audio buffer\n", RECORD_BUFFER_SIZE + 44);
    Serial.printf("[Memory] Free PSRAM: %d bytes\n", ESP.getFreePsram());

    // Load saved session ID
    preferences.begin(NVS_NAMESPACE, false);
    sessionId = loadSessionId();
    if (sessionId.length() > 0) {
        Serial.printf("[Session] Loaded existing session: %s\n", sessionId.c_str());
    }

    // Setup hardware
    setupButton();
    setupI2SMicrophone();
    setupI2SAmp();
    setupSPIFFS();

    // Connect to WiFi
    currentState = STATE_CONNECTING;
    ledSetState(STATE_CONNECTING);
    setupWiFi();

    // Check server connectivity
    Serial.println("\n[Server] Checking connectivity...");
    if (checkServerStatus()) {
        Serial.println("[Server] Connection OK!");
        currentState = STATE_IDLE;
        ledSetState(STATE_IDLE);
    } else {
        Serial.println("[Server] Connection failed - will retry on first request");
        currentState = STATE_IDLE;
        ledSetState(STATE_IDLE);
    }

    Serial.println("\n========================================");
    Serial.println("   Ready! Press button to speak.");
    Serial.println("========================================\n");
}

// ============================================================================
// Main Loop
// ============================================================================

void loop() {
    // Handle WiFi reconnection
    if (WiFi.status() != WL_CONNECTED && currentState != STATE_CONNECTING) {
        Serial.println("[WiFi] Connection lost, reconnecting...");
        currentState = STATE_CONNECTING;
        ledSetState(STATE_CONNECTING);
        setupWiFi();
        if (WiFi.status() == WL_CONNECTED) {
            currentState = STATE_IDLE;
            ledSetState(STATE_IDLE);
        }
    }

    // Handle button press (only in IDLE state)
    if (buttonPressed && currentState == STATE_IDLE) {
        unsigned long pressTime = buttonPressStart;
        buttonPressed = false;

        // Debounce check
        if (millis() - lastDebounceTime > BUTTON_DEBOUNCE_MS) {
            lastDebounceTime = millis();
            processVoiceInteraction();
        }
    }

    // Handle audio playback (non-blocking)
    audio.loop();

    // Update LED animation
    ledUpdate();

    delay(10);
}

// ============================================================================
// WiFi Setup
// ============================================================================

void setupWiFi() {
    Serial.print("[WiFi] Connecting to ");
    Serial.println(WIFI_SSID);

    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    unsigned long startTime = millis();
    int dots = 0;

    while (WiFi.status() != WL_CONNECTED) {
        if (millis() - startTime > WIFI_CONNECT_TIMEOUT_MS) {
            Serial.println("\n[WiFi] Connection timeout!");
            return;
        }

        delay(500);
        Serial.print(".");
        dots++;
        if (dots % 40 == 0) Serial.println();

        ledUpdate();
    }

    Serial.println();
    Serial.print("[WiFi] Connected! IP: ");
    Serial.println(WiFi.localIP());
    Serial.printf("[WiFi] Signal strength: %d dBm\n", WiFi.RSSI());
}

// ============================================================================
// I2S Microphone Setup
// ============================================================================

void setupI2SMicrophone() {
    Serial.println("[I2S] Setting up microphone...");

    i2s_config_t i2s_mic_config = {
        .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
        .sample_rate = SAMPLE_RATE,
        .bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT,
        .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
        .communication_format = I2S_COMM_FORMAT_STAND_I2S,
        .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
        .dma_buf_count = 8,
        .dma_buf_len = 1024,
        .use_apll = false,
        .tx_desc_auto_clear = false,
        .fixed_mclk = 0
    };

    i2s_pin_config_t i2s_mic_pins = {
        .bck_io_num = I2S_MIC_SCK,
        .ws_io_num = I2S_MIC_WS,
        .data_out_num = I2S_PIN_NO_CHANGE,
        .data_in_num = I2S_MIC_SD
    };

    esp_err_t err = i2s_driver_install(I2S_MIC_PORT, &i2s_mic_config, 0, NULL);
    if (err != ESP_OK) {
        Serial.printf("[I2S] Microphone driver install failed: %d\n", err);
        return;
    }

    err = i2s_set_pin(I2S_MIC_PORT, &i2s_mic_pins);
    if (err != ESP_OK) {
        Serial.printf("[I2S] Microphone pin config failed: %d\n", err);
        return;
    }

    i2s_zero_dma_buffer(I2S_MIC_PORT);
    Serial.println("[I2S] Microphone ready");
}

// ============================================================================
// I2S Amplifier Setup
// ============================================================================

void setupI2SAmp() {
    Serial.println("[I2S] Setting up amplifier...");

    audio.setPinout(I2S_AMP_BCLK, I2S_AMP_LRC, I2S_AMP_DIN);
    audio.setVolume(15);  // 0-21

    Serial.println("[I2S] Amplifier ready");
}

// ============================================================================
// Button Setup
// ============================================================================

void setupButton() {
    Serial.println("[Button] Setting up...");
    pinMode(BUTTON_PIN, INPUT_PULLUP);
    attachInterrupt(digitalPinToInterrupt(BUTTON_PIN), buttonISR, FALLING);
    Serial.println("[Button] Ready");
}

// ============================================================================
// LED Setup and Control
// ============================================================================

void setupLED() {
    ledcSetup(0, 5000, 8);  // Channel 0, 5kHz, 8-bit resolution
    ledcAttachPin(LED_PIN, 0);
    ledcWrite(0, 0);
}

void ledSetState(SystemState state) {
    currentState = state;
    lastLedUpdate = millis();

    switch (state) {
        case STATE_IDLE:
            ledBrightness = LED_IDLE_BRIGHTNESS;
            ledDirection = 0;  // Solid
            ledcWrite(0, ledBrightness);
            break;
        case STATE_RECORDING:
            ledBrightness = LED_RECORDING_BRIGHTNESS;
            ledDirection = -15;  // Fast pulse down
            break;
        case STATE_PROCESSING:
            ledBrightness = LED_PROCESSING_BRIGHTNESS / 2;
            ledDirection = 10;  // Medium pulse
            break;
        case STATE_PLAYING:
            ledBrightness = LED_PLAYING_BRIGHTNESS / 2;
            ledDirection = 5;  // Gentle pulse
            break;
        case STATE_ERROR:
            ledBrightness = 0;
            ledDirection = 0;  // Fast blink handled separately
            break;
        case STATE_CONNECTING:
            ledBrightness = 0;
            ledDirection = 0;  // Slow blink handled separately
            break;
        default:
            ledcWrite(0, 0);
            break;
    }
}

void ledUpdate() {
    unsigned long now = millis();

    switch (currentState) {
        case STATE_RECORDING:
            if (now - lastLedUpdate > 20) {
                lastLedUpdate = now;
                ledBrightness += ledDirection;
                if (ledBrightness >= LED_RECORDING_BRIGHTNESS) {
                    ledBrightness = LED_RECORDING_BRIGHTNESS;
                    ledDirection = -15;
                }
                if (ledBrightness <= 100) {
                    ledBrightness = 100;
                    ledDirection = 15;
                }
                ledcWrite(0, ledBrightness);
            }
            break;

        case STATE_PROCESSING:
            if (now - lastLedUpdate > 50) {
                lastLedUpdate = now;
                ledBrightness += ledDirection;
                if (ledBrightness >= LED_PROCESSING_BRIGHTNESS) {
                    ledBrightness = LED_PROCESSING_BRIGHTNESS;
                    ledDirection = -10;
                }
                if (ledBrightness <= 50) {
                    ledBrightness = 50;
                    ledDirection = 10;
                }
                ledcWrite(0, ledBrightness);
            }
            break;

        case STATE_PLAYING:
            if (now - lastLedUpdate > 100) {
                lastLedUpdate = now;
                ledBrightness += ledDirection;
                if (ledBrightness >= LED_PLAYING_BRIGHTNESS) {
                    ledBrightness = LED_PLAYING_BRIGHTNESS;
                    ledDirection = -5;
                }
                if (ledBrightness <= 30) {
                    ledBrightness = 30;
                    ledDirection = 5;
                }
                ledcWrite(0, ledBrightness);
            }
            break;

        case STATE_ERROR:
            if (now - lastLedUpdate > 100) {
                lastLedUpdate = now;
                ledBrightness = (ledBrightness > 0) ? 0 : LED_ERROR_BRIGHTNESS;
                ledcWrite(0, ledBrightness);
            }
            break;

        case STATE_CONNECTING:
            if (now - lastLedUpdate > 500) {
                lastLedUpdate = now;
                ledBrightness = (ledBrightness > 0) ? 0 : 128;
                ledcWrite(0, ledBrightness);
            }
            break;

        default:
            break;
    }
}

// ============================================================================
// Voice Interaction Flow
// ============================================================================

void processVoiceInteraction() {
    Serial.println("\n========== Voice Interaction ==========");

    // Step 1: Record audio
    currentState = STATE_RECORDING;
    ledSetState(STATE_RECORDING);

    Serial.println("[Recording] Hold button and speak...");
    recordedBytes = recordAudio(recordBuffer + 44, RECORD_BUFFER_SIZE);  // Leave space for WAV header

    if (recordedBytes < 1000) {
        Serial.println("[Recording] Too short, ignoring");
        currentState = STATE_IDLE;
        ledSetState(STATE_IDLE);
        return;
    }

    float duration = (float)recordedBytes / (SAMPLE_RATE * 2);
    Serial.printf("[Recording] Complete: %d bytes (%.1f seconds)\n", recordedBytes, duration);

    // Step 2: Add WAV header
    createWavHeader(recordBuffer, recordedBytes);
    size_t totalWavSize = recordedBytes + 44;

    // Step 3: Send to server
    currentState = STATE_PROCESSING;
    ledSetState(STATE_PROCESSING);

    Serial.println("[Processing] Sending to server...");

    String newSessionId;
    bool success = sendVoiceRequest(recordBuffer, totalWavSize, newSessionId);

    if (!success) {
        Serial.println("[Processing] Failed!");
        currentState = STATE_ERROR;
        ledSetState(STATE_ERROR);
        delay(2000);
        currentState = STATE_IDLE;
        ledSetState(STATE_IDLE);
        return;
    }

    // Update session ID if changed
    if (newSessionId.length() > 0 && newSessionId != sessionId) {
        sessionId = newSessionId;
        saveSessionId(sessionId);
        Serial.printf("[Session] Updated: %s\n", sessionId.c_str());
    }

    // Step 4: Play audio response from SPIFFS
    currentState = STATE_PLAYING;
    ledSetState(STATE_PLAYING);

    if (!playAudioResponse()) {
        Serial.println("[Playing] Failed to play audio!");
        currentState = STATE_ERROR;
        ledSetState(STATE_ERROR);
        delay(1000);
    } else {
        // Wait for playback to complete
        while (audio.isRunning()) {
            audio.loop();
            ledUpdate();
            delay(10);
        }
        Serial.println("[Playing] Complete");
    }

    // Return to idle
    currentState = STATE_IDLE;
    ledSetState(STATE_IDLE);

    Serial.println("========================================\n");
}

// ============================================================================
// Audio Recording
// ============================================================================

size_t recordAudio(uint8_t* buffer, size_t maxSize) {
    size_t totalBytesRead = 0;
    int16_t* samples = (int16_t*)buffer;
    size_t maxSamples = maxSize / 2;

    unsigned long recordStart = millis();
    unsigned long lastPrint = 0;

    // Clear the buffer first
    i2s_zero_dma_buffer(I2S_MIC_PORT);

    // Record while button is held
    while (digitalRead(BUTTON_PIN) == LOW) {
        // Check max recording time
        if (millis() - recordStart > (RECORD_TIME_MAX_SEC * 1000)) {
            Serial.println("[Recording] Max time reached");
            break;
        }

        // Read audio data
        size_t bytesRead = 0;
        size_t remainingBytes = maxSize - totalBytesRead;
        size_t toRead = min((size_t)4096, remainingBytes);

        if (toRead == 0) {
            Serial.println("[Recording] Buffer full");
            break;
        }

        esp_err_t result = i2s_read(I2S_MIC_PORT, buffer + totalBytesRead, toRead, &bytesRead, 100);

        if (result == ESP_OK && bytesRead > 0) {
            // Apply gain to recorded samples
            int16_t* newSamples = (int16_t*)(buffer + totalBytesRead);
            size_t numSamples = bytesRead / 2;
            for (size_t i = 0; i < numSamples; i++) {
                int32_t sample = newSamples[i] * MIC_GAIN_FACTOR;
                // Clamp to 16-bit range
                if (sample > 32767) sample = 32767;
                if (sample < -32768) sample = -32768;
                newSamples[i] = (int16_t)sample;
            }

            totalBytesRead += bytesRead;

            // Print progress every second
            if (DEBUG_AUDIO_LEVELS && millis() - lastPrint > 1000) {
                lastPrint = millis();
                // Calculate RMS
                float sum = 0;
                for (size_t i = 0; i < numSamples; i++) {
                    sum += (float)newSamples[i] * newSamples[i];
                }
                float rms = sqrt(sum / numSamples);
                Serial.printf("[Recording] %d bytes, RMS: %.0f\n", totalBytesRead, rms);
            }
        }

        ledUpdate();
    }

    return totalBytesRead;
}

// ============================================================================
// WAV Header Creation
// ============================================================================

size_t createWavHeader(uint8_t* buffer, size_t dataSize) {
    uint32_t fileSize = dataSize + 36;
    uint32_t byteRate = SAMPLE_RATE * CHANNELS * BITS_PER_SAMPLE / 8;
    uint16_t blockAlign = CHANNELS * BITS_PER_SAMPLE / 8;

    // RIFF header
    buffer[0] = 'R'; buffer[1] = 'I'; buffer[2] = 'F'; buffer[3] = 'F';
    buffer[4] = fileSize & 0xFF;
    buffer[5] = (fileSize >> 8) & 0xFF;
    buffer[6] = (fileSize >> 16) & 0xFF;
    buffer[7] = (fileSize >> 24) & 0xFF;
    buffer[8] = 'W'; buffer[9] = 'A'; buffer[10] = 'V'; buffer[11] = 'E';

    // fmt chunk
    buffer[12] = 'f'; buffer[13] = 'm'; buffer[14] = 't'; buffer[15] = ' ';
    buffer[16] = 16; buffer[17] = 0; buffer[18] = 0; buffer[19] = 0;  // Subchunk1Size (16 for PCM)
    buffer[20] = 1; buffer[21] = 0;  // AudioFormat (1 = PCM)
    buffer[22] = CHANNELS; buffer[23] = 0;  // NumChannels
    buffer[24] = SAMPLE_RATE & 0xFF;
    buffer[25] = (SAMPLE_RATE >> 8) & 0xFF;
    buffer[26] = (SAMPLE_RATE >> 16) & 0xFF;
    buffer[27] = (SAMPLE_RATE >> 24) & 0xFF;
    buffer[28] = byteRate & 0xFF;
    buffer[29] = (byteRate >> 8) & 0xFF;
    buffer[30] = (byteRate >> 16) & 0xFF;
    buffer[31] = (byteRate >> 24) & 0xFF;
    buffer[32] = blockAlign & 0xFF;
    buffer[33] = (blockAlign >> 8) & 0xFF;
    buffer[34] = BITS_PER_SAMPLE; buffer[35] = 0;

    // data chunk
    buffer[36] = 'd'; buffer[37] = 'a'; buffer[38] = 't'; buffer[39] = 'a';
    buffer[40] = dataSize & 0xFF;
    buffer[41] = (dataSize >> 8) & 0xFF;
    buffer[42] = (dataSize >> 16) & 0xFF;
    buffer[43] = (dataSize >> 24) & 0xFF;

    return 44;
}

// ============================================================================
// HTTP Request to Server
// ============================================================================

bool sendVoiceRequest(uint8_t* wavData, size_t wavSize, String& responseSessionId) {
    WiFiClientSecure client;

    // Skip certificate verification for local server
    client.setInsecure();

    HTTPClient http;

    String url = String(SERVER_USE_HTTPS ? "https://" : "http://") +
                 SERVER_HOST + ":" + String(SERVER_PORT) + VOICE_ENDPOINT;

    Serial.printf("[HTTP] POST %s (%d bytes)\n", url.c_str(), wavSize);

    http.begin(client, url);
    http.setTimeout(HTTP_RESPONSE_TIMEOUT_MS);

    // Build multipart form data
    String boundary = "----ESP32Boundary" + String(millis());

    // Prepare the multipart body parts
    String bodyStart = "--" + boundary + "\r\n";
    bodyStart += "Content-Disposition: form-data; name=\"audio\"; filename=\"recording.wav\"\r\n";
    bodyStart += "Content-Type: audio/wav\r\n\r\n";

    String bodyMid = "\r\n";

    // Add session_id if we have one
    if (sessionId.length() > 0) {
        bodyMid += "--" + boundary + "\r\n";
        bodyMid += "Content-Disposition: form-data; name=\"session_id\"\r\n\r\n";
        bodyMid += sessionId + "\r\n";
    }

    // Add use_rag parameter
    bodyMid += "--" + boundary + "\r\n";
    bodyMid += "Content-Disposition: form-data; name=\"use_rag\"\r\n\r\n";
    bodyMid += "true\r\n";

    String bodyEnd = "--" + boundary + "--\r\n";

    size_t totalSize = bodyStart.length() + wavSize + bodyMid.length() + bodyEnd.length();

    http.addHeader("Content-Type", "multipart/form-data; boundary=" + boundary);
    http.addHeader("Content-Length", String(totalSize));

    // Use the streaming approach with multiple writes
    if (!client.connect(SERVER_HOST, SERVER_PORT)) {
        Serial.println("[HTTP] Connection failed!");
        http.end();
        return false;
    }

    // Build and send request manually for large payloads
    client.print("POST " + String(VOICE_ENDPOINT) + " HTTP/1.1\r\n");
    client.print("Host: " + String(SERVER_HOST) + "\r\n");
    client.print("Content-Type: multipart/form-data; boundary=" + boundary + "\r\n");
    client.print("Content-Length: " + String(totalSize) + "\r\n");
    client.print("Connection: close\r\n");
    client.print("\r\n");

    // Send body in chunks
    client.print(bodyStart);

    // Send WAV data in chunks
    size_t sent = 0;
    size_t chunkSize = 4096;
    while (sent < wavSize) {
        size_t toSend = min(chunkSize, wavSize - sent);
        client.write(wavData + sent, toSend);
        sent += toSend;

        // Update LED during upload
        ledUpdate();
        yield();
    }

    client.print(bodyMid);
    client.print(bodyEnd);

    Serial.println("[HTTP] Request sent, waiting for response...");

    // Wait for response
    unsigned long startWait = millis();
    while (!client.available() && millis() - startWait < HTTP_RESPONSE_TIMEOUT_MS) {
        delay(100);
        ledUpdate();
    }

    if (!client.available()) {
        Serial.println("[HTTP] Response timeout!");
        return false;
    }

    // Read status line
    String statusLine = client.readStringUntil('\n');
    Serial.printf("[HTTP] Status: %s\n", statusLine.c_str());

    int statusCode = statusLine.substring(9, 12).toInt();
    if (statusCode != 200) {
        Serial.printf("[HTTP] Error status: %d\n", statusCode);
        // Read and print error body
        while (client.available()) {
            Serial.write(client.read());
        }
        return false;
    }

    // Read headers to extract metadata
    String transcription = "";
    int contentLength = 0;

    while (client.available()) {
        String header = client.readStringUntil('\n');
        header.trim();

        if (header.length() == 0) {
            break;  // End of headers
        }

        if (DEBUG_HTTP_RESPONSE) {
            Serial.println("  " + header);
        }

        if (header.startsWith("X-Session-Id:")) {
            responseSessionId = header.substring(14);
            responseSessionId.trim();
        } else if (header.startsWith("X-Transcription:")) {
            transcription = header.substring(17);
            transcription.trim();
        } else if (header.startsWith("Content-Length:")) {
            contentLength = header.substring(16).toInt();
        }
    }

    Serial.printf("[HTTP] Response: %d bytes\n", contentLength);
    if (transcription.length() > 0) {
        Serial.printf("[Transcription] %s\n", transcription.c_str());
    }

    // Save audio response to SPIFFS file
    if (contentLength > 0) {
        // Open file for writing
        File audioFile = SPIFFS.open(AUDIO_RESPONSE_PATH, FILE_WRITE);
        if (!audioFile) {
            Serial.println("[SPIFFS] Failed to open file for writing!");
            return false;
        }

        Serial.printf("[SPIFFS] Saving %d bytes to %s...\n", contentLength, AUDIO_RESPONSE_PATH);

        // Download and write in chunks
        size_t bytesWritten = 0;
        uint8_t chunkBuffer[4096];

        while (bytesWritten < contentLength && client.connected()) {
            if (client.available()) {
                size_t toRead = min((size_t)sizeof(chunkBuffer), (size_t)(contentLength - bytesWritten));
                size_t got = client.readBytes(chunkBuffer, toRead);

                if (got > 0) {
                    size_t written = audioFile.write(chunkBuffer, got);
                    bytesWritten += written;

                    // Progress indicator every 10KB
                    if (bytesWritten % 10240 < got) {
                        Serial.printf("[SPIFFS] Progress: %d/%d bytes\n", bytesWritten, contentLength);
                    }
                }
            }
            ledUpdate();
            yield();
        }

        audioFile.close();
        Serial.printf("[SPIFFS] Saved %d bytes\n", bytesWritten);

        if (bytesWritten != contentLength) {
            Serial.printf("[SPIFFS] Warning: Expected %d bytes, got %d\n", contentLength, bytesWritten);
        }

        return bytesWritten > 0;
    }

    Serial.println("[HTTP] No audio content in response");
    return false;
}

// ============================================================================
// SPIFFS Setup
// ============================================================================

void setupSPIFFS() {
    Serial.println("[SPIFFS] Initializing...");

    if (!SPIFFS.begin(true)) {  // true = format if mount fails
        Serial.println("[SPIFFS] Mount failed!");
        return;
    }

    // Show SPIFFS info
    size_t totalBytes = SPIFFS.totalBytes();
    size_t usedBytes = SPIFFS.usedBytes();
    Serial.printf("[SPIFFS] Total: %d bytes, Used: %d bytes, Free: %d bytes\n",
                  totalBytes, usedBytes, totalBytes - usedBytes);

    // Remove old response file if exists
    if (SPIFFS.exists(AUDIO_RESPONSE_PATH)) {
        SPIFFS.remove(AUDIO_RESPONSE_PATH);
        Serial.println("[SPIFFS] Removed old response file");
    }

    Serial.println("[SPIFFS] Ready");
}

// ============================================================================
// Audio Playback from SPIFFS
// ============================================================================

bool playAudioResponse() {
    // Check if file exists
    if (!SPIFFS.exists(AUDIO_RESPONSE_PATH)) {
        Serial.println("[Audio] Response file not found!");
        return false;
    }

    // Get file size
    File audioFile = SPIFFS.open(AUDIO_RESPONSE_PATH, FILE_READ);
    if (!audioFile) {
        Serial.println("[Audio] Failed to open response file!");
        return false;
    }
    size_t fileSize = audioFile.size();
    audioFile.close();

    Serial.printf("[Audio] Playing %s (%d bytes)\n", AUDIO_RESPONSE_PATH, fileSize);

    // Play using ESP32-audioI2S library
    if (!audio.connecttoFS(SPIFFS, AUDIO_RESPONSE_PATH + 1)) {  // +1 to skip leading '/'
        Serial.println("[Audio] Failed to connect to audio file!");
        return false;
    }

    Serial.println("[Audio] Playback started");
    return true;
}

// ============================================================================
// Server Status Check
// ============================================================================

bool checkServerStatus() {
    WiFiClientSecure client;
    client.setInsecure();

    HTTPClient http;

    String url = String(SERVER_USE_HTTPS ? "https://" : "http://") +
                 SERVER_HOST + ":" + String(SERVER_PORT) + STATUS_ENDPOINT;

    http.begin(client, url);
    http.setTimeout(5000);

    int httpCode = http.GET();
    http.end();

    return httpCode == 200;
}

// ============================================================================
// Session Management
// ============================================================================

String loadSessionId() {
    return preferences.getString(NVS_SESSION_KEY, "");
}

void saveSessionId(const String& sid) {
    preferences.putString(NVS_SESSION_KEY, sid);
}
