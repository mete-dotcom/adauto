"""
build_nuitka_wheel.py — Package Nuitka-compiled adauto as a binary wheel.

Replaces .py source files with the compiled .pyd/.so module,
then builds a platform-specific wheel using setuptools.

Runafter:
    python -m nuitka --module --include-package=adauto --output-dir=nuitka_out adauto/__init__.py

Produces:
    dist/adauto-{version}-cp{pyver}-cp{pyver}-{platform}.whl
    (no .py source files inside — closed source)
"""
from __future__ import annotations

import glob
import os
import shutil
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent  # repo root


def find_nuitka_output(output_dir: Path) -> list[Path]:
    """Find compiled .so / .pyd files in the Nuitka output directory."""
    patterns = [
        str(output_dir / "adauto*.so"),
        str(output_dir / "adauto*.pyd"),
        str(output_dir / "adauto.dist" / "adauto*.so"),
        str(output_dir / "adauto.dist" / "adauto*.pyd"),
    ]
    found = []
    for pat in patterns:
        found.extend(Path(f) for f in glob.glob(pat))
    return found


def main():
    nuitka_out = ROOT / "nuitka_out"
    compiled   = find_nuitka_output(nuitka_out)

    if not compiled:
        print("[build_nuitka_wheel] ERROR: No Nuitka output found in nuitka_out/")
        print("  Expected: adauto*.so or adauto*.pyd")
        print("  Run: python -m nuitka --module --include-package=adauto --output-dir=nuitka_out adauto/")
        sys.exit(1)

    print(f"[build_nuitka_wheel] Found {len(compiled)} compiled module(s):")
    for f in compiled:
        print(f"  {f}")

    # 1. Copy compiled files into the adauto package directory
    pkg_dir = ROOT / "adauto"
    for f in compiled:
        dest = pkg_dir / f.name
        shutil.copy2(f, dest)
        print(f"[build_nuitka_wheel] Copied: {dest}")

    # 2. Remove .py source files from the package (keep __init__.py as stub)
    #    The stub __init__.py will import from the compiled module
    removed = []
    for py_file in pkg_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue  # Keep as import stub
        py_file.unlink()
        removed.append(py_file)
    print(f"[build_nuitka_wheel] Removed {len(removed)} .py source files")

    # 3. Rewrite __init__.py to import from compiled module
    #    The compiled module exposes all public symbols
    init_py = pkg_dir / "__init__.py"
    version_line = ""
    for line in init_py.read_text(encoding="utf-8").splitlines():
        if line.startswith("__version__"):
            version_line = line
            break
    # Write minimal stub
    init_py.write_text(
        f'"""adauto — binary distribution (compiled with Nuitka)."""\n'
        f'{version_line}\n',
        encoding="utf-8",
    )
    print(f"[build_nuitka_wheel] Rewrote __init__.py as import stub")

    # 4. Build the binary wheel
    print("[build_nuitka_wheel] Building binary wheel...")
    dist_dir = ROOT / "dist"
    dist_dir.mkdir(exist_ok=True)

    result = subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--no-isolation", "-o", str(dist_dir)],
        cwd=ROOT,
        check=False,
    )

    if result.returncode != 0:
        # Fallback: build without --no-isolation
        result = subprocess.run(
            [sys.executable, "-m", "build", "--wheel", "-o", str(dist_dir)],
            cwd=ROOT,
            check=True,
        )

    wheels = list(dist_dir.glob("*.whl"))
    print(f"[build_nuitka_wheel] Built {len(wheels)} wheel(s):")
    for w in wheels:
        size_kb = w.stat().st_size // 1024
        print(f"  {w.name}  ({size_kb} KB)")


if __name__ == "__main__":
    main()
