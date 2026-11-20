<img src="docs/assets/faceflow-nameplate.png" alt="FaceFlow" width="760">

[![CI](https://github.com/376east/faceflow/actions/workflows/ci.yml/badge.svg?branch=master&event=push)](https://github.com/376east/faceflow/actions/workflows/ci.yml) [![Stack](https://img.shields.io/badge/Stack-Python%20%C2%B7%20Flask-555?style=flat)](requirements.txt)

**[Русский](README.ru.md)**

Prepare an event gallery for your guests. They can submit a selfie, review matching photos, and download their selection. Recognition runs on the photographer's computer.

## Run locally

Requires Python 3.12. On Windows, run:

```powershell
git clone https://github.com/376east/faceflow.git
cd faceflow
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe scripts/download_models.py
.venv/Scripts/python.exe app.py --open
```

FaceFlow opens at `http://127.0.0.1:8765`. It only listens on your computer. Keep the photographer's access link private. Review matches before using them.

## Project links

[Dependencies](requirements.txt) · [Third-party licenses](THIRD_PARTY.md) · [Report an issue](https://github.com/376east/faceflow/issues)
