"""Command-line interface for scanning, building, and verifying projects."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from builder import Builder, BuildError, build_manifest_release, verify_archive
from project_config import ConfigError, load_project_config
import scanner


def _parser():
    parser = argparse.ArgumentParser(prog="quakebuild")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("scan", "build", "verify"):
        command = subparsers.add_parser(name)
        command.add_argument("--config", required=True)
        command.add_argument("--version", default="dev")
        if name == "verify":
            command.add_argument("--archive")
    return parser


def _scan(config):
    root = Path(config["fs_basepath"])
    data_root = root / config["fs_game"]
    qc_root = root / config.get("qc_dir", "qc")
    results = scanner.scan_all(
        qc_dir=str(qc_root),
        bsp_dir=str(data_root / "maps"),
        scripts_dir=str(data_root / "scripts"),
    )
    print(json.dumps(results, indent=2, sort_keys=True))
    return results


def _legacy_build(config):
    print("WARNING: scanner builds may contain third-party assets and are not distributable.", file=sys.stderr)
    scanned = _scan(config)
    assets = sorted({asset for values in scanned.values() for asset in values})
    builder = Builder()
    builder.set_paths(config["fs_basepath"], config["fs_game"])
    builder.output_path = config.get("output_path", "")
    builder.build_naming = config.get("build_naming", "date")
    builder.pk3_packs = config.get("pk3_packs", [])
    builder.ignore_patterns = config.get("ignore_patterns", [])
    builder.set_config(config.get("includes", []), config.get("remove_paths", []))
    return builder.run_build(assets)


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        config = load_project_config(args.config)
        if args.command == "scan":
            _scan(config)
            return 0
        if args.command == "build":
            if config.get("build_mode") == "manifest":
                output = build_manifest_release(config, args.version)
            else:
                output = _legacy_build(config)
            print(output)
            return 0
        archive = args.archive
        if not archive:
            template = config.get("artifact_name", "QuakeBuild-{version}")
            archive = Path(config.get("output_path") or ".") / f"{template.format(version=args.version)}.zip"
        metadata = verify_archive(archive, config.get("forbidden_globs", []))
        print(json.dumps(metadata, indent=2, sort_keys=True))
        return 0
    except (BuildError, ConfigError, KeyError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

