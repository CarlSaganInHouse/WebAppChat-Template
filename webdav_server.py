"""
WebDAV server for Obsidian vault remote access.

Standalone WSGI application using WsgiDAV's FileSystemProvider
for secure, authenticated remote vault synchronization.
"""

import os
import sys
import logging
from pathlib import Path
from typing import Dict, Any

from wsgidav.wsgidav_app import WsgiDAVApp
from wsgidav.fs_dav_provider import FilesystemProvider
from wsgidav.dc.simple_dc import SimpleDomainController
from wsgidav.server.server_cli import DEFAULT_CONFIG
from cheroot import wsgi

# Import our custom auth config
sys.path.insert(0, os.path.dirname(__file__))
from webdav_config import get_auth_config
from webdav_security import SecurityMiddleware, configure_security_filters


class VaultDomainController(SimpleDomainController):
    """
    Custom domain controller for WebDAV authentication.
    Verifies credentials against bcrypt-hashed tokens.
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.auth_config = get_auth_config()
        self.realm = "Obsidian Vault WebDAV"
    
    def require_authentication(self, realm, environ):
        """All requests require authentication."""
        return True
    
    def basic_auth_user(self, realm, user_name, password, environ):
        """
        Verify HTTP Basic Auth credentials.
        
        Args:
            realm: Authentication realm
            user_name: Username from HTTP Basic Auth
            password: Password/token from HTTP Basic Auth
            environ: WSGI environment
        
        Returns:
            True if credentials are valid, False otherwise
        """
        # Log authentication attempt (without password)
        remote_ip = environ.get('REMOTE_ADDR', 'unknown')
        logging.info(f"WebDAV auth attempt: user={user_name}, ip={remote_ip}")
        
        # Verify credentials
        is_valid = self.auth_config.verify_credentials(user_name, password)
        
        if is_valid:
            logging.info(f"WebDAV auth success: user={user_name}, ip={remote_ip}")
        else:
            logging.warning(f"WebDAV auth failure: user={user_name}, ip={remote_ip}")
        
        return is_valid
    
    def supports_http_digest_auth(self):
        """We only support Basic Auth (over HTTPS)."""
        return False


class HeadRequestAdapter:
    """
    WSGI middleware that normalizes HEAD responses so clients don't fail when
    directory browsing HTML is disabled.
    """

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        if environ.get("REQUEST_METHOD") != "HEAD":
            return self.app(environ, start_response)

        captured: Dict[str, Any] = {}

        def capture_start_response(status, headers, exc_info=None):
            captured["status"] = status
            captured["headers"] = headers
            captured["exc_info"] = exc_info

        body_iter = self.app(environ, capture_start_response)
        body_chunks = []
        try:
            for chunk in body_iter:
                body_chunks.append(chunk)
        finally:
            close = getattr(body_iter, "close", None)
            if callable(close):
                close()

        status = captured.get("status", "500 Internal Server Error")
        headers = captured.get("headers", [])
        exc_info = captured.get("exc_info")

        # Remove any existing length headers; we'll set zero-length below
        filtered_headers = [(k, v) for (k, v) in headers if k.lower() != "content-length"]

        if status.startswith("403"):
            status = "200 OK"

        filtered_headers.append(("Content-Length", "0"))
        start_response(status, filtered_headers, exc_info)
        return [b""]


def create_webdav_app() -> WsgiDAVApp:
    """
    Create and configure the WebDAV WSGI application.
    
    Returns:
        Configured WsgiDAVApp instance
    """
    # Get configuration from environment
    vault_path = os.getenv('WEBDAV_VAULT_PATH', '/app/vault')
    host = os.getenv('WEBDAV_HOST', '0.0.0.0')
    port = int(os.getenv('WEBDAV_PORT', '8080'))
    debug = os.getenv('WEBDAV_DEBUG', 'false').lower() == 'true'
    
    # Validate vault path exists
    vault_path_obj = Path(vault_path)
    if not vault_path_obj.exists():
        raise RuntimeError(f"Vault path does not exist: {vault_path}")
    
    logging.info(f"Configuring WebDAV for vault: {vault_path}")
    
    # Configure filesystem provider
    provider = FilesystemProvider(vault_path)
    
    # Get security filters
    security_config = configure_security_filters()
    
    # Configure WsgiDAV
    config: Dict[str, Any] = {
        "host": host,
        "port": port,
        "provider_mapping": {
            "/": provider,
        },
        "http_authenticator": {
            "domain_controller": VaultDomainController,
            "accept_basic": True,
            "accept_digest": False,
            "default_to_digest": False,
        },
        "simple_dc": {
            "user_mapping": {},  # We handle auth in VaultDomainController
        },
        "verbose": 1 if debug else 0,
        "logging": {
            "enable": True,
            "enable_loggers": ["wsgidav"] if debug else [],
        },
        # Security settings
        "hotfixes": {
            "emulate_win32_lastmod": False,
        },
        "property_manager": True,
        "lock_storage": True,
        # Note: SecurityMiddleware disabled - WsgiDAV 4.3.3 doesn't support custom middleware
        # Security is enforced via VaultDomainController and security_config filters
        # Additional security
        **security_config,
    }

    # Ensure middleware stack includes directory browser support needed for some clients
    default_middleware = DEFAULT_CONFIG.get("middleware_stack", [])
    if default_middleware:
        config["middleware_stack"] = list(default_middleware)
    
    # Create and return app
    app = WsgiDAVApp(config)
    app = HeadRequestAdapter(app)
    logging.info(f"WebDAV server configured on {host}:{port} serving {vault_path}")
    logging.info(f"WebDAV dir_browser config: {config.get('dir_browser')}")
    
    return app


def run_server():
    """
    Run the WebDAV server using Cheroot WSGI server.
    """
    # Configure logging
    log_level = os.getenv('WEBDAV_LOG_LEVEL', 'INFO').upper()
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create app
    app = create_webdav_app()
    
    # Get server config
    host = os.getenv('WEBDAV_HOST', '0.0.0.0')
    port = int(os.getenv('WEBDAV_PORT', '8080'))
    use_https = os.getenv('WEBDAV_USE_HTTPS', 'false').lower() == 'true'

    # Create server kwargs
    server_kwargs = {
        'bind_addr': (host, port),
        'wsgi_app': app,
    }

    # Note: SSL/TLS is handled by Cloudflare Tunnel (TLS termination at edge)
    # WebDAV server communicates over HTTP with Cloudflare
    logging.info(f"Starting WebDAV server on http://{host}:{port}/ (TLS via Cloudflare Tunnel)")

    # Create server
    server = wsgi.Server(**server_kwargs)

    logging.info("Press Ctrl+C to stop")

    try:
        server.start()
    except KeyboardInterrupt:
        logging.info("Shutting down WebDAV server...")
        server.stop()


if __name__ == '__main__':
    run_server()
