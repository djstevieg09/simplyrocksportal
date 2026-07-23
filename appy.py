import os
import re
import time
import random
import string
import sqlite3
from datetime import datetime
from queue import Queue
from threading import Thread

import requests
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash

# --- 1. INITIALISE MAIN FLASK APP INSTANCE ---
app = Flask(__name__)
app.secret_key = "simplyrocks_secure_master_portal_key_string_09"

# --- 2. GLOBAL SYSTEM CONFIGURATION & PATHS ---
DEFAULT_DNS = "http://simplyrocks.org:80"
TMDB_API_KEY = os.environ.get('TMDB_API_KEY')

DB_FILE = "/data/database.db"

# --- 3. QUEUE STORAGE CONFIGURATIONS ---
NOTIFICATION_QUEUE = Queue()

# --- MASTER RESELLER CONFIG ---
RESELLER_PANEL_URL = "https://theservice.rocks:80"
RESELLER_USERNAME = os.environ.get('RESELLER_USER')
RESELLER_PASSWORD = os.environ.get('RESELLER_PASS')

# --- TELEGRAM BOT CONFIG ---
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# Xtream default password for sync
XTREAM_DEFAULT_PASSWORD = os.environ.get('XTREAM_DEFAULT_PASSWORD', '')

# Fixed pricing
SPOTIFY_PRICE = 45.00  # GBP
FRIEND_RENEWAL_BONUS = 10.00  # GBP for referrer on renewal
NEW_FRIEND_BONUS = 25.00  # GBP for new referral line


def init_db():
    """Initialise database structures and ensure schema is up to date."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()

        # requests table
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

        # payments table
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

        # referral_wallets table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS referral_wallets (
                username TEXT PRIMARY KEY,
                earned_balance REAL DEFAULT 0.0,
                spent_balance REAL DEFAULT 0.0,
                last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # channel_reports table
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

        # user_metadata table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_metadata (
                username TEXT PRIMARY KEY,
                expiry_date TEXT NOT NULL,
                expiry_timestamp INTEGER NOT NULL,
                alert_sent INTEGER DEFAULT 0,
                last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # vod_reports table
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

        # portal_users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS portal_users (
                username TEXT PRIMARY KEY,
                password TEXT NOT NULL,
                expiry_date TEXT NOT NULL,
                expiry_timestamp INTEGER NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # live_channels table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS live_channels (
                stream_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # announcements table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS announcements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message TEXT NOT NULL,
                active INTEGER DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # spotify_orders table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS spotify_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                portal_username TEXT NOT NULL,
                spotify_username TEXT NOT NULL,
                spotify_password TEXT NOT NULL,
                amount REAL NOT NULL,
                discount_used REAL NOT NULL DEFAULT 0.0,
                status TEXT NOT NULL DEFAULT 'Pending',
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # referral_friends table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS referral_friends (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_username TEXT NOT NULL,
                friend_username TEXT NOT NULL,
                friend_password TEXT NOT NULL,
                expiry_timestamp INTEGER NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # activity_log table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                action TEXT,
                ip_address TEXT,
                user_agent TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # pending_users table for registration approvals
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pending_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                email TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Migration for vod_reports.issue_notes
        try:
            cursor.execute("ALTER TABLE vod_reports ADD COLUMN issue_notes TEXT DEFAULT ''")
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                print(f"DATABASE UPDATE NOTICE: {e}")

        conn.commit()


def seed_uk_channels():
    """Populate live_channels table with a broad set of popular UK channels in FHD/HD/SD variants."""
    base_channels = [
        # BBC family
        "BBC One",
        "BBC Two",
        "BBC Three",
        "BBC Four",
        "CBBC",
        "CBeebies",
        "BBC News",
        "BBC Parliament",

        # ITV family
        "ITV1",
        "ITV2",
        "ITV3",
        "ITV4",
        "ITVBe",

        # Channel 4 family
        "Channel 4",
        "E4",
        "More4",
        "Film4",
        "4seven",

        # Channel 5 family
        "Channel 5",
        "5STAR",
        "5USA",
        "5Action",
        "Paramount Network",

        # Sky Entertainment / Lifestyle
        "Sky One",
        "Sky Atlantic",
        "Sky Witness",
        "Sky Max",
        "Sky Comedy",
        "Sky Crime",
        "Sky Documentaries",
        "Sky Nature",
        "Sky Arts",

        # Sky Cinema (Movies)
        "Sky Cinema Premiere",
        "Sky Cinema Action",
        "Sky Cinema Comedy",
        "Sky Cinema Drama",
        "Sky Cinema Thriller",
        "Sky Cinema Family",
        "Sky Cinema Greats",
        "Sky Cinema Scifi & Horror",

        # Sky Sports
        "Sky Sports Main Event",
        "Sky Sports Premier League",
        "Sky Sports Football",
        "Sky Sports Cricket",
        "Sky Sports Golf",
        "Sky Sports F1",
        "Sky Sports Arena",
        "Sky Sports News",

        # TNT Sports
        "TNT Sports 1",
        "TNT Sports 2",
        "TNT Sports 3",
        "TNT Sports 4",

        # UKTV / Freeview entertainment
        "Dave",
        "Drama",
        "Yesterday",
        "GOLD",
        "W",
        "Alibi",

        # News
        "Sky News",
        "GB News",
        "TalkTV",
        "CNN International",

        # Kids
        "Cartoon Network",
        "Boomerang",
        "Cartoonito",
        "Nickelodeon",
        "Nick Jr.",
        "Nicktoons",
        "POP",
        "Tiny Pop",
        "CITV",

        # Music
        "4Music",
        "MTV",
        "MTV Music",
        "Kerrang!",
        "Box Hits",
    ]

    variants = ["FHD", "HD", "SD"]

    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            count = 0
            for base_name in base_channels:
                safe_base = (
                    base_name.upper()
                    .replace(" ", "-")
                    .replace("&", "AND")
                    .replace(".", "")
                )
                for v in variants:
                    name = f"{base_name} {v}"
                    stream_id = f"UK-{safe_base}-{v}"
                    cursor.execute('''
                        INSERT INTO live_channels (stream_id, name)
                        VALUES (?, ?)
                        ON CONFLICT(stream_id) DO UPDATE SET name = excluded.name
                    ''', (stream_id, name))
                    count += 1
            conn.commit()
        print(f"UK CHANNEL SEED: Loaded/updated {count} channel variants into live_channels.")
    except Exception as e:
        print(f"UK CHANNEL SEED ERROR: {e}")


# Trigger DB init and channel seed
init_db()
seed_uk_channels()
NOTIFICATION_QUEUE = Queue()
CACHED_CHANNELS = []


def is_admin():
    """Central admin check, using session and environment-based master username."""
    secure_admin_username = (os.environ.get('PORTAL_ADMIN_USER') or "djstevieg09").lower()
    current_user = str(session.get('username', '')).lower()
    return session.get('logged_in') and (session.get('is_admin') or current_user == secure_admin_username)


def log_activity(username, action):
    """Record a simple audit log entry."""
    try:
        ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        ua = request.headers.get('User-Agent', '')
    except RuntimeError:
        ip = ''
        ua = ''
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO activity_log (username, action, ip_address, user_agent)
                VALUES (?, ?, ?, ?)
            ''', (username, action, ip, ua))
            conn.commit()
    except Exception as e:
        print(f"ACTIVITY LOG ERROR: {e}")


def send_telegram_alert_direct(message_text):
    """Send a formatted text message to Telegram using environment tokens."""
    try:
        bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
        chat_id = os.environ.get('TELEGRAM_CHAT_ID')

        if not bot_token or not chat_id:
            print("TELEGRAM NOTICE: Missing secure environment keys.", flush=True)
            return False

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
    """Dummy panel extension; preserved from previous version (not used by portal users)."""
    try:
        api_endpoint = f"{DEFAULT_DNS.rstrip('/')}/api.php"
        package_id_map = {
            '1': '66',
            '2': '70',
            '3': '74',
            '4': '78'
        }
        target_package = package_id_map.get(str(connections_count), '66')
        print(f"AUTOMATION: Sending API payload to extend line {client_username} with Package {target_package}...")

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
                print(f"AUTOMATION WARNING: Panel rejected parameters: {response.text}")
                return False, f"Panel rejection: {response.text}"
            print(f"AUTOMATION SUCCESS: {client_username} extended.")
            return True, "Line extended automatically."
        else:
            print(f"AUTOMATION ERROR: {response.status_code}")
            return False, f"Panel API error code: {response.status_code}"

    except Exception as e:
        print(f"AUTOMATION EXCEPTION: {e}")
        return False, f"Panel connection timeout exception: {e}"


def verify_xtream_credentials(dns, username, password):
    """
    Authenticates clients securely against local portal_users database.
    """
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM portal_users WHERE LOWER(username) = LOWER(?)",
                (username.strip().lower(),)
            )
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


# --- NEW: USER REGISTRATION ENDPOINT ---

@app.route('/register', methods=['POST'])
def register():
    """
    Public registration endpoint.
    Accepts username, password, optional email and puts them into pending_users for admin approval.
    """
    data = request.json or {}
    uname = data.get('username', '').strip()
    pword = data.get('password', '').strip()
    email = data.get('email', '').strip()

    if not uname or not pword:
        return jsonify({'success': False, 'message': 'Username and password are required.'}), 400

    # Basic validation
    if len(uname) < 3:
        return jsonify({'success': False, 'message': 'Username must be at least 3 characters.'}), 400
    if len(pword) < 4:
        return jsonify({'success': False, 'message': 'Password must be at least 4 characters.'}), 400

    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()

            # Check if username already exists in portal_users
            cursor.execute("SELECT username FROM portal_users WHERE LOWER(username) = LOWER(?)", (uname.lower(),))
            if cursor.fetchone():
                return jsonify({'success': False, 'message': 'This username is already approved and in use.'}), 400

            # Check if already pending
            cursor.execute("SELECT username FROM pending_users WHERE LOWER(username) = LOWER(?)", (uname.lower(),))
            if cursor.fetchone():
                return jsonify({'success': False, 'message': 'This username is already awaiting approval.'}), 400

            # Store hashed password in pending for safety
            hashed_pword = generate_password_hash(pword)

            cursor.execute('''
                INSERT INTO pending_users (username, password, email)
                VALUES (?, ?, ?)
            ''', (uname, hashed_pword, email or None))
            conn.commit()

        log_activity(uname, "Registration submitted (pending approval)")

        send_telegram_alert_direct(
            f"<b>📝 NEW REGISTRATION PENDING APPROVAL</b>\n"
            f"<b>Username:</b> <code>{uname}</code>\n"
            f"<b>Email:</b> <code>{email or 'N/A'}</code>"
        )

        return jsonify({'success': True, 'message': 'Registration submitted. Admin must approve your account before you can log in.'})
    except Exception as e:
        print(f"REGISTRATION ERROR: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/', endpoint='login', methods=['GET', 'POST'])
def login():
    """Handles admin + portal user login."""
    if request.method == 'GET':
        return render_template('login.html', default_dns=DEFAULT_DNS)

    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()

    if not username or not password:
        return render_template('login.html', error="Please supply both username and password configurations.")

    # Admin login via env vars
    secure_admin_username = os.environ.get('PORTAL_ADMIN_USER')
    secure_admin_password = os.environ.get('PORTAL_ADMIN_PASS')

    if secure_admin_username and secure_admin_password:
        if username.lower() == secure_admin_username.lower() and password == secure_admin_password:
            session['logged_in'] = True
            session['username'] = username
            session['password'] = password
            session['is_admin'] = True
            session['expiry_date'] = "Reseller Control"
            print("ADMIN LOGIN DETECTED.")
            log_activity(username, "Admin login")
            return redirect('/admin')

    # Client login
    success, user_info = verify_xtream_credentials(DEFAULT_DNS, username, password)

    if success and user_info:
        session['logged_in'] = True
        session['username'] = username
        session['password'] = password
        session['is_admin'] = False

        log_activity(username, "User login")

        raw_exp = user_info.get('exp_date')
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

        # cache metadata
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
                        f"<b>⏳ APPROACHING EXPIRATION</b>\n"
                        f"<b>User:</b> <code>{username}</code>\n"
                        f"<b>Expiry:</b> {readable_date}\n"
                        f"<b>Days Left:</b> {days_left_gate}"
                    )
                    send_telegram_alert_direct(countdown_warning_text)
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
        except Exception as db_err:
            print(f"LOCAL CACHE ERROR: {db_err}")

        return redirect(url_for('dashboard'))
    else:
        return render_template('login.html', error="Invalid username/password, or your account is not yet approved.")


@app.route('/admin/get_pending_users')
def admin_get_pending_users():
    """Admin: retrieve list of registration requests awaiting approval."""
    if not is_admin():
        return jsonify([]), 403

    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT id, username, email, created_at FROM pending_users ORDER BY created_at DESC")
            rows = cursor.fetchall()
        pending_list = []
        for r in rows:
            pending_list.append({
                'id': r['id'],
                'username': r['username'],
                'email': r['email'] or '',
                'created_at': r['created_at']
            })
        return jsonify(pending_list)
    except Exception as e:
        print(f"ADMIN GET_PENDING_USERS ERROR: {e}")
        return jsonify([]), 500


@app.route('/admin/approve_user', methods=['POST'])
def admin_approve_user():
    """Admin: approve a pending registration and create a portal account with default 1-year expiry."""
    if not is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    data = request.json or {}
    pending_id = data.get('id')
    if not pending_id:
        return jsonify({'success': False, 'message': 'Missing pending user id.'}), 400

    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("SELECT * FROM pending_users WHERE id = ?", (pending_id,))
            p = cursor.fetchone()
            if not p:
                return jsonify({'success': False, 'message': 'Pending registration not found.'}), 404

            uname = p['username']
            hashed_pword = p['password']

            # Default 1-year expiry from today
            one_year_ts = int(time.time()) + (365 * 86400)
            readable_expiry = datetime.fromtimestamp(one_year_ts).strftime('%B %d, %Y')

            # Ensure username not already in portal_users
            cursor.execute("SELECT username FROM portal_users WHERE LOWER(username) = LOWER(?)", (uname.lower(),))
            if cursor.fetchone():
                cursor.execute("DELETE FROM pending_users WHERE id = ?", (pending_id,))
                conn.commit()
                return jsonify({'success': False, 'message': 'User already exists in portal_users. Pending entry removed.'}), 400

            cursor.execute('''
                INSERT INTO portal_users (username, password, expiry_date, expiry_timestamp)
                VALUES (?, ?, ?, ?)
            ''', (uname, hashed_pword, readable_expiry, one_year_ts))

            cursor.execute('''
                INSERT INTO user_metadata (username, expiry_date, expiry_timestamp, alert_sent)
                VALUES (?, ?, ?, 0)
                ON CONFLICT(username) DO UPDATE SET
                    expiry_date = excluded.expiry_date,
                    expiry_timestamp = excluded.expiry_timestamp
            ''', (uname, readable_expiry, one_year_ts))

            cursor.execute("DELETE FROM pending_users WHERE id = ?", (pending_id,))

            conn.commit()

        log_activity(session.get('username', 'admin'), f"Approved registration for {uname}")

        send_telegram_alert_direct(
            f"<b>✅ REGISTRATION APPROVED</b>\n"
            f"<b>Username:</b> <code>{uname}</code>\n"
            f"<b>Default Expiry:</b> {readable_expiry}"
        )

        return jsonify({'success': True, 'message': f"User '{uname}' approved and added to portal users."})
    except Exception as e:
        print(f"ADMIN APPROVE_USER ERROR: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/reject_user', methods=['POST'])
def admin_reject_user():
    """Admin: reject a pending registration (delete from pending_users)."""
    if not is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    data = request.json or {}
    pending_id = data.get('id')
    if not pending_id:
        return jsonify({'success': False, 'message': 'Missing pending user id.'}), 400
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT username FROM pending_users WHERE id = ?", (pending_id,))
            row = cursor.fetchone()
            if not row:
                return jsonify({'success': False, 'message': 'Pending registration not found.'}), 404
            uname = row[0]
            cursor.execute("DELETE FROM pending_users WHERE id = ?", (pending_id,))
            conn.commit()
        log_activity(session.get('username', 'admin'), f"Rejected registration for {uname}")
        return jsonify({'success': True, 'message': f"Registration for '{uname}' rejected and removed."})
    except Exception as e:
        print(f"ADMIN REJECT_USER ERROR: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/create_portal_user', methods=['POST'])
def admin_create_portal_user():
    """Admin: create or update a portal user with custom expiry date."""
    if not is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    data = request.json or {}
    uname = data.get('username', '').strip()
    pword = data.get('password', '').strip()
    exp_str = data.get('expiry_date', '').strip()

    if not uname or not pword or not exp_str:
        return jsonify({'success': False, 'message': 'All fields are mandatory'}), 400

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

        send_telegram_alert_direct(
            f"<b>👤 NEW/UPDATED PORTAL USER</b>\n"
            f"<b>Username:</b> <code>{uname}</code>\n"
            f"<b>Password:</b> <code>{pword}</code>\n"
            f"<b>Expiry:</b> {readable_date}"
        )

        return jsonify({'success': True, 'message': f"Account '{uname}' saved."})
    except Exception as e:
        print(f"ADMIN CREATE USER ERROR: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/create_new_user_one_year', methods=['POST'])
def admin_create_new_user_one_year():
    """
    Admin: create a new portal user with a 1-year expiry from today.
    Expects JSON: {username, password}
    """
    if not is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    data = request.json or {}
    uname = data.get('username', '').strip()
    pword = data.get('password', '').strip()

    if not uname or not pword:
        return jsonify({'success': False, 'message': 'Username and password are mandatory'}), 400

    try:
        one_year_ts = int(time.time()) + (365 * 86400)
        readable_expiry = datetime.fromtimestamp(one_year_ts).strftime('%B %d, %Y')
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
            ''', (uname, hashed_pword, readable_expiry, one_year_ts))

            cursor.execute('''
                INSERT INTO user_metadata (username, expiry_date, expiry_timestamp, alert_sent)
                VALUES (?, ?, ?, 0)
                ON CONFLICT(username) DO UPDATE SET
                    expiry_date = excluded.expiry_date,
                    expiry_timestamp = excluded.expiry_timestamp
            ''', (uname, readable_expiry, one_year_ts))

            conn.commit()

        send_telegram_alert_direct(
            f"<b>👤 NEW PORTAL USER (AUTO-1YR)</b>\n"
            f"<b>Username:</b> <code>{uname}</code>\n"
            f"<b>Password:</b> <code>{pword}</code>\n"
            f"<b>Expiry:</b> {readable_expiry}"
        )

        log_activity(session.get('username', 'admin'), f"Created new user {uname} with 1-year expiry")

        return jsonify({'success': True, 'message': f"User '{uname}' created/updated with 1-year expiry ({readable_expiry})."})
    except Exception as e:
        print(f"ADMIN CREATE_NEW_USER_ONE_YEAR ERROR: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/reset_portal_user_password', methods=['POST'])
def admin_reset_portal_user_password():
    """Admin: reset a portal user's password to a new random value."""
    if not is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    data = request.json or {}
    target_user = str(data.get('username', '')).strip()
    if not target_user:
        return jsonify({'success': False, 'message': 'Missing target username.'}), 400

    try:
        chars = string.ascii_letters + string.digits
        new_plain = ''.join(random.choice(chars) for _ in range(10))
        new_hashed = generate_password_hash(new_plain)

        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE portal_users SET password = ? WHERE LOWER(username) = LOWER(?)",
                (new_hashed, target_user.lower())
            )
            if cursor.rowcount == 0:
                return jsonify({'success': False, 'message': 'User not found.'}), 404
            conn.commit()

        send_telegram_alert_direct(
            f"<b>🔑 PORTAL PASSWORD RESET</b>\n"
            f"<b>User:</b> <code>{target_user}</code>\n"
            f"<b>New Password:</b> <code>{new_plain}</code>"
        )

        log_activity(session.get('username', 'admin'), f"Reset password for {target_user}")

        return jsonify({
            'success': True,
            'message': f"Password reset for '{target_user}'.",
            'new_password': new_plain
        })
    except Exception as e:
        print(f"ADMIN RESET PASSWORD ERROR: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/delete_portal_user/<string:username>', methods=['POST'])
def admin_delete_portal_user(username):
    """Admin: delete a portal user."""
    if not is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM portal_users WHERE LOWER(username) = LOWER(?)", (username.lower(),))
            cursor.execute("DELETE FROM user_metadata WHERE LOWER(username) = LOWER(?)", (username.lower(),))
            conn.commit()
        log_activity(session.get('username', 'admin'), f"Deleted portal user {username}")
        return jsonify({'success': True, 'message': f"Account '{username}' deleted."})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/sync_live_panel_expirations', methods=['POST'])
def sync_live_panel_expirations():
    """Admin: refresh expirations by querying IPTV panel without wiping user_metadata."""
    if not is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    sync_count = 0
    captured_count = 0
    current_timestamp = int(time.time())

    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT username FROM portal_users")
            tracked_users = [row['username'].strip() for row in cursor.fetchall()]

        if not tracked_users:
            tracked_users = ["DC-Firestick"]

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
                                ON CONFLICT(username) DO UPDATE SET
                                    expiry_date = excluded.expiry_date,
                                    expiry_timestamp = excluded.expiry_timestamp
                            ''', (uname, readable_date, exp_ts))
                            conn2.commit()

                        if days_left <= 31:
                            captured_count += 1

                        sync_count += 1
            except Exception as loop_err:
                print(f"SYNC LOOP FAULT for {uname}: {loop_err}")
                continue

        log_activity(session.get('username', 'admin'), f"Synced expirations: {sync_count} users, {captured_count} expiring <=31d")

        return jsonify({
            'success': True,
            'message': f'Sync complete. Checked {sync_count} users; {captured_count} currently expire in 31 days or less.'
        })

    except Exception as e:
        print(f"SYNC ERROR: {e}")
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
                    if days_remaining <= 7:
                        show_expiry_warning = True
                except Exception:
                    pass

    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM requests WHERE username = ? ORDER BY timestamp DESC", (session['username'],))
        user_requests = cursor.fetchall()

        cursor.execute("SELECT message FROM announcements WHERE active = 1 ORDER BY created_at DESC LIMIT 1")
        row = cursor.fetchone()
        active_announcement = row['message'] if row else None

        cursor.execute("""
            SELECT order_id, amount, status, timestamp
            FROM payments
            WHERE username = ?
            ORDER BY timestamp DESC
            LIMIT 10
        """, (session['username'],))
        user_payments = cursor.fetchall()

        cursor.execute("""
            SELECT earned_balance, spent_balance 
            FROM referral_wallets 
            WHERE LOWER(username) = LOWER(?)
        """, (session['username'].lower(),))
        row_wallet = cursor.fetchone()
        if row_wallet:
            total_earned = row_wallet['earned_balance'] or 0.0
            total_spent = row_wallet['spent_balance'] or 0.0
        else:
            total_earned = 0.0
            total_spent = 0.0

    return render_template(
        'dashboard.html',
        username=session['username'],
        requests=user_requests,
        expiry_date=session.get('expiry_date', 'Active Line'),
        show_warning=show_expiry_warning,
        days_left=days_remaining,
        announcement=active_announcement,
        payments=user_payments,
        total_earned=total_earned,
        total_spent=total_spent
    )


@app.route('/search_media')
def search_media():
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

        print(f"TMDB ERROR code {response.status_code}")
        return jsonify({"results": []})
    except Exception as e:
        print(f"TMDB EXCEPTION: {e}")
        return jsonify({"results": []})


@app.route('/get_referral_friends')
def get_referral_friends():
    """Return a list of referred friends for the logged-in user, expiry from main portal data."""
    if not session.get('logged_in'):
        return jsonify([]), 401

    referrer = session.get('username')
    results = []
    now_ts = int(time.time())

    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute('''
                SELECT friend_username
                FROM referral_friends
                WHERE LOWER(referrer_username) = LOWER(?)
                ORDER BY created_at DESC
            ''', (referrer.lower(),))
            friends = cursor.fetchall()

            for row in friends:
                friend_user = row['friend_username']

                exp_ts = 0

                # Try portal_users
                cursor.execute("""
                    SELECT expiry_timestamp
                    FROM portal_users
                    WHERE LOWER(username)=LOWER(?)
                """, (friend_user.lower(),))
                row_portal = cursor.fetchone()
                if row_portal and row_portal['expiry_timestamp']:
                    exp_ts = int(row_portal['expiry_timestamp'])

                # Fallback to user_metadata
                if exp_ts <= 0:
                    cursor.execute("""
                        SELECT expiry_timestamp
                        FROM user_metadata
                        WHERE LOWER(username)=LOWER(?)
                    """, (friend_user.lower(),))
                    row_meta = cursor.fetchone()
                    if row_meta and row_meta['expiry_timestamp']:
                        exp_ts = int(row_meta['expiry_timestamp'])

                if exp_ts > 0:
                    readable = datetime.fromtimestamp(exp_ts).strftime('%B %d, %Y')
                    days_left = int((exp_ts - now_ts) / 86400)
                else:
                    readable = "Unknown"
                    days_left = None

                results.append({
                    'friend_username': friend_user,
                    'expiry_date': readable,
                    'days_left': days_left
                })
    except Exception as e:
        print("GET_REFERRAL_FRIENDS ERROR:", e)

    return jsonify(results)


@app.route('/renew_friend_line', methods=['POST'])
def renew_friend_line():
    """
    User-initiated: renew a referred friend's IPTV line.
    Called after successful PayPal payment from the dashboard.
    """
    if not session.get('logged_in'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    data = request.json or {}
    referrer = session.get('username')
    friend_username = (data.get('friend_username') or '').strip()
    order_id = (data.get('orderID') or '').strip()
    amount_str = (data.get('amount') or '0').strip()
    discount_str = (data.get('discount_redeemed') or '0').strip()
    connections = (data.get('connections') or '1').strip()

    if not friend_username or not order_id:
        return jsonify({'success': False, 'message': 'Missing friend_username or orderID'}), 400

    try:
        amount_val = float(amount_str)
    except ValueError:
        amount_val = 0.0
    try:
        discount_val = float(discount_str)
    except ValueError:
        discount_val = 0.0

    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO payments (username, order_id, amount, status)
                VALUES (?, ?, ?, 'Completed')
            ''', (referrer, order_id, f"{amount_val:.2f}"))

            one_year_ts = int(time.time()) + (365 * 86400)
            cursor.execute("""
                UPDATE referral_friends
                SET expiry_timestamp = ?
                WHERE LOWER(friend_username) = LOWER(?)
            """, (one_year_ts, friend_username.lower()))

            cursor.execute("""
                INSERT INTO referral_wallets (username, earned_balance, spent_balance)
                VALUES (?, ?, 0.0)
                ON CONFLICT(username) DO UPDATE SET
                    earned_balance = earned_balance + ?
            """, (referrer, FRIEND_RENEWAL_BONUS, FRIEND_RENEWAL_BONUS))

            conn.commit()

        readable = datetime.fromtimestamp(one_year_ts).strftime('%B %d, %Y')
        send_telegram_alert_direct(
            f"<b>🔁 FRIEND LINE RENEWAL</b>\n"
            f"<b>Referrer:</b> <code>{referrer}</code>\n"
            f"<b>Friend Line:</b> <code>{friend_username}</code>\n"
            f"<b>Order ID:</b> <code>{order_id}</code>\n"
            f"<b>Paid:</b> £{amount_val:.2f}\n"
            f"<b>Wallet Used:</b> £{discount_val:.2f}\n"
            f"<b>Connections:</b> {connections}\n"
            f"<b>New Local Expiry (Portal):</b> {readable}"
        )

        log_activity(referrer, f"Renewed friend line {friend_username} ({connections} conn, order {order_id})")

        return jsonify({'success': True, 'message': f"Friend line '{friend_username}' renewed. Admin will extend it on the IPTV panel."})
    except Exception as e:
        print("RENEW_FRIEND_LINE ERROR:", e)
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/reassign_referral_friend', methods=['POST'])
def admin_reassign_referral_friend():
    """
    Admin: move ANY portal user under ANY referrer so they appear as a managed friend.
    """
    if not is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    data = request.json or {}
    friend_username = (data.get('friend_username') or '').strip()
    new_referrer = (data.get('new_referrer') or '').strip()
    old_referrer = (data.get('old_referrer') or '').strip()

    if not friend_username or not new_referrer:
        return jsonify({
            'success': False,
            'message': 'friend_username and new_referrer are required.'
        }), 400

    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()

            cursor.execute(
                "SELECT username FROM portal_users WHERE LOWER(username) = LOWER(?)",
                (new_referrer.lower(),)
            )
            if not cursor.fetchone():
                return jsonify({
                    'success': False,
                    'message': f"New referrer '{new_referrer}' does not exist as a portal user."
                }), 400

            cursor.execute(
                "SELECT username FROM portal_users WHERE LOWER(username) = LOWER(?)",
                (friend_username.lower(),)
            )
            if not cursor.fetchone():
                return jsonify({
                    'success': False,
                    'message': f"Friend user '{friend_username}' does not exist in portal_users."
                }), 400

            cursor.execute("""
                SELECT id FROM referral_friends
                WHERE LOWER(friend_username) = LOWER(?)
            """, (friend_username.lower(),))
            rows = cursor.fetchall()

            if not rows:
                cursor.execute("""
                    INSERT INTO referral_friends
                        (referrer_username, friend_username, friend_password, expiry_timestamp)
                    VALUES (?, ?, ?, 0)
                """, (new_referrer, friend_username, 'N/A'))
                conn.commit()

                log_activity(
                    session.get('username', 'admin'),
                    f"Created new referral_friends row: friend '{friend_username}' now managed by '{new_referrer}'"
                )

                return jsonify({
                    'success': True,
                    'message': (
                        f"No existing referral record; created new link: "
                        f"friend '{friend_username}' is now managed by '{new_referrer}'."
                    )
                })

            if old_referrer:
                cursor.execute("""
                    UPDATE referral_friends
                    SET referrer_username = ?
                    WHERE LOWER(friend_username) = LOWER(?)
                      AND LOWER(referrer_username) = LOWER(?)
                """, (new_referrer, friend_username.lower(), old_referrer.lower()))
            else:
                cursor.execute("""
                    UPDATE referral_friends
                    SET referrer_username = ?
                    WHERE LOWER(friend_username) = LOWER(?)
                """, (new_referrer, friend_username.lower()))

            if cursor.rowcount == 0:
                msg = (
                    f"Friend '{friend_username}' has referral records, but none under "
                    f"current referrer '{old_referrer}'."
                    if old_referrer else
                    "No matching friend record found to reassign."
                )
                return jsonify({'success': False, 'message': msg}), 404

            conn.commit()

        log_activity(
            session.get('username', 'admin'),
            f"Reassigned referral friend '{friend_username}' to referrer '{new_referrer}'"
            + (f" (from '{old_referrer}')" if old_referrer else "")
        )

        return jsonify({
            'success': True,
            'message': f"Friend '{friend_username}' is now managed by '{new_referrer}'."
        })
    except Exception as e:
        print("ADMIN REASSIGN REFERRAL ERROR:", e)
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/remove_managed_friend', methods=['POST'])
def remove_managed_friend():
    """
    Referrer: remove a managed friend from their referral_friends list.
    Does NOT delete the friend from portal_users or anywhere else.
    """
    if not session.get('logged_in'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    data = request.json or {}
    friend_username = (data.get('friend_username') or '').strip()
    if not friend_username:
        return jsonify({'success': False, 'message': 'Missing friend_username'}), 400

    referrer = session.get('username')
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM referral_friends
                WHERE LOWER(referrer_username)=LOWER(?)
                  AND LOWER(friend_username)=LOWER(?)
            """, (referrer.lower(), friend_username.lower()))
            deleted = cursor.rowcount
            conn.commit()

        if deleted == 0:
            return jsonify({'success': False, 'message': 'No matching managed friend found.'}), 404

        log_activity(referrer, f"Removed managed friend '{friend_username}'")
        return jsonify({'success': True, 'message': f"'{friend_username}' removed from your managed list."})
    except Exception as e:
        print("REMOVE_MANAGED_FRIEND ERROR:", e)
        return jsonify({'success': False, 'message': str(e)}), 500


# --- the rest of your routes remain unchanged: channel reports, VOD reports, admin panel, etc. ---

@app.route('/submit_channel_report', methods=['POST'])
def submit_channel_report():
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

        send_telegram_alert_direct(
            f"<b>📺 LIVE TV STREAM FAULT TICKET</b>\n"
            f"<b>User:</b> <code>{username}</code>\n"
            f"<b>Channel:</b> <b>{ch_name}</b>\n"
            f"<b>Stream ID:</b> <code>{ch_id}</code>\n"
            f"<b>Issue:</b> {issue}"
        )

        log_activity(username, f"Channel fault report: {ch_name} (ID {ch_id}) - {issue}")

        return jsonify({'success': True, 'message': 'Stream fault ticket logged.'})
    except Exception as e:
        print(f"CHANNEL REPORT ERROR: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin')
def admin_panel():
    if not is_admin():
        return "<h3>Access Denied</h3>", 403

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

        cursor.execute("SELECT * FROM spotify_orders ORDER BY timestamp DESC")
        spotify_orders = cursor.fetchall()

        cursor.execute("SELECT message FROM announcements WHERE active = 1 ORDER BY created_at DESC LIMIT 1")
        row = cursor.fetchone()
        latest_announcement = row['message'] if row else ''

        cursor.execute("SELECT * FROM activity_log ORDER BY timestamp DESC LIMIT 50")
        activity_rows = cursor.fetchall()

    return render_template(
        'admin.html',
        requests=all_requests,
        payment_logs=all_payments,
        channel_reports=all_reports,
        vod_reports=all_vod_reports,
        wallets=all_wallets,
        portal_users=all_portal_users,
        live_channels=all_live_channels,
        client_expiration_list=client_expiration_list,
        spotify_orders=spotify_orders,
        latest_announcement=latest_announcement,
        activity_rows=activity_rows
    )


# (rest of your existing admin helper routes: adjust_user_credit, update_status, delete_request, etc.)
# ... unchanged from your last working script ...


@app.route('/logout')
def logout():
    username = session.get('username')
    session.clear()
    if username:
        log_activity(username, "Logout")
    return redirect('/')


if __name__ == '__main__':
    app.run(debug=True, port=5000)
