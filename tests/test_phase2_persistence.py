from platform_core.storage.memory_storage import InMemoryStorage
from platform_core.persistence.checkpoint_manager import CheckpointManager
from platform_core.persistence.state_loader import StateLoader
from platform_core.persistence.state_saver import StateSaver
from platform_core.persistence.migration_manager import MigrationManager
from platform_core.persistence.recovery_manager import RecoveryManager

def test_checkpoint_save_and_restore():
    storage = InMemoryStorage()
    manager = CheckpointManager(storage)

    manager.save("daily-job", {"completed": 10})

    loader = StateLoader(manager)

    assert loader.restore("daily-job") == {"completed": 10}

def test_state_saver():
    storage = InMemoryStorage()
    manager = CheckpointManager(storage)
    saver = StateSaver(manager)

    saver.save("test", {"status": "success"})

    assert manager.load("test")["state"]["status"] == "success"

def test_migration_manager():
    storage = InMemoryStorage()
    migration = MigrationManager(storage, current_version=1)

    assert migration.needs_migration()

    migration.mark_current()

    assert not migration.needs_migration()

def test_recovery_manager():
    storage = InMemoryStorage()
    manager = CheckpointManager(storage)
    manager.save("job", {"progress": 50})

    recovery = RecoveryManager(StateLoader(manager))
    result = recovery.recover("job")

    assert result["recovered"] is True
    assert result["state"]["progress"] == 50

def test_missing_checkpoint():
    storage = InMemoryStorage()
    manager = CheckpointManager(storage)

    assert manager.load("missing") is None
