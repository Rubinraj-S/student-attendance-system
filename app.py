from flask import Flask, request, jsonify
import sqlite3
from datetime import datetime

app = Flask(__name__)

# Database setup
def init_db():
    conn = sqlite3.connect('attendance.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            roll_number TEXT UNIQUE,
            class TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            date TEXT,
            status TEXT,
            FOREIGN KEY(student_id) REFERENCES students(id)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# Add student
@app.route('/add_student', methods=['POST'])
def add_student():
    data = request.json
    conn = sqlite3.connect('attendance.db')
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO students (name, roll_number, class) VALUES (?, ?, ?)",
                       (data['name'], data['roll_number'], data['class']))
        conn.commit()
        return jsonify({"message": "Student added successfully!"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    finally:
        conn.close()

# Mark attendance
@app.route('/mark_attendance', methods=['POST'])
def mark_attendance():
    data = request.json
    conn = sqlite3.connect('attendance.db')
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO attendance (student_id, date, status) VALUES (?, ?, ?)",
                       (data['student_id'], data['date'], data['status']))
        conn.commit()
        return jsonify({"message": "Attendance marked successfully!"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    finally:
        conn.close()

# Get report
@app.route('/attendance_report/<int:student_id>', methods=['GET'])
def attendance_report(student_id):
    conn = sqlite3.connect('attendance.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT s.name, s.roll_number, a.date, a.status
        FROM attendance a
        JOIN students s ON a.student_id = s.id
        WHERE s.id = ?
    ''', (student_id,))
    records = cursor.fetchall()
    conn.close()
    return jsonify(records)

if __name__ == '__main__':
    app.run(debug=True)

