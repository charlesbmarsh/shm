# -*- coding: utf-8 -*-
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
        cursor.execute(''' 
            CREATE TABLE IF NOT EXISTS sensor_readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                sync_id TEXT UNIQUE,
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
        
        # 1. Parse Data
        sync_id = data[0].get('sync_id')
        
        # --- TIMESTAMP UPDATE IS HERE ---
        # Format: YYYY-MM-DD HH:MM:SS.mmm
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        
        mapping = {
            "accel_x": "accel_x", "accel_y": "accel_y", "accel_z": "accel_z",
            "incl_beam": "incl_beam", "incl_col": "incl_col",
            "disp_1": "disp", "strain_1": "strain_1", "strain_2": "strain_2"
        }

        row_data = {"sync_id": sync_id, "timestamp": timestamp}
        
        for key in mapping.values():
            row_data[key] = None

        for item in data:
            s_id = item.get('sensor_id')
            val = item.get('value')
            if s_id in mapping:
                row_data[mapping[s_id]] = val

        # 2. Update Buffer
        live_buffer.append(row_data)
        if len(live_buffer) > 50:
            live_buffer.pop(0) 

        # 3. Save to DB
        if recording:
            with sqlite3.connect(DB_FILE) as conn:
                cursor = conn.cursor()
                columns = ', '.join(row_data.keys())
                placeholders = ', '.join(['?'] * len(row_data))
                values = list(row_data.values())
                sql = f"INSERT OR REPLACE INTO sensor_readings ({columns}) VALUES ({placeholders})"
                cursor.execute(sql, values)
                conn.commit()

        return jsonify({"message": "Received"}), 200

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
