import os
import sqlite3
import csv
import io
from flask import Flask, jsonify, render_template, request, Response
from datetime import datetime

app = Flask(__name__, template_folder='templates')
DB_FILE = "sensor_data.db"

# --- GLOBAL STATE ---
recording = False
live_buffer = [] 

# --- DATABASE SETUP ---
def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        # Ensuring schema matches your incoming data structure
        cursor.execute(''' 
            CREATE TABLE IF NOT EXISTS sensor_readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                sync_id TEXT,
                accel_x REAL, accel_y REAL,
                incl_beam REAL, incl_col REAL,
                disp REAL,
                strain REAL
            )
        ''')
        conn.commit()

init_db()

# --- ROUTES ---

@app.route('/update', methods=['POST'])
def update_sensor():
    global live_buffer, recording
    try:
        data = request.get_json()
        if not data or not isinstance(data, list):
            return jsonify({"error": "Invalid format"}), 400
        
        # Process each reading in the batch
        for item in data:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            
            # Extract fields directly from the JSON keys sent by ESP32
            row = {
                "timestamp": timestamp,
                "sync_id": item.get('sync_id'),
                "accel_x": item.get('accel_x'),
                "accel_y": item.get('accel_y'),
                "incl_beam": item.get('incl_beam'),
                "incl_col": item.get('incl_col'),
                "disp": item.get('disp'),
                "strain": item.get('strain') # Added strain here
            }

            # Update Buffer
            live_buffer.append(row)
            if len(live_buffer) > 50:
                live_buffer.pop(0) 

            # Save to DB if recording
            if recording:
                with sqlite3.connect(DB_FILE) as conn:
                    cursor = conn.cursor()
                    columns = ', '.join(row.keys())
                    placeholders = ', '.join(['?'] * len(row))
                    values = list(row.values())
                    sql = f"INSERT INTO sensor_readings ({columns}) VALUES ({placeholders})"
                    cursor.execute(sql, values)
                    conn.commit()

        return jsonify({"message": "Received"}), 200

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

# ... (keep other routes: /, /data, /status, /toggle_record, /download, /clear_data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
