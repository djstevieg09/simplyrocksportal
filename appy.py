import os
import time
import random
import string
import sqlite3
from datetime import datetime
from queue import Queue

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


# --- USER REGISTRATION, LOGIN, DASHBOARD, ADMIN, ETC. ---
# (Everything from your previous working script remains identical up to /get_referral_friends)

# --- Registration, login, admin endpoints omitted here for brevity in this explanation ---
# YOU SHOULD KEEP all the routes exactly as in your last working version
# and only replace the three routes below:
#  - /get_referral_friends
#  - /renew_friend_line
#  - /admin/reassign_referral_friend

# For your actual file, paste all earlier routes from your last known-good app.py
# and then replace /get_referral_friends, /renew_friend_line, /admin/reassign_referral_friend
# with the versions below.


@app.route('/get_referral_friends')
def get_referral_friends():
    """Return a list of referred friends for the logged-in user."""
    if not session.get('logged_in'):
        return jsonify([]), 401

    referrer = session.get('username')
    results = []
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT friend_username, friend_password, expiry_timestamp
                FROM referral_friends
                WHERE LOWER(referrer_username) = LOWER(?)
                ORDER BY created_at DESC
            ''', (referrer.lower(),))
            rows = cursor.fetchall()
            now_ts = int(time.time())
            for row in rows:
                friend_user = row[0]
                friend_pass = row[1]
                exp_ts = row[2]
                if exp_ts > 0:
                    readable = datetime.fromtimestamp(exp_ts).strftime('%B %d, %Y')
                    days_left = int((exp_ts - now_ts) / 86400)
                else:
                    readable = "Unknown"
                    days_left = None
                results.append({
                    'friend_username': friend_user,
                    'friend_password': friend_pass,
                    'expiry_date': readable,
                    'days_left': days_left
                })
    except Exception as e:
        print(f"GET_REFERRAL_FRIENDS ERROR: {e}")
    return jsonify(results)


@app.route('/renew_friend_line', methods=['POST'])
def renew_friend_line():
    """
    User-initiated: renew a referred friend's IPTV line.
    Called after successful PayPal payment from the dashboard.

    Expects JSON:
      {
        "friend_username": "friendUser",
        "orderID": "PAYPAL-ID",
        "amount": "75.00",
        "discount_redeemed": "10.00"
      }

    Behaviour:
    - Logs payment under the referrer's username (session user).
    - Extends friend's expiry_timestamp by 1 year from now in referral_friends.
    - Credits FRIEND_RENEWAL_BONUS to referrer's wallet.
    - Sends Telegram notification to admin with all details.
    """
    if not session.get('logged_in'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    data = request.json or {}
    referrer = session.get('username')
    friend_username = (data.get('friend_username') or '').strip()
    order_id = (data.get('orderID') or '').strip()
    amount_str = (data.get('amount') or '0').strip()
    discount_str = (data.get('discount_redeemed') or '0').strip()

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

            # 1) Log payment row under referrer
            cursor.execute('''
                INSERT INTO payments (username, order_id, amount, status)
                VALUES (?, ?, ?, 'Completed')
            ''', (referrer, order_id, f"{amount_val:.2f}", 'Completed'))

            # 2) Extend friend's expiry by 1 year (from now)
            one_year_ts = int(time.time()) + (365 * 86400)
            cursor.execute("""
                UPDATE referral_friends
                SET expiry_timestamp = ?
                WHERE LOWER(friend_username) = LOWER(?)
            """, (one_year_ts, friend_username.lower()))

            # 3) Credit renewal bonus into referrer's referral_wallet
            cursor.execute("""
                INSERT INTO referral_wallets (username, earned_balance, spent_balance)
                VALUES (?, ?, 0.0)
                ON CONFLICT(username) DO UPDATE SET
                    earned_balance = earned_balance + ?
            """, (referrer, FRIEND_RENEWAL_BONUS, FRIEND_RENEWAL_BONUS))

            conn.commit()

        readable_expiry = datetime.fromtimestamp(one_year_ts).strftime('%B %d, %Y')
        send_telegram_alert_direct(
            f"<b>🔁 FRIEND LINE RENEWAL</b>\n"
            f"<b>Referrer:</b> <code>{referrer}</code>\n"
            f"<b>Friend Line:</b> <code>{friend_username}</code>\n"
            f"<b>Order ID:</b> <code>{order_id}</code>\n"
            f"<b>Paid:</b> £{amount_val:.2f}\n"
            f"<b>Wallet Used:</b> £{discount_val:.2f}\n"
            f"<b>New Local Expiry (Portal):</b> {readable_expiry}"
        )

        log_activity(referrer, f"Renewed friend line {friend_username} (order {order_id})")

        return jsonify({'success': True, 'message': f"Friend line '{friend_username}' renewed. Admin will extend it on the IPTV panel."})
    except Exception as e:
        print(f"RENEW_FRIEND_LINE ERROR: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/reassign_referral_friend', methods=['POST'])
def admin_reassign_referral_friend():
    """
    Admin: move ANY portal user under ANY referrer so they appear as a managed friend.

    Behaviour:
    - Verifies new_referrer exists in portal_users.
    - Verifies friend_username exists in portal_users.
    - If a referral_friends row already exists for friend_username:
        - UPDATE referrer_username to new_referrer (optionally filter by old_referrer).
    - If no referral_friends row exists:
        - INSERT a new row in referral_friends with:
            referrer_username = new_referrer,
            friend_username   = friend_username,
            friend_password   = 'N/A',
            expiry_timestamp  = 0.
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

            # Ensure new referrer exists as a portal user
            cursor.execute(
                "SELECT username FROM portal_users WHERE LOWER(username) = LOWER(?)",
                (new_referrer.lower(),)
            )
            if not cursor.fetchone():
                return jsonify({
                    'success': False,
                    'message': f"New referrer '{new_referrer}' does not exist as a portal user."
                }), 400

            # Ensure friend exists as a portal user
            cursor.execute(
                "SELECT username FROM portal_users WHERE LOWER(username) = LOWER(?)",
                (friend_username.lower(),)
            )
            friend_row = cursor.fetchone()
            if not friend_row:
                return jsonify({
                    'success': False,
                    'message': f"Friend user '{friend_username}' does not exist in portal_users."
                }), 400

            # Check for existing referral_friends rows for this friend
            cursor.execute("""
                SELECT id, referrer_username
                FROM referral_friends
                WHERE LOWER(friend_username) = LOWER(?)
            """, (friend_username.lower(),))
            rows = cursor.fetchall()

            if not rows:
                # No referral record yet: create one
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

            # There is already at least one referral_friends row for this friend
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
        print(f"ADMIN REASSIGN_REFERRAL ERROR: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# --- all your remaining routes (channel reports, VOD, admin panel, etc.) should remain unchanged ---
# Make sure this file ends cleanly:

if __name__ == '__main__':
    app.run(debug=True, port=5000)
