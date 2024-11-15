from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import firebase_admin
from firebase_admin import credentials, firestore
from paho.mqtt.client import Client
import RPi.GPIO as GPIO
from mfrc522 import SimpleMFRC522
import time

# Initialize Flask app
app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Secret key for sessions (important for flash messages)

# Initialize Firebase Admin SDK
cred = credentials.Certificate('/home/pi/firebase-credentials.json')  # Replace with your Firebase credentials path
firebase_admin.initialize_app(cred)
db = firestore.client()

# MQTT setup
MQTT_BROKER = '192.168.137.182'  # Your MQTT broker IP address
MQTT_TOPIC = 'parking-system/rfid'  # The topic to subscribe to
mqtt_client = Client()

# Store the matched user name globally
matched_user = None
last_received_rfid = None  # Stores the latest RFID from Arduino

# Initialize RFID reader
reader = SimpleMFRC522()

# Callback function to handle received MQTT messages
def on_mqtt_message(client, userdata, msg):
    global matched_user, last_received_rfid
    rfid_tag = msg.payload.decode('utf-8')
    print(f"Received RFID Tag from Arduino: {rfid_tag}")
    last_received_rfid = rfid_tag  # Update with the latest RFID received

    # Query Firestore to check if the RFID tag exists
    user_ref = db.collection('users').where('rfid_tag', '==', rfid_tag).stream()
    user_found = False
    for user in user_ref:
        name = user.to_dict().get('name')
        matched_user = name  # Store the matched user name
        print(f"Match found! Welcome, {name}")
        user_found = True
        break

    if not user_found:
        matched_user = None
        print("RFID Tag not found in database.")

# MQTT Client setup
mqtt_client.on_message = on_mqtt_message
mqtt_client.connect(MQTT_BROKER, 1883)
mqtt_client.subscribe(MQTT_TOPIC)
mqtt_client.loop_start()

# Function to read RFID tag from the device (connected RFID reader)
def read_rfid_from_device():
    try:
        print("Place your RFID tag near the scanner...")
        rfid_id, _ = reader.read()
        hex_rfid = hex(rfid_id)[2:-2].lower()  # Convert ID to hexadecimal
        print(f"RFID Tag Scanned: {hex_rfid}")
        return hex_rfid
    except Exception as e:
        print(f"Error reading RFID tag: {str(e)}")
        return None
    finally:
        GPIO.cleanup()

# Function to retrieve RFID tag from Arduino over MQTT
def read_rfid_from_arduino():
    global last_received_rfid
    last_received_rfid = None  # Reset before waiting
    print("Waiting for RFID from Arduino...")

    # Wait until the Arduino publishes an RFID tag to the MQTT topic
    timeout = time.time() + 10  # 10-second timeout
    while last_received_rfid is None and time.time() < timeout:
        time.sleep(0.1)  # Poll every 0.1 seconds

    if last_received_rfid:
        print(f"RFID Tag received from Arduino: {last_received_rfid}")
        return last_received_rfid
    else:
        print("Timeout: No RFID tag received from Arduino.")
        return None

# Route to scan RFID tag from the device (connected RFID reader)
@app.route('/scan_rfid')
def scan_rfid():
    rfid_tag = read_rfid_from_device()
    if rfid_tag:
        return jsonify({'rfid_tag': rfid_tag})
    else:
        flash("Failed to scan RFID tag.", "error")
        return redirect(url_for('index'))

# Route to scan RFID tag from Arduino (via MQTT)
@app.route('/scan_rfid_arduino')
def scan_rfid_arduino():
    rfid_tag = read_rfid_from_arduino()
    if rfid_tag:
        return jsonify({'rfid_tag': rfid_tag})
    else:
        flash("Failed to receive RFID tag from Arduino.", "error")
        return redirect(url_for('verify_user'))

# Flask route to display index page (Home)
@app.route('/')
def index():
    return render_template('index.html', matched_user=matched_user)

# Flask route for verifying user
@app.route('/verify_user')
def verify_user():
    return render_template('verify_user.html')

# Route for adding user
@app.route('/add_user')
def add_user():
    return render_template('add_user.html')

# Route for handling the form submission of verified RFID
@app.route('/verify_user_action', methods=['POST'])
def verify_user_action():
    rfid_tag = request.form['rfid_tag']
    
    # Check if the RFID tag exists in Firestore
    user_ref = db.collection('users').where('rfid_tag', '==', rfid_tag.lower()).stream()
    user_found = False
    for user in user_ref:
        name = user.to_dict().get('name')
        global matched_user
        matched_user = name  # Store the matched user name
        user_found = True
        break

    if user_found:
        return redirect(url_for('parking_status'))
    else:
        flash("RFID Tag not found. Please try again.", 'error')
        return redirect(url_for('verify_user'))

# Route for adding user action (adding RFID and name to Firestore)
@app.route('/add_user_action', methods=['POST'])
def add_user_action():
    rfid_tag = request.form['rfid_tag']
    name = request.form['name']

    # Add the user to Firestore
    db.collection('users').add({'rfid_tag': rfid_tag.lower(), 'name': name})

    flash(f"User {name} added successfully!", 'success')
    return redirect(url_for('index'))

# Route to display parking status after user verification
@app.route('/parking_status')
def parking_status():
    return render_template('parking_status.html', matched_user=matched_user)
@app.route('/check_verification')
def check_verification():
    global matched_user
    if matched_user:
        return jsonify({'status': 'verified', 'name': matched_user})
    else:
        return jsonify({'status': 'not_verified'})

@app.route('/open_gate', methods=['POST'])
def open_gate():
    # Publish a message to the MQTT topic to trigger the servo
    mqtt_client.publish('parking-system/servo', 'rotate')
    flash("Gate is opening...", "info")
    return jsonify({'status': 'Gate opening triggered'})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)  # Run the server

