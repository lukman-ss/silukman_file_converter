import subprocess
import sys
from collections.abc import Mapping, Sequence


def run_hidden_process(
    args: Sequence[str],
    cwd: str | None = None,
    timeout: int | float | None = None,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    startupinfo = None
    creationflags = 0

    if sys.platform.startswith("win"):
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        creationflags = subprocess.CREATE_NO_WINDOW

    return subprocess.run(
        args,
        cwd=cwd,
        timeout=timeout,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=False,
        startupinfo=startupinfo,
        creationflags=creationflags,
        check=False,
        env=env,
    )
