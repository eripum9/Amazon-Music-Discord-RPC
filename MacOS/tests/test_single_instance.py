# MIT License - Copyright (c) 2026 eripum9

import time

import pytest

from MacOS.single_instance import SingleInstance


def test_only_one_instance_can_acquire_and_commands_reach_owner(tmp_path):
    commands = []
    owner = SingleInstance(commands.append, directory=tmp_path)
    second = SingleInstance(directory=tmp_path)
    try:
        assert owner.acquire() is True
        assert second.acquire() is False
        assert second.notify("settings") is True
        deadline = time.monotonic() + 2
        while not commands and time.monotonic() < deadline:
            time.sleep(0.01)
        assert commands == ["settings"]
    finally:
        second.close()
        owner.close()


def test_owner_can_be_reacquired_after_clean_close(tmp_path):
    first = SingleInstance(directory=tmp_path)
    assert first.acquire() is True
    first.close()
    replacement = SingleInstance(directory=tmp_path)
    try:
        assert replacement.acquire() is True
    finally:
        replacement.close()


def test_rejects_unknown_commands(tmp_path):
    instance = SingleInstance(directory=tmp_path)
    with pytest.raises(ValueError):
        instance.notify("run-arbitrary-command")


def test_refuses_to_replace_regular_file_at_socket_path(tmp_path):
    instance = SingleInstance(directory=tmp_path)
    instance.socket_path.write_text("do not delete", encoding="utf-8")
    with pytest.raises(RuntimeError, match="untrusted"):
        instance.acquire()
    assert instance.socket_path.read_text(encoding="utf-8") == "do not delete"
    instance.socket_path.unlink()
    instance.close()
