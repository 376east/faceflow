# Синтетические данные

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
