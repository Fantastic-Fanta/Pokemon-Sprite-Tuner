from pathlib import Path

from PIL import Image


def process_gif(
    input_path,
    output_path=None,
    output_base=None,
    bg_path=None,
    invert=True,
    contrast=1.0,
):
    path = Path(input_path)
    img = Image.open(input_path)

    outputs_dir = Path(__file__).resolve().parent.parent / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    if output_path is None:
        base = output_base or path.stem
        suffix = "_glitch.gif" if invert else "_whiteout.gif"
        output_path = outputs_dir / f"{base}{suffix}"
    else:
        output_path = outputs_dir / Path(output_path).name

    palette = []
    for i in range(255):
        palette.extend([i, i, i])
    palette.extend([0, 0, 0])

    frames = []
    n_frames = getattr(img, "n_frames", 1)
    for i in range(n_frames):
        img.seek(i)
        frame = img.copy().convert("RGBA")
        data = list(frame.getdata())
        out_indices = []
        mid = 127.5
        for r, g, b, a in data:
            if a == 0:
                out_indices.append(255)
            else:
                grey = int(0.299 * r + 0.587 * g + 0.114 * b)
                v = min(254, 255 - grey) if invert else grey
                v = mid + (v - mid) * contrast
                v = max(0, min(254, int(v)))
                out_indices.append(v)
        out_frame = Image.new("P", frame.size)
        out_frame.putpalette(palette)
        out_frame.putdata(out_indices)
        out_frame.info["transparency"] = 255
        frames.append(out_frame)

    if bg_path:
        bg_img = Image.open(bg_path).convert("RGBA")
        bg_w, bg_h = bg_img.size
        gif_w, gif_h = frames[0].size
        scale = min(6 / 7 * bg_w / gif_w, 6 / 7 * bg_h / gif_h)
        new_w = max(1, int(gif_w * scale))
        new_h = max(1, int(gif_h * scale))
        paste_x = (bg_w - new_w) // 2
        paste_y = (bg_h - new_h) // 2

        composited = []
        for frame in frames:
            data = frame.get_flattened_data()
            pal = frame.getpalette()
            out_data = []
            for idx in data:
                if idx == 255:
                    out_data.append((0, 0, 0, 0))
                else:
                    out_data.append((pal[idx * 3], pal[idx * 3 + 1], pal[idx * 3 + 2], 255))
            rgba = Image.new("RGBA", frame.size)
            rgba.putdata(out_data)
            if scale != 1:
                rgba = rgba.resize((new_w, new_h), Image.NEAREST)
            layer = Image.new("RGBA", (bg_w, bg_h))
            layer.paste(rgba, (paste_x, paste_y))
            composited.append(Image.alpha_composite(bg_img, layer))

        frames = [f.convert("RGB") for f in composited]

    save_kw = {"disposal": 2} if bg_path else {"transparency": 255, "disposal": 2}
    if len(frames) == 1:
        frames[0].save(output_path, "GIF", **save_kw)
    else:
        duration = img.info.get("duration", 100)
        loop = img.info.get("loop", 0)
        frames[0].save(
            output_path,
            "GIF",
            save_all=True,
            append_images=frames[1:],
            duration=duration,
            loop=loop,
            **save_kw,
        )


def _get_neighbors(x, y, width, height):
    out = []
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            nx, ny = x + dx, y + dy
            if 0 <= nx < width and 0 <= ny < height:
                out.append((nx, ny))
    return out


def _solid_neighbors_diagonal_only(idx, width, height, solid_mask):
    y, x = idx // width, idx % width
    has_ortho, has_diag = False, False
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            nx, ny = x + dx, y + dy
            if 0 <= nx < width and 0 <= ny < height and solid_mask[ny * width + nx]:
                if dx == 0 or dy == 0:
                    has_ortho = True
                else:
                    has_diag = True
    return has_diag and not has_ortho


def _build_fading_contour(
    width,
    height,
    solid_mask,
    contour_rings=5,
):
    INF = 1 << 30
    dist = [INF] * (width * height)
    for y in range(height):
        for x in range(width):
            idx = y * width + x
            if solid_mask[idx]:
                dist[idx] = 0

    current = set()
    for idx in range(width * height):
        if dist[idx] == 0:
            y, x = idx // width, idx % width
            for nx, ny in _get_neighbors(x, y, width, height):
                nidx = ny * width + nx
                if not solid_mask[nidx]:
                    current.add(nidx)

    d = 1
    while current and d <= contour_rings:
        next_front = set()
        for idx in current:
            if dist[idx] > d:
                dist[idx] = d
                y, x = idx // width, idx % width
                for nx, ny in _get_neighbors(x, y, width, height):
                    nidx = ny * width + nx
                    if not solid_mask[nidx] and dist[nidx] == INF:
                        next_front.add(nidx)
        current = next_front
        d += 1

    result = [None] * (width * height)
    for idx in range(width * height):
        if solid_mask[idx] or dist[idx] == INF or dist[idx] > contour_rings:
            result[idx] = None
        else:
            ring = dist[idx] - 1
            if ring == 0 and _solid_neighbors_diagonal_only(idx, width, height, solid_mask):
                ring = 1
            result[idx] = ring

    return result


_GLOW_COLOR = (255, 255, 255)
_BG_COLOR = (166, 193, 238)
_CHAR_PALETTE_SIZE = 249
_BG_PALETTE_INDEX = 255


def process_gif_with_glow(
    input_path,
    output_path=None,
    output_base=None,
    contour_rings=3,
    bg_path=None,
    ring_opacities=None,
    contrast=1.0,
    debug_edge=None,
    debug_region=None,
    output_format="GIF",
):
    path = Path(input_path)
    img = Image.open(input_path)

    outputs_dir = Path(__file__).resolve().parent.parent / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    if output_path is None:
        base = output_base or path.stem
        ext = ".webp" if output_format.upper() == "WEBP" else ".gif"
        output_path = outputs_dir / f"{base}_phantom{ext}"
    else:
        output_path = outputs_dir / Path(output_path).name

    palette = []
    for i in range(_CHAR_PALETTE_SIZE):
        v = int(i * 254 / (_CHAR_PALETTE_SIZE - 1)) if _CHAR_PALETTE_SIZE > 1 else 0
        palette.extend([v, v, v])
    for r in range(contour_rings):
        t = r / max(1, contour_rings - 1)
        R = int(_GLOW_COLOR[0] * (1 - t) + _BG_COLOR[0] * t)
        G = int(_GLOW_COLOR[1] * (1 - t) + _BG_COLOR[1] * t)
        B = int(_GLOW_COLOR[2] * (1 - t) + _BG_COLOR[2] * t)
        palette.extend([R, G, B])
    for _ in range(256 - _CHAR_PALETTE_SIZE - contour_rings - 1):
        palette.extend(_BG_COLOR)
    palette.extend(_BG_COLOR)

    width, height = img.size
    frames = []
    n_frames = getattr(img, "n_frames", 1)
    for i in range(n_frames):
        img.seek(i)
        frame = img.copy().convert("RGBA")
        data = list(frame.getdata())
        solid_mask = [a > 0 for _, _, _, a in data]

        base_values = []
        for r, g, b, a in data:
            if a == 0:
                base_values.append(None)
            else:
                grey = int(0.299 * r + 0.587 * g + 0.114 * b)
                base_values.append(min(254, 255 - grey))

        contour = _build_fading_contour(width, height, solid_mask, contour_rings=contour_rings)

        mid = 127.5
        out_indices = []
        for idx in range(width * height):
            if solid_mask[idx]:
                v = base_values[idx]
                v = mid + (v - mid) * contrast
                v = max(0, min(254, int(v)))
                v = int(v * (_CHAR_PALETTE_SIZE - 1) / 254)
                out_indices.append(min(_CHAR_PALETTE_SIZE - 1, v))
            elif contour[idx] is not None:
                out_indices.append(_CHAR_PALETTE_SIZE + contour[idx])
            else:
                out_indices.append(_BG_PALETTE_INDEX)

        out_frame = Image.new("P", frame.size)
        out_frame.putpalette(palette)
        out_frame.putdata(out_indices)
        frames.append(out_frame)

    if bg_path:
        bg_img = Image.open(bg_path).convert("RGBA")
        bg_w, bg_h = bg_img.size
        gif_w, gif_h = frames[0].size

        scale = min(6 / 7 * bg_w / gif_w, 6 / 7 * bg_h / gif_h)
        new_w = max(1, int(gif_w * scale))
        new_h = max(1, int(gif_h * scale))

        opacities = ring_opacities or [1 - r / contour_rings for r in range(contour_rings)]
        opacities = (opacities + [0.0] * contour_rings)[:contour_rings]

        composited = []
        for frame in frames:
            data = frame.get_flattened_data()
            palette_data = frame.getpalette()
            out_data = []
            for idx in data:
                if idx == _BG_PALETTE_INDEX:
                    out_data.append((0, 0, 0, 0))
                elif _CHAR_PALETTE_SIZE <= idx < _CHAR_PALETTE_SIZE + contour_rings:
                    ring = idx - _CHAR_PALETTE_SIZE
                    a = int(255 * opacities[ring])
                    out_data.append((255, 255, 255, a))
                else:
                    r = palette_data[idx * 3]
                    g = palette_data[idx * 3 + 1]
                    b = palette_data[idx * 3 + 2]
                    out_data.append((r, g, b, 255))
            rgba = Image.new("RGBA", frame.size)
            rgba.putdata(out_data)
            if scale != 1:
                rgba = rgba.resize((new_w, new_h), Image.NEAREST)

            paste_x = (bg_w - new_w) // 2
            paste_y = (bg_h - new_h) // 2
            layer = Image.new("RGBA", (bg_w, bg_h))
            layer.paste(rgba, (paste_x, paste_y))
            composited.append(Image.alpha_composite(bg_img, layer))

        frames = [f.convert("RGBA") for f in composited]

    duration = img.info.get("duration", 100)
    loop = img.info.get("loop", 0)
    fmt = output_format.upper()

    if fmt == "WEBP" and isinstance(duration, (int, float)) and duration < 20:
        duration = 20

    if fmt == "WEBP":
        out_path = Path(output_path)
        if out_path.suffix.lower() != ".webp":
            out_path = out_path.with_suffix(".webp")

        if len(frames) == 1:
            frames[0].convert("RGBA").save(out_path, "WEBP", lossless=True, loop=loop)
        else:
            base = frames[0].convert("RGBA")
            extras = [f.convert("RGBA") for f in frames[1:]]
            base.save(
                out_path,
                "WEBP",
                save_all=True,
                append_images=extras,
                duration=duration,
                loop=loop,
                lossless=True,
            )
    else:
        save_kw = {"disposal": 2}
        if len(frames) == 1:
            frames[0].save(output_path, "GIF", **save_kw)
        else:
            frames[0].save(
                output_path,
                "GIF",
                save_all=True,
                append_images=frames[1:],
                duration=duration,
                loop=loop,
                **save_kw,
            )

