"""
Authentication utilities for password hashing, API key generation, and validation.
"""

import secrets
import hashlib
import structlog
from typing import Optional, Tuple
from functools import wraps
from datetime import datetime, timedelta

try:
    import bcrypt
except ImportError:
    bcrypt = None

from flask import request, redirect, url_for, jsonify, g, session
from config import get_settings

logger = structlog.get_logger()


# ========== Password Hashing ==========

def hash_password(password: str, rounds: Optional[int] = None) -> str:
    """
    Hash a password using bcrypt.

    Args:
        password: Plain text password
        rounds: Number of bcrypt rounds (uses config default if None)

    Returns:
        Hashed password string

    Raises:
        ValueError: If bcrypt is not installed
    """
    if bcrypt is None:
        raise ValueError(
            "bcrypt is required for password hashing. "
            "Install it with: pip install bcrypt"
        )

    if rounds is None:
        rounds = get_settings().bcrypt_rounds

    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt(rounds=rounds)
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')


def verify_password(password: str, password_hash: str) -> bool:
    """
    Verify a password against a bcrypt hash.

    Args:
        password: Plain text password to verify
        password_hash: Bcrypt hash to check against

    Returns:
        True if password matches, False otherwise
    """
    if bcrypt is None:
        logger.error("bcrypt_not_installed")
        return False

    try:
        password_bytes = password.encode('utf-8')
        hash_bytes = password_hash.encode('utf-8')
        return bcrypt.checkpw(password_bytes, hash_bytes)
    except Exception as e:
        logger.warning("password_verification_failed", error=str(e))
        return False


# ========== API Key Generation & Hashing ==========

def generate_api_key(length: int = 32) -> str:
    """
    Generate a cryptographically secure random API key.

    Args:
        length: Length of the key in bytes (default 32)

    Returns:
        URL-safe base64 encoded API key
    """
    return secrets.token_urlsafe(length)


def hash_api_key(api_key: str) -> str:
    """
    Hash an API key using SHA-256.

    Args:
        api_key: Plain text API key

    Returns:
        Hexadecimal SHA-256 hash
    """
    return hashlib.sha256(api_key.encode()).hexdigest()


def verify_api_key(api_key: str, api_key_hash: str) -> bool:
    """
    Verify an API key against a hash.

    Args:
        api_key: Plain text API key to verify
        api_key_hash: SHA-256 hash to check against

    Returns:
        True if key matches hash, False otherwise
    """
    computed_hash = hash_api_key(api_key)
    return computed_hash == api_key_hash


# ========== Session Management ==========

def create_session(user_id: int, username: str, remember_me: bool = False) -> None:
    """
    Create a Flask session for a user.

    Args:
        user_id: User database ID
        username: Username
        remember_me: If True, extend session lifetime to SESSION_LIFETIME_DAYS
    """
    settings = get_settings()

    session.permanent = remember_me
    session['user_id'] = user_id
    session['username'] = username

    if remember_me:
        session.permanent_lifetime = timedelta(days=settings.session_lifetime_days)

    logger.info("session_created", user_id=user_id, username=username, remember_me=remember_me)


def destroy_session() -> None:
    """Clear the current user session."""
    session.clear()
    logger.info("session_destroyed")


def get_current_user() -> Optional[dict]:
    """
    Get the current logged-in user from session.

    Returns:
        Dictionary with user_id and username, or None if not logged in
    """
    if 'user_id' in session and 'username' in session:
        return {
            'user_id': session['user_id'],
            'username': session['username']
        }
    return None


def extract_api_key_from_request() -> Optional[str]:
    """
    Extract API key from Authorization header.

    Expected format: Authorization: Bearer <api_key>

    Returns:
        API key string or None if not present
    """
    auth_header = request.headers.get('Authorization', '')

    if not auth_header.startswith('Bearer '):
        return None

    return auth_header[7:].strip()  # Remove 'Bearer ' prefix


# ========== Authentication Decorators ==========

def auth_required(allow_api_key: bool = True):
    """
    Decorator to require authentication on a route.

    Checks for:
    1. Valid session (browser)
    2. Valid API key (if allow_api_key=True)

    Behavior:
    - For browser requests without auth: redirects to /login
    - For API requests without auth: returns 401 JSON error

    Args:
        allow_api_key: If False, only session authentication is allowed

    Example:
        @app.route('/protected')
        @auth_required()
        def protected_route():
            user = get_current_user()
            return jsonify({"message": f"Hello {user['username']}"})
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            settings = get_settings()

            # Skip auth check if disabled
            if not settings.auth_enabled:
                g.current_user = None
                g.auth_method = None
                return f(*args, **kwargs)

            from auth_db import get_auth_db

            # Check for valid session first
            current_user = get_current_user()
            if current_user:
                g.current_user = current_user
                g.auth_method = 'session'
                return f(*args, **kwargs)

            # Check for valid API key
            if allow_api_key:
                api_key = extract_api_key_from_request()
                if api_key:
                    auth_db = get_auth_db()
                    api_key_hash = hash_api_key(api_key)
                    key_data = auth_db.get_api_key_by_hash(api_key_hash)

                    if key_data and not key_data.get('revoked'):
                        auth_db.update_api_key_last_used(key_data['id'])
                        g.current_user = {
                            'user_id': None,
                            'username': None,
                            'api_key_label': key_data['label']
                        }
                        g.auth_method = 'api_key'
                        logger.info("api_key_authenticated", label=key_data['label'])
                        return f(*args, **kwargs)
                    else:
                        ip_address = request.remote_addr
                        auth_db.log_auth_attempt(
                            event_type='api_key_auth',
                            success=False,
                            ip_address=ip_address,
                            key_label='invalid'
                        )
                        logger.warning("invalid_api_key_attempt", ip_address=ip_address)

            # Not authenticated - respond based on request type
            # Use best_match to properly handle Accept header with wildcards
            best_match = request.accept_mimetypes.best_match(['application/json', 'text/html'])

            if best_match == 'application/json':
                # API request
                return jsonify({"error": "Unauthorized"}), 401

            # Browser request - redirect to login
            next_url = request.url
            return redirect(url_for('auth.login', next=next_url))

        return decorated_function
    return decorator


def session_required(f):
    """
    Decorator to require session authentication (no API keys allowed).
    Used for sensitive operations like password changes, key management.

    Example:
        @app.route('/api-keys')
        @session_required
        def manage_api_keys():
            user = get_current_user()
            return jsonify({"message": f"Hello {user['username']}"})
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        settings = get_settings()

        if not settings.auth_enabled:
            g.current_user = None
            return f(*args, **kwargs)

        current_user = get_current_user()
        if not current_user:
            # Use best_match to properly handle Accept header with wildcards
            best_match = request.accept_mimetypes.best_match(['application/json', 'text/html'])

            if best_match == 'application/json':
                return jsonify({"error": "Session authentication required"}), 401
            return redirect(url_for('auth.login', next=request.url))

        g.current_user = current_user
        g.auth_method = 'session'
        return f(*args, **kwargs)

    return decorated_function
