"""Seed an isolated synthetic gallery through the real Flask API, no fake matches."""
from pathlib import Path
import os,sys,io,json,time
ROOT=Path(__file__).resolve().parents[1]
os.environ['FACEFLOW_DATA']=str(ROOT/'work/demo-data')
sys.path.insert(0,str(ROOT))
from PIL import Image,ImageEnhance
import app

def jpg(image):
    stream=io.BytesIO();image.convert('RGB').save(stream,format='JPEG',quality=95);return stream.getvalue()

def main():
    client=app.app.test_client();admin={'X-Admin-Key':app.CONFIG['admin']}
    created=client.post('/api/events',headers=admin,json={'title':'Demo Night · синтетическая съемка','description':'Все персонажи вымышленные. Демонстрация интерфейса и поиска на синтетических данных; не проверка точности на реальных событиях.','consent':True})
    if created.status_code!=201:raise RuntimeError(created.get_json())
    eid=created.json['id'];a=Image.open(ROOT/'demo/synthetic/person-a.png');b=Image.open(ROOT/'demo/synthetic/person-b.png')
    images=[('person-a-01.jpg',a),('person-a-02.jpg',ImageEnhance.Brightness(a).enhance(.85)),('person-b-01.jpg',b),('no-face.jpg',Image.new('RGB',(512,512),'#ededdf'))]
    for name,image in images:
        response=client.post('/api/events/'+eid+'/photos',headers=admin,data={'photo':(io.BytesIO(jpg(image)),name)})
        response.request.environ['wsgi.input'].close()
        if response.status_code!=201:raise RuntimeError(response.get_json())
    for _ in range(600):
        event=client.get('/api/events/'+eid,headers=admin).json
        if not event['pending']:break
        time.sleep(.1)
    else:raise RuntimeError('Demo indexing timed out')
    if event['errors']:raise RuntimeError('Demo indexing failed')
    response=client.patch('/api/events/'+eid,headers=admin,json={'status':'published'})
    if response.status_code!=200:raise RuntimeError(response.get_json())
    session={'event_id':eid,'admin_url':'http://127.0.0.1:8766/#admin='+app.CONFIG['admin'],'guest_url':'http://127.0.0.1:8766/e/'+eid+'#g='+event['guest'],'data_path':str(app.DATA)}
    (ROOT/'work').mkdir(exist_ok=True)
    (ROOT/'work/demo-session.json').write_text(json.dumps(session,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Synthetic gallery ready. Local session URLs: work/demo-session.json (never commit).')
    print('FACEFLOW_DATA:',app.DATA)

if __name__=='__main__':
    try:main()
    finally:app.pool.shutdown(wait=True)
