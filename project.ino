#include <SPI.h>
#include <WiFiNINA.h>
#include <PubSubClient.h>
#include <MFRC522.h>
#include <Servo.h>

// WiFi credentials for connecting to the local network
const char* ssid = "Redmi Note 10S";       // WiFi network name (SSID)
const char* password = "12345678";         // WiFi network password

// MQTT server and topic configurations
const char* mqtt_server = "192.168.137.182";  // IP address of the MQTT broker
const char* rfid_topic = "parking-system/rfid";  // Topic to publish RFID tags
const char* servo_topic = "parking-system/servo";  // Topic to subscribe for servo control commands

// RFID reader pins and initialization
#define SS_PIN 10    // RFID reader Slave Select (SS) pin
#define RST_PIN 9    // RFID reader Reset pin
MFRC522 rfid(SS_PIN, RST_PIN);  // Create an instance of the MFRC522 class

// Servo motor setup
Servo servo;  // Create a Servo object

// MQTT and WiFi client setup
WiFiClient wifiClient;
PubSubClient client(wifiClient);

void setup() {
  Serial.begin(9600);       // Initialize serial communication at 9600 bps
  SPI.begin();              // Initialize SPI communication for the RFID reader
  rfid.PCD_Init();          // Initialize the RFID reader
  
  // Attach the servo to pin 6
  servo.attach(6);
  servo.write(0);           // Set the servo to its initial position (0 degrees)
  
  // Connect to the WiFi network
  connectWiFi();

  // Configure the MQTT client
  client.setServer(mqtt_server, 1883);  // Set the MQTT broker and port
  client.setCallback(mqttCallback);    // Set the callback function for incoming messages
  reconnectMQTT();                     // Connect to the MQTT broker
}

void loop() {
  // Ensure MQTT connection stays active
  if (!client.connected()) {
    reconnectMQTT();  // Reconnect if disconnected
  }
  client.loop();  // Handle incoming MQTT messages
  
  // Check for a new RFID card
  if (rfid.PICC_IsNewCardPresent() && rfid.PICC_ReadCardSerial()) {
    String rfidTag = "";
    
    // Convert RFID UID to a hexadecimal string
    for (byte i = 0; i < rfid.uid.size; i++) {
      String byteStr = String(rfid.uid.uidByte[i], HEX);  // Convert each byte to hex
      if (byteStr.length() == 1) {
        byteStr = "0" + byteStr;  // Pad single-digit hex values with a leading zero
      }
      rfidTag += byteStr;
    }
    
    Serial.print("RFID Tag: ");
    Serial.println(rfidTag);

    // Publish the RFID tag to the MQTT topic
    client.publish(rfid_topic, rfidTag.c_str());
    
    // Halt communication with the card
    rfid.PICC_HaltA();
    delay(2000);  // Delay to avoid repeated scans of the same card
  }
}

// Connect to the WiFi network
void connectWiFi() {
  Serial.print("Connecting to WiFi...");
  while (WiFi.begin(ssid, password) != WL_CONNECTED) {
    delay(1000);
    Serial.print(".");  // Indicate ongoing connection attempt
  }
  Serial.println("Connected to WiFi!");
}

// Reconnect to the MQTT broker if disconnected
void reconnectMQTT() {
  while (!client.connected()) {
    Serial.print("Connecting to MQTT...");
    if (client.connect("ArduinoClient")) {  // Attempt to connect with a client ID
      Serial.println("Connected to MQTT broker!");
      client.subscribe(servo_topic);       // Subscribe to the servo control topic
    } else {
      Serial.print("Failed to connect, rc=");
      Serial.println(client.state());      // Print the error code
      delay(2000);                         // Wait before retrying
    }
  }
}

// Callback function for handling incoming MQTT messages
void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String message = "";
  for (int i = 0; i < length; i++) {
    message += (char)payload[i];  // Construct the message from payload bytes
  }
  Serial.print("Message received on topic ");
  Serial.print(topic);
  Serial.print(": ");
  Serial.println(message);

  // Check if the message is for servo control
  if (String(topic) == servo_topic && message == "rotate") {
    openGate();  // Trigger the servo to open the gate
  }
}

// Function to control the servo for opening and closing the gate
void openGate() {
  Serial.println("Opening gate...");
  servo.write(90);  // Rotate the servo to 90 degrees
  delay(10000);     // Keep the gate open for 10 seconds
  servo.write(0);   // Return the servo to 0 degrees (closed position)
  Serial.println("Gate closed.");
}
