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

        # NEW: pending_users table for registration approvals
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
            print(f"AUTOMATION ERROR: Panel API code: {response.status_code}")
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

            # Store hashed password also in pending for safety
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
        return render_template('login.html', error="Invalid username or password profile details, or your account is not yet approved.")


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
                # Remove from pending, but don't overwrite existing
                cursor.execute("DELETE FROM pending_users WHERE id = ?", (pending_id,))
                conn.commit()
                return jsonify({'success': False, 'message': 'User already exists in portal_users. Pending entry removed.'}), 400

            # Insert into portal_users
            cursor.execute('''
                INSERT INTO portal_users (username, password, expiry_date, expiry_timestamp)
                VALUES (?, ?, ?, ?)
            ''', (uname, hashed_pword, readable_expiry, one_year_ts))

            # Insert into user_metadata
            cursor.execute('''
                INSERT INTO user_metadata (username, expiry_date, expiry_timestamp, alert_sent)
                VALUES (?, ?, ?, 0)
                ON CONFLICT(username) DO UPDATE SET
                    expiry_date = excluded.expiry_date,
                    expiry_timestamp = excluded.expiry_timestamp
            ''', (uname, readable_expiry, one_year_ts))

            # Delete from pending_users
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


# --- The rest of your routes: dashboard, media search, referrals, payments, spotify, reports, admin panel, etc. ---
# (All unchanged from the previous full appy.py I gave you,
# except for minor log_activity calls we already integrated.)

# ... [KEEP all the previous routes from the last appy.py here unchanged] ...

if __name__ == '__main__':
    app.run(debug=True, port=5000)
