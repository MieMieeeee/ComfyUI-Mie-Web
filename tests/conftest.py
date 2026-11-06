"""Shared fixtures.

The tests must not touch the real asset library or the real keys file, so
every test gets a temporary plugin root with an empty library in it.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app import config  # noqa: E402


@pytest.fixture()
def plugin_root(tmp_path, monkeypatch):
    """A throwaway plugin root with an empty asset library."""
    root = tmp_path / "plugin"
    (root / "asset_library" / "characters").mkdir(parents=True)
    (root / "asset_library" / "scenes").mkdir(parents=True)
    (root / "asset_library" / "storyboards").mkdir(parents=True)
    monkeypatch.setattr(config, "PLUGIN_ROOT", root)
    monkeypatch.setattr(config, "LLM_KEYS_FILE", root / "mie_llm_keys.json")
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setenv("MIE_PLUGIN_ROOT", str(root))
    return root


@pytest.fixture()
def client(plugin_root):
    """A Flask test client bound to the throwaway plugin root."""
    from app.flask_app import create_app
    return create_app().test_client()


#: A minimal PNG and a minimal WAV, made rather than hand-written: a
#: hex literal that is one byte off fails deep inside PIL or libsndfile,
#: which tells you nothing about the code under test.
def _png_bytes(width: int = 4, height: int = 4) -> bytes:
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGBA", (width, height), (255, 0, 0, 255)).save(buf, format="PNG")
    return buf.getvalue()


def _wav_bytes(seconds: float = 0.25, rate: int = 16000) -> bytes:
    import io
    import wave
    frames = int(seconds * rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(bytes(2 * frames))
    return buf.getvalue()


PNG_1x1 = _png_bytes()
WAV_1S = _wav_bytes()
