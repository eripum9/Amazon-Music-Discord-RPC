# MIT License - Copyright (c) 2026 eripum9

import json
import os
import tempfile

from self_tests import run_self_tests


def main():
    with tempfile.TemporaryDirectory(prefix="AmazonMusicRPC_SelfTests_") as directory:
        results = run_self_tests(directory, os.path.join(directory, "diagnostics.json"))
    print(json.dumps(results, indent=2))
    failed = [result for result in results if result.get("status") != "pass"]
    print(f"{len(results) - len(failed)}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
