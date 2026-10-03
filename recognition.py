"""Local YuNet/SFace inference, with thread-local networks and multi-scale detection."""
from pathlib import Path
import hashlib
import json
import threading
import time
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
local = threading.local()
verified = False
verify_lock = threading.Lock()


def verify_models():
    global verified
    with verify_lock:
        if not verified:
            manifest = json.loads((ROOT / 'models' / 'manifest.json').read_text())
            for item in manifest['models']:
                if hashlib.sha256((ROOT / 'models' / item['file']).read_bytes()).hexdigest() != item['sha256']:
                    raise RuntimeError('Model checksum mismatch: ' + item['file'])
            verified = True


def engine():
    verify_models()
    if not hasattr(local, 'networks'):
        local.networks = (
            cv2.FaceDetectorYN.create(str(ROOT / 'models' / 'face_detection_yunet_2023mar.onnx'), '', (320, 320), .8, .3, 5000),
            cv2.FaceRecognizerSF.create(str(ROOT / 'models' / 'face_recognition_sface_2021dec.onnx'), ''),
        )
    return local.networks


def overlap(a, b):
    x=max(a[0],b[0]);y=max(a[1],b[1])
    w=max(0,min(a[0]+a[2],b[0]+b[2])-x)
    h=max(0,min(a[1]+a[3],b[1]+b[3])-y)
    intersection=w*h
    return intersection/max(1,a[2]*a[3]+b[2]*b[3]-intersection)


def analyze(image, detailed=False):
    """All vectors share SFace's feature space; boxes refer to original pixels."""
    started=time.perf_counter()
    detector,recognizer=engine()
    rgb=np.asarray(image.convert('RGB'))
    original=cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR)
    h,w=original.shape[:2]
    candidates=[]

    def detect_region(region, offset_x=0, offset_y=0, max_side=1800):
        rh,rw=region.shape[:2]
        scale=min(max_side/max(rw,rh),1)
        if max(rw,rh)<512:
            scale=512/max(rw,rh)
        resized=cv2.resize(region,(max(32,round(rw*scale)),max(32,round(rh*scale))))
        sx=resized.shape[1]/rw;sy=resized.shape[0]/rh
        detector.setInputSize((resized.shape[1],resized.shape[0]))
        _,found=detector.detect(resized)
        if found is not None:
            for face in found:
                mapped=face.copy()
                mapped[[0,2,4,6,8,10,12]]/=sx
                mapped[[1,3,5,7,9,11,13]]/=sy
                mapped[[0,4,6,8,10,12]]+=offset_x
                mapped[[1,5,7,9,11,13]]+=offset_y
                if min(mapped[2:4])>=16:
                    candidates.append(mapped)

    detect_region(original)
    if detailed and max(w,h)>1800:
        # Overlapping tiles preserve small faces otherwise lost in downscaling.
        tile=1200;step=900
        xs=list(range(0,max(1,w-tile+1),step));ys=list(range(0,max(1,h-tile+1),step))
        if w>tile and xs[-1]!=w-tile:xs.append(w-tile)
        if h>tile and ys[-1]!=h-tile:ys.append(h-tile)
        for y in ys:
            for x in xs:
                detect_region(original[y:min(y+tile,h),x:min(x+tile,w)],x,y,1200)
    selected=[]
    for face in sorted(candidates,key=lambda f:float(f[14]),reverse=True):
        if not any(overlap(face,existing)>.35 for existing in selected):
            selected.append(face)
    output=[]
    for face in selected:
        aligned=recognizer.alignCrop(original,face)
        vector=recognizer.feature(aligned).flatten().astype(np.float32)
        norm=np.linalg.norm(vector)
        if norm<=0 or not np.isfinite(vector).all():continue
        warnings=[]
        size=float(min(face[2:4]))
        sharpness=float(cv2.Laplacian(cv2.cvtColor(aligned,cv2.COLOR_BGR2GRAY),cv2.CV_64F).var())
        if size<48:warnings.append('small_face')
        if sharpness<35:warnings.append('blurred_face')
        output.append({'vector':vector/norm,'box':[round(float(x),1) for x in face[:4]],
                       'confidence':float(face[14]),'sharpness':round(sharpness,1),'warnings':warnings})
    return {'faces':output,'width':w,'height':h,'duration_ms':round((time.perf_counter()-started)*1000)}
