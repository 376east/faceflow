"""Seed an isolated demo gallery through the real Flask API."""
import argparse
import io
import json
import os
from pathlib import Path
import sys
import time
from PIL import Image, ImageEnhance

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'demo/synthetic'


def jpg(image):
    stream = io.BytesIO()
    image.convert('RGB').save(stream, format='JPEG', quality=95)
    return stream.getvalue()


def load_dataset(directory=None):
    fixtures = (Path(directory) if directory is not None else FIXTURES).resolve()
    manifest_path = fixtures / 'event-manifest.json'
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        if manifest.get('version') != 2 or not manifest.get('photos') or not manifest.get('selfies'):
            raise ValueError('Expected version 2 event manifest with photos and selfies')
        if 'description' in manifest and not isinstance(manifest['description'], str):
            raise ValueError('Manifest description must be a string')

        def read(relative):
            path = (fixtures / relative).resolve()
            if not path.is_relative_to(fixtures):
                raise ValueError('Manifest path must stay inside the dataset directory')
            return path.read_bytes()

        selfies = {identity: read(path) for identity, path in manifest['selfies'].items()}
        photos = []
        names = set()
        for item in manifest['photos']:
            name = Path(item['file']).name
            people = item['people']
            if name in names or not isinstance(people, list) or not set(people).issubset(selfies):
                raise ValueError('Photo names must be unique and people must have selfies')
            names.add(name)
            photo = {'name': name, 'people': people, 'raw': read(item['file'])}
            for field in ('scenario', 'difficulty'):
                if field in item:
                    if not isinstance(item[field], str) or not item[field].strip():
                        raise ValueError(f'Photo {field} must be a nonempty string')
                    photo[field] = item[field]
            photos.append(photo)
        dataset = {'title': manifest['title'], 'photos': photos, 'selfies': selfies, 'source': 'manifest-v2'}
        if 'description' in manifest:
            dataset['description'] = manifest['description']
        return dataset
    with Image.open(fixtures / 'person-a.png') as a, Image.open(fixtures / 'person-b.png') as b:
        return {'title': 'Demo Night · синтетическая съемка', 'source': 'legacy-fixtures',
                'selfies': {'person-a': jpg(a), 'person-b': jpg(b)},
                'photos': [
                    {'name': 'person-a-01.jpg', 'people': ['person-a'], 'raw': jpg(a)},
                    {'name': 'person-a-02.jpg', 'people': ['person-a'], 'raw': jpg(ImageEnhance.Brightness(a).enhance(.85))},
                    {'name': 'person-b-01.jpg', 'people': ['person-b'], 'raw': jpg(b)},
                    {'name': 'no-face.jpg', 'people': [], 'raw': jpg(Image.new('RGB', (512, 512), '#ededdf'))}]}


def import_app(data_path):
    # Ignore inherited FACEFLOW_DATA: demo commands never use real galleries.
    os.environ['FACEFLOW_DATA'] = str(data_path)
    sys.path.insert(0, str(ROOT))
    import app
    return app


def require(response, status):
    if response.status_code != status:
        raise RuntimeError(f'API returned {response.status_code}, expected {status}: {response.get_json()}')
    return response.get_json()


def seed(module, dataset, timeout=300, empty=False):
    client = module.app.test_client()
    admin = {'X-Admin-Key': module.CONFIG['admin']}
    eid = require(client.post('/api/events', headers=admin, json={
        'title': dataset['title'], 'description': dataset.get('description', 'Все персонажи вымышленные. Демонстрация поиска на синтетических данных; не оценка точности на реальных событиях.'),
        'consent': True}), 201)['id']
    if not empty:
        for photo in dataset['photos']:
            response = client.post(f'/api/events/{eid}/photos', headers=admin,
                                   data={'photo': (io.BytesIO(photo['raw']), photo['name'])})
            try:
                require(response, 201)
            finally:
                response.request.environ['wsgi.input'].close()
        deadline = time.monotonic() + timeout
        while True:
            event = require(client.get(f'/api/events/{eid}', headers=admin), 200)
            if not event['pending']:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError('Demo indexing timed out')
            time.sleep(.1)
        if event['errors'] or event['ready'] != len(dataset['photos']):
            raise RuntimeError('Demo indexing failed or photo count differs')
        require(client.patch(f'/api/events/{eid}', headers=admin, json={'status': 'published'}), 200)
    event = require(client.get(f'/api/events/{eid}', headers=admin), 200)
    return client, eid, event


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--empty', action='store_true', help='Create a draft session without uploading photos')
    parser.add_argument('--timeout', type=float, default=300, help='Indexing deadline in seconds')
    parser.add_argument('--dataset', type=Path, help='Dataset directory (default: demo/synthetic)')
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error('--timeout must be positive')
    dataset = {'title': 'Demo Night · синтетическая съемка'} if args.empty and args.dataset is None else load_dataset(args.dataset)
    module = import_app(ROOT / 'work/demo-data')
    try:
        _, eid, event = seed(module, dataset, args.timeout, args.empty)
        session = {'event_id': eid, 'admin_url': 'http://127.0.0.1:8766/#admin=' + module.CONFIG['admin'],
                   'guest_url': f'http://127.0.0.1:8766/e/{eid}#g=' + event['guest'], 'data_path': str(module.DATA)}
        (ROOT / 'work/demo-session.json').write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'Demo gallery: {event["ready"]}/{event["total"]} ready, {event["errors"]} errors.')
        print('Local session URLs: work/demo-session.json (never commit).')
    finally:
        module.pool.shutdown(wait=True)


if __name__ == '__main__':
    main()
