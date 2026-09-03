"""App / user-data / workspace paths. Works from source, frozen, and FHS installs."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def bundle_dir() -> Path:
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return app_dir()


def _xdg_home(env_key: str, fallback: Path) -> Path:
    raw = (os.environ.get(env_key) or "").strip()
    if raw:
        return Path(raw).expanduser() / "sm0l"
    return fallback / "sm0l"


def user_data() -> Path:
    """Sessions and other app data: $XDG_DATA_HOME/sm0l or ~/.local/share/sm0l."""
    base = _xdg_home("XDG_DATA_HOME", Path.home() / ".local" / "share")
    base.mkdir(parents=True, exist_ok=True)
    (base / "sessions").mkdir(exist_ok=True)
    return base


def sessions_dir() -> Path:
    p = user_data() / "sessions"
    p.mkdir(parents=True, exist_ok=True)
    return p


def config_dir() -> Path:
    """Settings: $XDG_CONFIG_HOME/sm0l or ~/.config/sm0l."""
    base = _xdg_home("XDG_CONFIG_HOME", Path.home() / ".config")
    base.mkdir(parents=True, exist_ok=True)
    return base


def config_path() -> Path:
    return config_dir() / "config.json"


def default_workspace() -> Path:
    p = Path.home() / "sm0l_workspace"
    p.mkdir(parents=True, exist_ok=True)
    return p


def share_dirs() -> list[Path]:
    """Installed share trees (user then system) that may hold assets."""
    dirs: list[Path] = []
    data_home = (os.environ.get("XDG_DATA_HOME") or "").strip()
    dirs.append(Path(data_home).expanduser() / "sm0l" if data_home else Path.home() / ".local" / "share" / "sm0l")
    extra = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    for raw in extra.split(":"):
        raw = raw.strip()
        if raw:
            dirs.append(Path(raw).expanduser() / "sm0l")
    return dirs


def asset(*parts: str) -> Path | None:
    bases = [bundle_dir(), app_dir(), bundle_dir() / "_internal"]
    if is_frozen():
        bases.append(Path(sys.executable).resolve().parent / "_internal")
    bases.extend(share_dirs())
    seen: set[Path] = set()
    for base in bases:
        try:
            base = base.resolve()
        except OSError:
            continue
        if base in seen:
            continue
        seen.add(base)
        cand = base.joinpath(*parts)
        if cand.is_file():
            return cand
        cand = base / "assets" / Path(*parts).name
        if cand.is_file():
            return cand
    return None
