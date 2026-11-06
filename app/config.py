"""Paths and settings for the ComfyUI-Mie web front end.

Everything the app touches on disk is named here, so a deployment is a
matter of environment variables rather than code edits. The defaults are
this machine's layout (see F:/Mie-Skills/AGENTS.md).
"""

from __future__ import annotations

import os
import pathlib

#: The web app's own root.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

#: The ComfyUI pack that owns the asset library and the LLM keys. The
#: library lives in <pack>/asset_library, and the keys file sits next to
#: the pack's README.
PLUGIN_ROOT = pathlib.Path(
    os.environ.get(
        "MIE_PLUGIN_ROOT",
        r"C:\PP\V9\V9-Large\ComfyUI_Mie_2026_V9.0_Large\ComfyUI\custom_nodes\comfyui_mienodes",
    )
)

#: The LLM platform keys. It lives in the pack, NOT next to the installed
#: ``mie_llm`` package: ``mie_llm.utils.load_plugin_config`` resolves a
#: bare file name against the package's parent directory, which for a
#: pip-installed package is site-packages. The web app therefore reads and
#: writes the file itself and hands the connectors an absolute path.
LLM_KEYS_FILE = pathlib.Path(
    os.environ.get("MIE_LLM_KEYS_FILE", str(PLUGIN_ROOT / "mie_llm_keys.json"))
)

#: The web app's own settings (theme choice, ComfyUI URL, ...).
SETTINGS_FILE = pathlib.Path(
    os.environ.get(
        "MIE_WEB_SETTINGS",
        str(pathlib.Path(os.environ.get("APPDATA", pathlib.Path.home()))
            / "ComfyUI-Mie-Web" / "settings.json"),
    )
)

#: ComfyUI's address. The web app never starts ComfyUI itself; the
#: launcher does (see F:/Mie-Skills/AGENTS.md).
COMFYUI_URL = os.environ.get("MIE_COMFYUI_URL", "http://127.0.0.1:8188")

#: The LAN box. It is often off, so the app must treat it as optional.
LAN_COMFYUI_URL = os.environ.get("MIE_LAN_COMFYUI_URL", "http://192.168.31.150:8188")

#: Where uploaded assets go. Same-machine deployment (the plan's D8): the
#: role portraits and voice samples land in ComfyUI's input/ directory.
COMFYUI_ROOT = pathlib.Path(
    os.environ.get(
        "MIE_COMFYUI_ROOT",
        r"C:\PP\V9\V9-Large\ComfyUI_Mie_2026_V9.0_Large\ComfyUI",
    )
)

#: The web app listens here. ComfyUI keeps 8188; the plan's D2 says the
#: product layer picks a free port and binds 0.0.0.0 for the LAN.
WEB_HOST = os.environ.get("MIE_WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.environ.get("MIE_WEB_PORT", "8199"))

#: Never reload: a second process would fight over the render queue.
WEB_DEBUG = os.environ.get("MIE_WEB_DEBUG", "0") == "1"

#: The workflow the video page runs. It is the one the engine ships, and
#: it is the new-architecture one: the engine reads the script asset and
#: assembles the plan, and the chain runs the |MieH3 nodes.
DEFAULT_WORKFLOW = pathlib.Path(
    os.environ.get(
        "MIE_WEB_WORKFLOW",
        str(REPO_ROOT / "presets" / "mie_h3_storyboard_movie.api.json"),
    )
)

#: Where a finished render's files are collected from.
OUTPUT_SUBDIRS = ("live_storyboards", "h3_chains")


def ensure_dirs() -> None:
    """Create the directories the app writes into."""
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
