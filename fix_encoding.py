"""Fix encoding issues in scenario YAML files."""
from pathlib import Path

specs_dir = Path("data/scenario_specs")

# Fix BOM in DRE files
for name in sorted(specs_dir.glob("SC-*.yaml")):
    content = name.read_bytes()
    if content[:3] == b'\xef\xbb\xbf':
        print(f"{name.name}: BOM detected, removing")
        name.write_bytes(content[3:])

# Check for non-UTF-8 bytes in all files
for name in sorted(specs_dir.glob("SC-*.yaml")):
    content = name.read_bytes()
    for i, b in enumerate(content):
        if b > 127:
            # Try to decode as UTF-8 from this position
            try:
                content[i:i+4].decode('utf-8')
            except Exception:
                print(f"{name.name}: problematic byte at pos {i}: {hex(b)}")

# Try reading MPI-003 with utf-8
try:
    p = specs_dir / "SC-MPI-003.yaml"
    text = p.read_text(encoding='utf-8')
    print(f"SC-MPI-003.yaml: reads OK with utf-8, length={len(text)}")
except Exception as e:
    print(f"SC-MPI-003.yaml: utf-8 read error: {e}")
    # Read with utf-8 and replace bad chars
    content = p.read_bytes()
    text = content.decode('utf-8', errors='replace')
    # Find the star emoji or other chars
    for i, ch in enumerate(text[690:720]):
        if ord(ch) > 127:
            print(f"  char at {690+i}: U+{ord(ch):04X} = {ch}")
