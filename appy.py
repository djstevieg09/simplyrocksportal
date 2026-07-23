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
    (Local verification, not remote Xtream API.)
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


@app.route('/', endpoint='login', methods=['GET', 'POST'])
def login():
    """Handles secure user and administrator authentication, strictly validating credentials against the local server."""
    if request.method == 'GET':
        return render_template('login.html', default_dns=DEFAULT_DNS)

    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()

    if not username or not password:
        return render_template('login.html', error="Please supply both username and password configurations.")

    # --- 1. ADMINISTRATIVE LOGIN ---
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
                        f"<i>Action Required: Contact client for renewal.</i>\n"
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


@app.route('/admin/reset_portal_user_password', methods=['POST'])
def admin_reset_portal_user_password():
    """Admin-only: reset a portal user's password to a new random value and return it once."""
    if not is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    data = request.json or {}
    target_user = str(data.get('username', '')).strip()
    if not target_user:
        return jsonify({'success': False, 'message': 'Missing target username.'}), 400

    try:
        # Generate new random password
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

        # Optional Telegram notification
        try:
            send_telegram_alert_direct(
                f"<b>🔑 PORTAL PASSWORD RESET</b>\n"
                f"----------------------------------------\n"
                f"<b>User:</b> <code>{target_user}</code>\n"
                f"<b>New Password:</b> <code>{new_plain}</code>\n"
                f"----------------------------------------\n"
                f"<i>Share this new password securely with the customer.</i>"
            )
        except Exception:
            pass

        return jsonify({
            'success': True,
            'message': f"Password reset successfully for user '{target_user}'.",
            'new_password': new_plain
        })
    except Exception as e:
        print(f"ADMIN RESET PORTAL PASSWORD ERROR: {e}")
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

# (Remaining routes unchanged from the previous full version you already have.)

# ... KEEP all the other routes exactly as in the last working version:
# /search_media, /create_referral_line, /submit_request, /log_payment,
# /get_referral_balance, /admin, /admin/adjust_user_credit,
# /admin/update_status, /admin/delete_request, /search_channels,
# /logout, /complete_manual_renewal, /update_request_status_by_admin,
# /delete_channel_report_by_admin, /submit_vod_report,
# /admin/add_live_channel, /admin/delete_live_channel,
# /submit_crowdsourced_channel, /admin/amend_user_expiry,
# /submit_channel_report, /admin/force_db_patch_override,
# /delete_vod_report_by_admin


if __name__ == '__main__':
    app.run(debug=True, port=5000)
