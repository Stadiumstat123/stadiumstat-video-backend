import base64,hashlib,hmac,json,os,tempfile,time,unittest,uuid
_TEMP=tempfile.TemporaryDirectory()
os.environ['DATA_DIR']=_TEMP.name
os.environ['VIDEO_SERVICE_SECRET']='test-only-secret-with-at-least-32-characters'
os.environ['ALLOWED_ORIGINS']='https://site.example'
from fastapi.testclient import TestClient
from service.api import app
from service.storage import connect

def token(job,scope='upload',owner='a'*64,size=4):
    data={'job':job,'scope':scope,'sub':owner,'exp':int(time.time())+300,'size':size,'config':{'sport':'nba','regions':{k:[.1,.1,.1,.05] for k in ['home','away','period','clock']}}}
    payload=base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b'=')
    sig=base64.urlsafe_b64encode(hmac.new(os.environ['VIDEO_SERVICE_SECRET'].encode(),payload,hashlib.sha256).digest()).rstrip(b'=')
    return (payload+b'.'+sig).decode()
class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(app)
        with connect() as db:
            db.execute('DELETE FROM jobs');db.execute('INSERT OR REPLACE INTO runtime VALUES (1,?,1)',(int(time.time()),))
    def test_upload_and_owner_isolation(self):
        job=str(uuid.uuid4());h={'Authorization':'Bearer '+token(job)}
        self.assertEqual(self.client.put('/v1/uploads/'+job,content=b'test').status_code,401)
        self.assertEqual(self.client.put('/v1/uploads/'+job,content=b'test',headers=h).status_code,200)
        self.assertEqual(self.client.put('/v1/uploads/'+job,content=b'test',headers=h).status_code,409)
        self.assertEqual(self.client.get('/v1/jobs/'+job,headers={'Authorization':'Bearer '+token(job,'read','b'*64)}).status_code,404)
        r=self.client.get('/v1/jobs/'+job,headers={'Authorization':'Bearer '+token(job,'read')})
        self.assertEqual(r.json()['state'],'queued');self.assertNotIn('owner',r.json())
        self.assertEqual(self.client.delete('/v1/jobs/'+job,headers={'Authorization':'Bearer '+token(job,'delete')}).status_code,200)
    def test_incomplete_upload_and_wrong_scope(self):
        job=str(uuid.uuid4())
        self.assertEqual(self.client.put('/v1/uploads/'+job,content=b'x',headers={'Authorization':'Bearer '+token(job,'read')}).status_code,401)
        self.assertEqual(self.client.put('/v1/uploads/'+job,content=b'x',headers={'Authorization':'Bearer '+token(job)}).status_code,400)
    def test_readiness_blocks_uploads(self):
        with connect() as db:db.execute('UPDATE runtime SET ready=0')
        job=str(uuid.uuid4());self.assertFalse(self.client.get('/health').json()['ready'])
        self.assertEqual(self.client.put('/v1/uploads/'+job,content=b'test',headers={'Authorization':'Bearer '+token(job)}).status_code,503)
if __name__=='__main__':unittest.main()
