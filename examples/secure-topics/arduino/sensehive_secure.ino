// Publish to a SenseHive secure topic from an ESP32 (Arduino core, mbedTLS built in).
// Libraries: PubSubClient. Protocol: docs/SECURE-TOPICS.md.
// The clock must be right (configTime + NTP): a message more than 5 minutes off is refused.
// Fill in Wi-Fi, broker, the key id and the 64-hex key from SenseHive (Secure topics, Generate keys).
#include <WiFi.h>
#include <PubSubClient.h>
#include <time.h>
#include "mbedtls/aes.h"
#include "mbedtls/md.h"
#include "mbedtls/base64.h"
#include "esp_random.h"

const char* WIFI_SSID = "your-wifi";
const char* WIFI_PASS = "your-password";
const char* BROKER    = "192.168.1.10";
const char* KID       = "0123456789abcdef";                                        // from SenseHive
const char* KEY_HEX   = "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff";
const char* TOPIC     = "sensehive/secure/site-a/pump-1";

WiFiClient net;
PubSubClient mqtt(net);

static void hmac256(const uint8_t* key, size_t keyLen, const uint8_t* msg, size_t msgLen, uint8_t out[32]) {
  mbedtls_md_hmac(mbedtls_md_info_from_type(MBEDTLS_MD_SHA256), key, keyLen, msg, msgLen, out);
}

static String b64(const uint8_t* data, size_t len) {
  size_t olen = 0;
  static unsigned char buf[1500];
  mbedtls_base64_encode(buf, sizeof(buf), &olen, data, len);
  return String((const char*)buf).substring(0, olen);
}

// The JSON envelope for `payload` (up to ~1 kB here; raise the buffers for more).
String seal(const char* payload) {
  uint8_t key[32];
  for (int i = 0; i < 32; i++) sscanf(KEY_HEX + 2 * i, "%2hhx", &key[i]);
  uint8_t encKey[32], macKey[32];
  hmac256(key, 32, (const uint8_t*)"sst1 enc", 8, encKey);
  hmac256(key, 32, (const uint8_t*)"sst1 mac", 8, macKey);

  uint8_t nonce[16], counter[16], block[16];
  esp_fill_random(nonce, 16);
  memcpy(counter, nonce, 16);
  size_t len = strlen(payload), off = 0;
  static uint8_t ct[1024];
  mbedtls_aes_context aes;
  mbedtls_aes_init(&aes);
  mbedtls_aes_setkey_enc(&aes, encKey, 256);
  mbedtls_aes_crypt_ctr(&aes, len, &off, counter, block, (const uint8_t*)payload, ct);
  mbedtls_aes_free(&aes);

  long t = (long)time(nullptr);
  String ts = String(t);
  static uint8_t signedBuf[1200];
  size_t n = 0;
  auto add = [&](const uint8_t* p, size_t l) { memcpy(signedBuf + n, p, l); n += l; };
  const uint8_t zero = 0;
  add((const uint8_t*)"sst1", 4); add(&zero, 1);
  add((const uint8_t*)TOPIC, strlen(TOPIC)); add(&zero, 1);
  add((const uint8_t*)KID, strlen(KID)); add(&zero, 1);
  add((const uint8_t*)ts.c_str(), ts.length()); add(&zero, 1);
  add(nonce, 16); add(ct, len);
  uint8_t tag[32];
  hmac256(macKey, 32, signedBuf, n, tag);

  return String("{\"v\":1,\"k\":\"") + KID + "\",\"t\":" + ts + ",\"i\":\"" + b64(nonce, 16) +
         "\",\"c\":\"" + b64(ct, len) + "\",\"m\":\"" + b64(tag, 16) + "\"}";
}

void setup() {
  Serial.begin(115200);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) delay(300);
  configTime(0, 0, "pool.ntp.org");
  while (time(nullptr) < 1700000000) delay(300);          // wait for NTP
  mqtt.setServer(BROKER, 1883);
  mqtt.setBufferSize(2048);
}

void loop() {
  if (!mqtt.connected()) mqtt.connect("esp32-secure-demo");
  mqtt.loop();
  static unsigned long last = 0;
  if (millis() - last > 10000) {
    last = millis();
    String msg = seal("{\"temp\":21.5}");
    mqtt.publish(TOPIC, msg.c_str());
  }
}
