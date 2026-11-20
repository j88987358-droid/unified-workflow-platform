class PluginCompatibilityChecker:

    CORE_API_VERSION = "1.0"

    def check(self, manifest):

        plugin_api = manifest.get("api_version")

        return {
            "compatible": plugin_api == self.CORE_API_VERSION,
            "core_api": self.CORE_API_VERSION,
            "plugin_api": plugin_api
        }
