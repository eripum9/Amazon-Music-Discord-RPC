# MIT License - Copyright (c) 2026 eripum9

import pytest

import release_artifact


@pytest.mark.parametrize("version", ["12.3.0", "13.0.0"])
def test_embedded_pillow_version_finds_semantic_version(monkeypatch, version):
    monkeypatch.setattr(
        release_artifact,
        "embedded_module_constants",
        lambda executable, module_name: (0, ("annotations",), version, None),
    )
    assert release_artifact.embedded_pillow_version("app.exe") == version


def test_embedded_pillow_version_rejects_missing_version(monkeypatch):
    monkeypatch.setattr(
        release_artifact,
        "embedded_module_constants",
        lambda executable, module_name: (None, "development"),
    )
    with pytest.raises(ValueError, match="could not be determined"):
        release_artifact.embedded_pillow_version("app.exe")
