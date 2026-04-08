from flask import Flask, render_template, request, redirect, session, url_for
import sqlite3
import json
from datetime import datetime
import PyPDF2
import re

app = Flask(__name__)
app.secret_key = 'super_secret_key'

def get_db():
    conn = sqlite3.connect('college.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS settings 
                 (id INTEGER PRIMARY KEY, academic_year TEXT, semester TEXT)''')
    c.execute("SELECT COUNT(*) FROM settings")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO settings (academic_year, semester) VALUES (?, ?)", ("2023-2024", "Odd"))
    c.execute('''CREATE TABLE IF NOT EXISTS classes (id INTEGER PRIMARY KEY, name TEXT UNIQUE)''')
    c.execute('''CREATE TABLE IF NOT EXISTS exams (id INTEGER PRIMARY KEY, name TEXT UNIQUE)''')
    c.execute('''CREATE TABLE IF NOT EXISTS subjects (id INTEGER PRIMARY KEY, name TEXT, class_name TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS students (id INTEGER PRIMARY KEY, roll_no TEXT, name TEXT, class_name TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS marks (id INTEGER PRIMARY KEY, student_id INTEGER, exam TEXT, subject TEXT, mark TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS exam_dates (
        id INTEGER PRIMARY KEY, class_name TEXT, exam TEXT, subject TEXT, exam_date TEXT)''')
    conn.commit()
    conn.close()

init_db()

@app.route('/', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == 'user' and password == 'user123':
            session['logged_in'] = True
            return redirect(url_for('dashboard'))
        else:
            error = "Invalid Credentials! Use admin / admin123"
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if 'logged_in' not in session: 
        return redirect(url_for('login'))
    
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT name FROM classes")
    classes = [row[0] for row in c.fetchall()]
    c.execute("SELECT name FROM exams")
    exams = [row[0] for row in c.fetchall()]
    
    class_subject_map = {}
    for cls in classes:
        c.execute("SELECT name FROM subjects WHERE class_name=?", (cls,))
        class_subject_map[cls] = [row[0] for row in c.fetchall()]
        
    conn.close()
    return render_template('index.html', classes=classes, exams=exams, class_subject_map=json.dumps(class_subject_map))

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if request.method == 'POST' and request.form.get('action') == 'login':
        username = request.form.get('username')
        password = request.form.get('password')

        if username == 'admin' and password == '1234':
            session['admin_logged_in'] = True
            return redirect(url_for('admin'))
        else:
            return render_template('admin.html', login_error="Invalid Username or Password")
        
    if not session.get('admin_logged_in'):
        return render_template('admin.html')
    
   
    
    conn = get_db()
    c = conn.cursor()

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'update_settings':
            year = request.form.get('academic_year')
            sem = request.form.get('semester')
            c.execute("UPDATE settings SET academic_year=?, semester=? WHERE id=1", (year, sem))
        if action == 'add_class':
            class_name = request.form.get('class_name')
            if class_name:
                c.execute("INSERT OR IGNORE INTO classes (name) VALUES (?)", (class_name,))
        elif action == 'add_exam':
            exam_name = request.form.get('exam_name')
            if exam_name:
                c.execute("INSERT OR IGNORE INTO exams (name) VALUES (?)", (exam_name,))
        elif action == 'add_subject':
            subject_name = request.form.get('subject_name')
            class_name = request.form.get('class_name')
            if subject_name and class_name:
                c.execute("INSERT INTO subjects (name, class_name) VALUES (?, ?)", (subject_name, class_name))
        elif action == 'add_student':
            roll_no = request.form.get('roll_no')
            student_name = request.form.get('student_name')
            class_name = request.form.get('class_name')
            if roll_no and student_name and class_name:
                c.execute("INSERT INTO students (roll_no, name, class_name) VALUES (?, ?, ?)", 
                         (roll_no, student_name, class_name))
        elif action == 'delete_class':
            cls = request.form.get('class_name')
            if cls:
                c.execute("DELETE FROM classes WHERE name=?", (cls,))
                c.execute("DELETE FROM subjects WHERE class_name=?", (cls,))
                c.execute("DELETE FROM students WHERE class_name=?", (cls,))
        elif action == 'delete_exam':
            exam_name = request.form.get('exam_name')
            if exam_name:
                c.execute("DELETE FROM exams WHERE name=?", (exam_name,))
        elif action == 'delete_subject':
            subject_id = request.form.get('id')
            if subject_id:
                c.execute("DELETE FROM subjects WHERE id=?", (subject_id,))
        elif action == 'delete_student':
            student_id = request.form.get('id')
            if student_id:
                c.execute("DELETE FROM students WHERE id=?", (student_id,))
                
        # --- NEW PDF UPLOAD LOGIC ---
        elif action == 'upload_pdf':
            class_name = request.form.get('class_name')
            pdf_file = request.files.get('pdf_file')
            
            if class_name and pdf_file and pdf_file.filename.endswith('.pdf'):
                try:
                    reader = PyPDF2.PdfReader(pdf_file)
                    text = ""
                    for page in reader.pages:
                        extracted = page.extract_text()
                        if extracted:
                            text += extracted + "\n"
                    
                    c.execute("SELECT roll_no FROM students WHERE class_name=?", (class_name,))
                    existing_rolls = [row[0] for row in c.fetchall()]
                    
                    # Regex Pattern: Looks for 5-15 Alphanumeric characters (Roll No), followed by space and Name
                    pattern = r'\b([A-Za-z0-9]{5,15})\s+([A-Za-z\s\.]{3,50})\b'
                    
                    for line in text.split('\n'):
                        match = re.search(pattern, line)
                        if match:
                            roll_no = match.group(1).strip().upper()
                            name = match.group(2).strip().upper()
                            # Clean up name: remove any accidental numbers stuck at the end
                            name = re.sub(r'\d+', '', name).strip()
                            
                            if roll_no not in existing_rolls and len(name) > 2:
                                c.execute("INSERT INTO students (roll_no, name, class_name) VALUES (?, ?, ?)", 
                                         (roll_no, name, class_name))
                                existing_rolls.append(roll_no)
                except Exception as e:
                    print(f"PDF Error: {e}")
            
        conn.commit()
        return redirect(url_for('admin'))
    c.execute("SELECT academic_year, semester FROM settings WHERE id=1")
    current_settings = c.fetchone()
    c.execute("SELECT * FROM classes")
    classes = c.fetchall()
    c.execute("SELECT * FROM exams")
    exams = c.fetchall()
    c.execute("SELECT id, name, class_name FROM subjects")
    subjects = c.fetchall()
    c.execute("SELECT id, roll_no, name, class_name FROM students")
    students = c.fetchall()
    conn.close()
    
    return render_template('admin.html', classes=classes, exams=exams, subjects=subjects, students=students,settings=current_settings)

@app.route('/enter_marks', methods=['GET', 'POST'])
def enter_marks():
    if 'logged_in' not in session: 
        return redirect(url_for('login'))
    
    class_name = request.args.get('class_name')
    exam = request.args.get('exam')
    subject = request.args.get('subject')

    if not all([class_name, exam, subject]):
        return redirect(url_for('dashboard'))

    conn = get_db()
    c = conn.cursor()
    
    if request.method == 'POST':
        for student_id, mark in request.form.items():
            if student_id.isdigit(): 
                c.execute("DELETE FROM marks WHERE student_id=? AND exam=? AND subject=?", 
                         (student_id, exam, subject))
                if mark.strip() != "":
                    c.execute("INSERT INTO marks (student_id, exam, subject, mark) VALUES (?, ?, ?, ?)", 
                              (student_id, exam, subject, mark.strip().upper()))
        
        exam_date = request.form.get('exam_date')
        if exam_date:
            c.execute("DELETE FROM exam_dates WHERE class_name=? AND exam=? AND subject=?", 
                     (class_name, exam, subject))
            c.execute("INSERT INTO exam_dates (class_name, exam, subject, exam_date) VALUES (?, ?, ?, ?)", 
                     (class_name, exam, subject, exam_date))
        
        conn.commit()
        conn.close()
        return redirect(url_for('dashboard'))

    c.execute("SELECT id, roll_no, name FROM students WHERE class_name=?", (class_name,))
    students = c.fetchall()
    
    existing_marks = {}
    for st in students:
        c.execute("SELECT mark FROM marks WHERE student_id=? AND exam=? AND subject=?", 
                 (st[0], exam, subject))
        res = c.fetchone()
        existing_marks[st[0]] = res[0] if res else ""
    
    c.execute("SELECT exam_date FROM exam_dates WHERE class_name=? AND exam=? AND subject=?", 
             (class_name, exam, subject))
    date_res = c.fetchone()
    existing_date = date_res[0] if date_res else ""
    
    conn.close()
    
    return render_template('enter_marks.html', students=students, exam=exam, subject=subject, class_name=class_name, existing_marks=existing_marks, existing_date=existing_date)

@app.route('/report')
def report():
    if 'logged_in' not in session: 
        return redirect(url_for('login'))
    
    class_name = request.args.get('class_name')
    exam = request.args.get('exam')
    
    if not all([class_name, exam]):
        return redirect(url_for('dashboard'))
    
    conn = get_db()
    c = conn.cursor()
    
    c.execute("SELECT id, roll_no, name FROM students WHERE class_name=?", (class_name,))
    students = c.fetchall()

    c.execute("SELECT name FROM subjects WHERE class_name=?", (class_name,))
    active_subjects = [row[0] for row in c.fetchall()]
    
    # 🔥 NEW: subject-wise tracking
    subject_totals = {sub: 0 for sub in active_subjects}
    subject_counts = {sub: 0 for sub in active_subjects}
    subject_pass = {sub: 0 for sub in active_subjects}
    
    report_data = []

    for idx, student in enumerate(students, 1):
        student_marks = []
        fail_count = 0

        for sub in active_subjects:
            c.execute("SELECT mark FROM marks WHERE student_id=? AND exam=? AND subject=?", 
                     (student[0], exam, sub))
            res = c.fetchone()
            val = res[0] if res else "-"

            student_marks.append(val)

            # 🔥 NEW: calculation
            if val != "-" and val != "AB":
                subject_totals[sub] += int(val)
                subject_counts[sub] += 1

                if int(val) >= 25:
                    subject_pass[sub] += 1

            # existing fail logic
            if val == 'AB' or (val.isdigit() and int(val) < 25):
                fail_count += 1

        report_data.append({
            'sno': idx,
            'roll_no': student[1],
            'name': student[2],
            'marks': student_marks,
            'failed': fail_count
        })

    
    subject_percentage = {}

    for sub in active_subjects:
        if subject_counts[sub] > 0:
            subject_percentage[sub] = round((subject_pass[sub] / subject_counts[sub]) * 100, 2)
        else:
            subject_percentage[sub] = 0

    conn.close()

    return render_template(
        'report.html',
        report_data=report_data,
        exam=exam,
        class_name=class_name,
        subjects=active_subjects,
        subject_percentage=subject_percentage   # 🔥 pass to HTML
    )

@app.route('/subject_analysis')
def subject_analysis():
    if 'logged_in' not in session: return redirect(url_for('login'))
    
    class_name = request.args.get('class_name')
    exam = request.args.get('exam')
    subject = request.args.get('subject')
    
    if not all([class_name, exam, subject]): return redirect(url_for('dashboard'))
    
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, roll_no, name FROM students WHERE class_name=?", (class_name,))
    students = c.fetchall()
    
    marks_list = []
    appeared = 0
    passed = 0
    failed = 0
    
    for student in students:
        c.execute("SELECT mark FROM marks WHERE student_id=? AND exam=? AND subject=?", (student[0], exam, subject))
        res = c.fetchone()
        mark = res[0] if res else "-"
        marks_list.append({'roll_no': student[1], 'name': student[2], 'mark': mark})
        
        if mark != "-" and mark != "AB":
            appeared += 1
            if mark.isdigit() and int(mark) >= 25: passed += 1
            elif mark.isdigit() and int(mark) < 25: failed += 1
        elif mark == "AB":
            appeared += 1
            failed += 1
            
    pass_percentage = (passed / appeared * 100) if appeared > 0 else 0
    
    c.execute("SELECT exam_date FROM exam_dates WHERE class_name=? AND exam=? AND subject=?", (class_name, exam, subject))
    date_res = c.fetchone()
    exam_date = date_res[0] if date_res else "Date not set"
    conn.close()
    
    return render_template('subject_analysis.html', class_name=class_name, exam=exam, subject=subject, exam_date=exam_date, marks_list=marks_list, total_students=len(students), appeared=appeared, passed=passed, failed=failed, pass_percentage=round(pass_percentage, 2))

if __name__ == '__main__':
    app.run(debug=True)                                                                                                       
