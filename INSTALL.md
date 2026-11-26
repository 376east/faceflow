# Run FaceFlow on Windows

Download the `FaceFlow-vX.Y.Z-source.zip` asset from Releases and extract it to a writable folder. Open PowerShell in the extracted folder.

The verified runtime is [CPython 3.12.10, Windows x64](https://www.python.org/downloads/release/python-31210/). Setup needs internet access to PyPI and GitHub's model download host.

```powershell
py -3.12 -c "import sys, sysconfig; assert sys.version_info[:3] == (3, 12, 10) and sysconfig.get_platform() == 'win-amd64', 'Use CPython 3.12.10 x64'"
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --only-binary=:all: --require-hashes -r requirements-windows.lock
.\.venv\Scripts\python.exe scripts/download_models.py
.\.venv\Scripts\python.exe app.py --open
```

Run the commands in order and resolve any error before continuing. `requirements-windows.lock` pins the direct and transitive Windows wheel versions and verifies their SHA-256 hashes. The model setup verifies each download against [the pinned manifest](models/manifest.json). For an OpenCV DLL import error, install the [Microsoft Visual C++ x64 Redistributable](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist).

FaceFlow opens at `http://127.0.0.1:8765`. If the browser does not open, use the full photographer link printed in the terminal. Keep that link private. If the port is occupied, add `--port 8766` to the launch command. Use the same launch command for subsequent sessions and press Ctrl+C in the terminal to stop FaceFlow.

FaceFlow stores galleries and credentials in `data/` by default. Keep that folder private. Back it up separately before moving to a new version. Search and photo downloads run locally. Loopback access limits gallery links to the computer running FaceFlow.

See the [Windows guide](docs/WINDOWS.md) for installing with Setup and sharing a shoot with phones on your local network.

The FaceFlow code is licensed under the [MIT license](LICENSE). See the [license scope and third-party notices](THIRD_PARTY.md) for the models, browser assets, and Python runtime.
