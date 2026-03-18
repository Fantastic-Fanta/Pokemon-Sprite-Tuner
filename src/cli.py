import argparse
from pathlib import Path

from .io import resolve_input, resolve_bg_path, load_presets
from .img import process_gif, process_gif_with_glow


def main():
    parser = argparse.ArgumentParser(
        prog="gif-convert.py",
        description="Convert sprites or GIFs using presets.",
    )

    parser.add_argument("input", help="Pokémon name (Showdown sprite) or path to a GIF file")
    parser.add_argument("output", nargs="?", help="Optional output path (basename only is used)")
    parser.add_argument("--preset", metavar="NAME", help="Named preset from reskins.yaml")

    args = parser.parse_args()

    presets, project_root = load_presets()

    use_glow = False
    glow_opts = {}
    bg_path = None
    is_whiteout = False
    base_contrast = 1.0
    base_invert = True

    def apply_preset(name):
        nonlocal use_glow, bg_path, is_whiteout, base_contrast, base_invert
        cfg = presets.get(name, {}) if isinstance(presets, dict) else {}
        if not isinstance(cfg, dict):
            cfg = {}

        base_invert = bool(cfg.get("invert", True))
        is_whiteout = not base_invert
        if "contrast" in cfg:
            base_contrast = float(cfg["contrast"])

        bg_val = cfg.get("bg", False)
        if isinstance(bg_val, str):
            bg_path_local = resolve_bg_path(bg_val, base_dir=project_root)
        elif bg_val:
            bg_path_local = resolve_bg_path(base_dir=project_root)
        else:
            bg_path_local = None

        nonlocal_bg = "bg_path"
        globals()[nonlocal_bg]
        locals()[nonlocal_bg] if False else None
        bg_path_container = [bg_path]
        bg_path_container[0] = bg_path_local
        bg_path = bg_path_container[0]

        rings = cfg.get("glow_rings")
        if isinstance(rings, (list, tuple)) and rings:
            use_glow = True
            glow_opts["ring_opacities"] = list(rings)
            glow_opts["contour_rings"] = len(rings)
            if "contrast" in cfg:
                glow_opts["contrast"] = float(cfg["contrast"])
            if name == "phantom":
                glow_opts.setdefault("output_format", "WEBP")
        else:
            use_glow = False

    preset_name = args.preset or None
    if preset_name:
        glow_opts.clear()
        apply_preset(preset_name)

    input_arg = args.input
    output_path = args.output

    input_path, output_base = resolve_input(input_arg)
    if use_glow:
        glow_opts["bg_path"] = bg_path
        process_gif_with_glow(input_path, output_path, output_base=output_base, **glow_opts)
    else:
        process_gif(
            input_path,
            output_path,
            output_base=output_base,
            bg_path=bg_path,
            invert=not is_whiteout if base_invert else False,
            contrast=base_contrast,
        )

    if Path(input_path).name.startswith("_tmp_"):
        Path(input_path).unlink(missing_ok=True)

