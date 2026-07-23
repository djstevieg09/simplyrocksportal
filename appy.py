import os
import re
import time
import random
import sqlite3
from datetime import datetime
from queue import Queue
from threading import Thread

import requests
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash

# --- 1. INITIALISE MAIN FLASK APP INSTANCE (MUST BE DECLARED FIRST) ---
app = Flask(__name__)
app.secret_key = "simplyrocks_secure_master_portal_key_string_09"

# --- 2. GLOBAL SYSTEM CONFIGURATION & HARDWARE LINK PATHS ---
DEFAULT_DNS = "http://simplyrocks.org:80"
TMDB_API_KEY = os.environ.get('TMDB_API_KEY')

# FIXED PERMANENT VAULT ROADMAP: Keeps your database file 100% safe from cloud reboots!
DB_FILE = "/data/database.db"

# --- 3. QUEUE STORAGE CONFIGURATIONS ---
NOTIFICATION_QUEUE = Queue()

# --- MASTER RESELLER CODES AUTO-EXTEND CONFIGURATION ---
RESELLER_PANEL_URL = "https://theservice.rocks:80"
RESELLER_USERNAME = os.environ.get('RESELLER_USER')
RESELLER_PASSWORD = os.environ.get('RESELLER_PASS')

# --- TELEGRAM BOT ALERTS CONFIGURATION ---
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# Xtream default password for sync (moved from hard-coded string)
XTREAM_DEFAULT_PASSWORD = os.environ.get('XTREAM_DEFAULT_PASSWORD', '')


def init_db():
    """Initialises database structures and forces data column schema expansions on persistent disk tables safely."""
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

        # 7. Secure Local Portal User Accounts Ledger Table Structure Mount
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

        # DATABASE MIGRATION ENGINE FOR vod_reports.issue_notes
        try:
            cursor.execute("ALTER TABLE vod_reports ADD COLUMN issue_notes TEXT DEFAULT ''")
            print("DATABASE AUTOMATION: Successfully injected 'issue_notes' column into persistent storage disk!")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                pass
            else:
                print(f"DATABASE UPDATE NOTICE: {e}")

        conn.commit()


# Trigger the clean build immediately on file parse!
init_db()

# FIXED DEFINITION: Capitalized to match your explicit top-level module imports
NOTIFICATION_QUEUE = Queue()

# Create a global holding variable to cache your channels in server memory for lightning-fast lookups
CACHED_CHANNELS = []


def is_admin():
    """Central admin check, using session and environment-based master username."""
    secure_admin_username = (os.environ.get('PORTAL_ADMIN_USER') or "djstevieg09").lower()
    current_user = str(session.get('username', '')).lower()
    return session.get('logged_in') and (session.get('is_admin') or current_user == secure_admin_username)


def send_telegram_alert_direct(message_text):
    """Safely extracts your hidden tokens from Render's variables and routes them to the correct Telegram API endpoint."""
    try:
        bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
        chat_id = os.environ.get('TELEGRAM_CHAT_ID')

        if not bot_token or not chat_id:
            print("TELEGRAM NOTICE: Missing secure environment keys inside your Render settings panel.", flush=True)
            return False

        # Correct official Telegram API address:
        api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

        payload = {
            "chat_id": chat_id,
            "text": message_text,
            "parse_mode": "HTML"
        }

        response = requests.post(api_url, json=payload, timeout=8)
        print(f"TELEGRAM DIRECT PUSH CODE: {response.status_code}", flush=True)
        return response.status_code == 200
    except Exception as e:
        print(f"TELEGRAM DIRECT PUSH ERROR: {e}", flush=True)
        return False


def trigger_automatic_panel_extension(client_username, connections_count):
    """Connects directly to the official master panel api.php script to deduct credits and auto-extend lines instantly."""
    try:
        api_endpoint = f"{DEFAULT_DNS.rstrip('/')}/api.php"

        package_id_map = {
            '1': '66',  # 1 Connection 12 Months
            '2': '70',  # 2 Connections 12 Months
            '3': '74',  # 3 Connections 12 Months
            '4': '78'   # 4 Connections 12 Months
        }

        target_package = package_id_map.get(str(connections_count), '66')
        print(f"AUTOMATION: Sending official API payload to extend line {client_username} with Package {target_package}...")

        payload = {
            'action': 'extend',
            'username': RESELLER_USERNAME,
            'password': RESELLER_PASSWORD,
            'sub_user': client_username,
            'package_id': target_package
        }

        response = requests.get(api_endpoint, params=payload, timeout=15)

        if response.status_code == 200:
            res_text = response.text.strip().lower()

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
    """
    Authenticates clients securely against local portal_users database.
    (Note: This is local verification, not remote Xtream API.)
    """
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM portal_users WHERE LOWER(username) = LOWER(?)", (username.strip().lower(),))
            user_row = cursor.fetchone()

        if user_row and check_password_hash(user_row['password'], password.strip()):
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
    """Handles secure user and administrator authentication, strictly validating credentials against the local server."""
    if request.method == 'GET':
        return render_template('login.html', default_dns=DEFAULT_DNS)

    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()

    if not username or not password:
        return render_template('login.html', error="Please supply both username and password configurations.")

    # --- 1. ADMINISTRATIVE LOGIN MASTER LOCAL BYPASS CHANNEL ---
    secure_admin_username = os.environ.get('PORTAL_ADMIN_USER')
    secure_admin_password = os.environ.get('PORTAL_ADMIN_PASS')

    if secure_admin_username and secure_admin_password:
        if username.lower() == secure_admin_username.lower() and password == secure_admin_password:
            session['logged_in'] = True
            session['username'] = username
            session['password'] = password
            session['is_admin'] = True
            session['expiry_date'] = "Reseller Control"
            print("ADMIN LOGIN DETECTED: Locally validated credentials via cloud environment. Routing to console...")
            return redirect('/admin')

    # --- 2. CLIENT TIER CHANNEL: Local Validation ---
    dns = DEFAULT_DNS
    success, user_info = verify_xtream_credentials(dns, username, password)

    if success and user_info:
        session['logged_in'] = True
        session['username'] = username
        session['password'] = password
        session['is_admin'] = False

        print("\n--- XTREAM CODES SERVER RESPONSE SNAPSHOT (LOCAL MOCK) ---")
        raw_exp = user_info.get('exp_date')
        print(f"Extracted genuine exp_date string: {raw_exp}")
        print("---------------------------------------------------------\n")

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
                    send_telegram_alert_direct(countdown_warning_text)
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
        return render_template('login.html', error="Invalid username or password profile details.")


@app.route('/admin/create_portal_user', methods=['POST'])
def admin_create_portal_user():
    """Manually registers custom user access lines into the local database."""
    if not is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    data = request.json or {}
    uname = data.get('username', '').strip()
    pword = data.get('password', '').strip()
    exp_str = data.get('expiry_date', '').strip()  # Expecting Format: YYYY-MM-DD

    if not uname or not pword or not exp_str:
        return jsonify({'success': False, 'message': 'All entry profile parameters are mandatory'}), 400

    try:
        dt_obj = datetime.strptime(exp_str, '%Y-%m-%d')
        exp_ts = int(time.mktime(dt_obj.timetuple()))
        readable_date = dt_obj.strftime('%B %d, %Y')

        hashed_pword = generate_password_hash(pword)

        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO portal_users (username, password, expiry_date, expiry_timestamp)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(username) DO UPDATE SET
                    password = excluded.password,
                    expiry_date = excluded.expiry_date,
                    expiry_timestamp = excluded.expiry_timestamp
            ''', (uname, hashed_pword, readable_date, exp_ts))

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
        send_telegram_alert_direct(countdown_warning_text)

        return jsonify({'success': True, 'message': f"Account line '{uname}' saved to portal registry ledger!"})
    except Exception as e:
        print(f"ADMIN ACC GENERATION FAILURE: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/delete_portal_user/<string:username>', methods=['POST'])
def admin_delete_portal_user(username):
    """Allows admin to completely wipe a registered user account."""
    if not is_admin():
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


@app.route('/sync_live_panel_expirations', methods=['POST'])
def sync_live_panel_expirations():
    """Reads all logged-in usernames from local storage, wipes the dashboard cache view, and rebuilds it using fresh panel data."""
    if not is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    sync_count = 0
    captured_count = 0
    current_timestamp = int(time.time())

    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT username FROM user_metadata")
            tracked_users = [row['username'].strip() for row in cursor.fetchall()]

        if not tracked_users:
            tracked_users = ["DC-Firestick"]

        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM user_metadata")
            conn.commit()

        print("\n--- LIVE EXPIRED-GATE MONITOR AUTOMATION ENGAGED ---")

        for uname in tracked_users:
            if not uname or (RESELLER_USERNAME and uname.lower() == RESELLER_USERNAME.lower()):
                continue

            try:
                api_endpoint = f"{DEFAULT_DNS.rstrip('/')}/player_api.php"
                response = requests.get(api_endpoint, params={
                    'username': uname,
                    'password': XTREAM_DEFAULT_PASSWORD
                }, timeout=5)

                if response.status_code == 200:
                    panel_data = response.json()
                    user_info = panel_data.get('user_info', {}) if isinstance(panel_data, dict) else {}
                    raw_exp = user_info.get('exp_date')

                    if raw_exp and str(raw_exp).strip().lower() not in ['null', '', '0', 'none', 'false']:
                        exp_ts = int(raw_exp)
                        readable_date = datetime.fromtimestamp(exp_ts).strftime('%B %d, %Y')
                        days_left = int((exp_ts - current_timestamp) / 86400)

                        with sqlite3.connect(DB_FILE) as conn2:
                            cursor2 = conn2.cursor()
                            cursor2.execute('''
                                INSERT INTO user_metadata (username, expiry_date, expiry_timestamp, alert_sent)
                                VALUES (?, ?, ?, 0)
                            ''', (uname, readable_date, exp_ts))
                            conn2.commit()

                        if days_left <= 31:
                            print(f"DASHBOARD CAPTURE: Saved expiring user onto matrix view: {uname} ({days_left} Days Left)")
                            captured_count += 1
                        else:
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

    days_remaining = None
    show_expiry_warning = False

    if session.get('password') and session.get('username'):
        success, user_info = verify_xtream_credentials(DEFAULT_DNS, session['username'], session['password'])
        if success and user_info:
            raw_exp = user_info.get('exp_date')
            if raw_exp and str(raw_exp).strip().lower() not in ['null', '', '0', 'none', 'false']:
                try:
                    exp_timestamp = int(raw_exp)
                    current_timestamp = int(time.time())
                    seconds_left = exp_timestamp - current_timestamp
                    days_remaining = int(seconds_left / 86400)

                    # Show expiry warning if 7 days or less remaining
                    if days_remaining <= 7:
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
    """Generates standalone portal accounts for referred friends and rewards referrer."""
    if not session.get('logged_in'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    data = request.json or {}
    f_name = data.get('first_name', '').strip().capitalize()
    l_name = data.get('last_name', '').strip().capitalize()
    phone_str = data.get('phone', '').strip()
    referrer = session.get('username')

    if not f_name or not l_name or not phone_str:
        return jsonify({'success': False, 'message': '❌ REJECTION: First name, Last name, and Phone fields are strictly mandatory!'}), 400

    try:
        generated_username = f"{f_name}-{l_name}"

        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT username FROM portal_users WHERE LOWER(username) = LOWER(?)", (generated_username.lower(),))
            collision_row = cursor.fetchone()

            if collision_row:
                generated_username = f"{f_name}-{l_name}-{random.randint(10, 99)}"

            generated_password_plain = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=8))
            generated_password_hashed = generate_password_hash(generated_password_plain)
            one_year_ts = int(time.time()) + (365 * 86400)
            readable_expiry = datetime.fromtimestamp(one_year_ts).strftime('%B %d, %Y')

            cursor.execute('''
                INSERT INTO portal_users (username, password, expiry_date, expiry_timestamp)
                VALUES (?, ?, ?, ?)
            ''', (generated_username, generated_password_hashed, readable_expiry, one_year_ts))

            cursor.execute('''
                INSERT INTO user_metadata (username, expiry_date, expiry_timestamp, alert_sent)
                VALUES (?, ?, ?, 0)
            ''', (generated_username, readable_expiry, one_year_ts))

            cursor.execute("SELECT username FROM referral_wallets WHERE LOWER(username) = LOWER(?)", (referrer.lower(),))
            wallet_exists = cursor.fetchone()
            if not wallet_exists:
                cursor.execute("INSERT INTO referral_wallets (username, earned_balance, spent_balance) VALUES (?, 0.0, 0.0)", (referrer,))

            cursor.execute("UPDATE referral_wallets SET earned_balance = earned_balance + 25.00 WHERE LOWER(username) = LOWER(?)", (referrer.lower(),))
            conn.commit()

        print(f"REFERRAL ENFORCER: Created new customer profile: {generated_username}")

        notification_text = (
            f"<b>🎉 NEW REFERRAL ACQUIRED [+£25 CREDIT UNLOCKED]</b>\n"
            f"----------------------------------------\n"
            f"<b>Portal Source:</b> <b>SimplyRocks Portal</b> 🌐\n"
            f"<b>Referrer User:</b> <code>{referrer}</code>\n"
            f"<b>Added Credit:</b> +£25.00 Reward Balance 💰\n\n"
            f"<b>New Friend Account Line Created:</b>\n"
            f"👤 <b>User:</b> <code>{generated_username}</code>\n"
            f"🔑 <b>Pass:</b> <code>{generated_password_plain}</code>\n"
            f"📅 <b>Expiry:</b> {readable_expiry}\n"
            f"----------------------------------------"
        )
        send_telegram_alert_direct(notification_text)

        return jsonify({
            'success': True,
            'generated_user': generated_username,
            'generated_pass': generated_password_plain
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

    send_telegram_alert_direct(request_alert_text)

    return jsonify({'success': True, 'message': 'Request submitted successfully!'})


def deduct_wallet_credits(user_name, spent_amount):
    """Safely records a wallet deduction by increasing spent_balance in the database ledger row history."""
    try:
        amount_val = float(spent_amount)
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO referral_wallets (username, earned_balance, spent_balance)
                VALUES (?, 0.0, 0.0)
                ON CONFLICT(username) DO NOTHING
            ''', (user_name,))

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
    """Logs purchases, subtracts discount credit, and auto-extends lines by 365 days."""
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

            if discount_redeemed > 0:
                cursor.execute("""
                    UPDATE referral_wallets
                    SET spent_balance = spent_balance + ?
                    WHERE LOWER(username) = LOWER(?)
                """, (discount_redeemed, username.lower()))

            status_text = 'Completed' if amount_paid > 0 else 'Completed (Wallet Full Redeem)'
            cursor.execute("""
                INSERT INTO payments (username, order_id, amount, status)
                VALUES (?, ?, ?, ?)
            """, (username, order_id, f"£{amount_paid:.2f} ({connections} Conn)", status_text))

            cursor.execute("SELECT expiry_timestamp FROM user_metadata WHERE LOWER(username) = LOWER(?)", (username.lower(),))
            meta_row = cursor.fetchone()

            current_time = int(time.time())
            base_timestamp = meta_row[0] if (meta_row and meta_row[0] > current_time) else current_time
            new_expiry_ts = base_timestamp + (365 * 86400)
            new_readable_date = datetime.fromtimestamp(new_expiry_ts).strftime('%B %d, %Y')

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
        send_telegram_alert_direct(alert_text)

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


@app.route('/admin')
def admin_panel():
    """Private queue manager pulling your complete client expiration map directly from your fast local metadata cache table."""
    if not is_admin():
        return "<h3>🚫 Access Denied: You must be logged in as the master administrator to view this page.</h3>", 403

    client_expiration_list = []
    current_timestamp = int(time.time())

    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT username, expiry_date, expiry_timestamp FROM user_metadata")
        cached_users = cursor.fetchall()

        secure_admin_username = (os.environ.get('PORTAL_ADMIN_USER') or "djstevieg09").lower()

        for user in cached_users:
            uname = user['username']
            exp_timestamp = user['expiry_timestamp']
            readable_date = user['expiry_date']

            if not uname or uname.lower() == secure_admin_username:
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

        cursor.execute("SELECT * FROM requests ORDER BY timestamp DESC")
        all_requests = cursor.fetchall()

        cursor.execute("SELECT * FROM payments ORDER BY timestamp DESC")
        all_payments = cursor.fetchall()

        cursor.execute("SELECT * FROM channel_reports ORDER BY timestamp DESC")
        all_reports = cursor.fetchall()

        cursor.execute("SELECT id, username, title, media_type, issue_type FROM vod_reports ORDER BY timestamp DESC")
        all_vod_reports = cursor.fetchall()

        cursor.execute("SELECT username, (earned_balance - spent_balance) AS active_credit FROM referral_wallets WHERE (earned_balance - spent_balance) > 0 ORDER BY active_credit DESC")
        all_wallets = cursor.fetchall()

        cursor.execute("SELECT * FROM portal_users ORDER BY created_at DESC")
        all_portal_users = cursor.fetchall()

        cursor.execute("SELECT * FROM live_channels ORDER BY name ASC")
        all_live_channels = cursor.fetchall()

    return render_template(
        'admin.html',
        requests=all_requests,
        payment_logs=all_payments,
        channel_reports=all_reports,
        vod_reports=all_vod_reports,
        wallets=all_wallets,
        portal_users=all_portal_users,
        live_channels=all_live_channels,
        client_expiration_list=client_expiration_list
    )


@app.route('/admin/adjust_user_credit', methods=['POST'])
def admin_manual_inject_credit_final():
    """Allows admin to manually inject balance credit to any user profile."""
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.json or {}

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

        cursor.execute("SELECT username FROM referral_wallets WHERE LOWER(username) = LOWER(?)", (target_user.lower(),))
        existing_row = cursor.fetchone()

        matched_username = existing_row[0] if existing_row else target_user

        if not existing_row:
            cursor.execute("INSERT INTO referral_wallets (username, earned_balance, spent_balance) VALUES (?, 0.0, 0.0)", (matched_username,))

        cursor.execute("UPDATE referral_wallets SET earned_balance = earned_balance + ? WHERE LOWER(username) = LOWER(?)", (amount_float, matched_username.lower()))
        conn.commit()

    print(f"ADMIN UTILITY: Manually adjusted credit balance by £{amount_float} for user line: {matched_username}")

    send_telegram_alert_direct(
        f"<b>⚙️ MANUAL CREDIT ALLOCATION APPLIED</b>\n"
        f"----------------------------------------\n"
        f"<b>Target User:</b> <code>{matched_username}</code>\n"
        f"<b>Added Value:</b> +£{amount_float} GBP\n"
        f"----------------------------------------"
    )

    return jsonify({'success': True, 'message': f'Successfully credited £{amount_float} to user {matched_username}!'})


@app.route('/admin/update_status/<int:req_id>', methods=['POST'])
def update_status(req_id):
    """Allows admin to change media request status from Pending to Completed safely."""
    if not is_admin():
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
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 401

    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM requests WHERE id = ?", (req_id,))
        conn.commit()

    return jsonify({'success': True, 'message': 'Request cleared successfully'})


@app.route('/search_channels')
def search_channels():
    """Queries your fast local database table lineup to return matching channel streams."""
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
            cursor.execute("SELECT stream_id, name FROM live_channels WHERE LOWER(name) LIKE ? ORDER BY name ASC LIMIT 15", (f"%{query}%",))
            rows = cursor.fetchall()

            for row in rows:
                matches.append({
                    'id': str(row['stream_id']),
                    'name': str(row['name'])
                })

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


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


@app.route('/complete_manual_renewal/<int:payment_id>', methods=['POST'])
def complete_manual_renewal(payment_id):
    """Flips a pending manual request to Completed once the admin clicks the dashboard confirmation button."""
    if not is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT username, amount FROM payments WHERE id = ?", (payment_id,))
            row = cursor.fetchone()

            if row:
                username = row[0]
                cursor.execute("UPDATE payments SET status = 'Completed' WHERE id = ?", (payment_id,))
                conn.commit()
                print(f"ADMIN ACTION: Manually confirmed line extension for user: {username}")
                return jsonify({'success': True, 'message': f'Line {username} marked as completed!'})

            return jsonify({'success': False, 'message': 'Payment ticket record not found'}), 404

    except Exception as e:
        print(f"ADMIN ACTION ERROR: Failed to update payment status rows: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/update_request_status_by_admin/<int:request_id>', methods=['POST'])
def admin_update_media_status(request_id):
    """Updates a movie or series submission entry to Completed directly within the database log."""
    if not is_admin():
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
    """Deletes a resolved stream fault ticket completely out of your workspace matrix database."""
    if not is_admin():
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
    """Securely submits movie and show fault tickets."""
    if not session.get('logged_in'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    data = request.json or {}
    vod_title = data.get('title', '').strip()
    media_type = data.get('media_type', '').strip()
    issue = data.get('issue_type', '').strip()
    notes = data.get('issue_notes', '').strip()[:100]
    username = session.get('username')

    if not vod_title or not issue:
        return jsonify({'success': False, 'message': 'Missing mandatory data parameters.'}), 400

    if issue == "Other" and notes:
        final_issue_string = f"Other: {notes}"
    else:
        final_issue_string = issue

    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO vod_reports (username, title, media_type, issue_type)
                VALUES (?, ?, ?, ?)
            ''', (username, vod_title, media_type if media_type else 'movie', final_issue_string))
            conn.commit()

        print(f"VOD FAULT LOGGED: '{vod_title}' -> {final_issue_string} by user: {username}")

        alert_msg = (
            f"<b>🎬 VOD CATALOG FAULT TICKET RECEIVED</b>\n"
            f"----------------------------------------\n"
            f"<b>Portal Source:</b> <b>SimplyRocks Portal</b> 🌐\n"
            f"<b>Reported By User:</b> <code>{username}</code>\n\n"
            f"<b>Content Title:</b> <b>{vod_title}</b>\n"
            f"<b>Media Profile:</b> <code>{str(media_type).upper()}</code>\n"
            f"<b>Issue Category:</b> <b>{final_issue_string}</b>\n"
            f"----------------------------------------"
        )
        send_telegram_alert_direct(alert_msg)

        return jsonify({'success': True, 'message': 'VOD catalog fault ticket successfully logged!'})
    except Exception as e:
        print(f"VOD SUBMISSION FAULT: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/add_live_channel', methods=['POST'])
def admin_add_live_channel():
    """Allows admin to register a custom stream name and Stream ID into the local channels database ledger."""
    if not is_admin():
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
    """Allows admin to remove a stream out of your local channels list."""
    if not is_admin():
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
    """Allows admin to manually change or correct any user's expiration date."""
    if not is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    data = request.json or {}
    target_user = data.get('username', '').strip()
    new_date_str = data.get('expiry_date', '').strip()  # Expects Format: YYYY-MM-DD

    if not target_user or not new_date_str:
        return jsonify({'success': False, 'message': 'Missing user or date fields'}), 400

    try:
        dt_obj = datetime.strptime(new_date_str, '%Y-%m-%d')
        new_ts = int(time.mktime(dt_obj.timetuple()))
        readable_date = dt_obj.strftime('%B %d, %Y')

        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT username FROM portal_users WHERE LOWER(username) = LOWER(?)", (target_user.lower(),))
            user_exists = cursor.fetchone()

            if user_exists:
                cursor.execute("UPDATE portal_users SET expiry_date=?, expiry_timestamp=? WHERE LOWER(username)=LOWER(?)", (readable_date, new_ts, target_user.lower()))

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
    """Allows standard clients to securely submit channel fault tickets."""
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
            cursor.execute('''
                INSERT INTO channel_reports (username, channel_name, channel_id, issue_type)
                VALUES (?, ?, ?, ?)
            ''', (username, ch_name, ch_id, issue))
            conn.commit()

        print(f"FAULT TICKET LOGGED: Channel '{ch_name}' reported by user: {username}")

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
        send_telegram_alert_direct(alert_msg)

        return jsonify({'success': True, 'message': 'Stream report fault ticket successfully logged with admin!'})
    except Exception as e:
        print(f"CHANNEL REPORT DATA SUBMISSION FAULT: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/force_db_patch_override')
def admin_force_db_patch_override():
    """Forces an immediate structural column rewrite onto your persistent storage disk."""
    secure_admin_username = (os.environ.get('PORTAL_ADMIN_USER') or "djstevieg09").lower()

    if not session.get('logged_in') or str(session.get('username', '')).lower() != secure_admin_username:
        return "Unauthorized Access Gate", 403

    log_messages = []
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()

            cursor.execute("PRAGMA table_info(vod_reports)")
            columns = [row[1] for row in cursor.fetchall()]
            log_messages.append(f"Current columns found on disk: {columns}")

            if 'issue_notes' not in columns:
                cursor.execute("ALTER TABLE vod_reports ADD COLUMN issue_notes TEXT DEFAULT ''")
                conn.commit()
                log_messages.append("🚀 SUCCESS: Forced 'issue_notes' column into your persistent database!")
            else:
                log_messages.append("✅ Column already present inside disk registry array layout.")

        return f"<h3>Database Migration Diagnostic Output:</h3><p>{'<br>'.join(log_messages)}</p>"
    except Exception as e:
        return f"<h3>❌ Extraction Error Triggered:</h3><p>{str(e)}</p>", 500


@app.route('/delete_vod_report_by_admin/<int:report_id>', methods=['POST'])
def admin_clear_vod_report(report_id):
    """Allows the master admin to remove resolved VOD fault tickets."""
    if not is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM vod_reports WHERE id = ?", (report_id,))
            conn.commit()
        print(f"ADMIN ACTION: Manually cleared resolved VOD ticket ID: {report_id}")
        return jsonify({'success': True, 'message': 'Ticket resolved and dropped successfully!'})
    except Exception as e:
        print(f"ADMIN VOD REMOVAL FAULT: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, port=5000)
