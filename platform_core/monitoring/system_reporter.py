from datetime import datetime, timezone

class SystemReporter:

    def generate(self, health_results):
        total = len(health_results)

        healthy = sum(
            item["status"] == "HEALTHY"
            for item in health_results
        )

        unhealthy = sum(
            item["status"] == "UNHEALTHY"
            for item in health_results
        )

        errors = sum(
            item["status"] == "ERROR"
            for item in health_results
        )

        unknown = total - healthy - unhealthy - errors

        return {
            "generated_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "total_components": total,
            "healthy": healthy,
            "unhealthy": unhealthy,
            "errors": errors,
            "unknown": unknown,
            "overall_status": (
                "HEALTHY"
                if total > 0 and healthy == total
                else "DEGRADED"
            ),
            "components": health_results,
        }
