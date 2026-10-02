import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import requests


DEFAULT_VERSION = "0.9.0"


class UpdateError(RuntimeError):
    pass


def _resource_path(name):
    executable_dir = Path(sys.executable).resolve().parent
    external = executable_dir / name

    if external.exists():
        return external

    if hasattr(sys, "_MEIPASS"):
        bundled = Path(sys._MEIPASS) / name
        if bundled.exists():
            return bundled

    local = Path(__file__).resolve().parent / name
    if local.exists():
        return local

    return external


def get_current_version():
    path = _resource_path("version.txt")

    try:
        value = path.read_text(encoding="utf-8").strip()
        if value:
            return value.lstrip("vV")
    except Exception:
        pass

    return DEFAULT_VERSION


def load_update_config():
    path = _resource_path("update_config.json")

    default = {
        "github_owner": "CHANGE_ME",
        "github_repo": "ShinriTracker",
        "asset_name": "ShinriTracker.exe",
        "auto_check": True,
    }

    try:
        loaded = json.loads(
            path.read_text(encoding="utf-8")
        )
        if isinstance(loaded, dict):
            default.update(loaded)
    except Exception:
        pass

    return default


def is_update_configured():
    config = load_update_config()
    owner = str(config.get("github_owner", "")).strip()
    repo = str(config.get("github_repo", "")).strip()

    return bool(
        owner
        and repo
        and owner.upper() != "CHANGE_ME"
    )


def _version_tuple(value):
    parts = re.findall(r"\d+", str(value))

    if not parts:
        return (0,)

    return tuple(int(part) for part in parts[:4])


def is_newer_version(remote, current=None):
    if current is None:
        current = get_current_version()

    return _version_tuple(remote) > _version_tuple(current)


def check_for_update(timeout=10):
    config = load_update_config()

    if not is_update_configured():
        raise UpdateError(
            "Автообновление ещё не привязано к GitHub-репозиторию. "
            "Укажи github_owner/github_repo в update_config.json "
            "или собери Release через готовый GitHub Actions workflow."
        )

    owner = config["github_owner"]
    repo = config["github_repo"]

    url = (
        f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    )

    response = requests.get(
        url,
        timeout=timeout,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "ShinriTracker-Updater",
        },
    )

    if response.status_code == 404:
        return {
            "available": False,
            "reason": "no_release",
            "current_version": get_current_version(),
        }

    try:
        response.raise_for_status()
    except Exception as error:
        raise UpdateError(
            f"GitHub вернул ошибку {response.status_code}."
        ) from error

    release = response.json()
    tag = str(release.get("tag_name", "")).lstrip("vV")

    asset_name = config.get(
        "asset_name",
        "ShinriTracker.exe",
    )

    asset = None

    for item in release.get("assets", []):
        if item.get("name") == asset_name:
            asset = item
            break

    if asset is None:
        for item in release.get("assets", []):
            if str(item.get("name", "")).lower().endswith(".exe"):
                asset = item
                break

    return {
        "available": bool(tag and is_newer_version(tag)),
        "current_version": get_current_version(),
        "version": tag,
        "name": release.get("name") or release.get("tag_name") or tag,
        "notes": release.get("body") or "",
        "page_url": release.get("html_url") or "",
        "asset": asset,
    }


def download_update(update_info, progress_callback=None, timeout=30):
    asset = update_info.get("asset")

    if not asset:
        raise UpdateError(
            "В Release нет EXE-файла обновления."
        )

    url = asset.get("browser_download_url")

    if not url:
        raise UpdateError(
            "GitHub не вернул ссылку на файл обновления."
        )

    version = update_info.get("version") or "new"
    target = (
        Path(tempfile.gettempdir())
        / f"ShinriTracker_update_{version}.exe"
    )

    digest = hashlib.sha256()

    with requests.get(
        url,
        stream=True,
        timeout=timeout,
        headers={"User-Agent": "ShinriTracker-Updater"},
    ) as response:
        response.raise_for_status()

        total = int(response.headers.get("Content-Length", 0) or 0)
        downloaded = 0

        with open(target, "wb") as file:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue

                file.write(chunk)
                digest.update(chunk)
                downloaded += len(chunk)

                if progress_callback:
                    progress_callback(downloaded, total)

    expected_digest = str(asset.get("digest") or "").strip()

    if expected_digest.lower().startswith("sha256:"):
        expected_hash = expected_digest.split(":", 1)[1].strip().lower()
        actual_hash = digest.hexdigest().lower()

        if expected_hash and expected_hash != actual_hash:
            try:
                target.unlink()
            except OSError:
                pass

            raise UpdateError(
                "SHA-256 скачанного EXE не совпадает с GitHub Release."
            )

    return str(target)


def can_self_update():
    return bool(getattr(sys, "frozen", False)) and sys.platform.startswith("win")


def launch_update_replacer(downloaded_exe):
    if not can_self_update():
        raise UpdateError(
            "Автозамена работает только у собранного Windows EXE. "
            "При запуске из PyCharm можно проверить наличие обновления, "
            "но заменить исходники автоматически нельзя."
        )

    current_exe = Path(sys.executable).resolve()
    downloaded_exe = Path(downloaded_exe).resolve()
    pid = os.getpid()

    script = Path(tempfile.gettempdir()) / "shinri_tracker_update.bat"

    content = f'''@echo off\r\nsetlocal\r\n:waitloop\r\ntasklist /FI "PID eq {pid}" 2>NUL | find "{pid}" >NUL\r\nif not errorlevel 1 (\r\n  timeout /t 1 /nobreak >NUL\r\n  goto waitloop\r\n)\r\ncopy /Y "{downloaded_exe}" "{current_exe}" >NUL\r\nif errorlevel 1 (\r\n  start "" "{downloaded_exe}"\r\n) else (\r\n  start "" "{current_exe}"\r\n  del /Q "{downloaded_exe}" >NUL 2>NUL\r\n)\r\ndel "%~f0"\r\n'''

    script.write_text(
        content,
        encoding="utf-8",
    )

    creationflags = 0

    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        creationflags = subprocess.CREATE_NO_WINDOW

    subprocess.Popen(
        ["cmd.exe", "/c", str(script)],
        creationflags=creationflags,
        close_fds=True,
    )

    return True
