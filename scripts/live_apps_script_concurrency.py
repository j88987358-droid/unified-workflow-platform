"""Live Apps Script CAS concurrency check used only by the gated GitHub Actions workflow."""
import argparse
import os
from platform_core.storage.apps_script_storage import AppsScriptStorage

INCREMENTS_PER_RUNNER = 10


def storage():
    return AppsScriptStorage(
        url=os.environ["GOOGLE_APPS_SCRIPT_URL"],
        token=os.environ["GOOGLE_APPS_SCRIPT_TOKEN"],
        timeout=60,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("init", "worker", "verify", "cleanup"))
    parser.add_argument("key")
    args = parser.parse_args()
    adapter = storage()

    if args.mode == "init":
        adapter.set(args.key, {"count": 0})
        print("Initialized isolated live-CAS test key.")
    elif args.mode == "worker":
        for _ in range(INCREMENTS_PER_RUNNER):
            adapter.atomic_update(
                args.key,
                lambda current: {"count": int((current or {}).get("count", 0)) + 1},
                max_retries=100,
            )
        print(f"Runner completed {INCREMENTS_PER_RUNNER} increments.")
    else:
        current = adapter.get(args.key)
        actual = int((current or {}).get("count", -1))
        expected = 2 * INCREMENTS_PER_RUNNER
        if actual != expected:
            raise SystemExit(f"CAS concurrency check failed: expected {expected}, got {actual}")
        print(f"PASS: two independent GitHub runners preserved all {expected} increments.")

    elif args.mode == "cleanup":
        adapter.delete(args.key)
        print("Live-CAS test key cleanup requested.")


if __name__ == "__main__":
    main()
