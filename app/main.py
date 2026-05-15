from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow


def main() -> int:
    if "--sample-matrix" in sys.argv:
        from app.core.sample_matrix import cli

        args = [arg for arg in sys.argv[1:] if arg != "--sample-matrix"]
        return cli(args)

    app = QApplication(sys.argv)
    app.setApplicationName("silukman_file_converter")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
