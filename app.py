import os
import razorpay
from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import google.generativeai as genai
from flask_pymongo import PyMongo # MongoDB ke liye

app = Flask(__name__)
app.secret_key = "health_assist_secret_key"

# --- PERMANENT MONGODB CONFIG ---
# Aapki copy ki hui connection string
app.config["MONGO_URI"] = "mongodb+srv://choudharymahal123:@@$1Sniperz@cluster0.sr2fpbq.mongodb.net/health_portal?retryWrites=true&w=majority"
mongo = PyMongo(app)

# --- RAZORPAY CONFIG ---
RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "rzp_test_S65Om1hBEBByIX")
RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "LwkTinu4TO0QKvjuTEWxHLmD")
razor_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

# --- AI CONFIGURATION ---
genai.configure(api_key=os.environ.get("GEMINI_API_KEY", "AIzaSyAqgI3UWadfzTBqyFjf5c9tJMYtMXJuLGA"))
model = genai.GenerativeModel("gemini-1.5-flash")

# --- ROUTES ---

@app.route('/')
def home():
    if 'username' in session: return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    message = ""
    if request.method == 'POST':
        users = mongo.db.users
        name = request.form['name']
        email = request.form['email']
        mobile = request.form['mobile']
        username = request.form['username']
        password = request.form['password']
        
        # Check if user exists
        existing_user = users.find_one({"$or": [{"username": username}, {"email": email}, {"mobile": mobile}]})
        
        if existing_user is None:
            hashed_password = generate_password_hash(password)
            users.insert_one({
                "name": name, "email": email, "mobile": mobile, 
                "username": username, "password": hashed_password, 
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            return redirect(url_for('login'))
        else:
            message = "Username/Email/Mobile already exists."
            
    return render_template('signup.html', message=message)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = mongo.db.users.find_one({"username": username})
        
        if user and check_password_hash(user['password'], password):
            session['username'] = user['username']
            now = datetime.now()
            mongo.db.login_logs.insert_one({
                "username": username, 
                "login_date": now.strftime("%Y-%m-%d"), 
                "login_time": now.strftime("%H:%M:%S")
            })
            return redirect(url_for('dashboard'))
        return render_template('login.html', message="Invalid Credentials")
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'username' not in session: return redirect(url_for('login'))
    user_medicines = list(mongo.db.medicines.find({"username": session['username']}).sort("med_time", 1))
    return render_template('dashboard.html', page='home', username=session['username'], medicines=user_medicines)

@app.route('/appointments', methods=['GET', 'POST'])
def appointments():
    if 'username' not in session: return redirect(url_for('login'))
    if request.method == 'POST':
        fees = 500
        order_params = {'amount': fees * 100, 'currency': 'INR', 'payment_capture': '1'}
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
    
    mongo.db.appointments.insert_one({
        "username": session['username'],
        "doctor": request.form.get('doctor'),
        "appointment_date": request.form.get('date'),
        "appointment_time": request.form.get('time'),
        "problem": request.form.get('problem'),
        "amount": request.form.get('amount'),
        "payment_id": request.form.get('payment_id'),
        "payment_status": 'Paid',
        "status": 'Confirmed',
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    return render_template('payment_success.html', username=session['username'])

@app.route('/my-appointments')
def my_appointments():
    if 'username' not in session: return redirect(url_for('login'))
    apps = list(mongo.db.appointments.find({"username": session['username']}).sort("created_at", -1))
    return render_template('my_appointments.html', page='appointments', username=session['username'], appointments=apps)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
