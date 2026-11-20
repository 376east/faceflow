# Сторонние материалы

Лицензия на собственный код проекта пока не выбрана. Доступность репозитория сама по себе не назначает MIT или другую лицензию. Этот файл перечисляет условия сторонних компонентов и не меняет права на собственный код.

Модели берутся из OpenCV Zoo на закрепленной ревизии `47534e27c9851bb1128ccc0102f1145e27f23f98`. Веса не хранятся в Git; [download_models.py](scripts/download_models.py) скачивает их по [manifest.json](models/manifest.json) и проверяет размер и SHA-256.

- YuNet: [официальная MIT License](https://github.com/opencv/opencv_zoo/blob/47534e27c9851bb1128ccc0102f1145e27f23f98/models/face_detection_yunet/LICENSE), локальная копия [YuNet-LICENSE.txt](models/YuNet-LICENSE.txt).
- SFace: [официальная Apache License 2.0](https://github.com/opencv/opencv_zoo/blob/47534e27c9851bb1128ccc0102f1145e27f23f98/models/face_recognition_sface/LICENSE), локальная копия [SFace-LICENSE.txt](models/SFace-LICENSE.txt).

Python-библиотеки устанавливаются отдельно по [requirements.txt](requirements.txt); их лицензионные файлы доступны в соответствующих пакетах. FFmpeg и системные шрифты нужны только для производства видео и не распространяются здесь.

Синтетические портреты созданы для этого демо встроенным imagegen без референсов реальных людей; [происхождение и запросы](demo/synthetic/PROVENANCE.md). Точная модель генерации инструментом не сообщена. WAV озвучки созданы Microsoft ru-RU-SvetlanaNeural; см. описание происхождения синтетических материалов. Электронная подложка синтезируется локально кодом проекта, сторонней музыкальной записи нет.
