# HTTP API

Контракт текущей реализации: [маршруты app.py](../app.py), [браузерный клиент](../web/app.js). Это локальный API без версионированного публичного обещания совместимости. Базовый адрес штатного запуска - `http://127.0.0.1:8765`; JSON - UTF-8, файлы - multipart/form-data.

## Доступ

- **Admin:** заголовок `X-Admin-Key` со значением из локального `config.json`.
- **Guest:** заголовок `X-Guest-Key` с ключом конкретной съёмки.
- **Ticket:** подписанная строка в query `ticket` для media/ZIP или JSON-поле для feedback. Она выдаётся сервером; не формируйте и не изменяйте её на клиенте.

Источник: [app.py: admin, event, make_ticket, access_ticket](../app.py). Ни ключи, ни tickets не нужно публиковать в примерах запросов, логах или Git. В ссылках UI ключи находятся во fragment, а tickets в query; ссылки сами предоставляют доступ. [web/app.js](../web/app.js).

## Съёмки

| Метод и путь | Доступ | Вход | Успешный ответ |
| --- | --- | --- | --- |
| `GET /api/events` | Admin | - | `200 {events: [EventAdminSummary], pid: number}` |
| `POST /api/events` | Admin | JSON: `title`, `consent: true`, необязательный `description` | `201 {id: string}` |
| `GET /api/events/{event}` | Admin или Guest | - | `200 EventAdmin` либо `EventGuest` |
| `PATCH /api/events/{event}` | Admin | JSON: любое подмножество `title`, `description`, `status`, `detailed` | `200 {ok: true, reindexed: boolean}` |
| `POST /api/events/{event}/rotate-link` | Admin | - | `200 {guest: string}` |
| `POST /api/events/{event}/retry` | Admin | - | `200 {queued: number}` |
| `DELETE /api/events/{event}` | Admin | - | `200 {ok: true}` |

Источник: [app.py: list_events, create_event, get_event, update_event, rotate_link, retry, delete_event](../app.py).

`title` после trim - 1..120 символов, `description` - до 2000 символов. Лимит описания одинаков в UI и API. Максимум 30 съёмок. `status` - `draft | published | paused`, `detailed` - JSON boolean. Новая съёмка создаётся `draft`, с `detailed = true`; публикация требует `ready > 0` и `pending == 0`, иначе `409`. Изменение `detailed` переиндексирует всю съёмку; retry ставит в очередь только `error`. [app.py: create_event, update_event, requeue](../app.py), [web/app.js: adminEvent](../web/app.js).

`GET` выбирает admin-ветку при наличии непустого `X-Admin-Key`: неверный admin key не откатывается к guest key. Guest получает заголовок съёмки и прогресс даже для draft/paused, но не список фото. [app.py: get_event](../app.py).

### Объекты ответа

`EventAdminSummary`:

```text
id: string, title: string, guest: string, created: Unix seconds,
description: string, status: draft|published|paused,
detailed: SQLite integer 0|1, link_version: integer,
total, ready, pending, errors, faces, no_faces: integer,
views, searches, downloads, feedback: integer
```

`EventAdmin` - этот объект плюс `photos: [PhotoAdmin]`. `EventGuest` содержит только `id, title, description, status, total, ready, pending, errors`. `views` увеличивается при guest GET без cookie `ff_view_<event>`; cookie выставляется на сутки. [app.py: summary, get_event](../app.py).

`PhotoAdmin`:

```text
id, name: string; status: pending|ready|error; error: string|null;
count, width, height, size, bytes, duration_ms: integer;
warnings: string[]; preview, download: relative URL
```

`size` и `bytes` - одинаковый размер нормализованного JPEG; `count` - число проиндексированных лиц. `warnings` могут содержать `small_face`, `blurred_face`, `no_faces`. Ссылки создаются и для pending/error, но media требует ready. [app.py: get_event, index_photo, media](../app.py), [recognition.py: analyze](../recognition.py).

## Фотографии и поиск

| Метод и путь | Доступ | Вход | Успешный ответ |
| --- | --- | --- | --- |
| `POST /api/events/{event}/photos` | Admin | multipart: один `photo` | `201 {id, duplicate: false}`; дубликат: `200 {id, duplicate: true}` |
| `DELETE /api/events/{event}/photos/{photo}` | Admin | - | `200 {ok: true}` |
| `POST /api/events/{event}/search` | Guest | multipart: `selfie`, `consent=yes` | `200 SearchResult` |
| `GET /media/{event}/{photo}?ticket=...` | Ticket | необязательные `thumb=1`, `download=1` | `200 image/jpeg` |
| `GET /api/events/{event}/download?ticket=...` | Ticket | необязательный `ids=id1,id2` | `200 application/zip` |
| `POST /api/events/{event}/feedback` | Guest + Ticket | JSON: `ticket`, `photo_id`, `kind: "not_me"` | `200 {ok: true}` |

Источник: [app.py: upload, delete_photo, search, media, download, feedback](../app.py).

### Ограничения файлов

Фото галереи: JPEG/PNG/WebP до 25 МиБ; селфи: те же форматы до 10 МиБ. Изображение имеет не менее 32 пикселей по каждой стороне и не более 50 млн пикселей. Общий HTTP body ограничен 26 МиБ. На съёмку - до 5000 фото и 8 ГиБ нормализованных JPEG; превью и база в этот предел не входят. Дедупликация - SHA-256 исходных байтов в пределах одной съёмки; разные кодировки того же изображения могут считаться разными файлами. [app.py: app.config, decode, upload, search](../app.py).

### Поиск

Поиск доступен только в `published` съёмке, когда очередь пуста и есть готовые фотографии, иначе `409`. На селфи должно детектироваться ровно одно лицо; лицо с `small_face` отклоняется (`400`). `blurred_face` само по себе не является серверным запретом. [app.py: search](../app.py), [recognition.py: analyze](../recognition.py).

```json
{
  "photos": [
    {"id": "photo-id", "name": "frame.png", "preview": "/media/...", "download": "/media/..."}
  ],
  "zip": "/api/events/event-id/download?ticket=...",
  "ticket": "signed-value",
  "duration_ms": 123,
  "count": 1,
  "expires_in": 1200
}
```

Пример показывает схему, значения условные. При пустой выдаче `photos=[]`, `count=0`, `zip=null`; ticket всё равно выдаётся. Числовая похожесть не возвращается. Сравнение использует скалярное произведение нормализованных векторов с унаследованным порогом `0.60`; независимая точность текущей реализации не измерена. [app.py: search](../app.py), [threshold.json](../evaluation/threshold.json).

### Билеты, скачивание и обратная связь

Ticket действителен 1200 секунд, только для указанной съёмки и включённых photo ID. Смена гостевой ссылки увеличивает `link_version` и аннулирует прежние билеты. Гостевой ticket требует опубликованной съёмки; административный может читать draft/paused. [app.py: make_ticket, rotate_link, access_ticket](../app.py).

`thumb=1` выдаёт JPEG-превью; `download=1` - attachment с исходным stem имени и расширением `.jpg`. ZIP допускает `ids` только как подмножество ticket; дубли IDs убираются. Если разрешённый кадр удалён, ZIP отвечает `409`; пустой набор - `400`. Сумма файлов больше 256 МиБ - `413`. ZIP содержит нормализованные JPEG, имена вида `001_<stem>.jpg`. [app.py: media, download](../app.py).

Feedback принимает только `not_me`, photo ID должен входить в ticket. Повтор одного сочетания event/photo/ticket/kind игнорируется; в базе хранится SHA-256 ticket, не его исходная строка. Отметка не меняет модель и не скрывает кадр на сервере; клиент исключает его из выбора для текущего ZIP. [app.py: feedback](../app.py), [web/app.js: results](../web/app.js).

## Ошибки и заголовки

Ожидаемые ошибки API возвращают JSON `{"error": "сообщение"}`. `400` - неверный ввод или ограничение, `403` - ключ/ticket, `404` - отсутствующий объект, `409` - неподходящий статус/готовность или изменившаяся подборка, `413` - размер, `500` - внутренняя ошибка. JSON handlers зарегистрированы для 400/403/404/413/500; 409 возвращается явно соответствующими маршрутами. Другие ошибки HTTP не имеют обещанного JSON-формата. [app.py: error_response и маршруты](../app.py).

Все ответы получают `Cache-Control: no-store`, `Referrer-Policy: no-referrer`, `X-Content-Type-Options: nosniff` и CSP. Cookies не являются проверкой доступа; ключи и tickets проверяются на сервере. [app.py: headers, admin, event, access_ticket](../app.py).

HTML `/` и `/e/{event}` и статика `/assets/{name}` выдаются без ключа; получение HTML не означает доступ к данным. [app.py: page, assets](../app.py).