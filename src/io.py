from pathlib import Path
from urllib.request import Request, urlopen

import yaml

_SHOWDOWN_SPRITE_URL = "https://play.pokemonshowdown.com/sprites/ani/{name}.gif"


def resolve_input(arg, output_dir=None):
    path = Path(arg)
    if path.suffix:
        return str(path.resolve()), path.stem

    name = arg.lower().strip()
    url = _SHOWDOWN_SPRITE_URL.format(name=name)
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req) as resp:
        data = resp.read()

    base_dir = Path(__file__).resolve().parent.parent
    tmp_dir = output_dir or base_dir
    tmp_path = tmp_dir / f"_tmp_{name}.gif"
    tmp_path.write_bytes(data)
    return str(tmp_path), name


def resolve_bg_path(path_arg=None, base_dir=None):
    base_dir = base_dir or (Path(__file__).resolve().parent.parent / "backgrounds")
    if path_arg:
        p = Path(path_arg)
        if not p.is_absolute():
            p = base_dir / p
        return str(p)
    return str(base_dir / "bg.png")


def load_presets(config_path=None):
    if config_path is None:
        config_path = Path(__file__).resolve().parent / "reskins.yaml"
    else:
        config_path = Path(config_path)
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    return (data or {}, config_path.parent)

