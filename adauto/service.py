"""
OS service management for adauto.
Windows : registry autorun via VBScript launcher
Linux   : systemd user unit
macOS   : launchd plist

Usage:
    adauto service install
    adauto service start
    adauto service stop
    adauto service status
    adauto service uninstall
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

APP_NAME   = "adauto"
PYTHON_EXE = sys.executable


# ── Windows ───────────────────────────────────────────────────────────────────

def _win_vbs_path() -> Path:
    return Path.home() / ".adauto" / "start_adauto.vbs"


def _win_install() -> None:
    vbs = _win_vbs_path()
    vbs.parent.mkdir(parents=True, exist_ok=True)
    vbs.write_text(
        f'Set WshShell = CreateObject("WScript.Shell")\n'
        f'WshShell.Run "{PYTHON_EXE} -m adauto serve", 0, False\n'
    )
    # Register in HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run
    import winreg
    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0, winreg.KEY_SET_VALUE,
    )
    winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'wscript.exe "{vbs}"')
    winreg.CloseKey(key)
    print(f"[service] installed (Windows autorun). Reboot or run: wscript.exe \"{vbs}\"")


def _win_uninstall() -> None:
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE,
        )
        winreg.DeleteValue(key, APP_NAME)
        winreg.CloseKey(key)
    except FileNotFoundError:
        pass
    vbs = _win_vbs_path()
    if vbs.exists():
        vbs.unlink()
    print("[service] uninstalled")


def _win_start() -> None:
    vbs = _win_vbs_path()
    if not vbs.exists():
        print("[service] not installed. Run: adauto service install")
        return
    subprocess.Popen(["wscript.exe", str(vbs)])
    print("[service] started")


def _win_stop() -> None:
    subprocess.run(
        ["powershell", "-Command",
         f"Get-Process -Name python* | Where-Object {{$_.CommandLine -like '*adauto*'}} | Stop-Process -Force"],
        capture_output=True,
    )
    print("[service] stopped")


def _win_status() -> None:
    result = subprocess.run(
        ["powershell", "-Command",
         "Get-Process python* 2>$null | Select-Object Id,CPU,WorkingSet"],
        capture_output=True, text=True,
    )
    print(result.stdout or "[service] not running")


# ── Linux (systemd) ───────────────────────────────────────────────────────────

def _systemd_unit_path() -> Path:
    return Path.home() / ".config" / "systemd" / "user" / f"{APP_NAME}.service"


def _linux_install() -> None:
    unit = _systemd_unit_path()
    unit.parent.mkdir(parents=True, exist_ok=True)
    unit.write_text(
        f"[Unit]\n"
        f"Description=adauto marketing automation server\n"
        f"After=network.target\n\n"
        f"[Service]\n"
        f"ExecStart={PYTHON_EXE} -m adauto serve\n"
        f"Restart=on-failure\n"
        f"RestartSec=5\n\n"
        f"[Install]\n"
        f"WantedBy=default.target\n"
    )
    subprocess.run(["systemctl", "--user", "daemon-reload"])
    subprocess.run(["systemctl", "--user", "enable", APP_NAME])
    print(f"[service] installed. Run: adauto service start")


def _linux_uninstall() -> None:
    subprocess.run(["systemctl", "--user", "disable", APP_NAME], capture_output=True)
    p = _systemd_unit_path()
    if p.exists():
        p.unlink()
    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
    print("[service] uninstalled")


def _linux_start() -> None:
    subprocess.run(["systemctl", "--user", "start", APP_NAME])


def _linux_stop() -> None:
    subprocess.run(["systemctl", "--user", "stop", APP_NAME])


def _linux_status() -> None:
    subprocess.run(["systemctl", "--user", "status", APP_NAME])


# ── macOS (launchd) ───────────────────────────────────────────────────────────

def _plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"com.adauto.plist"


def _macos_install() -> None:
    plist = _plist_path()
    plist.parent.mkdir(parents=True, exist_ok=True)
    plist.write_text(
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        f'"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        f'<plist version="1.0"><dict>\n'
        f'  <key>Label</key><string>com.adauto</string>\n'
        f'  <key>ProgramArguments</key><array>'
        f'<string>{PYTHON_EXE}</string><string>-m</string><string>adauto</string><string>serve</string></array>\n'
        f'  <key>RunAtLoad</key><true/>\n'
        f'  <key>KeepAlive</key><true/>\n'
        f'</dict></plist>\n'
    )
    subprocess.run(["launchctl", "load", str(plist)])
    print(f"[service] installed + started")


def _macos_uninstall() -> None:
    p = _plist_path()
    if p.exists():
        subprocess.run(["launchctl", "unload", str(p)], capture_output=True)
        p.unlink()
    print("[service] uninstalled")


def _macos_start() -> None:
    subprocess.run(["launchctl", "load", str(_plist_path())])


def _macos_stop() -> None:
    subprocess.run(["launchctl", "unload", str(_plist_path())])


def _macos_status() -> None:
    subprocess.run(["launchctl", "list", "com.adauto"])


# ── Dispatch ──────────────────────────────────────────────────────────────────

def service_cmd(action: str) -> None:
    """action: install | uninstall | start | stop | status"""
    p = sys.platform
    if p == "win32":
        dispatch = {
            "install": _win_install, "uninstall": _win_uninstall,
            "start": _win_start, "stop": _win_stop, "status": _win_status,
        }
    elif p == "darwin":
        dispatch = {
            "install": _macos_install, "uninstall": _macos_uninstall,
            "start": _macos_start, "stop": _macos_stop, "status": _macos_status,
        }
    else:
        dispatch = {
            "install": _linux_install, "uninstall": _linux_uninstall,
            "start": _linux_start, "stop": _linux_stop, "status": _linux_status,
        }

    fn = dispatch.get(action)
    if fn is None:
        print(f"[service] unknown action: {action}. Use: install|uninstall|start|stop|status")
        return
    fn()
