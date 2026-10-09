#include "dht11.h"

DHT11Sensor::DHT11Sensor() 
    : dht(Pins::DHT_PIN, DHT11), 
      lastValidTemperature(25.0f), 
      lastValidHumidity(60.0f), 
      sensorWorking(false), 
      lastReadTime(0) {}

void DHT11Sensor::begin() {
    dht.begin();
    lastReadTime = millis();
    update();
    Serial.println("[DHT11] Initialized");
}

void DHT11Sensor::update() {
    unsigned long now = millis();
    // Đọc không quá nhanh, theo chu kỳ cấu hình (2000ms)
    if (now - lastReadTime >= Config::DHT_READ_INTERVAL_MS) {
        lastReadTime = now;

        float h = dht.readHumidity();
        float t = dht.readTemperature();

        if (isnan(h) || isnan(t)) {
            sensorWorking = false;
            Serial.println("[DHT11] Read failed");
        } else {
            lastValidHumidity = h;
            lastValidTemperature = t;
            sensorWorking = true;
        }
    }
}

float DHT11Sensor::getTemperature() const {
    return lastValidTemperature;
}

float DHT11Sensor::getHumidity() const {
    return lastValidHumidity;
}

bool DHT11Sensor::isSensorOK() const {
    return sensorWorking;
}

void DHT11Sensor::printDebugStatus() const {
    Serial.println("--- [TEST 4] DHT11 TEMPERATURE & HUMIDITY ---");
    Serial.printf("  GPIO Pin   : %d (1-Wire)\n", Pins::DHT_PIN);
    Serial.printf("  Temperature: %.1f °C\n", lastValidTemperature);
    Serial.printf("  Humidity   : %.1f %%\n", lastValidHumidity);
    Serial.printf("  Sensor OK  : %s\n", sensorWorking ? "YES (Reading valid)" : "NO (Check wiring/pull-up)");
    Serial.println("---------------------------------------------");
}
