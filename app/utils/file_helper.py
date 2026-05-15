from pathlib import Path


def ensure_output_dir(path: str) -> Path:
    output_dir = Path(path)
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def unique_paths(paths: list[str]) -> list[str]:
    seen = set()
    result = []
    for path in paths:
        normalized = str(Path(path).resolve())
        if normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result
