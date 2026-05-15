from __future__ import annotations

import argparse
import shutil
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_PACKAGE = ROOT_DIR / "clean_windows_validation_package"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a no-Python clean Windows validation package.")
    parser.add_argument("--output", default=str(DEFAULT_PACKAGE))
    args = parser.parse_args(argv)

    package = Path(args.output).resolve()
    build_package(package)
    print(f"Clean Windows validation package created: {package}")
    return 0


def build_package(package: Path) -> None:
    if package.exists():
        shutil.rmtree(package)
    (package / "dist").mkdir(parents=True)
    (package / "qa").mkdir(parents=True)

    primary_exe = ROOT_DIR / "dist" / "silukman_file_converter_optimized.exe"
    if not primary_exe.exists():
        primary_exe = ROOT_DIR / "dist" / "silukman_file_converter.exe"

    required = [
        primary_exe,
        ROOT_DIR / "qa" / "clean_windows_runner.ps1",
        ROOT_DIR / "README_CLEAN_WINDOWS_QA.md",
        ROOT_DIR / "samples",
    ]
    missing = [path for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing required package inputs: " + ", ".join(str(path) for path in missing))

    shutil.copy2(primary_exe, package / "dist" / "silukman_file_converter.exe")
    optimized = ROOT_DIR / "dist" / "silukman_file_converter_optimized.exe"
    if optimized.exists():
        shutil.copy2(optimized, package / "dist" / "silukman_file_converter_optimized.exe")
    shutil.copy2(ROOT_DIR / "qa" / "clean_windows_runner.ps1", package / "qa" / "clean_windows_runner.ps1")
    shutil.copy2(ROOT_DIR / "README_CLEAN_WINDOWS_QA.md", package / "README_CLEAN_WINDOWS_QA.md")
    copy_samples(ROOT_DIR / "samples", package / "samples")

    forbidden = find_forbidden(package)
    if forbidden:
        raise RuntimeError("Forbidden files/folders in clean package: " + ", ".join(str(path) for path in forbidden[:10]))


def copy_samples(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True)
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        target = destination / relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def find_forbidden(package: Path) -> list[Path]:
    forbidden_names = {
        ".git",
        ".pytest_cache",
        ".venv",
        ".venv_ocr",
        "__pycache__",
        "app",
        "build",
        "scripts",
        "tests",
        "tools",
        "venv",
    }
    forbidden_suffixes = {".py", ".pyc", ".pyo"}
    found: list[Path] = []
    for path in package.rglob("*"):
        if any(part in forbidden_names for part in path.parts):
            found.append(path)
        elif path.suffix.lower() in forbidden_suffixes:
            found.append(path)
    return found


if __name__ == "__main__":
    raise SystemExit(main())
