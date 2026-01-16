"""
Scheduler Service

Centralized background job scheduler using APScheduler.
Handles periodic tasks like RAG syncing, cleanup, and maintenance.

This service encapsulates:
- Job scheduling and management
- RAG auto-sync from Obsidian vault
- Database maintenance (VACUUM, ANALYZE)
- Chat cleanup (old/inactive chats)
- Health monitoring
"""

import threading
import structlog
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Callable
from pathlib import Path
from apscheduler.schedulers.background import BackgroundScheduler

logger = structlog.get_logger()


class SchedulerService:
    """
    Background job scheduler service.

    Manages periodic tasks for data synchronization, cleanup, and maintenance.
    """

    def __init__(self):
        """Initialize the scheduler service."""
        self.scheduler: Optional[BackgroundScheduler] = None
        self.is_running = False

        # Job-specific state
        self.rag_sync_lock = threading.Lock()
        self.last_rag_sync_time: Optional[datetime] = None
        self.last_rag_sync_duration: Optional[float] = None
        self.last_rag_sync_error: Optional[str] = None
        self.files_synced_count = 0

        # Job statistics
        self.job_stats: Dict[str, Dict[str, Any]] = {}

    def start(self, config: Optional[Dict[str, Any]] = None) -> None:
        """
        Start the scheduler.

        Args:
            config: Optional configuration dict with job settings
        """
        if self.is_running:
            logger.warning("scheduler_already_running")
            return

        try:
            from config import get_settings
            settings = get_settings()
            config = config or {}

            self.scheduler = BackgroundScheduler()

            # Register jobs based on config
            if config.get('rag_sync_enabled', settings.rag_auto_sync_enabled):
                self._register_rag_sync_job(
                    interval_minutes=config.get('rag_sync_interval', settings.rag_auto_sync_interval_minutes)
                )

            if config.get('cleanup_enabled', True):
                self._register_cleanup_job(
                    interval_hours=config.get('cleanup_interval_hours', 24)
                )

            if config.get('db_maintenance_enabled', True):
                self._register_db_maintenance_job(
                    interval_hours=config.get('db_maintenance_interval_hours', 168)  # Weekly
                )

            self.scheduler.start()
            self.is_running = True
            logger.info("scheduler_started")

        except Exception as e:
            logger.error("scheduler_start_error", error=str(e))
            raise

    def shutdown(self) -> None:
        """Gracefully shutdown the scheduler."""
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown()
            self.is_running = False
            logger.info("scheduler_stopped")

    # ========================================================================
    # RAG SYNC JOB
    # ========================================================================

    def _register_rag_sync_job(self, interval_minutes: int) -> None:
        """
        Register the RAG auto-sync job.

        Args:
            interval_minutes: Sync interval in minutes
        """
        self.scheduler.add_job(
            self._rag_sync_task,
            'interval',
            minutes=interval_minutes,
            id='rag_sync_job',
            name='RAG Auto-Sync',
            replace_existing=True,
            next_run_time=None  # Don't run immediately
        )
        logger.info("rag_sync_job_registered", interval_minutes=interval_minutes)

    def _rag_sync_task(self) -> None:
        """
        Background task for automatic RAG synchronization.
        Syncs Obsidian vault files to RAG database periodically.
        """
        from config import get_settings
        from services.rag_service import get_rag_service

        settings = get_settings()

        # Use lock to prevent concurrent syncs
        if not self.rag_sync_lock.acquire(blocking=False):
            logger.warning("rag_sync_already_in_progress")
            return

        try:
            start_time = datetime.utcnow()
            logger.info("rag_sync_start", interval_minutes=settings.rag_auto_sync_interval_minutes)

            # Get vault path
            vault = self._resolve_vault_path(settings.vault_path)
            if not vault:
                self.last_rag_sync_error = f"Vault not found at {settings.vault_path}"
                logger.error("rag_sync_vault_not_found", path=str(settings.vault_path))
                return

            # Get RAG service
            rag_service = get_rag_service()

            synced = []
            errors = []
            skipped = 0

            # Find all markdown files
            md_files = list(vault.rglob("*.md"))

            for md_file in md_files:
                try:
                    # Skip hidden files/directories
                    if any(part.startswith(".") for part in md_file.parts):
                        skipped += 1
                        continue

                    # Read content
                    content = md_file.read_text(encoding="utf-8")

                    # Skip empty files
                    if not content.strip():
                        skipped += 1
                        continue

                    # Create source name with vault: prefix
                    relative_path = md_file.relative_to(vault)
                    source_name = f"vault:{relative_path}"

                    # Check if source exists (to update or create)
                    import sqlite3
                    conn = rag_service.get_conn()
                    existing = conn.execute(
                        "SELECT id FROM sources WHERE name = ?", (source_name,)
                    ).fetchone()

                    if existing:
                        # Update: delete old chunks
                        source_id = existing[0]
                        conn.execute("DELETE FROM chunks WHERE source_id = ?", (source_id,))
                        conn.commit()
                        conn.close()
                    else:
                        conn.close()

                    # Upsert source
                    source_id = rag_service.upsert_source(source_name)

                    # Chunk text
                    chunks_text = rag_service.chunk_text(content)

                    if not chunks_text:
                        skipped += 1
                        continue

                    # Generate embeddings
                    embeddings = rag_service.embed_texts(chunks_text)

                    # Prepare chunks with embeddings
                    chunks_data = [
                        (i, text, emb) for i, (text, emb) in enumerate(zip(chunks_text, embeddings))
                    ]

                    # Add to database
                    rag_service.add_chunks(source_id, chunks_data)

                    synced.append(str(relative_path))

                except Exception as e:
                    error_msg = f"{md_file.name}: {str(e)}"
                    errors.append(error_msg)
                    logger.error("rag_sync_file_error", file=str(md_file), error=str(e))

            # Calculate duration
            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()

            # Update state
            self.last_rag_sync_time = end_time
            self.last_rag_sync_duration = duration
            self.last_rag_sync_error = None if not errors else f"{len(errors)} files failed"
            self.files_synced_count = len(synced)

            # Update stats
            self.job_stats['rag_sync'] = {
                'last_run': end_time.isoformat(),
                'duration_seconds': duration,
                'files_synced': len(synced),
                'files_skipped': skipped,
                'errors': len(errors)
            }

            logger.info(
                "rag_sync_complete",
                synced=len(synced),
                skipped=skipped,
                errors=len(errors),
                duration_seconds=duration
            )

        except Exception as e:
            self.last_rag_sync_error = str(e)
            logger.error("rag_sync_task_error", error=str(e))

        finally:
            self.rag_sync_lock.release()

    def _resolve_vault_path(self, configured_path: Path) -> Optional[Path]:
        """
        Resolve vault path, trying alternative locations if configured path doesn't exist.

        Args:
            configured_path: Configured vault path

        Returns:
            Resolved vault path or None if not found
        """
        if configured_path.exists():
            return configured_path

        # Try alternative paths
        alternative_paths = [
            Path("/obsidian-vault"),
            Path("../obsidian-vault"),
            Path("r:/obsidian-vault"),
            Path("/mnt/obsidian-vault"),
            Path("/app/vault"),
            Path("r:/WebAppChat/vault"),
            Path("./vault"),
        ]

        for alt_path in alternative_paths:
            if alt_path.exists():
                logger.info("vault_path_resolved", configured=str(configured_path), actual=str(alt_path))
                return alt_path

        return None

    def trigger_rag_sync(self) -> Dict[str, Any]:
        """
        Manually trigger RAG sync (non-blocking).

        Returns:
            Status dict
        """
        if not self.rag_sync_lock.acquire(blocking=False):
            return {
                "success": False,
                "message": "RAG sync already in progress"
            }

        try:
            # Release lock immediately and run in thread
            self.rag_sync_lock.release()

            # Run sync in background thread
            import threading
            thread = threading.Thread(target=self._rag_sync_task)
            thread.daemon = True
            thread.start()

            return {
                "success": True,
                "message": "RAG sync started in background"
            }

        except Exception as e:
            logger.error("manual_rag_sync_error", error=str(e))
            return {
                "success": False,
                "message": f"Error starting RAG sync: {str(e)}"
            }

    def get_rag_sync_status(self) -> Dict[str, Any]:
        """
        Get RAG sync status.

        Returns:
            Status dict with last sync info
        """
        return {
            "last_sync_time": self.last_rag_sync_time.isoformat() if self.last_rag_sync_time else None,
            "last_duration_seconds": self.last_rag_sync_duration,
            "last_error": self.last_rag_sync_error,
            "files_synced": self.files_synced_count,
            "sync_in_progress": self.rag_sync_lock.locked()
        }

    # ========================================================================
    # CLEANUP JOB
    # ========================================================================

    def _register_cleanup_job(self, interval_hours: int) -> None:
        """
        Register the cleanup job.

        Args:
            interval_hours: Cleanup interval in hours
        """
        self.scheduler.add_job(
            self._cleanup_task,
            'interval',
            hours=interval_hours,
            id='cleanup_job',
            name='Database Cleanup',
            replace_existing=True
        )
        logger.info("cleanup_job_registered", interval_hours=interval_hours)

    def _cleanup_task(self) -> None:
        """
        Clean up old/inactive data.

        Currently performs:
        - Remove chats older than X days (configurable)
        - Archive inactive sessions
        """
        try:
            start_time = datetime.utcnow()
            logger.info("cleanup_task_start")

            from config import get_settings
            settings = get_settings()

            # Cleanup configuration (can be added to settings later)
            max_chat_age_days = getattr(settings, 'max_chat_age_days', 365)  # 1 year default

            # Get storage service
            from services.storage_service import get_storage_service
            storage = get_storage_service()

            # Find old chats
            all_chats = storage.list_chats()
            cutoff_time = datetime.utcnow() - timedelta(days=max_chat_age_days)
            cutoff_timestamp = int(cutoff_time.timestamp())

            deleted_count = 0
            for chat in all_chats:
                if chat.get('updated_at', 0) < cutoff_timestamp:
                    if storage.delete_chat(chat['id']):
                        deleted_count += 1

            duration = (datetime.utcnow() - start_time).total_seconds()

            # Update stats
            self.job_stats['cleanup'] = {
                'last_run': datetime.utcnow().isoformat(),
                'duration_seconds': duration,
                'chats_deleted': deleted_count
            }

            logger.info(
                "cleanup_task_complete",
                chats_deleted=deleted_count,
                duration_seconds=duration
            )

        except Exception as e:
            logger.error("cleanup_task_error", error=str(e))

    # ========================================================================
    # DATABASE MAINTENANCE JOB
    # ========================================================================

    def _register_db_maintenance_job(self, interval_hours: int) -> None:
        """
        Register the database maintenance job.

        Args:
            interval_hours: Maintenance interval in hours
        """
        self.scheduler.add_job(
            self._db_maintenance_task,
            'interval',
            hours=interval_hours,
            id='db_maintenance_job',
            name='Database Maintenance',
            replace_existing=True
        )
        logger.info("db_maintenance_job_registered", interval_hours=interval_hours)

    def _db_maintenance_task(self) -> None:
        """
        Perform database maintenance.

        Currently performs:
        - VACUUM on SQLite databases
        - ANALYZE for query optimization
        """
        try:
            start_time = datetime.utcnow()
            logger.info("db_maintenance_task_start")

            # Maintain chat database
            from chat_db import get_chat_db
            chat_db = get_chat_db()
            conn = chat_db.get_conn()
            conn.execute("VACUUM;")
            conn.execute("ANALYZE;")
            conn.close()
            logger.info("chat_db_maintenance_complete")

            # Maintain RAG database
            from services.rag_service import get_rag_service
            rag_service = get_rag_service()
            conn = rag_service.get_conn()
            conn.execute("VACUUM;")
            conn.execute("ANALYZE;")
            conn.close()
            logger.info("rag_db_maintenance_complete")

            duration = (datetime.utcnow() - start_time).total_seconds()

            # Update stats
            self.job_stats['db_maintenance'] = {
                'last_run': datetime.utcnow().isoformat(),
                'duration_seconds': duration
            }

            logger.info("db_maintenance_task_complete", duration_seconds=duration)

        except Exception as e:
            logger.error("db_maintenance_task_error", error=str(e))

    # ========================================================================
    # STATUS & MANAGEMENT
    # ========================================================================

    def get_status(self) -> Dict[str, Any]:
        """
        Get scheduler status.

        Returns:
            Status dict with scheduler and job info
        """
        if not self.scheduler:
            return {
                "running": False,
                "jobs": []
            }

        jobs_info = []
        for job in self.scheduler.get_jobs():
            jobs_info.append({
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None
            })

        return {
            "running": self.is_running,
            "jobs": jobs_info,
            "stats": self.job_stats
        }

    def add_job(
        self,
        func: Callable,
        job_id: str,
        name: str,
        trigger: str = 'interval',
        **kwargs
    ) -> bool:
        """
        Add a custom job to the scheduler.

        Args:
            func: Function to run
            job_id: Unique job ID
            name: Human-readable job name
            trigger: Trigger type ('interval', 'cron', 'date')
            **kwargs: Additional scheduler arguments

        Returns:
            True if added successfully
        """
        try:
            if not self.scheduler:
                logger.error("scheduler_not_started")
                return False

            self.scheduler.add_job(
                func,
                trigger,
                id=job_id,
                name=name,
                replace_existing=True,
                **kwargs
            )

            logger.info("custom_job_added", job_id=job_id, name=name)
            return True

        except Exception as e:
            logger.error("add_job_error", job_id=job_id, error=str(e))
            return False

    def remove_job(self, job_id: str) -> bool:
        """
        Remove a job from the scheduler.

        Args:
            job_id: Job ID to remove

        Returns:
            True if removed successfully
        """
        try:
            if not self.scheduler:
                return False

            self.scheduler.remove_job(job_id)
            logger.info("job_removed", job_id=job_id)
            return True

        except Exception as e:
            logger.error("remove_job_error", job_id=job_id, error=str(e))
            return False


# Singleton instance
_scheduler_service: Optional[SchedulerService] = None


def get_scheduler_service() -> SchedulerService:
    """
    Get the singleton scheduler service instance.

    Returns:
        SchedulerService instance
    """
    global _scheduler_service

    if _scheduler_service is None:
        _scheduler_service = SchedulerService()

    return _scheduler_service


# Singleton instance
_scheduler_service_instance = None


def get_scheduler_service():
    """
    Get the singleton SchedulerService instance.

    Returns:
        SchedulerService: The singleton instance
    """
    global _scheduler_service_instance
    if _scheduler_service_instance is None:
        _scheduler_service_instance = SchedulerService()
    return _scheduler_service_instance
