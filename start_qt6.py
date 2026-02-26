#!/usr/bin/env python3
import os
import runpy


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    app_path = os.path.join(base_dir, "app.py")
    runpy.run_path(app_path, run_name="__main__")


if __name__ == "__main__":
    main()
