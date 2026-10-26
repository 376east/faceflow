"""FaceFlow local MVP. Run with .venv/Scripts/python.exe app.py."""
from __future__ import annotations

import hashlib
import io
import json
import logging
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import threading
import time
import warnings
import zipfile
import re
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

import cv2
import numpy as np
from flask import Flask, Request, abort, jsonify, request, send_file, send_from_directory
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from PIL import Image, ImageOps, UnidentifiedImageError
from recognition import analyze, verify_models

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('FACEFLOW_DATA', str(ROOT / 'data'))).resolve()
DATA.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = DATA / 'config.json'
if not CONFIG_FILE.exists():
    CONFIG_FILE.write_text(json.dumps({'admin': secrets.token_urlsafe(32), 'signing': secrets.token_urlsafe(32)}), encoding='utf-8')
CONFIG = json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
signer = URLSafeTimedSerializer(CONFIG['signing'], salt='photo-access')


class MemoryUploadRequest(Request):
    def _get_file_stream(self, total_content_length, content_type, filename=None, content_length=None):
        # Prevent Werkzeug spilling large selfies to temporary files on disk.
        return io.BytesIO()


app = Flask(__name__, static_folder=None)
app.request_class = MemoryUploadRequest
app.config['MAX_CONTENT_LENGTH'] = 26 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 50_000_000
warnings.simplefilter('error', Image.DecompressionBombWarning)
lock = threading.RLock()
pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='face-index')
cv2.setNumThreads(2)
THRESHOLD = 0.60  # Inherited local-MVP threshold; see PLAN.md evaluation gaps.
threshold_file = ROOT / 'evaluation' / 'threshold.json'
if threshold_file.exists():
    THRESHOLD = float(json.loads(threshold_file.read_text())['threshold'])


@contextmanager
def db():
    connection = sqlite3.connect(DATA / 'faceflow.sqlite', timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys=ON')
    connection.execute('PRAGMA secure_delete=ON')
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def migrate_face_boxes(conn):
    """Queue old face indexes once; retain their rows and stored photographs."""
    if 'box' not in {row[1] for row in conn.execute('PRAGMA table_info(faces)')}:
        conn.execute('ALTER TABLE faces ADD COLUMN box TEXT')
    return conn.execute("""UPDATE photos SET status='pending',error=NULL,count=0,generation=generation+1
        WHERE status='ready' AND EXISTS
        (SELECT 1 FROM faces WHERE faces.photo=photos.id AND faces.box IS NULL)""").rowcount


with db() as conn:
    conn.executescript('''
    PRAGMA journal_mode=WAL;
    CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, title TEXT NOT NULL, guest TEXT NOT NULL, created REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS photos(id TEXT PRIMARY KEY, event TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
      name TEXT NOT NULL, hash TEXT NOT NULL, size INTEGER NOT NULL, status TEXT NOT NULL, error TEXT, count INTEGER DEFAULT 0,
      UNIQUE(event, hash));
    CREATE TABLE IF NOT EXISTS faces(photo TEXT NOT NULL REFERENCES photos(id) ON DELETE CASCADE, vector BLOB NOT NULL);
    CREATE INDEX IF NOT EXISTS photos_event ON photos(event);
    CREATE INDEX IF NOT EXISTS faces_photo ON faces(photo);
    CREATE TABLE IF NOT EXISTS metrics(event TEXT REFERENCES events(id) ON DELETE CASCADE,name TEXT,count INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(event,name));
    CREATE TABLE IF NOT EXISTS feedback(event TEXT REFERENCES events(id) ON DELETE CASCADE,photo TEXT REFERENCES photos(id) ON DELETE CASCADE,grant TEXT,kind TEXT,created REAL,UNIQUE(event,photo,grant,kind));
    ''')
    # Additive migration preserves every existing gallery and uploaded file.
    for table, additions in {
        'events': {'description':"TEXT NOT NULL DEFAULT ''", 'status':"TEXT NOT NULL DEFAULT 'published'", 'detailed':'INTEGER NOT NULL DEFAULT 1', 'link_version':'INTEGER NOT NULL DEFAULT 0'},
        'photos': {'width':'INTEGER DEFAULT 0','height':'INTEGER DEFAULT 0','warnings':"TEXT DEFAULT '[]'",'generation':'INTEGER NOT NULL DEFAULT 0','duration_ms':'INTEGER DEFAULT 0'},
    }.items():
        present={r['name'] for r in conn.execute(f'PRAGMA table_info({table})')}
        for name,definition in additions.items():
            if name not in present:conn.execute(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')
    migrate_face_boxes(conn)
    if conn.execute('PRAGMA user_version').fetchone()[0]<2:
        for row in conn.execute('SELECT id,event FROM photos').fetchall():
            stored=DATA/row['event']/(row['id']+'.jpg')
            if stored.exists():conn.execute('UPDATE photos SET size=? WHERE id=?',(stored.stat().st_size,row['id']))
        conn.execute('PRAGMA user_version=2')


def load_models():
    verify_models()


def decode(raw, jpeg_only=False):
    try:
        with Image.open(io.BytesIO(raw)) as source:
            if jpeg_only and source.format != 'JPEG':
                raise ValueError('Для галереи подходят только JPEG.')
            if source.format not in ('JPEG', 'PNG', 'WEBP'):
                raise ValueError('Используйте JPEG, PNG или WebP.')
            if source.width * source.height > 50_000_000 or min(source.size) < 32:
                raise ValueError('Фото должно быть от 32 пикселей и не больше 50 мегапикселей.')
            image = ImageOps.exif_transpose(source).convert('RGB')
            image.load()
            return image
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValueError('Не удалось прочитать изображение. Выберите другой файл.') from None


def features(image):
    return [face['vector'] for face in analyze(image)['faces']]


def normalized_face_box(box, width, height):
    if box is None or width <= 0 or height <= 0:
        return None
    x, y, w, h = box
    left, top = max(0, min(width, x)), max(0, min(height, y))
    right, bottom = max(left, min(width, x+w)), max(top, min(height, y+h))
    return [left/width, top/height, (right-left)/width, (bottom-top)/height]


def index_photo(photo_id):
    photo = None
    try:
        with lock, db() as conn:
            photo = conn.execute('SELECT p.*,e.detailed FROM photos p JOIN events e ON e.id=p.event WHERE p.id=?', (photo_id,)).fetchone()
            if not photo or photo['status']!='pending':return
            folder = DATA / photo['event']
            with Image.open(folder / (photo_id + '.jpg')) as source:
                image=source.convert('RGB')
        # Expensive inference does not block gallery reads, uploads or searches.
        result=analyze(image,detailed=bool(photo['detailed']))
        thumb=image.copy();thumb.thumbnail((720,720))
        flags=sorted({flag for face in result['faces'] for flag in face['warnings']})
        if not result['faces']:flags.append('no_faces')
        with lock, db() as conn:
            current=conn.execute('SELECT generation FROM photos WHERE id=?',(photo_id,)).fetchone()
            if not current or current['generation']!=photo['generation']:return
            thumb.save(folder/(photo_id+'-thumb.jpg'),quality=82)
            conn.execute('DELETE FROM faces WHERE photo=?', (photo_id,))
            conn.executemany('INSERT INTO faces(photo,vector,box) VALUES (?,?,?)',
                [(photo_id,f['vector'].tobytes(),json.dumps(f['box']) if f.get('box') is not None else None) for f in result['faces']])
            conn.execute("UPDATE photos SET status='ready',count=?,error=NULL,width=?,height=?,warnings=?,duration_ms=? WHERE id=?",(len(result['faces']),result['width'],result['height'],json.dumps(flags),result['duration_ms'],photo_id))
    except Exception:
        logging.exception('Index failed for %s',photo_id)
        if photo:
            with lock, db() as conn:
                conn.execute("UPDATE photos SET status='error',error=? WHERE id=? AND generation=?",('Не удалось обработать фото. Попробуйте повторную обработку.',photo_id,photo['generation']))


def increment(event_id,name):
    with db() as conn:
        if not conn.execute('SELECT id FROM events WHERE id=?',(event_id,)).fetchone():return
        conn.execute('INSERT INTO metrics(event,name,count) VALUES (?,?,1) ON CONFLICT(event,name) DO UPDATE SET count=count+1',(event_id,name))


def restore_staged(stage,metadata):
    original=DATA/metadata['event']
    payload=stage/'payload'
    if metadata.get('photo') and payload.exists():
        for item in payload.iterdir():
            target=original/item.name
            if not target.exists():item.replace(target)
    elif payload.exists() and not original.exists():payload.replace(original)
    shutil.rmtree(stage)


def remove_storage(event_id,photo_id=None):
    """Rename first, commit deletion, then purge; failed commit restores local copies."""
    stage=DATA/'.trash'/secrets.token_hex(12)
    with lock:
        event(event_id)
        with db() as conn:
            if photo_id and not conn.execute('SELECT id FROM photos WHERE event=? AND id=?',(event_id,photo_id)).fetchone():abort(404)
        metadata={'event':event_id,'photo':photo_id}
        stage.mkdir(parents=True)
        (stage/'operation.json').write_text(json.dumps(metadata),encoding='utf-8')
        try:
            if photo_id:
                (stage/'payload').mkdir()
                for suffix in ('.jpg','-thumb.jpg'):
                    source=DATA/event_id/(photo_id+suffix)
                    if source.exists():source.replace(stage/'payload'/source.name)
            else:(DATA/event_id).replace(stage/'payload')
            with db() as conn:
                if photo_id:conn.execute('DELETE FROM photos WHERE event=? AND id=?',(event_id,photo_id))
                else:conn.execute('DELETE FROM events WHERE id=?',(event_id,))
        except Exception:
            restore_staged(stage,metadata)
            raise
        try:shutil.rmtree(stage)
        except OSError:logging.exception('Committed deletion awaiting cleanup: %s',stage.name)


def recover_deletions():
    """Recover the rename/SQLite gap after a forced process shutdown."""
    trash=DATA/'.trash'
    if not trash.exists():return
    for stage in trash.iterdir():
        try:
            metadata=json.loads((stage/'operation.json').read_text(encoding='utf-8'))
            if not re.fullmatch('[0-9a-f]{24}',metadata['event']) or (metadata.get('photo') and not re.fullmatch('[0-9a-f]{24}',metadata['photo'])):raise ValueError('Invalid deletion journal')
            with db() as conn:
                exists=conn.execute('SELECT id FROM photos WHERE id=? AND event=?',(metadata['photo'],metadata['event'])).fetchone() if metadata.get('photo') else conn.execute('SELECT id FROM events WHERE id=?',(metadata['event'],)).fetchone()
            if exists:restore_staged(stage,metadata)
            else:shutil.rmtree(stage)
        except Exception:logging.exception('Unable to recover deletion journal %s',stage.name)


def requeue(event_id,only_errors=False):
    with lock:
        with db() as conn:
            condition="AND status='error'" if only_errors else ''
            rows=conn.execute('SELECT id FROM photos WHERE event=? '+condition,(event_id,)).fetchall()
            for row in rows:
                conn.execute("UPDATE photos SET status='pending',error=NULL,count=0,generation=generation+1 WHERE id=?",(row['id'],))
                conn.execute('DELETE FROM faces WHERE photo=?',(row['id'],))
        for row in rows:pool.submit(index_photo,row['id'])
    return len(rows)


def admin():
    if not secrets.compare_digest(request.headers.get('X-Admin-Key', ''), CONFIG['admin']):
        abort(403)


def event(event_id, guest=False):
    with db() as conn:
        row = conn.execute('SELECT * FROM events WHERE id=?', (event_id,)).fetchone()
    if not row:
        abort(404)
    if guest and not secrets.compare_digest(request.headers.get('X-Guest-Key', ''), row['guest']):
        abort(403)
    return row


def summary(event_id):
    with db() as conn:
        counts = conn.execute('SELECT status,COUNT(*) n,SUM(count) faces FROM photos WHERE event=? GROUP BY status', (event_id,)).fetchall()
    values = {row['status']: row['n'] for row in counts}
    with db() as conn:
        no_faces=conn.execute("SELECT COUNT(*) FROM photos WHERE event=? AND status='ready' AND count=0",(event_id,)).fetchone()[0]
        metrics={r['name']:r['count'] for r in conn.execute('SELECT name,count FROM metrics WHERE event=?',(event_id,))}
        feedback=conn.execute('SELECT COUNT(*) FROM feedback WHERE event=?',(event_id,)).fetchone()[0]
    return dict(total=sum(values.values()), ready=values.get('ready', 0), pending=values.get('pending', 0), errors=values.get('error', 0), faces=sum(row['faces'] or 0 for row in counts),no_faces=no_faces,views=metrics.get('views',0),searches=metrics.get('searches',0),downloads=metrics.get('downloads',0),feedback=feedback)


def make_ticket(event_id,photos,admin_access=False,version=None):
    if version is None:version=event(event_id)['link_version']
    return signer.dumps({'event':event_id,'photos':photos,'version':version,'admin':admin_access})


def photo_url(event_id, photo_id, thumb=False,admin_access=False,version=None):
    ticket = make_ticket(event_id,[photo_id],admin_access,version)
    return f'/media/{event_id}/{photo_id}?ticket={ticket}' + ('&thumb=1' if thumb else '')


@app.after_request
def headers(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' blob:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    return response


@app.errorhandler(400)
@app.errorhandler(403)
@app.errorhandler(404)
@app.errorhandler(413)
@app.errorhandler(500)
def error_response(error):
    messages = {400: 'Некорректный запрос.', 403: 'Нет доступа. Откройте полную ссылку.', 404: 'Съёмка или файл не найдены.', 413: 'Файл слишком большой. Максимум 25 МБ.', 500: 'Ошибка обработки. Попробуйте ещё раз.'}
    return jsonify(error=messages.get(error.code, 'Ошибка запроса.')), error.code


@app.get('/')
@app.get('/e/<event_id>')
def page(event_id=None):
    return send_from_directory(ROOT / 'web', 'index.html')


@app.get('/assets/<path:name>')
def assets(name):
    return send_from_directory(ROOT / 'web', name)


@app.get('/api/events')
def list_events():
    admin()
    with db() as conn:
        rows = conn.execute("""SELECT e.*,p.id cover_photo FROM events e
            LEFT JOIN (SELECT event,MIN(rowid) first_ready FROM photos WHERE status='ready' GROUP BY event) c ON c.event=e.id
            LEFT JOIN photos p ON p.rowid=c.first_ready ORDER BY e.created DESC""").fetchall()
    events=[]
    for row in rows:
        item=dict(row)
        cover_photo=item.pop('cover_photo')
        item['cover']=photo_url(row['id'],cover_photo,thumb=True,admin_access=True,version=row['link_version']) if cover_photo else None
        events.append(item | summary(row['id']))
    return jsonify(events=events, pid=os.getpid())


@app.post('/api/events')
def create_event():
    admin()
    body = request.get_json(silent=True) or {}
    if not isinstance(body,dict):abort(400)
    title = body.get('title')
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 120:
        return jsonify(error='Введите название съёмки, до 120 символов.'), 400
    if body.get('consent') is not True:
        return jsonify(error='Подтвердите разрешение на обработку фотографий.'), 400
    description=body.get('description','')
    if not isinstance(description,str) or len(description)>2000:return jsonify(error='Описание должно быть не длиннее 2000 символов.'),400
    with lock, db() as conn:
        if conn.execute('SELECT COUNT(*) FROM events').fetchone()[0] >= 30:
            return jsonify(error='Максимум 30 съёмок. Удалите ненужные.'), 400
        event_id = secrets.token_hex(12)
        guest_key = secrets.token_urlsafe(24)
        (DATA / event_id).mkdir()
        conn.execute("INSERT INTO events(id,title,guest,created,description,status,detailed) VALUES (?,?,?,?,?,'draft',1)", (event_id, title.strip(), guest_key, time.time(),description.strip()))
    return jsonify(id=event_id), 201


@app.get('/api/events/<event_id>')
def get_event(event_id):
    if request.headers.get('X-Admin-Key'):
        admin()
        row = event(event_id)
        with db() as conn:
            photos = conn.execute('SELECT id,name,status,error,count,width,height,size,warnings,duration_ms FROM photos WHERE event=? ORDER BY rowid DESC', (event_id,)).fetchall()
        return jsonify(dict(row) | summary(event_id) | {'photos': [dict(p) | {'bytes':p['size'],'warnings':json.loads(p['warnings']),'preview': photo_url(event_id, p['id'], True,True,row['link_version']),'download':photo_url(event_id,p['id'],False,True,row['link_version'])+'&download=1'} for p in photos]})
    row = event(event_id, guest=True)
    response=jsonify(id=row['id'], title=row['title'],description=row['description'],status=row['status'], **{k:v for k,v in summary(event_id).items() if k in {'total','ready','pending','errors'}})
    cookie='ff_view_'+event_id
    if not request.cookies.get(cookie):
        increment(event_id,'views')
        response.set_cookie(cookie,'1',max_age=86400,httponly=True,samesite='Lax')
    return response


@app.patch('/api/events/<event_id>')
def update_event(event_id):
    admin()
    body=request.get_json(silent=True)
    if not isinstance(body,dict):abort(400)
    fields={}
    for key in ('title','description'):
        if key in body:
            value=body[key];maximum=120 if key=='title' else 2000
            if not isinstance(value,str) or len(value.strip())>maximum or (key=='title' and not value.strip()):
                return jsonify(error='Проверьте название и описание съёмки.'),400
            fields[key]=value.strip()
    if 'status' in body:
        if not isinstance(body['status'],str) or body['status'] not in {'draft','published','paused'}:abort(400)
        fields['status']=body['status']
    if 'detailed' in body:
        if not isinstance(body['detailed'],bool):abort(400)
        fields['detailed']=int(body['detailed'])
    with lock:
        with db() as conn:
            old=event(event_id)
            if fields.get('status')=='published':
                info=summary(event_id)
                if info['pending'] or not info['ready']:return jsonify(error='Сначала загрузите фотографии и дождитесь обработки.'),409
            if fields:
                assignments=','.join(f'{key}=?' for key in fields)
                conn.execute(f'UPDATE events SET {assignments} WHERE id=?',(*fields.values(),event_id))
            changed_detail='detailed' in fields and fields['detailed']!=old['detailed']
        if changed_detail:requeue(event_id)
    return jsonify(ok=True,reindexed=changed_detail)


@app.post('/api/events/<event_id>/rotate-link')
def rotate_link(event_id):
    admin()
    with lock,db() as conn:
        event(event_id)
        key=secrets.token_urlsafe(24)
        conn.execute('UPDATE events SET guest=?,link_version=link_version+1 WHERE id=?',(key,event_id))
    return jsonify(guest=key)


@app.post('/api/events/<event_id>/retry')
def retry(event_id):
    admin();event(event_id)
    return jsonify(queued=requeue(event_id,only_errors=True))


@app.delete('/api/events/<event_id>/photos/<photo_id>')
def delete_photo(event_id,photo_id):
    admin()
    remove_storage(event_id,photo_id)
    return jsonify(ok=True)


@app.post('/api/events/<event_id>/photos')
def upload(event_id):
    admin()
    event(event_id)
    file = request.files.get('photo')
    if not file:
        return jsonify(error='Выберите файл.'), 400
    raw = file.read(25 * 1024 * 1024 + 1)
    if len(raw) > 25 * 1024 * 1024:
        abort(413)
    try:
        image = decode(raw)
    except ValueError as err:
        return jsonify(error=str(err)), 400
    digest = hashlib.sha256(raw).hexdigest()
    filename = Path((file.filename or 'photo.jpg').replace('\\', '/')).name[:150]
    normalized=io.BytesIO()
    image.save(normalized,format='JPEG',quality=95)
    payload=normalized.getvalue()
    path=None
    try:
        with lock, db() as conn:
            event(event_id)
            duplicate = conn.execute('SELECT id FROM photos WHERE event=? AND hash=?', (event_id, digest)).fetchone()
            if duplicate:
                return jsonify(id=duplicate['id'], duplicate=True)
            count, size = conn.execute('SELECT COUNT(*),COALESCE(SUM(size),0) FROM photos WHERE event=?', (event_id,)).fetchone()
            if count >= 5000 or size + len(payload) > 8 * 1024**3:
                return jsonify(error='Лимит съёмки: 5000 фото или 8 ГБ.'), 400
            photo_id = secrets.token_hex(12)
            path = DATA / event_id / (photo_id + '.jpg')
            path.write_bytes(payload)  # strips EXIF; user originals are untouched
            conn.execute('INSERT INTO photos(id,event,name,hash,size,status) VALUES (?,?,?,?,?,?)', (photo_id, event_id, filename, digest, len(payload), 'pending'))
    except Exception:
        if path:path.unlink(missing_ok=True)
        raise
    pool.submit(index_photo, photo_id)
    return jsonify(id=photo_id, duplicate=False), 201


@app.post('/api/events/<event_id>/search')
def search(event_id):
    started=time.perf_counter()
    initial=event(event_id, guest=True)
    if initial['status']!='published':return jsonify(error='Фотограф ещё не открыл поиск для этой съёмки.'),409
    if request.form.get('consent') != 'yes':
        return jsonify(error='Подтвердите обработку селфи для поиска.'), 400
    file = request.files.get('selfie')
    if not file:
        return jsonify(error='Выберите селфи.'), 400
    raw = file.read(10 * 1024 * 1024 + 1)
    if len(raw) > 10 * 1024 * 1024:
        return jsonify(error='Селфи должно быть не больше 10 МБ.'), 400
    try:
        image = decode(raw)
        analysis=analyze(image)
        if len(analysis['faces'])!=1:
            return jsonify(error='На селфи должно быть одно хорошо видимое лицо. Попробуйте другой снимок.'),400
        face=analysis['faces'][0]
        if 'small_face' in face['warnings']:
            return jsonify(error='Лицо слишком маленькое. Выберите селфи, где лицо видно крупнее.'),400
        query=face['vector']
        with lock:
            current=event(event_id, guest=True)
            if current['status']!='published':return jsonify(error='Поиск временно закрыт фотографом.'),409
            progress = summary(event_id)
            if progress['pending'] or not progress['ready']:
                return jsonify(error='Галерея ещё не готова. Подождите завершения обработки.'), 409
            with db() as conn:
                rows = conn.execute('SELECT p.id,p.name,p.width,p.height,f.vector,f.box FROM photos p JOIN faces f ON p.id=f.photo WHERE p.event=? AND p.status=?', (event_id, 'ready')).fetchall()
            best = {}
            for row in rows:
                score = float(np.dot(query, np.frombuffer(row['vector'], dtype=np.float32)))
                if score >= THRESHOLD and (row['id'] not in best or score > best[row['id']]['score']):
                    best[row['id']] = {'id': row['id'], 'name': row['name'], 'score': score,
                        'width': row['width'], 'height': row['height'],
                        'face_box': normalized_face_box(json.loads(row['box']) if row['box'] is not None else None, row['width'], row['height'])}
            matches = sorted(best.values(), key=lambda row: row['score'], reverse=True)
            ticket = make_ticket(event_id,[p['id'] for p in matches],version=current['link_version'])
            for item in matches:
                item.pop('score')
                item['preview'] = photo_url(event_id, item['id'], True,version=current['link_version'])
                item['download'] = photo_url(event_id, item['id'],version=current['link_version']) + '&download=1'
            increment(event_id,'searches')
            return jsonify(photos=matches, zip=f'/api/events/{event_id}/download?ticket={ticket}' if matches else None, ticket=ticket,duration_ms=round((time.perf_counter()-started)*1000),count=len(matches),expires_in=1200)
    except ValueError as err:
        return jsonify(error=str(err)), 400


def access_ticket(event_id,token=None):
    try:
        value = signer.loads(token if token is not None else request.args.get('ticket', ''), max_age=1200)
        if value['event'] != event_id or not isinstance(value['photos'], list):
            abort(403)
        current=event(event_id)
        if value.get('version')!=current['link_version'] or (not value.get('admin') and current['status']!='published'):abort(403)
        return value['photos']
    except (BadSignature, SignatureExpired, KeyError, TypeError):
        abort(403)


@app.get('/media/<event_id>/<photo_id>')
def media(event_id, photo_id):
    with lock, db() as conn:
        if photo_id not in access_ticket(event_id):abort(403)
        row = conn.execute('SELECT * FROM photos WHERE event=? AND id=? AND status=?', (event_id, photo_id, 'ready')).fetchone()
        if not row:
            abort(404)
        path = DATA / event_id / (photo_id + ('-thumb.jpg' if request.args.get('thumb') == '1' else '.jpg'))
        # Close the filesystem handle before sending: deletion must work on Windows
        # even while a client still holds a download response.
        payload = io.BytesIO(path.read_bytes())
        if request.args.get('download')=='1':increment(event_id,'downloads')
        return send_file(payload, mimetype='image/jpeg', as_attachment=request.args.get('download') == '1', download_name=Path(row['name']).stem + '.jpg')


@app.get('/api/events/<event_id>/download')
def download(event_id):
    archive = io.BytesIO()
    with lock, db() as conn:
        ids = access_ticket(event_id)
        if 'ids' in request.args:
            selected_ids=request.args['ids'].split(',')
            if not selected_ids or not set(selected_ids).issubset(set(ids)):abort(403)
            ids=list(dict.fromkeys(selected_ids))
        if not ids:abort(400)
        event(event_id)
        rows = conn.execute('SELECT id,name FROM photos WHERE event=? AND status=?', (event_id, 'ready')).fetchall()
        selected = [row for row in rows if row['id'] in ids]
        if {row['id'] for row in selected}!=set(ids):return jsonify(error='Подборка изменилась. Выполните поиск заново.'),409
        total = sum((DATA / event_id / (row['id'] + '.jpg')).stat().st_size for row in selected)
        if total > 256 * 1024**2:
            return jsonify(error='Подборка больше 256 МБ. Скачивайте фотографии отдельно.'), 413
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_STORED) as zipped:
            for i, row in enumerate(selected, 1):
                zipped.write(DATA / event_id / (row['id'] + '.jpg'), f'{i:03d}_{Path(row["name"]).stem}.jpg')
        increment(event_id,'downloads')
    archive.seek(0)
    return send_file(archive, mimetype='application/zip', as_attachment=True, download_name='my-photos.zip')


@app.post('/api/events/<event_id>/feedback')
def feedback(event_id):
    event(event_id,guest=True)
    body=request.get_json(silent=True)
    if not isinstance(body,dict) or body.get('kind')!='not_me' or not isinstance(body.get('photo_id'),str) or not isinstance(body.get('ticket'),str):abort(400)
    with lock,db() as conn:
        if body['photo_id'] not in access_ticket(event_id,body['ticket']):abort(403)
        if not conn.execute('SELECT id FROM photos WHERE id=? AND event=?',(body['photo_id'],event_id)).fetchone():abort(404)
        conn.execute('INSERT OR IGNORE INTO feedback VALUES (?,?,?,?,?)',(event_id,body['photo_id'],hashlib.sha256(body['ticket'].encode()).hexdigest(),'not_me',time.time()))
    return jsonify(ok=True)


@app.delete('/api/events/<event_id>')
def delete_event(event_id):
    admin()
    remove_storage(event_id)
    return jsonify(ok=True)


def acquire_data_lock():
    handle=(DATA/'.instance.lock').open('a+b')
    if handle.tell()==0:handle.write(b'1');handle.flush()
    handle.seek(0)
    try:
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        return handle
    except OSError:
        handle.close()
        return None

if __name__ == '__main__':
    import argparse
    from waitress import serve
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--open', action='store_true', help='Open the photographer page in your default browser')
    args = parser.parse_args()
    # A second START click reopens this instance instead of colliding on the port.
    import urllib.request
    import urllib.error
    address = f'http://127.0.0.1:{args.port}'
    try:
        probe = urllib.request.Request(address + '/api/events', headers={'X-Admin-Key': CONFIG['admin']})
        with urllib.request.urlopen(probe, timeout=1) as response:
            running = json.load(response)
        if isinstance(running.get('events'), list):
            print(f'FaceFlow already running: {address}/#admin={CONFIG["admin"]}', flush=True)
            if args.open:
                import webbrowser
                webbrowser.open(f'{address}/#admin={CONFIG["admin"]}')
            pool.shutdown(wait=False)
            raise SystemExit(0)
    except (urllib.error.URLError, OSError, ValueError):
        pass
    instance_guard=acquire_data_lock()
    if instance_guard is None:
        print('Another FaceFlow process uses this data folder. Reopen its existing browser tab or stop it first.',flush=True)
        pool.shutdown(wait=False)
        raise SystemExit(1)
    recover_deletions()
    load_models()
    with db() as conn:
        pending = conn.execute("SELECT id FROM photos WHERE status='pending'").fetchall()
    for row in pending:
        pool.submit(index_photo, row['id'])
    print(f'FaceFlow: http://127.0.0.1:{args.port}/#admin={CONFIG["admin"]}', flush=True)
    if args.open:
        import socket
        import webbrowser
        def open_browser():
            for _ in range(100):
                try:
                    with socket.create_connection(('127.0.0.1', args.port), timeout=.2):
                        webbrowser.open(f'http://127.0.0.1:{args.port}/#admin={CONFIG["admin"]}')
                        return
                except OSError:
                    time.sleep(.1)
        threading.Thread(target=open_browser, daemon=True).start()
    try:
        serve(app, host='127.0.0.1', port=args.port, threads=4,
              max_request_body_size=26 * 1024**2, inbuf_overflow=28 * 1024**2)
    finally:
        pool.shutdown(wait=True)
        instance_guard.close()
