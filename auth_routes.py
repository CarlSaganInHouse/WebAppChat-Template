"""
Authentication routes blueprint.
Handles login, logout, and API key management.
"""

from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify, g
from functools import wraps
from config import get_settings
from auth_db import get_auth_db
from utils.auth_utils import (
    verify_password,
    create_session,
    destroy_session,
    get_current_user,
    hash_api_key,
    generate_api_key,
    session_required
)
import structlog

logger = structlog.get_logger()

# Create blueprint
auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


# ========== Helper Functions ==========

def get_client_ip() -> str:
    """Get client IP address from request."""
    if request.environ.get('HTTP_X_FORWARDED_FOR'):
        return request.environ.get('HTTP_X_FORWARDED_FOR').split(',')[0]
    return request.remote_addr


# ========== Routes ==========

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """
    Login page and handler.
    GET: Display login form
    POST: Process login attempt
    """
    # If already logged in, redirect to main app
    if get_current_user():
        return redirect(url_for('chat.home'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember_me = request.form.get('remember_me') == 'on'

        if not username or not password:
            return render_template(
                'login.html',
                error='Username and password are required'
            ), 400

        settings = get_settings()
        auth_db = get_auth_db(settings.chat_db_path)
        client_ip = get_client_ip()

        # Look up user
        user = auth_db.get_user_by_username(username)

        if user:
            is_valid = verify_password(password, user['password_hash'])
        else:
            is_valid = False

        if user and is_valid:
            # Successful login
            create_session(user['id'], username, remember_me=remember_me)
            auth_db.log_auth_attempt(
                event_type='login',
                success=True,
                ip_address=client_ip,
                username=username
            )
            logger.info("login_successful", username=username, ip_address=client_ip)

            # Redirect to next page or home
            next_url = request.args.get('next')
            if next_url and next_url.startswith('/'):
                return redirect(next_url)
            return redirect(url_for('chat.home'))
        else:
            # Failed login
            auth_db.log_auth_attempt(
                event_type='login',
                success=False,
                ip_address=client_ip,
                username=username
            )
            logger.warning("login_failed", username=username, ip_address=client_ip)

            return render_template(
                'login.html',
                error='Invalid username or password'
            ), 401

    return render_template('login.html')


@auth_bp.route('/logout', methods=['GET', 'POST'])
@session_required
def logout():
    """Logout and destroy session."""
    user = get_current_user()
    if user:
        logger.info("logout_successful", username=user['username'])
    destroy_session()
    return redirect(url_for('auth.login'))


@auth_bp.route('/api-keys', methods=['GET', 'POST'])
@session_required
def manage_api_keys():
    """
    API key management page.
    GET: Display list of API keys
    POST: Create new API key
    """
    settings = get_settings()
    auth_db = get_auth_db(settings.chat_db_path)
    user = get_current_user()

    if request.method == 'POST':
        label = request.form.get('label', '').strip()

        if not label:
            return render_template(
                'api_keys.html',
                keys=auth_db.list_api_keys(),
                error='Label is required'
            ), 400

        try:
            api_key = generate_api_key(32)
            key_hash = hash_api_key(api_key)
            key_id = auth_db.create_api_key(label, key_hash)

            logger.info(
                "api_key_created_via_ui",
                label=label,
                key_id=key_id,
                username=user['username']
            )

            return render_template(
                'api_keys.html',
                keys=auth_db.list_api_keys(),
                new_key={
                    'id': key_id,
                    'label': label,
                    'key': api_key,
                    'plaintext_warning': True
                }
            )
        except Exception as e:
            logger.error(
                "api_key_creation_failed",
                label=label,
                error=str(e),
                username=user['username']
            )
            return render_template(
                'api_keys.html',
                keys=auth_db.list_api_keys(),
                error=f'Failed to create API key: {e}'
            ), 500

    keys = auth_db.list_api_keys()
    return render_template('api_keys.html', keys=keys)


@auth_bp.route('/api-keys/<int:key_id>/revoke', methods=['POST'])
@session_required
def revoke_api_key(key_id: int):
    """Revoke an API key."""
    settings = get_settings()
    auth_db = get_auth_db(settings.chat_db_path)
    user = get_current_user()

    if auth_db.revoke_api_key(key_id):
        logger.info(
            "api_key_revoked_via_ui",
            key_id=key_id,
            username=user['username']
        )
        best_match = request.accept_mimetypes.best_match(['application/json', 'text/html'])
        if best_match == 'application/json':
            return jsonify({"status": "success"}), 200
        return redirect(url_for('auth.manage_api_keys'))
    else:
        logger.warning(
            "api_key_revoke_failed",
            key_id=key_id,
            username=user['username']
        )
        best_match = request.accept_mimetypes.best_match(['application/json', 'text/html'])
        if best_match == 'application/json':
            return jsonify({"error": "Key not found"}), 404
        return redirect(url_for('auth.manage_api_keys')), 404


@auth_bp.route('/settings', methods=['GET', 'POST'])
@session_required
def user_settings():
    """
    User settings page.
    GET: Display settings form
    POST: Update settings
    """
    from user_settings_db import get_user_settings_db

    user = get_current_user()
    user_id = user['user_id']

    settings = get_settings()
    settings_db = get_user_settings_db(settings.chat_db_path)

    if request.method == 'POST':
        vault_path = request.form.get('vault_path', '').strip()
        shared_paths_str = request.form.get('shared_paths', '').strip()
        rag_collection = request.form.get('rag_collection', 'default').strip()

        # Update vault path
        if vault_path:
            settings_db.update_vault_path(user_id, vault_path)

        # Update shared paths (comma-separated)
        if shared_paths_str:
            paths = [p.strip() for p in shared_paths_str.split(',') if p.strip()]
            settings_db.update_shared_paths(user_id, paths)
        else:
            settings_db.update_shared_paths(user_id, [])

        # Update RAG collection
        settings_db.update_rag_collection(user_id, rag_collection)

        logger.info(
            "user_settings_updated",
            user_id=user_id,
            username=user['username']
        )

        return redirect(url_for('auth.user_settings'))

    # GET: Display form
    user_settings = settings_db.get_user_settings(user_id)

    return render_template(
        'user_settings.html',
        user_settings=user_settings,
        system_default_vault=settings.vault_path,
        username=user['username']
    )


@auth_bp.route('/callback')
@session_required
def microsoft_oauth_callback():
    """
    OAuth callback for Microsoft To Do authentication.
    Handles the authorization code and token exchange.
    """
    from microsoft_todo_service import MicrosoftToDoService
    from user_settings_db import UserSettingsDB

    user = get_current_user()
    if not user:
        return redirect(url_for('auth.login'))

    user_id = user['user_id']
    auth_code = request.args.get('code')
    error = request.args.get('error')
    error_description = request.args.get('error_description')

    # Handle OAuth errors
    if error:
        logger.warning(
            "microsoft_oauth_error",
            user_id=user_id,
            error=error,
            error_description=error_description
        )
        return render_template(
            'oauth_result.html',
            success=False,
            message=f"Authorization failed: {error_description or error}",
            title="Microsoft Authorization Failed"
        ), 400

    if not auth_code:
        logger.warning("microsoft_oauth_missing_code", user_id=user_id)
        return render_template(
            'oauth_result.html',
            success=False,
            message="Missing authorization code from Microsoft",
            title="Authorization Failed"
        ), 400

    try:
        # Initialize service (without cached token initially)
        service = MicrosoftToDoService(user_id=user_id)

        # Exchange auth code for access token
        success, error_msg = service.acquire_token_by_auth_code(auth_code)

        if not success:
            logger.error("microsoft_oauth_token_exchange_failed", user_id=user_id, error=error_msg)
            return render_template(
                'oauth_result.html',
                success=False,
                message=f"Failed to obtain access token: {error_msg}",
                title="Token Exchange Failed"
            ), 400

        # Verify we can access user profile
        success, profile, profile_error = service.get_user_profile()
        if not success:
            logger.error("microsoft_profile_retrieval_failed", user_id=user_id, error=profile_error)
            return render_template(
                'oauth_result.html',
                success=False,
                message=f"Failed to verify Microsoft account: {profile_error}",
                title="Verification Failed"
            ), 400

        # Save token cache to user settings
        settings = get_settings()
        user_db = UserSettingsDB(settings.chat_db_path)
        user_settings = user_db.get_user_settings(user_id)

        # Update preferences with token cache
        preferences = user_settings.get('preferences', {})
        preferences['microsoft_todo_token_cache'] = service.get_token_cache_json()
        preferences['microsoft_todo_email'] = profile.get('mail', profile.get('userPrincipalName', 'Unknown'))

        user_db.update_preferences(user_id, preferences)

        logger.info(
            "microsoft_oauth_success",
            user_id=user_id,
            email=profile.get('mail', profile.get('userPrincipalName'))
        )

        return render_template(
            'oauth_result.html',
            success=True,
            message=f"✓ Successfully connected to Microsoft account: {profile.get('mail', 'Your Account')}",
            title="Authorization Successful",
            redirect_url=url_for('chat.home')
        )

    except Exception as e:
        logger.error("microsoft_oauth_exception", user_id=user_id, error=str(e))
        return render_template(
            'oauth_result.html',
            success=False,
            message=f"An error occurred: {str(e)}",
            title="Authorization Error"
        ), 500


@auth_bp.route('/authorize-microsoft')
@session_required
def authorize_microsoft():
    """
    Initiate Microsoft To Do OAuth authorization flow.
    Uses session to store the long auth URL and redirects via JavaScript.
    """
    from microsoft_todo_service import MicrosoftToDoService

    user = get_current_user()
    if not user:
        return redirect(url_for('auth.login'))

    user_id = user.get('user_id') or user.get('id') if isinstance(user, dict) else user

    try:
        service = MicrosoftToDoService(user_id=user_id)
        auth_url = service.get_authorization_url()

        print(f"[AUTH] Generated auth_url length: {len(auth_url) if auth_url else 0}", flush=True)
        print(f"[AUTH] First 100 chars of auth_url: {auth_url[:100] if auth_url else 'EMPTY'}", flush=True)

        logger.info(
            "microsoft_authorization_initiated",
            user_id=user_id,
            username=user.get('username') if isinstance(user, dict) else None
        )

        # Store auth URL in session and use JavaScript to redirect
        # (Server-side redirect header has length limits)
        session['microsoft_auth_url'] = auth_url

        return render_template(
            'microsoft_auth_redirect.html',
            auth_url=auth_url
        )
    except Exception as e:
        logger.error("microsoft_authorization_failed", user_id=user_id, error=str(e))
        return render_template(
            'oauth_result.html',
            success=False,
            message=f"Failed to start authorization: {str(e)}",
            title="Authorization Failed"
        ), 500
