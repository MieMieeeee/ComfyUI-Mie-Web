"""LLM platform and model settings.

The API keys live in the ComfyUI pack's ``mie_llm_keys.json`` - the SAME
file the plugin's nodes read, so a key set here is live for the nodes
immediately. That file is flat: platform key name -> token string.

The chosen MODELS cannot live there: the keys file holds tokens only, and
the model is a node widget. They live in the web app's own settings,
which also holds the platform the app treats as current.

Note the file path: ``mie_llm.utils.load_plugin_config`` resolves a bare
file name against the INSTALLED PACKAGE's parent directory, which for a
pip-installed mie_llm is site-packages. The plugin root is not there. So
the web app reads and writes the file itself and hands the connectors an
absolute path.
"""

from __future__ import annotations

import json

from mie_llm import platforms as _platforms

from app import config

#: Keys that are not platforms.
RESERVED_KEYS = ("_comment",)


def _settings() -> dict:
    try:
        return json.loads(config.SETTINGS_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_settings(data: dict) -> None:
    config.ensure_dirs()
    config.SETTINGS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_keys() -> dict:
    """The plugin's keys file, as {key: token}."""
    try:
        raw = json.loads(config.LLM_KEYS_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {k: v for k, v in raw.items() if k not in RESERVED_KEYS}


def write_keys(keys: dict) -> None:
    """Write the keys file, keeping any comment line it had."""
    existing = {}
    try:
        existing = json.loads(config.LLM_KEYS_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        existing = {}
    if not isinstance(existing, dict):
        existing = {}
    merged = {k: v for k, v in existing.items() if k in RESERVED_KEYS}
    merged.update({k: v for k, v in keys.items() if k not in RESERVED_KEYS})
    config.LLM_KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.LLM_KEYS_FILE.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")


def mask(token: str) -> str:
    """A token as it should be shown: the head, the tail, the length."""
    token = (token or "").strip()
    if not token:
        return ""
    if len(token) <= 12:
        return "*" * len(token)
    return "%s…%s (%d)" % (token[:6], token[-4:], len(token))


def endpoint_of(row: dict) -> str:
    """Where this platform's connector talks."""
    connector = _platforms.connector_class(row)
    url = getattr(connector, "api_url", None) or getattr(connector, "base_url", None)
    if not url and row.get("host"):
        return hosts().get(row["key"], "")
    return url or ""


def hosts() -> dict:
    """The local servers, keyed by platform key."""
    saved = _settings()
    return dict(saved.get("hosts") or {})


def models() -> dict:
    """The chosen model per platform key."""
    saved = _settings()
    return dict(saved.get("models") or {})


def current_platform() -> str:
    """The platform the app treats as current."""
    saved = _settings()
    return str(saved.get("current_platform") or "")


def model_for(config_key: str) -> str:
    """The model to use for one platform: the user's choice, else the
    platform's own default."""
    row = next((r for r in _platforms.PLATFORMS if r["key"] == config_key), None)
    chosen = models().get(config_key)
    if chosen:
        return chosen
    return (row or {}).get("default", "")


def list_platforms() -> list[dict]:
    """Every platform, with its endpoint, models and key state."""
    keys = read_keys()
    chosen_models = models()
    current = current_platform()
    out = []
    for row in _platforms.PLATFORMS:
        token = keys.get(row["key"], "") or ""
        out.append({
            "key": row["key"],
            "name": row["name"],
            "connector": row["connector"],
            "node": row["node"],
            "endpoint": endpoint_of(row),
            "models": row.get("models") or [],
            "default_model": row.get("default", ""),
            "model": chosen_models.get(row["key"]) or row.get("default", ""),
            "needs_key": not row.get("host"),
            "has_key": bool(token),
            "key_masked": mask(token),
            "host": row.get("host", False),
            "current": row["key"] == current,
        })
    return out


def set_key(config_key: str, token: str) -> dict:
    """Store one platform's token in the plugin's keys file."""
    keys = read_keys()
    keys[config_key] = (token or "").strip()
    write_keys(keys)
    return {"key": config_key, "has_key": bool(keys[config_key]),
            "key_masked": mask(keys[config_key])}


def set_model(config_key: str, model: str) -> dict:
    """Store the chosen model for one platform."""
    saved = _settings()
    chosen = dict(saved.get("models") or {})
    chosen[config_key] = (model or "").strip()
    saved["models"] = chosen
    _save_settings(saved)
    return {"key": config_key, "model": chosen[config_key]}


def set_current(config_key: str) -> dict:
    """Choose the platform the app treats as current."""
    saved = _settings()
    saved["current_platform"] = config_key
    _save_settings(saved)
    return {"current_platform": config_key}


def set_host(config_key: str, host: str) -> dict:
    """Store a local server's address (Ollama)."""
    saved = _settings()
    local = dict(saved.get("hosts") or {})
    local[config_key] = (host or "").strip()
    saved["hosts"] = local
    _save_settings(saved)
    return {"key": config_key, "host": local[config_key]}


def build_connector(row: dict, model: str = ""):
    """Instantiate a platform's connector, wired to the plugin's keys.

    The key comes from the keys file (the plugin's), so a key set in the
    plugin is the same key the app shows.
    """
    connector = _platforms.connector_class(row)
    token = read_keys().get(row["key"], "") or ""
    model = model or model_for(row["key"])
    kwargs = {
        "config_file": str(config.LLM_KEYS_FILE),
        "config_key": row["key"],
        "prefer_local_config": True,
    }
    if row.get("host"):
        host = hosts().get(row["key"]) or "http://127.0.0.1:11434"
        return connector(host, model, api_token=token or "ollama", **kwargs)
    if row["connector"] == "GeneralLLMServiceConnector":
        # The generic one has no endpoint of its own - the user gives it.
        return connector(endpoint_of(row) or token, token, model, **kwargs)
    return connector(token, model, **kwargs)


def test_connection(config_key: str, model: str = "", prompt: str = "") -> dict:
    """Call the platform once and report what came back.

    This is a real network call - it is only ever made because the user
    asked for it.
    """
    row = next((r for r in _platforms.PLATFORMS if r["key"] == config_key), None)
    if row is None:
        return {"ok": False, "error": "unknown platform %r" % config_key}
    if row.get("host"):
        host = hosts().get(row["key"]) or "http://127.0.0.1:11434"
    if not row.get("host") and not read_keys().get(row["key"]):
        return {"ok": False, "error": "no API key for %s" % row["name"]}
    try:
        connector = build_connector(row, model)
    except Exception as exc:  # noqa: BLE001 - reported to the user
        return {"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)}
    messages = [{"role": "user", "content": prompt or "ping"}]
    try:
        answer = connector.invoke(messages)
    except Exception as exc:  # noqa: BLE001 - the provider's error is the answer
        return {"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)}
    return {
        "ok": True,
        "answer": (answer or "")[:500],
        "model": getattr(connector, "model", ""),
        "finish_reason": getattr(connector, "last_finish_reason", ""),
    }
