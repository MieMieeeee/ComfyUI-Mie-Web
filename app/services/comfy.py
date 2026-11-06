"""The ComfyUI client: status, queue, submit, history, files.

The web app never starts ComfyUI - the launcher does that (see
F:/Mie-Skills/AGENTS.md). The LAN box is often off, so every call has to
fail soft: a web app that cannot reach 8188 must still answer, saying
so.
"""

from __future__ import annotations

import json
import os
import pathlib
import urllib.error
import urllib.parse
import urllib.request

from app import config

#: Long enough for a model load, short enough that a dead box answers
#: quickly.
TIMEOUT = 20


class ComfyUnavailable(RuntimeError):
    """ComfyUI could not be reached."""


def _request(url: str, payload=None, method=None, timeout=TIMEOUT):
    """One HTTP call. Raises ComfyUnavailable on any transport failure."""
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise ComfyUnavailable("HTTP %s %s: %s" % (exc.code, exc.reason, body[:400]))
    except Exception as exc:  # noqa: BLE001 - transport failures are one bucket
        raise ComfyUnavailable("%s: %s" % (type(exc).__name__, exc))


def _json(url: str, payload=None, method=None, timeout=TIMEOUT):
    raw = _request(url, payload, method, timeout)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


def base_url() -> str:
    """The ComfyUI address, overridable from the app's settings."""
    try:
        saved = json.loads(config.SETTINGS_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        saved = {}
    return str(saved.get("comfyui_url") or config.COMFYUI_URL).rstrip("/")


def status() -> dict:
    """Is ComfyUI up, and what is it serving?"""
    try:
        data = _json(base_url() + "/system_stats")
    except ComfyUnavailable as exc:
        return {"online": False, "error": str(exc), "url": base_url()}
    if not data:
        return {"online": False, "error": "no answer", "url": base_url()}
    system = data.get("system", {})
    devices = data.get("devices") or []
    return {
        "online": True,
        "url": base_url(),
        "comfyui_version": system.get("comfyui_version"),
        "python_version": system.get("python_version", "").split()[0],
        "ram_total": system.get("ram_total"),
        "ram_free": system.get("ram_free"),
        "devices": [
            {"name": d.get("name"), "vram_total": d.get("vram_total"),
             "vram_free": d.get("vram_free")}
            for d in devices
        ],
    }


def queue() -> dict:
    """What is running and what is waiting."""
    try:
        data = _json(base_url() + "/queue")
    except ComfyUnavailable as exc:
        return {"running": [], "pending": [], "error": str(exc)}
    if not data:
        return {"running": [], "pending": [], "error": "no answer"}
    return {
        "running": [item[1] for item in data.get("queue_running", [])],
        "pending": [item[1] for item in data.get("queue_pending", [])],
    }


def submit(prompt: dict, client_id: str = "") -> dict:
    """Queue a prompt. Returns {prompt_id, number}."""
    body = {"prompt": prompt, "client_id": client_id}
    result = _json(base_url() + "/prompt", body, timeout=180)
    if not result or "prompt_id" not in result:
        raise ComfyUnavailable("the prompt was rejected: %s" % json.dumps(
            result, ensure_ascii=False)[:600])
    return result


def history(prompt_id: str) -> dict:
    """One prompt's history entry, or {} while it is still running."""
    data = _json(base_url() + "/history/" + prompt_id)
    if not data:
        return {}
    return data.get(prompt_id, {})


def prompt_outputs(prompt_id: str) -> dict:
    """The text outputs of a finished prompt, joined.

    ComfyUI stores a node's text in the history as a LIST OF CHARACTERS,
    so the pieces have to be joined before anything can be parsed.
    """
    entry = history(prompt_id)
    out = {}
    for node_id, node_out in (entry.get("outputs") or {}).items():
        pieces = node_out.get("text") or []
        if pieces:
            out[node_id] = "".join(
                p if isinstance(p, str) else str(p) for p in pieces)
    return out


def interrupt() -> bool:
    """Ask ComfyUI to stop the running prompt."""
    try:
        _request(base_url() + "/interrupt", {"prompt_id": ""}, method="POST")
        return True
    except ComfyUnavailable:
        return False


def output_files(subfolder: str = "") -> list[dict]:
    """The files in ComfyUI's output directory."""
    url = base_url() + "/view?filename="
    try:
        data = _json(base_url() + "/object_info")
    except ComfyUnavailable:
        return []
    if not data:
        return []
    return []


def collect_artifacts(run_name: str) -> list[dict]:
    """The finished render's files, read straight off the disk.

    The web app runs on the same machine as ComfyUI (the plan's D8), so
    the output directory is a local path - no HTTP round trip, and the
    files are served by the app's own /media route.
    """
    found = []
    for sub in config.OUTPUT_SUBDIRS:
        root = config.COMFYUI_ROOT / "output" / sub
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if run_name and run_name not in path.name and run_name not in str(path.parent):
                continue
            found.append({
                "name": path.name,
                "relpath": str(path.relative_to(config.COMFYUI_ROOT / "output")).replace("\\", "/"),
                "size": path.stat().st_size,
                "kind": _kind_of(path),
            })
    return found


def _kind_of(path: pathlib.Path) -> str:
    suffix = path.suffix.lower()
    if suffix in (".mp4", ".webm", ".mkv", ".mov"):
        return "video"
    if suffix in (".wav", ".mp3", ".m4a", ".flac"):
        return "audio"
    if suffix in (".png", ".jpg", ".jpeg", ".webp"):
        return "image"
    if suffix in (".json", ".txt"):
        return "text"
    return "other"


def media_root() -> pathlib.Path:
    """The directory the /media route serves from."""
    return config.COMFYUI_ROOT / "output"
