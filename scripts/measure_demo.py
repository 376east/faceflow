"""Measure the bundled synthetic demo over local HTTP; never a human accuracy benchmark."""
import argparse
import ctypes
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import io
import json
import math
import os
from pathlib import Path
import platform
import statistics
import subprocess
import tempfile
import threading
import time
import urllib.request
import uuid

from seed_demo import ROOT, import_app, load_dataset


def memory_usage():
    if os.name != 'nt':
        import resource
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return {'peak_working_set_bytes': peak * (1 if platform.system() == 'Darwin' else 1024)}
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_ = [('cb', wintypes.DWORD), ('faults', wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in ('peak', 'working', 'peak_paged', 'paged',
                'peak_nonpaged', 'nonpaged', 'pagefile', 'peak_pagefile')]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    get_handle = ctypes.windll.kernel32.GetCurrentProcess
    get_handle.restype = wintypes.HANDLE
    get_memory = ctypes.windll.psapi.GetProcessMemoryInfo
    get_memory.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    if not get_memory(get_handle(), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError()
    return {'working_set_bytes': counters.working, 'peak_working_set_bytes': counters.peak}


def hardware():
    result = {'os': platform.platform(), 'cpu': platform.processor(), 'logical_cpus': os.cpu_count()}
    if os.name == 'nt':
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:
            result['cpu'] = winreg.QueryValueEx(key, 'ProcessorNameString')[0].strip()
        class MemoryStatus(ctypes.Structure):
            _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [
                (name, ctypes.c_ulonglong) for name in ('total', 'available', 'page_total',
                    'page_available', 'virtual_total', 'virtual_available', 'extended')]
        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            raise ctypes.WinError()
        result['physical_ram_bytes'] = status.total
    return result


def stats(values):
    ordered = sorted(values)
    return {'samples': len(values), 'min': min(values), 'median': statistics.median(values),
            'mean': statistics.mean(values), 'p95_nearest_rank': ordered[math.ceil(.95 * len(values))-1],
            'max': max(values)}


def snapshot():
    cpu = os.times()
    return time.perf_counter(), cpu.user + cpu.system


def elapsed(start):
    wall, cpu = snapshot()
    wall -= start[0]
    cpu -= start[1]
    return {'wall_seconds': wall, 'process_cpu_seconds': cpu,
            'process_cpu_percent_one_logical_core': 100 * cpu / wall, **memory_usage()}


def multipart(field, raw, filename, consent=False):
    boundary = 'faceflow-' + uuid.uuid4().hex
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
            'Content-Type: image/jpeg\r\n\r\n').encode() + raw + b'\r\n'
    if consent:
        body += f'--{boundary}\r\nContent-Disposition: form-data; name="consent"\r\n\r\nyes\r\n'.encode()
    return body + f'--{boundary}--\r\n'.encode(), 'multipart/form-data; boundary=' + boundary


def source_hashes():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in ('app.py', 'recognition.py', 'scripts/seed_demo.py', 'scripts/measure_demo.py')}


def measure(data_path, port, timeout, repeats):
    from waitress import create_server, wasyncore
    source_before = source_hashes()
    setup = snapshot()
    dataset = load_dataset()
    module = import_app(data_path)
    if module.THRESHOLD != .60:
        module.pool.shutdown(wait=True)
        raise RuntimeError('Benchmark requires unchanged threshold 0.60')
    server = None
    thread = None
    try:
        server = create_server(module.app, host='127.0.0.1', port=port, threads=4,
                               map={}, asyncore_loop_timeout=.1)
        thread = threading.Thread(target=server.run, name='benchmark-http', daemon=True)
        thread.start()
        base = 'http://127.0.0.1:' + str(server.effective_port)
        # Ignore proxy environment variables for this loopback-only measurement.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        def call(method, path, headers=None, payload=None, upload=None):
            headers = dict(headers or {})
            if upload is not None:
                payload, headers['Content-Type'] = multipart(*upload)
            elif payload is not None:
                payload = json.dumps(payload).encode()
                headers['Content-Type'] = 'application/json'
            with opener.open(urllib.request.Request(base+path, data=payload, headers=headers, method=method), timeout=timeout) as response:
                return json.load(response)
        report = {'measured_at_utc': datetime.now(timezone.utc).isoformat(),
            'git_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
            'source_sha256': source_before, 'hardware': hardware(),
            'backend': {'http': 'Waitress', 'application': 'Flask', 'inference': 'OpenCV CPU YuNet/SFace',
                'python': platform.python_version(), 'packages': {name: version(name) for name in
                    ('waitress', 'flask', 'opencv-python-headless', 'numpy', 'pillow')},
                'opencv_threads': module.cv2.getNumThreads(), 'index_workers': 1, 'http_threads': 4,
                'port': int(server.effective_port), 'threshold': module.THRESHOLD,
                'models': json.loads((ROOT/'models/manifest.json').read_text())},
            'dataset': {'source': 'bundled synthetic manifest-v2', 'photos': len(dataset['photos']),
                'selfies': len(dataset['selfies']), 'photo_input_bytes': sum(len(p['raw']) for p in dataset['photos']),
                'selfie_input_bytes': sum(map(len, dataset['selfies'].values())),
                'manifest_sha256': hashlib.sha256((ROOT/'tests/fixtures/event-manifest.json').read_bytes()).hexdigest()},
            'human_accuracy': 'NOT_ASSESSED', 'setup': elapsed(setup)}
        admin = {'X-Admin-Key': module.CONFIG['admin']}
        started = snapshot()
        eid = call('POST', '/api/events', admin, {'title': dataset['title'], 'consent': True})['id']
        path = '/api/events/' + eid
        for photo in dataset['photos']:
            call('POST', path+'/photos', admin, upload=('photo', photo['raw'], photo['name']))
        deadline = time.monotonic() + timeout
        while True:
            event = call('GET', path, admin)
            if not event['pending']:
                break
            if time.monotonic() >= deadline:
                raise TimeoutError('Indexing deadline exceeded')
            time.sleep(.05)
        report['indexing'] = elapsed(started)
        if event['errors'] or event['ready'] != len(dataset['photos']):
            raise RuntimeError('Not all input photos indexed successfully')
        report['indexing']['photos_per_wall_second'] = event['ready']/report['indexing']['wall_seconds']
        report['readiness'] = {key: event[key] for key in ('total','ready','errors','pending','faces','no_faces')}
        with module.db() as conn:
            times = [row[0] for row in conn.execute('SELECT duration_ms FROM photos WHERE event=?',(eid,))]
        report['indexing']['per_photo_inference_ms'] = stats(times)
        call('PATCH', path, admin, {'status': 'published'})
        guest = {'X-Guest-Key': event['guest']}
        started = snapshot()
        searches = []
        for repeat in range(repeats):
            for identity, raw in dataset['selfies'].items():
                begin = time.perf_counter()
                result = call('POST', path+'/search', guest, upload=('selfie',raw,'selfie.jpg',True))
                searches.append({'identity': identity, 'repeat': repeat+1, 'api_duration_ms': result['duration_ms'],
                    'http_wall_ms': (time.perf_counter()-begin)*1000, 'returned_photos': result['count']})
        report['search'] = {**elapsed(started), 'queries': searches,
            'api_duration_ms': stats([s['api_duration_ms'] for s in searches]),
            'http_wall_ms': stats([s['http_wall_ms'] for s in searches])}
        files = [p for p in data_path.rglob('*') if p.is_file()]
        report['disk'] = {'logical_bytes': sum(p.stat().st_size for p in files), 'files': len(files),
            'normalized_jpeg_bytes': sum(p.stat().st_size for p in files if p.suffix=='.jpg' and not p.stem.endswith('-thumb')),
            'thumbnail_bytes': sum(p.stat().st_size for p in files if p.stem.endswith('-thumb'))}
        report['source_unchanged_during_run'] = source_before == source_hashes()
        return report
    finally:
        module.pool.shutdown(wait=True)
        if server is not None:
            server.task_dispatcher.shutdown()
            wasyncore.close_all(map=server._map)
        if thread is not None:
            thread.join(timeout=5)
            if thread.is_alive():
                raise RuntimeError('Benchmark HTTP thread did not stop')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--port', type=int, default=0, help='Dedicated loopback port; 0 selects a free port')
    parser.add_argument('--timeout', type=float, default=300)
    parser.add_argument('--repeats', type=int, default=3)
    args = parser.parse_args()
    if args.timeout <= 0 or args.repeats < 1 or not 0 <= args.port <= 65535:
        parser.error('timeout/repeats must be positive and port must be 0..65535')
    args.work_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='benchmark-', dir=args.work_dir) as directory:
        report = measure(Path(directory), args.port, args.timeout, args.repeats)
    report['isolated_data_removed'] = True
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Benchmark report: {args.report}; human_accuracy=NOT_ASSESSED')


if __name__ == '__main__':
    main()
