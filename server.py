import os
import sqlite3
import csv
import io
from flask import Flask, jsonify, render_template, request, Response

app = Flask(__name__, template_folder='templates')
DB_FILE = "sensor_data.db"

# --- GLOBAL STATE ---
recording = False
live_buffer = [] 

# NEW: Calibration State
latest_raw_data = {}      # Keeps track of the exact raw numbers coming from the ESP32s
calibration_offsets = {}  # Holds the "Tare" values

# --- DATABASE SETUP ---
def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute(''' 
            CREATE TABLE IF NOT EXISTS sensor_readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT,
                timestamp TEXT,
                accel_x REAL, accel_y REAL,
                incl_beam REAL, incl_col REAL,
                disp REAL,
                strain REAL
            )
        ''')
        conn.commit()

init_db()

# --- ROUTES ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/data')
def get_data():
    return jsonify(live_buffer)

@app.route('/status')
def get_status():
    return jsonify({"recording": recording})

@app.route('/toggle_record', methods=['POST'])
def toggle_record():
    global recording
    recording = not recording
    return jsonify({"recording": recording})

# NEW: The Tare Endpoint
@app.route('/calibrate', methods=['POST'])
def calibrate_sensors():
    global calibration_offsets, latest_raw_data
    # Take a snapshot of the latest raw data and lock it in as the new offset
    for dev_id, raw_vals in latest_raw_data.items():
        calibration_offsets[dev_id] = raw_vals.copy()
    return jsonify({"message": "Sensors Tared Successfully!"})

@app.route('/update', methods=['POST'])
def update_sensor():
    global live_buffer, recording, latest_raw_data, calibration_offsets
    try:
        data = request.get_json()
        if not data or not isinstance(data, list):
            return jsonify({"error": "Invalid format"}), 400
        
        new_rows = []
        for item in data:
            dev_id = item.get('device_id', 'Unknown')
            
            # 1. Update the background raw tracker
            latest_raw_data[dev_id] = {
                'accel_x': item.get('accel_x', 0),
                'accel_y': item.get('accel_y', 0),
                'incl_beam': item.get('incl_beam', 0),
                'incl_col': item.get('incl_col', 0),
                'disp': item.get('disp', 0),
                'strain': item.get('strain', 0)
            }
            
            # 2. Get the specific offsets for this node (default to 0 if not tared yet)
            offsets = calibration_offsets.get(dev_id, {})
            
            # 3. Apply the offset math before saving
            row = {
                "device_id": dev_id,
                "timestamp": item.get('timestamp'),
                "accel_x": item.get('accel_x', 0) - offsets.get('accel_x', 0),
                "accel_y": item.get('accel_y', 0) - offsets.get('accel_y', 0),
                "incl_beam": item.get('incl_beam', 0) - offsets.get('incl_beam', 0),
                "incl_col": item.get('incl_col', 0) - offsets.get('incl_col', 0),
                "disp": item.get('disp', 0) - offsets.get('disp', 0),
                "strain": item.get('strain', 0) - offsets.get('strain', 0)
            }
            new_rows.append(row)

        live_buffer.extend(new_rows)
        if len(live_buffer) > 250:
            live_buffer = live_buffer[-250:] 

        if recording:
            with sqlite3.connect(DB_FILE) as conn:
                cursor = conn.cursor()
                columns = ', '.join(new_rows[0].keys())
                placeholders = ', '.join(['?'] * len(new_rows[0]))
                values = [list(r.values()) for r in new_rows]
                
                sql = f"INSERT INTO sensor_readings ({columns}) VALUES ({placeholders})"
                cursor.executemany(sql, values)
                conn.commit()

        return jsonify({"message": "Received"}), 200

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/download')
def download_data():
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM sensor_readings ORDER BY timestamp ASC")
        rows = cursor.fetchall()
        headers = [d[0] for d in cursor.description]
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows(rows)
        return Response(output.getvalue(), mimetype="text/csv", headers={"Content-disposition": "attachment; filename=sensor_data.csv"})

@app.route('/clear_data', methods=['POST'])
def clear_data():
    with sqlite3.connect(DB_FILE) as conn:
        conn.cursor().execute("DELETE FROM sensor_readings")
    return jsonify({"message": "Cleared"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
