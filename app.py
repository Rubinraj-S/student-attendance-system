import logging
from flask import Flask, request, jsonify, session, render_template_string, send_from_directory
import sqlite3
from flask_bcrypt import Bcrypt
from flask_cors import CORS
from datetime import datetime
import math
import csv
import os
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from io import StringIO
from flask_mail import Mail, Message
import random
import string
from werkzeug.utils import secure_filename

# Set up logging for user activities
logging.basicConfig(filename='attendance_system.log', level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
app.secret_key = "supersecretkey"
bcrypt = Bcrypt(app)
CORS(app)

# Email Setup (for notifications)
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'your-email@gmail.com'
app.config['MAIL_PASSWORD'] = 'your-email-password'
mail = Mail(app)

# File upload folder configuration
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'csv'}

# Ensuring the upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Database initialization
def init_db():
    """Initialize the SQLite database with required tables."""
    conn = sqlite3.connect('attendance.db')
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            role TEXT
        )
    ''')

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

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            code TEXT UNIQUE
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS grades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            course_id INTEGER,
            grade TEXT,
            FOREIGN KEY(student_id) REFERENCES students(id),
            FOREIGN KEY(course_id) REFERENCES courses(id)
        )
    ''')

    cursor.execute("SELECT * FROM users WHERE username = 'admin'")
    if not cursor.fetchone():
        hashed_password = bcrypt.generate_password_hash("admin123").decode('utf-8')
        cursor.execute("INSERT INTO users (username, password, role) VALUES ('admin', ?, 'admin')", (hashed_password,))
    
    conn.commit()
    conn.close()

init_db()

# Helper function to send a welcome email
def send_welcome_email(username):
    """Send a welcome email after user registration."""
    subject = "Welcome to the Student Attendance System"
    body = f"Hello {username},\n\nWelcome to the system! Your registration was successful."
    message = MIMEMultipart()
    message['From'] = app.config['MAIL_USERNAME']
    message['To'] = username
    message['Subject'] = subject
    message.attach(MIMEText(body, 'plain'))
    
    try:
        with smtplib.SMTP(app.config['MAIL_SERVER'], app.config['MAIL_PORT']) as server:
            server.starttls()
            server.login(app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
            server.sendmail(message['From'], message['To'], message.as_string())
            logging.info(f"Welcome email sent to {username}.")
    except Exception as e:
        logging.error(f"Error sending welcome email to {username}: {e}")

# User management
@app.route('/register', methods=['POST'])
def register():
    """Register a new user."""
    data = request.json
    username, password, role = data.get('username'), data.get('password'), data.get('role')
    
    if not username or not password or not role:
        return jsonify({"error": "All fields are required!"}), 400

    if len(username) < 4:
        return jsonify({"error": "Username must be at least 4 characters long!"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters long!"}), 400

    # Check for valid username format
    if not re.match("^[a-zA-Z0-9_]+$", username):
        return jsonify({"error": "Username can only contain letters, numbers, and underscores."}), 400

    hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
    conn = sqlite3.connect('attendance.db')
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", 
                       (username, hashed_password, role))
        conn.commit()
        logging.info(f"New user {username} registered with role {role}.")
        send_welcome_email(username)
        return jsonify({"message": "User registered successfully!"}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "Username already exists!"}), 400
    finally:
        conn.close()

@app.route('/login', methods=['POST'])
def login():
    """Login an existing user."""
    data = request.json
    username, password = data.get('username'), data.get('password')
    conn = sqlite3.connect('attendance.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()

    if user and bcrypt.check_password_hash(user[2], password):
        session['user'] = {"id": user[0], "username": user[1], "role": user[3]}
        logging.info(f"User {username} logged in with role {user[3]}.")
        return jsonify({"message": "Login successful!", "user": session['user']}), 200
    return jsonify({"error": "Invalid username or password!"}), 401

@app.route('/logout', methods=['POST'])
def logout():
    """Logout the current user."""
    if 'user' in session:
        logging.info(f"User {session['user']['username']} logged out.")
    session.pop('user', None)
    return jsonify({"message": "Logged out successfully!"}), 200

# Student management
@app.route('/add_student', methods=['POST'])
def add_student():
    """Add a new student."""
    if session.get('user', {}).get('role') != 'admin':
        return jsonify({"error": "Unauthorized!"}), 403
    
    data = request.json
    name, roll_number, student_class = data.get('name'), data.get('roll_number'), data.get('class')
    
    if not name or not roll_number or not student_class:
        return jsonify({"error": "All fields are required!"}), 400

    conn = sqlite3.connect('attendance.db')
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO students (name, roll_number, class) VALUES (?, ?, ?)", 
                       (name, roll_number, student_class))
        conn.commit()
        logging.info(f"New student added: {name} ({roll_number})")
        return jsonify({"message": "Student added successfully!"}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "Student with this roll number already exists!"}), 400
    finally:
        conn.close()

@app.route('/students', methods=['GET'])
def list_students():
    """List all students with pagination."""
    page = request.args.get('page', 1, type=int)
    per_page = 5  # Number of students per page
    offset = (page - 1) * per_page

    conn = sqlite3.connect('attendance.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM students LIMIT ? OFFSET ?", (per_page, offset))
    students = cursor.fetchall()
    conn.close()

    # Calculate total pages
    conn = sqlite3.connect('attendance.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM students")
    total_students = cursor.fetchone()[0]
    conn.close()

    total_pages = math.ceil(total_students / per_page)

    return jsonify({
        "students": [{"id": s[0], "name": s[1], "roll_number": s[2], "class": s[3]} for s in students],
        "total_pages": total_pages,
        "current_page": page
    })

@app.route('/update_student', methods=['PUT'])
def update_student():
    """Update a student's information."""
    data = request.json
    student_id = data.get('id')
    name = data.get('name')
    roll_number = data.get('roll_number')
    student_class = data.get('class')

    if not student_id:
        return jsonify({"error": "Student ID is required!"}), 400

    if not name or not roll_number or not student_class:
        return jsonify({"error": "All fields are required!"}), 400

    conn = sqlite3.connect('attendance.db')
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE students 
        SET name = ?, roll_number = ?, class = ? 
        WHERE id = ?
    ''', (name, roll_number, student_class, student_id))
    conn.commit()
    conn.close()

    return jsonify({"message": "Student updated successfully!"}), 200

@app.route('/delete_student', methods=['DELETE'])
def delete_student():
    """Delete a student from the system."""
    student_id = request.args.get('id')
    if not student_id:
        return jsonify({"error": "Student ID is required!"}), 400

    conn = sqlite3.connect('attendance.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM students WHERE id = ?', (student_id,))
    conn.commit()
    conn.close()

    return jsonify({"message": "Student deleted successfully!"}), 200

# Attendance management
@app.route('/mark_attendance', methods=['POST'])
def mark_attendance():
    """Mark attendance for a student."""
    data = request.json
    student_id, status = data.get('student_id'), data.get('status')
    date = datetime.now().strftime('%Y-%m-%d')

    if not student_id or not status:
        return jsonify({"error": "Student ID and status are required!"}), 400

    conn = sqlite3.connect('attendance.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO attendance (student_id, date, status) 
        VALUES (?, ?, ?)
    ''', (student_id, date, status))
    conn.commit()
    conn.close()

    return jsonify({"message": "Attendance marked successfully!"}), 201

@app.route('/attendance', methods=['GET'])
def get_attendance():
    """Get attendance records for a student."""
    student_id = request.args.get('student_id')

    if not student_id:
        return jsonify({"error": "Student ID is required!"}), 400

    conn = sqlite3.connect('attendance.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT a.date, a.status, s.name
        FROM attendance a
        JOIN students s ON a.student_id = s.id
        WHERE s.id = ?
    ''', (student_id,))
    records = cursor.fetchall()
    conn.close()

    return jsonify({
        "attendance": [{"date": r[0], "status": r[1], "name": r[2]} for r in records]
    })

# Course management
@app.route('/add_course', methods=['POST'])
def add_course():
    """Add a new course."""
    if session.get('user', {}).get('role') != 'admin':
        return jsonify({"error": "Unauthorized!"}), 403
    
    data = request.json
    name, code = data.get('name'), data.get('code')
    
    if not name or not code:
        return jsonify({"error": "All fields are required!"}), 400

    conn = sqlite3.connect('attendance.db')
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO courses (name, code) VALUES (?, ?)", 
                       (name, code))
        conn.commit()
        logging.info(f"New course added: {name} ({code})")
        return jsonify({"message": "Course added successfully!"}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "Course with this code already exists!"}), 400
    finally:
        conn.close()

@app.route('/courses', methods=['GET'])
def list_courses():
    """List all courses."""
    conn = sqlite3.connect('attendance.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM courses")
    courses = cursor.fetchall()
    conn.close()

    return jsonify({
        "courses": [{"id": c[0], "name": c[1], "code": c[2]} for c in courses]
    })

@app.route('/delete_course', methods=['DELETE'])
def delete_course():
    """Delete a course from the system."""
    course_id = request.args.get('id')
    if not course_id:
        return jsonify({"error": "Course ID is required!"}), 400

    conn = sqlite3.connect('attendance.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM courses WHERE id = ?', (course_id,))
    conn.commit()
    conn.close()

    return jsonify({"message": "Course deleted successfully!"}), 200

# Grades management
@app.route('/add_grade', methods=['POST'])
def add_grade():
    """Add a grade for a student in a course."""
    data = request.json
    student_id, course_id, grade = data.get('student_id'), data.get('course_id'), data.get('grade')

    if not student_id or not course_id or not grade:
        return jsonify({"error": "All fields are required!"}), 400

    conn = sqlite3.connect('attendance.db')
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO grades (student_id, course_id, grade) VALUES (?, ?, ?)", 
                       (student_id, course_id, grade))
        conn.commit()
        return jsonify({"message": "Grade added successfully!"}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "Grade for this student and course already exists!"}), 400
    finally:
        conn.close()

@app.route('/grades', methods=['GET'])
def get_grades():
    """Get all grades for a student."""
    student_id = request.args.get('student_id')

    if not student_id:
        return jsonify({"error": "Student ID is required!"}), 400

    conn = sqlite3.connect('attendance.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT g.grade, c.name, c.code
        FROM grades g
        JOIN courses c ON g.course_id = c.id
        WHERE g.student_id = ?
    ''', (student_id,))
    grades = cursor.fetchall()
    conn.close()

    return jsonify({
        "grades": [{"grade": g[0], "course_name": g[1], "course_code": g[2]} for g in grades]
    })

# Generate reports (Attendance Report, Grades Report, etc.)
@app.route('/generate_attendance_report', methods=['GET'])
def generate_attendance_report():
    """Generate a detailed attendance report for all students."""
    conn = sqlite3.connect('attendance.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT s.name, s.roll_number, a.date, a.status
        FROM attendance a
        JOIN students s ON a.student_id = s.id
    ''')
    report_data = cursor.fetchall()
    conn.close()

    report = "Name, Roll Number, Date, Status\n"
    for row in report_data:
        report += f"{row[0]}, {row[1]}, {row[2]}, {row[3]}\n"

    return jsonify({"report": report})

@app.route('/generate_grades_report', methods=['GET'])
def generate_grades_report():
    """Generate a detailed grades report for all students in all courses."""
    conn = sqlite3.connect('attendance.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT s.name, s.roll_number, c.name, c.code, g.grade
        FROM grades g
        JOIN students s ON g.student_id = s.id
        JOIN courses c ON g.course_id = c.id
    ''')
    report_data = cursor.fetchall()
    conn.close()

    report = "Name, Roll Number, Course Name, Course Code, Grade\n"
    for row in report_data:
        report += f"{row[0]}, {row[1]}, {row[2]}, {row[3]}, {row[4]}\n"

    return jsonify({"report": report})

# Run the Flask application
if __name__ == '__main__':
    app.run(debug=True)
