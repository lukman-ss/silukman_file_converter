from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
FIXED_ZIP_TIME = (2026, 1, 1, 0, 0, 0)
PACKAGE_NAME = "silukman_file_converter"

EXCLUDED_DIRS = {
    ".git",
    ".kiro",
    ".pytest_cache",
    ".venv_ocr",
    "__pycache__",
    "build",
    "dist",
    "output",
    "venv",
}
PACKAGE_FORBIDDEN_DIRS = {
    ".git",
    ".kiro",
    ".pytest_cache",
    ".venv_ocr",
    "__pycache__",
    "build",
    "output",
    "venv",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".log"}
TRACKED_SAMPLE_PATHS: set[str] | None = None

ROOT_FILES = [
    "CHANGELOG.md",
    "LICENSE",
    "README.md",
    "README_CLEAN_WINDOWS_QA.md",
    "RELEASE_MANIFEST.json",
    "VERSION",
    "build.ps1",
    "build_beta_package.ps1",
    "build_installer.ps1",
    "build_optimized.ps1",
    "build_release_package.ps1",
    "run_production_qa.ps1",
    "validate_release_package.ps1",
    "requirements.txt",
    "silukman_file_converter.spec",
    "silukman_file_converter_optimized.spec",
]

ROOT_DIRS = ["app", "docs", "installer", "qa", "release", "samples", "scripts", "summary", "tests", "tools"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a clean deterministic release package.")
    parser.add_argument("--channel", choices=["internal-beta", "production"], default="production")
    parser.add_argument("--version", default=read_text(ROOT / "VERSION").strip())
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args(argv)

    errors = validate_source_tree(args.channel, args.version)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    if args.validate_only:
        print("Package validation passed.")
        return 0

    stage_root = DIST / "release_stage" / f"{PACKAGE_NAME}-{args.version}-{args.channel}"
    if stage_root.exists():
        shutil.rmtree(stage_root)
    stage_root.mkdir(parents=True)

    copy_release_tree(stage_root)
    copy_exe(stage_root)
    copy_latest_summary(stage_root)
    manifest = build_manifest(stage_root, args.channel, args.version)
    (stage_root / "RELEASE_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    validate_staged_package(stage_root)

    zip_path = DIST / f"{PACKAGE_NAME}_{args.version}_{args.channel}.zip"
    if zip_path.exists():
        zip_path.unlink()
    write_deterministic_zip(stage_root, zip_path)

    print(f"Release package created: {zip_path}")
    print(f"Staging directory: {stage_root}")
    return 0


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def validate_source_tree(channel: str, version: str) -> list[str]:
    errors: list[str] = []
    required = [ROOT / name for name in ROOT_FILES] + [ROOT / name for name in ROOT_DIRS]
    required.append(DIST / "silukman_file_converter.exe")
    required.append(ROOT / "release" / f"{channel}.json")
    for path in required:
        if not path.exists():
            errors.append(f"Required path is missing: {path.relative_to(ROOT)}")

    if not version:
        errors.append("VERSION is empty.")
    if channel == "production" and ("internal-beta" in version or "-beta" in version):
        errors.append("Production channel cannot use an internal beta version string.")

    spec = read_text(ROOT / "silukman_file_converter.spec")
    if "console=False" not in spec:
        errors.append("PyInstaller spec must keep console=False.")

    return errors


def copy_release_tree(stage_root: Path) -> None:
    for file_name in ROOT_FILES:
        copy_file(ROOT / file_name, stage_root / file_name)

    for dir_name in ROOT_DIRS:
        copy_dir(ROOT / dir_name, stage_root / dir_name)


def copy_exe(stage_root: Path) -> None:
    dist_dir = stage_root / "dist"
    dist_dir.mkdir(exist_ok=True)
    optimized = DIST / "silukman_file_converter_optimized.exe"
    source = optimized if optimized.exists() else DIST / "silukman_file_converter.exe"
    copy_file(source, dist_dir / "silukman_file_converter.exe")


def copy_latest_summary(stage_root: Path) -> None:
    summary_dir = stage_root / "summary"
    summary_dir.mkdir(exist_ok=True)
    latest = latest_summary_exe()
    if latest is None:
        return

    copy_file(latest, summary_dir / "summary_exe.json")
    for name in ["summary.md", "file.md"]:
        candidate = latest.parent / name
        if candidate.exists():
            copy_file(candidate, summary_dir / name)


def latest_summary_exe() -> Path | None:
    root = ROOT / "output" / "sample_file_matrix"
    if not root.exists():
        return None
    files = sorted(root.rglob("summary_exe.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    return files[0] if files else None


def copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def copy_dir(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    for path in sorted(source.rglob("*")):
        if should_skip(path):
            continue
        relative = path.relative_to(source)
        target = destination / relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            copy_file(path, target)


def should_skip(path: Path) -> bool:
    try:
        relative = normalize_path(path.relative_to(ROOT))
        if is_untracked_local_sample(relative):
            return True
    except ValueError:
        pass
    parts = set(path.parts)
    if parts & EXCLUDED_DIRS:
        return True
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return True
    return False


def is_untracked_local_sample(relative: str) -> bool:
    if not relative.startswith("samples/"):
        return False
    git_dir = ROOT / ".git"
    if not git_dir.exists():
        return False
    return relative not in tracked_sample_paths()


def tracked_sample_paths() -> set[str]:
    global TRACKED_SAMPLE_PATHS
    if TRACKED_SAMPLE_PATHS is not None:
        return TRACKED_SAMPLE_PATHS
    result = subprocess.run(
        ["git", "ls-files", "samples"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    TRACKED_SAMPLE_PATHS = set(result.stdout.splitlines()) if result.returncode == 0 else set()
    return TRACKED_SAMPLE_PATHS


def build_manifest(stage_root: Path, channel: str, version: str) -> dict:
    base = json.loads(read_text(ROOT / "RELEASE_MANIFEST.json"))
    summary_path = stage_root / "summary" / "summary_exe.json"
    summary_raw = read_summary_raw(summary_path)
    summary = summarize_latest_test(summary_raw)
    exe_path = stage_root / "dist" / "silukman_file_converter.exe"
    files = [
        {
            "path": normalize_path(path.relative_to(stage_root)),
            "size": path.stat().st_size,
            "sha256": sha256(path),
        }
        for path in sorted(stage_root.rglob("*"))
        if path.is_file() and path.name != "RELEASE_MANIFEST.json"
    ]

    base.update(
        {
            "version": version,
            "channel": channel,
            "generated_at_utc": deterministic_generated_at(summary_raw),
            "entrypoint_sha256": sha256(exe_path),
            "latest_test_summary": summary,
            "files": files,
        }
    )
    if channel == "production":
        base["status"] = "READY_FOR_PRODUCTION"
        base["final_production_readiness"] = "READY_FOR_PRODUCTION"
    return base


def read_summary_raw(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def summarize_latest_test(data: dict | None) -> dict | None:
    if not data:
        return None
    return {
        "is_frozen": data.get("is_frozen"),
        "exe_verification": data.get("exe_verification"),
        "exe_ocr_verification": data.get("exe_ocr_verification"),
        "production_readiness": data.get("production_readiness"),
        "final_production_readiness": data.get("final_production_readiness"),
        "summary": data.get("summary"),
        "run_dir": data.get("run_dir"),
    }


def deterministic_generated_at(summary_data: dict | None) -> str:
    source_date_epoch = os_environ("SOURCE_DATE_EPOCH")
    if source_date_epoch and source_date_epoch.isdigit():
        return datetime.fromtimestamp(int(source_date_epoch), timezone.utc).replace(microsecond=0).isoformat()

    try:
        run_dir = str((summary_data or {}).get("run_dir") or "")
        run_id = Path(run_dir).name
        parsed = datetime.strptime(run_id, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        return parsed.isoformat()
    except Exception:
        return "1970-01-01T00:00:00+00:00"


def os_environ(name: str) -> str | None:
    import os

    return os.environ.get(name)


def validate_staged_package(stage_root: Path) -> None:
    required = [
        "VERSION",
        "LICENSE",
        "CHANGELOG.md",
        "README.md",
        "RELEASE_MANIFEST.json",
        "dist/silukman_file_converter.exe",
        "installer/silukman_file_converter.iss",
        "summary/summary_exe.json",
        "summary/file.md",
    ]
    missing = [item for item in required if not (stage_root / item).exists()]
    if missing:
        raise RuntimeError(f"Staged package is missing required files: {', '.join(missing)}")

    forbidden = [path for path in stage_root.rglob("*") if should_skip_package_file(path)]
    if forbidden:
        preview = ", ".join(normalize_path(path.relative_to(stage_root)) for path in forbidden[:10])
        raise RuntimeError(f"Staged package contains forbidden files: {preview}")


def write_deterministic_zip(stage_root: Path, zip_path: Path) -> None:
    files = sorted(path for path in stage_root.rglob("*") if path.is_file())
    top = stage_root.name
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for file_path in files:
            relative = Path(top) / file_path.relative_to(stage_root)
            info = zipfile.ZipInfo(normalize_path(relative), FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, file_path.read_bytes())


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def should_skip_package_file(path: Path) -> bool:
    parts = set(path.parts)
    if parts & PACKAGE_FORBIDDEN_DIRS:
        return True
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return True
    return False


def normalize_path(path: Path) -> str:
    return path.as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
