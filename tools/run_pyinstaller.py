import sys

import PyInstaller
import PyInstaller.__main__

# Teach PyInstaller about Pyston
if hasattr(sys, "pyston_version_info"):
    PyInstaller.compat.PYDYLIB_NAMES.clear()
    PyInstaller.compat.PYDYLIB_NAMES.update(["libpython3.8-pyston2.3.so"])

PyInstaller.__main__.run(
    ["-n", "snooty", "--onedir", "--contents-directory", ".", "snootycli.py"]
)
