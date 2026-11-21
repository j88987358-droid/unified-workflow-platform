from abc import ABC, abstractmethod

class BaseWorker(ABC):
    name = None
    version = "1.0.0"

    @abstractmethod
    def initialize(self, context):
        pass

    @abstractmethod
    def execute(self, task):
        pass

    @abstractmethod
    def health_check(self):
        pass

    def shutdown(self):
        pass
