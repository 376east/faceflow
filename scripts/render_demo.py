"""Verify and render the saved event demo with embedded captions."""
import argparse
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preview', action='store_true', help='Save scene snapshots without rendering MP4')
    args = parser.parse_args()
    npx = shutil.which('npx.cmd') or shutil.which('npx')
    if not npx:
        parser.error('Node.js 22+ with npx is required')
    command = [npx, 'hyperframes@0.8.153']
    subprocess.run(command + ['check', 'demo'], cwd=ROOT, check=True)
    if args.preview:
        subprocess.run(command + ['snapshot', 'demo', '--at', '2,8,14,20,28,35,40,46,50,54,58,62,65,70,77',
                                  '--output', str(ROOT / 'work/demo-preview')], cwd=ROOT, check=True)
    else:
        subprocess.run(command + ['render', 'demo', '--quality', 'delivery', '--fps', '24',
                                  '--output', 'demo/faceflow-demo.mp4', '--skill', 'product-launch-video'],
                       cwd=ROOT, check=True)


if __name__ == '__main__':
    main()
