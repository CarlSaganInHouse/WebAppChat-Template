"""
Microsoft To Do Service

Manages Microsoft Graph API access to user's To Do tasks using OAuth 2.0 with MSAL.
Handles authentication, token caching per-user, and task operations.

Uses delegated permissions - each user authenticates with their own Microsoft account.
"""

import os
import json
import structlog
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from msal import ConfidentialClientApplication, SerializableTokenCache
from dotenv import load_dotenv
import requests

# Load environment variables
load_dotenv()

logger = structlog.get_logger()


class MicrosoftToDoService:
    """
    Manages Microsoft To Do operations via Microsoft Graph API.
    Handles OAuth authentication, token caching, and task operations.
    """

    def __init__(self, user_id: Optional[int] = None, token_cache_data: Optional[str] = None):
        """
        Initialize Microsoft To Do service.

        Args:
            user_id: WebAppChat user ID (for logging/tracking)
            token_cache_data: Serialized token cache from user settings (JSON string)
        """
        # Load OAuth configuration from environment
        self.client_id = os.getenv('WEBCHAT_CLIENT_ID')
        self.client_secret = os.getenv('WEBCHAT_CLIENT_SECRET')
        # Use "common" endpoint for personal Microsoft accounts (multi-tenant)
        self.tenant_id = "common"
        self.redirect_uri = os.getenv('WEBCHAT_REDIRECT_URI', 'http://localhost:5000/auth/callback')

        if not all([self.client_id, self.tenant_id]):
            raise ValueError("Missing required OAuth configuration (WEBCHAT_CLIENT_ID, WEBCHAT_TENANT_ID)")

        self.user_id = user_id
        self.authority = f"https://login.microsoftonline.com/{self.tenant_id}"
        self.scopes = [
            "https://graph.microsoft.com/Tasks.ReadWrite",
            "https://graph.microsoft.com/Mail.Send",
            "https://graph.microsoft.com/User.Read"
        ]

        # Initialize token cache
        self.token_cache = SerializableTokenCache()
        if token_cache_data:
            try:
                self.token_cache.deserialize(token_cache_data)
                logger.info("token_cache_loaded", user_id=user_id)
            except Exception as e:
                logger.warning("token_cache_load_failed", user_id=user_id, error=str(e))
                # Continue with empty cache

        # Create MSAL confidential client app (for secure web backend)
        self.app = ConfidentialClientApplication(
            self.client_id,
            authority=self.authority,
            client_credential=self.client_secret,
            token_cache=self.token_cache
        )

        self.access_token = None

    def get_authorization_url(self) -> str:
        """
        Get the authorization URL for user login.

        Returns:
            Microsoft login URL for redirect
        """
        try:
            result = self.app.get_authorization_request_url(
                scopes=self.scopes,
                redirect_uri=self.redirect_uri
            )
            print(f"[MSAL] get_authorization_request_url returned type: {type(result)}", flush=True)
            print(f"[MSAL] result value: {result}", flush=True)

            if isinstance(result, tuple):
                auth_url = result[0]
            else:
                auth_url = result

            print(f"[MSAL] Final auth_url length: {len(auth_url)}", flush=True)
            print(f"[MSAL] Final auth_url first 100 chars: {auth_url[:100]}", flush=True)

            logger.info("authorization_url_generated", user_id=self.user_id)
            return auth_url
        except Exception as e:
            print(f"[MSAL] Error generating auth URL: {str(e)}", flush=True)
            logger.error("authorization_url_generation_failed", user_id=self.user_id, error=str(e))
            raise

    def acquire_token_by_auth_code(self, auth_code: str) -> Tuple[bool, Optional[str]]:
        """
        Exchange authorization code for access token.

        Args:
            auth_code: Authorization code from OAuth callback

        Returns:
            Tuple of (success, error_message)
        """
        try:
            result = self.app.acquire_token_by_authorization_code(
                code=auth_code,
                scopes=self.scopes,
                redirect_uri=self.redirect_uri
            )

            if "access_token" in result:
                self.access_token = result["access_token"]
                logger.info("token_acquired_by_auth_code", user_id=self.user_id)
                return True, None
            else:
                error = result.get("error_description", result.get("error", "Unknown error"))
                logger.error("auth_code_exchange_failed", user_id=self.user_id, error=error)
                return False, error

        except Exception as e:
            error_msg = str(e)
            logger.error("auth_code_exchange_exception", user_id=self.user_id, error=error_msg)
            return False, error_msg

    def get_access_token(self) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Get valid access token, refreshing if needed.

        Returns:
            Tuple of (success, access_token, error_message)
        """
        # Try to get from cache silently (handles refresh automatically)
        accounts = self.app.get_accounts()
        if accounts:
            try:
                result = self.app.acquire_token_silent(self.scopes, account=accounts[0])
                if result and "access_token" in result:
                    self.access_token = result["access_token"]
                    logger.info("token_acquired_silent", user_id=self.user_id)
                    return True, self.access_token, None
                elif result and "error" in result:
                    error = result.get("error_description", result.get("error", "Unknown error"))
                    logger.warning("token_refresh_failed", user_id=self.user_id, error=error)
                    return False, None, error
            except Exception as e:
                error_msg = str(e)
                logger.warning("token_acquisition_exception", user_id=self.user_id, error=error_msg)
                return False, None, error_msg

        # No token available
        logger.warning("no_token_available", user_id=self.user_id)
        return False, None, "Not authenticated. Please authorize with Microsoft first."

    def get_cached_token(self) -> Optional[str]:
        """
        Get access token without refresh attempt (for checking auth status).

        Returns:
            Access token if available, None otherwise
        """
        return self.access_token

    def get_token_cache_json(self) -> str:
        """
        Get serialized token cache for storing in database.

        Returns:
            JSON string of token cache
        """
        return self.token_cache.serialize()

    def is_authenticated(self) -> bool:
        """
        Check if user is authenticated with Microsoft.

        Returns:
            True if access token is available
        """
        accounts = self.app.get_accounts()
        return len(accounts) > 0

    def get_user_profile(self) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Get the authenticated user's profile.

        Returns:
            Tuple of (success, profile_dict, error_message)
        """
        success, token, error = self.get_access_token()
        if not success:
            return False, None, error

        try:
            headers = {"Authorization": f"Bearer {token}"}
            response = requests.get(
                "https://graph.microsoft.com/v1.0/me",
                headers=headers,
                timeout=10
            )

            if response.status_code == 200:
                profile = response.json()
                logger.info("user_profile_retrieved", user_id=self.user_id, email=profile.get("mail"))
                return True, profile, None
            else:
                error_msg = f"Graph API error: {response.status_code}"
                logger.error("user_profile_failed", user_id=self.user_id, status=response.status_code)
                return False, None, error_msg

        except Exception as e:
            error_msg = str(e)
            logger.error("user_profile_exception", user_id=self.user_id, error=error_msg)
            return False, None, error_msg

    # ========== To Do Operations ==========

    def get_task_lists(self) -> Tuple[bool, Optional[List[Dict]], Optional[str]]:
        """
        Get all task lists for the user.

        Returns:
            Tuple of (success, task_lists, error_message)
        """
        success, token, error = self.get_access_token()
        if not success:
            return False, None, error

        try:
            headers = {"Authorization": f"Bearer {token}"}
            response = requests.get(
                "https://graph.microsoft.com/v1.0/me/todo/lists",
                headers=headers,
                timeout=10
            )

            if response.status_code == 200:
                lists = response.json().get("value", [])
                logger.info("task_lists_retrieved", user_id=self.user_id, count=len(lists))
                return True, lists, None
            else:
                error_msg = f"Graph API error: {response.status_code}"
                logger.error("task_lists_failed", user_id=self.user_id, status=response.status_code)
                return False, None, error_msg

        except Exception as e:
            error_msg = str(e)
            logger.error("task_lists_exception", user_id=self.user_id, error=error_msg)
            return False, None, error_msg

    def get_default_task_list(self) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Get the ID of the default 'Tasks' task list.

        Returns:
            Tuple of (success, list_id, error_message)
        """
        success, lists, error = self.get_task_lists()
        if not success:
            return False, None, error

        if not lists:
            return False, None, "No task lists found"

        # Default list is usually the first one or named "Tasks"
        default_list = lists[0]
        list_id = default_list.get("id")

        logger.info("default_task_list_found", user_id=self.user_id, list_id=list_id)
        return True, list_id, None

    def create_task(
        self,
        title: str,
        list_id: Optional[str] = None,
        body: Optional[str] = None,
        due_date: Optional[str] = None
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Create a new task in a task list.

        Args:
            title: Task title (required)
            list_id: Task list ID (uses default if not provided)
            body: Task description/body (optional)
            due_date: Due date in YYYY-MM-DD format (optional)

        Returns:
            Tuple of (success, task_dict, error_message)
        """
        success, token, error = self.get_access_token()
        if not success:
            return False, None, error

        # Get default list if not provided
        if not list_id:
            success, list_id, error = self.get_default_task_list()
            if not success:
                return False, None, error

        try:
            payload = {
                "title": title,
            }

            if body:
                payload["body"] = {"content": body, "contentType": "text"}

            if due_date:
                payload["dueDateTime"] = {
                    "dateTime": f"{due_date}T00:00:00",
                    "timeZone": "UTC"
                }

            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }

            response = requests.post(
                f"https://graph.microsoft.com/v1.0/me/todo/lists/{list_id}/tasks",
                headers=headers,
                json=payload,
                timeout=10
            )

            if response.status_code == 201:
                task = response.json()
                logger.info(
                    "task_created",
                    user_id=self.user_id,
                    task_id=task.get("id"),
                    title=title
                )
                return True, task, None
            else:
                error_msg = f"Failed to create task: {response.status_code}"
                logger.error("task_creation_failed", user_id=self.user_id, status=response.status_code)
                return False, None, error_msg

        except Exception as e:
            error_msg = str(e)
            logger.error("task_creation_exception", user_id=self.user_id, error=error_msg)
            return False, None, error_msg

    def get_tasks(
        self,
        list_id: Optional[str] = None,
        only_incomplete: bool = True
    ) -> Tuple[bool, Optional[List[Dict]], Optional[str]]:
        """
        Get tasks from a task list.

        Args:
            list_id: Task list ID (uses default if not provided)
            only_incomplete: Only return incomplete tasks (default: True)

        Returns:
            Tuple of (success, tasks, error_message)
        """
        success, token, error = self.get_access_token()
        if not success:
            return False, None, error

        # Get default list if not provided
        if not list_id:
            success, list_id, error = self.get_default_task_list()
            if not success:
                return False, None, error

        try:
            url = f"https://graph.microsoft.com/v1.0/me/todo/lists/{list_id}/tasks"

            # Filter for incomplete tasks only
            params = {}
            if only_incomplete:
                params['$filter'] = "status ne 'completed'"

            headers = {"Authorization": f"Bearer {token}"}

            response = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=10
            )

            if response.status_code == 200:
                tasks = response.json().get("value", [])
                logger.info("tasks_retrieved", user_id=self.user_id, count=len(tasks))
                return True, tasks, None
            else:
                error_msg = f"Graph API error: {response.status_code}"
                logger.error("tasks_retrieval_failed", user_id=self.user_id, status=response.status_code)
                return False, None, error_msg

        except Exception as e:
            error_msg = str(e)
            logger.error("tasks_retrieval_exception", user_id=self.user_id, error=error_msg)
            return False, None, error_msg

    def update_task(
        self,
        task_id: str,
        list_id: Optional[str] = None,
        title: Optional[str] = None,
        body: Optional[str] = None,
        is_completed: Optional[bool] = None
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Update a task.

        Args:
            task_id: Task ID to update
            list_id: Task list ID (uses default if not provided)
            title: New title (optional)
            body: New body/description (optional)
            is_completed: Mark as completed (optional)

        Returns:
            Tuple of (success, task_dict, error_message)
        """
        success, token, error = self.get_access_token()
        if not success:
            return False, None, error

        # Get default list if not provided
        if not list_id:
            success, list_id, error = self.get_default_task_list()
            if not success:
                return False, None, error

        try:
            payload = {}

            if title is not None:
                payload["title"] = title

            if body is not None:
                payload["body"] = {"content": body, "contentType": "text"}

            if is_completed is not None:
                payload["status"] = "completed" if is_completed else "notStarted"

            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }

            response = requests.patch(
                f"https://graph.microsoft.com/v1.0/me/todo/lists/{list_id}/tasks/{task_id}",
                headers=headers,
                json=payload,
                timeout=10
            )

            if response.status_code == 200:
                task = response.json()
                logger.info("task_updated", user_id=self.user_id, task_id=task_id)
                return True, task, None
            else:
                error_msg = f"Failed to update task: {response.status_code}"
                logger.error("task_update_failed", user_id=self.user_id, status=response.status_code)
                return False, None, error_msg

        except Exception as e:
            error_msg = str(e)
            logger.error("task_update_exception", user_id=self.user_id, error=error_msg)
            return False, None, error_msg

    def delete_task(
        self,
        task_id: str,
        list_id: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Delete a task.

        Args:
            task_id: Task ID to delete
            list_id: Task list ID (uses default if not provided)

        Returns:
            Tuple of (success, error_message)
        """
        success, token, error = self.get_access_token()
        if not success:
            return False, error

        # Get default list if not provided
        if not list_id:
            success, list_id, error = self.get_default_task_list()
            if not success:
                return False, error

        try:
            headers = {"Authorization": f"Bearer {token}"}

            response = requests.delete(
                f"https://graph.microsoft.com/v1.0/me/todo/lists/{list_id}/tasks/{task_id}",
                headers=headers,
                timeout=10
            )

            if response.status_code == 204:
                logger.info("task_deleted", user_id=self.user_id, task_id=task_id)
                return True, None
            else:
                error_msg = f"Failed to delete task: {response.status_code}"
                logger.error("task_deletion_failed", user_id=self.user_id, status=response.status_code)
                return False, error_msg

        except Exception as e:
            error_msg = str(e)
            logger.error("task_deletion_exception", user_id=self.user_id, error=error_msg)
            return False, error_msg
