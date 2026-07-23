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
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'simplyrocks_secure_master_portal_key_string_09')
if app.secret_key == 'simplyrocks_secure_master_portal_key_string_09':
    print("SECURITY WARNING: FLASK_SECRET_KEY env var is not set. Using the built-in "
          "fallback key is NOT safe for production - anyone who reads this source "
          "code can forge session cookies. Set FLASK_SECRET_KEY to a long random "
          "string in your environment.", flush=True)

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

# --- PAYPAL SERVER-SIDE VERIFICATION CONFIG ---
# These are DIFFERENT from the public JS SDK client-id used in dashboard.html.
# Create a REST app at developer.paypal.com to get a Client ID + Secret, then
# set them as environment variables. The secret must NEVER appear in any HTML
# or JS sent to the browser.
PAYPAL_CLIENT_ID = os.environ.get('PAYPAL_CLIENT_ID')
PAYPAL_CLIENT_SECRET = os.environ.get('PAYPAL_CLIENT_SECRET')
PAYPAL_API_BASE = os.environ.get('PAYPAL_API_BASE', 'https://api-m.paypal.com')

# Simple in-memory token cache so we don't re-authenticate with PayPal on every request.
_paypal_token_cache = {"token": None, "expires_at": 0}

# Fixed pricing
SPOTIFY_PRICE = 45.00  # GBP
FRIEND_RENEWAL_BONUS = 10.00  # GBP for referrer on renewal
NEW_FRIEND_BONUS = 25.00  # GBP for new referral line
REFERRAL_LINE_PRICE = 75.00  # GBP price of a new 1-year friend line
CONNECTION_TIER_PRICES = {"1": 75.00, "2": 100.00, "3": 125.00, "4": 150.00}  # GBP


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

        # referral_transactions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS referral_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,         -- the referrer
                friend_username TEXT,          -- the friend (if applicable)
                type TEXT NOT NULL,            -- 'NEW_FRIEND' or 'FRIEND_RENEWAL'
                amount REAL NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Migration for vod_reports.issue_notes
        try:
            cursor.execute("ALTER TABLE vod_reports ADD COLUMN issue_notes TEXT DEFAULT ''")
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                print(f"DATABASE UPDATE NOTICE: {e}")

        # Unique index on referral_friends to prevent duplicates
        try:
            cursor.execute('''
                CREATE UNIQUE INDEX IF NOT EXISTS idx_referral_unique
                ON referral_friends (LOWER(referrer_username), LOWER(friend_username))
            ''')
        except sqlite3.OperationalError as e:
            print(f"REFERRAL INDEX NOTICE: {e}")

        # NEW: unique index on payments.order_id so a real PayPal order_id
        # can never be logged/credited twice (replay protection).
        try:
            cursor.execute('''
                CREATE UNIQUE INDEX IF NOT EXISTS idx_payments_order_id_unique
                ON payments (order_id)
            ''')
        except sqlite3.OperationalError as e:
            print(f"PAYMENTS ORDER_ID INDEX NOTICE: {e}")

        conn.commit()


def seed_uk_channels():
    """Populate live_channels table with a broad set of popular UK channels in FHD/HD/SD variants."""
    base_channels = [
        # BBC family
        "BBC One", "BBC Two", "BBC Three", "BBC Four",
        "CBBC", "CBeebies", "BBC News", "BBC Parliament",
        # ITV family
        "ITV1", "ITV2", "ITV3", "ITV4", "ITVBe",
        # Channel 4 family
        "Channel 4", "E4", "More4", "Film4", "4seven",
        # Channel 5 family
        "Channel 5", "5STAR", "5USA", "5Action", "Paramount Network",
        # Sky Entertainment / Lifestyle
        "Sky One", "Sky Atlantic", "Sky Witness", "Sky Max", "Sky Comedy",
        "Sky Crime", "Sky Documentaries", "Sky Nature", "Sky Arts",
        # Sky Cinema (Movies)
        "Sky Cinema Premiere", "Sky Cinema Action", "Sky Cinema Comedy",
        "Sky Cinema Drama", "Sky Cinema Thriller", "Sky Cinema Family",
        "Sky Cinema Greats", "Sky Cinema Scifi & Horror",
        # Sky Sports
        "Sky Sports Main Event", "Sky Sports Premier League", "Sky Sports Football",
        "Sky Sports Cricket", "Sky Sports Golf", "Sky Sports F1",
        "Sky Sports Arena", "Sky Sports News",
        # TNT Sports
        "TNT Sports 1", "TNT Sports 2", "TNT Sports 3", "TNT Sports 4",
        # UKTV / Freeview entertainment
        "Dave", "Drama", "Yesterday", "GOLD", "W", "Alibi",
        # News
        "Sky News", "GB News", "TalkTV", "CNN International",
        # Kids
        "Cartoon Network", "Boomerang", "Cartoonito", "Nickelodeon",
        "Nick Jr.", "Nicktoons", "POP", "Tiny Pop", "CITV",
        # Music
        "4Music", "MTV", "MTV Music", "Kerrang!", "Box Hits",
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


# =============================================================================
# PAYPAL SERVER-SIDE VERIFICATION HELPERS
# =============================================================================
# The browser can be edited by anyone using its developer tools, so the price
# and "success" state that the front-end JS sends can never be trusted on
# their own. Before any of the money-related routes below grant a benefit
# (renewal, Spotify order, new referral line), they now ask PayPal directly
# "did this order really happen, and for how much?" using these helpers.

def get_paypal_access_token():
    """
    Fetch (and cache) an OAuth2 access token from PayPal using this app's
    server-side client credentials. This is completely separate from the
    public JS SDK client-id used in dashboard.html.
    """
    now = time.time()
    if _paypal_token_cache["token"] and _paypal_token_cache["expires_at"] > now + 30:
        return _paypal_token_cache["token"]

    if not PAYPAL_CLIENT_ID or not PAYPAL_CLIENT_SECRET:
        raise RuntimeError("PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET not configured.")

    resp = requests.post(
        f"{PAYPAL_API_BASE}/v1/oauth2/token",
        auth=(PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET),
        data={"grant_type": "client_credentials"},
        headers={"Accept": "application/json", "Accept-Language": "en_US"},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()

    _paypal_token_cache["token"] = data["access_token"]
    _paypal_token_cache["expires_at"] = now + data.get("expires_in", 300)
    return _paypal_token_cache["token"]


def verify_paypal_order(order_id, expected_amount, expected_currency="GBP"):
    """
    Fetch an order directly from PayPal and confirm it is real, was captured,
    and matches the amount we expect (within a 1p rounding tolerance).

    Returns (True, order_json) on success, or (False, reason_string) on failure.
    """
    if not order_id:
        return False, "Missing order_id"

    try:
        token = get_paypal_access_token()
    except Exception as e:
        return False, f"PayPal auth error: {e}"

    try:
        resp = requests.get(
            f"{PAYPAL_API_BASE}/v2/checkout/orders/{order_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
    except Exception as e:
        return False, f"PayPal lookup error: {e}"

    if resp.status_code != 200:
        return False, f"PayPal order lookup failed ({resp.status_code})"

    order = resp.json()

    status = order.get("status")
    if status != "COMPLETED":
        return False, f"Order status is '{status}', expected COMPLETED"

    try:
        purchase_unit = order["purchase_units"][0]
        captured_amount = purchase_unit["payments"]["captures"][0]["amount"]
        actual_value = float(captured_amount["value"])
        actual_currency = captured_amount["currency_code"]
    except (KeyError, IndexError, ValueError):
        return False, "Could not read captured amount from PayPal order"

    if actual_currency != expected_currency:
        return False, f"Currency mismatch: got {actual_currency}, expected {expected_currency}"

    if abs(actual_value - float(expected_amount)) > 0.01:
        return False, f"Amount mismatch: PayPal shows {actual_value}, expected {expected_amount}"

    return True, order


def order_id_already_used(order_id):
    """Prevent replay: has this order_id already been logged in payments?"""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM payments WHERE order_id = ?", (order_id,))
        return cursor.fetchone() is not None


def get_wallet_balance(username):
    """Real server-side wallet balance lookup - never trust a client-claimed balance."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT earned_balance, spent_balance
            FROM referral_wallets
            WHERE LOWER(username) = LOWER(?)
        """, (username.lower(),))
        row = cursor.fetchone()
        if not row:
            return 0.0
        return (row['earned_balance'] or 0.0) - (row['spent_balance'] or 0.0)


# --- USER REGISTRATION & LOGIN ---

@app.route('/register', methods=['POST'])
def register():
    """
    Public registration endpoint.
    """
    data = request.json or {}
    uname = data.get('username', '').strip()
    pword = data.get('password', '').strip()
    email = data.get('email', '').strip()

    if not uname or not pword:
        return jsonify({'success': False, 'message': 'Username and password are required.'}), 400
    if len(uname) < 3:
        return jsonify({'success': False, 'message': 'Username must be at least 3 characters.'}), 400
    if len(pword) < 4:
        return jsonify({'success': False, 'message': 'Password must be at least 4 characters.'}), 400

    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT username FROM portal_users WHERE LOWER(username) = LOWER(?)", (uname.lower(),))
            if cursor.fetchone():
                return jsonify({'success': False, 'message': 'This username is already approved and in use.'}), 400

            cursor.execute("SELECT username FROM pending_users WHERE LOWER(username) = LOWER(?)", (uname.lower(),))
            if cursor.fetchone():
                return jsonify({'success': False, 'message': 'This username is already awaiting approval.'}), 400

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

    secure_admin_username = os.environ.get('PORTAL_ADMIN_USER')
    secure_admin_password = os.environ.get('PORTAL_ADMIN_PASS')

    if secure_admin_username and secure_admin_password:
        if username.lower() == secure_admin_username.lower() and password == secure_admin_password:
            session['logged_in'] = True
            session['username'] = username
            session['is_admin'] = True
            session['expiry_date'] = "Reseller Control"
            log_activity(username, "Admin login")
            return redirect('/admin')

    success, user_info = verify_xtream_credentials(DEFAULT_DNS, username, password)

    if success and user_info:
        session['logged_in'] = True
        session['username'] = username
        session['is_admin'] = False
        # NOTE: we intentionally do NOT store the plaintext password in the
        # session anymore. Nothing else in the app read it, and it's not
        # something that should sit inside a browser cookie even signed.

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


# --- DASHBOARD & MEDIA SEARCH ---

@app.route('/dashboard')
def dashboard():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    username = session.get('username')
    days_remaining = None
    show_expiry_warning = False
    expiry_display = 'Active Line'

    # Fresh expiry from portal_users
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT expiry_date, expiry_timestamp
                FROM portal_users
                WHERE LOWER(username) = LOWER(?)
            """, (username.lower(),))
            row_exp = cursor.fetchone()

        if row_exp:
            exp_ts = row_exp['expiry_timestamp'] or 0
            if exp_ts > 0:
                expiry_display = datetime.fromtimestamp(exp_ts).strftime('%B %d, %Y')
                now_ts = int(time.time())
                days_remaining = int((exp_ts - now_ts) / 86400)
                if days_remaining <= 7:
                    show_expiry_warning = True
            else:
                expiry_display = 'Unlimited Account'
        else:
            expiry_display = session.get('expiry_date', 'Active Line')
    except Exception as e:
        print("DASHBOARD EXPIRY LOOKUP ERROR:", e)
        expiry_display = session.get('expiry_date', 'Active Line')

    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM requests WHERE username = ? ORDER BY timestamp DESC", (username,))
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
        """, (username,))
        user_payments = cursor.fetchall()

        cursor.execute("""
            SELECT earned_balance, spent_balance 
            FROM referral_wallets 
            WHERE LOWER(username) = LOWER(?)
        """, (username.lower(),))
        row_wallet = cursor.fetchone()
        if row_wallet:
            total_earned = row_wallet['earned_balance'] or 0.0
            total_spent = row_wallet['spent_balance'] or 0.0
        else:
            total_earned = 0.0
            total_spent = 0.0

        cursor.execute("""
            SELECT friend_username, type, amount, timestamp
            FROM referral_transactions
            WHERE LOWER(username) = LOWER(?)
            ORDER BY timestamp DESC
            LIMIT 10
        """, (username.lower(),))
        referral_history = cursor.fetchall()

    session['expiry_date'] = expiry_display

    return render_template(
        'dashboard.html',
        username=username,
        requests=user_requests,
        expiry_date=expiry_display,
        show_warning=show_expiry_warning,
        days_left=days_remaining,
        announcement=active_announcement,
        payments=user_payments,
        total_earned=total_earned,
        total_spent=total_spent,
        new_friend_bonus=NEW_FRIEND_BONUS,
        friend_renewal_bonus=FRIEND_RENEWAL_BONUS,
        referral_history=referral_history
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


@app.route('/submit_request', methods=['POST'])
def submit_request():
    """User: submit a movie/TV request, with Telegram alert."""
    if not session.get('logged_in'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    data = request.json or {}
    username = session.get('username')

    title = (data.get('title') or '').strip()
    year = (data.get('year') or '').strip()
    media_type = (data.get('type') or data.get('media_type') or 'movie').strip()
    imdb_id = (data.get('imdbID') or '').strip()
    poster = (data.get('poster') or '').strip()

    if not title:
        return jsonify({'success': False, 'message': 'Missing title'}), 400

    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO requests (username, title, year, media_type, imdb_id, poster)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (username, title, year, media_type, imdb_id, poster))
            conn.commit()

        send_telegram_alert_direct(
            f"<b>🎞 NEW MEDIA REQUEST</b>\n"
            f"<b>User:</b> <code>{username}</code>\n"
            f"<b>Title:</b> {title} {f'({year})' if year else ''}\n"
            f"<b>Type:</b> {media_type.upper()}\n"
            f"<b>ID:</b> <code>{imdb_id or 'N/A'}</code>"
        )

        log_activity(username, f"Submitted media request: {title} [{media_type}] {year}")
        return jsonify({'success': True, 'message': 'Request submitted.'})
    except Exception as e:
        print("SUBMIT_REQUEST ERROR:", e)
        return jsonify({'success': False, 'message': str(e)}), 500


# --- REFERRAL WALLET BALANCE ---

@app.route('/get_referral_balance')
def get_referral_balance():
    """Return current referral wallet balance for logged in user."""
    if not session.get('logged_in'):
        return jsonify({'balance': 0.0}), 401

    username = session.get('username')
    try:
        balance = get_wallet_balance(username)
        return jsonify({'balance': balance})
    except Exception as e:
        print("GET_REFERRAL_BALANCE ERROR:", e)
        return jsonify({'balance': 0.0}), 500


# --- REFERRAL FRIENDS (MANAGED USERS) ---

@app.route('/get_referral_friends')
def get_referral_friends():
    """Return a list of referred friends, expiry from main portal data."""
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
                cursor.execute("""
                    SELECT expiry_timestamp
                    FROM portal_users
                    WHERE LOWER(username)=LOWER(?)
                """, (friend_user.lower(),))
                row_p = cursor.fetchone()
                if row_p and row_p['expiry_timestamp']:
                    exp_ts = int(row_p['expiry_timestamp'])

                if exp_ts <= 0:
                    cursor.execute("""
                        SELECT expiry_timestamp
                        FROM user_metadata
                        WHERE LOWER(username)=LOWER(?)
                    """, (friend_user.lower(),))
                    row_m = cursor.fetchone()
                    if row_m and row_m['expiry_timestamp']:
                        exp_ts = int(row_m['expiry_timestamp'])

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
    Called after a PayPal payment from the dashboard - now verified server-side
    against PayPal directly before anything is written or credited.
    """
    if not session.get('logged_in'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    data = request.json or {}
    referrer = session.get('username')
    friend_username = (data.get('friend_username') or '').strip()
    order_id = (data.get('orderID') or '').strip()
    discount_str = (data.get('discount_redeemed') or '0').strip()
    connections = (data.get('connections') or '1').strip()

    if not friend_username or not order_id:
        return jsonify({'success': False, 'message': 'Missing friend_username or orderID'}), 400

    try:
        discount_val = float(discount_str)
    except ValueError:
        discount_val = 0.0

    # Reject a PayPal order_id that's already been logged for any payment.
    if order_id_already_used(order_id):
        return jsonify({'success': False, 'message': 'This order has already been processed.'}), 400

    # Check the referrer's real wallet balance before honoring any discount.
    real_balance = get_wallet_balance(referrer)
    if discount_val > real_balance + 0.01:
        return jsonify({'success': False, 'message': 'Wallet discount exceeds your available balance.'}), 400

    # Price comes from the server's own tier table, not whatever the browser sent.
    base_price = CONNECTION_TIER_PRICES.get(connections, 75.00)
    expected_amount = max(0.0, base_price - discount_val)

    if expected_amount > 0:
        ok, result = verify_paypal_order(order_id, expected_amount, "GBP")
        if not ok:
            print(f"RENEW_FRIEND_LINE VERIFICATION FAILED for {referrer}: {result}")
            return jsonify({'success': False, 'message': 'Payment could not be verified.'}), 400

    amount_val = expected_amount

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

            cursor.execute('''
                INSERT INTO referral_transactions (username, friend_username, type, amount)
                VALUES (?, ?, ?, ?)
            ''', (referrer, friend_username, 'FRIEND_RENEWAL', FRIEND_RENEWAL_BONUS))

            if discount_val > 0:
                cursor.execute("""
                    INSERT INTO referral_wallets (username, earned_balance, spent_balance)
                    VALUES (?, 0.0, ?)
                    ON CONFLICT(username) DO UPDATE SET
                        spent_balance = spent_balance + ?
                """, (referrer, discount_val, discount_val))

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

                action_msg = f"Created referral_friends row: '{friend_username}' now managed by '{new_referrer}'"
                admin_user = session.get('username', 'admin')
                log_activity(admin_user, action_msg)
                send_telegram_alert_direct(
                    f"<b>👥 NEW MANAGED FRIEND LINK</b>\n"
                    f"<b>Admin:</b> <code>{admin_user}</code>\n"
                    f"<b>Friend:</b> <code>{friend_username}</code>\n"
                    f"<b>Referrer:</b> <code>{new_referrer}</code>"
                )

                return jsonify({
                    'success': True,
                    'message': f"No existing referral record; created new link: '{friend_username}' is now managed by '{new_referrer}'."
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

        admin_user = session.get('username', 'admin')
        action_msg = (
            f"Reassigned referral friend '{friend_username}' to referrer '{new_referrer}'"
            + (f" (from '{old_referrer}')" if old_referrer else "")
        )
        log_activity(admin_user, action_msg)
        send_telegram_alert_direct(
            f"<b>👥 REFERRAL OWNERSHIP CHANGED</b>\n"
            f"<b>Admin:</b> <code>{admin_user}</code>\n"
            f"<b>Friend:</b> <code>{friend_username}</code>\n"
            f"<b>New Referrer:</b> <code>{new_referrer}</code>\n"
            + (f"<b>Old Referrer:</b> <code>{old_referrer}</code>" if old_referrer else "")
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
        send_telegram_alert_direct(
            f"<b>🗑 MANAGED FRIEND REMOVED</b>\n"
            f"<b>Referrer:</b> <code>{referrer}</code>\n"
            f"<b>Friend:</b> <code>{friend_username}</code>"
        )

        return jsonify({'success': True, 'message': f"'{friend_username}' removed from your managed list."})
    except Exception as e:
        print("REMOVE_MANAGED_FRIEND ERROR:", e)
        return jsonify({'success': False, 'message': str(e)}), 500


# --- PAYMENT & WALLET OPERATIONS (DASHBOARD) ---

@app.route('/log_payment', methods=['POST'])
def log_payment():
    """
    Log IPTV renewal payment from PayPal (or free wallet redemption).
    Now verified server-side against PayPal directly before anything is
    written or credited.
    """
    if not session.get('logged_in'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    data = request.json or {}
    username = session.get('username')
    order_id = (data.get('orderID') or '').strip()
    discount_str = (data.get('discount_redeemed') or '0').strip()
    connections = (data.get('connections') or '1').strip()

    if not order_id:
        return jsonify({'success': False, 'message': 'Missing orderID'}), 400

    try:
        discount_val = float(discount_str)
    except ValueError:
        discount_val = 0.0

    # Reject a PayPal order_id that's already been logged for any payment.
    if order_id_already_used(order_id):
        return jsonify({'success': False, 'message': 'This order has already been processed.'}), 400

    # Check the user's real wallet balance before honoring any discount.
    if discount_val > 0:
        real_balance = get_wallet_balance(username)
        if discount_val > real_balance + 0.01:
            return jsonify({'success': False, 'message': 'Wallet discount exceeds your available balance.'}), 400

    # Price comes from the server's own tier table, not whatever the browser sent.
    base_price = CONNECTION_TIER_PRICES.get(connections, 75.00)
    expected_amount = max(0.0, base_price - discount_val)

    if expected_amount <= 0:
        # Free wallet redemption path - no PayPal order exists at all, so there
        # is nothing to check with PayPal, but the wallet balance check above
        # already confirmed the "free" renewal is genuinely covered by credit.
        if not order_id.startswith("WALLET-FREE-REDEEM-"):
            return jsonify({'success': False, 'message': 'Invalid order reference for free redemption.'}), 400
    else:
        ok, result = verify_paypal_order(order_id, expected_amount, "GBP")
        if not ok:
            print(f"LOG_PAYMENT VERIFICATION FAILED for {username}: {result}")
            return jsonify({'success': False, 'message': 'Payment could not be verified.'}), 400

    amount_val = expected_amount

    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO payments (username, order_id, amount, status)
                VALUES (?, ?, ?, ?)
            ''', (username, order_id, f"{amount_val:.2f}", 'Pending Manual'))

            if discount_val > 0:
                cursor.execute('''
                    INSERT INTO referral_wallets (username, earned_balance, spent_balance)
                    VALUES (?, 0.0, ?)
                    ON CONFLICT(username) DO UPDATE SET
                        spent_balance = spent_balance + ?
                ''', (username, discount_val, discount_val))

            conn.commit()

        readable_connections = f"{connections} connection{'s' if str(connections) != '1' else ''}"

        send_telegram_alert_direct(
            f"<b>💳 IPTV RENEWAL PAYMENT</b>\n"
            f"<b>User:</b> <code>{username}</code>\n"
            f"<b>Order ID:</b> <code>{order_id}</code>\n"
            f"<b>Plan:</b> {readable_connections}\n"
            f"<b>Paid:</b> £{amount_val:.2f}\n"
            f"<b>Wallet Used:</b> £{discount_val:.2f}\n"
            f"<b>Status:</b> Pending manual extension"
        )

        log_activity(username, f"IPTV renewal payment logged (order {order_id}, {connections} conn)")

        return jsonify({'success': True, 'message': 'Payment logged; admin will extend your line.'})
    except Exception as e:
        print("LOG_PAYMENT ERROR:", e)
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/buy_spotify', methods=['POST'])
def buy_spotify():
    """
    Log a Spotify order and apply wallet discount.
    Now verified server-side against PayPal directly before anything is
    written or credited.
    """
    if not session.get('logged_in'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    data = request.json or {}
    portal_user = session.get('username')
    order_id = (data.get('orderID') or '').strip()
    su = (data.get('spotify_username') or '').strip()
    sp = (data.get('spotify_password') or '').strip()
    discount_str = (data.get('discount_redeemed') or '0').strip()

    if not order_id or not su or not sp:
        return jsonify({'success': False, 'message': 'Missing Spotify details or orderID'}), 400

    try:
        discount_val = float(discount_str)
    except ValueError:
        discount_val = 0.0

    if order_id_already_used(order_id):
        return jsonify({'success': False, 'message': 'This order has already been processed.'}), 400

    real_balance = get_wallet_balance(portal_user)
    if discount_val > real_balance + 0.01:
        return jsonify({'success': False, 'message': 'Wallet discount exceeds your available balance.'}), 400

    amount_val = max(0.0, SPOTIFY_PRICE - discount_val)

    if amount_val > 0:
        ok, result = verify_paypal_order(order_id, amount_val, "GBP")
        if not ok:
            print(f"BUY_SPOTIFY VERIFICATION FAILED for {portal_user}: {result}")
            return jsonify({'success': False, 'message': 'Payment could not be verified.'}), 400

    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO spotify_orders (
                    portal_username, spotify_username, spotify_password,
                    amount, discount_used, status
                )
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                portal_user, su, sp,
                amount_val, discount_val, 'Pending'
            ))

            cursor.execute('''
                INSERT INTO payments (username, order_id, amount, status)
                VALUES (?, ?, ?, ?)
            ''', (portal_user, order_id, f"{amount_val:.2f}", 'Completed'))

            if discount_val > 0:
                cursor.execute('''
                    INSERT INTO referral_wallets (username, earned_balance, spent_balance)
                    VALUES (?, 0.0, ?)
                    ON CONFLICT(username) DO UPDATE SET
                        spent_balance = spent_balance + ?
                ''', (portal_user, discount_val, discount_val))

            conn.commit()

        send_telegram_alert_direct(
            f"<b>🎵 NEW SPOTIFY ORDER</b>\n"
            f"<b>Portal User:</b> <code>{portal_user}</code>\n"
            f"<b>Spotify User:</b> <code>{su}</code>\n"
            f"<b>Order ID:</b> <code>{order_id}</code>\n"
            f"<b>Paid:</b> £{amount_val:.2f}\n"
            f"<b>Wallet Used:</b> £{discount_val:.2f}\n"
            f"<b>Status:</b> Pending upgrade"
        )

        log_activity(portal_user, f"Spotify order logged for {su} (order {order_id})")

        return jsonify({'success': True, 'message': 'Spotify order logged.'})
    except Exception as e:
        print("BUY_SPOTIFY ERROR:", e)
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/create_referral_line', methods=['POST'])
def create_referral_line():
    """
    Create a new friend line + reward referrer.
    Now REQUIRES and verifies a real PayPal order server-side before creating
    the line - previously this route created a paid IPTV line for free with
    no payment check at all.
    """
    if not session.get('logged_in'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    data = request.json or {}
    referrer = session.get('username')
    first_name = (data.get('first_name') or '').strip()
    last_name = (data.get('last_name') or '').strip()
    phone = (data.get('phone') or '').strip()
    order_id = (data.get('orderID') or '').strip()

    if not first_name or not last_name or not phone:
        return jsonify({'success': False, 'message': 'Missing friend details'}), 400
    if not order_id:
        return jsonify({'success': False, 'message': 'Missing orderID'}), 400
    if order_id_already_used(order_id):
        return jsonify({'success': False, 'message': 'This order has already been processed.'}), 400

    ok, result = verify_paypal_order(order_id, REFERRAL_LINE_PRICE, "GBP")
    if not ok:
        print(f"CREATE_REFERRAL_LINE VERIFICATION FAILED for {referrer}: {result}")
        return jsonify({'success': False, 'message': 'Payment could not be verified.'}), 400

    try:
        base = re.sub(r'[^a-zA-Z0-9]', '', f"{first_name}{last_name}")[:10] or "friend"
        suffix = ''.join(random.choices(string.digits, k=3))
        friend_username = f"{base}{suffix}".lower()
        plain_password = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
        hashed = generate_password_hash(plain_password)

        expiry_ts = int(time.time()) + 365 * 86400
        expiry_date = datetime.fromtimestamp(expiry_ts).strftime('%Y-%m-%d')

        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO portal_users (username, password, expiry_date, expiry_timestamp)
                VALUES (?, ?, ?, ?)
            ''', (friend_username, hashed, expiry_date, expiry_ts))

            cursor.execute('''
                INSERT INTO referral_friends (referrer_username, friend_username, friend_password, expiry_timestamp)
                VALUES (?, ?, ?, ?)
            ''', (referrer, friend_username, plain_password, expiry_ts))

            cursor.execute('''
                INSERT INTO referral_wallets (username, earned_balance, spent_balance)
                VALUES (?, ?, 0.0)
                ON CONFLICT(username) DO UPDATE SET
                    earned_balance = earned_balance + ?
            ''', (referrer, NEW_FRIEND_BONUS, NEW_FRIEND_BONUS))

            cursor.execute('''
                INSERT INTO referral_transactions (username, friend_username, type, amount)
                VALUES (?, ?, ?, ?)
            ''', (referrer, friend_username, 'NEW_FRIEND', NEW_FRIEND_BONUS))

            # This payment was never logged before. Logging it also means
            # order_id_already_used() correctly blocks a replay of this
            # exact order on any future request.
            cursor.execute('''
                INSERT INTO payments (username, order_id, amount, status)
                VALUES (?, ?, ?, 'Completed')
            ''', (referrer, order_id, f"{REFERRAL_LINE_PRICE:.2f}"))

            conn.commit()

        send_telegram_alert_direct(
            f"<b>👤 NEW FRIEND LINE CREATED</b>\n"
            f"<b>Referrer:</b> <code>{referrer}</code>\n"
            f"<b>Friend:</b> <code>{friend_username}</code>\n"
            f"<b>Phone:</b> <code>{phone}</code>\n"
            f"<b>Expiry (portal):</b> {expiry_date}\n"
            f"<b>Order ID:</b> <code>{order_id}</code>\n"
            f"<b>Referrer Wallet Bonus:</b> £{NEW_FRIEND_BONUS:.2f}"
        )

        log_activity(referrer, f"Created referral friend '{friend_username}' (order {order_id})")

        return jsonify({
            'success': True,
            'generated_user': friend_username,
            'generated_pass': plain_password
        })
    except Exception as e:
        print("CREATE_REFERRAL_LINE ERROR:", e)
        return jsonify({'success': False, 'message': str(e)}), 500


# --- LIVE CHANNELS: SEARCH & REPORTING ---

@app.route('/search_channels')
def search_channels():
    """
    Simple live channel search used for the dropdown on dashboard.
    Expects ?q= query, returns list of {name, stream_id}.
    """
    if not session.get('logged_in'):
        return jsonify([]), 401

    q = (request.args.get('q') or '').strip()
    if not q:
        return jsonify([])

    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            like = f"%{q}%"
            cursor.execute("""
                SELECT name, stream_id
                FROM live_channels
                WHERE name LIKE ?
                ORDER BY name ASC
                LIMIT 50
            """, (like,))
            rows = cursor.fetchall()
        return jsonify([{'name': r['name'], 'stream_id': r['stream_id']} for r in rows])
    except Exception as e:
        print("SEARCH_CHANNELS ERROR:", e)
        return jsonify([]), 500


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


# --- VOD: SEARCH (TMDB) & REPORTING ---

@app.route('/search_vod_catalog')
def search_vod_catalog():
    """
    Use TMDB to search movies & TV for VOD reporting dropdown.
    Query param: ?q=
    """
    if not session.get('logged_in'):
        return jsonify({"results": []}), 401

    query = (request.args.get('q') or '').strip()
    if not query:
        return jsonify({"results": []})

    try:
        url = "https://api.themoviedb.org/3/search/multi"
        resp = requests.get(url, params={
            'api_key': TMDB_API_KEY,
            'language': 'en-US',
            'query': query,
            'page': 1,
            'include_adult': 'false'
        }, timeout=6)
        if resp.status_code != 200:
            print("TMDB VOD SEARCH ERROR:", resp.status_code, resp.text[:200])
            return jsonify({"results": []})
        return jsonify(resp.json())
    except Exception as e:
        print("TMDB VOD SEARCH EXCEPTION:", e)
        return jsonify({"results": []})


@app.route('/submit_vod_report', methods=['POST'])
def submit_vod_report():
    """
    User: submit VOD fault ticket.
    Expects JSON:
      title, media_type ('movie'|'tv'), issue_type, issue_notes (optional)
    """
    if not session.get('logged_in'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    data = request.json or {}
    username = session.get('username')
    title = (data.get('title') or '').strip()
    media_type = (data.get('media_type') or '').strip()
    issue_type = (data.get('issue_type') or '').strip()
    issue_notes = (data.get('issue_notes') or '').strip()

    if not title or not media_type or not issue_type:
        return jsonify({'success': False, 'message': 'Missing title, type or issue.'}), 400

    final_issue_type = issue_type
    if issue_type.lower() == 'other' and issue_notes:
        final_issue_type = f"Other: {issue_notes[:100]}"

    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO vod_reports (username, title, media_type, issue_type, issue_notes)
                VALUES (?, ?, ?, ?, ?)
            ''', (username, title, media_type, final_issue_type, issue_notes[:255]))
            conn.commit()

        send_telegram_alert_direct(
            f"<b>🎬 VOD FAULT TICKET</b>\n"
            f"<b>User:</b> <code>{username}</code>\n"
            f"<b>Title:</b> {title}\n"
            f"<b>Type:</b> {media_type.upper()}\n"
            f"<b>Issue:</b> {final_issue_type}"
        )

        log_activity(username, f"VOD fault report: {title} ({media_type}) - {final_issue_type}")

        return jsonify({'success': True, 'message': 'VOD fault ticket logged.'})
    except Exception as e:
        print("SUBMIT_VOD_REPORT ERROR:", e)
        return jsonify({'success': False, 'message': str(e)}), 500


# --- ADMIN PANEL & HELPERS ---

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


@app.route('/admin/set_announcement', methods=['POST'])
def set_announcement():
    if not is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    data = request.json or {}
    msg = (data.get('message') or '').strip()
    if not msg:
        return jsonify({'success': False, 'message': 'Message is required.'}), 400

    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE announcements SET active = 0")
            cursor.execute("INSERT INTO announcements (message, active) VALUES (?, 1)", (msg,))
            conn.commit()
        return jsonify({'success': True, 'message': 'Announcement updated.'})
    except Exception as e:
        print("SET_ANNOUNCEMENT ERROR:", e)
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/get_pending_users')
def admin_get_pending_users():
    if not is_admin():
        return jsonify([]), 403

    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT id, username, email, created_at FROM pending_users ORDER BY created_at ASC')
            rows = cursor.fetchall()
        return jsonify([dict(r) for r in rows])
    except Exception as e:
        print("GET_PENDING_USERS ERROR:", e)
        return jsonify([]), 500


@app.route('/admin/approve_user', methods=['POST'])
def approve_user():
    if not is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    data = request.json or {}
    pid = data.get('id')
    if not pid:
        return jsonify({'success': False, 'message': 'Missing pending user ID.'}), 400

    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute('SELECT * FROM pending_users WHERE id = ?', (pid,))
            pending = cursor.fetchone()
            if not pending:
                return jsonify({'success': False, 'message': 'Pending user not found.'}), 404

            uname = pending['username']
            hashed_pw = pending['password']

            expiry_ts = int(time.time()) + 365 * 86400
            expiry_date = datetime.fromtimestamp(expiry_ts).strftime('%Y-%m-%d')

            cursor.execute('''
                INSERT INTO portal_users (username, password, expiry_date, expiry_timestamp)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(username) DO UPDATE SET
                    password = excluded.password,
                    expiry_date = excluded.expiry_date,
                    expiry_timestamp = excluded.expiry_timestamp
            ''', (uname, hashed_pw, expiry_date, expiry_ts))

            cursor.execute('DELETE FROM pending_users WHERE id = ?', (pid,))
            conn.commit()

        admin_user = session.get('username', 'admin')
        log_activity(admin_user, f"Approved pending user {uname}")
        send_telegram_alert_direct(
            f"<b>✅ REGISTRATION APPROVED</b>\n"
            f"<b>User:</b> <code>{uname}</code>\n"
            f"<b>Approved by:</b> <code>{admin_user}</code>"
        )

        return jsonify({'success': True, 'message': f"User '{uname}' approved and portal account created."})
    except Exception as e:
        print("APPROVE_USER ERROR:", e)
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/reject_user', methods=['POST'])
def reject_user():
    if not is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    data = request.json or {}
    pid = data.get('id')
    if not pid:
        return jsonify({'success': False, 'message': 'Missing pending user ID.'}), 400

    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT username FROM pending_users WHERE id = ?', (pid,))
            row = cursor.fetchone()
            if not row:
                return jsonify({'success': False, 'message': 'Pending user not found.'}), 404
            uname = row[0]

            cursor.execute('DELETE FROM pending_users WHERE id = ?', (pid,))
            conn.commit()

        admin_user = session.get('username', 'admin')
        log_activity(admin_user, f"Rejected pending user {uname}")

        return jsonify({'success': True, 'message': f"Registration for '{uname}' rejected and removed."})
    except Exception as e:
        print("REJECT_USER ERROR:", e)
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/sync_live_panel_expirations', methods=['POST'])
def sync_live_panel_expirations():
    """Placeholder for syncing expiry from reseller panel."""
    if not is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    # TODO: Implement actual call to reseller API and update user_metadata.
    return jsonify({'success': True, 'message': 'Sync placeholder (implement reseller API).'})


@app.route('/update_request_status_by_admin/<int:req_id>', methods=['POST'])
def update_request_status_by_admin(req_id):
    if not is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE requests SET status = ? WHERE id = ?', ('Completed', req_id))
            if cursor.rowcount == 0:
                return jsonify({'success': False, 'message': 'Request not found.'}), 404
            conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        print("UPDATE_REQUEST_STATUS ERROR:", e)
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/delete_request/<int:req_id>', methods=['POST'])
def admin_delete_request(req_id):
    if not is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM requests WHERE id = ?', (req_id,))
            if cursor.rowcount == 0:
                return jsonify({'success': False, 'message': 'Request not found.'}), 404
            conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        print("DELETE_REQUEST ERROR:", e)
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/delete_channel_report_by_admin/<int:report_id>', methods=['POST'])
def delete_channel_report_by_admin(report_id):
    if not is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM channel_reports WHERE id = ?', (report_id,))
            if cursor.rowcount == 0:
                return jsonify({'success': False, 'message': 'Report not found.'}), 404
            conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        print("DELETE_CHANNEL_REPORT ERROR:", e)
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/delete_vod_report_by_admin/<int:report_id>', methods=['POST'])
def delete_vod_report_by_admin(report_id):
    if not is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM vod_reports WHERE id = ?', (report_id,))
            if cursor.rowcount == 0:
                return jsonify({'success': False, 'message': 'Report not found.'}), 404
            conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        print("DELETE_VOD_REPORT ERROR:", e)
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/adjust_user_credit', methods=['POST'])
def adjust_user_credit():
    if not is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    data = request.json or {}
    username = (data.get('target_username') or '').strip()
    amount_str = (data.get('amount') or '').strip()

    if not username or not amount_str:
        return jsonify({'success': False, 'message': 'Username and amount are required.'}), 400

    try:
        amount_val = float(amount_str)
    except ValueError:
        return jsonify({'success': False, 'message': 'Invalid amount value.'}), 400

    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO referral_wallets (username, earned_balance, spent_balance)
                VALUES (?, ?, 0.0)
                ON CONFLICT(username) DO UPDATE SET
                    earned_balance = earned_balance + ?
            ''', (username, amount_val, amount_val))
            conn.commit()

        admin_user = session.get('username', 'admin')
        log_activity(admin_user, f"Manual wallet credit +£{amount_val:.2f} to {username}")

        return jsonify({'success': True, 'message': f"Credited £{amount_val:.2f} to {username}'s wallet."})
    except Exception as e:
        print("ADJUST_USER_CREDIT ERROR:", e)
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/create_portal_user', methods=['POST'])
def create_portal_user():
    if not is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    data = request.json or {}
    username = (data.get('username') or '').strip()
    password = (data.get('password') or '').strip()
    expiry_date_str = (data.get('expiry_date') or '').strip()

    if not username or not password or not expiry_date_str:
        return jsonify({'success': False, 'message': 'username, password, expiry_date required.'}), 400

    try:
        expiry_dt = datetime.strptime(expiry_date_str, '%Y-%m-%d')
        expiry_ts = int(expiry_dt.timestamp())
    except ValueError:
        return jsonify({'success': False, 'message': 'Expiry date must be YYYY-MM-DD.'}), 400

    try:
        hashed = generate_password_hash(password)
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO portal_users (username, password, expiry_date, expiry_timestamp)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(username) DO UPDATE SET
                    password = excluded.password,
                    expiry_date = excluded.expiry_date,
                    expiry_timestamp = excluded.expiry_timestamp
            ''', (username, hashed, expiry_date_str, expiry_ts))
            conn.commit()

        admin_user = session.get('username', 'admin')
        log_activity(admin_user, f"Created/updated portal user {username}")

        return jsonify({'success': True, 'message': f"Portal user '{username}' saved."})
    except Exception as e:
        print("CREATE_PORTAL_USER ERROR:", e)
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/delete_portal_user/<username>', methods=['POST'])
def delete_portal_user(username):
    if not is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM portal_users WHERE LOWER(username) = LOWER(?)', (username,))
            if cursor.rowcount == 0:
                return jsonify({'success': False, 'message': 'User not found.'}), 404
            conn.commit()

        admin_user = session.get('username', 'admin')
        log_activity(admin_user, f"Deleted portal user {username}")

        return jsonify({'success': True})
    except Exception as e:
        print("DELETE_PORTAL_USER ERROR:", e)
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/reset_portal_user_password', methods=['POST'])
def reset_portal_user_password():
    if not is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    data = request.json or {}
    username = (data.get('username') or '').strip()
    if not username:
        return jsonify({'success': False, 'message': 'Username required.'}), 400

    new_plain = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
    hashed = generate_password_hash(new_plain)

    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute(
                'UPDATE portal_users SET password = ? WHERE LOWER(username) = LOWER(?)',
                (hashed, username.lower())
            )
            if cursor.rowcount == 0:
                return jsonify({'success': False, 'message': 'User not found.'}), 404
            conn.commit()

        admin_user = session.get('username', 'admin')
        log_activity(admin_user, f"Reset portal password for {username}")

        return jsonify({'success': True, 'new_password': new_plain})
    except Exception as e:
        print("RESET_PORTAL_PW ERROR:", e)
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/amend_user_expiry', methods=['POST'])
def amend_user_expiry():
    if not is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    data = request.json or {}
    username = (data.get('username') or '').strip()
    expiry_date_str = (data.get('expiry_date') or '').strip()

    if not username or not expiry_date_str:
        return jsonify({'success': False, 'message': 'username and expiry_date required.'}), 400

    try:
        expiry_dt = datetime.strptime(expiry_date_str, '%Y-%m-%d')
        expiry_ts = int(expiry_dt.timestamp())
    except ValueError:
        return jsonify({'success': False, 'message': 'Expiry date must be YYYY-MM-DD.'}), 400

    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE portal_users
                SET expiry_date = ?, expiry_timestamp = ?
                WHERE LOWER(username) = LOWER(?)
            ''', (expiry_date_str, expiry_ts, username.lower()))
            if cursor.rowcount == 0:
                return jsonify({'success': False, 'message': 'Portal user not found.'}), 404
            conn.commit()

        admin_user = session.get('username', 'admin')
        log_activity(admin_user, f"Adjusted expiry for {username} to {expiry_date_str}")

        return jsonify({'success': True, 'message': f"Expiry for '{username}' set to {expiry_date_str}."})
    except Exception as e:
        print("AMEND_USER_EXPIRY ERROR:", e)
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/add_live_channel', methods=['POST'])
def add_live_channel():
    if not is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    data = request.json or {}
    name = (data.get('name') or '').strip()
    stream_id = (data.get('stream_id') or '').strip()
    if not name or not stream_id:
        return jsonify({'success': False, 'message': 'Name and stream_id are required.'}), 400

    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO live_channels (stream_id, name)
                VALUES (?, ?)
                ON CONFLICT(stream_id) DO UPDATE SET
                    name = excluded.name
            ''', (stream_id, name))
            conn.commit()
        return jsonify({'success': True, 'message': 'Channel saved.'})
    except Exception as e:
        print("ADD_LIVE_CHANNEL ERROR:", e)
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/delete_live_channel/<stream_id>', methods=['POST'])
def delete_live_channel(stream_id):
    if not is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM live_channels WHERE stream_id = ?', (stream_id,))
            if cursor.rowcount == 0:
                return jsonify({'success': False, 'message': 'Channel not found.'}), 404
            conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        print("DELETE_LIVE_CHANNEL ERROR:", e)
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/complete_manual_renewal/<int:payment_id>', methods=['POST'])
def complete_manual_renewal(payment_id):
    if not is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE payments SET status = ? WHERE id = ?', ('Completed', payment_id))
            if cursor.rowcount == 0:
                return jsonify({'success': False, 'message': 'Payment record not found.'}), 404
            conn.commit()
        admin_user = session.get('username', 'admin')
        log_activity(admin_user, f"Marked manual renewal payment {payment_id} as Completed")
        return jsonify({'success': True})
    except Exception as e:
        print("COMPLETE_MANUAL_RENEWAL ERROR:", e)
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/logout')
def logout():
    username = session.get('username')
    session.clear()
    if username:
        log_activity(username, "Logout")
    return redirect('/')


if __name__ == '__main__':
    app.run(debug=False, port=5000)
