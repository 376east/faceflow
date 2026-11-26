"""Launch FaceFlow with the installed runtime and a per-user data directory."""
import ctypes
import os
from pathlib import Path
import runpy
import sys


if __name__ == "__main__":
    os.environ.setdefault("FACEFLOW_DATA", str(Path(os.environ["LOCALAPPDATA"]) / "FaceFlow" / "data"))
    ctypes.windll.kernel32.SetConsoleTitleW("FaceFlow")
    print("FaceFlow — close this window or press Ctrl+C to stop the gallery.", flush=True)
    if len(sys.argv) == 1:
        sys.argv.append("--open")
    runpy.run_module("app", run_name="__main__")
