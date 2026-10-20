import copy
import io
import json
from pathlib import Path
from threading import Event
import zipfile

import pytest
from PIL import Image, ImageChops

from rc2vi import animation as engine


def small_project():
    project = engine.new_project("minimal")
    project.update(width=320, height=180, fps=6, intro=1., loop=.5)
    project["layers"] = [engine.make_layer(text="Việt Nam", name="Chữ Việt", style="metal",
        effect="typewriter", loop_effect="shine", font_size=110, start=0., duration=.6)]
    return project


def same_pixels(first, second):
    return ImageChops.difference(first, second).getbbox() is None


def test_default_project_preserves_brand_hierarchy_and_sequence():
    project = engine.new_project()
    top, lower = project["layers"]
    assert top["text"] == "GinzaTech" and lower["text"] == "DJI Modder"
    assert lower["font_size"] == pytest.approx(top["font_size"] * .55)
    assert lower["width"] == pytest.approx(top["width"] * .55)
    assert top["start"] + top["duration"] < lower["start"]
    before = copy.deepcopy(project)
    assert engine.validate_project(project) == project
    assert project == before
    assert len(engine.EFFECTS) >= 14 and len(engine.LOOP_EFFECTS) >= 6


@pytest.mark.parametrize("key,value", [
    ("fps", float("nan")), ("fps", 31), ("width", 1921), ("height", True),
    ("intro", 0), ("loop", 11), ("schema", 2),
])
def test_invalid_project_settings_are_rejected(key, value):
    project = small_project()
    project[key] = value
    with pytest.raises(engine.AnimationError):
        engine.validate_project(project)


def test_invalid_layer_color_and_duplicate_ids_are_rejected():
    project = small_project()
    project["layers"][0]["color"] = "red"
    with pytest.raises(engine.AnimationError, match="#RRGGBB"):
        engine.validate_project(project)
    project = small_project()
    project["layers"].append(copy.deepcopy(project["layers"][0]))
    with pytest.raises(engine.AnimationError, match="định danh"):
        engine.validate_project(project)


def test_subtitle_starts_after_brand_and_unicode_is_drawn():
    project = engine.new_project()
    project["background"].update(type="solid", color="#000000")
    early = engine.render_frame(project, 1.95, size=(640, 360))
    assert early.crop((0, 185, 640, 280)).getbbox() is None
    late = engine.render_frame(project, 3.5, size=(640, 360))
    assert late.crop((0, 185, 640, 280)).getbbox() is not None
    project["layers"][0]["text"] = "Gìn giữ bầu trời Việt Nam"
    assert engine.render_frame(project, 4, size=(640, 360)).getbbox() is not None


@pytest.mark.parametrize("effect", [effect for effect in engine.EFFECTS if effect != "none"])
def test_each_entrance_effect_changes_actual_pixels(effect):
    project = small_project()
    project["layers"][0].update(effect=effect, start=0., duration=1.)
    a = engine.render_frame(project, .23)
    b = engine.render_frame(project, .71)
    assert a.mode == "RGB" and a.size == (320, 180)
    assert not same_pixels(a, b), effect
    assert same_pixels(a, engine.render_frame(project, .23)), "Renderer must be deterministic"


@pytest.mark.parametrize("effect", [effect for effect in engine.LOOP_EFFECTS if effect != "none"])
def test_each_loop_effect_animates_and_returns_to_start(effect):
    project = small_project()
    project["layers"][0]["loop_effect"] = effect
    a = engine.render_frame(project, .08, phase="loop")
    b = engine.render_frame(project, .31, phase="loop")
    assert not same_pixels(a, b), effect
    assert same_pixels(engine.render_frame(project, 0, phase="loop"), engine.render_frame(project, project["loop"], phase="loop"))


def test_typewriter_changes_only_on_whole_character_steps():
    project = small_project()
    project["layers"][0].update(text="ABCDEFGHIJ", duration=1., style="flat")
    assert same_pixels(engine.render_frame(project, .11), engine.render_frame(project, .19))
    assert not same_pixels(engine.render_frame(project, .11), engine.render_frame(project, .21))
    assert engine.render_frame(project, 0).getbbox() is None


def test_gradient_and_transparent_image_background_and_aspect_ratio(tmp_path):
    project = small_project()
    project["layers"] = []
    project["background"].update(type="gradient", color="#000000", color2="#ffffff")
    frame = engine.render_frame(project, 0)
    assert frame.getpixel((0, 0)) == (0, 0, 0)
    assert frame.getpixel((0, 179)) == (255, 255, 255)
    asset = tmp_path / "wide.png"
    Image.new("RGBA", (80, 20), (250, 0, 0, 255)).save(asset)
    project["background"].update(type="image", image=str(asset), fit="contain", color="#000000")
    frame = engine.render_frame(project, 0)
    assert frame.getpixel((160, 90)) == (250, 0, 0)
    assert frame.getpixel((160, 0)) == (0, 0, 0)
    assert frame.getpixel((160, 51)) == (250, 0, 0)


def test_export_android_archive_is_stored_rgb_and_trim_reconstructs(tmp_path):
    project = small_project()
    result = engine.export_animation(project, tmp_path / "output")
    assert result["frames"] == 9 and result["intro_frames"] == 6 and result["loop_frames"] == 3
    assert result["trimmed"] is True
    assert all(Path(result[field]).is_file() for field in ("zip", "preview", "poster"))
    with zipfile.ZipFile(result["zip"]) as archive:
        assert archive.read("desc.txt").decode() == "320 180 6\np 1 0 part0\np 0 0 part1\n"
        assert all(entry.compress_type == zipfile.ZIP_STORED for entry in archive.infolist())
        pngs = [name for name in archive.namelist() if name.endswith(".png")]
        assert len(pngs) == 9
        trims = archive.read("part0/trim.txt").decode().splitlines()
        assert len(trims) == 6
        for index in (0, 2, 5):
            frame = Image.open(io.BytesIO(archive.read(f"part0/{index:05d}.png")))
            assert frame.mode == "RGB"
            geometry = trims[index].replace("x", "+").split("+")
            width, height, x, y = map(int, geometry)
            assert frame.size == (width, height)
            restored = Image.new("RGB", (320, 180)); restored.paste(frame, (x, y))
            assert same_pixels(restored, engine.render_frame(project, index / 6))
    with Image.open(result["preview"]) as preview:
        assert preview.is_animated
        duration = 0
        for frame_index in range(preview.n_frames):
            preview.seek(frame_index)
            duration += preview.info["duration"]
        assert abs(duration - result["frames"] / result["fps"] * 1000) <= 10
    assert len(result["sha256"]) == 64
    json.dumps(result)  # The frozen app's CLI serializes the entire result.


def test_non_black_background_exports_full_canvas_without_trim(tmp_path):
    project = small_project()
    project["background"].update(type="solid", color="#102030")
    result = engine.export_animation(project, tmp_path / "custom.zip")
    with zipfile.ZipFile(result["zip"]) as archive:
        assert "part0/trim.txt" not in archive.namelist()
        frame = Image.open(io.BytesIO(archive.read("part0/00000.png")))
        assert frame.size == (320, 180) and frame.getpixel((0, 0)) == (16, 32, 48)


def test_gif_duration_uses_cumulative_centisecond_rounding(tmp_path):
    project = small_project()
    project.update(fps=24, intro=4., loop=1.)
    result = engine.export_animation(project, tmp_path)
    with Image.open(result["preview"]) as preview:
        duration = 0
        for frame_index in range(preview.n_frames):
            preview.seek(frame_index)
            duration += preview.info["duration"]
    assert abs(duration - 5000) <= 10


def test_two_named_exports_keep_independent_previews_posters_and_metadata(tmp_path):
    project = small_project()
    first = engine.export_animation(project, tmp_path / "first.zip")
    saved = {field: Path(first[field]).read_bytes() for field in ("zip", "preview", "poster", "metadata")}
    project["layers"][0]["text"] = "Thiết kế khác"
    project["background"]["color"] = "#100827"
    second = engine.export_animation(project, tmp_path / "second.zip")
    for field, data in saved.items():
        assert Path(first[field]) != Path(second[field])
        assert Path(first[field]).read_bytes() == data
    assert Path(first["preview"]).name == "first.preview.gif"
    assert json.loads(Path(first["metadata"]).read_text("utf-8"))["zip"] == first["zip"]
    directory_result = engine.export_animation(project, tmp_path / "directory")
    assert Path(directory_result["preview"]).name == "preview.gif"
    assert Path(directory_result["poster"]).name == "poster.png"
    assert Path(directory_result["metadata"]).name == "export.json"


def test_cancel_keeps_previous_output_and_removes_temporary_files(tmp_path):
    output = tmp_path / "bootanimation.zip"
    output.write_bytes(b"previous valid archive")
    cancel = Event()
    updates = []
    def report(done, total, message):
        updates.append((done, total, message))
        if done == 3:
            cancel.set()
    with pytest.raises(engine.AnimationCancelled):
        engine.export_animation(small_project(), output, cancel=cancel, progress=report)
    assert output.read_bytes() == b"previous valid archive"
    assert [p.name for p in tmp_path.iterdir()] == ["bootanimation.zip"]
    assert len(updates) == 3


def test_loop_memory_and_layer_schedule_limits_fail_before_export(tmp_path):
    project = engine.new_project()
    project.update(fps=30, loop=2.)
    with pytest.raises(engine.AnimationError, match="256 MiB"):
        engine.export_animation(project, tmp_path)
    project = small_project()
    project["layers"][0].update(start=.8, duration=.7)
    with pytest.raises(engine.AnimationError, match="kết thúc"):
        engine.export_animation(project, tmp_path)
    assert not list(tmp_path.iterdir())


def test_black_trim_loop_uses_actual_texture_budget(tmp_path, monkeypatch):
    project = small_project()
    project["layers"][0].update(font_size=30, width=.1, loop_effect="none")
    monkeypatch.setattr(engine, "MAX_LOOP_TEXTURE_BYTES", 60_000)
    # Three full-canvas RGBA frames require 691,200 bytes; trimmed glyphs fit.
    result = engine.export_animation(project, tmp_path / "trimmed")
    assert result["loop_texture_bytes"] <= 60_000
    assert result["loop_texture_padded_estimate_bytes"] >= result["loop_texture_bytes"]
    project["layers"][0].update(font_size=150, width=.9)
    with pytest.raises(engine.AnimationError, match="sau khi cắt"):
        engine.export_animation(project, tmp_path / "too-large")
    assert not list((tmp_path / "too-large").iterdir())


def test_portable_project_embeds_deduplicates_assets_and_survives_source_removal(tmp_path):
    asset = tmp_path / "source.png"
    Image.new("RGBA", (30, 40), (10, 230, 80, 255)).save(asset)
    project = small_project()
    project["background"].update(type="image", image=str(asset))
    project["layers"].append(engine.make_layer("image", image=str(asset), effect="fade", start=0, duration=.5))
    expected = engine.render_frame(project, .7)
    original = copy.deepcopy(project)
    saved = engine.save_project(project, tmp_path / "portable.rc2anim")
    assert project == original
    with zipfile.ZipFile(saved) as archive:
        assert len([name for name in archive.namelist() if name.startswith("assets/")]) == 1
        manifest = json.loads(archive.read("manifest.json"))
        assert not manifest["background"]["image"].startswith(str(tmp_path))
    asset.unlink()
    loaded = engine.load_project(saved, tmp_path / "cache")
    assert Path(loaded["background"]["image"]).is_file()
    assert same_pixels(expected, engine.render_frame(loaded, .7))


@pytest.mark.parametrize("member", ["../escape.png", "/absolute.png", "assets/../escape.png", "assets\\escape.png", "C:/evil.png", "assets/a/b.png", "assets//a.png"])
def test_unsafe_portable_paths_are_rejected_without_extraction(tmp_path, member):
    archive_path = tmp_path / "unsafe.rc2anim"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("manifest.json", json.dumps(small_project()))
        archive.writestr(member, b"untrusted")
    if "\\" in member:
        # Windows ZipFile.writestr sanitizes names; patch both ZIP headers to
        # represent a file actually received from an untrusted external writer.
        archive_path.write_bytes(archive_path.read_bytes().replace(member.replace("\\", "/").encode(), member.encode()))
    with pytest.raises(engine.AnimationError):
        engine.load_project(archive_path, tmp_path / "cache")
    assert not list((tmp_path / "cache").iterdir())
    assert not (tmp_path / "escape.png").exists()


def test_missing_asset_absolute_reference_and_oversized_member_rejected(tmp_path, monkeypatch):
    project = small_project()
    project["background"].update(type="image", image="C:/private/file.png")
    archive_path = tmp_path / "bad.rc2anim"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("manifest.json", json.dumps(project))
    with pytest.raises(engine.AnimationError):
        engine.load_project(archive_path, tmp_path / "cache")
    monkeypatch.setattr(engine, "MAX_ASSET_BYTES", 100)
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(small_project()))
        archive.writestr("assets/oversize.bin", b"a" * 101)
    with pytest.raises(engine.AnimationError, match="quá lớn"):
        engine.load_project(archive_path, tmp_path / "cache")


def test_image_pixel_limit_is_checked_before_decoding(tmp_path, monkeypatch):
    asset = tmp_path / "large.png"
    Image.new("RGB", (20, 20)).save(asset)
    project = small_project()
    project["background"].update(type="image", image=str(asset))
    monkeypatch.setattr(engine, "MAX_IMAGE_PIXELS", 100)
    with pytest.raises(engine.AnimationError, match="megapixel"):
        engine.render_frame(project, 0)
