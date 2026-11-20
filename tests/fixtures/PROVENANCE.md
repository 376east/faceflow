# Синтетические данные

## Съёмка 13 октября 2026

`event/conference-001.jpg` ... `conference-096.jpg` и четыре портрета в `selfies/` созданы встроенным OpenAI imagegen. Все персонажи взрослые и вымышленные. Точная модель инструментом не сообщена. [Манифест](event-manifest.json) хранит ожидаемых участников каждого кадра. [check_demo.py](../../scripts/check_demo.py) сохраняет фактические совпадения и пропуски в локальный отчёт.

Сначала создан лист четырёх персонажей: Aya - женщина с рыжими волосами, веснушками и зелёным пиджаком; Arjun - мужчина с тёмными кудрями, бородой и синим пиджаком; Mei - женщина с коротким каре и круглыми очками; Max - мужчина с седыми волосами и бордовой рубашкой. Их портреты выделены в отдельные JPEG для поиска.

По этому синтетическому референсу сгенерированы 24 листа по четыре независимо составленных фотографии. Каждая четверть выделена в самостоятельный JPEG 768×512. Фотографии не размножены поворотами, изменением яркости или повторными кадрированиями одного снимка. Запросы задавали одно IT-мероприятие в деревянном зале с тёмно-синей сценой, светлыми креслами и красно-чёрными лентами бейджей. Ситуации: выступление, вопросы из зала, панельная дискуссия, регистрация, заметки, кофе, общение и вечерний отдых. Менялись жесты, положение камеры, поворот лица, дневной и тёплый свет; внешность сохранялась по референсу. Есть девять парных кадров.

Набор закреплён для функциональной проверки и измерения скорости. Повторная генерация не гарантирует совпадение лиц. Порог продукта не изменён ради этого набора. [Локальное измерение скорости](../../docs/VERIFICATION.md#локальное-измерение-скорости).

## Прежние тестовые портреты

`person-a.png` и `person-b.png` созданы для FaceFlow 4 октября 2026 встроенным инструментом OpenAI imagegen. Референсы, фотографии настоящих людей, личные сообщения и пользовательские селфи инструменту не передавались. Точная модель генерации инструментом не сообщена. Сохраненные PNG являются закрепленными входами тестов; повторная генерация по запросам ниже не обязана дать те же лица.

Это два вымышленных взрослых персонажа. Ни портреты, ни производные варианты не являются набором для независимой оценки качества распознавания. Изменение яркости того же исходника - функциональный smoke test. В отличие от прежней локальной демки, материалы реальных мероприятий в этом публичном наборе отсутствуют. [Тесты](../../tests/test_flow.py), [подготовка съемки](../../scripts/seed_demo.py).

## Запрос для person-a.png

```text
Use case: photorealistic-natural. Create one synthetic demonstration photograph for an open-source face-photo-search application. A completely fictional young adult woman, age 25, with short dark curly hair, dark brown eyes and a vivid cobalt-blue jacket, facing the camera, head and shoulders, neutral friendly expression, bright soft daylight. A softly blurred contemporary conference foyer in background. Front-facing, unobstructed single face, no other faces, no logos, no text, no actual known person or reference. 1024x1024 square photographic composition. This is generated test data, not a real person.
```

## Запрос для person-b.png

```text
Use case: photorealistic-natural. Create one synthetic demonstration photograph for an open-source face-photo-search application. A completely fictional young adult man, age 28, with medium-brown skin, short black hair, neatly trimmed beard, dark eyes, a warm terracotta T-shirt. Head-and-shoulders, facing camera, unobstructed single face, neutral relaxed expression. Softly blurred modern conference foyer behind him, bright soft daylight. No other faces, no logos, no text, no known person or reference image. Square 1024x1024 photographic composition. Generated test data, not a real person.
```

Размер запрошен в тексте; фактические пиксели определяются сохраненными PNG. Созданные изображения скопированы в проект без замены локальных пользовательских данных.
