from collections import defaultdict

class EventBus:
    def __init__(self):
        self.listeners = defaultdict(list)

    def subscribe(self, event_name, callback):
        if callback not in self.listeners[event_name]:
            self.listeners[event_name].append(callback)

    def unsubscribe(self, event_name, callback):
        if callback in self.listeners[event_name]:
            self.listeners[event_name].remove(callback)

    def publish(self, event_name, payload=None):
        results = []

        for callback in list(self.listeners[event_name]):
            results.append(callback(payload or {}))

        return results
