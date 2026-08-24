# MIT License - Copyright (c) 2026 eripum9

import sys


def pytest_ignore_collect(collection_path, config):
    parts = {part.casefold() for part in collection_path.parts}
    if "macos" in parts and "tests" in parts and sys.platform != "darwin":
        return True
    if "windows" in parts and "tests" in parts and sys.platform != "win32":
        return True
    return None
