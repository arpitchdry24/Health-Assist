import os
import sqlite3
import razorpay  # Yeh install hona chahiye (pip install razorpay)
from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
from PIL import Image
from google import genai 

app = Flask(__name__)
app.secret_key = "health_assist_secret_key"

# --- RAZORPAY CONFIG (Apni Keys yahan dalo) ---
RAZORPAY_KEY_ID = "rzp_test_S5j1rugiPWxTeK"
RAZORPAY_KEY_SECRET = "BN1GvBL4pVxKQluL4M0UUoWI"
razor_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

# --- AI CONFIGURATION ---
client = genai.Client(api_key="AIzaSyBGCZuX1_3eE7JfJwemY9qQzPUMjWyUL1o")
MODEL_ID = "gemini-2.0-flash-exp" 

# --- UPLOAD CONFIG ---
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- DATABASE CONNECTION ---
def get_db_connection():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn

# --- INITIALIZE DATABASE ---
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, email TEXT UNIQUE, mobile TEXT UNIQUE, username TEXT UNIQUE, password TEXT, created_at TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS login_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, login_date TEXT, login_time TEXT)")
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            doctor TEXT,
            appointment_date TEXT,
            appointment_time TEXT,
            problem TEXT,
            amount INTEGER,
            payment_id TEXT,
            payment_status TEXT DEFAULT 'Pending',
            status TEXT DEFAULT 'Confirmed',
            created_at TEXT
        )
    """)
    cursor.execute("CREATE TABLE IF NOT EXISTS medicines (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, med_name TEXT, med_time TEXT, status TEXT DEFAULT 'Pending')")
    conn.commit()
    conn.close()

# --- ROUTES ---

@app.route('/')
def home():
    if 'username' in session: return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    message = ""
    if request.method == 'POST':
        name, email, mobile, username, password = request.form['name'], request.form['email'], request.form['mobile'], request.form['username'], request.form['password']
        hashed_password = generate_password_hash(password)
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = get_db_connection()
        try:
            conn.execute("INSERT INTO users (name, email, mobile, username, password, created_at) VALUES (?, ?, ?, ?, ?, ?)", 
                         (name, email, mobile, username, hashed_password, created_at))
            conn.commit()
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            message = "Username/Email/Mobile already exists."
        finally:
            conn.close()
    return render_template('signup.html', message=message)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username, password = request.form['username'], request.form['password']
        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if user and check_password_hash(user['password'], password):
            session['username'] = user['username']
            now = datetime.now()
            conn.execute("INSERT INTO login_logs (username, login_date, login_time) VALUES (?, ?, ?)",
                         (username, now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S")))
            conn.commit()
            conn.close()
            return redirect(url_for('dashboard'))
        return render_template('login.html', message="Invalid Credentials")
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'username' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    user_medicines = conn.execute("SELECT * FROM medicines WHERE username=? ORDER BY med_time ASC", 
                                  (session['username'],)).fetchall()
    conn.close()
    return render_template('dashboard.html', page='home', username=session['username'], medicines=user_medicines)

@app.route('/appointments', methods=['GET', 'POST'])
def appointments():
    if 'username' not in session: return redirect(url_for('login'))
    if request.method == 'POST':
        fees = 500
        # REAL Razorpay Order Creation
        order_params = {
            'amount': fees * 100, # Paise mein
            'currency': 'INR',
            'payment_capture': '1'
        }
        razorpay_order = razor_client.order.create(data=order_params)
        
        data = {
            'doctor': request.form.get('doctor'),
            'date': request.form.get('date'),
            'time': request.form.get('time'),
            'problem': request.form.get('problem'),
            'fees': fees,
            'order_id': razorpay_order['id'],
            'razorpay_key': RAZORPAY_KEY_ID
        }
        return render_template('checkout.html', data=data, username=session['username'])
    
    return render_template('appointments.html', page='book', username=session['username'])

@app.route('/process-payment', methods=['POST'])
def process_payment():
    if 'username' not in session: return redirect(url_for('login'))
    
    # Razorpay se aane wala data
    payment_id = request.form.get('payment_id')
    doctor = request.form.get('doctor')
    adate = request.form.get('date')
    atime = request.form.get('time')
    problem = request.form.get('problem')
    amount = request.form.get('amount')

    # Yahan hum database mein entry save karte hain
    conn = get_db_connection()
    conn.execute("""INSERT INTO appointments 
        (username, doctor, appointment_date, appointment_time, problem, amount, payment_id, payment_status, created_at) 
        VALUES (?,?,?,?,?,?,?,?,?)""",
        (session['username'], doctor, adate, atime, problem, amount, payment_id, 'Paid', datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    
    return render_template('payment_success.html', username=session['username'])

@app.route('/my-appointments')
def my_appointments():
    if 'username' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    apps = conn.execute("SELECT * FROM appointments WHERE username=? ORDER BY created_at DESC", (session['username'],)).fetchall()
    conn.close()
    return render_template('my_appointments.html', page='appointments', username=session['username'], appointments=apps)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True)