import os
import re
import struct
import zipfile
import glob as _glob

# Configuration Defaults (can be overridden)
QC_DIR = "../qc"
BSP_DIR = "../data/maps"

IMAGE_EXTENSIONS = [".png", ".tga", ".jpg", ".jpeg", ".webp"]

def resolve_image_extension(rel_path, data_dir):
    """
    For image resource paths: if the file doesn't exist with its current extension,
    try the other known image extensions and return the first one found on disk.
    Non-image paths are returned unchanged.
    """
    ext = os.path.splitext(rel_path)[1].lower()
    if ext not in IMAGE_EXTENSIONS:
        return rel_path
    if os.path.isfile(os.path.join(data_dir, rel_path)):
        return rel_path
    base = os.path.splitext(rel_path)[0]
    for alt in IMAGE_EXTENSIONS:
        if alt == ext:
            continue
        candidate = base + alt
        if os.path.isfile(os.path.join(data_dir, candidate)):
            return candidate
    return rel_path  # not found with any extension, keep original


def is_valid_resource(path, extensions):
    """Checks if a path has one of the valid extensions and reasonable length."""
    path = path.strip().lower()
    return any(path.endswith(ext) and len(path) > 4 for ext in extensions)

def should_ignore(path):
    path = path.lower()
    return (path == "textures/weapons" or 
            path == "textures/monsters/dog/dog" or 
            path == "$lightmap" or 
            path == "noshader" or 
            path == "textures/common/caulk" or 
            path == "textures/common/clip" or 
            path == "textures/common/trigger")

def is_valid_texture_path(path):
    """
    Validates that the path contains only safe characters.
    Rejects spaces, $, control chars, etc.
    Allowed: A-Z, a-z, 0-9, _, -, /, .
    """
    # Regex for safe path
    # Note: we need to allow correct directory separators. we assume / is used internally.
    # We allow +, *, and # which are common in Quake-style texture names (sequences, etc).
    return re.match(r'^[a-zA-Z0-9_\-\/\.\+\*\#]+$', path) is not None

# --- QC Scanning Logic ---

def _strip_qc_inactive_code(content):
    """
    Remove inactive code from QC source before scanning for resource references.
    Handles in order:
      1. Block comments  /* ... */   (multiline, newlines preserved)
      2. #if 0 ... #endif blocks     (with correct nesting; #else re-activates)
      3. Line comments   // ...
    """
    # 1. Block comments — replace with equivalent newlines to keep line numbers intact
    content = re.sub(
        r'/\*.*?\*/',
        lambda m: '\n' * m.group().count('\n'),
        content,
        flags=re.DOTALL
    )

    # 2. #if 0 blocks with nesting
    lines = content.split('\n')
    out = []
    skip_depth = 0
    for line in lines:
        s = line.strip()
        if skip_depth > 0:
            if re.match(r'#\s*if\b', s):           # nested #if inside skipped block
                skip_depth += 1
            elif re.match(r'#\s*endif\b', s):
                skip_depth -= 1
            elif skip_depth == 1 and re.match(r'#\s*else\b', s):
                skip_depth = 0                       # #else of the #if 0 is live code
            out.append('')                           # blank the skipped line
        else:
            if re.match(r'#\s*if\s+0\b', s):
                skip_depth = 1
                out.append('')
            else:
                out.append(line)
    content = '\n'.join(out)

    # 3. Line comments — strip from // to end of line
    # QC resource paths never contain "://" so this is safe
    result = []
    for line in content.split('\n'):
        idx = line.find('//')
        result.append(line[:idx] if idx >= 0 else line)
    return '\n'.join(result)


def extract_from_qc_content(content):
    """Extracts resource references from QC text content."""
    resources = set()

    content = _strip_qc_inactive_code(content)

    # --- Explicitly-extensioned resources ---
    # Match any quoted path ending with a known extension.
    patterns = [
        r'"([a-zA-Z0-9_\-\/]+\.wav)"',
        r'"([a-zA-Z0-9_\-\/]+\.md3)"',
        r'"([a-zA-Z0-9_\-\/]+\.iqm)"',
        r'"([a-zA-Z0-9_\-\/]+\.obj)"',
        r'"([a-zA-Z0-9_\-\/]+\.mdl)"',
        r'"([a-zA-Z0-9_\-\/]+\.spr)"',
        r'"([a-zA-Z0-9_\-\/]+\.spr32)"',
        # UI / HUD images referenced with explicit extension
        r'"([a-zA-Z0-9_\-\/]+\.png)"',
        r'"([a-zA-Z0-9_\-\/]+\.jpg)"',
        r'"([a-zA-Z0-9_\-\/]+\.jpeg)"',
        r'"([a-zA-Z0-9_\-\/]+\.tga)"',
        r'"([a-zA-Z0-9_\-\/]+\.webp)"',
        # Fonts
        r'"([a-zA-Z0-9_\-\/]+\.ttf)"',
        r'"([a-zA-Z0-9_\-\/]+\.otf)"',
    ]
    for p in patterns:
        for m in re.findall(p, content):
            if m.endswith(".wav") and not m.startswith("sound/"):
                m = "sound/" + m
            resources.add(m)

    # --- Extensionless image paths from UI draw calls ---
    # drawpic / drawsubpic / precache_pic often pass paths without an extension;
    # the engine tries .tga, .png, .jpg in order. We record these as .png so the
    # builder knows at least one variant is needed (PBR logic handles the rest).
    # Require at least one '/' so bare strings like cvar names ("zr_hotbar") are ignored.
    # Real image paths always have a directory component (e.g. "gfx/hud/health").
    ui_funcs = r'(?:drawpic|drawsubpic|precache_pic)\s*\([^)]*"([a-zA-Z0-9_\-\/]+\/[a-zA-Z0-9_\-\/]+)"'
    for m in re.findall(ui_funcs, content, re.IGNORECASE):
        # Skip if it already has a known extension (caught above)
        if not re.search(r'\.(wav|md3|iqm|obj|mdl|spr32?|png|jpe?g|tga|webp)$', m, re.IGNORECASE):
            resources.add(m + ".png")
 

    return list(resources)

def scan_qc_files(qc_dir=QC_DIR):
    """
    Scans all .qc files in the directory.
    Returns a dict: { "absolute/path/to/file.qc": [ "resource1.wav", ... ] }
    """
    results = {}
    if not os.path.exists(qc_dir):
        return results

    for root, _, files in os.walk(qc_dir):
        for file in files:
            if file.lower().endswith(".qc") or file.lower().endswith(".c") or file.lower().endswith(".h") or file.lower().endswith(".qh"):
                path = os.path.join(root, file)
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                        resources = extract_from_qc_content(content)
                        if resources:
                            results[path] = resources
                except Exception as e:
                    print(f"Error scanning QC {path}: {e}")
    return results

# --- BSP Scanning Logic ---

def _extract_entities(raw_bytes):
    """Extract resource references (.wav, .md3, .iqm, .obj, .mdl, .spr, .spr32) from BSP entity lump data."""
    resources = set()
    try:
        text = raw_bytes.decode('utf-8', errors='ignore')
        matches = re.findall(r'"([^"]+)"', text)
        for m in matches:
            if is_valid_resource(m, [".wav", ".md3", ".iqm", ".obj", ".mdl", ".spr", ".spr32"]):
                clean_m = m.strip()
                if clean_m.endswith(".wav") and not clean_m.startswith("sound/"):
                    clean_m = "sound/" + clean_m
                resources.add(clean_m)
    except Exception:
        pass
    return resources

def _scan_q3_bsp(f):
    """Parse a Quake 3 BSP (IBSP v46). File position is after the 8-byte header."""
    resources = set()

    # 17 lumps: offset + size
    lumps = [struct.unpack('<ii', f.read(8)) for _ in range(17)]

    # Entities (Lump 0)
    ents_offset, ents_length = lumps[0]
    f.seek(ents_offset)
    resources.update(_extract_entities(f.read(ents_length)))

    # Textures (Lump 1) — 72-byte entries: 64-char name + 4 flags + 4 contents
    tex_offset, tex_length = lumps[1]
    num_textures = tex_length // 72
    f.seek(tex_offset)
    for _ in range(num_textures):
        name_bytes = f.read(64)
        f.read(8)  # flags + contents
        name = name_bytes.rstrip(b'\x00').decode('utf-8', errors='ignore')
        if name and not should_ignore(name) and is_valid_texture_path(name):
            resources.add(name + ".png")

    return resources

def _scan_q1_bsp(f):
    """Parse a Quake 1 BSP (version 29). File position is after the 4-byte version."""
    resources = set()

    # 15 lumps: offset + size
    lumps = [struct.unpack('<ii', f.read(8)) for _ in range(15)]

    # Entities (Lump 0)
    ents_offset, ents_length = lumps[0]
    f.seek(ents_offset)
    resources.update(_extract_entities(f.read(ents_length)))

    # Mip Textures (Lump 2)
    # Format: mipheader_t { long numtex; long offset[numtex]; }
    # Each offset points to miptex_t { char name[16]; u_long width, height, offset1-4; }
    # Offsets are relative to lump start. -1 means texture is in external WAD.
    tex_offset, tex_length = lumps[2]
    if tex_length > 4:
        f.seek(tex_offset)
        numtex = struct.unpack('<i', f.read(4))[0]
        if 0 < numtex < 65536:
            offsets = [struct.unpack('<i', f.read(4))[0] for _ in range(numtex)]
            for off in offsets:
                if off < 0:
                    continue  # texture in external WAD, not in BSP
                f.seek(tex_offset + off)
                name_bytes = f.read(16)
                name = name_bytes.split(b'\x00', 1)[0].decode('ascii', errors='ignore')
                if name and not should_ignore(name) and is_valid_texture_path(name):
                    resources.add(name + ".png")

    return resources

def scan_bsp_files(bsp_dir=BSP_DIR):
    """
    Scans Quake 1 (BSP29), BSP2, 2PSB, and Quake 3 (IBSP v46) files for resource references.
    Returns a dict: { "absolute/path/to/map.bsp": [ "resource1.wav", ... ] }
    """
    results = {}
    if not os.path.exists(bsp_dir):
        return results

    for root, _, files in os.walk(bsp_dir):
        for file in files:
            if file.lower().endswith(".bsp"):
                path = os.path.join(root, file)
                try:
                    with open(path, "rb") as f:
                        header = f.read(4)

                        if header == b'IBSP':
                            # Quake 3 BSP
                            version = struct.unpack('<i', f.read(4))[0]
                            if version == 0x2e:
                                resources = _scan_q3_bsp(f)
                            else:
                                continue
                        elif header in (b'BSP2', b'2PSB'):
                            # BSP2 / 2PSB — extended Q1 format, same lump layout
                            resources = _scan_q1_bsp(f)
                        else:
                            # Quake 1 BSP — no magic, first 4 bytes are version
                            version = struct.unpack('<i', header)[0]
                            if version == 29:
                                resources = _scan_q1_bsp(f)
                            else:
                                continue

                        if resources:
                            results[path] = list(resources)
                except Exception as e:
                    print(f"Error scanning BSP {path}: {e}")
    return results

# --- MD3 Scanning Logic ---

def extract_from_md3(path):
    """Extracts shader/texture references from an MD3 file.

    Uses proper structural parsing (surface → shader NAME fields) as the primary
    method, with a textures/-anchored regex fallback for any paths the parser misses.
    """
    textures = set()

    def _add(name):
        name = re.sub(r'\.(tga|jpg|jpeg|png|bmp|webp)$', '', name, flags=re.IGNORECASE)
        if name and not should_ignore(name) and is_valid_texture_path(name):
            textures.add(name + ".png")

    try:
        with open(path, "rb") as f:
            data = f.read()

        # --- Structural parsing ---
        # Header layout (all S32 little-endian):
        #   0  IDENT "IDP3"
        #   4  VERSION
        #   8  NAME[64]
        #  72  FLAGS
        #  76  NUM_FRAMES
        #  80  NUM_TAGS
        #  84  NUM_SURFACES
        #  88  NUM_SKINS
        #  92  OFS_FRAMES
        #  96  OFS_TAGS
        # 100  OFS_SURFACES
        # 104  OFS_EOF
        if len(data) >= 108 and data[:4] == b'IDP3':
            try:
                num_surfaces = struct.unpack_from('<i', data, 84)[0]
                ofs_surfaces = struct.unpack_from('<i', data, 100)[0]

                surface_base = ofs_surfaces
                for _ in range(num_surfaces):
                    if surface_base + 108 > len(data):
                        break

                    # Surface header layout:
                    #   0  IDENT
                    #   4  NAME[64]
                    #  68  FLAGS
                    #  72  NUM_FRAMES
                    #  76  NUM_SHADERS
                    #  80  NUM_VERTS
                    #  84  NUM_TRIANGLES
                    #  88  OFS_TRIANGLES
                    #  92  OFS_SHADERS
                    #  96  OFS_ST
                    # 100  OFS_XYZNORMAL
                    # 104  OFS_END
                    num_shaders = struct.unpack_from('<i', data, surface_base + 76)[0]
                    ofs_shaders = struct.unpack_from('<i', data, surface_base + 92)[0]
                    ofs_end     = struct.unpack_from('<i', data, surface_base + 104)[0]

                    # Each Shader entry: NAME[64] + SHADER_INDEX(4) = 68 bytes
                    shader_base = surface_base + ofs_shaders
                    for j in range(num_shaders):
                        off = shader_base + j * 68
                        if off + 64 > len(data):
                            break
                        name = data[off:off + 64].split(b'\x00', 1)[0].decode('utf-8', errors='ignore')
                        _add(name)

                    if ofs_end <= 0:
                        break
                    surface_base += ofs_end
            except Exception:
                pass

        # --- Regex fallback ---
        # Catches any paths the structural parser missed (e.g. malformed surfaces).
        # Anchored to textures/ to avoid garbage from binary data; captures full
        # path (e.g. models/foo/textures/bar) by scanning token-by-token.
        candidates = re.findall(rb'[a-zA-Z0-9_.+\-*#/]{4,256}', data)
        for c in candidates:
            if b'textures/' in c:
                try:
                    _add(c.decode('utf-8', errors='ignore'))
                except Exception:
                    pass

    except Exception as e:
        print(f"Error scanning MD3 {path}: {e}")

    return list(textures)

def extract_from_events(path):
    """Extracts .wav sound references from an IQM .events sidecar.

    Format (whitespace-separated): <group> <time> <eventcode> <opts>
    The <opts> field holds a .wav path for sound events (e.g. an HL SCRIPT_EVENT
    footstep), or a number / "-" for non-sound events. We only harvest tokens
    ending in .wav. Sound paths in .events are stored WITHOUT the sound/ prefix
    (the engine plays them via the sound() builtin, which is rooted at sound/),
    so we normalize to "sound/..." to match how QC/BSP .wav refs are recorded.
    """
    sounds = set()
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("//"):
                    continue
                for tok in line.split():
                    t = tok.strip().lower()
                    # HL prefixes streamed/looping sounds with '*' (a precache
                    # sentinel the engine strips, not part of the filename).
                    t = t.lstrip("*")
                    if t.endswith(".wav") and len(t) > 4:
                        if not t.startswith("sound/"):
                            t = "sound/" + t
                        if is_valid_texture_path(t):
                            sounds.add(t)
    except Exception as e:
        print(f"Error scanning events {path}: {e}")
    return list(sounds)


def extract_from_skin(path):
    """Extracts texture references from a .skin file (mesh,texture)."""
    textures = set()
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("//"):
                    continue
                
                parts = line.split(',')
                if len(parts) >= 2:
                    # format: meshname,texturepath
                    tex = parts[1].strip()
                    # Clean up
                    tex = re.sub(r'\.(tga|jpg|jpeg|png|bmp)$', '', tex, flags=re.IGNORECASE)
                    
                    if not should_ignore(tex) and is_valid_texture_path(tex):
                        textures.add(tex + ".png")
    except Exception as e:
        print(f"Error scanning skin {path}: {e}")
    return list(textures)


# --- IQM Scanning Logic ---

def extract_from_iqm(path):
    """Extracts material/texture references from an IQM model file."""
    textures = set()
    try:
        with open(path, "rb") as f:
            magic = f.read(16)
            if magic != b'INTERQUAKEMODEL\0':
                return []

            version = struct.unpack('<I', f.read(4))[0]
            if version != 2:
                return []

            filesize, flags = struct.unpack('<II', f.read(8))
            num_text, ofs_text = struct.unpack('<II', f.read(8))
            num_meshes, ofs_meshes = struct.unpack('<II', f.read(8))

            # Read the text table
            if num_text > 0 and ofs_text > 0:
                f.seek(ofs_text)
                text_data = f.read(num_text)
            else:
                text_data = b''

            # Read meshes — each is 6 uints (24 bytes)
            if num_meshes > 0 and ofs_meshes > 0:
                f.seek(ofs_meshes)
                for _ in range(num_meshes):
                    mesh_data = struct.unpack('<6I', f.read(24))
                    material_offset = mesh_data[1]  # material field

                    if 0 < material_offset < len(text_data):
                        # Extract null-terminated string from text table
                        end = text_data.index(b'\0', material_offset) if b'\0' in text_data[material_offset:] else len(text_data)
                        material = text_data[material_offset:end].decode('utf-8', errors='ignore')
                        if material and is_valid_texture_path(material):
                            # Strip existing extension if present
                            clean = re.sub(r'\.(tga|jpg|jpeg|png|bmp)$', '', material, flags=re.IGNORECASE)
                            if not should_ignore(clean):
                                textures.add(clean + ".png")
    except Exception as e:
        print(f"Error scanning IQM {path}: {e}")
    return list(textures)


# --- OBJ Scanning Logic ---

def extract_from_obj(path):
    """Extracts material library and texture references from an OBJ model file."""
    textures = set()
    obj_dir = os.path.dirname(path)
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line.lower().startswith("mtllib "):
                    mtl_name = line.split(None, 1)[1].strip()
                    mtl_path = os.path.join(obj_dir, mtl_name)
                    # Add the .mtl file itself as a dependency
                    # textures.add(mtl_name)
                    # Parse the .mtl file for texture maps
                    # mtl_textures = _parse_mtl_file(mtl_path, obj_dir)
                    # textures.update(mtl_textures)
    except Exception as e:
        print(f"Error scanning OBJ {path}: {e}")
    return list(textures)


def _parse_mtl_file(mtl_path, obj_dir):
    """Parses a .mtl file for texture map references."""
    textures = set()
    map_keywords = {"map_kd", "map_ks", "map_ka", "map_bump", "bump", "map_d",
                    "map_ns", "disp", "decal", "map_refl", "norm"}
    try:
        with open(mtl_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split(None, 1)
                if len(parts) >= 2 and parts[0].lower() in map_keywords:
                    tex_path = parts[1].strip()
                    # Handle options before texture path (e.g. -bm 1.0 texture.png)
                    while tex_path.startswith("-"):
                        option_parts = tex_path.split(None, 2)
                        if len(option_parts) >= 3:
                            tex_path = option_parts[2]
                        else:
                            tex_path = ""
                            break
                    if tex_path and is_valid_texture_path(tex_path):
                        textures.add(tex_path)
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"Error parsing MTL {mtl_path}: {e}")
    return textures


# --- Model Scanning (unified) ---

def scan_model_files(model_paths, data_root):
    """
    Scans a list of relative model paths for their texture dependencies.
    Supports MD3, IQM, OBJ.
    Also looks for .skin files in the same directory as MD3/IQM/MDL models.
    model_paths: list of strings (e.g. ['models/foo.md3', ...])
    data_root: absolute path to data directory
    Returns: { "/full/path/to/model": ["textures/bar.png", ...] }
    """
    results = {}

    extractors = {
        ".md3": extract_from_md3,
        ".iqm": extract_from_iqm,
    }

    for rel_path in model_paths:
        ext = os.path.splitext(rel_path)[1].lower()
        full_path = os.path.join(data_root, rel_path)

        if not os.path.isfile(full_path):
            continue

        resources = set()

        if ext == ".obj":
            # OBJ: extract mtllib + texture refs (paths relative to OBJ location)
            obj_textures = extract_from_obj(full_path)
            obj_dir = os.path.dirname(full_path)
            for t in obj_textures:
                # Convert to path relative to data_root
                abs_t = os.path.join(obj_dir, t) if not os.path.isabs(t) else t
                rel_t = os.path.relpath(abs_t, data_root).replace("\\", "/")
                resources.add(rel_t)
        elif ext == ".mdl":
            # MDL: auto-import retexture overrides (e.g. beam.mdl_0.png, beam.mdl_1.png)
            model_dir = os.path.dirname(full_path)
            model_filename = os.path.basename(full_path).lower()
            if os.path.isdir(model_dir):
                for f in os.listdir(model_dir):
                    fl = f.lower()
                    if fl.startswith(model_filename + "_") and fl.endswith(".png"):
                        rel = os.path.relpath(os.path.join(model_dir, f), data_root).replace("\\", "/")
                        resources.add(rel)
                    elif fl.endswith(".skin"):
                        skin_full_path = os.path.join(model_dir, f)
                        skin_rel_path = os.path.relpath(skin_full_path, data_root).replace("\\", "/")
                        resources.add(skin_rel_path)
                        resources.update(extract_from_skin(skin_full_path))
        elif ext in extractors:
            textures = extractors[ext](full_path)

            # Bodygroup-baked IQMs (mdl2iqm) store the mesh token itself in the
            # material field (e.g. "b1s3_sci2_face") as a placeholder — the real
            # texture (or common/nodraw) is resolved per-variant by the adjacent
            # .skin files, not by this raw name. Reporting it as a needed texture
            # is a false positive; skip when a .bodyinfo sidecar is present.
            if ext == ".iqm" and os.path.isfile(full_path + ".bodyinfo"):
                textures = set()

            resources.update(textures)

            # Look for adjacent .skin files (MD3/IQM/MDL)
            model_dir = os.path.dirname(full_path)
            if os.path.isdir(model_dir):
                for f in os.listdir(model_dir):
                    if f.lower().endswith(".skin"):
                        skin_full_path = os.path.join(model_dir, f)
                        skin_rel_path = os.path.relpath(skin_full_path, data_root).replace("\\", "/")
                        resources.add(skin_rel_path)
                        skin_textures = extract_from_skin(skin_full_path)
                        resources.update(skin_textures)

            # IQM: auto-import adjacent runtime sidecars. These are loaded by QC
            # via fopen (.framegroups/.events -> util_framegroups.qc,
            # .bodyinfo -> util_body.qc) and are NOT referenced by name anywhere
            # in the QC/BSP source, so the scanner is the only thing that can
            # discover them for the build. Missing them at runtime silently
            # breaks animation events and the bodygroup/skin-family system.
            if ext == ".iqm":
                for sidecar_ext in (".framegroups", ".events", ".bodyinfo"):
                    sc_path = full_path + sidecar_ext
                    if os.path.isfile(sc_path):
                        resources.add(os.path.relpath(sc_path, data_root).replace("\\", "/"))
                        # .events references .wav sounds that appear nowhere else
                        # in QC — harvest them so the build tracks/verifies them.
                        if sidecar_ext == ".events":
                            resources.update(extract_from_events(sc_path))

        if resources:
            results[full_path] = list(resources)

    return results


# --- Shader Scanning Logic ---

def parse_shader_content(content):
    """
    Parses Q3 shader text. Returns dict { "shadername": ["dep.png", ...] }
    This is a simplistic parser that tracks braces.
    """
    definitions = {}
    
    # Pre-process: remove C-style comments //
    lines = []
    for line in content.split('\n'):
        line = re.sub(r'//.*', '', line).strip()
        if line:
            lines.append(line)
            
    full_text = " ".join(lines)
    
    # We need to tokenize somewhat intelligently to handle { }
    # A simple state machine is safer than regex for nested structures, 
    # though Q3 shaders generally aren't deeply nested except for stages.
    
    tokens = re.findall(r'({|}|[^{}\s]+)', full_text)
    
    current_shader = None
    brace_depth = 0
    
    # Keywords that introduce a texture file
    # qer_editorimage, map, clampmap, animMap, videoMap
    texture_keywords = {"map", "clampmap", "framemap", "animmap", "videomap", "qer_editorimage"}
    
    i = 0
    while i < len(tokens):
        t = tokens[i]
        
        if t == "{":
            brace_depth += 1
            # If depth 1, the previous token was the shader name
            if brace_depth == 1:
                # Look back for shader name
                if i > 0 and tokens[i-1] != "}":
                    current_shader = tokens[i-1].lower()
                    definitions[current_shader] = set()
        elif t == "}":
            brace_depth -= 1
            if brace_depth == 0:
                current_shader = None
        else:
            # We are inside a definition
            if current_shader and brace_depth > 0:
                # specific handling for animMap which has a frequency param
                keyword = t.lower()
                
                if keyword in texture_keywords:
                    # Next token(s) are textures
                    # map <texture>
                    # animMap <freq> <texture1> ...
                    
                    if i + 1 < len(tokens):
                        if keyword == "animmap":
                            # Skip frequency param
                            j = i + 2
                            # animMap <freq> <texture1> ... <textureN>
                            # We collect all following tokens that look like texture paths
                            while j < len(tokens):
                                candidate = tokens[j]
                                # Stop if we hit a brace or a known keyword (simplistic check)
                                if candidate in {"{", "}"} or candidate.lower() in texture_keywords:
                                    break
                                
                                # Clean it
                                clean_tex = re.sub(r'\.(tga|jpg|jpeg|png|bmp)$', '', candidate, flags=re.IGNORECASE)
                                
                                # A token with a '.' is only a texture if it has an image extension.
                                # Otherwise it must start with textures/
                                is_texture = False
                                if candidate.lower().endswith(('.tga', '.jpg', '.png', '.jpeg')):
                                    is_texture = True
                                elif candidate.lower().startswith("textures/"):
                                    is_texture = True
                                
                                if (is_texture and 
                                    not candidate.startswith("{") and not candidate.startswith("}") and
                                    is_valid_texture_path(clean_tex)):
                                    definitions[current_shader].add(clean_tex + ".png")
                                j += 1
                            # Move i forward to where j ended (minus 1 because the loop increment will add it)
                            i = j - 1
                        else:
                            # Single texture
                            tex = tokens[i+1]
                            # Clean it
                            clean_tex = re.sub(r'\.(tga|jpg|jpeg|png|bmp)$', '', tex, flags=re.IGNORECASE)
                            if not should_ignore(clean_tex) and is_valid_texture_path(clean_tex):
                                definitions[current_shader].add(clean_tex + ".png")
        
        # Fallback: Just look for any token looking like a texture path inside a shader block
        if current_shader and brace_depth > 0:
            if not t.startswith("{") and not t.startswith("}"):
                 # Check for extensions OR if it starts with textures/
                 # This avoids picking up numerical values like 0.25
                 is_texture = False
                 if t.lower().endswith(('.tga', '.jpg', '.png', '.jpeg')):
                    is_texture = True
                 elif t.lower().startswith("textures/"):
                    is_texture = True
                    
                 if is_texture:
                    clean = re.sub(r'\.(tga|jpg|jpeg|png|bmp)$', '', t, flags=re.IGNORECASE)
                    if not should_ignore(clean) and is_valid_texture_path(clean):
                        definitions[current_shader].add(clean + ".png")

        i += 1
        
    return {k: list(v) for k, v in definitions.items()}

def load_all_shaders(data_dir):
    """
    Scans scripts/ directory for .shader files.
    Returns global map: { "shadername": ["dep.png"] }
    """
    scripts_dir = os.path.join(data_dir, "scripts")
    shader_map = {}
    
    if not os.path.exists(scripts_dir):
        return shader_map

    for root, _, files in os.walk(scripts_dir):
        for file in files:
            if file.lower().endswith(".shader"):
                try:
                    with open(os.path.join(root, file), 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        defs = parse_shader_content(content)
                        for k, v in defs.items():
                            if k not in shader_map:
                                shader_map[k] = []
                            shader_map[k].extend(v)
                except Exception as e:
                    print(f"Error parsing shader {file}: {e}")
                    
    return shader_map

# --- Archive (PK3) Indexing ---

def index_pk3_archives(data_root):
    """
    Index the contents of every .pk3 archive under data_root.

    .pk3 is a plain zip (id Tech 3 convention); the engine mounts these at
    runtime, so an asset can legitimately be "present" without existing as a
    loose file on disk. Returns a lookup so the resource-tree UI can distinguish
    "packed in an archive" from genuinely "missing".

    Returns: dict { "maps/c1a0.bsp": "halflife_maps.pk3", ... }
             keys are lower-cased, forward-slash relative paths (resource paths
             are already stored lower/-slash elsewhere in the scanner); the
             value is the archive's basename for display.
    """
    index = {}
    if not data_root or not os.path.isdir(data_root):
        return index

    for root, _, files in os.walk(data_root):
        for file in files:
            if not file.lower().endswith(".pk3"):
                continue
            pk3_path = os.path.join(root, file)
            try:
                with zipfile.ZipFile(pk3_path, "r") as zf:
                    for name in zf.namelist():
                        if name.endswith("/"):
                            continue  # directory entry, not a file
                        key = name.replace("\\", "/").lower()
                        # First archive wins (mirrors typical mount order well
                        # enough for a "does it exist anywhere" check).
                        index.setdefault(key, file)
            except Exception as e:
                print(f"Error reading PK3 {pk3_path}: {e}")

    return index

# --- Main Scanner Entry Point ---

def scan_all(qc_dir=QC_DIR, bsp_dir=BSP_DIR, scripts_dir=None, extra_model_globs=None):
    """
    Runs all scanning logic.
    Returns a unified dictionary: { "SourceFile": ["Resource1", "Resource2"] }

    extra_model_globs: list of glob patterns (relative to the data root) whose
    on-disk matches are force-included as if referenced. Use for assets the QC
    builds dynamically at runtime and the scanner therefore cannot follow --
    e.g. func_breakable gib sets ("models/*gibs*.iqm"). Matched model files also
    flow through the model dependency scan below, so their textures/skins get
    bundled too.
    """
    all_results = {}
    
    
    # If scripts_dir not provided, try to derive from bsp_dir (data/maps -> data/scripts)
    data_dir = os.path.dirname(bsp_dir)
    if not scripts_dir:
        scripts_dir = os.path.join(data_dir, "scripts")
        
    print("Loading Shaders...")
    shader_map = load_all_shaders(data_dir) # Pass data root, function assumes /scripts inside
    
    print("Scanning QC files...")
    qc_results = scan_qc_files(qc_dir)
    all_results.update(qc_results)
    
    print("Scanning BSP files...")
    bsp_results = scan_bsp_files(bsp_dir)
    
    # Resolve Shaders in BSP results
    # For every resource found in BSP, check if it's a shader.
    # If so, add its dependencies.
    # Note: We should probably keep the shader name itself? 
    # Actually, the user wants "needed resources". 
    # If a shader is used, the shader FILE is needed (handled by builder copying 'scripts'),
    # and the IMAGES are needed.
    
    for bsp_path, resources in bsp_results.items():
        expanded_resources = set()
        for r in resources:
            r_lower = r.lower()
            # Try exact match or without extension
            # BSP often refers to "textures/foo" which matches "textures/foo" in shader
            
            # Check if r is in shader_map
            # Remove .png if we added it speculatively in scan_bsp
            r_clean = r
            if r.endswith(".png"): 
                r_clean = r[:-4]
                
            if r_clean in shader_map:
                # It is a shader!
                # Add its dependencies
                deps = shader_map[r_clean]
                for d in deps:
                    expanded_resources.add(d)
                # Should we keep the original 'r'? 
                # If it's just a shader name, it's not a file. 
                # But if it wasn't a shader, we assumed it was a file (r).
                # If it IS a shader, we don't need 'r' if 'r' is just an abstract name.
                pass
            else:
                # Not a shader, keep as is (it's a direct texture reference)
                expanded_resources.add(r)
                
        # Update results
        all_results[bsp_path] = list(expanded_resources)
    
    # --- Force-included assets from extra_model_globs ---
    # Resources the QC builds dynamically (e.g. func_breakable gibs) can't be
    # discovered by static scanning. Resolve the configured globs against disk
    # and inject the matches as a synthetic source so they are (a) bundled and
    # (b) picked up by the model dependency scan below (textures/skins).
    if extra_model_globs:
        forced = set()
        for pattern in extra_model_globs:
            search = os.path.join(data_dir, pattern.replace("\\", "/"))
            for match in _glob.glob(search, recursive=True):
                if os.path.isfile(match):
                    rel = os.path.relpath(match, data_dir).replace("\\", "/")
                    forced.add(rel)
        if forced:
            all_results["<extra_model_globs>"] = sorted(forced)
            print(f"Force-included {len(forced)} file(s) from extra_model_globs")

    # --- Recursive Model Scanning ---
    model_extensions = {".md3", ".iqm", ".obj", ".mdl"}
    print("Scanning discovered model files...")
    found_models = set()
    for resources in all_results.values():
        for r in resources:
            ext = os.path.splitext(r)[1].lower()
            if ext in model_extensions:
                found_models.add(r)

    model_results = scan_model_files(found_models, data_dir)
    all_results.update(model_results)

    # --- Resolve image extensions against disk ---
    # For any image resource, if the recorded extension doesn't exist on disk,
    # substitute the first matching alternative (.png -> .tga -> .jpg -> etc.)
    print("Resolving image extensions...")
    resolved_results = {}
    for src, resources in all_results.items():
        resolved = [resolve_image_extension(r, data_dir) for r in resources]
        resolved_results[src] = resolved
    all_results = resolved_results

    return all_results

if __name__ == "__main__":
    # Test run
    results = scan_all()
    for src, res in results.items():
        print(f"\nSource: {os.path.basename(src)}")
        for r in res[:5]: # Show first 5
            print(f"  - {r}")
        if len(res) > 5:
            print(f"  ... and {len(res)-5} more")
