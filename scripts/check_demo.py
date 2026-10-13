"""Assess demo selfie search and downloads through normal Flask routes."""
import argparse
from collections import Counter
import hashlib
import io
import json
import math
from pathlib import Path
import statistics
import tempfile
import zipfile

from PIL import Image
from seed_demo import ROOT, import_app, load_dataset, require, seed


def decode_jpeg(raw):
    with Image.open(io.BytesIO(raw)) as image:
        if image.format != 'JPEG':
            raise RuntimeError('Download is not JPEG')
        image.load()


def metrics(tp, fp, fn):
    return {'TP': tp, 'FP': fp, 'FN': fn,
            'precision': tp / (tp + fp) if tp + fp else None,
            'recall': tp / (tp + fn) if tp + fn else None}


def summarize(identities):
    enrolled = [item for item in identities.values() if item['enrolled']]
    negatives = [item for item in identities.values() if not item['enrolled']]
    aggregate = metrics(*(sum(item[key] for item in enrolled) for key in ('TP', 'FP', 'FN')))
    for key in ('precision', 'recall'):
        values = [item[key] for item in enrolled if item[key] is not None]
        aggregate['macro_' + key] = statistics.mean(values) if values else None
    durations = sorted(item['duration_ms'] for item in identities.values())
    return {'queries': len(identities), 'metric_unit': 'query-photo pair',
            'undefined_ratios': 'null; excluded from macro averages',
            'enrolled': {'queries': len(enrolled), **aggregate},
            'nonenrolled': {'queries': len(negatives),
                'false_positive_queries': sum(bool(item['FP']) for item in negatives),
                'false_positive_photos': sum(item['FP'] for item in negatives),
                'correct_empty_searches': sum(not item['returned'] for item in negatives)},
            'latency_ms': {'source': 'API duration_ms', 'samples': len(durations),
                'min': min(durations) if durations else None,
                'median': statistics.median(durations) if durations else None,
                'mean': statistics.mean(durations) if durations else None,
                'p95': durations[math.ceil(.95 * len(durations)) - 1] if durations else None,
                'max': max(durations) if durations else None,
                'p95_method': 'nearest rank'}}


def assess(module, dataset, timeout):
    if module.THRESHOLD != .60:
        raise RuntimeError('Assessment requires unchanged product threshold 0.60')
    client, eid, event = seed(module, dataset, timeout)
    report = {'source': dataset['source'], 'threshold': module.THRESHOLD,
              'readiness': {key: event[key] for key in ('total', 'ready', 'pending', 'errors', 'faces', 'no_faces')},
              'identities': {}, 'downloads': {'jpeg': 0, 'zip': 0, 'zip_entries': 0},
              'breakdown': {'scenario': {}, 'difficulty': {}}}
    annotations = {photo['name']: photo for photo in dataset['photos']}
    for field, groups in report['breakdown'].items():
        for photo in dataset['photos']:
            groups.setdefault(photo.get(field, 'unannotated'), {'TP': 0, 'FP': 0, 'FN': 0})
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
            **metrics(len(tp), len(fp), len(fn)), 'enrolled': bool(expected),
            'duration_ms': result['duration_ms'], 'true_positives': sorted(tp),
            'false_positives': sorted(fp), 'false_negatives': sorted(fn)}
        for field, groups in report['breakdown'].items():
            for key, names in (('TP', tp), ('FP', fp), ('FN', fn)):
                for name in names:
                    label = annotations.get(name, {}).get(field, 'unannotated')
                    groups.setdefault(label, {'TP': 0, 'FP': 0, 'FN': 0})[key] += 1
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
    report['summary'] = summarize(report['identities'])
    report['perfect_manifest_match'] = all(not item['FP'] and not item['FN'] for item in report['identities'].values())
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeout', type=float, default=300)
    parser.add_argument('--report', type=Path, default=ROOT / 'work/demo-assessment.json')
    parser.add_argument('--dataset', type=Path, help='Dataset directory (default: demo/synthetic)')
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error('--timeout must be positive')
    dataset = load_dataset(args.dataset)
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
        print(f'{identity}: TP={item["TP"]} FP={item["FP"]} FN={item["FN"]} '
              f'precision={item["precision"]} recall={item["recall"]} duration_ms={item["duration_ms"]}')
    print(json.dumps(report['summary'], ensure_ascii=False))
    if not report['perfect_manifest_match']:
        print('Manifest mismatch: report preserved; exit status 1 (threshold and labels unchanged).')
    return 0 if report['perfect_manifest_match'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
