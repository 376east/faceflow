"""Install the pinned Windows Chrome for Testing into this repository's ignored work/."""
import hashlib
from pathlib import Path
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = '153.0.8010.36'
SHA256 = '8edfaa0923c11a30a9315a5e7e5794c5efb60146edea7e3f749f7fdc2aa026cb'
FOLDER = ROOT / 'work' / 'test-browser' / VERSION


def install():
    FOLDER.mkdir(parents=True, exist_ok=True)
    archive = FOLDER / 'chrome-win64.zip'
    if not archive.exists() or hashlib.sha256(archive.read_bytes()).hexdigest() != SHA256:
        with urllib.request.urlopen(f'https://storage.googleapis.com/chrome-for-testing-public/{VERSION}/win64/chrome-win64.zip', timeout=60) as response:
            with archive.open('wb') as target:
                while chunk := response.read(1024 * 1024):
                    target.write(chunk)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != SHA256:
        raise RuntimeError('Chrome for Testing archive SHA-256 mismatch')
    with zipfile.ZipFile(archive) as bundle:
        for item in bundle.infolist():
            if not (FOLDER / item.filename).resolve().is_relative_to(FOLDER.resolve()):
                raise ValueError('Browser archive entry escapes its installation folder')
        if not (FOLDER / 'chrome-win64' / 'chrome.exe').exists():
            bundle.extractall(FOLDER)
    print(f'Chrome for Testing {VERSION} verified in work/test-browser')


if __name__ == '__main__':
    install()
