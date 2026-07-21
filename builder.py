"""Safe build and verification primitives for QuakeGameBuilder."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tempfile
from datetime import datetime
import zipfile


BUILD_NAMING_DATE = "date"
BUILD_NAMING_NUMERIC = "numeric"
_MONTH_DAYS = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 303, 334]
_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


class BuildError(RuntimeError):
    """Raised when a build would be incomplete or unsafe."""


def build_number_from_date(dt):
    y, m, d = dt.year, dt.month, dt.day
    leap_days = sum(1 for year in range(2000, y) if _is_leap(year))
    if _is_leap(y) and m > 2:
        leap_days += 1
    return 365 * (y - 1999) - 31 + _MONTH_DAYS[m - 1] + d + leap_days


def _is_leap(year):
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit(path):
    root = Path(path).resolve()
    try:
        result = subprocess.run(
            ["git", "-c", f"safe.directory={root}", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _resolved(path):
    return Path(path).expanduser().resolve()


def _require_within(path, root, label):
    candidate = _resolved(path)
    boundary = _resolved(root)
    try:
        candidate.relative_to(boundary)
    except ValueError as exc:
        raise BuildError(f"{label} escapes its allowed root: {candidate}") from exc
    return candidate


def _require_regular_source(path, project_root):
    lexical = Path(path)
    if lexical.is_symlink():
        raise BuildError(f"Symlink sources are not allowed: {lexical}")
    source = _require_within(lexical, project_root, "Source")
    if not source.is_file():
        raise BuildError(f"Source file is missing or not regular: {source}")
    return source


def _safe_destination(root, relative_path):
    raw = str(relative_path).replace("\\", "/")
    pure = PurePosixPath(raw)
    if pure.is_absolute() or not raw or ".." in pure.parts or ":" in raw:
        raise BuildError(f"Unsafe destination path: {relative_path}")
    return _require_within(Path(root).joinpath(*pure.parts), root, "Destination")


def _matches_forbidden(path, patterns):
    normalized = str(path).replace("\\", "/").lstrip("./").lower()
    return any(fnmatch.fnmatch(normalized, pattern.replace("\\", "/").lower()) for pattern in patterns)


def _copy_tree_safe(source, destination, source_root, destination_root):
    source = Path(source)
    if source.is_symlink():
        raise BuildError(f"Symlink includes are not allowed: {source}")
    source = _require_within(source, source_root, "Include")
    destination = _require_within(destination, destination_root, "Include destination")
    if source.is_file():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        return
    if not source.is_dir():
        raise BuildError(f"Include path not found: {source}")
    for current, directories, files in os.walk(source):
        current_path = Path(current)
        for name in directories:
            if (current_path / name).is_symlink():
                raise BuildError(f"Symlink includes are not allowed: {current_path / name}")
        for name in files:
            src_file = current_path / name
            if src_file.is_symlink():
                raise BuildError(f"Symlink includes are not allowed: {src_file}")
            rel = src_file.relative_to(source)
            dst_file = _require_within(destination / rel, destination_root, "Include destination")
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)


class Builder:
    """Backward-compatible scanner build with path containment and atomic output."""

    def __init__(self):
        self.log_callback = print
        self.fs_basepath = "../"
        self.fs_game = "data"
        self.output_path = ""
        self.build_naming = BUILD_NAMING_DATE
        self.includes = []
        self.remove_paths = []
        self.pk3_packs = []

    def set_paths(self, fs_basepath, fs_game):
        self.fs_basepath = fs_basepath
        self.fs_game = fs_game

    def set_config(self, includes, remove_paths):
        self.includes = includes
        self.remove_paths = remove_paths

    def error(self, message):
        self.log_callback(f"ERROR: {message}")

    def warning(self, message):
        self.log_callback(f"WARNING: {message}")

    def log(self, message):
        self.log_callback(message)

    def generate_build_name(self):
        now = datetime.now()
        if self.build_naming == BUILD_NAMING_NUMERIC:
            base_name = f"build{build_number_from_date(now)}"
        else:
            base_name = f"build{now.strftime('%Y%m%d')}"
        output_root = _resolved(self.output_path or Path.cwd())
        output_root.mkdir(parents=True, exist_ok=True)
        candidate = output_root / base_name
        suffix = 0
        while candidate.exists():
            suffix += 1
            candidate = output_root / f"{base_name}_{suffix}"
        return str(candidate)

    def run_build(self, custom_assets=None):
        project_root = _resolved(self.fs_basepath)
        data_root = _require_within(project_root / self.fs_game, project_root, "Game directory")
        final_path = Path(self.generate_build_name())
        output_root = final_path.parent
        staging = Path(tempfile.mkdtemp(prefix=f".{final_path.name}-", dir=output_root))
        release_data = staging / self.fs_game
        release_data.mkdir(parents=True)
        try:
            for item in self.includes:
                source = _require_within(data_root / item, project_root, "Include")
                destination = _require_within(release_data / item, staging, "Include destination")
                _copy_tree_safe(source, destination, project_root, staging)

            for relative in sorted(set(custom_assets or [])):
                source = _require_regular_source(data_root / relative, data_root)
                destination = _safe_destination(release_data, relative)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)

            for item in self.remove_paths:
                target = _require_within(release_data / item, staging, "Remove path")
                if target.is_dir():
                    shutil.rmtree(target)
                elif target.is_file():
                    target.unlink()

            if self.pk3_packs:
                self._pack_pk3(release_data, staging)

            (staging / "version.txt").write_text(
                f"Build date: {datetime.now().isoformat()}\nBuild name: {final_path.name}\n",
                encoding="utf-8",
            )
            os.replace(staging, final_path)
            return str(final_path)
        except Exception:
            if staging.exists():
                shutil.rmtree(staging)
            raise

    def _pack_pk3(self, data_dir, staging_root):
        for pack in self.pk3_packs:
            name = str(pack.get("name", "")).strip()
            paths = pack.get("paths", [])
            if not name or not paths:
                continue
            if Path(name).name != name or name in (".", ".."):
                raise BuildError(f"Unsafe PK3 name: {name}")
            if not name.lower().endswith(".pk3"):
                name += ".pk3"
            pk3_path = _require_within(Path(data_dir) / name, staging_root, "PK3 output")
            members = []
            for item in paths:
                source = _require_within(Path(data_dir) / item, data_dir, "PK3 source")
                if source.is_symlink():
                    raise BuildError(f"Symlink PK3 sources are not allowed: {source}")
                if source.is_file():
                    members.append(source)
                elif source.is_dir():
                    for child in source.rglob("*"):
                        if child.is_symlink():
                            raise BuildError(f"Symlink PK3 sources are not allowed: {child}")
                        if child.is_file():
                            members.append(child)
                else:
                    raise BuildError(f"PK3 source not found: {source}")
            with zipfile.ZipFile(pk3_path, "w", zipfile.ZIP_DEFLATED) as archive:
                for source in sorted(set(members)):
                    archive.write(source, source.relative_to(data_dir).as_posix())
            for item in paths:
                source = _require_within(Path(data_dir) / item, data_dir, "PK3 cleanup")
                if source.is_dir():
                    shutil.rmtree(source)
                elif source.is_file():
                    source.unlink()


def _load_manifest(path):
    with open(path, "r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    if manifest.get("schema_version") != 1 or not isinstance(manifest.get("files"), list):
        raise BuildError("Manifest must have schema_version 1 and a files array")
    return manifest


def _deterministic_zip(source_dir, archive_path):
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for source in sorted(path for path in Path(source_dir).rglob("*") if path.is_file()):
            relative = source.relative_to(source_dir).as_posix()
            info = zipfile.ZipInfo(relative, _ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, source.read_bytes())


def build_manifest_release(config, version):
    """Build a distributable archive from an exact file allowlist."""
    project_root = _resolved(config["fs_basepath"])
    manifest_path = _require_regular_source(config["manifest"], project_root)
    output_root = _resolved(config.get("output_path") or project_root / "dist")
    output_root.mkdir(parents=True, exist_ok=True)
    artifact_template = config.get("artifact_name", "QuakeBuild-{version}")
    artifact_name = artifact_template.format(version=version)
    if Path(artifact_name).name != artifact_name or not artifact_name:
        raise BuildError(f"Unsafe artifact name: {artifact_name}")
    final_archive = output_root / f"{artifact_name}.zip"
    if final_archive.exists():
        raise BuildError(f"Release archive already exists: {final_archive}")

    forbidden = config.get("forbidden_globs", [])
    manifest = _load_manifest(manifest_path)
    staging = Path(tempfile.mkdtemp(prefix=f".{artifact_name}-", dir=output_root))
    temporary_archive = output_root / f".{artifact_name}.zip.tmp"
    destinations = set()
    records = []
    try:
        for entry in manifest["files"]:
            if not isinstance(entry, dict) or set(entry) != {"source", "destination"}:
                raise BuildError("Every manifest entry must contain only source and destination")
            destination_text = str(entry["destination"]).replace("\\", "/")
            if destination_text in destinations:
                raise BuildError(f"Duplicate manifest destination: {destination_text}")
            if _matches_forbidden(destination_text, forbidden):
                raise BuildError(f"Manifest destination is forbidden: {destination_text}")
            destinations.add(destination_text)
            source = _require_regular_source(project_root / entry["source"], project_root)
            destination = _safe_destination(staging, destination_text)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            records.append({
                "path": destination_text,
                "sha256": sha256_file(destination),
                "size": destination.stat().st_size,
            })

        metadata = {
            "schema_version": 1,
            "version": version,
            "project_commit": git_commit(project_root),
            "tool_commit": git_commit(Path(__file__).resolve().parent),
            "files": sorted(records, key=lambda item: item["path"]),
        }
        metadata_path = staging / "release-manifest.json"
        metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        _deterministic_zip(staging, temporary_archive)
        verify_archive(temporary_archive, forbidden)
        os.replace(temporary_archive, final_archive)
        return str(final_archive)
    except Exception:
        if temporary_archive.exists():
            temporary_archive.unlink()
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def verify_archive(archive_path, forbidden_globs=None):
    forbidden = forbidden_globs or []
    with zipfile.ZipFile(archive_path, "r") as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise BuildError("Archive contains duplicate paths")
        for name in names:
            _safe_destination(Path("."), name)
            if _matches_forbidden(name, forbidden):
                raise BuildError(f"Archive contains forbidden path: {name}")
        try:
            metadata = json.loads(archive.read("release-manifest.json"))
        except (KeyError, json.JSONDecodeError) as exc:
            raise BuildError("Archive is missing a valid release-manifest.json") from exc
        expected = {entry["path"] for entry in metadata.get("files", [])}
        actual = set(names) - {"release-manifest.json"}
        if actual != expected:
            raise BuildError("Archive members do not match the release manifest")
        for entry in metadata["files"]:
            digest = hashlib.sha256(archive.read(entry["path"])).hexdigest()
            if digest != entry["sha256"]:
                raise BuildError(f"Hash mismatch for {entry['path']}")
    return metadata
