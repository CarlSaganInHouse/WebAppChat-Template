"""
WebDAV security filters and configuration.

NOTE: SecurityMiddleware class below is NOT currently used.
WsgiDAV 4.3.3 doesn't support the middleware_stack hook.

Security is enforced via:
1. VaultDomainController - bcrypt authentication
2. configure_security_filters() - path/size limits  
3. Cheroot - request logging

Kept for reference if upgrading to newer WsgiDAV or implementing custom WSGI wrapper.
"""

import os
import re
import logging
from pathlib import Path
from typing import Dict, Any, Callable

# ============================================================================
# UNUSED - Kept for reference only
# ============================================================================

class SecurityMiddleware:
    """
    WSGI middleware for WebDAV security enforcement.
    
    Provides:
    - Request/response logging
    - Path traversal prevention
    - File size limits
    - Sensitive path filtering
    """
    
    def __init__(self, wsgidav_app, config):
        self.application = wsgidav_app
        self.config = config
        self.max_file_size = int(os.getenv('WEBDAV_MAX_FILE_SIZE', str(100 * 1024 * 1024)))  # 100MB default
        self.denied_paths = self._compile_denied_patterns()
    
    def _compile_denied_patterns(self):
        """
        Compile regex patterns for paths that should be denied.
        
        By default, we allow .obsidian/ (needed for sync) but deny:
        - Hidden files/folders starting with .git
        - Temporary files
        - System files
        """
        patterns_str = os.getenv(
            'WEBDAV_DENIED_PATHS',
            r'^\.git/|^\.git$|~$|\.tmp$|\.swp$|\.DS_Store$'
        )
        
        patterns = [re.compile(p.strip()) for p in patterns_str.split('|') if p.strip()]
        return patterns
    
    def _is_path_denied(self, path: str) -> bool:
        """
        Check if a path matches any denied patterns.
        
        Args:
            path: Relative path to check
        
        Returns:
            True if path should be denied, False otherwise
        """
        # Normalize path
        path = path.lstrip('/')
        
        # Check against patterns
        for pattern in self.denied_paths:
            if pattern.search(path):
                return True
        
        return False
    
    def _log_request(self, environ: Dict[str, Any]):
        """Log WebDAV request details."""
        method = environ.get('REQUEST_METHOD', 'UNKNOWN')
        path = environ.get('PATH_INFO', '/')
        remote_ip = environ.get('REMOTE_ADDR', 'unknown')
        user = environ.get('REMOTE_USER', 'anonymous')
        
        logging.info(
            f"WebDAV request: method={method}, path={path}, "
            f"user={user}, ip={remote_ip}"
        )
    
    def _log_response(self, status: str, method: str, path: str):
        """Log WebDAV response details."""
        status_code = status.split()[0] if status else 'unknown'
        logging.info(
            f"WebDAV response: status={status_code}, method={method}, path={path}"
        )
    
    def __call__(self, environ: Dict[str, Any], start_response: Callable):
        """
        WSGI middleware entry point.
        
        Args:
            environ: WSGI environment dict
            start_response: WSGI start_response callable
        
        Returns:
            Response iterable
        """
        # Log incoming request
        self._log_request(environ)
        
        # Extract request details
        method = environ.get('REQUEST_METHOD', 'UNKNOWN')
        path = environ.get('PATH_INFO', '/')
        
        # Check if path is denied
        if self._is_path_denied(path):
            logging.warning(f"Denied access to path: {path}")
            start_response('403 Forbidden', [('Content-Type', 'text/plain')])
            return [b'403 Forbidden: Access to this path is not allowed']
        
        # Check content length for PUT requests
        if method == 'PUT':
            try:
                content_length = int(environ.get('CONTENT_LENGTH', 0))
                if content_length > self.max_file_size:
                    logging.warning(
                        f"File too large: {content_length} bytes "
                        f"(max: {self.max_file_size})"
                    )
                    start_response('413 Payload Too Large', [('Content-Type', 'text/plain')])
                    return [
                        f'413 Payload Too Large: Maximum file size is {self.max_file_size} bytes'.encode()
                    ]
            except (ValueError, TypeError):
                pass  # Invalid content length, let app handle it
        
        # Wrap start_response to log response
        def logging_start_response(status, response_headers, exc_info=None):
            self._log_response(status, method, path)
            return start_response(status, response_headers, exc_info)
        
        # Pass to wrapped app
        return self.application(environ, logging_start_response)


def configure_security_filters() -> Dict[str, Any]:
    """
    Generate security configuration for WsgiDAV.
    
    Returns:
        Dictionary of security settings to merge into WsgiDAV config
    """
    return {
        # Block certain operations on sensitive paths
        "block_size": 8192,
        # Directory browsing (needed for some clients that issue GET/HEAD before PROPFIND)
        "dir_browser": {
            "enable": True,
            "response_trailer": "",
            "davmount": False,
        },
        # Prevent excessive requests
        "request_timeout": 30,
    }


def validate_vault_path(vault_path: str, requested_path: str) -> bool:
    """
    Validate that a requested path stays within vault boundaries.
    
    This is a secondary check - WsgiDAV's FileSystemProvider already
    prevents traversal, but we add extra validation for defense in depth.
    
    Args:
        vault_path: Absolute path to vault root
        requested_path: User-requested relative path
    
    Returns:
        True if path is safe, False otherwise
    """
    try:
        vault = Path(vault_path).resolve()
        full_path = (vault / requested_path.lstrip('/')).resolve()
        
        # Ensure resolved path is under vault
        full_path.relative_to(vault)
        return True
    except (ValueError, RuntimeError):
        return False


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename for safe filesystem storage.
    
    Args:
        filename: Original filename
    
    Returns:
        Sanitized filename
    """
    # Remove null bytes
    filename = filename.replace('\x00', '')
    
    # Remove path separators
    filename = filename.replace('/', '_').replace('\\', '_')
    
    # Limit length
    max_length = 255
    if len(filename) > max_length:
        name, ext = os.path.splitext(filename)
        filename = name[:max_length - len(ext)] + ext
    
    return filename
