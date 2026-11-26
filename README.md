<img src="docs/assets/faceflow-nameplate.png" alt="FaceFlow" width="760">

[![CI](https://github.com/376east/faceflow/actions/workflows/ci.yml/badge.svg?branch=master&event=push)](https://github.com/376east/faceflow/actions/workflows/ci.yml) [![Stack](https://img.shields.io/badge/Stack-Python%20%C2%B7%20Flask-555?style=flat)](requirements.txt)

**[Download the Windows source ZIP](https://github.com/376east/faceflow/releases/download/v0.1.0/FaceFlow-v0.1.0-source.zip)** · [Release notes and checksum](https://github.com/376east/faceflow/releases/tag/v0.1.0) · [Русский](README.ru.md)

FaceFlow helps guests find their event photos with a selfie. The photographer manages the gallery, and guests can review and download their matches on the same Windows computer. The app interface is in Russian.

## Run locally

1. Install [CPython 3.12.10 for Windows x64](https://www.python.org/downloads/release/python-31210/) and extract the source ZIP into a writable folder.
2. Open PowerShell in that folder and follow [INSTALL.md](INSTALL.md). Setup needs internet access to install the pinned Python dependencies and download the recognition models. The setup commands verify the dependencies and models before launch.
3. Use the private photographer link opened by FaceFlow or printed in PowerShell. FaceFlow listens on `127.0.0.1:8765` by default, so both gallery views work only on the computer running the app.

## Try your first search

1. Create a shoot and upload photos you have permission to process. Wait for processing to finish, then choose **Опубликовать** (Publish).
2. Under **Ссылка для гостей** (Guest link), choose **Открыть** (Open) in the photographer view.
3. Add a selfie with one visible face, accept the consent prompt, and choose **Найти мои фото** (Find my photos). Review the matches and download the photos you want.

## Project links

FaceFlow's own source code is published without a declared license. Third-party components retain their own licenses. [Third-party licenses](THIRD_PARTY.md)

[Changelog](CHANGELOG.md) · [Dependencies](requirements.txt) · [Report an issue](https://github.com/376east/faceflow/issues)
