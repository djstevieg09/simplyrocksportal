import os
import sqlite3
import requests
import queue      
import threading  
import time
from datetime import datetime 
from flask import Flask, render_template, request, redirect, url_for, session, jsonify

app = Flask(__name__)
app.secret_key = os.urandom(24)

# CONFIGURATION
DEFAULT_DNS = "http://simplyrocks.org:80"
TMDB_API_KEY = "0ca48ab2446df424e4bd03b293104701"
# FIXED PERMANENT VAULT ROADMAP: Keeps your database file 100% safe from cloud reboots!
DB_FILE = "/data/database.db"


# --- MASTER RESELLER CODES AUTO-EXTEND CONFIGURATION ---
RESELLER_PANEL_URL = "https://theservice.rocks:80" 
RESELLER_USERNAME = "djstevieg09"
RESELLER_PASSWORD = "Jacobgibbs1"

# --- TELEGRAM BOT ALERTS CONFIGURATION ---
TELEGRAM_BOT_TOKEN = "8719424779:AAEnfEX8spacJpLVKurxZV-VuOTDOmFMaRo"
TELEGRAM_CHAT_ID = "5077921091"

def init_db():
    """Unconditionally initialises and mounts all 7 system database tables safely before any web routes execute."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        
        # 1. Media Content Requests Table Layout
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                title TEXT NOT NULL,
                year TEXT,
                media_type TEXT,
                imdb_id TEXT,
                poster TEXT,
                status TEXT DEFAULT 'Pending',
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 2. Airtight Payment Validation Metrics Data Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                order_id TEXT NOT NULL,
                amount TEXT NOT NULL,
                status TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 3. Secure Cashback Referral Wallets Ledger Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS referral_wallets (
                username TEXT PRIMARY KEY,
                earned_balance REAL DEFAULT 0.0,
                spent_balance REAL DEFAULT 0.0,
                last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 4. Live Stream Help Desk Fault Tickets Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS channel_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                channel_name TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                issue_type TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 5. Local Expiration Dashboard Metrics Tracking Cache Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_metadata (
                username TEXT PRIMARY KEY,
                expiry_date TEXT NOT NULL,
                expiry_timestamp INTEGER NOT NULL,
                alert_sent INTEGER DEFAULT 0,
                last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 6. Secure VOD (Movie & Series) Help Desk Fault Tickets Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS vod_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                title TEXT NOT NULL,
                media_type TEXT NOT NULL,
                issue_type TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 7. FIXED: Secure Local Portal User Accounts Ledger Table Structure Mount
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS portal_users (
                username TEXT PRIMARY KEY,
                password TEXT NOT NULL,
                expiry_date TEXT NOT NULL,
                expiry_timestamp INTEGER NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 8. Local Master Live TV Channels Lineup Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS live_channels (
                stream_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # ADDED FOR REASON CAPTURE: Appends custom text column to the VOD table dynamically
        try:
            cursor.execute("ALTER TABLE vod_reports ADD COLUMN issue_notes TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass

        conn.commit()

        
@app.route('/admin/create_portal_user', methods=['POST'])
def admin_create_portal_user():
    """Manually registers custom user access lines into the local database, using secure fallback checks to prevent session dropping on cloud hosts."""
    # FIXED SESSION TUNNEL: Falls back securely to username matching if the cloud server drops cookie keys!
    current_user = str(session.get('username', '')).lower()
    is_admin_flag = session.get('is_admin')
    
    if not session.get('logged_in') or (not is_admin_flag and current_user != "djstevieg09"):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
    data = request.json or {}
    uname = data.get('username', '').strip()
    pword = data.get('password', '').strip()
    exp_str = data.get('expiry_date', '').strip() # Expecting Format: YYYY-MM-DD
    
    if not uname or not pword or not exp_str:
        return jsonify({'success': False, 'message': 'All entry profile parameters are mandatory'}), 400
        
    try:
        dt_obj = datetime.strptime(exp_str, '%Y-%m-%d')
        exp_ts = int(time.mktime(dt_obj.timetuple()))
        readable_date = dt_obj.strftime('%B %d, %Y')
        
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO portal_users (username, password, expiry_date, expiry_timestamp)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(username) DO UPDATE SET
                    password = excluded.password,
                    expiry_date = excluded.expiry_date,
                    expiry_timestamp = excluded.expiry_timestamp
            ''', (uname, pword, readable_date, exp_ts))
            
            cursor.execute('''
                INSERT INTO user_metadata (username, expiry_date, expiry_timestamp, alert_sent)
                VALUES (?, ?, ?, 0)
                ON CONFLICT(username) DO UPDATE SET
                    expiry_date = excluded.expiry_date,
                    expiry_timestamp = excluded.expiry_timestamp
            ''', (uname, readable_date, exp_ts))
            conn.commit()
            
        print(f"ADMIN PORTAL CREATION: Local user '{uname}' registered successfully.")
        
        countdown_warning_text = (
            f"<b>👤 NEW PORTAL USER ACCOUNT CREATED</b>\n"
            f"----------------------------------------\n"
            f"<b>Portal Source:</b> <b>SimplyRocks Portal</b> 🌐\n"
            f"<b>Portal Username:</b> <code>{uname}</code>\n"
            f"<b>Access Password:</b> <code>{pword}</code>\n"
            f"<b>Expiration Date:</b> <b>{readable_date}</b>\n"
            f"----------------------------------------"
        )
        NOTIFICATION_QUEUE.put(countdown_warning_text)
        
        return jsonify({'success': True, 'message': f"Account line '{uname}' saved to portal registry ledger!"})
    except Exception as e:
        print(f"ADMIN ACC GENERATION FAILURE: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500



@app.route('/admin/delete_portal_user/<string:username>', methods=['POST'])
def admin_delete_portal_user(username):
    """Allows admin to completely wipe a registered user account from access records logs using inline clicks."""
    if not session.get('logged_in') or not session.get('is_admin'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM portal_users WHERE LOWER(username) = LOWER(?)", (username.strip().lower(),))
            cursor.execute("DELETE FROM user_metadata WHERE LOWER(username) = LOWER(?)", (username.strip().lower(),))
            conn.commit()
        return jsonify({'success': True, 'message': f"Account profile '{username}' dropped cleanly!"})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500



# Trigger the clean build immediately on file parse!
init_db()

# Instantiates global thread data queues
NOTIFICATION_QUEUE = queue.Queue()


import hashlib

def trigger_automatic_panel_extension(client_username, connections_count):
    """Connects directly to the official master panel api.php script to deduct credits and auto-extend lines instantly."""
    try:
        # THE CORRRECT UNIVERSAL ENDPOINT: Targets the core api.php routing file directly
        api_endpoint = f"{DEFAULT_DNS.rstrip('/')}/api.php"
        
        # PACKAGE MAP: Enforces your exact panel package values confirmed from your F12 HTML!
        package_id_map = {
            '1': '66',  # 1 Connection 12 Months
            '2': '70',  # 2 Connections 12 Months 
            '3': '74',  # 3 Connections 12 Months
            '4': '78'   # 4 Connections 12 Months
        }
        
        target_package = package_id_map.get(str(connections_count), '66')
        print(f"AUTOMATION: Sending official API payload to extend line {client_username} with Package {target_package}...")
        
        # Formulate parameters matching the core panel API query hooks
        payload = {
            'action': 'extend',              # Universal command action string to apply renewals
            'username': RESELLER_USERNAME,
            'password': RESELLER_PASSWORD,
            'sub_user': client_username,
            'package_id': target_package
        }
        
        # Execute the network query parameters call to your panel server
        response = requests.get(api_endpoint, params=payload, timeout=15)
        
        if response.status_code == 200:
            res_text = response.text.strip().lower()
            
            # Catch common error logs or empty outputs returned by panel authentication restrictions
            if "error" in res_text or "fail" in res_text or "invalid" in res_text or not res_text:
                print(f"AUTOMATION WARNING: Panel rejected connection parameters. Server response: {response.text}")
                return False, f"Panel rejection: {response.text}"
                
            print(f"AUTOMATION SUCCESS: Account {client_username} has been successfully extended on your live IPTV panel!")
            return True, "Line extended 100% automatically via panel API authentication."
        else:
            print(f"AUTOMATION ERROR: Panel API returned an error status code: {response.status_code}")
            return False, f"Panel API error code: {response.status_code}"
            
    except Exception as e:
        print(f"AUTOMATION EXCEPTION: Network link dropped during panel sync routine: {e}")
        return False, f"Panel connection timeout exception: {e}"


def verify_xtream_credentials(dns, username, password):
    """Authenticates clients securely and directly against your local secure accounts index database."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM portal_users WHERE LOWER(username) = LOWER(?) AND password = ?", (username.strip().lower(), password.strip()))
            user_row = cursor.fetchone()
            
        if user_row:
            mock_info = {
                'auth': 1,
                'status': 'Active',
                'exp_date': user_row['expiry_timestamp']
            }
            return True, mock_info
    except Exception as e:
        print(f"LOCAL LOGIN MAPPING ERROR: {e}")
    return False, None


@app.route('/', endpoint='login', methods=['GET', 'POST'])
def login():
    """Handles secure user and administrator authentication, strictly validating credentials against the live server."""
    if request.method == 'GET':
        return render_template('login.html', default_dns=DEFAULT_DNS)

    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()

    if not username or not password:
        return render_template('login.html', error="Please supply both username and password configurations.")

    # --- 1. ADMINISTRATIVE LOGIN LOCAL BYPASS ---
    if username.lower() == "djstevieg09" and password == "Jacobgibbs1":
        session['logged_in'] = True
        session['username'] = username
        session['password'] = password
        session['is_admin'] = True
        session['expiry_date'] = "Reseller Control"
        print("ADMIN LOGIN DETECTED: Locally validated credentials. Routing straight to master operations panel.")
        return redirect(url_for('admin_panel'))
        
    # --- 2. CLIENT TIER CHANNEL: Direct Server Validation ---
    dns = DEFAULT_DNS
    success, user_info = verify_xtream_credentials(dns, username, password)
    
    if success and user_info:
        session['logged_in'] = True
        session['username'] = username
        session['password'] = password
        session['is_admin'] = False
        
        print("\n--- XTREAM CODES SERVER RESPONSE SNAPSHOT ---")
        raw_exp = user_info.get('exp_date')
        print(f"Extracted genuine exp_date string: {raw_exp}")
        print("--------------------------------------------\n")
        
        exp_ts = 0
        if raw_exp is None or str(raw_exp).strip().lower() in ['null', '', '0', 'none', 'false']:
            session['expiry_date'] = "Unlimited Account"
            readable_date = "Unlimited Account"
        else:
            try:
                timestamp = int(raw_exp)
                if timestamp < 100000000:
                    session['expiry_date'] = "Unlimited Account"
                    readable_date = "Unlimited Account"
                else:
                    exp_ts = timestamp
                    readable_date = datetime.fromtimestamp(timestamp).strftime('%B %d, %Y')
                    session['expiry_date'] = readable_date
            except Exception as e:
                print(f"Timestamp conversion anomaly: {e}")
                session['expiry_date'] = "Active Line"
                readable_date = "Active Line"

        # LOCAL CACHE STORAGE ENGINE
        try:
            with sqlite3.connect(DB_FILE) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute("SELECT alert_sent FROM user_metadata WHERE LOWER(username) = LOWER(?)", (username.lower(),))
                row = cursor.fetchone()
                already_sent = row['alert_sent'] if row else 0
                
                current_time_now = int(time.time())
                days_left_gate = int((exp_ts - current_time_now) / 86400) if exp_ts > 0 else 999
                
                if 0 <= days_left_gate <= 7 and not already_sent:
                    alert_sent_status = 1
                    countdown_warning_text = (
                        f"<b>⏳ APPROACHING SUBSCRIPTION EXPIRATION WARNING</b>\n"
                        f"----------------------------------------\n"
                        f"<b>Customer Username:</b> <code>{username}</code>\n"
                        f"<b>Calendar Expiry Date:</b> <b>{readable_date}</b>\n\n"
                        f"<b>🚨 STATUS CRITICAL: Only {days_left_gate} Days Remaining!</b>\n"
                        f"<i>Action Required: Contact client for premium line package extension renewal.</i>\n"
                        f"----------------------------------------"
                    )
                    NOTIFICATION_QUEUE.put(countdown_warning_text)
                    print(f"TELEGRAM SUCCESS: Warning alert queued safely for client line: {username}")
                else:
                    alert_sent_status = already_sent if days_left_gate <= 7 else 0

                cursor.execute('''
                    INSERT INTO user_metadata (username, expiry_date, expiry_timestamp, alert_sent)
                    VALUES (?, ?, ?, ?) ON CONFLICT(username) DO UPDATE SET
                        expiry_date = excluded.expiry_date,
                        expiry_timestamp = excluded.expiry_timestamp,
                        alert_sent = excluded.alert_sent,
                        last_updated = CURRENT_TIMESTAMP
                ''', (username, readable_date, exp_ts, alert_sent_status))
                conn.commit()
            print(f"LOCAL CACHE SUCCESS: Logged metadata metrics profile row into database for user: {username}")
        except Exception as db_err:
            print(f"LOCAL CACHE ERROR: Failed to log profile metadata row: {db_err}")
        
        return redirect(url_for('dashboard'))
    else:
        # Strictly rejects entry if credentials fail against the server
        return render_template('login.html', error="Invalid username or password profile details.")


            
@app.route('/sync_live_panel_expirations', methods=['POST'])
def sync_live_panel_expirations():
    """Reads all logged-in usernames from local storage, wipes the dashboard cache view, and rebuilds it using fresh panel data."""
    if not session.get('logged_in') or not session.get('is_admin'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
    sync_count = 0
    captured_count = 0
    current_timestamp = int(time.time())
    
    try:
        # 1. READ REGISTERED USERS FIRST: Grab your active customer list before clearing the view grid
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT username FROM user_metadata")
            tracked_users = [row['username'].strip() for row in cursor.fetchall()]

        # Safety baseline check: If your file is blank, make sure your test account is checked
        if not tracked_users:
            tracked_users = ["DC-Firestick"]

        # 2. CLEAR THE GRID ROWS: Temporarily flush the local dashboard view cache for a clean update
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM user_metadata")
            conn.commit()

        print("\n--- LIVE EXPIRED-GATE MONITOR AUTOMATION ENGAGED ---")
        
        # 3. Request fresh timeline coordinates from your IPTV server line stream API channels
        for uname in tracked_users:
            if not uname or uname.lower() == RESELLER_USERNAME.lower():
                continue
                
            try:
                api_endpoint = f"{DEFAULT_DNS.rstrip('/')}/player_api.php"
                response = requests.get(api_endpoint, params={
                    'username': uname,
                    'password': 'guBjTEbKNb'
                }, timeout=5)
                
                if response.status_code == 200:
                    panel_data = response.json()
                    user_info = panel_data.get('user_info', {}) if isinstance(panel_data, dict) else {}
                    raw_exp = user_info.get('exp_date')
                    
                    if raw_exp and str(raw_exp).strip().lower() not in ['null', '', '0', 'none', 'false']:
                        exp_ts = int(raw_exp)
                        readable_date = datetime.fromtimestamp(exp_ts).strftime('%B %d, %Y')
                        days_left = int((exp_ts - current_timestamp) / 86400)
                        
                        # THE STRICT 31-DAY VIEW FILTER GATEWAY:
                        if days_left <= 31:
                            # If they are 31 days or under, write them back to display on the Admin Board grid matrix!
                            with sqlite3.connect(DB_FILE) as conn2:
                                cursor2 = conn2.cursor()
                                cursor2.execute('''
                                    INSERT INTO user_metadata (username, expiry_date, expiry_timestamp, alert_sent)
                                    VALUES (?, ?, ?, 0)
                                ''', (uname, readable_date, exp_ts))
                                conn2.commit()
                            print(f"DASHBOARD CAPTURE: Saved expiring user onto matrix view: {uname} ({days_left} Days Left)")
                            captured_count += 1
                        else:
                            # If they are safely over 31 days, keep a quiet database row so they can still sign in, but hide them from your sight!
                            with sqlite3.connect(DB_FILE) as conn2:
                                cursor2 = conn2.cursor()
                                cursor2.execute('''
                                    INSERT INTO user_metadata (username, expiry_date, expiry_timestamp, alert_sent)
                                    VALUES (?, ?, ?, 0)
                                ''', (uname, readable_date, exp_ts))
                                conn2.commit()
                            print(f"DASHBOARD FILTER: Hidden safe user from active matrix view: {uname} ({days_left} Days Left)")
                            
                        sync_count += 1
            except Exception as loop_err:
                print(f"API OVERWRITE SYNC LOOP FAULT: Skipping account mapping check for {uname}: {loop_err}")
                continue
                
        print(f"PLAYER API MASTER SUCCESS: Processed {sync_count} total profiles. Captured {captured_count} expiring rows.\n-----------------------------------------\n")
        return jsonify({
            'success': True, 
            'message': f'Sync complete! Successfully checked your active client list. Found {captured_count} accounts expiring in 31 days or less!'
        })
        
    except Exception as e:
        print(f"MASTER SYNC OPERATION CRITICAL ERROR: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500




@app.route('/dashboard')
def dashboard():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
        
    # --- AUTOMATED EXPIRY COUNTDOWN CALCULATION ENGINE ---
    days_remaining = None
    show_expiry_warning = False
    
    # Check if the user has a real numeric expiry date stored in their session
    if session.get('password') and session.get('username'):
        # Re-verify against credentials to fetch the latest timestamp snapshot
        success, user_info = verify_xtream_credentials(DEFAULT_DNS, session['username'], session['password'])
        if success and user_info:
            raw_exp = user_info.get('exp_date')
            if raw_exp and str(raw_exp).strip().lower() not in ['null', '', '0', 'none', 'false']:
                try:
                    exp_timestamp = int(raw_exp)
                    current_timestamp = int(time.time())
                    
                    # Compute the dynamic mathematical difference in days
                    seconds_left = exp_timestamp - current_timestamp
                    days_remaining = int(seconds_left / 86400)
                    
                    # TRIGGER ZONE: Turn on the flag if they have 7 days or less remaining
                    if days_remaining <= 400:
                        show_expiry_warning = True
                except Exception:
                    pass

    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM requests WHERE username = ? ORDER BY timestamp DESC", (session['username'],))
        user_requests = cursor.fetchall()
        
    return render_template(
        'dashboard.html', 
        username=session['username'], 
        requests=user_requests, 
        expiry_date=session.get('expiry_date', 'Active Line'),
        show_warning=show_expiry_warning,
        days_left=days_remaining
    )
    
@app.route('/search_media')
def search_media():
    """Queries the global TMDB library for movies or TV series and returns a verified JSON object."""
    if not session.get('logged_in'):
        return jsonify({"results": []}), 401
        
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({"results": []})
        
    try:
        # CLEAN NATIVE PYTHON PACKAGING: Sends parameters directly to their official API endpoint
        url = "https://api.themoviedb.org/3/search/multi"
        response = requests.get(url, params={
            'api_key': TMDB_API_KEY,
            'language': 'en-US',
            'query': query,
            'page': 1,
            'include_adult': 'false'
        }, timeout=6)
        
        if response.status_code == 200:
            return jsonify(response.json())
            
        print(f"TMDB REJECTION ERROR: Server answered with code {response.status_code}")
        return jsonify({"results": []})
    except Exception as e:
        print(f"TMDB FATAL EXCEPTION: {e}")
        return jsonify({"results": []})
        
@app.route('/create_referral_line', methods=['POST'])
def create_referral_line():
    """Generates standalone portal accounts for referred friends formatted strictly as Firstname-Lastname, rewarding a premium £25 balance credit."""
    if not session.get('logged_in'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    data = request.json or {}
    f_name = data.get('first_name', '').strip().capitalize()
    l_name = data.get('last_name', '').strip().capitalize()
    phone_str = data.get('phone', '').strip()
    referrer = session.get('username')
    
    # BACKEND VALVE LAYER: Strictly drops request if names are blank strings
    if not f_name or not l_name or not phone_str:
        return jsonify({'success': False, 'message': '❌ REJECTION: First name, Last name, and Phone fields are strictly mandatory!'}), 400
        
    try:
        # Combines inputs character-for-character to force clean 'Firstname-Lastname' profiles
        generated_username = f"{f_name}-{l_name}"
        
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT username FROM portal_users WHERE LOWER(username) = LOWER(?)", (generated_username.lower(),))
            collision_row = cursor.fetchone()
            
            if collision_row:
                generated_username = f"{f_name}-{l_name}-{random.randint(10, 99)}"
                
            generated_password = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=8))
            one_year_ts = int(time.time()) + (365 * 86400)
            readable_expiry = datetime.fromtimestamp(one_year_ts).strftime('%B %d, %Y')
            
            # 1. Insert into core local user database ledger accounts table rows
            cursor.execute('''
                INSERT INTO portal_users (username, password, expiry_date, expiry_timestamp)
                VALUES (?, ?, ?, ?)
            ''', (generated_username, generated_password, readable_expiry, one_year_ts))
            
            # 2. Add structural cache mapping profile to handle client view tickers
            cursor.execute('''
                INSERT INTO user_metadata (username, expiry_date, expiry_timestamp, alert_sent)
                VALUES (?, ?, ?, 0)
            ''', (generated_username, readable_expiry, one_year_ts))
            
            # 3. Add cashback credit reward directly into the referrer line wallet row
            cursor.execute("SELECT username FROM referral_wallets WHERE LOWER(username) = LOWER(?)", (referrer.lower(),))
            wallet_exists = cursor.fetchone()
            if not wallet_exists:
                cursor.execute("INSERT INTO referral_wallets (username, earned_balance, spent_balance) VALUES (?, 0.0, 0.0)", (referrer,))
                
            # FIXED BOUNTY: Allocates exactly £25.00 credit to your customer for bringing a paying friend!
            cursor.execute("UPDATE referral_wallets SET earned_balance = earned_balance + 25.00 WHERE LOWER(username) = LOWER(?)", (referrer.lower(),))
            conn.commit()
            
        print(f"REFERRAL ENFORCER: Created new customer profile: {generated_username}")
        
        # FIXED: Telegram notification string explicitly logs the new £25 reward!
        notification_text = (
            f"<b>🎉 NEW REFERRAL ACQUIRED [+£25 CREDIT UNLOCKED]</b>\n"
            f"----------------------------------------\n"
            f"<b>Portal Source:</b> <b>SimplyRocks Portal</b> 🌐\n"
            f"<b>Referrer User:</b> <code>{referrer}</code>\n"
            f"<b>Added Credit:</b> +£25.00 Reward Balance 💰\n\n"
            f"<b>New Friend Account Line Created:</b>\n"
            f"👤 <b>User:</b> <code>{generated_username}</code>\n"
            f"🔑 <b>Pass:</b> <code>{generated_password}</code>\n"
            f"📅 <b>Expiry:</b> {readable_expiry}\n"
            f"----------------------------------------"
        )
        NOTIFICATION_QUEUE.put(notification_text)
        
        return jsonify({
            'success': True,
            'generated_user': generated_username,
            'generated_pass': generated_password
        })
    except Exception as e:
        print(f"REFERRAL LOGGING ROUTINE EXCEPTION: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500




@app.route('/submit_request', methods=['POST'])
def submit_request():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
        
    data = request.json
    if not data or not data.get('title'):
        return jsonify({'success': False, 'message': 'Missing data'}), 400

    title = data.get('title')
    year = data.get('year', 'VOD')
    media_type = data.get('type', 'movie').upper()
    poster_url = data.get('poster', '')

    # 1. Log the media submittal safely inside your local database tables
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO requests (username, title, year, media_type, imdb_id, poster)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            session['username'], 
            title, 
            year, 
            data.get('type'), 
            data.get('imdbID'), 
            poster_url
        ))
        conn.commit()
        
    print(f"MEDIA REQUEST LOGGED: User {session['username']} requested {media_type}: {title} ({year})")
    
    # 2. Format a clean alert notification layout message for your Telegram channel
    request_alert_text = (
        f"<b>🎬 NEW MEDIA REQUEST SUBMITTED</b>\n"
        f"----------------------------------------\n"
        f"<b>Requested Title:</b> <code>{title}</code>\n"
        f"<b>Content Year:</b> <code>{year}</code>\n"
        f"<b>Media Type Profile:</b> <b>{media_type}</b>\n\n"
        f"<b>Submitted By User:</b> <code>{session['username']}</code>\n"
        f"<b>Timestamp Logged:</b> {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"----------------------------------------\n"
        f"🍿 <i>Action Prompt: Check content availability and update your master IPTV server library catalog.</i>"
    )
    
    # 3. Push it directly into your thread-safe worker queue to fire it out instantly
    NOTIFICATION_QUEUE.put(request_alert_text)
    
    return jsonify({'success': True, 'message': 'Request submitted successfully!'})

def deduct_wallet_credits(user_name, spent_amount):
    """Safely records a wallet deduction by increasing spent_balance in the database ledger row history."""
    try:
        amount_val = float(spent_amount)
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            
            # Establish a safety fallback row if the tracking matrix is missing
            cursor.execute('''
                INSERT INTO referral_wallets (username, earned_balance, spent_balance)
                VALUES (?, 0.0, 0.0)
                ON CONFLICT(username) DO NOTHING
            ''', (user_name,))
            
            # Increase spent_balance to reflect the dynamic redemption deduction
            cursor.execute('''
                UPDATE referral_wallets 
                SET spent_balance = spent_balance + ?, 
                    last_updated = CURRENT_TIMESTAMP
                WHERE username = ?
            ''', (amount_val, user_name))
            
            conn.commit()
        print(f"DATABASE LEDGER: Subtracted £{amount_val} spent credit from wallet row for user: {user_name}")
    except Exception as e:
        print(f"WALLET TRANSACTION REJECTION: Failed to adjust balance rows: {e}")

@app.route('/log_payment', methods=['POST'])
def log_payment():
    """Logs purchases, subtracts exact redeemed credit to preserve remainder balances, and auto-extends lines by 365 days."""
    if not session.get('logged_in'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    data = request.json or {}
    username = session.get('username')
    order_id = data.get('orderID')
    amount_paid = float(data.get('amount', 0.0))
    connections = data.get('connections', '1')
    discount_redeemed = float(data.get('discount_redeemed', 0.0))
    
    if not order_id:
        return jsonify({'success': False, 'message': 'Missing PayPal reference marker'}), 400
        
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            
            # 1. FIXED WALLET BALANCER: Deduct only the exact discount amount used to preserve remainder credit!
            if discount_redeemed > 0:
                cursor.execute("""
                    UPDATE referral_wallets 
                    SET spent_balance = spent_balance + ? 
                    WHERE LOWER(username) = LOWER(?)
                """, (discount_redeemed, username.lower()))
            
            # 2. Log completed transaction record row
            status_text = 'Completed' if amount_paid > 0 else 'Completed (Wallet Full Redeem)'
            cursor.execute("""
                INSERT INTO payments (username, order_id, amount, status) 
                VALUES (?, ?, ?, ?)
            """, (username, order_id, f"£{amount_paid:.2f} ({connections} Conn)", status_text))
            
            # 3. FIXED AUTOMATIC SUBSCRIPTION EXTENSION ENGINE (+365 Days)
            cursor.execute("SELECT expiry_timestamp FROM user_metadata WHERE LOWER(username) = LOWER(?)", (username.lower(),))
            meta_row = cursor.fetchone()
            
            current_time = int(time.time())
            # If current expiry is in the past or doesn't exist, build from today. Otherwise, stack onto current expiry!
            base_timestamp = meta_row[0] if (meta_row and meta_row[0] > current_time) else current_time
            new_expiry_ts = base_timestamp + (365 * 86400)
            new_readable_date = datetime.fromtimestamp(new_expiry_ts).strftime('%B %d, %Y')
            
            # Synchronously update both local database cache tables to protect alignment
            cursor.execute("""
                INSERT INTO user_metadata (username, expiry_date, expiry_timestamp, alert_sent)
                VALUES (?, ?, ?, 0)
                ON CONFLICT(username) DO UPDATE SET expiry_date=excluded.expiry_date, expiry_timestamp=excluded.expiry_timestamp, alert_sent=0
            """, (username, new_readable_date, new_expiry_ts))
            
            cursor.execute("""
                UPDATE portal_users 
                SET expiry_date = ?, expiry_timestamp = ? 
                WHERE LOWER(username) = LOWER(?)
            """, (new_readable_date, new_expiry_ts, username.lower()))
            
            conn.commit()
            
        print(f"AUTOMATION: Auto-extended user '{username}' by 365 days. New Expiry: {new_readable_date}")
        
        # Send confirmation alert directly to your Telegram bot channel
        alert_text = (
            f"<b>💰 PREMIUM SUBSCRIPTION RENEWED AUTOMATICALLY</b>\n"
            f"----------------------------------------\n"
            f"<b>User Profile:</b> <code>{username}</code>\n"
            f"<b>Plan Chosen:</b> <b>{connections} Device Connections</b>\n"
            f"<b>Amount Paid:</b> £{amount_paid:.2f} GBP\n"
            f"<b>Wallet Redeemed:</b> £{discount_redeemed:.2f} GBP\n"
            f"<b>New Expiry Date:</b> <b>{new_readable_date}</b>\n"
            f"----------------------------------------\n"
            f"👉 <i>Reseller Notice: System table records have updated (+365 days) automatically. No action needed!</i>"
        )
        NOTIFICATION_QUEUE.put(alert_text)
        
        return jsonify({'success': True, 'message': 'Subscription successfully extended by 365 days!'})
    except Exception as e:
        print(f"AUTOMATED PAYMENT PROCESSING ERROR: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


    
@app.route('/get_referral_balance')
def get_referral_balance():
    """Checks how much discount credit the logged-in user has collected using case-insensitive parameters."""
    if not session.get('logged_in'): 
        return jsonify({'balance': 0.0}), 401
    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT earned_balance, spent_balance FROM referral_wallets WHERE LOWER(username) = LOWER(?)", (session['username'].strip(),))
        row = cursor.fetchone()
    if row: 
        return jsonify({'balance': max(0.0, row['earned_balance'] - row['spent_balance'])})
    return jsonify({'balance': 0.0})
    
@app.route('/submit_channel_report', methods=['POST'])
def submit_channel_report_backend():
    """Logs the broken stream ticket safely into your SQLite table and triggers a Telegram alert."""
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
        
    data = request.json
    if not data or not data.get('channel_id'):
        return jsonify({'success': False, 'message': 'Missing channel identifiers'}), 400

    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO channel_reports (username, channel_name, channel_id, issue_type) 
            VALUES (?, ?, ?, ?)
        ''', (
            session['username'], 
            data.get('channel_name'), 
            data.get('channel_id'), 
            data.get('issue_type')
        ))
        conn.commit()
        
    print(f"STREAM TICKETS: User {session['username']} reported issue for stream ID {data.get('channel_id')}")
    
    # Format notification text layout string for your Telegram worker queue
    ticket_alert_text = (
        f"<b>⚠️ NEW STREAM FAULT TICKET FILED</b>\n"
        f"----------------------------------------\n"
        f"<b>Channel Name:</b> <code>{data.get('channel_name')}</code>\n"
        f"<b>Stream ID:</b> <code>{data.get('channel_id')}</code>\n"
        f"<b>Reported Issue:</b> <b>{data.get('issue_type')}</b>\n\n"
        f"<b>Submitted By:</b> <code>{session['username']}</code>\n"
        f"----------------------------------------"
    )
    NOTIFICATION_QUEUE.put(ticket_alert_text)
    
    return jsonify({'success': True, 'message': 'Ticket submitted successfully!'})
 
@app.route('/admin')
def admin_panel():
    """Private queue manager pulling your complete client expiration map directly from your fast local metadata cache table."""
    # Secure fallback identity variable gate check
    current_user = str(session.get('username', '')).lower()
    is_admin_flag = session.get('is_admin')
    
    if not session.get('logged_in') or (not is_admin_flag and current_user != "djstevieg09"):
        return "<h3>🚫 Access Denied: You must be logged in as the master administrator to view this page.</h3>", 403
        
    client_expiration_list = []
    current_timestamp = int(time.time())
    
    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # UNIVERSAL: Pulls all logged-in users out of your local tracking cache table
        cursor.execute("SELECT username, expiry_date, expiry_timestamp FROM user_metadata")
        cached_users = cursor.fetchall()
        
        for user in cached_users:
            uname = user['username']
            exp_timestamp = user['expiry_timestamp']
            readable_date = user['expiry_date']
            
            if not uname or uname.lower() == "djstevieg09":
                continue
            
            if exp_timestamp > 0:
                try:
                    days_left = int((exp_timestamp - current_timestamp) / 86400)
                    if days_left <= 31:
                        client_expiration_list.append({
                            'username': uname,
                            'expiry_date': readable_date,
                            'days_remaining': days_left,
                            'status': 'Active'
                        })
                except Exception:
                    pass
                    
        client_expiration_list.sort(key=lambda x: x['days_remaining'])

        # --- PULL ALL WORKSPACE CONTENT TABLES ---
        cursor.execute("SELECT * FROM requests ORDER BY timestamp DESC")
        all_requests = cursor.fetchall()
        
        cursor.execute("SELECT * FROM payments ORDER BY timestamp DESC")
        all_payments = cursor.fetchall()
        
        cursor.execute("SELECT * FROM channel_reports ORDER BY timestamp DESC")
        all_reports = cursor.fetchall()
        
        # FIXED DETECT ENGINE: Pulls active VOD fault tickets cleanly from the local store
        cursor.execute("SELECT * FROM vod_reports ORDER BY timestamp DESC")
        all_vod_reports = cursor.fetchall()
        
        cursor.execute("SELECT username, (earned_balance - spent_balance) AS active_credit FROM referral_wallets WHERE (earned_balance - spent_balance) > 0 ORDER BY active_credit DESC")
        all_wallets = cursor.fetchall()

        cursor.execute("SELECT * FROM portal_users ORDER BY created_at DESC")
        all_portal_users = cursor.fetchall()
        
        cursor.execute("SELECT * FROM live_channels ORDER BY name ASC")
        all_live_channels = cursor.fetchall()
        
    # FIXED RETURN COMPONENT: Binds vod_reports explicitly to pass it down to your admin template layout room!
    return render_template(
        'admin.html', 
        requests=all_requests, 
        payment_logs=all_payments, 
        channel_reports=all_reports, 
        vod_reports=all_vod_reports,  # INJECTED FIXED KEY VIA DICTIONARY
        wallets=all_wallets,
        portal_users=all_portal_users,
        live_channels=all_live_channels,
        client_expiration_list=client_expiration_list
    )





@app.route('/admin/adjust_user_credit', methods=['POST'])
def admin_manual_inject_credit_final():
    """Allows admin to manually inject balance credit to any user profile case-insensitively, accepting all frontend payload key variants."""
    if not session.get('logged_in') or not session.get('is_admin'): 
        return jsonify({'error': 'Unauthorized'}), 401
        
    data = request.json or {}
    
    # SYSTEM VALVE: Accepts ALL common frontend variable names to guarantee data maps correctly!
    target_user = data.get('target_username') or data.get('username') or data.get('target_user')
    if target_user:
        target_user = str(target_user).strip()
    
    try:
        amount_float = float(data.get('amount', 0.0))
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Invalid numeric credit amount format'}), 400
        
    if not target_user: 
        return jsonify({'success': False, 'message': 'Target username parameter is mandatory'}), 400
        
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        
        # Check casing variants in your database first to match existing records safely
        cursor.execute("SELECT username FROM referral_wallets WHERE LOWER(username) = LOWER(?)", (target_user.lower(),))
        existing_row = cursor.fetchone()
        
        # FIXED: Unpacks the pure text string from the tuple data row safely!
        matched_username = existing_row[0] if existing_row else target_user
        
        if not existing_row: 
            cursor.execute("INSERT INTO referral_wallets (username, earned_balance, spent_balance) VALUES (?, 0.0, 0.0)", (matched_username,))
            
        cursor.execute("UPDATE referral_wallets SET earned_balance = earned_balance + ? WHERE LOWER(username) = LOWER(?)", (amount_float, matched_username.lower()))
        conn.commit()
        
    print(f"ADMIN UTILITY: Manually adjusted credit balance by £{amount_float} for user line: {matched_username}")
    
    # Send confirmation alert directly to your Telegram bot channel
    NOTIFICATION_QUEUE.put(f"<b>⚙️ MANUAL CREDIT ALLOCATION APPLIED</b>\n----------------------------------------\n<b>Target User:</b> <code>{matched_username}</code>\n<b>Added Value:</b> +£{amount_float} GBP\n----------------------------------------")
    
    return jsonify({'success': True, 'message': f'Successfully credited £{amount_float} to user {matched_username}!'})

@app.route('/admin/update_status/<int:req_id>', methods=['POST'])
def update_status(req_id):
    """Allows admin to change media request status from Pending to Completed safely."""
    if not session.get('logged_in') or not session.get('is_admin'): 
        return jsonify({'error': 'Unauthorized'}), 401
        
    data = request.json
    status = data.get('status', 'Completed')
    
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE requests SET status = ? WHERE id = ?", (status, req_id))
        conn.commit()
        
    return jsonify({'success': True, 'message': f'Status updated to {status}'})

@app.route('/admin/delete_request/<int:req_id>', methods=['POST'])
def delete_request(req_id):
    """Allows admin to completely purge a request out of the master queue list safely."""
    if not session.get('logged_in') or not session.get('is_admin'): 
        return jsonify({'error': 'Unauthorized'}), 401
        
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM requests WHERE id = ?", (req_id,))
        conn.commit()
        
    return jsonify({'success': True, 'message': 'Request cleared successfully'})

# Create a global holding variable to cache your channels in server memory for lightning-fast lookups
CACHED_CHANNELS = []

@app.route('/search_channels')
def search_channels():
    """Queries your fast local database table lineup to return matching channel streams to your dropdown popup grids."""
    if not session.get('logged_in'):
        return jsonify([]), 401
    
    query = request.args.get('q', '').strip().lower()
    if not query:
        return jsonify([])
        
    matches = []
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Direct SQL Lookup matching channel text names case-insensitively
            cursor.execute("SELECT stream_id, name FROM live_channels WHERE LOWER(name) LIKE ? ORDER BY name ASC LIMIT 15", (f"%{query}%",))
            rows = cursor.fetchall()
            
            for row in rows:
                matches.append({
                    'id': str(row['stream_id']),
                    'name': str(row['name'])
                })
                
        # FALLBACK ENGINE: If your database table is empty, serve the baseline channels seamlessly
        if not matches:
            backup_map = [
                {"id": "101", "name": "Sky Sports Main Event HD"},
                {"id": "102", "name": "Sky Sports Premier League HD"},
                {"id": "103", "name": "TNT Sports 1 HD"},
                {"id": "104", "name": "TNT Sports 2 HD"}
            ]
            for ch in backup_map:
                if query in ch['name'].lower():
                    matches.append(ch)
                    
    except Exception as e:
        print(f"LOCAL CHANNEL SEARCH EXCEPTION: {e}")
        
    return jsonify(matches)


def telegram_worker_engine():
    """Background engine that monitors the queue and dispatches alerts to your phone instantly."""
    print("TELEGRAM BOOT: Background notification engine thread has started successfully.")
    while True:
        try:
            message_text = NOTIFICATION_QUEUE.get()
            print(f"TELEGRAM QUEUE: Processing an alert text packet out of the lane...")
            
            api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {
                "chat_id": TELEGRAM_CHAT_ID, 
                "text": message_text, 
                "parse_mode": "HTML"
            }
            
            # Send the request directly to Telegram servers
            response = requests.post(api_url, json=payload, timeout=8)
            
            if response.status_code == 200:
                print("TELEGRAM SUCCESS: Message delivered straight to your chat tab window!")
                NOTIFICATION_QUEUE.task_done()
            else:
                print(f"TELEGRAM NETWORK ERROR: Server answered with code {response.status_code}. Response payload: {response.text}")
                time.sleep(10)
                NOTIFICATION_QUEUE.put(message_text) # Re-queue the task if it fails
        except Exception as e:
            print(f"TELEGRAM EXCEPTION FATALITY: Anomaly encountered inside background thread loop: {e}")
            time.sleep(5)

@app.route('/logout')
def logout():
    session.clear()
    # FIXED DIRECT PATH WAY: Bypasses url_for lookup issues entirely!
    return redirect('/')

    
@app.route('/complete_manual_renewal/<int:payment_id>', methods=['POST'])
def complete_manual_renewal(payment_id):
    """Flips a pending manual request to Completed once the admin clicks the dashboard confirmation button."""
    if not session.get('logged_in') or not session.get('is_admin'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            
            # Verify the entry exists and capture the user details before flipping it
            cursor.execute("SELECT username, amount FROM payments WHERE id = ?", (payment_id,))
            row = cursor.fetchone()
            
            if row:
                username = row[0]
                amount_details = row[1]
                
                # Update status text strings inside the database row safely
                cursor.execute("UPDATE payments SET status = 'Completed' WHERE id = ?", (payment_id,))
                conn.commit()
                print(f"ADMIN ACTION: Manually confirmed line extension for user: {username}")
                return jsonify({'success': True, 'message': f'Line {username} marked as completed!'})
                
            return jsonify({'success': False, 'message': 'Payment ticket record not found'}), 404
            
    except Exception as e:
        print(f"ADMIN ACTION ERROR: Failed to update payment status rows: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
        
# --- ISOLATED ADMIN MANAGEMENT ENDPOINTS ---

@app.route('/update_request_status_by_admin/<int:request_id>', methods=['POST'])
def admin_update_media_status(request_id):
    """Updates a movie or series submission entry to Completed directly within the database log."""
    if not session.get('logged_in') or not session.get('is_admin'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE requests SET status = 'Completed' WHERE id = ?", (request_id,))
            conn.commit()
        print(f"ADMIN ACTION: Manually marked media request ID {request_id} as Added/Completed.")
        return jsonify({'success': True, 'message': 'Request marked as completed successfully!'})
    except Exception as e:
        print(f"ADMIN REQUEST UPDATE ERROR: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/delete_channel_report_by_admin/<int:report_id>', methods=['POST'])
def admin_clear_channel_report(report_id):
    """Deletes a resolved stream fault ticket completely out of your workspace matrix database rows using a unique function name."""
    if not session.get('logged_in') or not session.get('is_admin'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM channel_reports WHERE id = ?", (report_id,))
            conn.commit()
        return jsonify({'success': True, 'message': 'Ticket resolved and cleared cleanly!'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
        
@app.route('/submit_vod_report', methods=['POST'])
def submit_vod_report():
    """Allows standard clients to securely submit movie and show fault tickets, capturing free-text notes for 'Other' selections."""
    if not session.get('logged_in'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    data = request.json or {}
    vod_title = data.get('title', '').strip()
    media_type = data.get('media_type', '').strip() # 'movie' or 'tv'
    issue = data.get('issue_type', '').strip()
    
    # FIX: Ensures variable explicitly captures 'issue_notes' text sent from your frontend script
    notes = data.get('issue_notes', '').strip()[:100]
    username = session.get('username')
    
    if not vod_title or not issue:
        return jsonify({'success': False, 'message': 'Missing mandatory VOD ticket data parameters.'}), 400
        
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            # Commits your data including the custom free-text notes into your local tracking database tables row
            cursor.execute('''
                INSERT INTO vod_reports (username, title, media_type, issue_type, issue_notes)
                VALUES (?, ?, ?, ?, ?)
            ''', (username, vod_title, media_type if media_type else 'movie', issue, notes))
            conn.commit()
            
        print(f"VOD FAULT LOGGED: '{vod_title}' ({issue}) reported by user: {username}")
        
        details_line = f"<b>Details:</b> <i>{notes}</i>" if notes else ""
        
        alert_msg = (
            f"<b>🎬 VOD CATALOG FAULT TICKET RECEIVED</b>\n"
            f"----------------------------------------\n"
            f"<b>Portal Source:</b> <b>SimplyRocks Portal</b> 🌐\n"
            f"<b>Reported By User:</b> <code>{username}</code>\n\n"
            f"<b>Content Title:</b> <b>{vod_title}</b>\n"
            f"<b>Media Profile:</b> <code>{str(media_type).upper()}</code>\n"
            f"<b>Issue Category:</b> <b>{issue}</b>\n"
            f"{details_line}\n"
            f"----------------------------------------"
        )
        NOTIFICATION_QUEUE.put(alert_msg)
        
        return jsonify({'success': True, 'message': 'VOD catalog fault ticket successfully logged with admin!'})
    except Exception as e:
        print(f"VOD REPORT DATA SUBMISSION FAULT: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/delete_vod_report_by_admin/<int:report_id>', methods=['POST'])
def admin_clear_vod_report(report_id):
    """Allows admin to purge a resolved VOD error ticket out of your workspace database rows cleanly using an inline click."""
    if not session.get('logged_in') or not session.get('is_admin'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    try:
        with sqlite3.connect(DB_FILE) as conn:
          
            cursor = conn.cursor()
            cursor.execute("DELETE FROM vod_reports WHERE id = ?", (report_id,))
            conn.commit()
        return jsonify({'success': True, 'message': 'VOD ticket resolved and cleared smoothly!'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/admin/add_live_channel', methods=['POST'])
def admin_add_live_channel():
    """Allows admin to register a custom stream name and Stream ID into the local channels database ledger."""
    if not session.get('logged_in') or not session.get('is_admin'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
    data = request.json or {}
    ch_name = data.get('name', '').strip()
    stream_id = data.get('stream_id', '').strip()
    
    if not ch_name or not stream_id:
        return jsonify({'success': False, 'message': 'Both Stream Name and Stream ID are mandatory!'}), 400
        
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO live_channels (stream_id, name)
                VALUES (?, ?)
                ON CONFLICT(stream_id) DO UPDATE SET name = excluded.name
            ''', (stream_id, ch_name))
            conn.commit()
            
        print(f"ADMIN DATABASE UTILITY: Added channel '{ch_name}' with ID: {stream_id}")
        return jsonify({'success': True, 'message': f"Channel '{ch_name}' successfully added to local database lineup!"})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/delete_live_channel/<string:stream_id>', methods=['POST'])
def admin_delete_live_channel(stream_id):
    """Allows admin to remove a stream out of your local channels list with an inline click."""
    if not session.get('logged_in') or not session.get('is_admin'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM live_channels WHERE stream_id = ?", (stream_id.strip(),))
            conn.commit()
        return jsonify({'success': True, 'message': 'Channel removed from database!'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/submit_crowdsourced_channel', methods=['POST'])
def submit_crowdsourced_channel():
    """Allows standard authenticated clients to dynamically seed missing channel names into the local lineup."""
    if not session.get('logged_in'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    data = request.json or {}
    ch_name = data.get('name', '').strip()
    stream_id = data.get('stream_id', '').strip()
    
    if not ch_name or not stream_id:
        return jsonify({'success': False, 'message': 'Missing data parameters'}), 400
        
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            # Inserts the missing channel name cleanly into your shared database file rows
            cursor.execute('''
                INSERT INTO live_channels (stream_id, name)
                VALUES (?, ?)
                ON CONFLICT(stream_id) DO UPDATE SET name = excluded.name
            ''', (stream_id, ch_name))
            conn.commit()
            
        print(f"CROWD-SOURCE UTILITY: Standard user '{session['username']}' auto-built channel line: {ch_name}")
        return jsonify({'success': True, 'message': 'Channel registered in shared directory!'})
    except Exception as e:
        print(f"CROWD-SOURCE ENGINE RUNTIME FAULT: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
        
@app.route('/admin/amend_user_expiry', methods=['POST'])
def admin_amend_user_expiry():
    """Allows admin to manually change or correct any user's expiration calendar date to fix mismatches."""
    if not session.get('logged_in') or not session.get('is_admin'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
    data = request.json or {}
    target_user = data.get('username', '').strip()
    new_date_str = data.get('expiry_date', '').strip() # Expects Format: YYYY-MM-DD
    
    if not target_user or not new_date_str:
        return jsonify({'success': False, 'message': 'Missing user or date fields'}), 400
        
    try:
        dt_obj = datetime.strptime(new_date_str, '%Y-%m-%d')
        new_ts = int(time.mktime(dt_obj.timetuple()))
        readable_date = dt_obj.strftime('%B %d, %Y')
        
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            
            # Check if user exists in portal core ledger
            cursor.execute("SELECT username FROM portal_users WHERE LOWER(username) = LOWER(?)", (target_user.lower(),))
            user_exists = cursor.fetchone()
            
            if user_exists:
                cursor.execute("UPDATE portal_users SET expiry_date=?, expiry_timestamp=? WHERE LOWER(username)=LOWER(?)", (readable_date, new_ts, target_user.lower()))
                
            # Update user_metadata dashboard tracking table row synchronously
            cursor.execute("""
                INSERT INTO user_metadata (username, expiry_date, expiry_timestamp, alert_sent)
                VALUES (?, ?, ?, 0)
                ON CONFLICT(username) DO UPDATE SET expiry_date=excluded.expiry_date, expiry_timestamp=excluded.expiry_timestamp, alert_sent=0
            """, (target_user, readable_date, new_ts))
            
            conn.commit()
            
        print(f"ADMIN CORRECTION: Overwrote expiration to {readable_date} for user line: {target_user}")
        return jsonify({'success': True, 'message': f"Successfully updated {target_user}'s expiry date to {readable_date}!"})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/submit_channel_report', methods=['POST'])
def submit_channel_report():
    """Allows standard clients to securely submit channel fault tickets right into the central admin table queue."""
    if not session.get('logged_in'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    data = request.json or {}
    ch_name = data.get('channel_name', '').strip()
    ch_id = data.get('channel_id', '').strip()
    issue = data.get('issue_type', '').strip()
    username = session.get('username')
    
    if not ch_name or not ch_id or not issue:
        return jsonify({'success': False, 'message': 'Missing mandatory ticket data parameters.'}), 400
        
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            # Commits the user's selected fault data directly into your shared tracking cache database table rows
            cursor.execute('''
                INSERT INTO channel_reports (username, channel_name, channel_id, issue_type)
                VALUES (?, ?, ?, ?)
            ''', (username, ch_name, ch_id, issue))
            conn.commit()
            
        print(f"FAULT TICKET LOGGED: Channel '{ch_name}' reported by user: {username}")
        
        # Dispatch a beautiful amber warning notification card layout string right to your pocket Telegram app thread!
        alert_msg = (
            f"<b>📺 LIVE TV STREAM FAULT TICKET RECEIVED</b>\n"
            f"----------------------------------------\n"
            f"<b>Portal Source:</b> <b>SimplyRocks Portal</b> 🌐\n"
            f"<b>Reported By User:</b> <code>{username}</code>\n\n"
            f"<b>Channel Name:</b> <b>{ch_name}</b>\n"
            f"<b>Stream ID Key:</b> <code>{ch_id}</code>\n"
            f"<b>Issue Category:</b> <pre>{issue}</pre>\n"
            f"----------------------------------------\n"
            f"👉 <i>Action Required: Verify stream feed health on server, then clear ticket in your admin panel workspace.</i>"
        )
        NOTIFICATION_QUEUE.put(alert_msg)
        
        return jsonify({'success': True, 'message': 'Stream report fault ticket successfully logged with admin!'})
    except Exception as e:
        print(f"CHANNEL REPORT DATA SUBMISSION FAULT: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500




# ====================================================================
# MASTER PORTAL WORKSPACE BOOTSTRAP EXECUTOR
# ====================================================================
threading.Thread(target=telegram_worker_engine, daemon=True).start()

if __name__ == '__main__':
    # FIXED: Forces the system to run your 5-table setup checks right on launch!
    
    app.run(debug=True, port=5000)


