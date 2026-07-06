from __future__ import annotations

import sys

from cdm_desktop.app import create_qapplication
from cdm_desktop.logging_config import configure_logging
from cdm_desktop.paths import get_app_paths
from cdm_desktop.ui.main_window import MainWindow


def main() -> int:
    paths = get_app_paths()
    configure_logging(paths)

    app = create_qapplication(sys.argv)
    window = MainWindow(paths)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
