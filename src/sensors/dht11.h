#ifndef DHT11_SENSOR_H
#define DHT11_SENSOR_H

#include <Arduino.h>
#include <DHT.h>
#include "../config/pins.h"
#include "../config/config.h"

class DHT11Sensor {
public:
    DHT11Sensor();
    void begin();
    void update();

    float getTemperature() const;
    float getHumidity() const;
    bool isSensorOK() const;
    void printDebugStatus() const;

private:
    DHT dht;
    float lastValidTemperature;
    float lastValidHumidity;
    bool sensorWorking;
    unsigned long lastReadTime;
};

#endif // DHT11_SENSOR_H
