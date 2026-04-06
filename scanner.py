import os
import re
import struct

# Configuration Defaults (can be overridden)
QC_DIR = "../qc"
BSP_DIR = "../data/maps"

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

def extract_from_qc_content(content):
    """Extracts .wav, .md3, .iqm, .obj, .mdl, .spr32 references from QC text content."""
    resources = set()

    # Strip // line comments before scanning so commented-out references are ignored.
    # QC resource paths never contain "://" so this is safe.
    stripped_lines = []
    for line in content.split('\n'):
        idx = line.find('//')
        stripped_lines.append(line[:idx] if idx >= 0 else line)
    content = '\n'.join(stripped_lines)

    # Simple regex for quoted strings looking like resources
    # This matches "sound/path/file.wav" or "models/path/file.md3"
    patterns = [
        r'"([a-zA-Z0-9_\-\/]+\.wav)"',
        r'"([a-zA-Z0-9_\-\/]+\.md3)"',
        r'"([a-zA-Z0-9_\-\/]+\.iqm)"',
        r'"([a-zA-Z0-9_\-\/]+\.obj)"',
        r'"([a-zA-Z0-9_\-\/]+\.mdl)"',
        r'"([a-zA-Z0-9_\-\/]+\.spr)"',
        r'"([a-zA-Z0-9_\-\/]+\.spr32)"'
    ]
    for p in patterns:
        matches = re.findall(p, content)
        for m in matches:
            # Fix sound paths: logic often omits "sound/" prefix for precache_sound etc.
            if m.endswith(".wav") and not m.startswith("sound/"):
                m = "sound/" + m
            resources.add(m)
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
    """Extracts texture references from an MD3 file."""
    textures = set()
    try:
        with open(path, "rb") as f:
            data = f.read()
            # Look for strings starting with textures/
            # MD3 usually stores them as null-padded strings, but regex works fine on binary
            matches = re.findall(rb'textures\/[^\x00\s]{1,100}', data)
            for m in matches:
                try:
                    # Clean up and normalize
                    s = m.decode('utf-8', errors='ignore')
                    # Strip existing extensions if any (MD3s often have them, or not)
                    s = re.sub(r'\.(tga|jpg|jpeg|png|bmp)$', '', s, flags=re.IGNORECASE)
                    
                    if not should_ignore(s) and is_valid_texture_path(s):
                         # Assume .png as per other tools
                        textures.add(s + ".png")
                except Exception:
                    pass
    except Exception as e:
        print(f"Error scanning MD3 {path}: {e}")
    return list(textures)

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
                    textures.add(mtl_name)
                    # Parse the .mtl file for texture maps
                    mtl_textures = _parse_mtl_file(mtl_path, obj_dir)
                    textures.update(mtl_textures)
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
        elif ext in extractors:
            textures = extractors[ext](full_path)
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

# --- Main Scanner Entry Point ---

def scan_all(qc_dir=QC_DIR, bsp_dir=BSP_DIR, scripts_dir=None):
    """
    Runs all scanning logic.
    Returns a unified dictionary: { "SourceFile": ["Resource1", "Resource2"] }
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
