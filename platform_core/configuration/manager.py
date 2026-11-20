import json
from pathlib import Path

class ConfigurationManager:
    def __init__(self, config_path="config/platform.json"):
        self.config_path = Path(config_path)

    def load(self):
        if not self.config_path.exists():
            return {}

        return json.loads(
            self.config_path.read_text(encoding="utf-8")
        )
