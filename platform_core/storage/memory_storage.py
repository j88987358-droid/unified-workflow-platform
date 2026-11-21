from .base_storage import BaseStorage

class InMemoryStorage(BaseStorage):

    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value):
        self.data[key] = value
        return True

    def delete(self, key):
        self.data.pop(key, None)
        return True
