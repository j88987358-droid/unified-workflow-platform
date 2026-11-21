from datetime import datetime, timezone

class HealthMonitor:

    def __init__(self):
        self.components = {}

    def register(self, name, component):
        self.components[name] = component

    def check(self, name):
        if name not in self.components:
            return {
                "name": name,
                "status": "UNKNOWN",
                "checked_at": datetime.now(
                    timezone.utc
                ).isoformat(),
            }

        component = self.components[name]

        try:
            if hasattr(component, "health_check"):
                result = component.health_check()
            elif hasattr(component, "status"):
                result = component.status
            else:
                result = "REGISTERED"

            healthy = (
                result is True
                or result == "HEALTHY"
                or result == "REGISTERED"
                or (
                    isinstance(result, dict)
                    and result.get("healthy") is True
                )
            )

            return {
                "name": name,
                "status": "HEALTHY" if healthy else "UNHEALTHY",
                "details": result,
                "checked_at": datetime.now(
                    timezone.utc
                ).isoformat(),
            }

        except Exception as exc:
            return {
                "name": name,
                "status": "ERROR",
                "error": str(exc),
                "checked_at": datetime.now(
                    timezone.utc
                ).isoformat(),
            }

    def check_all(self):
        return [
            self.check(name)
            for name in self.components
        ]
