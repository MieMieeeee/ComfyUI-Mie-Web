"""Theme loading: the design tokens plus the theme presets.

The tokens.css is the design system (colours, spacing, components) and
themes.json holds the presets that override a handful of accent tokens.
Both come from the reference web app, so the two front ends look the
same. The user's choice is persisted next to the app's settings.
"""

from __future__ import annotations

import json

from app import config

DEFAULT_THEME_ID = "forest-island"

#: Must match --bg-app in tokens.css, or the browser's own chrome
#: (address bar, status bar) shows a different colour than the page.
PAGE_BG_COLOR = "#0f1115"

_TOKENS_PATH = config.REPO_ROOT / "app" / "static" / "tokens.css"
_THEMES_PATH = config.REPO_ROOT / "app" / "presets" / "themes.json"


def _load_tokens_css() -> str:
    """The design-system stylesheet, verbatim.

    Read every time rather than cached: it is a cold asset (the browser
    asks for it too), and caching would mean a restart after every edit
    during development.
    """
    try:
        return _TOKENS_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def list_themes() -> list[dict]:
    """Every preset, as {id, name, desc, tokens}."""
    try:
        raw = json.loads(_THEMES_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        raw = {}
    out = []
    for tid, theme in raw.items():
        out.append({
            "id": tid,
            "name": theme.get("name", tid),
            "desc": theme.get("desc", ""),
            "tokens": theme.get("tokens", {}),
        })
    return out


def theme_tokens(theme_id: str) -> dict:
    for theme in list_themes():
        if theme["id"] == theme_id:
            return theme["tokens"]
    return {}


def _strip_style_tag(html: str) -> str:
    """Drop a leading <style> block, so the CSS can be injected as one."""
    start = html.find("<style")
    if start < 0:
        return html
    end = html.find("</style>", start)
    if end < 0:
        return html
    return html[:start] + html[end + len("</style>"):]


def apply_theme(theme_id: str) -> str:
    """The CSS for one preset: the token overrides.

    The BARE declarations, not a <style> block: the template already
    wraps this in ``<style id="theme-injector">``, and a nested
    ``<style>`` would be parsed as an invalid selector and dropped -
    the page would then render with the default tokens and the theme
    would look like it did nothing.
    """
    tokens = theme_tokens(theme_id)
    if not tokens:
        return ""
    declarations = "\n".join(
        "  %s: %s;" % (name, value) for name, value in tokens.items())
    return ":root{\n%s\n}" % declarations


def load_saved_theme() -> str:
    """The theme the user last chose, or the default."""
    try:
        saved = json.loads(config.SETTINGS_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, AttributeError):
        saved = {}
    theme_id = str(saved.get("theme") or DEFAULT_THEME_ID)
    known = {theme["id"] for theme in list_themes()}
    return theme_id if theme_id in known else DEFAULT_THEME_ID


def save_theme(theme_id: str) -> str:
    """Persist the chosen theme; returns the id actually stored."""
    known = {theme["id"] for theme in list_themes()}
    if theme_id not in known:
        theme_id = DEFAULT_THEME_ID
    config.ensure_dirs()
    try:
        saved = json.loads(config.SETTINGS_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        saved = {}
    saved["theme"] = theme_id
    config.SETTINGS_FILE.write_text(
        json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")
    return theme_id
