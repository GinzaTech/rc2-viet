"""Portable, offline boot-animation projects and a deterministic Pillow renderer.

This module never accesses a device.  ZIP output uses Android's stored PNG format;
the final part loops until Android finishes booting.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
from functools import lru_cache
import uuid
import zipfile

from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageFilter, ImageFont, ImageOps

EFFECTS = {
    "none": "Hiện ngay", "fade": "Mờ dần vào", "typewriter": "Hiện từng chữ",
    "slide_left": "Trượt từ trái", "slide_right": "Trượt từ phải",
    "slide_up": "Trượt từ dưới lên", "slide_down": "Trượt từ trên xuống",
    "zoom": "Phóng to", "bounce": "Nảy đàn hồi", "glitch": "Nhiễu kỹ thuật số",
    "scan": "Quét sáng", "rotate": "Xoay vào", "wave": "Sóng ký tự",
    "neon": "Bật sáng neon", "wipe": "Lau ngang", "blur": "Lấy nét",
}
LOOP_EFFECTS = {
    "none": "Đứng yên", "pulse": "Nhịp sáng", "float": "Lơ lửng",
    "shine": "Ánh sáng lướt", "rotate": "Xoay nhẹ", "wave": "Sóng ngang",
}
PRESETS = {
    "scifi": "Sci-fi nổi", "metal": "Kim loại nổi", "neon": "Neon",
    "minimal": "Tối giản", "blueprint": "Công nghệ xanh",
}
MAX_ASSET_BYTES = 32 * 1024 * 1024
MAX_PROJECT_BYTES = 128 * 1024 * 1024
MAX_IMAGE_PIXELS = 16_777_216
MAX_LOOP_TEXTURE_BYTES = 256 * 1024 * 1024
MAX_EXPORT_BYTES = 512 * 1024 * 1024
_RESAMPLE = Image.Resampling.LANCZOS
_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


class AnimationError(ValueError):
    """An invalid project, asset, or output setting."""


class AnimationCancelled(RuntimeError):
    """The caller cancelled a render or export."""


def make_layer(kind="text", **overrides):
    layer = {
        "id": uuid.uuid4().hex, "kind": kind, "name": "Chữ mới" if kind == "text" else "Ảnh mới",
        "text": "GinzaTech", "image": "", "font": "", "font_size": 160,
        "x": .5, "y": .43, "width": .72, "color": "#e5edf7", "accent": "#41ccff",
        "style": "metal", "effect": "typewriter", "loop_effect": "shine",
        "start": .25, "duration": 1.5, "opacity": 1., "rotation": 0., "visible": True,
    }
    layer.update(overrides)
    return layer


def new_project(preset="scifi"):
    if preset not in PRESETS:
        raise AnimationError("Mẫu animation không tồn tại.")
    project = {
        "schema": 1, "name": "GinzaTech — DJI Modder", "width": 1920, "height": 1080,
        "fps": 24, "intro": 4., "loop": 1.,
        "background": {"type": "gradient", "color": "#02060c", "color2": "#16334a", "image": "", "fit": "cover"},
        "layers": [
            make_layer(name="Thương hiệu", text="GinzaTech", y=.42, font_size=180, start=.25, duration=1.65),
            make_layer(name="Dòng phụ", text="DJI Modder", y=.60, font_size=99, width=.396,
                       start=2., duration=1.2, style="flat", loop_effect="pulse"),
        ],
    }
    if preset == "metal":
        project["background"].update(type="solid", color="#000000")
        for layer in project["layers"]:
            layer.update(style="metal", color="#e6e8ee", accent="#7a96bc", effect="zoom")
    elif preset == "neon":
        project["background"].update(color="#070217", color2="#19052b")
        for layer in project["layers"]:
            layer.update(style="neon", color="#f3deff", accent="#c941ff", effect="neon")
    elif preset == "minimal":
        project["background"].update(type="solid", color="#000000")
        for layer in project["layers"]:
            layer.update(style="flat", color="#ffffff", effect="fade", loop_effect="none")
    elif preset == "blueprint":
        project["background"].update(color="#031522", color2="#084663")
        for layer in project["layers"]:
            layer.update(style="neon", color="#e2faff", accent="#23d6ff", effect="scan")
    return project


def _number(value, field, low, high, integer=False):
    if isinstance(value, bool):
        raise AnimationError(f"{field}: cần một số hợp lệ.")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise AnimationError(f"{field}: cần một số hợp lệ.") from exc
    if not math.isfinite(number) or not low <= number <= high or (integer and number != int(number)):
        raise AnimationError(f"{field}: giá trị phải nằm trong {low}–{high}.")
    return int(number) if integer else number


def _choice(value, choices, field):
    if not isinstance(value, str) or value not in choices:
        raise AnimationError(f"{field}: lựa chọn không hợp lệ.")
    return value


def _color(value, field):
    if not isinstance(value, str) or not _COLOR.fullmatch(value):
        raise AnimationError(f"{field}: dùng màu dạng #RRGGBB.")
    return value.lower()


def _path(value, field):
    if not isinstance(value, (str, Path)) or len(str(value)) > 4096 or "\x00" in str(value):
        raise AnimationError(f"{field}: đường dẫn không hợp lệ.")
    return str(value)


def validate_project(project):
    if not isinstance(project, dict) or project.get("schema", 1) != 1:
        raise AnimationError("Dự án animation không đúng định dạng phiên bản 1.")
    normalized = {
        "schema": 1, "name": str(project.get("name", "Animation RC2"))[:120],
        "width": _number(project.get("width", 1920), "Chiều rộng", 64, 1920, True),
        "height": _number(project.get("height", 1080), "Chiều cao", 64, 1080, True),
        "fps": _number(project.get("fps", 24), "FPS", 6, 30, True),
        "intro": _number(project.get("intro", 4), "Thời lượng mở đầu", .1, 14.9),
        "loop": _number(project.get("loop", 1), "Thời lượng lặp", .1, 10),
    }
    if normalized["intro"] + normalized["loop"] > 15.00001:
        raise AnimationError("Tổng mở đầu và đoạn lặp tối đa 15 giây.")
    background = project.get("background", {})
    if not isinstance(background, dict):
        raise AnimationError("Nền phải là một cấu hình hợp lệ.")
    normalized["background"] = {
        "type": _choice(background.get("type", "solid"), ("solid", "gradient", "image"), "Loại nền"),
        "color": _color(background.get("color", "#000000"), "Màu nền"),
        "color2": _color(background.get("color2", "#16334a"), "Màu nền thứ hai"),
        "image": _path(background.get("image", ""), "Ảnh nền"),
        "fit": _choice(background.get("fit", "cover"), ("cover", "contain"), "Căn ảnh nền"),
    }
    layers = project.get("layers", [])
    if not isinstance(layers, list) or len(layers) > 32:
        raise AnimationError("Dự án cho phép tối đa 32 lớp chữ/ảnh.")
    normalized["layers"] = []
    ids = set()
    for index, source in enumerate(layers):
        if not isinstance(source, dict):
            raise AnimationError(f"Lớp {index + 1} không hợp lệ.")
        layer = make_layer(**source)
        layer["kind"] = _choice(layer["kind"], ("text", "image"), "Loại lớp")
        layer["id"] = str(layer["id"])[:80]
        if not layer["id"] or layer["id"] in ids:
            raise AnimationError("Mỗi lớp phải có mã định danh riêng.")
        ids.add(layer["id"])
        layer["name"] = str(layer["name"])[:120]
        if not isinstance(layer["text"], str) or len(layer["text"]) > 500:
            raise AnimationError("Mỗi lớp chữ cho phép tối đa 500 ký tự.")
        if layer["text"].count("\n") > 11:
            raise AnimationError("Mỗi lớp chữ cho phép tối đa 12 dòng.")
        for key in ("image", "font"):
            layer[key] = _path(layer[key], key)
        for key in ("color", "accent"):
            layer[key] = _color(layer[key], key)
        for key, lo, hi in (("x", -1., 2.), ("y", -1., 2.), ("width", .02, 2.),
                            ("font_size", 8, 500), ("start", 0., 15.), ("duration", .05, 15.),
                            ("opacity", 0., 1.), ("rotation", -360., 360.)):
            layer[key] = _number(layer[key], key, lo, hi)
        layer["style"] = _choice(layer["style"], ("flat", "metal", "neon"), "Kiểu chữ")
        layer["effect"] = _choice(layer["effect"], EFFECTS, "Hiệu ứng xuất hiện")
        layer["loop_effect"] = _choice(layer["loop_effect"], LOOP_EFFECTS, "Hiệu ứng lặp")
        if not isinstance(layer["visible"], bool):
            raise AnimationError("Trạng thái hiển thị của lớp phải là bật/tắt.")
        # Keep only defined keys so arbitrary project data never reaches the renderer.
        normalized["layers"].append({key: layer[key] for key in make_layer()})
    return normalized


def _asset_stat(path):
    try:
        resolved = Path(path).expanduser().resolve(strict=True)
        info = resolved.stat()
        if not resolved.is_file() or info.st_size > MAX_ASSET_BYTES:
            raise AnimationError("Mỗi ảnh hoặc phông chữ phải là tệp tối đa 32 MiB.")
        return str(resolved), info.st_mtime_ns, info.st_size
    except (OSError, ValueError) as exc:
        raise AnimationError(f"Không đọc được tài nguyên: {path}") from exc


def _check_image(image):
    if image.width * image.height > MAX_IMAGE_PIXELS or max(image.size) > 16384:
        raise AnimationError("Ảnh quá lớn. Hãy giảm ảnh xuống tối đa 16 megapixel.")


@lru_cache(maxsize=8)
def _image_asset(path, mtime, length, width, height, fit):
    try:
        with Image.open(path) as opened:
            _check_image(opened)
            source = ImageOps.exif_transpose(opened)
            if fit == "cover":
                result = ImageOps.fit(source, (width, height), method=_RESAMPLE)
            else:
                result = ImageOps.contain(source, (width, height), method=_RESAMPLE)
            return result.convert("RGBA")
    except AnimationError:
        raise
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise AnimationError(f"Không mở được ảnh: {Path(path).name}") from exc


@lru_cache(maxsize=24)
def _font(path, size):
    candidates = [path] if path else []
    windows = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    candidates.extend(str(windows / name) for name in ("bahnschrift.ttf", "segoeuib.ttf", "arialbd.ttf"))
    candidates.extend(["DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"])
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except (OSError, ValueError):
            continue
    return ImageFont.load_default(size=size)


def _gradient(size, color1, color2):
    width, height = size
    a, b = ImageColor.getrgb(color1), ImageColor.getrgb(color2)
    stripe = Image.new("RGB", (1, height))
    stripe.putdata([tuple(round(a[i] + (b[i] - a[i]) * y / max(1, height - 1)) for i in range(3)) for y in range(height)])
    return stripe.resize((width, height))


@lru_cache(maxsize=6)
def _background_cached(signature, size, image_signature):
    background = json.loads(signature)
    if background["type"] == "gradient":
        return _gradient(size, background["color"], background["color2"]).convert("RGBA")
    result = Image.new("RGBA", size, background["color"])
    if background["type"] == "image":
        if not image_signature:
            raise AnimationError("Hãy chọn một ảnh nền.")
        source = _image_asset(*image_signature, *size, background["fit"])
        result.alpha_composite(source, ((size[0] - source.width) // 2, (size[1] - source.height) // 2))
    return result


def _text_layout(text, font_path, font_size, max_width, max_height):
    font = _font(font_path, font_size)
    # Pillow multiline_textbbox supports both Vietnamese accents and explicit lines.
    draw = ImageDraw.Draw(Image.new("L", (1, 1)))
    spacing = max(1, font_size // 8)
    box = draw.multiline_textbbox((0, 0), text or " ", font=font, spacing=spacing, align="center")
    reduction = min(1., max_width / max(1, box[2] - box[0]), max_height / max(1, box[3] - box[1]))
    if reduction < 1:
        font_size = max(1, math.floor(font_size * reduction))
        font, spacing = _font(font_path, font_size), max(1, font_size // 8)
        box = draw.multiline_textbbox((0, 0), text or " ", font=font, spacing=spacing, align="center")
    return font, box, spacing


def _text_mask(text, font_path, font_size, max_width, max_height):
    font, box, spacing = _text_layout(text, font_path, font_size, max_width, max_height)
    width, height = max(1, box[2] - box[0]), max(1, box[3] - box[1])
    mask = Image.new("L", (width, height))
    ImageDraw.Draw(mask).multiline_text((-box[0], -box[1]), text, font=font, fill=255, spacing=spacing, align="center")
    return mask


@lru_cache(maxsize=16)
def _layer_cached(signature, size, source_signature, font_signature):
    layer = json.loads(signature)
    scale = size[0] / layer.pop("canvas_width")
    max_width = max(1, round(size[0] * layer["width"]))
    if layer["kind"] == "image":
        if not source_signature:
            raise AnimationError(f"Hãy chọn ảnh cho lớp {layer['name']}.")
        # Layer images retain their aspect ratio; width is the bounding width.
        return _image_asset(*source_signature, max_width, max(1, round(size[1] * 1.5)), "contain")
    text = layer["text"]
    font_path = font_signature[0] if font_signature else ""
    mask = _text_mask(text, font_path, max(6, round(layer["font_size"] * scale)), max_width, max(1, round(size[1] * 1.5)))
    pad = max(4, round(22 * scale))
    mask = ImageOps.expand(mask, pad, fill=0)
    return _styled_text(mask, layer, scale)


def _styled_text(mask, layer, scale):
    color, accent = ImageColor.getrgb(layer["color"]), ImageColor.getrgb(layer["accent"])
    result = Image.new("RGBA", mask.size)
    if layer["style"] in ("metal", "neon"):
        radius = max(1., 7 * scale)
        glow = Image.new("RGBA", mask.size, accent + (0,))
        glow.putalpha(mask.filter(ImageFilter.GaussianBlur(radius)))
        result.alpha_composite(glow)
    if layer["style"] == "metal":
        depth = max(1, round(5 * scale))
        # A lower edge plus a highlight above the face creates a raised bevel.
        edge = Image.new("RGBA", mask.size, (14, 32, 49, 0))
        edge_mask = Image.new("L", mask.size)
        edge_mask.paste(mask, (depth, depth))
        edge.putalpha(edge_mask)
        result.alpha_composite(edge)
        face = _gradient(mask.size, "#ffffff", layer["color"]).convert("RGBA")
        face.putalpha(mask)
        result.alpha_composite(face)
        shifted = Image.new("L", mask.size)
        shifted.paste(mask, (0, max(1, round(2 * scale))))
        highlight = ImageChops.subtract(mask, shifted)
        top = Image.new("RGBA", mask.size, (255, 255, 255, 0))
        top.putalpha(highlight.point(lambda value: round(value * .8)))
        result.alpha_composite(top)
    else:
        face = Image.new("RGBA", mask.size, color + (0,))
        face.putalpha(mask)
        result.alpha_composite(face)
    return result


def _layer_image(layer, size, canvas_width):
    # Effect/timeline values are excluded from immutable texture cache keys.
    base = {key: layer[key] for key in ("kind", "text", "image", "font", "font_size", "width", "style", "color", "accent", "name")}
    base["canvas_width"] = canvas_width
    source_signature = _asset_stat(layer["image"]) if layer["kind"] == "image" and layer["image"] else None
    font_signature = _asset_stat(layer["font"]) if layer["font"] else None
    return _layer_cached(json.dumps(base, sort_keys=True), size, source_signature, font_signature).copy()


def _alpha(image, opacity):
    if opacity < .9999:
        image = image.copy()
        image.putalpha(image.getchannel("A").point(lambda value: round(value * max(0., opacity))))
    return image


def _wipe(image, progress):
    if progress >= 1:
        return image
    clip = Image.new("L", image.size)
    stop = max(0, min(image.width, round(image.width * progress)))
    if stop:
        ImageDraw.Draw(clip).rectangle((0, 0, stop - 1, image.height), fill=255)
    image.putalpha(ImageChops.multiply(image.getchannel("A"), clip))
    return image


def _typewriter_layer(layer, size, canvas_width, progress, texture):
    """Reveal whole glyphs without moving the final text's centered position."""
    import unicodedata
    scale = size[0] / canvas_width
    font_path = _asset_stat(layer["font"])[0] if layer["font"] else ""
    font, box, spacing = _text_layout(layer["text"], font_path,
        max(6, round(layer["font_size"] * scale)), max(1, round(size[0] * layer["width"])), max(1, round(size[1] * 1.5)))
    groups = []
    for char in layer["text"]:
        if groups and unicodedata.combining(char):
            groups[-1] += char
        else:
            groups.append(char)
    visible = "".join(groups[:min(len(groups), max(0, int(progress * len(groups))))])
    # Use final-line alignment and place only visible characters into a new mask.
    pad = max(4, round(22 * scale))
    mask = Image.new("L", texture.size)
    draw = ImageDraw.Draw(mask)
    full_lines = layer["text"].split("\n")
    visible_lines = visible.split("\n")
    max_line = max((draw.textlength(line, font=font) for line in full_lines), default=0)
    # Pillow multiline line spacing is based on the font's "A" bottom bound.
    line_height = font.getbbox("A")[3] + spacing
    for index, line in enumerate(visible_lines):
        if index >= len(full_lines):
            break
        left = (max_line - draw.textlength(full_lines[index], font=font)) / 2
        draw.text((pad - box[0] + left, pad - box[1] + index * line_height), line, font=font, fill=255)
    return _styled_text(mask, layer, scale)


def _shine(image, progress):
    mask = Image.new("L", image.size)
    draw = ImageDraw.Draw(mask)
    center = int((progress % 1.) * (image.width + image.height) - image.height // 2)
    stripe = max(3, image.width // 12)
    draw.polygon(((center - stripe, 0), (center + stripe, 0), (center + stripe - image.height // 2, image.height), (center - stripe - image.height // 2, image.height)), fill=145)
    mask = ImageChops.multiply(mask.filter(ImageFilter.GaussianBlur(max(1, stripe / 2))), image.getchannel("A"))
    overlay = Image.new("RGBA", image.size, (255, 255, 255, 0))
    overlay.putalpha(mask)
    image.alpha_composite(overlay)
    return image


def _wave(image, phase, amount):
    result = Image.new("RGBA", (image.width, image.height + 2 * amount))
    step = max(2, image.width // 70)
    for x in range(0, image.width, step):
        strip = image.crop((x, 0, min(x + step, image.width), image.height))
        y = amount + round(math.sin(x / max(1, image.width) * math.tau * 2 + phase) * amount)
        result.alpha_composite(strip, (x, y))
    return result


def _render_normalized(project, seconds, size, phase):
    background = project["background"]
    image_signature = _asset_stat(background["image"]) if background["type"] == "image" and background["image"] else None
    canvas = _background_cached(json.dumps(background, sort_keys=True), size, image_signature).copy()
    for layer in project["layers"]:
        if not layer["visible"] or layer["opacity"] <= 0 or (phase == "intro" and seconds < layer["start"]):
            continue
        progress = 1. if phase == "loop" else min(1., max(0., (seconds - layer["start"]) / layer["duration"]))
        effect = layer["effect"]
        texture = _layer_image(layer, size, project["width"])
        x, y = layer["x"] * size[0], layer["y"] * size[1]
        opacity, angle = layer["opacity"], layer["rotation"]
        eased = 1 - (1 - progress) ** 3
        if progress < 1:
            if effect in ("fade", "blur", "zoom", "rotate"):
                opacity *= progress
            if effect in ("typewriter", "wipe", "scan"):
                if effect == "typewriter" and layer["kind"] == "text":
                    texture = _typewriter_layer(layer, size, project["width"], progress, texture)
                else:
                    texture = _wipe(texture, progress)
                if effect == "scan":
                    texture = _shine(texture, progress)
            elif effect in ("slide_left", "slide_right"):
                x += (-1 if effect == "slide_left" else 1) * (1 - eased) * size[0]
            elif effect in ("slide_up", "slide_down"):
                y += (1 if effect == "slide_up" else -1) * (1 - eased) * size[1]
            elif effect in ("zoom", "bounce"):
                factor = .25 + .75 * eased if effect == "zoom" else 1 + 2.70158 * (progress - 1) ** 3 + 1.70158 * (progress - 1) ** 2
                factor = max(.01, factor)
                texture = texture.resize((max(1, round(texture.width * factor)), max(1, round(texture.height * factor))), _RESAMPLE)
            elif effect == "glitch":
                offset = max(1, round(18 * (1 - progress) * size[0] / project["width"]))
                red = Image.new("RGBA", texture.size, (255, 30, 95, 0)); red.putalpha(texture.getchannel("A"))
                blue = Image.new("RGBA", texture.size, (20, 220, 255, 0)); blue.putalpha(texture.getchannel("A"))
                texture.alpha_composite(_alpha(ImageChops.offset(red, offset, 0), .45))
                texture.alpha_composite(_alpha(ImageChops.offset(blue, -offset, 0), .45))
                y += math.sin(progress * 93) * offset
                opacity *= .65 + .35 * abs(math.sin(progress * 47))
            elif effect == "rotate":
                angle -= 80 * (1 - eased)
            elif effect == "wave":
                texture = _wave(texture, progress * math.tau * 2, max(1, round((1 - progress) * 16 * size[0] / project["width"])))
                opacity *= eased
            elif effect == "neon":
                opacity *= min(1., progress * 2) * (.25 if int(progress * 17) in (1, 3, 6, 8) else 1.)
            elif effect == "blur":
                texture = texture.filter(ImageFilter.GaussianBlur((1 - progress) * 14 * size[0] / project["width"]))
        if phase == "loop":
            turn = (seconds % project["loop"]) / project["loop"]
            loop_effect = layer["loop_effect"]
            if loop_effect == "pulse":
                opacity *= .78 + .22 * (.5 + .5 * math.cos(turn * math.tau))
            elif loop_effect == "float":
                y += math.sin(turn * math.tau) * size[1] * .012
            elif loop_effect == "shine":
                texture = _shine(texture, turn)
            elif loop_effect == "rotate":
                angle += math.sin(turn * math.tau) * 4
            elif loop_effect == "wave":
                texture = _wave(texture, turn * math.tau, max(1, round(size[1] * .008)))
        if abs(angle) > .001:
            texture = texture.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)
        texture = _alpha(texture, opacity)
        canvas.alpha_composite(texture, (round(x - texture.width / 2), round(y - texture.height / 2)))
    return canvas.convert("RGB")


def render_frame(project, seconds, size=None, phase="intro"):
    project = validate_project(project)
    seconds = _number(seconds, "Thời điểm xem trước", 0, 3600)
    phase = _choice(phase, ("intro", "loop"), "Đoạn animation")
    if size is None:
        size = (project["width"], project["height"])
    if not isinstance(size, (tuple, list)) or len(size) != 2:
        raise AnimationError("Kích thước xem trước không hợp lệ.")
    size = tuple(_number(value, "Kích thước xem trước", 16, 1920, True) for value in size)
    if size[0] * size[1] > 1920 * 1080:
        raise AnimationError("Xem trước tối đa 1920 × 1080 pixel.")
    return _render_normalized(project, seconds, size, phase)


def _cancelled(cancel):
    if cancel is None:
        return False
    return bool(cancel.is_set() if hasattr(cancel, "is_set") else cancel())


def _check_cancel(cancel):
    if _cancelled(cancel):
        raise AnimationCancelled("Đã hủy tạo animation.")


def export_animation(project, destination, cancel=None, progress=None):
    project = validate_project(project)
    for layer in project["layers"]:
        if layer["visible"] and layer["start"] + (0 if layer["effect"] == "none" else layer["duration"]) > project["intro"] + .00001:
            raise AnimationError(f"Lớp {layer['name']} kết thúc sau đoạn mở đầu. Hãy tăng thời lượng mở đầu hoặc giảm thời điểm bắt đầu/thời lượng hiệu ứng.")
    intro_frames = max(1, math.ceil(project["intro"] * project["fps"]))
    loop_frames = max(1, math.ceil(project["loop"] * project["fps"]))
    texture_bytes = project["width"] * project["height"] * 4 * loop_frames
    black_trim = project["background"]["type"] == "solid" and project["background"]["color"] == "#000000"
    if not black_trim and texture_bytes > MAX_LOOP_TEXTURE_BYTES:
        maximum = max(1, MAX_LOOP_TEXTURE_BYTES // (project["width"] * project["height"] * 4))
        raise AnimationError(f"Đoạn lặp cần khoảng {texture_bytes / 1048576:.0f} MiB bộ nhớ hình ảnh. Hãy giảm đoạn lặp còn tối đa {maximum / project['fps']:.2f} giây, giảm FPS hoặc độ phân giải (giới hạn 256 MiB).")
    _check_cancel(cancel)
    destination = Path(destination).expanduser().resolve()
    if destination.suffix.lower() == ".zip":
        output_dir, zip_name = destination.parent, destination.name
        preview_name = destination.stem + ".preview.gif"
        poster_name = destination.stem + ".poster.png"
        metadata_name = destination.stem + ".export.json"
    else:
        output_dir, zip_name = destination, "bootanimation.zip"
        preview_name, poster_name, metadata_name = "preview.gif", "poster.png", "export.json"
    output_dir.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".animation-", dir=str(output_dir)))
    total = intro_frames + loop_frames
    previews, preview_durations = [], []
    preview_step = max(1, math.ceil(total / 72))
    preview_size = (min(640, project["width"]), max(16, round(project["height"] * min(640, project["width"]) / project["width"])))
    actual_loop_texture_bytes, padded_loop_texture_bytes = 0, 0
    done = 0
    try:
        with zipfile.ZipFile(staging / zip_name, "w", compression=zipfile.ZIP_STORED, allowZip64=False) as archive:
            archive.writestr("desc.txt", f"{project['width']} {project['height']} {project['fps']}\np 1 0 part0\np 0 0 part1\n")
            for part, count, phase in (("part0", intro_frames, "intro"), ("part1", loop_frames, "loop")):
                trims = []
                for frame_index in range(count):
                    _check_cancel(cancel)
                    seconds = frame_index / project["fps"]
                    frame = _render_normalized(project, seconds, (project["width"], project["height"]), phase)
                    if done % preview_step == 0:
                        previews.append(frame.resize(preview_size, _RESAMPLE))
                        # GIF stores centiseconds.  Round cumulative endpoints,
                        # distributing 30/40 or 80/90 ms instead of losing time
                        # by truncating every 33.3/83.3 ms frame individually.
                        start_cs = round(done * 100 / project["fps"])
                        end_cs = round(min(done + preview_step, total) * 100 / project["fps"])
                        preview_durations.append(max(20, (end_cs - start_cs) * 10))
                    png = frame
                    if black_trim:
                        bbox = frame.getbbox() or (0, 0, 1, 1)
                        png = frame.crop(bbox)
                        trims.append(f"{png.width}x{png.height}+{bbox[0]}+{bbox[1]}")
                    if phase == "loop":
                        actual_loop_texture_bytes += png.width * png.height * 4
                        padded_loop_texture_bytes += (1 << (png.width - 1).bit_length()) * (1 << (png.height - 1).bit_length()) * 4
                        if actual_loop_texture_bytes > MAX_LOOP_TEXTURE_BYTES:
                            raise AnimationError("Đoạn lặp vượt 256 MiB bộ nhớ hình ảnh sau khi cắt nền đen. Hãy giảm thời lượng lặp, FPS, độ phân giải hoặc kích thước các lớp.")
                    with io.BytesIO() as data:
                        png.save(data, format="PNG", compress_level=1, optimize=False)
                        archive.writestr(f"{part}/{frame_index:05d}.png", data.getvalue())
                    if archive.fp.tell() > MAX_EXPORT_BYTES:
                        raise AnimationError("Gói animation vượt 512 MiB. Hãy giảm thời lượng, FPS hoặc độ phân giải.")
                    done += 1
                    if progress:
                        progress(done, total, f"Đang tạo {part}: {frame_index + 1}/{count}")
                if trims:
                    archive.writestr(f"{part}/trim.txt", "\n".join(trims) + "\n")
        _check_cancel(cancel)
        poster = _render_normalized(project, project["intro"], (project["width"], project["height"]), "intro")
        poster.save(staging / poster_name, format="PNG")
        if previews:
            previews[0].save(staging / preview_name, save_all=True, append_images=previews[1:], duration=preview_durations, loop=0, disposal=2, optimize=False)
        _check_cancel(cancel)
        digest = hashlib.sha256((staging / zip_name).read_bytes()).hexdigest()
        metadata = {
            "zip": str(output_dir / zip_name), "preview": str(output_dir / preview_name),
            "poster": str(output_dir / poster_name), "metadata": str(output_dir / metadata_name),
            "sha256": digest, "frames": total,
            "intro_frames": intro_frames, "loop_frames": loop_frames,
            "width": project["width"], "height": project["height"], "fps": project["fps"],
            "loop_texture_bytes": actual_loop_texture_bytes,
            "loop_texture_padded_estimate_bytes": padded_loop_texture_bytes,
            "trimmed": black_trim,
        }
        (staging / metadata_name).write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        for filename in (zip_name, preview_name, poster_name, metadata_name):
            os.replace(staging / filename, output_dir / filename)
        return metadata
    finally:
        for preview in previews:
            preview.close()
        shutil.rmtree(staging, ignore_errors=True)


def _asset_references(project):
    if project["background"]["image"]:
        yield project["background"], "image"
    for layer in project["layers"]:
        for field in ("image", "font"):
            if layer[field]:
                yield layer, field


def save_project(project, path):
    project = validate_project(project)
    path = Path(path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    total_size, assets = 0, {}
    try:
        with zipfile.ZipFile(staging, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for owner, field in _asset_references(project):
                signature = _asset_stat(owner[field])
                asset = Path(signature[0])
                data = asset.read_bytes()
                if len(data) > MAX_ASSET_BYTES:
                    raise AnimationError("Mỗi tài nguyên tối đa 32 MiB.")
                digest = hashlib.sha256(data).hexdigest()
                suffix = asset.suffix.lower()
                if not re.fullmatch(r"\.[a-z0-9]{1,8}", suffix):
                    suffix = ".asset"
                asset_name = f"assets/{digest}{suffix}"
                if asset_name not in assets:
                    total_size += len(data)
                    if total_size > MAX_PROJECT_BYTES:
                        raise AnimationError("Tài nguyên trong dự án tối đa 128 MiB.")
                    archive.writestr(asset_name, data)
                    assets[asset_name] = True
                owner[field] = asset_name
            archive.writestr("manifest.json", json.dumps(project, ensure_ascii=False, indent=2).encode("utf-8"))
        os.replace(staging, path)
    finally:
        if staging.exists():
            staging.unlink()
    return path


def _safe_member(name):
    if not isinstance(name, str) or "\\" in name or "\x00" in name or ":" in name or name.startswith("/"):
        raise AnimationError("Đường dẫn tài nguyên trong dự án không an toàn.")
    path = PurePosixPath(name)
    if not path.parts or any(part in (".", "..", "") for part in name.split("/")):
        raise AnimationError("Đường dẫn tài nguyên trong dự án không an toàn.")
    if name != "manifest.json" and (len(path.parts) != 2 or path.parts[0] != "assets"):
        raise AnimationError("Dự án chứa tệp ngoài thư mục tài nguyên.")
    return path


def load_project(path, cache_dir):
    path, cache_dir = Path(path).expanduser().resolve(), Path(cache_dir).expanduser().resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    destination = Path(tempfile.mkdtemp(prefix="project-", dir=str(cache_dir)))
    try:
        if path.stat().st_size > MAX_PROJECT_BYTES + 1024 * 1024:
            raise AnimationError("Tệp dự án vượt quá giới hạn 128 MiB.")
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if len(infos) > 100 or len({entry.filename for entry in infos}) != len(infos):
                raise AnimationError("Dự án có quá nhiều tệp hoặc có tên tệp trùng.")
            total_size = 0
            for entry in infos:
                _safe_member(entry.orig_filename)
                _safe_member(entry.filename)
                # Unix symlink bits and encrypted entries are not portable assets.
                if (entry.external_attr >> 16) & 0o170000 == 0o120000 or entry.flag_bits & 1:
                    raise AnimationError("Dự án chứa tài nguyên không hợp lệ.")
                limit = 256 * 1024 if entry.filename == "manifest.json" else MAX_ASSET_BYTES
                if entry.file_size > limit or entry.file_size < 0:
                    raise AnimationError("Một tài nguyên trong dự án quá lớn.")
                total_size += entry.file_size
                if total_size > MAX_PROJECT_BYTES + 256 * 1024:
                    raise AnimationError("Tài nguyên trong dự án vượt quá 128 MiB.")
            if "manifest.json" not in archive.namelist():
                raise AnimationError("Dự án thiếu manifest.json.")
            try:
                project = validate_project(json.loads(archive.read("manifest.json").decode("utf-8")))
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise AnimationError("Nội dung dự án không phải JSON hợp lệ.") from exc
            references = list(_asset_references(project))
            for owner, field in references:
                name = owner[field]
                _safe_member(name)
                if not name.startswith("assets/") or name not in archive.namelist():
                    raise AnimationError("Dự án thiếu tài nguyên được tham chiếu.")
                target = destination.joinpath(*PurePosixPath(name).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    with archive.open(name) as source, target.open("wb") as output:
                        shutil.copyfileobj(source, output, length=1024 * 1024)
                owner[field] = str(target)
        return project
    except AnimationError:
        shutil.rmtree(destination, ignore_errors=True)
        raise
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, RuntimeError) as exc:
        shutil.rmtree(destination, ignore_errors=True)
        raise AnimationError("Không mở được tệp dự án .rc2anim.") from exc
