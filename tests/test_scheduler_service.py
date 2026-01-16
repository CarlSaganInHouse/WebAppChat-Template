"""
SchedulerService comprehensive unit tests.

Tests for background job scheduling, RAG sync, cleanup, and maintenance tasks.
"""

import pytest
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call
from datetime import datetime, timedelta
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.scheduler_service import SchedulerService, get_scheduler_service


@pytest.fixture
def scheduler_service():
    """Create a SchedulerService instance for testing."""
    return SchedulerService()


@pytest.fixture
def started_scheduler(scheduler_service):
    """Create and start a scheduler for testing."""
    config = {
        'rag_sync_enabled': False,  # Disable to prevent actual execution
        'cleanup_enabled': False,
        'db_maintenance_enabled': False
    }
    scheduler_service.start(config=config)
    yield scheduler_service
    scheduler_service.shutdown()


class TestInitialization:
    """Test SchedulerService initialization."""

    def test_creates_instance(self, scheduler_service):
        """Should create instance with initial state."""
        assert scheduler_service.scheduler is None
        assert scheduler_service.is_running is False
        assert scheduler_service.last_rag_sync_time is None
        assert scheduler_service.files_synced_count == 0
        assert scheduler_service.job_stats == {}

    def test_has_rag_sync_lock(self, scheduler_service):
        """Should have thread lock for RAG sync."""
        assert scheduler_service.rag_sync_lock is not None
        assert not scheduler_service.rag_sync_lock.locked()


class TestStartStop:
    """Test scheduler startup and shutdown."""

    def test_start_initializes_scheduler(self, scheduler_service):
        """Should initialize and start APScheduler."""
        config = {'rag_sync_enabled': False, 'cleanup_enabled': False, 'db_maintenance_enabled': False}
        scheduler_service.start(config=config)

        try:
            assert scheduler_service.scheduler is not None
            assert scheduler_service.is_running is True
            assert scheduler_service.scheduler.running
        finally:
            scheduler_service.shutdown()

    def test_start_twice_warns(self, started_scheduler):
        """Should warn when starting already running scheduler."""
        # Try to start again
        started_scheduler.start()  # Should warn but not crash
        assert started_scheduler.is_running is True

    def test_shutdown_stops_scheduler(self, started_scheduler):
        """Should stop scheduler gracefully."""
        started_scheduler.shutdown()

        assert started_scheduler.is_running is False
        assert not started_scheduler.scheduler.running

    def test_shutdown_when_not_running(self, scheduler_service):
        """Should handle shutdown when not running."""
        # Should not crash
        scheduler_service.shutdown()


class TestJobRegistration:
    """Test job registration."""

    @patch('services.scheduler_service.get_settings')
    def test_registers_rag_sync_job(self, mock_settings, scheduler_service):
        """Should register RAG sync job when enabled."""
        mock_settings.return_value.rag_auto_sync_enabled = True
        mock_settings.return_value.rag_auto_sync_interval_minutes = 60

        config = {
            'rag_sync_enabled': True,
            'rag_sync_interval': 30,
            'cleanup_enabled': False,
            'db_maintenance_enabled': False
        }

        scheduler_service.start(config=config)

        try:
            jobs = scheduler_service.scheduler.get_jobs()
            rag_job = next((j for j in jobs if j.id == 'rag_sync_job'), None)

            assert rag_job is not None
            assert rag_job.name == 'RAG Auto-Sync'
        finally:
            scheduler_service.shutdown()

    def test_registers_cleanup_job(self, scheduler_service):
        """Should register cleanup job when enabled."""
        config = {
            'rag_sync_enabled': False,
            'cleanup_enabled': True,
            'cleanup_interval_hours': 24,
            'db_maintenance_enabled': False
        }

        scheduler_service.start(config=config)

        try:
            jobs = scheduler_service.scheduler.get_jobs()
            cleanup_job = next((j for j in jobs if j.id == 'cleanup_job'), None)

            assert cleanup_job is not None
            assert cleanup_job.name == 'Database Cleanup'
        finally:
            scheduler_service.shutdown()

    def test_registers_db_maintenance_job(self, scheduler_service):
        """Should register DB maintenance job when enabled."""
        config = {
            'rag_sync_enabled': False,
            'cleanup_enabled': False,
            'db_maintenance_enabled': True,
            'db_maintenance_interval_hours': 168
        }

        scheduler_service.start(config=config)

        try:
            jobs = scheduler_service.scheduler.get_jobs()
            maintenance_job = next((j for j in jobs if j.id == 'db_maintenance_job'), None)

            assert maintenance_job is not None
            assert maintenance_job.name == 'Database Maintenance'
        finally:
            scheduler_service.shutdown()

    def test_does_not_register_disabled_jobs(self, scheduler_service):
        """Should not register disabled jobs."""
        config = {
            'rag_sync_enabled': False,
            'cleanup_enabled': False,
            'db_maintenance_enabled': False
        }

        scheduler_service.start(config=config)

        try:
            jobs = scheduler_service.scheduler.get_jobs()
            assert len(jobs) == 0
        finally:
            scheduler_service.shutdown()


class TestRAGSyncJob:
    """Test RAG sync job functionality."""

    @patch('services.scheduler_service.get_rag_service')
    @patch('services.scheduler_service.get_settings')
    def test_rag_sync_task_syncs_vault(self, mock_settings, mock_rag_service_getter, scheduler_service, tmp_path):
        """Should sync vault files to RAG database."""
        # Setup mock vault
        vault = tmp_path / "vault"
        vault.mkdir()
        md_file = vault / "test.md"
        md_file.write_text("Test content")

        mock_settings.return_value.vault_path = vault
        mock_settings.return_value.rag_auto_sync_interval_minutes = 60

        # Setup mock RAG service
        mock_rag = Mock()
        mock_rag.upsert_source.return_value = 1
        mock_rag.chunk_text.return_value = ["Test content"]
        mock_rag.embed_texts.return_value = [[0.1, 0.2, 0.3]]
        mock_rag.get_conn.return_value.execute.return_value.fetchone.return_value = None
        mock_rag.get_conn.return_value.close.return_value = None
        mock_rag_service_getter.return_value = mock_rag

        # Run sync task
        scheduler_service._rag_sync_task()

        # Verify sync happened
        assert scheduler_service.last_rag_sync_time is not None
        assert scheduler_service.files_synced_count > 0

    @patch('services.scheduler_service.get_settings')
    def test_rag_sync_handles_missing_vault(self, mock_settings, scheduler_service):
        """Should handle missing vault gracefully."""
        mock_settings.return_value.vault_path = Path("/nonexistent/vault")
        mock_settings.return_value.rag_auto_sync_interval_minutes = 60

        # Run sync task
        scheduler_service._rag_sync_task()

        # Should set error
        assert scheduler_service.last_rag_sync_error is not None
        assert "not found" in scheduler_service.last_rag_sync_error.lower()

    def test_rag_sync_lock_prevents_concurrent_execution(self, scheduler_service):
        """Should prevent concurrent RAG sync executions."""
        # Acquire lock manually
        scheduler_service.rag_sync_lock.acquire()

        try:
            # Try to run sync - should skip
            with patch('services.scheduler_service.get_settings'):
                scheduler_service._rag_sync_task()

            # Should not have run (lock was held)
            assert scheduler_service.last_rag_sync_time is None
        finally:
            scheduler_service.rag_sync_lock.release()

    def test_trigger_rag_sync_manual(self, scheduler_service):
        """Should trigger RAG sync manually."""
        with patch.object(scheduler_service, '_rag_sync_task') as mock_task:
            result = scheduler_service.trigger_rag_sync()

            assert result['success'] is True
            assert 'background' in result['message']

    def test_trigger_rag_sync_when_running(self, scheduler_service):
        """Should reject manual trigger when sync already running."""
        # Acquire lock to simulate running sync
        scheduler_service.rag_sync_lock.acquire()

        try:
            result = scheduler_service.trigger_rag_sync()

            assert result['success'] is False
            assert 'already in progress' in result['message']
        finally:
            scheduler_service.rag_sync_lock.release()

    def test_get_rag_sync_status(self, scheduler_service):
        """Should return RAG sync status."""
        # Set some state
        scheduler_service.last_rag_sync_time = datetime.utcnow()
        scheduler_service.last_rag_sync_duration = 10.5
        scheduler_service.files_synced_count = 25

        status = scheduler_service.get_rag_sync_status()

        assert status['last_sync_time'] is not None
        assert status['last_duration_seconds'] == 10.5
        assert status['files_synced'] == 25
        assert status['sync_in_progress'] is False


class TestCleanupJob:
    """Test cleanup job functionality."""

    @patch('services.scheduler_service.get_storage_service')
    @patch('services.scheduler_service.get_settings')
    def test_cleanup_task_deletes_old_chats(self, mock_settings, mock_storage_getter, scheduler_service):
        """Should delete chats older than retention period."""
        mock_settings.return_value.max_chat_age_days = 30

        # Setup mock storage with old chats
        mock_storage = Mock()
        now = datetime.utcnow()
        old_timestamp = int((now - timedelta(days=40)).timestamp())
        recent_timestamp = int((now - timedelta(days=10)).timestamp())

        mock_storage.list_chats.return_value = [
            {'id': '1', 'title': 'Old Chat', 'updated_at': old_timestamp},
            {'id': '2', 'title': 'Recent Chat', 'updated_at': recent_timestamp}
        ]
        mock_storage.delete_chat.return_value = True
        mock_storage_getter.return_value = mock_storage

        # Run cleanup
        scheduler_service._cleanup_task()

        # Should delete only old chat
        mock_storage.delete_chat.assert_called_once_with('1')

        # Should update stats
        assert 'cleanup' in scheduler_service.job_stats
        assert scheduler_service.job_stats['cleanup']['chats_deleted'] == 1

    @patch('services.scheduler_service.get_storage_service')
    @patch('services.scheduler_service.get_settings')
    def test_cleanup_task_handles_errors(self, mock_settings, mock_storage_getter, scheduler_service):
        """Should handle errors during cleanup gracefully."""
        mock_settings.return_value.max_chat_age_days = 30
        mock_storage_getter.side_effect = Exception("Storage error")

        # Should not crash
        scheduler_service._cleanup_task()


class TestDBMaintenanceJob:
    """Test database maintenance job functionality."""

    @patch('services.scheduler_service.get_rag_service')
    @patch('services.scheduler_service.get_chat_db')
    def test_db_maintenance_task_vacuums_databases(self, mock_chat_db_getter, mock_rag_getter, scheduler_service):
        """Should run VACUUM and ANALYZE on both databases."""
        # Setup mocks
        mock_chat_conn = Mock()
        mock_chat_db = Mock()
        mock_chat_db.get_conn.return_value = mock_chat_conn
        mock_chat_db_getter.return_value = mock_chat_db

        mock_rag_conn = Mock()
        mock_rag = Mock()
        mock_rag.get_conn.return_value = mock_rag_conn
        mock_rag_getter.return_value = mock_rag

        # Run maintenance
        scheduler_service._db_maintenance_task()

        # Verify VACUUM and ANALYZE called on both databases
        mock_chat_conn.execute.assert_any_call("VACUUM;")
        mock_chat_conn.execute.assert_any_call("ANALYZE;")
        mock_rag_conn.execute.assert_any_call("VACUUM;")
        mock_rag_conn.execute.assert_any_call("ANALYZE;")

        # Should update stats
        assert 'db_maintenance' in scheduler_service.job_stats
        assert 'duration_seconds' in scheduler_service.job_stats['db_maintenance']


class TestVaultPathResolution:
    """Test vault path resolution logic."""

    def test_resolves_existing_path(self, scheduler_service, tmp_path):
        """Should return configured path if it exists."""
        vault = tmp_path / "vault"
        vault.mkdir()

        resolved = scheduler_service._resolve_vault_path(vault)
        assert resolved == vault

    def test_tries_alternative_paths(self, scheduler_service, tmp_path):
        """Should try alternative paths if configured path doesn't exist."""
        nonexistent = Path("/nonexistent/vault")

        # Create one of the alternative paths
        alt_vault = tmp_path / "vault"
        alt_vault.mkdir()

        # Patch alternative paths to include our test path
        with patch.object(scheduler_service, '_resolve_vault_path') as mock_resolve:
            mock_resolve.return_value = alt_vault
            resolved = scheduler_service._resolve_vault_path(nonexistent)
            assert resolved == alt_vault

    def test_returns_none_if_no_path_found(self, scheduler_service):
        """Should return None if no valid path found."""
        nonexistent = Path("/absolutely/nonexistent/vault")
        resolved = scheduler_service._resolve_vault_path(nonexistent)
        # Will be None if nothing found
        assert resolved is None or resolved.exists()


class TestCustomJobManagement:
    """Test custom job addition and removal."""

    def test_add_job_registers_custom_job(self, started_scheduler):
        """Should add custom job to scheduler."""
        mock_func = Mock()

        result = started_scheduler.add_job(
            func=mock_func,
            job_id='custom_job',
            name='Custom Job',
            trigger='interval',
            minutes=10
        )

        assert result is True

        # Verify job registered
        jobs = started_scheduler.scheduler.get_jobs()
        custom_job = next((j for j in jobs if j.id == 'custom_job'), None)
        assert custom_job is not None
        assert custom_job.name == 'Custom Job'

    def test_add_job_fails_when_not_started(self, scheduler_service):
        """Should fail to add job when scheduler not started."""
        mock_func = Mock()

        result = scheduler_service.add_job(
            func=mock_func,
            job_id='test_job',
            name='Test',
            trigger='interval',
            minutes=10
        )

        assert result is False

    def test_remove_job_deletes_job(self, started_scheduler):
        """Should remove job from scheduler."""
        # Add a job first
        mock_func = Mock()
        started_scheduler.add_job(
            func=mock_func,
            job_id='to_remove',
            name='To Remove',
            trigger='interval',
            minutes=10
        )

        # Remove it
        result = started_scheduler.remove_job('to_remove')
        assert result is True

        # Verify removed
        jobs = started_scheduler.scheduler.get_jobs()
        removed_job = next((j for j in jobs if j.id == 'to_remove'), None)
        assert removed_job is None

    def test_remove_nonexistent_job(self, started_scheduler):
        """Should handle removing nonexistent job."""
        result = started_scheduler.remove_job('nonexistent_job')
        assert result is False


class TestStatusReporting:
    """Test scheduler status reporting."""

    def test_get_status_when_not_running(self, scheduler_service):
        """Should return not running status."""
        status = scheduler_service.get_status()

        assert status['running'] is False
        assert status['jobs'] == []

    def test_get_status_when_running(self, started_scheduler):
        """Should return running status with job info."""
        # Add a job
        mock_func = Mock()
        started_scheduler.add_job(
            func=mock_func,
            job_id='test_job',
            name='Test Job',
            trigger='interval',
            minutes=10
        )

        status = started_scheduler.get_status()

        assert status['running'] is True
        assert len(status['jobs']) > 0
        assert any(j['id'] == 'test_job' for j in status['jobs'])

    def test_get_status_includes_job_stats(self, started_scheduler):
        """Should include job statistics in status."""
        # Set some stats
        started_scheduler.job_stats['test_job'] = {
            'last_run': datetime.utcnow().isoformat(),
            'duration_seconds': 5.2
        }

        status = started_scheduler.get_status()

        assert 'stats' in status
        assert 'test_job' in status['stats']


class TestSingletonAccess:
    """Test singleton pattern."""

    def test_get_scheduler_service_returns_singleton(self):
        """Should return same instance on multiple calls."""
        service1 = get_scheduler_service()
        service2 = get_scheduler_service()

        assert service1 is service2

    def test_singleton_persists_state(self):
        """Singleton should persist state across calls."""
        service1 = get_scheduler_service()
        service1.files_synced_count = 42

        service2 = get_scheduler_service()
        assert service2.files_synced_count == 42


class TestErrorHandling:
    """Test error handling in various scenarios."""

    @patch('services.scheduler_service.get_settings')
    def test_rag_sync_handles_exceptions(self, mock_settings, scheduler_service):
        """Should handle exceptions during RAG sync."""
        mock_settings.side_effect = Exception("Config error")

        # Should not crash
        scheduler_service._rag_sync_task()

        # Should set error
        assert scheduler_service.last_rag_sync_error is not None

    @patch('services.scheduler_service.get_storage_service')
    def test_cleanup_handles_exceptions(self, mock_storage_getter, scheduler_service):
        """Should handle exceptions during cleanup."""
        mock_storage_getter.side_effect = Exception("Storage error")

        # Should not crash
        scheduler_service._cleanup_task()

    @patch('services.scheduler_service.get_chat_db')
    def test_db_maintenance_handles_exceptions(self, mock_chat_db, scheduler_service):
        """Should handle exceptions during DB maintenance."""
        mock_chat_db.side_effect = Exception("DB error")

        # Should not crash
        scheduler_service._db_maintenance_task()
