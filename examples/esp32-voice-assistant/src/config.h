/**
 * ESP32 Voice Assistant Configuration
 *
 * Edit these values to match your setup
 */

#ifndef CONFIG_H
#define CONFIG_H

// ============================================================================
// WiFi Configuration
// ============================================================================
#define WIFI_SSID "YOUR_WIFI_SSID"
#define WIFI_PASSWORD "YOUR_WIFI_PASSWORD"
#define WIFI_CONNECT_TIMEOUT_MS 15000
#define WIFI_RECONNECT_DELAY_MS 5000

// ============================================================================
// Server Configuration
// ============================================================================
// WebAppChat server address (your homelab)
#define SERVER_HOST "192.168.50.5"
#define SERVER_PORT 5000
#define SERVER_USE_HTTPS true

// API endpoints
#define VOICE_ENDPOINT "/voice/process"
#define STATUS_ENDPOINT "/voice/status"

// HTTP timeouts
#define HTTP_CONNECT_TIMEOUT_MS 10000
#define HTTP_RESPONSE_TIMEOUT_MS 60000  // Voice processing can take a while

// ============================================================================
// Audio Input - INMP441 I2S Microphone
// ============================================================================
#define I2S_MIC_PORT I2S_NUM_0
#define I2S_MIC_SCK 2       // Serial Clock (BCK)
#define I2S_MIC_WS 15       // Word Select (LRCK)
#define I2S_MIC_SD 13       // Serial Data (DOUT)

// ============================================================================
// Audio Output - MAX98357A I2S Amplifier
// ============================================================================
#define I2S_AMP_PORT I2S_NUM_1
#define I2S_AMP_BCLK 26     // Bit Clock
#define I2S_AMP_LRC 25      // Left/Right Clock (Word Select)
#define I2S_AMP_DIN 22      // Data In

// ============================================================================
// Hardware Controls
// ============================================================================
#define BUTTON_PIN 4        // Push-to-talk button (active LOW with internal pullup)
#define LED_PIN 21          // Status LED (PWM capable)

// Button settings
#define BUTTON_DEBOUNCE_MS 50
#define BUTTON_LONG_PRESS_MS 3000  // Long press for special functions

// ============================================================================
// Audio Recording Settings
// ============================================================================
#define SAMPLE_RATE 16000           // 16kHz is optimal for Whisper
#define BITS_PER_SAMPLE 16          // 16-bit audio
#define CHANNELS 1                  // Mono
#define RECORD_TIME_MAX_SEC 30      // Maximum recording duration
#define RECORD_BUFFER_SIZE (SAMPLE_RATE * 2 * RECORD_TIME_MAX_SEC)  // bytes

// Audio level settings
#define MIC_GAIN_FACTOR 4           // Amplify mic input (adjust if too quiet/loud)
#define SILENCE_THRESHOLD 500       // RMS level below which is considered silence

// ============================================================================
// LED Patterns (PWM values 0-255)
// ============================================================================
#define LED_IDLE_BRIGHTNESS 30
#define LED_RECORDING_BRIGHTNESS 255
#define LED_PROCESSING_BRIGHTNESS 180
#define LED_PLAYING_BRIGHTNESS 120
#define LED_ERROR_BRIGHTNESS 255

// ============================================================================
// Session Management
// ============================================================================
#define SESSION_ID_MAX_LENGTH 64
#define NVS_NAMESPACE "voice_asst"
#define NVS_SESSION_KEY "session_id"

// ============================================================================
// Debug Settings
// ============================================================================
#define SERIAL_BAUD 115200
#define DEBUG_AUDIO_LEVELS false    // Print audio RMS levels during recording
#define DEBUG_HTTP_RESPONSE false   // Print full HTTP response headers

#endif // CONFIG_H
