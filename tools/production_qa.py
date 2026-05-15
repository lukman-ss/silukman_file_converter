from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = ROOT_DIR / "scripts" / "production_qa.py"


def main() -> int:
    spec = importlib.util.spec_from_file_location("silukman_production_qa", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load production QA script: {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return int(module.main(sys.argv[1:]))


if __name__ == "__main__":
    raise SystemExit(main())
