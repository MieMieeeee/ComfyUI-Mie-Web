"""The asset and script services."""

from __future__ import annotations

import json

import pytest

from app.services import library

from .conftest import PNG_1x1, WAV_1S


def test_empty_library_lists_nothing(plugin_root):
    payload = library.list_assets()
    assert payload["ok"] is True
    assert payload["characters"] == []
    assert payload["scenes"] == []
    assert payload["storyboards"] == []


def test_save_and_read_a_character(plugin_root):
    library.save_character("测试角色", "一个测试用的角色", "young female",
                           image_raw=PNG_1x1, audio_raw=WAV_1S)
    assert library.list_characters() == ["测试角色"]

    data = library.get_character("测试角色")
    assert data["description"] == "一个测试用的角色"
    assert data["voice"] == "young female"
    assert data["image_count"] == 1
    assert data["audio_count"] == 1
    assert data["image"].startswith("data:image/png;base64,")


def test_editing_keeps_the_media_when_none_is_given(plugin_root):
    library.save_character("测试角色", "第一版", "voice",
                           image_raw=PNG_1x1, audio_raw=WAV_1S)
    library.save_character("测试角色", "第二版", "voice")
    data = library.get_character("测试角色")
    assert data["description"] == "第二版"
    assert data["image_count"] == 1, "the portrait must survive a text edit"
    assert data["audio_count"] == 1, "the voice sample must survive too"


def test_a_new_character_needs_a_picture(plugin_root):
    with pytest.raises(ValueError):
        library.save_character("没有图", "描述", "voice")


def test_scenes_carry_an_ambience(plugin_root):
    library.save_scene("测试场景", "一个客厅", ambience="Quiet room tone",
                       image_raw=PNG_1x1)
    data = library.get_scene("测试场景")
    assert data["ambience"] == "Quiet room tone"
    assert data["image_count"] == 1


def test_ambience_none_keeps_and_empty_clears(plugin_root):
    library.save_scene("测试场景", "描述", ambience="Quiet room tone",
                       image_raw=PNG_1x1)
    library.save_scene("测试场景", "描述", ambience=None, image_raw=PNG_1x1)
    assert library.get_scene("测试场景")["ambience"] == "Quiet room tone"
    library.save_scene("测试场景", "描述", ambience="", image_raw=PNG_1x1)
    assert library.get_scene("测试场景")["ambience"] == ""


def test_delete_a_character(plugin_root):
    library.save_character("测试角色", "描述", "voice", image_raw=PNG_1x1)
    result = library.delete_character("测试角色")
    assert result["ok"] is True
    assert library.list_characters() == []


def test_a_jpeg_is_converted_to_png(plugin_root):
    from PIL import Image
    import io
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (255, 0, 0)).save(buf, format="JPEG")
    png = library.to_png_bytes(buf.getvalue())
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_a_wav_is_left_alone(plugin_root):
    assert library.to_wav_bytes(WAV_1S) == WAV_1S


# --------------------------------------------------------------------------- #
# script assets
# --------------------------------------------------------------------------- #

SCRIPT = {
    "version": 2,
    "name": "测试剧本",
    "language": "zh",
    "roles": [{
        "id": "character_1", "name": "甲", "presence": "on_screen",
        "initially_visible": True, "position": "center", "voice": "male voice",
    }],
    "camera": {"framing": "medium_close_up", "movement": "locked",
               "perspective": "observer"},
    "look": "", "setting": "",
    "constraints": "",
    "target_duration_seconds": 2,
    "continuation_overlap_frames": 0,
    "source_script": "甲：你好",
    "shots": [{
        "id": "scene_01", "duration_seconds": 5,
        "events": [{"id": "event_001", "type": "dialogue",
                    "character": "character_1", "text": "你好",
                    "language": "zh"}],
    }],
    "execution": {
        "look": "", "setting": "",
        "visible_state": "Character 1 stands at center.",
        "voices": {"character_1": "male voice"}, "directions": {},
    },
    "audio_mode": "generated",
}


def test_save_and_read_a_script(plugin_root):
    result = library.save_storyboard(dict(SCRIPT))
    assert result["status"] == "created"
    assert library.list_storyboards() == ["测试剧本"]
    data = library.get_storyboard("测试剧本")
    assert data["version"] == 2
    assert data["preview"], "a storyboard must have a human-readable preview"


def test_validate_accepts_a_good_script(plugin_root):
    result = library.validate_storyboard(dict(SCRIPT))
    assert result["ok"] is True, result["errors"]
    assert result["errors"] == []


def test_validate_rejects_a_script_whose_events_drift(plugin_root):
    broken = json.loads(json.dumps(SCRIPT))
    broken["shots"][0]["events"][0]["text"] = "别的"
    result = library.validate_storyboard(broken)
    assert result["ok"] is False
    assert "source events differ" in result["errors"][0]


def test_delete_a_script(plugin_root):
    library.save_storyboard(dict(SCRIPT))
    library.delete_storyboard("测试剧本")
    assert library.list_storyboards() == []
