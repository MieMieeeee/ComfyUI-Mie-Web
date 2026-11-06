"""The HTTP surface: every page and every API route."""

from __future__ import annotations

import io
import json

from app import config
from app.services import comfy, library

from .conftest import PNG_1x1
from .test_library import SCRIPT


def test_every_page_serves(client):
    for path in ("/", "/llm", "/assets", "/scripts", "/video"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert b"ComfyUI-Mie" in response.data, path


def test_the_theme_is_in_the_page(client):
    body = client.get("/").data.decode("utf-8")
    assert "theme-injector" in body
    assert "--bg-app" in body, "the design tokens must be injected"


def test_the_theme_is_not_double_wrapped(client):
    """A nested <style> is parsed as an invalid selector and dropped, so
    the page would render with the default tokens."""
    body = client.get("/").data.decode("utf-8")
    injector = body.split('<style id="theme-injector">')[1].split("</style>")[0]
    assert "<style" not in injector, injector[:120]
    assert injector.strip().startswith(":root")


def test_the_theme_can_be_chosen(client):
    response = client.post("/api/theme", json={"theme": "cyber-blue"})
    assert response.get_json()["theme"] == "cyber-blue"
    assert 'data-theme="cyber-blue"' in client.get("/").data.decode("utf-8")


def test_an_unknown_theme_falls_back(client):
    assert client.post("/api/theme", json={"theme": "nope"}).get_json()[
        "theme"] == "forest-island"


def test_the_asset_listing(client):
    payload = client.get("/api/assets").get_json()
    assert payload["ok"] is True
    assert "characters" in payload and "scenes" in payload


def test_a_character_can_be_created_and_read_back(client):
    response = client.post(
        "/api/assets/character",
        data={"name": "接口角色", "description": "描述", "voice": "male voice",
              "image": (io.BytesIO(PNG_1x1), "portrait.png")},
        content_type="multipart/form-data")
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["status"] == "created"

    data = client.get("/api/assets/character/接口角色").get_json()
    assert data["description"] == "描述"
    assert data["image"].startswith("data:image/png;base64,")


def test_a_missing_asset_is_a_404(client):
    assert client.get("/api/assets/character/不存在").status_code == 404


def test_a_script_can_be_saved_and_validated(client):
    response = client.post("/api/scripts", json={"json": json.dumps(SCRIPT)})
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["status"] == "created"

    names = client.get("/api/scripts").get_json()["names"]
    assert "测试剧本" in names

    check = client.post("/api/scripts/validate", json={"json": json.dumps(SCRIPT)})
    assert check.get_json()["ok"] is True


def test_a_broken_script_reports_the_contract_error(client):
    broken = json.loads(json.dumps(SCRIPT))
    broken["shots"][0]["events"][0]["text"] = "别的"
    result = client.post("/api/scripts/validate",
                          json={"json": json.dumps(broken)}).get_json()
    assert result["ok"] is False
    assert "source events differ" in result["errors"][0]


def test_the_platforms_are_listed(client):
    payload = client.get("/api/llm/platforms").get_json()
    assert len(payload["platforms"]) >= 20
    assert payload["keys_file"].endswith("mie_llm_keys.json")


def test_a_key_is_saved_through_the_api(client):
    response = client.post("/api/llm/key", json={"key": "minimax", "token": "sk-x"})
    assert response.get_json()["has_key"] is True
    assert client.post("/api/llm/model",
                       json={"key": "minimax", "model": "MiniMax-M3"}).get_json()[
                           "model"] == "MiniMax-M3"
    assert client.post("/api/llm/current",
                       json={"key": "minimax"}).get_json()[
                           "current_platform"] == "minimax"


def test_the_plan_preview_lists_the_roles(client):
    library.save_storyboard(dict(SCRIPT))
    response = client.post("/api/scripts/测试剧本/plan",
                           json={"role_assets": {"character_1": "甲"}})
    assert response.status_code == 200
    body = response.get_json()
    assert body["nodes"] > 20
    sockets = [r["socket"] for r in body["requirements"]]
    assert "character_1" in sockets


def test_a_reference_voice_role_must_be_wired(client):
    """The rule the assembler enforces: a role that borrows its voice
    from an asset needs that asset. A generated-voice role does not."""
    reference = json.loads(json.dumps(SCRIPT))
    reference["audio_mode"] = "reference"
    library.save_storyboard(reference)
    response = client.post("/api/render/submit",
                           json={"script": "测试剧本", "role_assets": {}})
    assert response.status_code == 400
    assert "character_1" in response.get_json()["error"]


def test_a_render_without_every_role_is_refused(client):
    library.save_storyboard(dict(SCRIPT))
    response = client.post("/api/render/submit",
                           json={"script": "测试剧本", "role_assets": {}})
    assert response.status_code == 400
    assert "character_1" in response.get_json()["error"]


def test_the_runs_on_disk_are_listed(client, tmp_path, monkeypatch):
    """The live job table is in memory, so a restart empties it. The
    renders are on disk and do not go anywhere, so they are indexed from
    there."""
    import json as _json
    root = tmp_path / "comfy"
    run = root / "output" / "h3_chains" / "sb_web_test" / "final"
    run.mkdir(parents=True)
    (run / "sb_web_test.mp4").write_bytes(b"movie")
    (run.parent.parent / "manifest.json").write_text(
        _json.dumps({"shots": [{"id": "scene_01"}]}), encoding="utf-8")
    monkeypatch.setattr(config, "COMFYUI_ROOT", root)

    runs = comfy.recent_runs()
    assert len(runs) == 1
    assert runs[0]["run_name"] == "sb_web_test"
    assert runs[0]["status"] == "success"
    assert runs[0]["video"].endswith("sb_web_test.mp4")
