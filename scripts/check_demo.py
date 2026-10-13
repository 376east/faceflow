"""Assess synthetic selfie search and downloads through normal Flask routes."""
import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import tempfile
import zipfile

from PIL import Image
from seed_demo import ROOT, import_app, load_dataset, require, seed


def decode_jpeg(raw):
    with Image.open(io.BytesIO(raw)) as image:
        if image.format != 'JPEG':
            raise RuntimeError('Download is not JPEG')
        image.load()


def assess(module, dataset, timeout):
    if module.THRESHOLD != .60:
        raise RuntimeError('Assessment requires unchanged product threshold 0.60')
    client, eid, event = seed(module, dataset, timeout)
    report = {'source': dataset['source'], 'threshold': module.THRESHOLD,
              'readiness': {key: event[key] for key in ('total', 'ready', 'pending', 'errors', 'faces', 'no_faces')},
              'identities': {}, 'downloads': {'jpeg': 0, 'zip': 0, 'zip_entries': 0}}
    for identity, raw in dataset['selfies'].items():
        expected = {photo['name'] for photo in dataset['photos'] if identity in photo['people']}
        response = client.post(f'/api/events/{eid}/search', headers={'X-Guest-Key': event['guest']},
                               data={'selfie': (io.BytesIO(raw), 'selfie.jpg'), 'consent': 'yes'})
        try:
            result = require(response, 200)
        finally:
            response.request.environ['wsgi.input'].close()
        actual = {photo['name'] for photo in result['photos']}
        if len(actual) != result['count'] or len(actual) != len(result['photos']):
            raise RuntimeError('Search count or photo names are inconsistent')
        tp, fp, fn = expected & actual, actual - expected, expected - actual
        report['identities'][identity] = {'expected': sorted(expected), 'returned': sorted(actual),
            'TP': len(tp), 'FP': len(fp), 'FN': len(fn), 'true_positives': sorted(tp),
            'false_positives': sorted(fp), 'false_negatives': sorted(fn)}
        downloaded = Counter()
        for photo in result['photos']:
            jpeg = client.get(photo['download'])
            if jpeg.status_code != 200 or jpeg.mimetype != 'image/jpeg':
                raise RuntimeError('JPEG download failed')
            decode_jpeg(jpeg.data)
            downloaded[(Path(photo['name']).stem + '.jpg', hashlib.sha256(jpeg.data).hexdigest())] += 1
            report['downloads']['jpeg'] += 1
            jpeg.close()
        if actual:
            archive = client.get(result['zip'])
            if archive.status_code != 200 or archive.mimetype != 'application/zip':
                raise RuntimeError('ZIP download failed')
            with zipfile.ZipFile(io.BytesIO(archive.data)) as zipped:
                entries = zipped.namelist()
                if zipped.testzip() is not None or len(entries) != len(actual):
                    raise RuntimeError('ZIP corruption or entry count mismatch')
                contents = Counter()
                for name in entries:
                    payload = zipped.read(name)
                    decode_jpeg(payload)
                    contents[(name.split('_', 1)[1], hashlib.sha256(payload).hexdigest())] += 1
                if contents != downloaded:
                    raise RuntimeError('ZIP contents differ from returned JPEGs')
            report['downloads']['zip'] += 1
            report['downloads']['zip_entries'] += len(entries)
            archive.close()
        elif result['zip'] is not None:
            raise RuntimeError('Empty search unexpectedly returned a ZIP')
    report['perfect_manifest_match'] = all(not item['FP'] and not item['FN'] for item in report['identities'].values())
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeout', type=float, default=300)
    parser.add_argument('--report', type=Path, default=ROOT / 'work/demo-assessment.json')
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error('--timeout must be positive')
    dataset = load_dataset()
    (ROOT / 'work').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='demo-check-', dir=ROOT / 'work') as data_path:
        module = import_app(data_path)
        try:
            report = assess(module, dataset, args.timeout)
        finally:
            module.pool.shutdown(wait=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    ready = report['readiness']
    print(f'Ready {ready["ready"]}/{ready["total"]}, errors {ready["errors"]}; report: {args.report}')
    for identity, item in report['identities'].items():
        print(f'{identity}: TP={item["TP"]} FP={item["FP"]} FN={item["FN"]}')
    return 0 if report['perfect_manifest_match'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
