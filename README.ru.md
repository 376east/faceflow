# FaceFlow

[English](README.md)

Фотограф открывает гостевую галерею. Участник делает селфи, проверяет найденные кадры и скачивает подборку. Поиск выполняется на компьютере фотографа.

## Запуск

Нужен Python 3.12. В PowerShell:

```powershell
git clone https://github.com/376east/faceflow.git
cd faceflow
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe scripts/download_models.py
.venv/Scripts/python.exe app.py --open
```

FaceFlow открывается по адресу `http://127.0.0.1:8765`. Приложение доступно на этом компьютере. Ссылка фотографа даёт доступ к управлению съёмкой, храните её отдельно. Проверяйте найденные кадры перед использованием.

[Сторонние лицензии](THIRD_PARTY.md) · [Сообщить о проблеме](https://github.com/376east/faceflow/issues)
