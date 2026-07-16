# MIT License - Copyright (c) 2026 eripum9

import re
from pathlib import Path


VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


def embedded_module_constants(executable, module_name):
    from PyInstaller.archive.readers import CArchiveReader

    archive = CArchiveReader(str(Path(executable)))
    pyz = archive.open_embedded_archive("PYZ.pyz")
    code = pyz.extract(module_name)
    if code is None:
        raise ValueError(f"Embedded module not found: {module_name}")
    return tuple(code.co_consts)


def embedded_pillow_version(executable):
    for value in embedded_module_constants(executable, "PIL._version"):
        if isinstance(value, str) and VERSION_PATTERN.fullmatch(value):
            return value
    raise ValueError("The packaged Pillow version could not be determined")
