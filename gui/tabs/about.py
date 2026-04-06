from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTextBrowser, QLabel
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtCore import QUrl

APP_VERSION = "0.1.0"
APP_AUTHOR = "KleskBY"
APP_REPO = "https://github.com/KleskBY/QuakeGameBuilder"
APP_WEBSITE = "https://quake.by"


class AboutTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        content = QTextBrowser()
        content.setOpenExternalLinks(True)
        content.setReadOnly(True)
        content.setHtml(self._build_html())
        layout.addWidget(content)

    def _build_html(self):
        return f"""
        <style>
            body {{ font-family: Segoe UI, sans-serif; padding: 16px; }}
            h1 {{ margin-bottom: 4px; }}
            .meta {{ color: #888; margin-bottom: 16px; }}
            .meta a {{ color: #4a9eff; }}
            h2 {{ color: #ddd; border-bottom: 1px solid #444; padding-bottom: 4px; margin-top: 24px; }}
            h3 {{ color: #ccc; margin-top: 16px; }}
            table {{ border-collapse: collapse; margin: 8px 0; }}
            th, td {{ border: 1px solid #555; padding: 6px 12px; text-align: left; }}
            th {{ background: #333; }}
            code {{ background: #2a2a2a; padding: 2px 6px; border-radius: 3px; font-size: 13px; }}
            pre {{ background: #1e1e1e; padding: 12px; border-radius: 4px; overflow-x: auto; font-size: 13px; }}
            ul {{ margin: 4px 0; padding-left: 24px; }}
            li {{ margin: 3px 0; }}
            a {{ color: #4a9eff; }}
        </style>

        <h1>Quake Game Builder</h1>
        <p class="meta">
            Version <b>{APP_VERSION}</b> &nbsp;&middot;&nbsp;
            Author <b>{APP_AUTHOR}</b> &nbsp;&middot;&nbsp;
            <a href="{APP_REPO}">GitHub</a> &nbsp;&middot;&nbsp;
            <a href="{APP_WEBSITE}">Website</a>
        </p>

        <p>A build tool for creating clean, standalone releases of games built on the
        <b>DarkPlaces</b> (Quake) engine. It automatically scans your project's source code,
        maps, models, and shaders to identify only the resources your game actually uses,
        then packages them into a minimal release build &mdash; no leftover dev files, no bloat.</p>

        <h2>Features</h2>
        <ul>
            <li><b>QC Source Scanning</b> &mdash; Extracts <code>.wav</code>, <code>.md3</code>,
                <code>.iqm</code>, <code>.obj</code>, <code>.mdl</code>, <code>.spr32</code>
                references from QuakeC source files</li>
            <li><b>BSP Map Scanning</b> &mdash; Parses Quake 1 BSP29, BSP2, 2PSB, and
                Quake 3 IBSP v46 formats to extract entity references and texture names</li>
            <li><b>Model Scanning</b> &mdash; Reads MD3 (binary texture paths), IQM (material names),
                OBJ (mtllib + .mtl textures), plus associated <code>.skin</code> files</li>
            <li><b>Shader Resolution</b> &mdash; Parses <code>.shader</code> files and resolves
                shader names to actual texture dependencies (<code>map</code>, <code>animMap</code>,
                <code>clampMap</code>, <code>qer_editorimage</code>, etc.)</li>
            <li><b>PBR Texture Variants</b> &mdash; Automatically copies <code>_norm</code>,
                <code>_gloss</code>, and <code>_glow</code> variants alongside base textures</li>
            <li><b>PK3 Packing</b> &mdash; Pack specified directories into <code>.pk3</code>
                archives (renamed .zip) for the Quake engine</li>
            <li><b>Configurable Includes/Excludes</b> &mdash; Specify directories, files, and
                executables to always include, and paths to strip from the final build</li>
            <li><b>Build Naming</b> &mdash; Choose between date-based (<code>build20260328</code>)
                or numeric naming schemes</li>
            <li><b>Missing File Detection</b> &mdash; Scanned resources that don't exist on disk
                are highlighted red in the Resource Tree</li>
        </ul>

        <h2>Usage</h2>
        <h3>Workflow</h3>
        <ol>
            <li><b>Configure</b> &mdash; Set <code>fs_basepath</code> (game root) and
                <code>fs_game</code> (data folder name) in the Settings tab</li>
            <li><b>Scan</b> &mdash; Click <i>Scan Project</i> to analyze QC files, BSP maps,
                models, and shaders</li>
            <li><b>Review</b> &mdash; Browse the Source Analyzer (which files reference which
                resources) and Resource Tree (all resources with missing file detection)</li>
            <li><b>Build</b> &mdash; Click <i>Build</i> to create a clean release with only
                the needed files</li>
        </ol>

        <h3>Standalone Executable</h3>
        <p>Use <code>build_tool.bat</code> to package the GUI as a single <code>.exe</code>
        via PyInstaller.</p>

        <h2>Configuration</h2>
        <p>All settings are stored in a JSON project file:</p>
        <table>
            <tr><th>Key</th><th>Description</th></tr>
            <tr><td><code>fs_basepath</code></td>
                <td>Absolute path to your game's root directory</td></tr>
            <tr><td><code>fs_game</code></td>
                <td>Name of the game data subdirectory (e.g. <code>data</code>, <code>id1</code>)</td></tr>
            <tr><td><code>output_path</code></td>
                <td>Where to write builds (empty = current directory)</td></tr>
            <tr><td><code>build_naming</code></td>
                <td>Naming scheme: <code>date</code> or <code>numeric</code></td></tr>
            <tr><td><code>includes</code></td>
                <td>Files/directories to always copy. Relative to data dir; use <code>../</code>
                    for paths outside it</td></tr>
            <tr><td><code>remove_paths</code></td>
                <td>Paths to strip from the build after copying</td></tr>
            <tr><td><code>pk3_packs</code></td>
                <td>Directories to pack into <code>.pk3</code> archives</td></tr>
        </table>

        <h2>Scan Pipeline</h2>
        <pre>
1. Load Shaders    Parse all .shader files in data/scripts/
                   Build map: shader_name -> [texture dependencies]

2. Scan QC Files   Regex-match resource paths (.wav, .md3, .iqm, .obj, .mdl, .spr, .spr32)
                   Auto-prefix "sound/" for .wav paths missing it

3. Scan BSP Files  Read Q1 BSP29 / BSP2 / 2PSB / Q3 IBSP v46:
                   - Entities lump: extract sound/model refs
                   - Textures lump: read texture names
                   Resolve names against shader map

4. Scan Models     For each model discovered in steps 2-3:
                   - MD3: extract embedded texture paths
                   - IQM: read mesh material names from text table
                   - OBJ: parse mtllib -> .mtl texture maps
                   - MDL: recognized (textures are embedded/external by convention)
                   - Find and parse adjacent .skin files</pre>

        <h2>Build Pipeline</h2>
        <pre>
1. Create build directory with chosen naming scheme
2. Copy all configured includes (dirs, executables, configs)
3. Copy scanned assets into build/data/
4. Copy PBR variants (_norm, _gloss, _glow) alongside textures
5. Remove configured exclude paths
6. Pack specified directories into .pk3 archives
7. Write version.txt with build metadata</pre>

        <h2>Requirements</h2>
        <ul>
            <li>Python 3.8+</li>
            <li>PyQt6 (for the GUI)</li>
        </ul>
        <p>The scanner and builder core (<code>scanner.py</code>, <code>builder.py</code>)
        use only the Python standard library.</p>

        <h2>License</h2>
        <p>GPL-3.0</p>
        """
