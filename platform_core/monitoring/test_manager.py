import subprocess
import sys

class TestManager:

    def run(self, test_path="tests"):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                test_path,
                "-v",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        return {
            "success": result.returncode == 0,
            "return_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
