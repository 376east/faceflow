"""Build and smoke-test the FaceFlow Windows release files from HEAD."""

import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import sysconfig
import tempfile
import time
import urllib.request
import zipfile


ROOT = Path(__file__).resolve().parents[1]
PYTHON_EMBED_URL = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip"
PYTHON_EMBED_SHA256 = "4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3"
RUNTIME_FILES = (
    "INSTALL.md",
    "LICENSE",
    "THIRD_PARTY.md",
    "docs/WINDOWS.md",
    "app.py",
    "lan.py",
    "recognition.py",
    "requirements.txt",
    "requirements-windows.lock",
    "evaluation/threshold.json",
    "models/manifest.json",
    "models/SFace-LICENSE.txt",
    "models/YuNet-LICENSE.txt",
    "scripts/download_models.py",
    "web/app.js",
    "web/gallery-controls.js",
    "web/index.html",
    "web/motion.js",
    "web/style.css",
    "web/vendor/Flip.min.js",
    "web/vendor/GSAP-NOTICE.txt",
    "web/vendor/gsap.min.js",
    "web/vendor/literata-LICENSE.txt",
    "web/vendor/literata-cyrillic.woff2",
    "web/vendor/literata-latin.woff2",
    "web/vendor/manrope-LICENSE.txt",
    "web/vendor/manrope-cyrillic.woff2",
    "web/vendor/manrope-latin.woff2",
    "web/vendor/photoswipe-LICENSE.txt",
    "web/vendor/photoswipe.css",
    "web/vendor/photoswipe.umd.min.js",
)


def verify_zip(archive, name, directory):
    with zipfile.ZipFile(archive) as bundle:
        files = [member.filename for member in bundle.infolist() if not member.is_dir()]
        expected = [f"{name}/{path}" for path in RUNTIME_FILES]
        if sorted(files) != sorted(expected):
            raise RuntimeError("Unexpected or missing release files")
        # Extract only the expected files. Directory entries are implicit.
        for path in expected:
            bundle.extract(path, directory)


def request(port, path, method="GET", headers=None, body=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


def smoke(directory):
    venv = directory / ".venv"
    python = venv / "Scripts" / "python.exe"
    env = os.environ | {"FACEFLOW_DATA": str(directory / "data")}

    def run(*command):
        subprocess.run(command, cwd=directory, env=env, check=True, timeout=360)

    requirements = (directory / "requirements.txt").read_text(encoding="utf-8").splitlines()
    lock = (directory / "requirements-windows.lock").read_text(encoding="utf-8").splitlines()
    locked = {line.split()[0].lower() for line in lock if line and not line.startswith("#")}
    if not {line.lower() for line in requirements if line and not line.startswith("#")} <= locked:
        raise RuntimeError("The Windows lock differs from requirements.txt")

    run(sys.executable, "-m", "venv", venv)
    run(python, "-m", "pip", "--disable-pip-version-check", "install", "--only-binary=:all:",
        "--require-hashes", "-r", "requirements-windows.lock")
    run(python, "-m", "pip", "check")
    run(python, "scripts/download_models.py")
    run(python, "-c", "from PIL import Image; from recognition import analyze; analyze(Image.new('RGB', (320, 320)))")

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    with subprocess.Popen(
        [python, "app.py", "--port", str(port)], cwd=directory, env=env,
        stdout=subprocess.DEVNULL, stderr=None,
    ) as server:
        try:
            verify_server(server, port, Path(env["FACEFLOW_DATA"]))
        finally:
            server.terminate()
            server.wait(timeout=10)


def build_setup(work, source, iscc, label, version):
    payload = work / "payload"
    runtime = payload / "runtime"
    application = payload / "app"
    archive = work / "python-embed.zip"
    urllib.request.urlretrieve(PYTHON_EMBED_URL, archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != PYTHON_EMBED_SHA256:
        raise RuntimeError("The embeddable Python ZIP checksum differs")
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(runtime)
    (runtime / "python312._pth").write_text(
        "python312.zip\n.\nsite-packages\n..\\app\n", encoding="ascii",
    )
    subprocess.run([
        sys.executable, "-m", "pip", "install", "--only-binary=:all:", "--require-hashes",
        "--no-compile", "--target", runtime / "site-packages", "-r", source / "requirements-windows.lock",
    ], check=True, timeout=360)
    manifest = json.loads((source / "models" / "manifest.json").read_text(encoding="utf-8"))
    weights = [Path("models") / entry["file"] for entry in manifest["models"]]
    for path in [*RUNTIME_FILES, *weights]:
        destination = application / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / path, destination)
    shutil.copyfile(ROOT / "installer" / "launch.py", application / "launch.py")
    name = f"FaceFlow-{label}-Setup-x64"
    smoke_installed(payload, work / "staged-profile", open_browser=False)
    if iscc is None:
        return None
    subprocess.run([
        str(iscc), f"/DAppVersion={version}", f"/DBuildOutput={work}",
        f"/DOutputName={name}", f"/DPayload={payload}", str(ROOT / "installer" / "FaceFlow.iss"),
    ], check=True, timeout=360)
    return work / f"{name}.exe"


def smoke_setup(setup, work):
    installed = work / "installed FaceFlow"
    profile = work / "profile"
    shortcut = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "FaceFlow.lnk"
    setup_flags = ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"]
    subprocess.run([setup, *setup_flags, f"/DIR={installed}"], check=True, timeout=120)
    try:
        verify_shortcut(shortcut, installed)
        smoke_installed(installed, profile)
    finally:
        subprocess.run([installed / "unins000.exe", *setup_flags], check=True, timeout=120)
    if shortcut.exists() or (installed / "runtime").exists() or (installed / "app").exists() or not (profile / "faceflow.sqlite").exists():
        raise RuntimeError("FaceFlow uninstall did not remove the program and preserve the gallery")


def verify_shortcut(shortcut, installed):
    if not shortcut.is_file():
        raise RuntimeError("Setup did not create its Start menu shortcut")
    command = (
        '$link=(New-Object -ComObject WScript.Shell).CreateShortcut($env:FACEFLOW_CHECK_SHORTCUT); '
        '$link | Select-Object TargetPath,Arguments,WorkingDirectory | ConvertTo-Json -Compress'
    )
    link = json.loads(subprocess.check_output(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        env=os.environ | {"FACEFLOW_CHECK_SHORTCUT": str(shortcut)}, text=True, timeout=15,
    ))
    arguments = re.fullmatch(r'-B\s+-X\s+utf8\s+(?:"([^"]+)"|(\S+))', link["Arguments"])
    if not arguments:
        raise RuntimeError(f"Unexpected installed shortcut arguments: {link['Arguments']!r}")
    expected = installed / "app"
    for actual, target in (
        (link["TargetPath"], installed / "runtime" / "python.exe"),
        (arguments.group(1) or arguments.group(2), expected / "launch.py"),
        (link["WorkingDirectory"], expected),
    ):
        if not Path(actual).exists() or not Path(actual).samefile(target):
            raise RuntimeError(f"Installed shortcut points to {actual!r}, expected {str(target)!r}")


def smoke_installed(installed, profile, open_browser=True):
    env = os.environ | {"FACEFLOW_DATA": str(profile)}
    executable = installed / "runtime" / "python.exe"
    launch = [executable, "-B", "-X", "utf8", installed / "app" / "launch.py"]
    port = 8765
    if not open_browser:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        launch += ["--port", str(port)]
    with subprocess.Popen(launch, cwd=installed / "app", env=env, stdout=subprocess.DEVNULL) as server:
        try:
            verify_server(server, port, profile)
        finally:
            server.terminate()
            server.wait(timeout=10)


def verify_server(server, port, data):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and server.poll() is None:
        try:
            status, html = request(port, "/")
        except OSError:
            time.sleep(0.2)
            continue
        if status != 200 or b"<title>FaceFlow</title>" not in html:
            raise RuntimeError("FaceFlow page did not load")
        break
    else:
        raise RuntimeError("FaceFlow failed to start")

    for path in re.findall(rb'(?:href|src)="(/assets/[^"]+)"', html):
        if request(port, path.decode("ascii"))[0] != 200:
            raise RuntimeError(f"Unable to load {path.decode('ascii')}")
    config = json.loads((data / "config.json").read_text(encoding="utf-8"))
    headers = {"X-Admin-Key": config["admin"], "Content-Type": "application/json"}
    status, payload = request(port, "/api/events", headers=headers)
    if status != 200 or json.loads(payload).get("events") != []:
        raise RuntimeError("The fresh FaceFlow server did not return an empty event list")
    status, payload = request(
        port, "/api/events", method="POST", headers=headers,
        body=json.dumps({"title": "Release smoke test", "consent": True}),
    )
    if status != 201 or not json.loads(payload).get("id"):
        raise RuntimeError("The FaceFlow server could not create an event")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="directory for verified release files")
    parser.add_argument("--tag", help="annotated release tag at HEAD, omitted for a preview")
    parser.add_argument("--iscc", type=Path, help="build the Windows Setup using this Inno Setup compiler")
    parser.add_argument("--embedded-only", action="store_true", help="verify the embedded runtime without Setup")
    args = parser.parse_args()
    if (
        sys.implementation.name != "cpython"
        or sys.version_info[:3] != (3, 12, 10)
        or sysconfig.get_platform() != "win-amd64"
    ):
        parser.error("Use CPython 3.12.10 on Windows x64")

    def git(*command):
        return subprocess.check_output(["git", *command], cwd=ROOT, text=True).strip()

    commit = git("rev-parse", "HEAD")
    version = f"preview-{commit[:12]}"
    if args.tag:
        if not re.fullmatch(r"v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", args.tag):
            parser.error("Expected a release tag in vMAJOR.MINOR.PATCH form")
        ref = f"refs/tags/{args.tag}"
        if git("cat-file", "-t", ref) != "tag" or git("rev-parse", f"{ref}^{{commit}}") != commit:
            parser.error("The release tag must be annotated and point to HEAD")
        version = args.tag
    name = f"FaceFlow-{version}-source"
    output = args.output.resolve()
    with tempfile.TemporaryDirectory(prefix="faceflow-release-") as temporary:
        directory = Path(temporary)
        archive = directory / f"{name}.zip"
        git("archive", "--format=zip", f"--prefix={name}/", f"--output={archive}",
            commit, "--", *RUNTIME_FILES)
        source = directory / name
        verify_zip(archive, name, directory)
        smoke(source)
        assets = [archive]
        if args.iscc or args.embedded_only:
            setup = build_setup(directory, source, args.iscc, version, args.tag[1:] if args.tag else "0.0.0")
            if setup:
                smoke_setup(setup, directory)
                assets.append(setup)
        output.mkdir(parents=True, exist_ok=True)
        for asset in assets:
            shutil.copyfile(asset, output / asset.name)
            digest = hashlib.sha256(asset.read_bytes()).hexdigest()
            (output / f"{asset.name}.sha256").write_text(f"{digest}  {asset.name}\n", encoding="ascii")
            print(f"Packaged {asset.name} from {commit}")


if __name__ == "__main__":
    main()
