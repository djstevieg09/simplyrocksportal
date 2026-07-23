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

# --- FLASK APP ---
app = Flask(__name__)
app.secret_key = "simplyrocks_secure_master_portal_key_string_09"

# --- CONFIG ---
DEFAULT_DNS = "http://simplyrocks.org:80"
TMDB_API_KEY = os.environ.get('TMDB_API_KEY')
DB_FILE = "/data/database.db"
NOTIFICATION_QUEUE = Queue()

RESELLER_PANEL_URL = "https://theservice.rocks:80"
RESELLER_USERNAME = os.environ.get('RESELLER_USER')
RESELLER_PASSWORD = os.environ.get('RESELLER_PASS')

TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

XTREAM_DEFAULT_PASSWORD = os.environ.get('XTREAM_DEFAULT_PASSWORD', '')

SPOTIFY_PRICE = 45.00
FRIEND_RENEWAL_BONUS = 10.00
NEW_FRIEND_BONUS = 25.00


# --- DB INIT ---
def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()

        c.execute('''
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

        c.execute('''
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                order_id TEXT NOT NULL,
                amount TEXT NOT NULL,
                status TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS referral_wallets (
                username TEXT PRIMARY KEY,
                earned_balance REAL DEFAULT 0.0,
                spent_balance REAL DEFAULT 0.0,
                last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS channel_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                channel_name TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                issue_type TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS user_metadata (
                username TEXT PRIMARY KEY,
                expiry_date TEXT NOT NULL,
                expiry_timestamp INTEGER NOT NULL,
                alert_sent INTEGER DEFAULT 0,
                last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS vod_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                title TEXT NOT NULL,
                media_type TEXT NOT NULL,
                issue_type TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS portal_users (
                username TEXT PRIMARY KEY,
                password TEXT NOT NULL,
                expiry_date TEXT NOT NULL,
                expiry_timestamp INTEGER NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS live_channels (
                stream_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS announcements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message TEXT NOT NULL,
                active INTEGER DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        c.execute('''
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

        c.execute('''
            CREATE TABLE IF NOT EXISTS referral_friends (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_username TEXT NOT NULL,
                friend_username TEXT NOT NULL,
                friend_password TEXT NOT NULL,
                expiry_timestamp INTEGER NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                action TEXT,
                ip_address TEXT,
                user_agent TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS pending_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                email TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        try:
            c.execute("ALTER TABLE vod_reports ADD COLUMN issue_notes TEXT DEFAULT ''")
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                print("DB MIGRATION:", e)

        conn.commit()


init_db()


def is_admin():
    secure_admin_username = (os.environ.get('PORTAL_ADMIN_USER') or "djstevieg09").lower()
    current_user = str(session.get('username', '')).lower()
    return session.get('logged_in') and (session.get('is_admin') or current_user == secure_admin_username)


def log_activity(username, action):
    try:
        ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        ua = request.headers.get('User-Agent', '')
    except RuntimeError:
        ip = ''
        ua = ''
    try:
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO activity_log (username, action, ip_address, user_agent)
                VALUES (?, ?, ?, ?)
            ''', (username, action, ip, ua))
            conn.commit()
    except Exception as e:
        print("ACTIVITY LOG ERROR:", e)


def send_telegram_alert_direct(message_text):
    try:
        bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
        chat_id = os.environ.get('TELEGRAM_CHAT_ID')
        if not bot_token or not chat_id:
            return False
        api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {"chat_id": chat_id, "text": message_text, "parse_mode": "HTML"}
        r = requests.post(api_url, json=payload, timeout=8)
        return r.status_code == 200
    except Exception as e:
        print("TELEGRAM ERROR:", e)
        return False


def verify_xtream_credentials(dns, username, password):
    """Use local portal_users as auth backend."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute(
                "SELECT * FROM portal_users WHERE LOWER(username)=LOWER(?)",
                (username.strip().lower(),)
            )
            row = c.fetchone()
        if row and check_password_hash(row['password'], password.strip()):
            return True, {'auth': 1, 'status': 'Active', 'exp_date': row['expiry_timestamp']}
    except Exception as e:
        print("LOGIN MAP ERROR:", e)
    return False, None


# --- REGISTRATION & LOGIN ---

@app.route('/register', methods=['POST'])
def register():
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
            c = conn.cursor()
            c.execute("SELECT username FROM portal_users WHERE LOWER(username)=LOWER(?)", (uname.lower(),))
            if c.fetchone():
                return jsonify({'success': False, 'message': 'This username is already approved and in use.'}), 400
            c.execute("SELECT username FROM pending_users WHERE LOWER(username)=LOWER(?)", (uname.lower(),))
            if c.fetchone():
                return jsonify({'success': False, 'message': 'This username is already awaiting approval.'}), 400

            hashed = generate_password_hash(pword)
            c.execute("INSERT INTO pending_users (username,password,email) VALUES (?,?,?)",
                      (uname, hashed, email or None))
            conn.commit()

        log_activity(uname, "Registration submitted (pending approval)")
        send_telegram_alert_direct(
            f"<b>📝 NEW REGISTRATION PENDING APPROVAL</b>\n"
            f"<b>Username:</b> <code>{uname}</code>\n"
            f"<b>Email:</b> <code>{email or 'N/A'}</code>"
        )
        return jsonify({'success': True, 'message': 'Registration submitted. Admin must approve your account.'})
    except Exception as e:
        print("REGISTRATION ERROR:", e)
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/', endpoint='login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html', default_dns=DEFAULT_DNS)

    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    if not username or not password:
        return render_template('login.html', error="Please supply both username and password.")

    secure_admin_username = os.environ.get('PORTAL_ADMIN_USER')
    secure_admin_password = os.environ.get('PORTAL_ADMIN_PASS')
    if secure_admin_username and secure_admin_password:
        if username.lower() == secure_admin_username.lower() and password == secure_admin_password:
            session['logged_in'] = True
            session['username'] = username
            session['password'] = password
            session['is_admin'] = True
            session['expiry_date'] = "Reseller Control"
            log_activity(username, "Admin login")
            return redirect('/admin')

    success, info = verify_xtream_credentials(DEFAULT_DNS, username, password)
    if not success:
        return render_template('login.html', error="Invalid username/password, or not approved yet.")

    session['logged_in'] = True
    session['username'] = username
    session['password'] = password
    session['is_admin'] = False
    log_activity(username, "User login")

    raw_exp = info.get('exp_date')
    exp_ts = 0
    if raw_exp is None or str(raw_exp).strip().lower() in ['null', '', '0', 'none', 'false']:
        session['expiry_date'] = "Unlimited Account"
        readable_date = "Unlimited Account"
    else:
        try:
            ts = int(raw_exp)
            if ts < 100000000:
                session['expiry_date'] = "Unlimited Account"
                readable_date = "Unlimited Account"
            else:
                exp_ts = ts
                readable_date = datetime.fromtimestamp(ts).strftime('%B %d, %Y')
                session['expiry_date'] = readable_date
        except Exception:
            session['expiry_date'] = "Active Line"
            readable_date = "Active Line"

    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT alert_sent FROM user_metadata WHERE LOWER(username)=LOWER(?)", (username.lower(),))
            row = c.fetchone()
            already_sent = row['alert_sent'] if row else 0
            now = int(time.time())
            days_left = int((exp_ts - now) / 86400) if exp_ts > 0 else 999
            if 0 <= days_left <= 7 and not already_sent:
                alert_sent = 1
                send_telegram_alert_direct(
                    f"<b>⏳ APPROACHING EXPIRATION</b>\n"
                    f"<b>User:</b> <code>{username}</code>\n"
                    f"<b>Expiry:</b> {readable_date}\n"
                    f"<b>Days Left:</b> {days_left}"
                )
            else:
                alert_sent = already_sent if days_left <= 7 else 0

            c.execute('''
                INSERT INTO user_metadata (username, expiry_date, expiry_timestamp, alert_sent)
                VALUES (?,?,?,?)
                ON CONFLICT(username) DO UPDATE SET
                    expiry_date=excluded.expiry_date,
                    expiry_timestamp=excluded.expiry_timestamp,
                    alert_sent=excluded.alert_sent,
                    last_updated=CURRENT_TIMESTAMP
            ''', (username, readable_date, exp_ts, alert_sent))
            conn.commit()
    except Exception as e:
        print("LOCAL CACHE ERROR:", e)

    return redirect(url_for('dashboard'))


# --- DASHBOARD ---

@app.route('/dashboard')
def dashboard():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    days_remaining = None
    show_warning = False
    if session.get('password') and session.get('username'):
        success, info = verify_xtream_credentials(DEFAULT_DNS, session['username'], session['password'])
        if success and info:
            raw = info.get('exp_date')
            if raw and str(raw).strip().lower() not in ['null', '', '0', 'none', 'false']:
                try:
                    ts = int(raw)
                    now = int(time.time())
                    days_remaining = int((ts - now) / 86400)
                    if days_remaining <= 7:
                        show_warning = True
                except Exception:
                    pass

    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM requests WHERE username=? ORDER BY timestamp DESC", (session['username'],))
        reqs = c.fetchall()

        c.execute("SELECT message FROM announcements WHERE active=1 ORDER BY created_at DESC LIMIT 1")
        row = c.fetchone()
        announcement = row['message'] if row else None

        c.execute("""
            SELECT order_id, amount, status, timestamp
            FROM payments
            WHERE username = ?
            ORDER BY timestamp DESC
            LIMIT 10
        """, (session['username'],))
        pays = c.fetchall()

        c.execute("""
            SELECT earned_balance, spent_balance FROM referral_wallets
            WHERE LOWER(username)=LOWER(?)
        """, (session['username'].lower(),))
        wrow = c.fetchone()
        if wrow:
            total_earned = wrow['earned_balance'] or 0.0
            total_spent = wrow['spent_balance'] or 0.0
        else:
            total_earned = 0.0
            total_spent = 0.0

    return render_template(
        'dashboard.html',
        username=session['username'],
        requests=reqs,
        expiry_date=session.get('expiry_date', 'Active Line'),
        show_warning=show_warning,
        days_left=days_remaining,
        announcement=announcement,
        payments=pays,
        total_earned=total_earned,
        total_spent=total_spent
    )


# --- SIMPLE MEDIA SEARCH ---

@app.route('/search_media')
def search_media():
    if not session.get('logged_in'):
        return jsonify({"results": []}), 401
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify({"results": []})
    try:
        url = "https://api.themoviedb.org/3/search/multi"
        r = requests.get(url, params={
            'api_key': TMDB_API_KEY,
            'language': 'en-US',
            'query': q,
            'page': 1,
            'include_adult': 'false'
        }, timeout=6)
        if r.status_code == 200:
            return jsonify(r.json())
    except Exception as e:
        print("TMDB ERROR:", e)
    return jsonify({"results": []})


# --- REFERRAL FRIENDS / RENEWALS ---

@app.route('/get_referral_friends')
def get_referral_friends():
    if not session.get('logged_in'):
        return jsonify([]), 401
    ref = session.get('username')
    out = []
    try:
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute('''
                SELECT friend_username, friend_password, expiry_timestamp
                FROM referral_friends
                WHERE LOWER(referrer_username)=LOWER(?)
                ORDER BY created_at DESC
            ''', (ref.lower(),))
            rows = c.fetchall()
            now = int(time.time())
            for u, pw, exp_ts in rows:
                if exp_ts > 0:
                    readable = datetime.fromtimestamp(exp_ts).strftime('%B %d, %Y')
                    days_left = int((exp_ts - now) / 86400)
                else:
                    readable = "Unknown"
                    days_left = None
                out.append({
                    'friend_username': u,
                    'friend_password': pw,
                    'expiry_date': readable,
                    'days_left': days_left
                })
    except Exception as e:
        print("GET_REFERRAL_FRIENDS ERROR:", e)
    return jsonify(out)


@app.route('/renew_friend_line', methods=['POST'])
def renew_friend_line():
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
            c = conn.cursor()
            c.execute('''
                INSERT INTO payments (username, order_id, amount, status)
                VALUES (?,?,?, 'Completed')
            ''', (referrer, order_id, f"{amount_val:.2f}"))

            one_year = int(time.time()) + 365 * 86400
            c.execute("""
                UPDATE referral_friends
                SET expiry_timestamp = ?
                WHERE LOWER(friend_username)=LOWER(?)
            """, (one_year, friend_username.lower()))

            c.execute("""
                INSERT INTO referral_wallets (username, earned_balance, spent_balance)
                VALUES (?, ?, 0.0)
                ON CONFLICT(username) DO UPDATE SET
                    earned_balance = earned_balance + ?
            """, (referrer, FRIEND_RENEWAL_BONUS, FRIEND_RENEWAL_BONUS))

            conn.commit()

        readable = datetime.fromtimestamp(one_year).strftime('%B %d, %Y')
        send_telegram_alert_direct(
            f"<b>🔁 FRIEND LINE RENEWAL</b>\n"
            f"<b>Referrer:</b> <code>{referrer}</code>\n"
            f"<b>Friend Line:</b> <code>{friend_username}</code>\n"
            f"<b>Order ID:</b> <code>{order_id}</code>\n"
            f"<b>Paid:</b> £{amount_val:.2f}\n"
            f"<b>Wallet Used:</b> £{discount_val:.2f}\n"
            f"<b>New Local Expiry (Portal):</b> {readable}"
        )
        log_activity(referrer, f"Renewed friend line {friend_username} (order {order_id})")
        return jsonify({'success': True, 'message': f"Friend line '{friend_username}' renewed. Admin will extend it."})
    except Exception as e:
        print("RENEW_FRIEND_LINE ERROR:", e)
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/reassign_referral_friend', methods=['POST'])
def admin_reassign_referral_friend():
    if not is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    data = request.json or {}
    friend_username = (data.get('friend_username') or '').strip()
    new_referrer = (data.get('new_referrer') or '').strip()
    old_referrer = (data.get('old_referrer') or '').strip()
    if not friend_username or not new_referrer:
        return jsonify({'success': False, 'message': 'friend_username and new_referrer are required.'}), 400
    try:
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT username FROM portal_users WHERE LOWER(username)=LOWER(?)", (new_referrer.lower(),))
            if not c.fetchone():
                return jsonify({'success': False, 'message': f"New referrer '{new_referrer}' does not exist."}), 400
            c.execute("SELECT username FROM portal_users WHERE LOWER(username)=LOWER(?)", (friend_username.lower(),))
            if not c.fetchone():
                return jsonify({'success': False, 'message': f"Friend '{friend_username}' does not exist."}), 400

            c.execute("""
                SELECT id FROM referral_friends
                WHERE LOWER(friend_username)=LOWER(?)
            """, (friend_username.lower(),))
            rows = c.fetchall()

            if not rows:
                c.execute("""
                    INSERT INTO referral_friends (referrer_username, friend_username, friend_password, expiry_timestamp)
                    VALUES (?, ?, ?, 0)
                """, (new_referrer, friend_username, 'N/A'))
                conn.commit()
                log_activity(session.get('username', 'admin'),
                             f"Created referral_friends for {friend_username} under {new_referrer}")
                return jsonify({'success': True,
                                'message': f"No existing record; created link: '{friend_username}' now managed by '{new_referrer}'."})

            if old_referrer:
                c.execute("""
                    UPDATE referral_friends
                    SET referrer_username=?
                    WHERE LOWER(friend_username)=LOWER(?) AND LOWER(referrer_username)=LOWER(?)
                """, (new_referrer, friend_username.lower(), old_referrer.lower()))
            else:
                c.execute("""
                    UPDATE referral_friends
                    SET referrer_username=?
                    WHERE LOWER(friend_username)=LOWER(?)
                """, (new_referrer, friend_username.lower()))
            if c.rowcount == 0:
                return jsonify({'success': False,
                                'message': f"Friend '{friend_username}' has records but none under '{old_referrer}'."}), 404
            conn.commit()

        log_activity(session.get('username', 'admin'),
                     f"Reassigned friend '{friend_username}' to referrer '{new_referrer}'")
        return jsonify({'success': True,
                        'message': f"Friend '{friend_username}' is now managed by '{new_referrer}'."})
    except Exception as e:
        print("ADMIN REASSIGN ERROR:", e)
        return jsonify({'success': False, 'message': str(e)}), 500


# --- LOGOUT ---

@app.route('/logout')
def logout():
    uname = session.get('username')
    session.clear()
    if uname:
        log_activity(uname, "Logout")
    return redirect('/')


if __name__ == '__main__':
    app.run(debug=True, port=5000)
