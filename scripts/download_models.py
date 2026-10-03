"""Download pinned OpenCV Zoo weights and verify exact length + SHA-256."""
from pathlib import Path
import hashlib,json,urllib.request

ROOT=Path(__file__).resolve().parents[1]

def main():
    manifest=json.loads((ROOT/'models/manifest.json').read_text(encoding='utf-8'))
    for item in manifest['models']:
        target=ROOT/'models'/item['file']
        if target.exists() and len(target.read_bytes())==item['bytes'] and hashlib.sha256(target.read_bytes()).hexdigest()==item['sha256']:
            print(item['file'],'verified');continue
        print('Downloading',item['file'])
        request=urllib.request.Request(item['source'],headers={'User-Agent':'FaceFlow-model-setup'})
        with urllib.request.urlopen(request,timeout=120) as response:payload=response.read(item['bytes']+1)
        if len(payload)!=item['bytes'] or hashlib.sha256(payload).hexdigest()!=item['sha256']:
            raise RuntimeError('Unexpected model content: '+item['file'])
        temporary=target.with_suffix('.download')
        temporary.write_bytes(payload);temporary.replace(target)
        print(item['file'],'verified')

if __name__=='__main__':main()
