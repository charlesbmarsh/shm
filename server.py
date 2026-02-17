# -*- coding: utf-8 -*-
import os
import sqlite3
import csv
import io
from flask import Flask, jsonify, render_template, request, Response
from datetime import datetime, timedelta

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
        # FIXED: Removed 'UNIQUE' from sync_id so we don't overwrite data
        cursor.execute(''' 
            CREATE TABLE IF NOT EXISTS sensor_readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                sync_id TEXT, 
                accel_x REAL, accel_y REAL, accel_z REAL,
                incl_beam REAL, incl_col REAL,
                disp REAL,
                strain_1 REAL, strain_2 REAL
            )
        ''')
        conn.commit()

init_db()

# --- ROUTES ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/update', methods=['POST'])
def update_sensor():
    global live_buffer, recording
    try:
        data = request.get_json()
        if not data or not isinstance(data, list):
            return jsonify({"error": "Invalid format"}), 400
        
        # We expect a list of 15 objects. 
        # The last object is "now", the previous is "now - 66ms", etc.
        base_time = datetime.now()
        
        # We process the list in reverse order to assign timestamps backwards
        # But the list comes in [oldest, ..., newest], so we handle accordingly.
        num_samples = len(data)
        time_step = 0.066 # 66ms per sample
        
        new_rows = []

        for i, item in enumerate(data):
            # Calculate timestamp: (Now) - (TimeStep * (Total - i - 1))
            offset = time_step * (num_samples - 1 - i)
            row_time = base_time - timedelta(seconds=offset)
            timestamp_str = row_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

            row_data = {
                "sync_id": item.get("sync_id", "0"),
                "timestamp": timestamp_str,
                "accel_x": item.get("accel_x"),
                "accel_y": item.get("accel_y"),
                "accel_z": item.get("accel_z"),
                "incl_beam": item.get("incl_beam"),
                "incl_col": item.get("incl_col"),
                "disp": item.get("disp"), # Note: ESP32 sends 'disp', DB uses 'disp'
                "strain_1": item.get("strain_1"),
                "strain_2": item.get("strain_2")
            }
            new_rows.append(row_data)

        # 2. Update Buffer (Extend with all new rows)
        live_buffer.extend(new_rows)
        # Keep buffer manageable (last 50 points)
        if len(live_buffer) > 50:
            live_buffer = live_buffer[-50:]

        # 3. Save to DB
        if recording:
            with sqlite3.connect(DB_FILE) as conn:
                cursor = conn.cursor()
                sql = '''INSERT INTO sensor_readings 
                         (timestamp, sync_id, accel_x, accel_y, accel_z, incl_beam, incl_col, disp, strain_1, strain_2) 
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'''
                
                # Prepare batch insert
                batch_values = []
                for r in new_rows:
                    batch_values.append((
                        r['timestamp'], r['sync_id'], 
                        r['accel_x'], r['accel_y'], r['accel_z'], 
                        r['incl_beam'], r['incl_col'], r['disp'], 
                        r['strain_1'], r['strain_2']
                    ))
                
                cursor.executemany(sql, batch_values)
                conn.commit()

        return jsonify({"message": f"Received {num_samples} samples"}), 200

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

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

@app.route('/download')
def download_data():
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM sensor_readings")
        rows = cursor.fetchall()
        headers = [description[0] for description in cursor.description]
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows(rows)
        
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-disposition": f"attachment; filename=sensor_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"}
        )

@app.route('/clear_data', methods=['POST'])
def clear_data():
    with sqlite3.connect(DB_FILE) as conn:
        conn.cursor().execute("DELETE FROM sensor_readings")
    return jsonify({"message": "Cleared"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
