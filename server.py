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
                sync_id TEXT,
                accel_x REAL, accel_y REAL, accel_z REAL,
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

@app.route('/update', methods=['POST'])
def update_sensor():
    global live_buffer, recording
    try:
        data = request.get_json()
        if not data or not isinstance(data, list):
            return jsonify({"error": "Invalid format"}), 400
        
        for item in data:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            row = {
                "timestamp": timestamp,
                "sync_id": item.get('sync_id'),
                "accel_x": item.get('accel_x'),
                "accel_y": item.get('accel_y'),
                "accel_z": item.get('accel_z'),
                "incl_beam": item.get('incl_beam'),
                "incl_col": item.get('incl_col'),
                "disp": item.get('disp'),
                "strain": item.get('strain')
            }
            live_buffer.append(row)
            if len(live_buffer) > 50: live_buffer.pop(0) 
            if recording:
                with sqlite3.connect(DB_FILE) as conn:
                    cursor = conn.cursor()
                    columns = ', '.join(row.keys())
                    placeholders = ', '.join(['?'] * len(row))
                    cursor.execute(f"INSERT INTO sensor_readings ({columns}) VALUES ({placeholders})", list(row.values()))
                    conn.commit()
        return jsonify({"message": "Received"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/download')
def download_data():
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM sensor_readings")
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
