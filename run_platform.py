import json

from platform_core.runtime import ArchitectureRuntime

def main():
    runtime = ArchitectureRuntime()

    try:
        runtime.initialize()

        print("ARCHITECTURE INITIALIZED")

        print(json.dumps(
            runtime.health_report(),
            indent=2,
        ))

        runtime.save_state()

        print("CHECKPOINT SAVED")

    finally:
        runtime.shutdown()

if __name__ == "__main__":
    main()
