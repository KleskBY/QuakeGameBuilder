"""Configuration loading shared by the CLI and GUI."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path


DEFAULT_CONFIG = {
    "schema_version": 1,
    "fs_basepath": "",
    "fs_game": "data",
    "qc_dir": "qc",
    "output_path": "",
    "build_mode": "scan",
    "build_naming": "date",
    "includes": [
        "cubemaps",
        "env",
        "gfx",
        "glsl",
        "maps",
        "particles",
        "progs",
        "scripts",
        "autoexec.cfg",
        "default.cfg",
        "csprogs.dat",
        "menu.dat",
        "progs.dat",
        "effectinfo.txt",
    ],
    "remove_paths": [
        "dlcache",
        "config.cfg",
        "../zircon_history.txt",
        "../darkplaces_history.txt",
    ],
    "pk3_packs": [],
    "ignore_patterns": [],
    "forbidden_globs": [],
    "archive": False,
    "open_after_build": True,
}


class ConfigError(ValueError):
    pass


def load_project_config(file_path):
    config_path = Path(file_path).expanduser().resolve()
    with config_path.open("r", encoding="utf-8") as handle:
        loaded = json.load(handle)
    schema = loaded.get("schema_version", 1)
    if schema != 1:
        raise ConfigError(f"Unsupported schema_version: {schema}")
    config = deepcopy(DEFAULT_CONFIG)
    config.update(loaded)
    config_dir = config_path.parent
    base_value = config.get("fs_basepath") or "."
    base = Path(base_value).expanduser()
    if not base.is_absolute():
        base = config_dir / base
    config["fs_basepath"] = str(base.resolve())
    for key in ("output_path", "manifest"):
        value = config.get(key)
        if value:
            path = Path(value).expanduser()
            if not path.is_absolute():
                path = config_dir / path
            config[key] = str(path.resolve())
    config["_config_path"] = str(config_path)
    return config
