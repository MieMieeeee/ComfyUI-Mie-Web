"""Character and scene assets: list, read, write, delete.

Everything goes through ``mie_craft.assets.library`` - the same
implementation the ComfyUI nodes use, so the web app and the plugin can
never drift apart. The web app adds only the two things the library
deliberately leaves out: turning an uploaded file into the bytes the
library stores (PNG for images, WAV for audio).

Two things to keep in mind:

  * ``plugin_root`` must be passed on every call. The library's default
    is the package's own parent directory, which for a pip-installed
    mie_craft is site-packages - the user's library would vanish.
  * The library writes audio as ``NN.wav``, so an uploaded MP3 has to be
    converted before it is handed over, or the file on disk lies about
    its contents.
"""

from __future__ import annotations

import io
import os
import pathlib

from mie_craft.assets import library as _library
from mie_craft.assets import script_asset as _script_asset

from app import config


def plugin_root() -> pathlib.Path:
    """The ComfyUI pack that owns the library."""
    return config.PLUGIN_ROOT


def library_dir() -> str:
    """The library root, as the library itself resolves it."""
    return _library.resolve_library_dir("", plugin_root=plugin_root())


def _library_kwargs() -> dict:
    return {"plugin_root": plugin_root()}


# --------------------------------------------------------------------------- #
# listing
# --------------------------------------------------------------------------- #

def list_assets() -> dict:
    """Every character, scene and storyboard, with their counts.

    ``list_assets_payload`` never raises - it reports the problem in the
    payload - so a broken library still produces a page.
    """
    payload = _library.list_assets_payload(library_dir(), **_library_kwargs())
    payload = _script_asset.augment_assets_payload(payload, library_dir())
    payload["library_dir"] = library_dir()
    return payload


def list_characters() -> list[str]:
    """The character names, as a list (the library returns a string)."""
    result = _library.list_characters(library_dir(), **_library_kwargs())
    return [n for n in result.get("names", "").splitlines() if n.strip()]


def list_scenes() -> list[str]:
    result = _library.list_scenes(library_dir(), **_library_kwargs())
    return [n for n in result.get("names", "").splitlines() if n.strip()]


def list_storyboards() -> list[str]:
    result = _script_asset.list_storyboards(library_dir())
    return [n for n in result.get("names", "").splitlines() if n.strip()]


# --------------------------------------------------------------------------- #
# one asset
# --------------------------------------------------------------------------- #

def _png_data_url(png_bytes: bytes) -> str:
    import base64
    return "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")


def get_character(name: str) -> dict:
    """One character's metadata, its portrait and its audio clips."""
    data = _library.load_character(library_dir(), name, **_library_kwargs())
    images = data.get("png_bytes_list") or []
    return {
        "kind": "character",
        "name": data.get("name", name),
        "description": data.get("description", ""),
        "voice": data.get("voice", ""),
        "image_count": len(images),
        "audio_count": len(data.get("audio_bytes_list") or []),
        "image": _png_data_url(images[0]) if images else "",
        "images": [_png_data_url(b) for b in images],
        "audio_exts": data.get("audio_exts") or [],
    }


def get_scene(name: str) -> dict:
    """One scene's metadata and its picture."""
    data = _library.load_scene(library_dir(), name, **_library_kwargs())
    images = data.get("png_bytes_list") or []
    return {
        "kind": "scene",
        "name": data.get("name", name),
        "description": data.get("description", ""),
        "ambience": data.get("ambience", ""),
        "image_count": len(images),
        "image": _png_data_url(images[0]) if images else "",
        "images": [_png_data_url(b) for b in images],
    }


def get_asset_meta(name: str, kind: str) -> dict:
    """The cheap metadata read - no image bytes."""
    return _library.read_asset_meta(library_dir(), name, kind, **_library_kwargs())


# --------------------------------------------------------------------------- #
# writing
# --------------------------------------------------------------------------- #

def to_png_bytes(raw: bytes) -> bytes:
    """Turn an uploaded image into PNG bytes.

    The library stores PNG and checks that all the frames of one asset
    share a resolution, so anything else has to be converted.
    """
    from PIL import Image
    with Image.open(io.BytesIO(raw)) as img:
        img = img.convert("RGBA") if img.mode in ("P", "LA", "RGBA") else img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()


def to_wav_bytes(raw: bytes) -> bytes:
    """Turn an uploaded clip into WAV bytes.

    The library names the file ``NN.wav`` no matter what it is given, so
    an MP3 handed over as-is would be a lie on disk.
    """
    if raw[:4] == b"RIFF" and raw[8:12] == b"WAVE":
        return raw
    try:
        import soundfile
    except ImportError:
        raise ValueError(
            "reading this audio format needs the soundfile package "
            "(pip install soundfile)")
    data, rate = soundfile.read(io.BytesIO(raw), dtype="float32", always_2d=False)
    if data.ndim > 1:
        data = data.mean(axis=1)
    buf = io.BytesIO()
    soundfile.write(buf, data, rate, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def save_character(name: str, description: str, voice: str,
                   image_raw: bytes = None, audio_raw: bytes = None) -> dict:
    """Create or update a character.

    ``image_raw`` / ``audio_raw`` of None mean "keep what is on disk", so
    editing the description never drops the portrait.
    """
    png_bytes = None
    if image_raw is not None:
        png_bytes = [to_png_bytes(image_raw)]
    wav_bytes = None
    if audio_raw is not None:
        wav_bytes = [to_wav_bytes(audio_raw)]
    return _library.save_character(
        library_dir(), name, description, voice,
        png_bytes_list=png_bytes, wav_bytes_list=wav_bytes, **_library_kwargs())


def save_scene(name: str, description: str, ambience: str = None,
               image_raw: bytes = None) -> dict:
    """Create or update a scene.

    ``ambience`` of None keeps the stored value; an empty string clears
    it. That is the library's convention, not the usual one.
    """
    png_bytes = None
    if image_raw is not None:
        png_bytes = [to_png_bytes(image_raw)]
    return _library.save_scene(
        library_dir(), name, description, png_bytes_list=png_bytes,
        ambience=ambience, **_library_kwargs())


def delete_character(name: str) -> dict:
    return _library.delete_character(library_dir(), name, **_library_kwargs())


def delete_scene(name: str) -> dict:
    return _library.delete_scene(library_dir(), name, **_library_kwargs())


# --------------------------------------------------------------------------- #
# script assets
# --------------------------------------------------------------------------- #

def get_storyboard(name: str) -> dict:
    """One script asset: its JSON, its preview and its requirements."""
    cleaned, path = _script_asset.load_storyboard(library_dir(), name)
    meta = _script_asset.read_storyboard_meta(library_dir(), name)
    return {
        "name": cleaned.get("name", name),
        "path": path,
        "version": cleaned.get("version"),
        "json": cleaned,
        "preview": _script_asset.storyboard_preview(cleaned),
        "requirements": meta.get("requirements") or [],
        "sections": meta.get("sections") or [],
    }


def save_storyboard(payload: dict) -> dict:
    """Validate and write a script asset."""
    cleaned, path, status = _script_asset.save_storyboard(library_dir(), payload)
    return {
        "name": cleaned.get("name", ""),
        "path": path,
        "status": status,
        "preview": _script_asset.storyboard_preview(cleaned),
    }


def delete_storyboard(name: str) -> dict:
    return _script_asset.delete_storyboard(library_dir(), name)


def validate_storyboard(payload: dict) -> dict:
    """Check a script asset without writing it.

    Returns the errors and the render-risk warnings separately: an error
    means the contract rejects it, a warning means it will render but
    something is tight.
    """
    from mie_craft.script import contract
    try:
        cleaned = contract.validate_v2(payload)
    except ValueError as exc:
        return {"ok": False, "errors": [str(exc)], "warnings": []}
    warnings = contract.storyboard_warnings(cleaned)
    return {"ok": True, "errors": [], "warnings": warnings, "json": cleaned}
