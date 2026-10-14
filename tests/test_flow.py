"""Actual OpenCV inference with synthetic fixtures; this is not an accuracy benchmark."""
import importlib.util
import io
import os
import sys
from pathlib import Path
import tempfile
import time
import unittest
import zipfile
import threading
from unittest.mock import patch
from PIL import Image, ImageEnhance

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
FIXTURES = Path(os.environ.get('FACEFLOW_FIXTURES', str(ROOT / 'demo' / 'synthetic')))
temporary = tempfile.TemporaryDirectory(prefix='faceflow-check-')
os.environ['FACEFLOW_DATA'] = temporary.name
spec = importlib.util.spec_from_file_location('faceflow_test_app', ROOT / 'app.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def jpg(image):
    result = io.BytesIO()
    image.convert('RGB').save(result, format='JPEG', quality=95)
    return result.getvalue()


class Flow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = module.app.test_client()
        cls.admin = {'X-Admin-Key': module.CONFIG['admin']}
        cls.alpha = Image.open(FIXTURES / 'person-a.png').convert('RGB').resize((512,512))
        cls.beta = Image.open(FIXTURES / 'person-b.png').convert('RGB').resize((512,512))
        with module.lock:
            cls.alpha_vector = module.features(cls.alpha)
            cls.beta_vector = module.features(cls.beta)
        print('Detected reference faces:', len(cls.alpha_vector), len(cls.beta_vector), flush=True)
        assert len(cls.alpha_vector) == len(cls.beta_vector) == 1

    @classmethod
    def tearDownClass(cls):
        module.pool.shutdown(wait=True)
        temporary.cleanup()

    def create(self, title='Integration event'):
        response = self.client.post('/api/events', headers=self.admin, json={'title':title, 'consent':True})
        self.assertEqual(response.status_code, 201)
        event_id = response.json['id']
        info = self.client.get('/api/events/' + event_id, headers=self.admin).json
        return event_id, {'X-Guest-Key':info['guest']}

    def upload(self, event_id, raw, name='photo.jpg'):
        response=self.client.post('/api/events/'+event_id+'/photos',headers=self.admin,data={'photo':(io.BytesIO(raw),name)})
        response.request.environ['wsgi.input'].close()
        return response

    def wait(self, event_id):
        for _ in range(150):
            response = self.client.get('/api/events/'+event_id,headers=self.admin).json
            if not response['pending']:
                if response['ready']:
                    published=self.client.patch('/api/events/'+event_id,headers=self.admin,json={'status':'published'})
                    self.assertEqual(published.status_code,200)
                return response
            time.sleep(.1)
        self.fail('Indexing timed out')

    def search(self, event_id, guest, image, consent='yes'):
        return self.client.post('/api/events/'+event_id+'/search',headers=guest,data={'selfie':(io.BytesIO(jpg(image)),'selfie.jpg'),'consent':consent})

    def test_large_closeup_selfie_is_found(self):
        import recognition
        eid, guest = self.create('Large closeup')
        self.assertEqual(self.upload(eid, jpg(self.alpha)).status_code, 201)
        self.wait(eid)
        x, y, width, height = recognition.analyze(self.alpha)['faces'][0]['box']
        closeup = self.alpha.crop((x-width*.15, y-height*.2, x+width*1.15, y+height*1.25))
        scale = 1066 / closeup.height
        closeup = closeup.resize((round(closeup.width * scale), 1066))
        result = self.search(eid, guest, closeup)
        self.assertEqual(result.status_code, 200, result.json)
        self.assertEqual(result.json['count'], 1)
        blank = self.search(eid, guest, Image.new('RGB', closeup.size, '#eee'))
        self.assertEqual(blank.status_code, 400)

    def test_01_real_search_download_and_isolation(self):
        eid, guest = self.create()
        other, other_guest = self.create('Unrelated event')
        canvas = Image.new('RGB',(1024,600),'#eee')
        canvas.paste(self.alpha,(0,44))
        beta_small = self.beta.copy();beta_small.thumbnail((512,600));canvas.paste(beta_small,(512,0))
        data = jpg(canvas)
        response = self.upload(eid,data,'group.jpg');self.assertEqual(response.status_code,201)
        group_id = response.json['id']
        duplicate=self.upload(eid,data);self.assertTrue(duplicate.json['duplicate'])
        self.assertEqual(self.upload(eid,jpg(self.beta),'person-b.jpg').status_code,201)
        self.assertEqual(self.upload(eid,jpg(Image.new('RGB',(512,512),'white')),'blank.jpg').status_code,201)
        self.assertEqual(self.upload(other,jpg(self.alpha),'other-event.jpg').status_code,201)
        info=self.wait(eid);self.wait(other)
        self.assertEqual(info['total'],3);self.assertEqual(info['errors'],0);self.assertGreaterEqual(info['faces'],3)
        query=ImageEnhance.Brightness(self.alpha).enhance(.85)
        files_before=sorted(str(p.relative_to(module.DATA)) for p in module.DATA.rglob('*') if p.is_file())
        result=self.search(eid,guest,query);self.assertEqual(result.status_code,200)
        files_after=sorted(str(p.relative_to(module.DATA)) for p in module.DATA.rglob('*') if p.is_file())
        self.assertEqual(files_before,files_after)
        self.assertEqual([p['id'] for p in result.json['photos']],[group_id])
        photo=result.json['photos'][0]
        self.assertEqual(self.client.get(photo['preview']).status_code,200)
        downloaded=self.client.get(photo['download']);self.assertEqual(downloaded.status_code,200)
        self.assertIn('attachment',downloaded.headers['Content-Disposition'])
        archive=self.client.get(result.json['zip']);self.assertEqual(archive.status_code,200)
        with zipfile.ZipFile(io.BytesIO(archive.data)) as zipped:
            self.assertEqual(len(zipped.namelist()),1)
            self.assertTrue(zipped.namelist()[0].endswith('group.jpg'))
        self.assertEqual(self.client.get(f'/media/{eid}/{group_id}').status_code,403)
        self.assertEqual(self.client.get(photo['download'].replace(eid,other)).status_code,403)
        self.assertEqual(self.client.get('/api/events/'+eid,headers=other_guest).status_code,403)
        self.assertEqual(self.client.get('/api/events/'+eid,headers=guest).json.get('photos'),None)
        self.assertEqual(self.search(eid,guest,canvas).status_code,400)
        self.assertEqual(self.search(eid,guest,Image.new('RGB',(512,512),'white')).status_code,400)
        self.assertEqual(self.search(eid,guest,self.alpha,consent='no').status_code,400)
        self.assertEqual(self.client.get('/api/events',headers=guest).status_code,403)
        self.assertEqual(self.client.delete('/api/events/'+eid,headers=guest).status_code,403)
        self.assertEqual(self.client.delete('/api/events/'+eid,headers=self.admin).status_code,200)
        self.assertEqual(self.client.get(photo['download']).status_code,404)
        self.assertEqual(self.client.get('/api/events/'+other,headers=other_guest).status_code,200)
        self.assertFalse((module.DATA/eid).exists())
        self.assertEqual(self.client.delete('/api/events/'+other,headers=self.admin).status_code,200)

    def test_02_input_validation_and_consent(self):
        context=module.app.test_request_context('/upload', method='POST', data={'selfie':(io.BytesIO(b'x'*800_000),'large.jpg')})
        with context:
            self.assertIsInstance(module.request.files['selfie'].stream,io.BytesIO)
        context.request.environ['wsgi.input'].close()
        self.assertEqual(self.client.post('/api/events',headers=self.admin,json={'title':'x'}).status_code,400)
        self.assertEqual(self.client.post('/api/events',json={'title':'x','consent':True}).status_code,403)
        self.assertEqual(self.client.post('/api/events',headers=self.admin,json={'title':42,'consent':True}).status_code,400)
        eid,guest=self.create()
        self.assertEqual(self.upload(eid,b'not a jpeg').status_code,400)
        self.assertEqual(self.search(eid,guest,self.alpha).status_code,409)
        self.assertEqual(self.upload(eid,(FIXTURES/'person-a.png').read_bytes(),'accepted.png').status_code,201)
        self.wait(eid)
        self.assertEqual(self.upload(eid,b'x'*(25*1024*1024+1)).status_code,413)
        self.assertEqual(self.client.delete('/api/events/'+eid,headers=self.admin).status_code,200)

    def test_03_model_reference_similarity(self):
        import numpy as np
        with module.lock:
            variant=module.features(ImageEnhance.Contrast(self.alpha).enhance(.8))[0]
        positive=float(np.dot(self.alpha_vector[0],variant));negative=float(np.dot(self.alpha_vector[0],self.beta_vector[0]))
        print(f'Cosine smoke test: same source transformed={positive:.4f}, different person={negative:.4f}, threshold={module.THRESHOLD}',flush=True)
        self.assertGreater(positive,module.THRESHOLD)
        self.assertLess(negative,module.THRESHOLD)

    def test_04_lifecycle_revocation_selection_feedback(self):
        eid,guest=self.create('Lifecycle')
        self.assertEqual(self.client.patch('/api/events/'+eid,headers=self.admin,json={'status':'published'}).status_code,409)
        first=self.upload(eid,jpg(self.alpha),'first.jpg').json['id']
        self.upload(eid,jpg(ImageEnhance.Contrast(self.alpha).enhance(.9)),'second.jpg')
        self.wait(eid)
        result=self.search(eid,guest,self.alpha).json
        self.assertEqual(result['count'],2)
        selected=self.client.get(result['zip']+'&ids='+first)
        self.assertEqual(selected.status_code,200)
        with zipfile.ZipFile(io.BytesIO(selected.data)) as zipped:self.assertEqual(len(zipped.namelist()),1)
        self.assertEqual(self.client.get(result['zip']+'&ids=not-authorized').status_code,403)
        body={'ticket':result['ticket'],'photo_id':first,'kind':'not_me'}
        self.assertEqual(self.client.post('/api/events/'+eid+'/feedback',headers=guest,json=body).status_code,200)
        self.assertEqual(self.client.post('/api/events/'+eid+'/feedback',headers=guest,json=body).status_code,200)
        info=self.client.get('/api/events/'+eid,headers=self.admin).json
        self.assertEqual(info['feedback'],1)
        self.assertEqual(self.client.patch('/api/events/'+eid,headers=self.admin,json={'status':'paused','description':'Guest description'}).status_code,200)
        self.assertEqual(self.search(eid,guest,self.alpha).status_code,409)
        self.assertEqual(self.client.get(result['photos'][0]['preview']).status_code,403)
        self.assertEqual(self.client.get(info['photos'][0]['preview']).status_code,200)
        self.client.patch('/api/events/'+eid,headers=self.admin,json={'status':'published'})
        new=self.client.post('/api/events/'+eid+'/rotate-link',headers=self.admin).json
        self.assertEqual(self.client.get('/api/events/'+eid,headers=guest).status_code,403)
        self.assertEqual(self.client.get(result['zip']).status_code,403)
        guest={'X-Guest-Key':new['guest']}
        self.assertEqual(self.search(eid,guest,self.alpha).status_code,200)
        self.assertEqual(self.client.delete('/api/events/'+eid+'/photos/'+first,headers=self.admin).status_code,200)
        fresh=self.search(eid,guest,self.alpha).json
        self.assertEqual(fresh['count'],1)
        stale_before_rotation=self.client.get(result['zip'])
        self.assertEqual(stale_before_rotation.status_code,403)
        self.assertEqual(self.search(eid,guest,self.alpha).json['count'],1)
        self.client.delete('/api/events/'+eid,headers=self.admin)

    def test_settings_patch_preserves_unrelated_fields(self):
        eid, _ = self.create('Original')
        path = '/api/events/' + eid
        self.upload(eid, jpg(self.alpha)); self.wait(eid)
        self.assertEqual(self.client.patch(path, headers=self.admin, json={'title':'Updated', 'description':'Saved elsewhere'}).status_code, 200)
        self.assertEqual(self.client.patch(path, headers=self.admin, json={'status':'paused'}).status_code, 200)
        info = self.client.get(path, headers=self.admin).json
        self.assertEqual((info['title'], info['description'], info['status']), ('Updated', 'Saved elsewhere', 'paused'))
        description = 'a' * 2000
        self.assertEqual(self.client.patch(path, headers=self.admin, json={'description': description}).status_code, 200)
        self.assertEqual(self.client.get(path, headers=self.admin).json['status'], 'paused')
        self.assertEqual(self.client.patch(path, headers=self.admin, json={'description': description + 'a'}).status_code, 400)
        self.assertEqual(self.client.get(path, headers=self.admin).json['description'], description)

    def test_invalid_status_patch_is_input_error_and_preserves_event(self):
        eid, _ = self.create('Unchanged')
        path = '/api/events/' + eid
        for status in ([], {}, None, True, 1, 'unknown'):
            with self.subTest(status=status):
                response = self.client.patch(path, headers=self.admin, json={'status':status, 'title':'Must not apply'})
                self.assertEqual(response.status_code, 400)
                self.assertIn('error', response.json)
                info = self.client.get(path, headers=self.admin).json
                self.assertEqual((info['title'], info['status']), ('Unchanged', 'draft'))

    def test_expired_ticket_requires_fresh_search(self):
        eid, guest = self.create('Expiry')
        photo_id = self.upload(eid, jpg(self.alpha)).json['id']; self.wait(eid)
        # Real signing/verification, only the creation timestamp is moved back.
        with patch('itsdangerous.timed.TimestampSigner.get_timestamp', return_value=int(time.time()) - 1201):
            expired = module.make_ticket(eid, [photo_id])
        self.assertEqual(self.client.get(f'/media/{eid}/{photo_id}?ticket={expired}').status_code, 403)
        self.assertEqual(self.client.get(f'/api/events/{eid}/download?ticket={expired}').status_code, 403)
        self.assertEqual(self.client.post(f'/api/events/{eid}/feedback', headers=guest, json={'ticket':expired, 'photo_id':photo_id, 'kind':'not_me'}).status_code, 403)
        fresh = self.search(eid, guest, self.alpha)
        self.assertEqual(fresh.status_code, 200)
        self.assertEqual(fresh.json['expires_in'], 1200)
        self.assertEqual(self.client.get(fresh.json['zip']).status_code, 200)

    def test_05_retry_and_reindex(self):
        eid,guest=self.create('Reindex')
        self.assertEqual(self.client.get('/api/events/'+eid,headers=self.admin).json['detailed'],1)
        photo_id=self.upload(eid,jpg(self.alpha)).json['id'];self.wait(eid)
        with module.lock,module.db() as conn:
            conn.execute("UPDATE photos SET status='error',error='simulated interrupted processing' WHERE id=?",(photo_id,))
        retried=self.client.post('/api/events/'+eid+'/retry',headers=self.admin)
        self.assertEqual(retried.json['queued'],1)
        self.assertEqual(self.wait(eid)['errors'],0)
        response=self.client.patch('/api/events/'+eid,headers=self.admin,json={'detailed':False})
        self.assertTrue(response.json['reindexed']);info=self.wait(eid)
        self.assertEqual(info['faces'],1)
        self.assertEqual(self.search(eid,guest,self.alpha).json['count'],1)
        self.client.delete('/api/events/'+eid,headers=self.admin)

    def test_06_invalid_json_and_scope(self):
        self.assertEqual(self.client.post('/api/events',headers=self.admin,json=['invalid']).status_code,400)
        eid,guest=self.create('Validation');other,_=self.create('Other')
        pid=self.upload(other,jpg(self.alpha)).json['id'];self.wait(other)
        self.assertEqual(self.client.delete('/api/events/'+eid+'/photos/'+pid,headers=self.admin).status_code,404)
        self.assertEqual(self.client.patch('/api/events/'+eid,headers=self.admin,json={'detailed':'yes'}).status_code,400)
        self.assertEqual(self.client.post('/api/events/'+eid+'/feedback',headers=guest,json={}).status_code,400)
        self.client.delete('/api/events/'+eid,headers=self.admin);self.client.delete('/api/events/'+other,headers=self.admin)

    def test_07_failed_delete_and_crash_recovery(self):
        import json
        eid,guest=self.create('Recoverability')
        pid=self.upload(eid,jpg(self.alpha)).json['id'];self.wait(eid)
        signed=self.search(eid,guest,self.alpha).json
        with module.db() as conn:
            conn.execute("CREATE TRIGGER reject_photo_delete BEFORE DELETE ON photos BEGIN SELECT RAISE(ABORT, 'simulated SQL failure'); END;")
        with self.assertLogs(level='ERROR'):
            response=self.client.delete('/api/events/'+eid+'/photos/'+pid,headers=self.admin)
        self.assertEqual(response.status_code,500)
        self.assertTrue((module.DATA/eid/(pid+'.jpg')).exists())
        self.assertEqual(self.client.get(signed['photos'][0]['download']).status_code,200)
        with module.db() as conn:conn.execute('DROP TRIGGER reject_photo_delete')
        stage=module.DATA/'.trash'/'simulated-crash';(stage/'payload').mkdir(parents=True)
        (stage/'operation.json').write_text(json.dumps({'event':eid,'photo':pid}))
        (module.DATA/eid/(pid+'.jpg')).replace(stage/'payload'/(pid+'.jpg'))
        module.recover_deletions()
        self.assertTrue((module.DATA/eid/(pid+'.jpg')).exists());self.assertFalse(stage.exists())
        self.client.delete('/api/events/'+eid+'/photos/'+pid,headers=self.admin)
        self.assertEqual(self.client.get(signed['zip']).status_code,409)
        self.client.delete('/api/events/'+eid,headers=self.admin)

    def test_08_delete_while_inference_is_running(self):
        eid,_=self.create('Concurrent deletion')
        entered=threading.Event();release=threading.Event();actual=module.analyze
        def delayed(*args,**kwargs):
            entered.set()
            if not release.wait(5):raise RuntimeError('Test synchronization timeout')
            return actual(*args,**kwargs)
        try:
            with patch.object(module,'analyze',side_effect=delayed):
                self.upload(eid,jpg(self.alpha));self.assertTrue(entered.wait(5))
                self.assertEqual(self.client.delete('/api/events/'+eid,headers=self.admin).status_code,200)
                release.set();module.pool.submit(lambda:None).result(timeout=5)
        finally:release.set()
        self.assertFalse((module.DATA/eid).exists())
        self.assertEqual(self.client.get('/api/events/'+eid,headers=self.admin).status_code,404)


if __name__=='__main__':
    unittest.main(verbosity=2)
