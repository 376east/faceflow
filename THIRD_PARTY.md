# Сторонние материалы

Собственный код и документация FaceFlow распространяются по [лицензии MIT](LICENSE). У сторонних компонентов действуют их собственные лицензии. Графика FaceFlow в `docs/assets/`, название, логотип и синтетические изображения в `tests/fixtures/` исключены из лицензии на код.

Модели берутся из OpenCV Zoo на закрепленной ревизии `47534e27c9851bb1128ccc0102f1145e27f23f98`. Веса не хранятся в Git; [download_models.py](scripts/download_models.py) скачивает их по [manifest.json](models/manifest.json) и проверяет размер и SHA-256.

- YuNet: [официальная MIT License](https://github.com/opencv/opencv_zoo/blob/47534e27c9851bb1128ccc0102f1145e27f23f98/models/face_detection_yunet/LICENSE), локальная копия [YuNet-LICENSE.txt](models/YuNet-LICENSE.txt).
- SFace: [официальная Apache License 2.0](https://github.com/opencv/opencv_zoo/blob/47534e27c9851bb1128ccc0102f1145e27f23f98/models/face_recognition_sface/LICENSE), локальная копия [SFace-LICENSE.txt](models/SFace-LICENSE.txt).

Python-библиотеки устанавливаются отдельно по [requirements.txt](requirements.txt); их лицензионные файлы доступны в соответствующих пакетах.

Установщик включает CPython и Python-библиотеки с их лицензионными файлами. [Лицензия CPython](https://docs.python.org/3.12/license.html)

Лицензии и уведомления браузерных компонентов приложены к исходникам. [PhotoSwipe](web/vendor/photoswipe-LICENSE.txt) · [GSAP](web/vendor/GSAP-NOTICE.txt) · [Manrope](web/vendor/manrope-LICENSE.txt) · [Literata](web/vendor/literata-LICENSE.txt)

Синтетические материалы для проверок созданы встроенным imagegen без референсов реальных людей. Точная модель генерации инструментом не сообщена. [Происхождение и запросы](tests/fixtures/PROVENANCE.md).
