class PluginManager:
    def __init__(self, registry):
        self.registry = registry
        self.instances = {}

    def discover(self):
        return self.registry.discover()

    def register_instance(self, plugin_id, instance):
        if plugin_id in self.instances:
            raise ValueError(f"Plugin already registered: {plugin_id}")

        self.instances[plugin_id] = instance

    def health_check(self, plugin_id):
        plugin = self.instances.get(plugin_id)
        if plugin is None:
            return False
        return bool(plugin.health_check())

    def shutdown_all(self):
        for plugin in self.instances.values():
            plugin.shutdown()
