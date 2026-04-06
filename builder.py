import os
import shutil
import zipfile
from datetime import datetime

BUILD_NAMING_DATE = "date"
BUILD_NAMING_NUMERIC = "numeric"

# Days elapsed at the start of each month (non-leap year)
_MONTH_DAYS = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 303, 334]

def build_number_from_date(dt):
    """Compute a numeric build number: 365*(y-1999) - 31 + days_in_year + day."""
    y, m, d = dt.year, dt.month, dt.day
    return 365 * (y - 1999) - 31 + _MONTH_DAYS[m - 1] + d

class Builder:
    def __init__(self):
        self.log_callback = print
        self.fs_basepath = "../" # Default relative to builder script
        self.fs_game = "data"
        self.output_path = "" # Empty = current directory
        self.build_naming = BUILD_NAMING_DATE
        self.includes = []
        self.remove_paths = []
        self.pk3_packs = []  # [{"name": "textures.pk3", "paths": ["textures/", "env/"]}, ...]

    def set_paths(self, fs_basepath, fs_game):
        self.fs_basepath = fs_basepath
        self.fs_game = fs_game
        
    def set_config(self, includes, remove_paths):
        self.includes = includes
        self.remove_paths = remove_paths

    def error(self, msg):
        self.log_callback(f"❌ ERROR: {msg}")

    def warning(self, msg):
        self.log_callback(f"⚠️ WARNING: {msg}")

    def log(self, msg):
        self.log_callback(f"🔧 {msg}")

    def generate_build_name(self):
        now = datetime.now()
        if self.build_naming == BUILD_NAMING_NUMERIC:
            num = build_number_from_date(now)
            build_base = f"build{num}"
        else:
            build_base = f"build{now.strftime('%Y%m%d')}"

        base_dir = self.output_path or ""
        suffix = 0
        build_name = build_base
        full_path = os.path.join(base_dir, build_name) if base_dir else build_name
        while os.path.exists(full_path):
            suffix += 1
            build_name = f"{build_base}_{suffix}"
            full_path = os.path.join(base_dir, build_name) if base_dir else build_name
        return full_path

    def copy_file(self, src, dst):
        if os.path.isfile(src):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            return True
        return False

    def copy_extra_texture_variants(self, relative_path, src_root, dst_root):
        """Copies _norm, _gloss, _glow variants for a texture."""
        if not relative_path.lower().endswith(".png"):
            return

        base_rel = relative_path[:-4] # remove .png
        for suffix in ["_norm.png", "_gloss.png", "_glow.png"]:
            extra_rel = base_rel + suffix
            extra_src = os.path.join(src_root, extra_rel)
            extra_dst = os.path.join(dst_root, extra_rel)
            
            if os.path.isfile(extra_src):
                self.copy_file(extra_src, extra_dst)
                self.log(f"  └─ Copied variant: {extra_rel}")

    def run_build(self, custom_assets=None):
        """
        Main build execution.
        custom_assets: list of relative paths (strings) to include.
        """
        release_path = self.generate_build_name()
        self.log(f"Creating build: {release_path}")
        
        # Resolve paths
        data_path = os.path.join(self.fs_basepath, self.fs_game)
        qc_path = os.path.join(self.fs_basepath, "qc")
        
        release_data_path = os.path.join(release_path, self.fs_game)
        os.makedirs(release_data_path, exist_ok=True)

        self.log(f"Source Data: {data_path}")
        self.log("Copying includes...")
        
        for item in self.includes:
            src = os.path.normpath(os.path.join(data_path, item))
            dst = os.path.normpath(os.path.join(release_data_path, item))
            
            if os.path.isdir(src):
                # It's a directory
                shutil.copytree(src, dst, dirs_exist_ok=True)
            elif os.path.isfile(src):
                # It's a file
                self.copy_file(src, dst)
            else:
                self.warning(f"Include path not found: {src}")

        self.log("Copying assets...")
        assets_to_copy = set(custom_assets) if custom_assets else set()

        for relative_path in sorted(list(assets_to_copy)):
            src_path = os.path.join(data_path, relative_path)
            dst_path = os.path.join(release_data_path, relative_path)
            
            if self.copy_file(src_path, dst_path):
                self.log(f"Copied asset: {relative_path}")
                # Check for texture variants
                if relative_path.startswith("textures/"):
                    self.copy_extra_texture_variants(relative_path, data_path, release_data_path)
            else:
                 # Try with prefixes (legacy fallback logic could go here if needed, 
                 # but cleaner to assume full paths in new system)
                 self.warning(f"File not found: {relative_path}")

        self.log("Removing unwanted paths...")
        for path in self.remove_paths:
            full_path = os.path.normpath(os.path.join(release_data_path, path))
            if os.path.isdir(full_path):
                shutil.rmtree(full_path, ignore_errors=True)
            elif os.path.isfile(full_path):
                os.remove(full_path)

        # Pack PK3 files
        if self.pk3_packs:
            self.log("Packing PK3 files...")
            self._pack_pk3(release_data_path)

        with open(os.path.join(release_path, "version.txt"), 'w') as vf:
            vf.write(f"Build date: {datetime.now().isoformat()}\n")
            vf.write(f"Build name: {release_path}\n")

        self.log("✅ Build complete.")
        return release_path

    def _pack_pk3(self, data_dir):
        """Pack specified directories into PK3 (zip) files and remove the originals."""
        for pack in self.pk3_packs:
            pk3_name = pack.get("name", "").strip()
            paths = pack.get("paths", [])
            if not pk3_name or not paths:
                continue

            if not pk3_name.lower().endswith(".pk3"):
                pk3_name += ".pk3"

            pk3_path = os.path.join(data_dir, pk3_name)
            file_count = 0

            with zipfile.ZipFile(pk3_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for prefix in paths:
                    prefix = prefix.strip().rstrip("/")
                    full_prefix = os.path.join(data_dir, prefix)
                    if os.path.isdir(full_prefix):
                        for root, _, files in os.walk(full_prefix):
                            for f in files:
                                abs_path = os.path.join(root, f)
                                arc_name = os.path.relpath(abs_path, data_dir).replace("\\", "/")
                                zf.write(abs_path, arc_name)
                                file_count += 1
                    elif os.path.isfile(full_prefix):
                        arc_name = os.path.relpath(full_prefix, data_dir).replace("\\", "/")
                        zf.write(full_prefix, arc_name)
                        file_count += 1
                    else:
                        self.warning(f"PK3 path not found: {prefix}")

            if file_count > 0:
                self.log(f"Packed {pk3_name} ({file_count} files)")
                # Remove the original directories/files that were packed
                for prefix in paths:
                    prefix = prefix.strip().rstrip("/")
                    full_prefix = os.path.join(data_dir, prefix)
                    if os.path.isdir(full_prefix):
                        shutil.rmtree(full_prefix, ignore_errors=True)
                    elif os.path.isfile(full_prefix):
                        os.remove(full_prefix)
            else:
                # Empty pk3, remove it
                os.remove(pk3_path)
                self.warning(f"PK3 {pk3_name} skipped (no files matched)")

def main():
    # Legacy CLI entry point
    builder = Builder()
    # Mock defaults if run directly?
    # For now, running directly might miss config. 
    # But this is primarily a library now.
    builder.run_build()

if __name__ == "__main__":
    main()

