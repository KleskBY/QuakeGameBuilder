import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from builder import Builder, BuildError, build_manifest_release, verify_archive
from project_config import load_project_config
import scanner


class ScannerTests(unittest.TestCase):
    def test_texture_characters(self):
        for path in (
            "textures/button/+0terminal",
            "textures/liquids/water1_*",
            "textures/sfx/fan#1",
        ):
            self.assertTrue(scanner.is_valid_texture_path(path))

    def test_shader_parser_avoids_numeric_false_positives(self):
        content = """
textures/button/terminal_shader
{
    qer_editorimage textures/button/terminal_editor.tga
    { animMap 2 textures/button/anim1 textures/button/anim2 textures/button/anim3 }
    { tcMod scale 0.25 0.5 }
}
"""
        found = set(scanner.parse_shader_content(content)["textures/button/terminal_shader"])
        self.assertEqual(found, {
            "textures/button/terminal_editor.png",
            "textures/button/anim1.png",
            "textures/button/anim2.png",
            "textures/button/anim3.png",
        })


class ManifestBuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "data").mkdir()
        (self.root / "data" / "progs.dat").write_bytes(b"compiled")
        self.manifest = self.root / "manifest.json"
        self.manifest.write_text(json.dumps({
            "schema_version": 1,
            "files": [{"source": "data/progs.dat", "destination": "data/progs.dat"}],
        }), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def config(self, output="dist"):
        return {
            "fs_basepath": str(self.root),
            "output_path": str(self.root / output),
            "manifest": str(self.manifest),
            "artifact_name": "test-{version}",
            "forbidden_globs": ["**/*.sav", "halflife_src/**"],
        }

    def test_exact_manifest_build_and_verify(self):
        archive = build_manifest_release(self.config(), "1.0.0")
        metadata = verify_archive(archive, self.config()["forbidden_globs"])
        self.assertEqual(metadata["version"], "1.0.0")
        self.assertEqual([item["path"] for item in metadata["files"]], ["data/progs.dat"])

    def test_deterministic_archive(self):
        first = Path(build_manifest_release(self.config("one"), "1.0.0")).read_bytes()
        second = Path(build_manifest_release(self.config("two"), "1.0.0")).read_bytes()
        self.assertEqual(first, second)

    def test_missing_source_leaves_no_release(self):
        (self.root / "data" / "progs.dat").unlink()
        with self.assertRaises(BuildError):
            build_manifest_release(self.config(), "1.0.0")
        self.assertFalse((self.root / "dist" / "test-1.0.0.zip").exists())

    def test_forbidden_destination_is_rejected(self):
        self.manifest.write_text(json.dumps({
            "schema_version": 1,
            "files": [{"source": "data/progs.dat", "destination": "data/save.sav"}],
        }), encoding="utf-8")
        with self.assertRaises(BuildError):
            build_manifest_release(self.config(), "1.0.0")

    def test_destination_traversal_is_rejected(self):
        self.manifest.write_text(json.dumps({
            "schema_version": 1,
            "files": [{"source": "data/progs.dat", "destination": "../escape.dat"}],
        }), encoding="utf-8")
        with self.assertRaises(BuildError):
            build_manifest_release(self.config(), "1.0.0")

    def test_source_traversal_is_rejected(self):
        outside = self.root.parent / "outside.dat"
        outside.write_bytes(b"outside")
        self.addCleanup(lambda: outside.unlink(missing_ok=True))
        self.manifest.write_text(json.dumps({
            "schema_version": 1,
            "files": [{"source": "../outside.dat", "destination": "outside.dat"}],
        }), encoding="utf-8")
        with self.assertRaises(BuildError):
            build_manifest_release(self.config(), "1.0.0")

    def test_symlink_source_is_rejected(self):
        link = self.root / "data" / "link.dat"
        try:
            link.symlink_to(self.root / "data" / "progs.dat")
        except OSError as exc:
            self.skipTest(f"Symlinks unavailable: {exc}")
        self.manifest.write_text(json.dumps({
            "schema_version": 1,
            "files": [{"source": "data/link.dat", "destination": "data/link.dat"}],
        }), encoding="utf-8")
        with self.assertRaises(BuildError):
            build_manifest_release(self.config(), "1.0.0")

    def test_legacy_remove_cannot_escape_staging(self):
        outside = self.root / "outside.txt"
        outside.write_text("keep", encoding="utf-8")
        builder = Builder()
        builder.set_paths(self.root, "data")
        builder.output_path = self.root / "legacy-output"
        builder.set_config([], ["../../outside.txt"])
        with self.assertRaises(BuildError):
            builder.run_build()
        self.assertEqual(outside.read_text(encoding="utf-8"), "keep")

    def test_unsafe_pk3_name_is_rejected(self):
        builder = Builder()
        builder.set_paths(self.root, "data")
        builder.output_path = self.root / "legacy-output"
        builder.set_config(["progs.dat"], [])
        builder.pk3_packs = [{"name": "../escape.pk3", "paths": ["progs.dat"]}]
        with self.assertRaises(BuildError):
            builder.run_build()

    def test_tampered_archive_fails_verification(self):
        archive = Path(build_manifest_release(self.config(), "1.0.0"))
        with zipfile.ZipFile(archive, "a") as handle:
            handle.writestr("extra.txt", "unexpected")
        with self.assertRaises(BuildError):
            verify_archive(archive)

    def test_relative_config_paths_resolve_from_config(self):
        config_dir = self.root / "configs"
        config_dir.mkdir()
        path = config_dir / "project.json"
        path.write_text(json.dumps({
            "fs_basepath": "..",
            "output_path": "../out",
            "manifest": "../manifest.json",
        }), encoding="utf-8")
        loaded = load_project_config(path)
        self.assertEqual(Path(loaded["fs_basepath"]), self.root)
        self.assertEqual(Path(loaded["manifest"]), self.manifest)

    def test_legacy_config_defaults_to_scan_mode(self):
        path = self.root / "legacy.json"
        path.write_text(json.dumps({"fs_basepath": ".", "fs_game": "data"}), encoding="utf-8")
        self.assertEqual(load_project_config(path)["build_mode"], "scan")


if __name__ == "__main__":
    unittest.main()
