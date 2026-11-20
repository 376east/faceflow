"""Build a source ZIP from HEAD and smoke-test its Windows install."""

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
import zipfile


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_FILES = (
    "INSTALL.md",
    "app.py",
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
    parser.add_argument("--output", type=Path, required=True, help="directory for the verified ZIP and checksum")
    parser.add_argument("--tag", help="annotated release tag at HEAD, omitted for a preview")
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
        verify_zip(archive, name, directory)
        smoke(directory / name)
        output.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(archive, output / archive.name)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        (output / f"{archive.name}.sha256").write_text(f"{digest}  {archive.name}\n", encoding="ascii")
        print(f"Verified {archive.name} from {commit}")


if __name__ == "__main__":
    main()
