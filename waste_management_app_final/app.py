from flask import Flask, request, jsonify, render_template, redirect, url_for, session
import sqlite3  # Add this import for SQLite
import os
import datetime
from datetime import timezone, timedelta
'''
Flask:  main web framework.

session: To store  login data.

sqlite3: lightweight database.

os: For path operations.

datetime: For time (used in notifications)

jsonify: For creating JSON responses.

session: To store  login data.

sqlite3:  lightweight database.

os:  For path operations.

datetime:  For time (used in notifications)
'''
app = Flask(__name__, static_folder='static')
app.secret_key = os.environ.get('SECRET_KEY', 'Ganesh@123')  # Better secret key handling

# Define database path
DB_PATH = os.path.join(os.path.dirname(__file__), 'user_database.db')

ADMIN_CREDENTIALS = {
    "username": "admin",
    "password": "911366", # Admin credentials for login
    "name"    : "Super Admin"
}

# Store notifications for collectors with IDs and completion status
collector_notifications = {}
next_notification_id = 1

# Function to get current time in IST
def get_current_time():
    # Get current UTC time
    utc_now = datetime.datetime.now(timezone.utc)
    # Convert to IST (UTC+5:30)
    ist = utc_now + timedelta(hours=5, minutes=30)
    return ist.strftime("%d-%m-%Y"), ist.strftime("%H:%M:%S")

# Initialize SQLite database
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Providers login info
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')

    # Provider's form details
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            name TEXT,
            address TEXT,
            phone TEXT,
            waste_type TEXT
        )
    ''')

    # Collectors table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS collectors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            contact TEXT,
            address TEXT,
            waste_type TEXT NOT NULL
        )
    ''')

    # Ratings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS collector_ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            collector_username TEXT NOT NULL,
            provider_username TEXT NOT NULL,
            rating INTEGER NOT NULL CHECK(rating >= 1 AND rating <= 5),
            comment TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (collector_username) REFERENCES collectors(username),
            FOREIGN KEY (provider_username) REFERENCES users(username),
            UNIQUE(collector_username, provider_username)
        )
    ''')

    conn.commit()
    conn.close()

def get_collector_rating(collector_username):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT AVG(rating) as avg_rating, COUNT(rating) as total_ratings 
        FROM collector_ratings 
        WHERE collector_username = ?
    ''', (collector_username,))
    result = cursor.fetchone()
    conn.close()
    
    avg_rating = round(result[0], 1) if result[0] is not None else 0
    total_ratings = result[1]
    return avg_rating, total_ratings

# Initialize collector_notifications for all collectors in DB
def initialize_collector_notifications():
    global collector_notifications
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # First ensure the collectors table exists
    init_db()
    
    cursor.execute('SELECT username FROM collectors')
    for row in cursor.fetchall():
        collector_notifications[row[0]] = []
    conn.close()

@app.route('/')
def home():
    return render_template('home.html')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        # Check if username already exists in the database
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
        existing_user = cursor.fetchone()

        if existing_user:
            conn.close()
            return "Username already exists. <a href='/signup'>Try again</a>"

        # Insert new user into the database
        cursor.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, password))
        conn.commit()
        conn.close()

        return redirect(url_for('home'))
    return render_template('signup.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        print("Login type received:", request.form.get('login_type'))
        login_type = request.form.get('login_type')  # 'provider' or 'collector'
        username = request.form.get('username')
        password = request.form.get('password')

        if login_type == 'provider':
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, password))
            user = cursor.fetchone()
            conn.close()

            if user:
                session['user'] = username
                return render_template('provider_login_success.html', username=username)
            return "Invalid provider credentials. <a href='/login'>Try again</a>"
        
        elif login_type == 'admin':
            if username == ADMIN_CREDENTIALS['username'] and password == ADMIN_CREDENTIALS['password']:
                session['admin'] = ADMIN_CREDENTIALS['username']
                return redirect(url_for('admin_dashboard'))
            return "Invalid admin credentials. <a href='/login'>Try again</a>"


        elif login_type == 'collector':
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM collectors WHERE username = ? AND password = ?', (username, password))
            collector = cursor.fetchone()
            conn.close()
            if collector:
                session['collector'] = username
                session.pop('notifications_loaded', None)
                return redirect(url_for('collector_dashboard'))
            return "Invalid collector credentials. <a href='/login'>Try again</a>"
    return render_template('login.html')


@app.route('/collectors/<waste_type>')
def get_collectors(waste_type):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT name, username, contact, address FROM collectors WHERE waste_type = ?', (waste_type,))
    collectors = []
    for row in cursor.fetchall():
        avg_rating, total_ratings = get_collector_rating(row[1])  # row[1] is username
        collectors.append({
            "name": row[0],
            "username": row[1],
            "contact": row[2],
            "address": row[3],
            "rating": avg_rating,
            "total_ratings": total_ratings
        })
    conn.close()
    if collectors:
        return render_template('collectors.html', waste_type=waste_type, collectors=collectors)
    return "No collectors found for this waste type."



@app.route('/provider', methods=['GET', 'POST'])
def provider():
    if request.method == 'POST':
        # Check if it's an edit request
        if request.form.get('action') == 'edit':
            return render_template('provider.html', 
                                 name=request.form.get('name'),
                                 address=request.form.get('address'),
                                 phone=request.form.get('phone'),
                                 waste_type=request.form.get('waste_type'),
                                 is_edit=True)

        # If collector is selected
        selected_collector_username = request.form.get('selected_collector')
        if selected_collector_username:
            provider_info = session.get('provider_info', {})
            if not provider_info:
                return "Session expired. Please start again. <a href='/provider'>Back</a>"

            global next_notification_id
            if selected_collector_username not in collector_notifications:
                collector_notifications[selected_collector_username] = []

            # Add current date and time to the notification
            current_date, current_time = get_current_time()

            collector_notifications[selected_collector_username].append({
                "id": next_notification_id,
                "name": provider_info.get('name'),
                "address": provider_info.get('address'),
                "phone": provider_info.get('phone'),
                "waste_type": provider_info.get('waste_type'),
                "date": current_date,
                "time": current_time,
                "completed": False
            })
            next_notification_id += 1
            return render_template('notification_sent.html',
                       collector=selected_collector_username,
                       provider=provider_info)

        # Get provider details from form
        name = request.form.get('name')
        address = request.form.get('address')
        phone = request.form.get('phone')
        waste_type = request.form.get('waste_type')

        username = session.get('user')
        if username:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            # Create table if it doesn't exist
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_details (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT,
                    name TEXT,
                    address TEXT,
                    phone TEXT,
                    waste_type TEXT,
                    UNIQUE(username)
                )
            ''')
            
            # Update or insert user details
            cursor.execute('''
                INSERT OR REPLACE INTO user_details (username, name, address, phone, waste_type)
                VALUES (?, ?, ?, ?, ?)
            ''', (username, name, address, phone, waste_type))
            
            conn.commit()
            conn.close()

        # Fetch collectors from DB with ratings
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT name, username, contact, address FROM collectors WHERE waste_type = ?', (waste_type,))
        collectors = []
        for row in cursor.fetchall():
            avg_rating, total_ratings = get_collector_rating(row[1])  # row[1] is username
            collectors.append({
                "name": row[0],
                "username": row[1],
                "contact": row[2],
                "address": row[3],
                "rating": avg_rating,
                "total_ratings": total_ratings
            })
        conn.close()
        
        if collectors:
            session['provider_info'] = {
                'name': name,
                'address': address,
                'phone': phone,
                'waste_type': waste_type
            }
            return render_template('collectors.html', waste_type=waste_type, collectors=collectors)
        return "No collectors available for this waste type."

    # GET request handling
    username = session.get('user')
    if username:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Create table if it doesn't exist
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_details (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                name TEXT,
                address TEXT,
                phone TEXT,
                waste_type TEXT,
                UNIQUE(username)
            )
        ''')
        
        # Get user's saved details
        cursor.execute('SELECT name, address, phone, waste_type FROM user_details WHERE username = ?', (username,))
        saved_details = cursor.fetchone()
        conn.close()

        if saved_details:
            name, address, phone, waste_type = saved_details
            return render_template('provider.html', 
                                 name=name, 
                                 address=address, 
                                 phone=phone, 
                                 waste_type=waste_type,
                                 has_saved_details=True)

    return render_template('provider.html', has_saved_details=False)


@app.route('/complete-notification', methods=['POST'])
def complete_notification():
    if 'collector' not in session:
        return redirect(url_for('login'))

    notification_id = int(request.form.get('notification_id'))
    username = session['collector']

    if username in collector_notifications:
        # Remove the completed notification immediately
        collector_notifications[username] = [
            note for note in collector_notifications[username]
            if note['id'] != notification_id
        ]

    return redirect(url_for('collector_dashboard'))

@app.route('/collector-dashboard')
def collector_dashboard():
    username = session.get('collector')
    if not username:
        return redirect(url_for('login'))

    # Fetch collector details from DB
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT name, username, contact, waste_type FROM collectors WHERE username = ?', (username,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return "Collector not found. <a href='/login'>Login again</a>"
    collector_details = {
        "name": row[0],
        "username": row[1],
        "contact": row[2],
        "waste_type": row[3]
    }
    if username not in collector_notifications:
        collector_notifications[username] = []
    notifications = collector_notifications.get(username, [])
    return render_template('collector_dashboard.html', collector=collector_details, notifications=notifications)

@app.route('/admin-dashboard', methods=['GET', 'POST'])
def admin_dashboard():
    if 'admin' not in session:
        return redirect(url_for('login'))

    message = ""

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    if request.method == 'POST':
        if request.form.get('action') == 'delete':
            delete_username = request.form.get('delete_username')
            cursor.execute('DELETE FROM collectors WHERE username = ?', (delete_username,))
            if cursor.rowcount > 0:
                conn.commit()
                message = f"✅ Collector with username '{delete_username}' deleted successfully!"
            else:
                message = f"❌ Collector with username '{delete_username}' not found."
        else:
            name = request.form.get('name')
            username = request.form.get('username')
            password = request.form.get('password')
            contact = request.form.get('contact')
            address = request.form.get('address')
            waste_type = request.form.get('waste_type')

            cursor.execute('SELECT * FROM collectors WHERE username = ?', (username,))
            if cursor.fetchone():
                message = f"❌ Collector with username '{username}' already exists."
            else:
                cursor.execute('''
                    INSERT INTO collectors (name, username, password, contact, address, waste_type)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (name, username, password, contact, address, waste_type))
                conn.commit()
                message = f"✅ Collector '{name}' added successfully under '{waste_type}'!"

    # Always fetch collectors, regardless of method
    cursor.execute('SELECT name, username, contact, address, waste_type FROM collectors')
    all_collectors = cursor.fetchall()
    conn.close()

    return render_template('admin_dashboard.html', message=message, collectors=all_collectors)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

@app.route('/rate-collector', methods=['POST'])
def rate_collector():
    if 'user' not in session:
        return redirect(url_for('login'))

    collector_username = request.form.get('collector_username')
    rating = request.form.get('rating')
    comment = request.form.get('comment', '')
    provider_username = session['user']

    if not collector_username or not rating or not rating.isdigit():
        return "Invalid rating data", 400

    rating = int(rating)
    if rating < 1 or rating > 5:
        return "Rating must be between 1 and 5", 400

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT OR REPLACE INTO collector_ratings 
            (collector_username, provider_username, rating, comment)
            VALUES (?, ?, ?, ?)
        ''', (collector_username, provider_username, rating, comment))
        conn.commit()
        return redirect(url_for('home'))
    except sqlite3.Error as e:
        return f"An error occurred: {str(e)}", 500
    finally:
        conn.close()


if __name__ == '__main__':
    init_db()  # Initialize database first
    initialize_collector_notifications()  # Then initialize notifications
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
# To run the app, use the command: python app.py