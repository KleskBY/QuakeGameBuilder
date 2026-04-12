# QuakeGameBuilder

A build tool for creating clean, standalone releases of games built on the **DarkPlaces** (Quake) engine. It automatically scans your project's source code, maps, models, and shaders to identify only the resources your game actually uses, then packages them into a minimal release build -- no leftover dev files, no bloat.

## Features

- **QC Source Scanning** -- Extracts `.wav`, `.md3`, `.iqm`, `.obj`, `.spr`, `.spr32` references from QuakeC source files
- **BSP Map Scanning** -- Parses Quake 3 BSP files (IBSP v46) to extract entity references and texture names from lump data
- **MD3 Model Scanning** -- Reads binary MD3 model files for embedded texture paths, plus associated `.skin` files
- **Shader Resolution** -- Parses `.shader` files and resolves shader names to their actual texture dependencies (supports `map`, `animMap`, `clampMap`, `qer_editorimage`, and more)
- **Texture Variants** -- Automatically copies `_norm`, `_gloss`, and `_glow` variants alongside base textures
- **Configurable Includes/Excludes** -- Specify directories, files, and executables to always include, and paths to strip from the final build
- **Dated Builds** -- Generates uniquely named build directories (`build20260328`, `build20260328_1`, etc.)
- **PyQt6 GUI** -- Tabbed interface for scanning, reviewing resource trees, adding manual entries, and viewing build logs
- **Version Metadata** -- Each build includes a `version.txt` with build date and name

## Requirements

- Python 3.8+
- PyQt6 (for the GUI)

## Quick Start

```bash
# Clone the repository
git clone https://github.com/user/QuakeGameBuilder.git
cd QuakeGameBuilder

# Install GUI dependency
pip install PyQt6

# Launch the GUI
python run_gui.py
```

## Configuration

All settings are stored in `builder_config.json`:

```json
{
    "fs_basepath": "C:\\Path\\To\\YourGame",
    "fs_game": "data",
    "includes": [
        "cubemaps",
        "gfx",
        "maps",
        "scripts",
        "progs",
        "../bin64",
        "autoexec.cfg",
        "progs.dat",
        "../yourgame.exe"
    ],
    "remove_paths": [
        "data/gfx/ui",
        "data/maps/test.bsp"
    ]
}
```

| Key | Description |
|-----|-------------|
| `fs_basepath` | Absolute path to your game's root directory |
| `fs_game` | Name of the game data subdirectory (typically `data` or `id1`) |
| `includes` | Files and directories to always copy into the build. Paths are relative to the data directory; use `../` prefix for files outside it (executables, licenses, etc.) |
| `remove_paths` | Paths to remove from the build after copying (test maps, dev configs, template files). Relative to the data directory. |

Settings can also be edited from the GUI's **Settings** tab.

## Usage

### GUI Workflow

1. **Configure** -- Set your game directory and data folder in the Settings tab (or edit `builder_config.json`)
2. **Scan** -- Click "Scan Project" to analyze all QC files, BSP maps, MD3 models, and shaders
3. **Review** -- Browse results in the Source Analyzer (which files reference which resources) and Resource Tree (which resources are used and how often)
4. **Add Manually** -- Use the Manual Additions tab to force-include files the scanner may have missed
5. **Build** -- Click "Build Release" to create a clean build directory with only the needed files

### CLI / Standalone Scanner

Run the scanner directly to inspect dependencies:

```bash
python scanner.py
```

This prints discovered resources per source file to stdout.

### Building a Standalone Executable

Use the included batch script to package the GUI as a single `.exe` via PyInstaller:

```bash
build_tool.bat
```

This installs PyInstaller and PyQt6 if needed, then produces a standalone executable.

## How It Works

### Scan Pipeline

```
1. Load Shaders    -- Parse all .shader files in data/scripts/
                      Build a map: shader_name -> [texture dependencies]

2. Scan QC Files   -- Regex-match quoted resource paths (.wav, .md3, .spr32)
                      Auto-prefix "sound/" for .wav paths missing it

3. Scan BSP Files  -- Read IBSP v46 binary format:
                      - Lump 0 (Entities): extract sound/model refs from entity strings
                      - Lump 1 (Textures): read 72-byte texture entries
                      Resolve texture names against shader map:
                      - If name matches a shader -> expand to shader's texture deps
                      - Otherwise -> treat as direct texture reference (.png)

4. Scan MD3 Files  -- For each .md3 discovered in steps 2-3:
                      - Extract embedded texture paths from binary data
                      - Find and parse adjacent .skin files (mesh,texture format)
```

### Build Pipeline

```
1. Create dated build directory (e.g., build20260328/)
2. Copy all "includes" (configured dirs, executables, configs)
3. Copy scanned assets + manual additions into build/data/
4. For each texture, also copy _norm, _gloss, _glow variants if they exist
5. Remove configured exclude paths (test maps, dev files)
6. Write version.txt with build metadata
```

## Project Structure

```
QuakeGameBuilder/
    scanner.py           # Resource dependency scanner (QC, BSP, MD3, shaders)
    builder.py           # Build engine (copy, variant detection, cleanup)
    builder_config.json  # User configuration
    run_gui.py           # GUI entry point
    gui/
        __init__.py
        config.py        # Configuration manager (load/save JSON)
        main_window.py   # Main window with tabbed interface
        workers.py       # Background threads for scan/build operations
        tabs/
            analyzer.py  # Source Analyzer tab (file -> resources)
            resources.py # Resource Tree tab (resource -> files, with counts)
            manual.py    # Manual Additions tab
            settings.py  # Settings editor tab
            logs.py      # Build log output tab
    build_tool.bat       # PyInstaller packaging script
    run.bat              # Simple GUI launcher
    test_fix.py          # Unit tests for scanner edge cases
```

## License

GPL-3.0
