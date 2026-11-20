import platform
import sys
import shutil

class EnvironmentManager:
    def inspect(self):
        disk = shutil.disk_usage(".")

        return {
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "python_executable": sys.executable,
            "disk_free_bytes": disk.free
        }
