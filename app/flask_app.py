"""The ComfyUI-Mie web front end.

Four pages, one per thing the short-drama pipeline needs:

  /llm      the LLM platforms and models
  /assets   the character and scene assets
  /scripts  the script assets
  /video    the render

Everything the pages show comes from the same packages the ComfyUI nodes
use (``mie_craft`` for the assets and the script contract, ``mie_llm``
for the platforms), so the web app and the plugin cannot disagree about
what an asset is or what a valid script is.
"""

from __future__ import annotations

import json
import os
import pathlib

from flask import Flask, abort, jsonify, render_template, request, send_from_directory

from app import config
from app.services import comfy, library, llm, runner, theme


def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024  # 64 MB uploads
    config.ensure_dirs()

    # The library resolves its root from this variable. It is read at call
    # time by mie_craft, but setting it here also keeps anything that
    # reads it at import time pointed at the right pack.
    os.environ.setdefault("MIE_PLUGIN_ROOT", str(config.PLUGIN_ROOT))

    # ------------------------------------------------------------------ #
    # pages
    # ------------------------------------------------------------------ #

    def page_context(**extra):
        theme_id = theme.load_saved_theme()
        context = {
            "theme_id": theme_id,
            "theme_css_content": theme.apply_theme(theme_id),
            "page_bg_color": theme.PAGE_BG_COLOR,
            "themes": theme.list_themes(),
        }
        context.update(extra)
        return context

    @app.route("/")
    def index():
        return render_template("video.html", **page_context(active="video"))

    @app.route("/llm")
    def llm_page():
        return render_template("llm.html", **page_context(active="llm"))

    @app.route("/assets")
    def assets_page():
        return render_template("assets.html", **page_context(active="assets"))

    @app.route("/scripts")
    def scripts_page():
        return render_template("scripts.html", **page_context(active="scripts"))

    @app.route("/video")
    def video_page():
        return render_template("video.html", **page_context(active="video"))

    # ------------------------------------------------------------------ #
    # theme and status
    # ------------------------------------------------------------------ #

    @app.route("/api/themes")
    def api_themes():
        return jsonify(theme.list_themes())

    @app.route("/api/theme", methods=["POST"])
    def api_set_theme():
        data = request.get_json(silent=True) or {}
        theme_id = theme.save_theme(str(data.get("theme") or ""))
        return jsonify({"theme": theme_id})

    @app.route("/api/comfy_status")
    def api_comfy_status():
        return jsonify(comfy.status())

    # ------------------------------------------------------------------ #
    # LLM platforms
    # ------------------------------------------------------------------ #

    @app.route("/api/llm/platforms")
    def api_llm_platforms():
        return jsonify({
            "platforms": llm.list_platforms(),
            "current": llm.current_platform(),
            "keys_file": str(config.LLM_KEYS_FILE),
        })

    @app.route("/api/llm/key", methods=["POST"])
    def api_llm_key():
        data = request.get_json(silent=True) or {}
        return jsonify(llm.set_key(str(data.get("key") or ""),
                                   str(data.get("token") or "")))

    @app.route("/api/llm/model", methods=["POST"])
    def api_llm_model():
        data = request.get_json(silent=True) or {}
        return jsonify(llm.set_model(str(data.get("key") or ""),
                                     str(data.get("model") or "")))

    @app.route("/api/llm/current", methods=["POST"])
    def api_llm_current():
        data = request.get_json(silent=True) or {}
        return jsonify(llm.set_current(str(data.get("key") or "")))

    @app.route("/api/llm/host", methods=["POST"])
    def api_llm_host():
        data = request.get_json(silent=True) or {}
        return jsonify(llm.set_host(str(data.get("key") or ""),
                                    str(data.get("host") or "")))

    @app.route("/api/llm/test", methods=["POST"])
    def api_llm_test():
        data = request.get_json(silent=True) or {}
        return jsonify(llm.test_connection(
            str(data.get("key") or ""), str(data.get("model") or ""),
            str(data.get("prompt") or "")))

    # ------------------------------------------------------------------ #
    # assets
    # ------------------------------------------------------------------ #

    @app.route("/api/assets")
    def api_assets():
        return jsonify(library.list_assets())

    @app.route("/api/assets/<kind>/<name>")
    def api_asset(kind, name):
        try:
            if kind == "character":
                return jsonify(library.get_character(name))
            if kind == "scene":
                return jsonify(library.get_scene(name))
        except (FileNotFoundError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 404
        abort(404)

    @app.route("/api/assets/<kind>", methods=["POST"])
    def api_save_asset(kind):
        # An upload is multipart, so the text fields arrive in
        # request.form - NOT in get_json(), which is empty for anything
        # that is not application/json. Both are accepted so the endpoint
        # works with a file and without one.
        data = request.get_json(silent=True) or {}
        form = request.form
        name = str(data.get("name") or form.get("name") or "")
        description = str(data.get("description") or form.get("description") or "")
        image_raw = _uploaded("image")
        audio_raw = _uploaded("audio")
        try:
            if kind == "character":
                result = library.save_character(
                    name, description,
                    str(data.get("voice") or form.get("voice") or ""),
                    image_raw=image_raw, audio_raw=audio_raw)
            elif kind == "scene":
                ambience = data.get("ambience", form.get("ambience"))
                result = library.save_scene(
                    name, description,
                    ambience=None if ambience is None else str(ambience),
                    image_raw=image_raw)
            else:
                abort(404)
        except (ValueError, FileNotFoundError) as exc:
            return jsonify({"error": str(exc)}), 400
        result.pop("png_bytes_list", None)
        result.pop("audio_bytes_list", None)
        return jsonify(result)

    @app.route("/api/assets/<kind>/<name>/delete", methods=["POST"])
    def api_delete_asset(kind, name):
        try:
            if kind == "character":
                return jsonify(library.delete_character(name))
            if kind == "scene":
                return jsonify(library.delete_scene(name))
        except (FileNotFoundError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 404
        abort(404)

    # ------------------------------------------------------------------ #
    # scripts
    # ------------------------------------------------------------------ #

    @app.route("/api/scripts")
    def api_scripts():
        return jsonify({"names": library.list_storyboards()})

    @app.route("/api/scripts/<name>")
    def api_script(name):
        try:
            return jsonify(library.get_storyboard(name))
        except (FileNotFoundError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 404

    @app.route("/api/scripts", methods=["POST"])
    def api_save_script():
        data = request.get_json(silent=True) or {}
        payload = data.get("json")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except ValueError as exc:
                return jsonify({"error": "the JSON does not parse: %s" % exc}), 400
        try:
            return jsonify(library.save_storyboard(payload))
        except (ValueError, FileNotFoundError) as exc:
            return jsonify({"error": str(exc)}), 400

    @app.route("/api/scripts/validate", methods=["POST"])
    def api_validate_script():
        data = request.get_json(silent=True) or {}
        payload = data.get("json")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except ValueError as exc:
                return jsonify({"ok": False, "errors": [str(exc)], "warnings": []})
        return jsonify(library.validate_storyboard(payload))

    @app.route("/api/scripts/<name>/delete", methods=["POST"])
    def api_delete_script(name):
        try:
            return jsonify(library.delete_storyboard(name))
        except (FileNotFoundError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 404

    @app.route("/api/scripts/<name>/plan", methods=["POST"])
    def api_script_plan(name):
        data = request.get_json(silent=True) or {}
        role_assets = {str(k): str(v) for k, v in (data.get("role_assets") or {}).items()}
        try:
            return jsonify(runner.plan_preview(name, role_assets))
        except (FileNotFoundError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400

    # ------------------------------------------------------------------ #
    # render
    # ------------------------------------------------------------------ #

    @app.route("/api/render/submit", methods=["POST"])
    def api_render_submit():
        data = request.get_json(silent=True) or {}
        role_assets = {str(k): str(v) for k, v in (data.get("role_assets") or {}).items()}
        try:
            record = runner.submit(
                str(data.get("script") or ""), role_assets,
                run_name=str(data.get("run_name") or ""),
                width=int(data.get("width") or 960),
                height=int(data.get("height") or 544),
                steps=int(data.get("steps") or 20),
                duration=int(data.get("duration") or 18))
        except (FileNotFoundError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400
        except comfy.ComfyUnavailable as exc:
            return jsonify({"error": str(exc)}), 502
        return jsonify(record)

    @app.route("/api/render/jobs")
    def api_render_jobs():
        return jsonify({"jobs": runner.jobs()})

    @app.route("/api/render/<job_id>")
    def api_render_job(job_id):
        return jsonify(runner.job(job_id))

    # ------------------------------------------------------------------ #
    # files
    # ------------------------------------------------------------------ #

    @app.route("/media/<path:relpath>")
    def media(relpath):
        """A finished render's file."""
        root = comfy.media_root()
        target = (root / relpath).resolve()
        if not str(target).startswith(str(root.resolve())):
            abort(403)
        if not target.is_file():
            abort(404)
        return send_from_directory(root, relpath)

    @app.route("/library/<path:relpath>")
    def library_file(relpath):
        """An asset's picture, straight from the library."""
        root = (config.PLUGIN_ROOT / "asset_library").resolve()
        target = (root / relpath).resolve()
        if not str(target).startswith(str(root)):
            abort(403)
        if not target.is_file():
            abort(404)
        return send_from_directory(root, relpath)

    return app


def _uploaded(field: str) -> bytes | None:
    """One uploaded file, as bytes; None when the field was not sent."""
    if field not in request.files:
        return None
    item = request.files[field]
    if not item or not item.filename:
        return None
    return item.read()


app = create_app()


if __name__ == "__main__":
    # Single process, no reloader: a second process would fight over the
    # render queue. The launcher-style start is in start_webui.bat.
    app.run(host=config.WEB_HOST, port=config.WEB_PORT,
            debug=config.WEB_DEBUG, use_reloader=False, threaded=True)
