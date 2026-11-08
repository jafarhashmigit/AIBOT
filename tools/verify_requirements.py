"""Check the requirement files against the running interpreter without installing anything.

1. Every pinned requirement must be installed at exactly the pinned version.
2. Every third-party module imported by a project script must be covered by a
   requirement file (core, research or legacy).

Usage:  python tools/verify_requirements.py [--json]
Exit code 0 when both checks pass for the files whose packages are installed.
"""

import ast
import json
import re
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIREMENT_FILES = ("requirements.txt", "requirements-research.txt", "requirements-legacy.txt")
SCAN_DIRS = (ROOT / "src", ROOT / "tools", ROOT / "tests")
SCAN_ROOT_FILES = tuple(ROOT.glob("*.py"))

# Import name -> distribution name, where they differ.
IMPORT_TO_DIST = {
    "sklearn": "scikit-learn",
    "MetaTrader5": "metatrader5",
    "huggingface_hub": "huggingface-hub",
    "yaml": "PyYAML",
    "dateutil": "python-dateutil",
}
# Modules that are not pip packages: project modules and the Kronos git checkout.
NON_PIP_MODULES = {"src", "evaluation", "model"}

PIN = re.compile(r"^([A-Za-z0-9_.\-]+)==([^\s;#]+)")


def norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_requirements(path: Path) -> dict:
    pins = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-r"):
            continue
        match = PIN.match(line)
        if not match:
            raise ValueError(f"{path.name}: unpinned or unsupported line: {line!r}")
        pins[norm(match.group(1))] = match.group(2)
    return pins


def project_modules() -> set:
    names = set()
    for folder in SCAN_DIRS:
        if folder.exists():
            names |= {p.stem for p in folder.rglob("*.py")}
            names |= {p.name for p in folder.rglob("*") if p.is_dir()}
    names |= {p.stem for p in SCAN_ROOT_FILES}
    return names


def third_party_imports() -> dict:
    stdlib = set(sys.stdlib_module_names)
    local = project_modules() | NON_PIP_MODULES
    found = {}
    files = list(SCAN_ROOT_FILES)
    for folder in SCAN_DIRS:
        if folder.exists():
            files += [p for p in folder.rglob("*.py") if "__pycache__" not in p.parts]
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                mods = [node.module.split(".")[0]]
            else:
                continue
            for mod in mods:
                if mod in stdlib or mod in local:
                    continue
                found.setdefault(mod, set()).add(str(path.relative_to(ROOT)).replace("\\", "/"))
    return {k: sorted(v) for k, v in sorted(found.items())}


def main() -> int:
    result = {"interpreter": sys.executable, "python": sys.version.split()[0], "files": {}, "imports": {}}
    all_pins = {}
    ok = True
    for name in REQUIREMENT_FILES:
        pins = parse_requirements(ROOT / name)
        rows = {}
        for dist, pinned in pins.items():
            try:
                installed = metadata.version(dist)
            except metadata.PackageNotFoundError:
                installed = None
            rows[dist] = {"pinned": pinned, "installed": installed,
                          "status": "MATCH" if installed == pinned else ("NOT_INSTALLED" if installed is None else "MISMATCH")}
        installed_any = any(r["installed"] for r in rows.values())
        file_ok = all(r["status"] == "MATCH" for r in rows.values())
        result["files"][name] = {"packages": rows, "fully_installed": file_ok, "applies_to_interpreter": installed_any}
        if any(r["status"] == "MISMATCH" for r in rows.values()):
            ok = False
        if name == "requirements.txt" and not file_ok:
            ok = False
        all_pins.update(pins)

    for mod, users in third_party_imports().items():
        dist = norm(IMPORT_TO_DIST.get(mod, mod))
        covered = dist in all_pins
        result["imports"][mod] = {"distribution": dist, "covered_by_requirements": covered, "used_in": users}
        ok &= covered
    result["passed"] = ok

    if "--json" in sys.argv:
        print(json.dumps(result, indent=2))
    else:
        print(f"Interpreter: {result['interpreter']} (Python {result['python']})")
        for name, info in result["files"].items():
            print(f"\n{name}  fully installed here: {info['fully_installed']}")
            for dist, r in info["packages"].items():
                print(f"  {dist:18s} pinned {r['pinned']:14s} installed {str(r['installed']):14s} {r['status']}")
        print("\nThird-party imports in project scripts:")
        for mod, r in result["imports"].items():
            print(f"  {mod:16s} -> {r['distribution']:16s} covered={r['covered_by_requirements']}  ({len(r['used_in'])} files)")
        print(f"\nPASSED: {ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
