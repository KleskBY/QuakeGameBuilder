import sys
import os

# Add current directory to path so we can import scanner
sys.path.append(os.getcwd())

import scanner

def test_is_valid_texture_path():
    print("Testing is_valid_texture_path...")
    paths = [
        "textures/button/+0terminal",
        "textures/liquids/water1_*",
        "textures/sfx/fan#1",
        "textures/base/concrete",
        "textures/common/caulk"
    ]
    for p in paths:
        valid = scanner.is_valid_texture_path(p)
        print(f"  {p}: {valid}")
        if not valid and "+" in p:
            print("  FAIL: + should be valid")

def test_parse_shader_content():
    print("\nTesting parse_shader_content...")
    shader_text = """
textures/button/terminal_shader
{
    qer_editorimage textures/button/terminal_editor.tga
    {
        map textures/button/+0terminal.png
        blendFunc GL_ONE GL_ZERO
    }
    {
        animMap 2 textures/button/anim1 textures/button/anim2 textures/button/anim3
        blendFunc GL_SRC_ALPHA GL_ONE_MINUS_SRC_ALPHA
        tcMod scale 0.25 0.5
    }
}
"""
    results = scanner.parse_shader_content(shader_text)
    print(f"Results: {results}")
    
    found_textures = set(results.get("textures/button/terminal_shader", []))
    expected = {
        "textures/button/terminal_editor.png",
        "textures/button/+0terminal.png",
        "textures/button/anim1.png",
        "textures/button/anim2.png",
        "textures/button/anim3.png"
    }
    
    unexpected = {"0.25.png", "0.5.png"}
    found_unexpected = found_textures.intersection(unexpected)
    
    if found_unexpected:
        print(f"  FAIL: Found unexpected textures: {found_unexpected}")
    
    missing = expected - found_textures
    if missing:
        print(f"  FAIL: Missing textures: {missing}")
    
    if not missing and not found_unexpected:
        print("  PASS: Correct textures found, false positives avoided")

if __name__ == "__main__":
    test_is_valid_texture_path()
    test_parse_shader_content()
