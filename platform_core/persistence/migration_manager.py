class MigrationManager:

    def __init__(self, storage, current_version=1):
        self.storage = storage
        self.current_version = current_version
        self.version_key = "platform:schema_version"

    def get_version(self):
        return self.storage.get(self.version_key) or 0

    def needs_migration(self):
        return self.get_version() < self.current_version

    def mark_current(self):
        return self.storage.set(
            self.version_key,
            self.current_version,
        )
