# MIT License - Copyright (c) 2026 eripum9

import os
import subprocess


def _ps_literal(value):
    return "'" + str(value or "").replace("'", "''") + "'"


def _powershell_executable():
    windows_dir = os.environ.get("SystemRoot") or os.environ.get("WINDIR") or r"C:\Windows"
    candidates = [
        os.path.join(windows_dir, "System32", "WindowsPowerShell", "v1.0", "powershell.exe"),
        os.path.join(windows_dir, "Sysnative", "WindowsPowerShell", "v1.0", "powershell.exe"),
        os.path.join(windows_dir, "SysWOW64", "WindowsPowerShell", "v1.0", "powershell.exe"),
        "powershell.exe",
    ]
    for candidate in candidates:
        if os.path.isabs(candidate):
            if os.path.exists(candidate):
                return candidate
        else:
            return candidate
    return "powershell.exe"


def _run_dialog(script):
    completed = subprocess.run(
        [_powershell_executable(), "-NoProfile", "-STA", "-Command", script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=0x08000000 if os.name == "nt" else 0,
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "File dialog failed").strip())
    return completed.stdout.strip()


def save_file_dialog(title, filename, default_ext, filter_text, initial_dir=""):
    script = f"""
Add-Type -AssemblyName System.Windows.Forms
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$dialog = New-Object System.Windows.Forms.SaveFileDialog
$dialog.Title = {_ps_literal(title)}
$dialog.FileName = {_ps_literal(filename)}
$dialog.DefaultExt = {_ps_literal(default_ext)}
$dialog.Filter = {_ps_literal(filter_text)}
$dialog.AddExtension = $true
$dialog.OverwritePrompt = $true
if ({_ps_literal(initial_dir)} -and (Test-Path -LiteralPath {_ps_literal(initial_dir)})) {{
    $dialog.InitialDirectory = {_ps_literal(initial_dir)}
}}
if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {{
    Write-Output $dialog.FileName
}}
"""
    return _run_dialog(script)


def open_file_dialog(title, filter_text, initial_dir=""):
    script = f"""
Add-Type -AssemblyName System.Windows.Forms
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$dialog = New-Object System.Windows.Forms.OpenFileDialog
$dialog.Title = {_ps_literal(title)}
$dialog.Filter = {_ps_literal(filter_text)}
$dialog.CheckFileExists = $true
$dialog.Multiselect = $false
if ({_ps_literal(initial_dir)} -and (Test-Path -LiteralPath {_ps_literal(initial_dir)})) {{
    $dialog.InitialDirectory = {_ps_literal(initial_dir)}
}}
if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {{
    Write-Output $dialog.FileName
}}
"""
    return _run_dialog(script)
