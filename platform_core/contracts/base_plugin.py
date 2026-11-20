from abc import ABC, abstractmethod

class BasePlugin(ABC):
    name = None
    version = None
    api_version = "1.0"

    @abstractmethod
    def initialize(self, context):
        pass

    @abstractmethod
    def health_check(self):
        pass

    @abstractmethod
    def execute(self, task):
        pass

    def shutdown(self):
        pass
