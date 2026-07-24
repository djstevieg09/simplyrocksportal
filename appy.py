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
from cryptography.fernet import Fernet, InvalidToken

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
RESELLER_PANEL_URL = "http://simplyapple.xyz"

# Many Xtream panels reject requests that don't look like they're coming
# from a real player app (TiviMate, VLC, IPTV Smarters, etc.) as a basic
# anti-scraping measure. A plain Python request's default User-Agent gets
# silently blocked by some panels, so every Xtream API call this app makes
# (bulk syncs AND live per-user login checks) identifies as a generic
# mobile player app instead.
XTREAM_USER_AGENT = (
    'Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 '
    '(KHTML, like Gecko) TiviMate/4.7.0 Chrome/108.0.0.0 Mobile Safari/537.36'
)
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

# The PUBLIC client-id used by the PayPal JS SDK in the browser (safe to be
# visible - it's not a secret). Set PAYPAL_JS_CLIENT_ID to switch between
# your sandbox and live PayPal apps without editing any HTML - just change
# this one environment variable (and PAYPAL_API_BASE/PAYPAL_CLIENT_ID/
# PAYPAL_CLIENT_SECRET to match) and redeploy.
PAYPAL_JS_CLIENT_ID = os.environ.get(
    'PAYPAL_JS_CLIENT_ID',
    'ATdPR1St1opgGEMuPFAy_fB40wlVWHQROIw6QcFUzNETlUOORBD-dYxoQVr6I4xHfIqALFi28mBxfTJx'
)

# Simple in-memory token cache so we don't re-authenticate with PayPal on every request.
_paypal_token_cache = {"token": None, "expires_at": 0}

# --- SPOTIFY PASSWORD ENCRYPTION ---
# Spotify account passwords need to be retrievable (you have to actually log
# into the customer's Spotify account), so they can't be one-way hashed like
# portal login passwords. Instead they're encrypted at rest with a key that
# only your server knows, so they're not sitting in the database - or your
# admin panel - as plain readable text.
#
# Generate a key once with:
#   python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# then set it as the SPOTIFY_ENCRYPTION_KEY environment variable. Do NOT
# change this value later or existing encrypted passwords won't decrypt.
SPOTIFY_ENCRYPTION_KEY = os.environ.get('SPOTIFY_ENCRYPTION_KEY')
_spotify_fernet = None
if SPOTIFY_ENCRYPTION_KEY:
    try:
        _spotify_fernet = Fernet(SPOTIFY_ENCRYPTION_KEY.encode())
    except Exception as e:
        print(f"SPOTIFY_ENCRYPTION_KEY is set but invalid: {e}", flush=True)
        _spotify_fernet = None
else:
    print("SECURITY WARNING: SPOTIFY_ENCRYPTION_KEY env var is not set. Spotify "
          "passwords will be stored in PLAIN TEXT until you set this. Generate "
          "one with: python3 -c \"from cryptography.fernet import Fernet; "
          "print(Fernet.generate_key().decode())\"", flush=True)


def encrypt_spotify_password(plain_text):
    """Encrypt a Spotify password before storing it. Falls back to storing
    plain text (with a warning already printed at startup) if no key is set,
    so the app still works while you're getting the key configured."""
    if not _spotify_fernet:
        return plain_text
    return _spotify_fernet.encrypt(plain_text.encode()).decode()


def decrypt_spotify_password(stored_value):
    """Decrypt a stored Spotify password for admin viewing."""
    if not _spotify_fernet:
        return stored_value
    try:
        return _spotify_fernet.decrypt(stored_value.encode()).decode()
    except (InvalidToken, ValueError):
        # Value was stored before encryption was enabled, or the key changed.
        return stored_value


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

        # vod_library table - a manually-maintained catalog of movies/shows
        # already available on the IPTV panel. Since there's no API access
        # to the reseller panel, this list is built by the admin (bulk
        # pasting titles) and used to flag "already available" matches
        # when someone searches to submit a request.
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS vod_library (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                normalized_title TEXT NOT NULL,
                media_type TEXT NOT NULL,
                year TEXT,
                added_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # renewal_jobs table - every line renewal (self or a referred
        # friend's line) creates a job here that the admin must manually
        # accept, since the actual line extension has to be done by hand on
        # the real IPTV reseller panel. Accepting a job adds 365 days to
        # whatever the account's expiry already was (matching how the panel
        # itself extends a renewed line), rather than 365 days from today.
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS renewal_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                renewal_type TEXT NOT NULL,
                referrer_username TEXT,
                connections TEXT,
                order_id TEXT,
                amount TEXT,
                status TEXT DEFAULT 'Pending',
                previous_expiry_date TEXT,
                new_expiry_date TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                completed_at DATETIME
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

        # Migration: allow requests to specify a particular season/episode of
        # a TV show, instead of only ever requesting the whole series.
        try:
            cursor.execute("ALTER TABLE requests ADD COLUMN season_number INTEGER")
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                print(f"DATABASE UPDATE NOTICE: {e}")
        try:
            cursor.execute("ALTER TABLE requests ADD COLUMN episode_number INTEGER")
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                print(f"DATABASE UPDATE NOTICE: {e}")

        # Same season/episode granularity for VOD fault reports, so people
        # can report an issue with one specific episode instead of only
        # ever reporting against the whole show.
        try:
            cursor.execute("ALTER TABLE vod_reports ADD COLUMN season_number INTEGER")
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                print(f"DATABASE UPDATE NOTICE: {e}")
        try:
            cursor.execute("ALTER TABLE vod_reports ADD COLUMN episode_number INTEGER")
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

        # Unique index on vod_library so importing the same title twice
        # (e.g. re-pasting a list) doesn't create duplicate catalog rows.
        try:
            cursor.execute('''
                CREATE UNIQUE INDEX IF NOT EXISTS idx_vod_library_unique
                ON vod_library (normalized_title, media_type)
            ''')
        except sqlite3.OperationalError as e:
            print(f"VOD LIBRARY INDEX NOTICE: {e}")

        conn.commit()


# NOTE: the static UK channel seed list has been removed. Live channels are
# now pulled directly from the real IPTV panel via the "Sync Live Channels
# From Panel" button in the admin panel, the same way movies/series are.

# Trigger DB init
init_db()
NOTIFICATION_QUEUE = Queue()
CACHED_CHANNELS = []


def is_admin():
    """
    Central admin check, using session and environment-based master username.
    NOTE: there is intentionally NO hardcoded fallback username anymore. If
    PORTAL_ADMIN_USER is not set in your environment, nobody can access admin
    routes via username-matching (the is_admin session flag from a genuine
    admin login still works as normal).
    """
    if not session.get('logged_in'):
        return False
    if session.get('is_admin'):
        return True
    secure_admin_username = os.environ.get('PORTAL_ADMIN_USER')
    if not secure_admin_username:
        return False
    current_user = str(session.get('username', '')).lower()
    return current_user == secure_admin_username.lower()


def normalize_title(title):
    """
    Reduce a title down to just lowercase letters/numbers so that small
    differences in punctuation/spacing/formatting ("Spider-Man" vs
    "Spiderman" vs "spider man") still match against the VOD library.
    """
    return re.sub(r'[^a-z0-9]', '', (title or '').lower())


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
    Authenticate a customer DIRECTLY against the real IPTV panel - the exact
    same check TiviMate/IPTV Smarters do when you type in your DNS +
    username + password. This uses the person's OWN credentials (not the
    reseller admin login), so it only succeeds if they genuinely have a
    real, active line on the panel.

    On success, the local portal_users record is automatically created (if
    it doesn't exist) or refreshed (if it does) via upsert_portal_user_from_panel(),
    so someone with a real line can just log in and "appear" in the portal
    without needing to be manually added first - but without real DNS
    access, no local account is ever created or updated at all.
    """
    dns_base = (dns or DEFAULT_DNS or '').strip()
    if not dns_base:
        print("VERIFY_XTREAM_CREDENTIALS ERROR: no DNS configured to check against.")
        return False, None

    try:
        url = f"{dns_base.rstrip('/')}/player_api.php"
        resp = requests.get(
            url,
            params={'username': username.strip(), 'password': password.strip()},
            headers={'User-Agent': XTREAM_USER_AGENT},
            timeout=15
        )
    except requests.exceptions.RequestException:
        print("VERIFY_XTREAM_CREDENTIALS ERROR: could not reach the panel.")
        return False, None

    if resp.status_code != 200:
        print(f"VERIFY_XTREAM_CREDENTIALS: panel returned HTTP {resp.status_code}.")
        return False, None

    try:
        data = resp.json()
    except ValueError:
        print("VERIFY_XTREAM_CREDENTIALS ERROR: panel response wasn't valid JSON.")
        return False, None

    user_info = data.get('user_info') or {}
    auth_ok = user_info.get('auth') == 1
    status_ok = str(user_info.get('status') or '').strip().lower() == 'active'

    if not (auth_ok and status_ok):
        return False, None

    # Real, active line confirmed by the panel itself - auto-provision the
    # local portal_users record so the rest of the portal's features
    # (wallet, referrals, requests, admin visibility) work for this user.
    upsert_portal_user_from_panel(username.strip(), password.strip(), user_info)

    return True, user_info


def upsert_portal_user_from_panel(username, password, user_info):
    """
    Called only after a successful LIVE panel authentication. Creates the
    local portal_users record on someone's first-ever login, or refreshes
    it on subsequent logins - keeping their expiry date in sync with
    whatever the real panel says, automatically, every time they log in.
    """
    raw_exp = user_info.get('exp_date')
    exp_ts = 0
    if raw_exp is not None and str(raw_exp).strip().lower() not in ('', 'null', '0', 'none', 'false'):
        try:
            candidate = int(raw_exp)
            if candidate >= 100000000:
                exp_ts = candidate
        except (TypeError, ValueError):
            pass

    expiry_date_str = datetime.fromtimestamp(exp_ts).strftime('%Y-%m-%d') if exp_ts > 0 else 'Unlimited'
    hashed = generate_password_hash(password)

    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO portal_users (username, password, expiry_date, expiry_timestamp)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(username) DO UPDATE SET
                    password = excluded.password,
                    expiry_date = excluded.expiry_date,
                    expiry_timestamp = excluded.expiry_timestamp
            ''', (username, hashed, expiry_date_str, exp_ts))
            conn.commit()
    except Exception as e:
        print("UPSERT_PORTAL_USER_FROM_PANEL ERROR:", e)


# --- XTREAM CODES API (REAL RESELLER PANEL INTEGRATION) ---
# This is the same API that apps like TiviMate/IPTV Smarters use when you
# type in your DNS + username + password - it's a standard format almost
# every IPTV reseller panel speaks, reached via player_api.php. We use the
# RESELLER_USERNAME/RESELLER_PASSWORD credentials (any working line's
# login works) to pull the real VOD movie list and series list.

def fetch_xtream_api(action, extra_params=None, timeout=60):
    """
    Call the Xtream Codes-compatible reseller panel API and return the
    parsed JSON response. Raises an exception on failure - callers should
    catch and report a friendly error.

    IMPORTANT: this deliberately never lets the username/password reach an
    exception message, a log line, or anything else that could get printed
    or stored - only the action name and HTTP status code are ever surfaced.
    """
    if not RESELLER_PANEL_URL or not RESELLER_USERNAME or not RESELLER_PASSWORD:
        raise RuntimeError(
            "Reseller panel isn't configured. Set RESELLER_USER and RESELLER_PASS "
            "environment variables (RESELLER_PANEL_URL is already set in the code)."
        )

    url = f"{RESELLER_PANEL_URL.rstrip('/')}/player_api.php"
    params = {
        'username': RESELLER_USERNAME,
        'password': RESELLER_PASSWORD,
        'action': action
    }
    if extra_params:
        params.update(extra_params)

    headers = {'User-Agent': XTREAM_USER_AGENT}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=timeout)
    except requests.exceptions.RequestException:
        # Re-raise as a clean error with no URL/credentials attached.
        raise RuntimeError(f"Could not connect to the IPTV panel for action '{action}'.") from None

    if resp.status_code != 200:
        # Deliberately does NOT include resp.url (which contains the
        # username/password as query params) anywhere in this message.
        raise RuntimeError(
            f"IPTV panel returned HTTP {resp.status_code} for action '{action}'. "
            f"This usually means the username/password isn't a valid line login, "
            f"or the panel doesn't support this API action."
        )

    return resp.json()


def parse_xtream_title(raw_name):
    """
    Xtream panel entries are often messy - things like
    "Gladiator (2000) [4K]" or "Breaking Bad HEVC MULTI". This does a
    best-effort cleanup to pull out a clean title and, if present, a year.
    It won't be perfect for every naming convention your provider uses, but
    combined with normalize_title()'s punctuation-stripping when matching,
    it catches the vast majority of real-world cases.
    """
    name = (raw_name or '').strip()

    # Strip common bracketed quality/language/codec tags.
    name = re.sub(
        r'\s*[\[\(](?:4K|UHD|FHD|HD|SD|HDR|HEVC|MULTI[- ]?AUDIO|DUAL[- ]?AUDIO|VOSTFR|SUBBED|SUBS?)[\]\)]\s*',
        ' ', name, flags=re.IGNORECASE
    )

    year = None
    # Trailing "(YYYY)" is the cleanest signal.
    match = re.search(r'\((\d{4})\)\s*$', name)
    if match:
        year = match.group(1)
        name = name[:match.start()].strip()
    else:
        # Fall back to a bare trailing 19xx/20xx year with no brackets.
        match2 = re.search(r'\b(19|20)\d{2}\b\s*$', name)
        if match2:
            year = match2.group(0)
            name = name[:match2.start()].strip()

    name = re.sub(r'\s+', ' ', name).strip(' -_')
    return name, year


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


# --- RENEWAL JOBS: MANUAL LINE EXTENSION QUEUE ---
# Every paid line renewal (a user's own line, or a referred friend's line)
# creates a job here. The actual extension has to happen on the real IPTV
# panel by hand, so this queue is what the admin works through - accepting
# a job adds 365 days to whatever the account's expiry already was, exactly
# matching how the real panel extends a renewed line.

def create_renewal_job(username, renewal_type, connections, order_id, amount, referrer_username=None):
    """Insert a new pending renewal job for the admin to accept."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO renewal_jobs (username, renewal_type, referrer_username, connections, order_id, amount, status)
                VALUES (?, ?, ?, ?, ?, ?, 'Pending')
            ''', (username, renewal_type, referrer_username, connections, order_id, amount))
            conn.commit()
    except Exception as e:
        print("CREATE_RENEWAL_JOB ERROR:", e)


def accept_renewal_job(job_id):
    """
    Accept a pending renewal job: add 365 days to the account's PREVIOUS
    expiry (not from today), update portal_users, mirror the new expiry
    into referral_friends if this was a friend renewal, and mark the job
    Completed. Returns (success, message_or_data).
    """
    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM renewal_jobs WHERE id = ?", (job_id,))
        job = cursor.fetchone()
        if not job:
            return False, "Renewal job not found."
        if job['status'] == 'Completed':
            return False, "This renewal job has already been completed."

        username = job['username']

        cursor.execute(
            "SELECT expiry_timestamp FROM portal_users WHERE LOWER(username) = LOWER(?)",
            (username.lower(),)
        )
        user_row = cursor.fetchone()
        if not user_row:
            return False, f"Portal account '{username}' not found - can't extend its expiry."

        previous_ts = user_row['expiry_timestamp'] or 0
        previous_readable = datetime.fromtimestamp(previous_ts).strftime('%Y-%m-%d') if previous_ts > 0 else 'None'

        # Add 365 days to whatever the expiry already was, matching how the
        # real panel extends a line. If there's no valid prior expiry to
        # build from (brand new/blank account), fall back to extending from
        # today instead of adding 365 days to a meaningless zero value.
        base_ts = previous_ts if previous_ts > 0 else int(time.time())
        new_ts = base_ts + (365 * 86400)
        new_readable = datetime.fromtimestamp(new_ts).strftime('%Y-%m-%d')

        cursor.execute('''
            UPDATE portal_users
            SET expiry_date = ?, expiry_timestamp = ?
            WHERE LOWER(username) = LOWER(?)
        ''', (new_readable, new_ts, username.lower()))

        # Keep the referral_friends tracking table in sync for friend renewals,
        # since that's what the "Friends You Referred" dashboard list reads from.
        if job['renewal_type'] == 'friend':
            cursor.execute('''
                UPDATE referral_friends
                SET expiry_timestamp = ?
                WHERE LOWER(friend_username) = LOWER(?)
            ''', (new_ts, username.lower()))

        cursor.execute('''
            UPDATE renewal_jobs
            SET status = 'Completed',
                previous_expiry_date = ?,
                new_expiry_date = ?,
                completed_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (previous_readable, new_readable, job_id))

        conn.commit()

    return True, {
        'username': username,
        'previous_expiry_date': previous_readable,
        'new_expiry_date': new_readable
    }


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
        referral_history=referral_history,
        paypal_client_id=PAYPAL_JS_CLIENT_ID
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

        if response.status_code != 200:
            print(f"TMDB ERROR code {response.status_code}")
            return jsonify({"results": []})

        data = response.json()

        # Flag each result as already_available if it matches something in
        # the manually-maintained vod_library catalog. This is the only way
        # to know what's "already on the system" since there's no API access
        # to the actual IPTV reseller panel.
        try:
            with sqlite3.connect(DB_FILE) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT normalized_title, media_type FROM vod_library")
                library_rows = cursor.fetchall()
            movie_titles = {r['normalized_title'] for r in library_rows if r['media_type'] == 'movie'}
            tv_titles = {r['normalized_title'] for r in library_rows if r['media_type'] == 'tv'}
        except Exception as e:
            print("SEARCH_MEDIA VOD LIBRARY LOOKUP ERROR:", e)
            movie_titles, tv_titles = set(), set()

        for item in data.get('results', []):
            media_type = item.get('media_type')
            if media_type not in ('movie', 'tv'):
                item['already_available'] = False
                continue
            display_title = item.get('title') if media_type == 'movie' else item.get('name')
            norm = normalize_title(display_title)
            lookup_set = movie_titles if media_type == 'movie' else tv_titles
            item['already_available'] = norm in lookup_set

        return jsonify(data)
    except Exception as e:
        print(f"TMDB EXCEPTION: {e}")
        return jsonify({"results": []})


@app.route('/get_tv_seasons')
def get_tv_seasons():
    """
    Return only the seasons of a TV show that have actually aired, so people
    can't request a season that hasn't come out yet.
    Expects ?tmdb_id=TMDB-<id> (the same imdbID format used elsewhere) or a
    plain numeric TMDB id.
    """
    if not session.get('logged_in'):
        return jsonify({'seasons': []}), 401

    raw_id = (request.args.get('tmdb_id') or '').strip()
    tv_id = raw_id.replace('TMDB-', '').strip()
    if not tv_id.isdigit():
        return jsonify({'seasons': []}), 400

    try:
        url = f"https://api.themoviedb.org/3/tv/{tv_id}"
        resp = requests.get(url, params={
            'api_key': TMDB_API_KEY,
            'language': 'en-US'
        }, timeout=6)

        if resp.status_code != 200:
            print("GET_TV_SEASONS TMDB ERROR:", resp.status_code)
            return jsonify({'seasons': []})

        data = resp.json()
        today_str = datetime.now().strftime('%Y-%m-%d')

        released_seasons = []
        for s in data.get('seasons', []):
            air_date = s.get('air_date')
            # Only include seasons that have an air date AND that date has
            # already happened - unreleased/upcoming seasons are excluded.
            if air_date and air_date <= today_str:
                released_seasons.append({
                    'season_number': s.get('season_number'),
                    'name': s.get('name') or f"Season {s.get('season_number')}",
                    'episode_count': s.get('episode_count'),
                    'air_date': air_date
                })

        released_seasons.sort(key=lambda x: x['season_number'])
        return jsonify({'seasons': released_seasons})
    except Exception as e:
        print("GET_TV_SEASONS EXCEPTION:", e)
        return jsonify({'seasons': []})


@app.route('/get_tv_season_episodes')
def get_tv_season_episodes():
    """
    Return only the episodes of a specific season that have actually aired,
    so people can't request an episode that hasn't come out yet.
    Expects ?tmdb_id=TMDB-<id>&season_number=<n>
    """
    if not session.get('logged_in'):
        return jsonify({'episodes': []}), 401

    raw_id = (request.args.get('tmdb_id') or '').strip()
    season_number = (request.args.get('season_number') or '').strip()
    tv_id = raw_id.replace('TMDB-', '').strip()

    if not tv_id.isdigit() or not season_number.isdigit():
        return jsonify({'episodes': []}), 400

    try:
        url = f"https://api.themoviedb.org/3/tv/{tv_id}/season/{season_number}"
        resp = requests.get(url, params={
            'api_key': TMDB_API_KEY,
            'language': 'en-US'
        }, timeout=6)

        if resp.status_code != 200:
            print("GET_TV_SEASON_EPISODES TMDB ERROR:", resp.status_code)
            return jsonify({'episodes': []})

        data = resp.json()
        today_str = datetime.now().strftime('%Y-%m-%d')

        released_episodes = []
        for ep in data.get('episodes', []):
            air_date = ep.get('air_date')
            if air_date and air_date <= today_str:
                released_episodes.append({
                    'episode_number': ep.get('episode_number'),
                    'name': ep.get('name') or f"Episode {ep.get('episode_number')}",
                    'air_date': air_date
                })

        released_episodes.sort(key=lambda x: x['episode_number'])
        return jsonify({'episodes': released_episodes})
    except Exception as e:
        print("GET_TV_SEASON_EPISODES EXCEPTION:", e)
        return jsonify({'episodes': []})


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

    # Optional: a specific season and/or episode of a TV show. Both are
    # None/blank for movies and for "whole series" TV requests.
    def _parse_int(value):
        try:
            if value in (None, '', 'null'):
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    season_number = _parse_int(data.get('season_number'))
    episode_number = _parse_int(data.get('episode_number'))

    if not title:
        return jsonify({'success': False, 'message': 'Missing title'}), 400

    # Build a human-readable scope suffix for logs/alerts, e.g.
    # " - Season 2, Episode 5" or " - Season 3 (entire season)".
    scope_label = ""
    if season_number and episode_number:
        scope_label = f" - Season {season_number}, Episode {episode_number}"
    elif season_number:
        scope_label = f" - Season {season_number} (entire season)"

    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO requests (username, title, year, media_type, imdb_id, poster, season_number, episode_number)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (username, title, year, media_type, imdb_id, poster, season_number, episode_number))
            conn.commit()

        send_telegram_alert_direct(
            f"<b>🎞 NEW MEDIA REQUEST</b>\n"
            f"<b>User:</b> <code>{username}</code>\n"
            f"<b>Title:</b> {title} {f'({year})' if year else ''}{scope_label}\n"
            f"<b>Type:</b> {media_type.upper()}\n"
            f"<b>ID:</b> <code>{imdb_id or 'N/A'}</code>"
        )

        log_activity(username, f"Submitted media request: {title} [{media_type}] {year}{scope_label}")
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

            # NOTE: the friend's actual expiry is NOT extended here anymore.
            # It used to be bumped immediately in this table, but that never
            # touched the friend's real portal_users record - meaning their
            # account expiry was never actually extended at all. The real
            # extension now only happens once the admin accepts the renewal
            # job below, via accept_renewal_job().

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

        # Create the job the admin will accept to actually extend the
        # friend's line on the real panel (see accept_renewal_job()).
        create_renewal_job(
            username=friend_username,
            renewal_type='friend',
            connections=connections,
            order_id=order_id,
            amount=f"{amount_val:.2f}",
            referrer_username=referrer
        )

        send_telegram_alert_direct(
            f"<b>🔁 FRIEND LINE RENEWAL PAID</b>\n"
            f"<b>Referrer:</b> <code>{referrer}</code>\n"
            f"<b>Friend Line:</b> <code>{friend_username}</code>\n"
            f"<b>Order ID:</b> <code>{order_id}</code>\n"
            f"<b>Paid:</b> £{amount_val:.2f}\n"
            f"<b>Wallet Used:</b> £{discount_val:.2f}\n"
            f"<b>Connections:</b> {connections}\n"
            f"<b>Status:</b> Pending manual extension in admin panel"
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

        # Create the job the admin will accept to actually extend this
        # account's expiry on the real panel (see accept_renewal_job()).
        create_renewal_job(
            username=username,
            renewal_type='self',
            connections=connections,
            order_id=order_id,
            amount=f"{amount_val:.2f}"
        )

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
        encrypted_sp = encrypt_spotify_password(sp)

        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO spotify_orders (
                    portal_username, spotify_username, spotify_password,
                    amount, discount_used, status
                )
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                portal_user, su, encrypted_sp,
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
    Use TMDB to search movies & TV for VOD reporting dropdown - but unlike
    the media request search, this ONLY returns titles that are actually on
    the system (matched against the vod_library catalog). There's no point
    letting someone file a fault report against something that was never
    added to the panel in the first place.
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

        data = resp.json()

        try:
            with sqlite3.connect(DB_FILE) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT normalized_title, media_type FROM vod_library")
                library_rows = cursor.fetchall()
            movie_titles = {r['normalized_title'] for r in library_rows if r['media_type'] == 'movie'}
            tv_titles = {r['normalized_title'] for r in library_rows if r['media_type'] == 'tv'}
        except Exception as e:
            print("SEARCH_VOD_CATALOG VOD LIBRARY LOOKUP ERROR:", e)
            movie_titles, tv_titles = set(), set()

        filtered_results = []
        for item in data.get('results', []):
            media_type = item.get('media_type')
            if media_type not in ('movie', 'tv'):
                continue
            display_title = item.get('title') if media_type == 'movie' else item.get('name')
            norm = normalize_title(display_title)
            lookup_set = movie_titles if media_type == 'movie' else tv_titles
            if norm in lookup_set:
                filtered_results.append(item)

        return jsonify({"results": filtered_results})
    except Exception as e:
        print("TMDB VOD SEARCH EXCEPTION:", e)
        return jsonify({"results": []})


@app.route('/submit_vod_report', methods=['POST'])
def submit_vod_report():
    """
    User: submit VOD fault ticket.
    Expects JSON:
      title, media_type ('movie'|'tv'), issue_type, issue_notes (optional),
      season_number (optional), episode_number (optional)
    """
    if not session.get('logged_in'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    data = request.json or {}
    username = session.get('username')
    title = (data.get('title') or '').strip()
    media_type = (data.get('media_type') or '').strip()
    issue_type = (data.get('issue_type') or '').strip()
    issue_notes = (data.get('issue_notes') or '').strip()

    def _parse_int(value):
        try:
            if value in (None, '', 'null'):
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    season_number = _parse_int(data.get('season_number'))
    episode_number = _parse_int(data.get('episode_number'))

    if not title or not media_type or not issue_type:
        return jsonify({'success': False, 'message': 'Missing title, type or issue.'}), 400

    final_issue_type = issue_type
    if issue_type.lower() == 'other' and issue_notes:
        final_issue_type = f"Other: {issue_notes[:100]}"

    scope_label = ""
    if season_number and episode_number:
        scope_label = f" - Season {season_number}, Episode {episode_number}"
    elif season_number:
        scope_label = f" - Season {season_number} (entire season)"

    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO vod_reports (username, title, media_type, issue_type, issue_notes, season_number, episode_number)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (username, title, media_type, final_issue_type, issue_notes[:255], season_number, episode_number))
            conn.commit()

        send_telegram_alert_direct(
            f"<b>🎬 VOD FAULT TICKET</b>\n"
            f"<b>User:</b> <code>{username}</code>\n"
            f"<b>Title:</b> {title}{scope_label}\n"
            f"<b>Type:</b> {media_type.upper()}\n"
            f"<b>Issue:</b> {final_issue_type}"
        )

        log_activity(username, f"VOD fault report: {title} ({media_type}) - {final_issue_type}")

        return jsonify({'success': True, 'message': 'VOD fault ticket logged.'})
    except Exception as e:
        print("SUBMIT_VOD_REPORT ERROR:", e)
        return jsonify({'success': False, 'message': str(e)}), 500


# --- ADMIN PANEL & HELPERS ---

def build_client_expiration_list(max_days=31):
    """
    Build the list of portal users expiring within `max_days` days, sourced
    directly from portal_users (the authoritative table for account expiry).
    We previously read this from user_metadata, but that table is only ever
    populated when a user logs in themselves - so any account created
    directly by an admin (via Create Portal User) that hasn't logged in yet
    would silently never show up here. Reading portal_users directly fixes
    that and makes this the real source of truth for both the initial page
    load and the "Sync" button.
    """
    secure_admin_username = (os.environ.get('PORTAL_ADMIN_USER') or '').lower()
    current_timestamp = int(time.time())
    client_expiration_list = []

    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT username, expiry_date, expiry_timestamp FROM portal_users")
        all_users = cursor.fetchall()

    for user in all_users:
        uname = user['username']
        exp_timestamp = user['expiry_timestamp'] or 0
        readable_date = user['expiry_date']

        if not uname:
            continue
        if secure_admin_username and uname.lower() == secure_admin_username:
            continue
        if exp_timestamp <= 0:
            continue

        days_left = int((exp_timestamp - current_timestamp) / 86400)
        if days_left <= max_days:
            client_expiration_list.append({
                'username': uname,
                'expiry_date': readable_date,
                'days_remaining': days_left,
                'status': 'Expired' if days_left < 0 else 'Active'
            })

    client_expiration_list.sort(key=lambda x: x['days_remaining'])
    return client_expiration_list


@app.route('/admin')
def admin_panel():
    if not is_admin():
        return "<h3>Access Denied</h3>", 403

    client_expiration_list = build_client_expiration_list()

    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM requests ORDER BY timestamp DESC")
        all_requests = cursor.fetchall()

        cursor.execute("SELECT * FROM payments ORDER BY timestamp DESC")
        all_payments = cursor.fetchall()

        cursor.execute("SELECT * FROM channel_reports ORDER BY timestamp DESC")
        all_reports = cursor.fetchall()

        cursor.execute("SELECT id, username, title, media_type, issue_type, season_number, episode_number FROM vod_reports ORDER BY timestamp DESC")
        all_vod_reports = cursor.fetchall()

        cursor.execute("SELECT username, (earned_balance - spent_balance) AS active_credit FROM referral_wallets WHERE (earned_balance - spent_balance) > 0 ORDER BY active_credit DESC")
        all_wallets = cursor.fetchall()

        cursor.execute("SELECT * FROM portal_users ORDER BY created_at DESC")
        all_portal_users = cursor.fetchall()

        cursor.execute("SELECT * FROM live_channels ORDER BY name ASC")
        all_live_channels = cursor.fetchall()

        cursor.execute("SELECT id, title, media_type, year, added_at FROM vod_library ORDER BY added_at DESC LIMIT 200")
        all_vod_library = cursor.fetchall()

        cursor.execute("SELECT COUNT(*) FROM vod_library")
        vod_library_count = cursor.fetchone()[0]

        cursor.execute("""
            SELECT * FROM renewal_jobs
            WHERE status = 'Pending'
            ORDER BY created_at ASC
        """)
        pending_renewal_jobs = cursor.fetchall()

        cursor.execute("""
            SELECT * FROM renewal_jobs
            WHERE status = 'Completed'
            ORDER BY completed_at DESC
            LIMIT 25
        """)
        recent_completed_renewal_jobs = cursor.fetchall()

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
        vod_library=all_vod_library,
        vod_library_count=vod_library_count,
        pending_renewal_jobs=pending_renewal_jobs,
        recent_completed_renewal_jobs=recent_completed_renewal_jobs,
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
    """
    Recalculate the client expiration matrix directly from portal_users (the
    real source of truth for expiry dates) and return it fresh.

    NOTE: this does NOT call your actual external IPTV reseller panel -
    RESELLER_PANEL_URL / RESELLER_USERNAME / RESELLER_PASSWORD are still
    unused, since that reseller panel's API isn't something this app has
    access to or details about. What this DOES do is guarantee the matrix
    you see always reflects the current, real portal_users table rather
    than a potentially stale/missing cache - so pressing "Sync" always
    gives you an accurate, up-to-the-second list of who's expiring soon.
    """
    if not is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    try:
        client_expiration_list = build_client_expiration_list()
        return jsonify({
            'success': True,
            'message': f"Refreshed - {len(client_expiration_list)} client(s) expiring within 31 days.",
            'clients': client_expiration_list
        })
    except Exception as e:
        print("SYNC_LIVE_PANEL_EXPIRATIONS ERROR:", e)
        return jsonify({'success': False, 'message': str(e)}), 500


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


# --- VOD LIBRARY: MANUALLY-MAINTAINED "ALREADY ON THE SYSTEM" CATALOG ---
# There's no API access to the actual IPTV reseller panel, so this catalog
# is built by the admin (pasting in titles that are already available) and
# used to flag matches when users search to submit a request.

@app.route('/admin/search_vod_library')
def admin_search_vod_library():
    """Search the local VOD library catalog - used by the admin panel to
    check whether something is already on the system."""
    if not is_admin():
        return jsonify([]), 403

    q = (request.args.get('q') or '').strip()

    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if q:
                like = f"%{q}%"
                cursor.execute("""
                    SELECT id, title, media_type, year, added_at
                    FROM vod_library
                    WHERE title LIKE ?
                    ORDER BY title ASC
                    LIMIT 200
                """, (like,))
            else:
                cursor.execute("""
                    SELECT id, title, media_type, year, added_at
                    FROM vod_library
                    ORDER BY added_at DESC
                    LIMIT 200
                """)
            rows = cursor.fetchall()
        return jsonify([dict(r) for r in rows])
    except Exception as e:
        print("ADMIN_SEARCH_VOD_LIBRARY ERROR:", e)
        return jsonify([]), 500


@app.route('/admin/import_vod_library', methods=['POST'])
def admin_import_vod_library():
    """
    Bulk-import a pasted list of titles into the VOD library.
    Expects JSON: { "media_type": "movie"|"tv", "titles_text": "one title per line" }
    Lines can optionally end with a year in parentheses, e.g. "Gladiator (2000)"
    - the year is parsed out and stored separately, but matching is by title only.
    """
    if not is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    data = request.json or {}
    media_type = (data.get('media_type') or '').strip().lower()
    titles_text = data.get('titles_text') or ''

    if media_type not in ('movie', 'tv'):
        return jsonify({'success': False, 'message': "media_type must be 'movie' or 'tv'."}), 400

    lines = [line.strip() for line in titles_text.splitlines() if line.strip()]
    if not lines:
        return jsonify({'success': False, 'message': 'No titles provided.'}), 400

    year_pattern = re.compile(r'^(.*?)\s*\((\d{4})\)\s*$')

    added = 0
    skipped_duplicates = 0

    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            for line in lines:
                match = year_pattern.match(line)
                if match:
                    title = match.group(1).strip()
                    year = match.group(2).strip()
                else:
                    title = line
                    year = None

                if not title:
                    continue

                norm = normalize_title(title)

                cursor.execute(
                    "SELECT id FROM vod_library WHERE normalized_title = ? AND media_type = ?",
                    (norm, media_type)
                )
                already_existed = cursor.fetchone() is not None

                cursor.execute('''
                    INSERT INTO vod_library (title, normalized_title, media_type, year)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(normalized_title, media_type) DO UPDATE SET
                        title = excluded.title,
                        year = excluded.year
                ''', (title, norm, media_type, year))

                if already_existed:
                    skipped_duplicates += 1
                else:
                    added += 1

            conn.commit()

        admin_user = session.get('username', 'admin')
        log_activity(admin_user, f"Imported {added} new VOD library entries, updated {skipped_duplicates} existing ({media_type})")

        return jsonify({
            'success': True,
            'message': f"Imported {len(lines)} line(s): {added} new, {skipped_duplicates} already existed (refreshed)."
        })
    except Exception as e:
        print("ADMIN_IMPORT_VOD_LIBRARY ERROR:", e)
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/delete_vod_library_entry/<int:entry_id>', methods=['POST'])
def admin_delete_vod_library_entry(entry_id):
    if not is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM vod_library WHERE id = ?', (entry_id,))
            if cursor.rowcount == 0:
                return jsonify({'success': False, 'message': 'Entry not found.'}), 404
            conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        print("ADMIN_DELETE_VOD_LIBRARY_ENTRY ERROR:", e)
        return jsonify({'success': False, 'message': str(e)}), 500


def perform_vod_library_sync():
    """
    Core VOD library sync logic - pulls movies + series from the real panel
    and refreshes the vod_library catalog. Has no Flask/session dependency
    so it can be called both from the admin "Sync" button and from the
    automatic background sync task. Returns a stats dict. Raises RuntimeError
    or requests exceptions on failure - callers handle those.
    """
    movies_added = 0
    movies_updated = 0
    series_added = 0
    series_updated = 0

    # --- Movies (VOD) ---
    vod_streams = fetch_xtream_api('get_vod_streams')
    if isinstance(vod_streams, list):
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            for item in vod_streams:
                raw_name = (item.get('name') or '').strip()
                if not raw_name:
                    continue
                title, year = parse_xtream_title(raw_name)
                if not title:
                    continue
                norm = normalize_title(title)

                cursor.execute(
                    "SELECT id FROM vod_library WHERE normalized_title = ? AND media_type = 'movie'",
                    (norm,)
                )
                existed = cursor.fetchone() is not None

                cursor.execute('''
                    INSERT INTO vod_library (title, normalized_title, media_type, year)
                    VALUES (?, ?, 'movie', ?)
                    ON CONFLICT(normalized_title, media_type) DO UPDATE SET
                        title = excluded.title,
                        year = excluded.year
                ''', (title, norm, year))

                if existed:
                    movies_updated += 1
                else:
                    movies_added += 1
            conn.commit()

    # --- Series ---
    series_list = fetch_xtream_api('get_series')
    if isinstance(series_list, list):
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            for item in series_list:
                raw_name = (item.get('name') or '').strip()
                if not raw_name:
                    continue
                title, year = parse_xtream_title(raw_name)
                if not title:
                    continue
                norm = normalize_title(title)

                cursor.execute(
                    "SELECT id FROM vod_library WHERE normalized_title = ? AND media_type = 'tv'",
                    (norm,)
                )
                existed = cursor.fetchone() is not None

                cursor.execute('''
                    INSERT INTO vod_library (title, normalized_title, media_type, year)
                    VALUES (?, ?, 'tv', ?)
                    ON CONFLICT(normalized_title, media_type) DO UPDATE SET
                        title = excluded.title,
                        year = excluded.year
                ''', (title, norm, year))

                if existed:
                    series_updated += 1
                else:
                    series_added += 1
            conn.commit()

    return {
        'movies_added': movies_added,
        'movies_updated': movies_updated,
        'series_added': series_added,
        'series_updated': series_updated,
    }


def perform_live_channels_sync():
    """
    Core live channels sync logic - fully replaces live_channels with the
    real list from the panel. No Flask/session dependency, so this can be
    called both from the admin "Sync" button and the automatic background
    sync task. Returns a stats dict. Raises RuntimeError if the panel
    returns nothing (so a failed call can't wipe the existing list).
    """
    live_streams = fetch_xtream_api('get_live_streams')

    if not isinstance(live_streams, list) or not live_streams:
        raise RuntimeError("Panel returned no live channels - nothing was changed.")

    channel_count = 0
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM live_channels")

        for item in live_streams:
            name = (item.get('name') or '').strip()
            raw_stream_id = item.get('stream_id')
            if not name or raw_stream_id is None:
                continue

            cursor.execute('''
                INSERT INTO live_channels (stream_id, name)
                VALUES (?, ?)
                ON CONFLICT(stream_id) DO UPDATE SET name = excluded.name
            ''', (str(raw_stream_id), name))
            channel_count += 1

        conn.commit()

    return {'channel_count': channel_count}


@app.route('/admin/sync_vod_library_from_panel', methods=['POST'])
def admin_sync_vod_library_from_panel():
    """
    Pull the REAL movie and series list from your IPTV reseller panel via
    the Xtream Codes API (the same API TiviMate/IPTV Smarters use when you
    log a device in) and use it to populate/refresh the VOD library catalog.

    This can take a while for large libraries (some panels have tens of
    thousands of VOD entries) - if your hosting platform has a request
    timeout shorter than this takes, the sync may get cut off. If that
    happens repeatedly, consider raising your gunicorn worker timeout
    (e.g. add `--timeout 120` to your start command on Render).

    Note: this now also runs automatically every 3 days in the background
    (see auto_sync_loop()) - this button is for triggering an on-demand
    refresh in between those automatic runs.
    """
    if not is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    if not RESELLER_USERNAME or not RESELLER_PASSWORD:
        return jsonify({
            'success': False,
            'message': 'RESELLER_USER and RESELLER_PASS environment variables are not set. '
                       'These should be any working line\'s username/password on your panel.'
        }), 400

    try:
        stats = perform_vod_library_sync()

        admin_user = session.get('username', 'admin')
        log_activity(
            admin_user,
            f"Synced VOD library from IPTV panel: "
            f"{stats['movies_added']} new movies ({stats['movies_updated']} refreshed), "
            f"{stats['series_added']} new series ({stats['series_updated']} refreshed)"
        )

        return jsonify({
            'success': True,
            'message': (
                f"Synced from your panel: {stats['movies_added']} new movies "
                f"({stats['movies_updated']} already catalogued, refreshed), "
                f"{stats['series_added']} new series ({stats['series_updated']} already catalogued, refreshed)."
            )
        })
    except RuntimeError as e:
        # This message is always safe to print/show - fetch_xtream_api()
        # never lets credentials reach this exception.
        print("SYNC_VOD_LIBRARY_FROM_PANEL ERROR:", str(e))
        return jsonify({'success': False, 'message': str(e)}), 502
    except requests.exceptions.RequestException:
        print("SYNC_VOD_LIBRARY_FROM_PANEL NETWORK ERROR: connection failed")
        return jsonify({'success': False, 'message': "Could not reach your IPTV panel."}), 502
    except Exception as e:
        print("SYNC_VOD_LIBRARY_FROM_PANEL UNEXPECTED ERROR:", type(e).__name__)
        return jsonify({'success': False, 'message': "An unexpected error occurred during sync."}), 500


@app.route('/admin/sync_live_channels_from_panel', methods=['POST'])
def admin_sync_live_channels_from_panel():
    """
    Pull the REAL live channel list from your IPTV reseller panel via the
    Xtream Codes API (action=get_live_streams) and use it to fully replace
    the live_channels table - this is what people search against when
    reporting a channel fault, so it needs to reflect what's actually live
    on the panel rather than a static placeholder list.

    This does a full replace (clears old entries, inserts fresh ones) rather
    than merging, since the old static UK channel list has been retired in
    favor of this real sync. The replace only happens after a successful,
    non-empty response from the panel, so a failed/empty API call can't
    wipe out your existing channel list.

    Note: this now also runs automatically every 3 days in the background
    (see auto_sync_loop()) - this button is for triggering an on-demand
    refresh in between those automatic runs.
    """
    if not is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    if not RESELLER_USERNAME or not RESELLER_PASSWORD:
        return jsonify({
            'success': False,
            'message': 'RESELLER_USER and RESELLER_PASS environment variables are not set. '
                       'These should be any working line\'s username/password on your panel.'
        }), 400

    try:
        stats = perform_live_channels_sync()

        admin_user = session.get('username', 'admin')
        log_activity(admin_user, f"Synced live channels from IPTV panel: {stats['channel_count']} channels")

        return jsonify({
            'success': True,
            'message': f"Synced {stats['channel_count']} live channels from your panel."
        })
    except RuntimeError as e:
        # Safe to print/show - fetch_xtream_api() never lets credentials
        # reach this exception.
        print("SYNC_LIVE_CHANNELS_FROM_PANEL ERROR:", str(e))
        return jsonify({'success': False, 'message': str(e)}), 502
    except requests.exceptions.RequestException:
        print("SYNC_LIVE_CHANNELS_FROM_PANEL NETWORK ERROR: connection failed")
        return jsonify({'success': False, 'message': "Could not reach your IPTV panel."}), 502
    except Exception as e:
        print("SYNC_LIVE_CHANNELS_FROM_PANEL UNEXPECTED ERROR:", type(e).__name__)
        return jsonify({'success': False, 'message': "An unexpected error occurred during sync."}), 500


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


@app.route('/admin/accept_renewal_job/<int:job_id>', methods=['POST'])
def admin_accept_renewal_job(job_id):
    """
    Admin: accept a pending renewal job. This is the actual "I've extended
    this line on the real panel" confirmation - it adds 365 days to whatever
    the account's expiry already was (matching how the reseller panel
    itself renews a line) and updates portal_users (and referral_friends,
    for friend renewals) to match.
    """
    if not is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    try:
        success, result = accept_renewal_job(job_id)
        if not success:
            return jsonify({'success': False, 'message': result}), 400

        admin_user = session.get('username', 'admin')
        log_activity(
            admin_user,
            f"Accepted renewal job #{job_id}: {result['username']} extended from "
            f"{result['previous_expiry_date']} to {result['new_expiry_date']}"
        )

        return jsonify({
            'success': True,
            'message': (
                f"{result['username']}'s line extended: "
                f"{result['previous_expiry_date']} → {result['new_expiry_date']}."
            )
        })
    except Exception as e:
        print("ADMIN_ACCEPT_RENEWAL_JOB ERROR:", e)
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/reveal_spotify_password/<int:order_id>')
def reveal_spotify_password(order_id):
    """
    Admin-only: decrypt and return the Spotify password for a specific order,
    on demand. This keeps the password out of the page's normal HTML/network
    response until an admin explicitly asks for it.
    """
    if not is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT spotify_password FROM spotify_orders WHERE id = ?", (order_id,))
            row = cursor.fetchone()

        if not row:
            return jsonify({'success': False, 'message': 'Order not found.'}), 404

        plain_password = decrypt_spotify_password(row['spotify_password'])

        admin_user = session.get('username', 'admin')
        log_activity(admin_user, f"Viewed Spotify password for order #{order_id}")

        return jsonify({'success': True, 'password': plain_password})
    except Exception as e:
        print("REVEAL_SPOTIFY_PASSWORD ERROR:", e)
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/logout')
def logout():
    username = session.get('username')
    session.clear()
    if username:
        log_activity(username, "Logout")
    return redirect('/')


# --- AUTOMATIC PANEL SYNC (every 3 days) ---
# Keeps the VOD library (movies/series) and live channel list up to date
# without anyone needing to click the manual "Sync" buttons. Runs as a
# background thread so it doesn't block normal web requests.

AUTO_SYNC_INTERVAL_SECONDS = 3 * 24 * 60 * 60  # 3 days


def auto_sync_loop():
    # Wait a bit after startup before the first run, partly so the app is
    # fully up before doing any work, and partly so every name this thread
    # calls is guaranteed to already exist (this function is only started
    # after the whole file has finished loading, so this is just an extra
    # safety margin, not a strict requirement).
    time.sleep(60)

    while True:
        if not RESELLER_USERNAME or not RESELLER_PASSWORD:
            print("AUTO SYNC: Skipped - RESELLER_USER/RESELLER_PASS not configured.", flush=True)
        else:
            try:
                print("AUTO SYNC: Starting scheduled VOD/series sync...", flush=True)
                vod_stats = perform_vod_library_sync()
                print(
                    f"AUTO SYNC: VOD library done - "
                    f"{vod_stats['movies_added']} new movies ({vod_stats['movies_updated']} refreshed), "
                    f"{vod_stats['series_added']} new series ({vod_stats['series_updated']} refreshed).",
                    flush=True
                )
                log_activity(
                    "System (auto-sync)",
                    f"Automatic VOD library sync: {vod_stats['movies_added']} new movies, "
                    f"{vod_stats['series_added']} new series"
                )
            except Exception as e:
                print(f"AUTO SYNC: VOD library sync failed - {type(e).__name__}: {e}", flush=True)

            try:
                print("AUTO SYNC: Starting scheduled live channel sync...", flush=True)
                channel_stats = perform_live_channels_sync()
                print(f"AUTO SYNC: Live channels done - {channel_stats['channel_count']} channels.", flush=True)
                log_activity(
                    "System (auto-sync)",
                    f"Automatic live channel sync: {channel_stats['channel_count']} channels"
                )
            except Exception as e:
                print(f"AUTO SYNC: Live channel sync failed - {type(e).__name__}: {e}", flush=True)

        time.sleep(AUTO_SYNC_INTERVAL_SECONDS)


# Started unconditionally at module load (not inside `if __name__ == '__main__'`)
# so it also runs under gunicorn on Render, not just when run directly.
_auto_sync_thread = Thread(target=auto_sync_loop, daemon=True)
_auto_sync_thread.start()


if __name__ == '__main__':
    app.run(debug=False, port=5000)
