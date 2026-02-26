#!/usr/bin/env python3
"""
Qt6 launcher that always runs via project venv Python.

Because this project had legacy dependencies in venv/lib/python3.13/site-packages
and current interpreter is Python 3.14, we append paths in a safe order:
1) system site-packages (PyQt6, lxml, etc.)
2) legacy project site-packages (flask, requests, DrissionPage, etc.)
"""

from __future__ import annotations

import sys
import os
from pathlib import Path


def extend_sys_path(project_dir: Path) -> None:
    system_site = Path("/usr/lib/python3.14/site-packages")
    legacy_site = project_dir / "venv" / "lib" / "python3.13" / "site-packages"

    for path in (system_site, legacy_site):
        if path.exists():
            path_str = str(path)
            if path_str not in sys.path:
                sys.path.append(path_str)


def main() -> None:
    project_dir = Path(__file__).resolve().parent
    # 固定工作目录，避免从其他目录启动时出现相对路径问题
    os.chdir(project_dir)
    project_dir_str = str(project_dir)
    if project_dir_str not in sys.path:
        sys.path.insert(0, project_dir_str)

    extend_sys_path(project_dir)

    if "--self-check" in sys.argv:
        import PyQt6  # noqa: F401
        import DrissionPage  # noqa: F401
        import flask  # noqa: F401
        import requests  # noqa: F401

        print("self-check ok")
        return

    from main_gui import main as qt_main

    qt_main()


if __name__ == "__main__":
    main()
