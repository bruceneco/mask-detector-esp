#include <ArduinoMqttClient.h>

#include <WebServer.h>
#include <WiFi.h>
#include <esp32cam.h>

const char *WIFI_SSID = "Naldo";
const char *WIFI_PASS = "zuedne1245";
const int buttonPin = 14;
const int redLedPin = 13;
const int yellowLedPin = 12;
const int greenLedPin = 2;
boolean detecting = false;
const char *broker = "192.168.0.106";
const char *publishTopic = "mask-detector/signal";
const char *resultTopic = "mask-detector/result";

const char hasMask = 1;
const char noMask = 2;
const char noFace = 0;

WebServer server(80);
WiFiClient wifiClient = server.client();
MqttClient mqttClient(wifiClient);

static auto hiRes = esp32cam::Resolution::find(800, 600);

void
takeAndSendPicture() {
    auto frame = esp32cam::capture();
    if (frame == nullptr) {
        Serial.println("CAPTURE FAIL");
        server.send(503, "", "");
        return;
    }
    Serial.printf("CAPTURE OK %dx%d %db\n", frame->getWidth(), frame->getHeight(),
                  static_cast<int>(frame->size()));

    server.setContentLength(frame->size());
    server.send(200, "image/jpeg");
    WiFiClient client = server.client();
    frame->writeTo(client);
}

void
handlePictureSignal() {
    if (!esp32cam::Camera.changeResolution(hiRes)) {
        Serial.println("SET-HI-RES FAIL");
    }
    takeAndSendPicture();
}

void sendDetectionSignal() {
    Serial.println("Sending signal...");
    mqttClient.beginMessage(publishTopic);
    mqttClient.print("");
    mqttClient.endMessage();
}

void onResult(int messageLen) {
    while (mqttClient.available() and detecting) {
        char result = (char) mqttClient.read();
        digitalWrite(yellowLedPin, LOW);
        if (result == '1') {
            digitalWrite(greenLedPin, HIGH);
        } else if (result == '0' or result == '2') {
            digitalWrite(redLedPin, HIGH);
        }
    }
    delay(2000);
    digitalWrite(redLedPin, LOW);
    digitalWrite(greenLedPin, LOW);
    detecting = false;
}

void processButton() {
    int value = digitalRead(buttonPin);
    if (value == HIGH and detecting != true) {
        detecting = true;
        digitalWrite(yellowLedPin, HIGH);
        sendDetectionSignal();
    }
};

void
setup() {
    Serial.begin(115200);
    Serial.println();

    {
        using namespace esp32cam;
        Config cfg;
        cfg.setPins(pins::AiThinker);
        cfg.setResolution(hiRes);
        cfg.setBufferCount(2);
        cfg.setJpeg(80);

        bool ok = Camera.begin(cfg);
        Serial.println(ok ? "CAMERA OK" : "CAMERA FAIL");
    }

    WiFi.persistent(false);
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
    }
    Serial.println("\nSERVER ON");
    Serial.print("http://");
    Serial.print(WiFi.localIP());
    Serial.println("/capture.jpg");

    server.on("/capture.jpg", handlePictureSignal);


    server.begin();

    pinMode(buttonPin, INPUT);
    pinMode(redLedPin, OUTPUT);
    pinMode(greenLedPin, OUTPUT);
    pinMode(yellowLedPin, OUTPUT);

    Serial.print("Attempting to connect to the MQTT broker: ");
    Serial.println(broker);

    while (!mqttClient.connect(broker, 1883)) {
        Serial.print("MQTT connection failed! Error code = ");
        Serial.println(mqttClient.connectError());
        delay(1000);
    }
    mqttClient.subscribe(resultTopic);
    mqttClient.onMessage(onResult);
    Serial.println("You're connected to the MQTT broker!");
}

void
loop() {
    server.handleClient();
    processButton();
    mqttClient.poll();
}