import importlib.util,json,os,sys,tempfile,threading,unittest,urllib.request,urllib.error,time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
spec=importlib.util.spec_from_file_location('features_server',Path(__file__).resolve().parents[1]/'server.py')
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)

class Features(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        s.DATA=self.root/'data';self.media=self.root/'media';self.media.mkdir();s.ROOTS=[self.media]
        s.ATTEMPTS.clear();s.DELETE_PREVIEWS.clear();s.init()
        self.admin_password='admin-password-123';self.viewer_password='viewer-password-123'
        with s.database() as c:
            c.execute('INSERT INTO users VALUES (1,?,?,1)',('Admin',s.hash_password(self.admin_password)))
            c.execute('INSERT INTO users VALUES (2,?,?,0)',('Viewer',s.hash_password(self.viewer_password)))
        self.movie=self.add('movie.mp4','movie')
        self.http=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler);self.url='http://127.0.0.1:'+str(self.http.server_port)
        threading.Thread(target=self.http.serve_forever,daemon=True).start()
        self.admin=self.login('Admin',self.admin_password);self.viewer=self.login('Viewer',self.viewer_password)
    def tearDown(self):self.http.shutdown();self.http.server_close();self.tmp.cleanup()
    def add(self,name,kind='episode',show='series-a'):
        path=self.media/name;path.parent.mkdir(exist_ok=True,parents=True);path.write_bytes(b'fake video content')
        with s.database() as c:
            return c.execute('INSERT INTO media(path,title,kind,series,show_key,size,mtime,added) VALUES (?,?,?,?,?,?,?,?)',(str(path),name,kind,show,show,path.stat().st_size,path.stat().st_mtime,time.time())).lastrowid
    def call(self,path,body=None,cookie=None):
        req=urllib.request.Request(self.url+path,data=json.dumps(body).encode() if body is not None else None,headers={'X-StreamPort':'1','Content-Type':'application/json','Cookie':cookie or ''})
        try:r=urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:r=e
        with r:return r.status,json.loads(r.read()),r.headers
    def login(self,name,password):
        status,body,h=self.call('/api/login',{'name':name,'password':password});self.assertEqual(status,200,body);return h['Set-Cookie'].split(';')[0]
    def preview(self,mid=None,scope='movie',cookie=None):
        return self.call('/api/media/delete-preview',{'id':mid or self.movie,'scope':scope},cookie or self.admin)
    def delete(self,token,password=None,cookie=None):
        return self.call('/api/media/delete',{'token':token,'password':password or self.admin_password},cookie or self.admin)
    def test_favorites_are_personal_persistent_and_idempotent(self):
        for _ in range(2):self.assertEqual(self.call('/api/favorites',{'id':self.movie,'favorite':True},self.viewer)[0],200)
        self.assertEqual(self.call('/api/library',cookie=self.viewer)[1][0]['favorite'],1)
        self.assertEqual(self.call('/api/library',cookie=self.admin)[1][0]['favorite'],0)
        s.init();self.assertEqual(self.call('/api/library',cookie=self.viewer)[1][0]['favorite'],1)
        self.call('/api/favorites',{'id':self.movie,'favorite':False},self.viewer)
        self.assertEqual(self.call('/api/library',cookie=self.viewer)[1][0]['favorite'],0)
        self.assertEqual(self.call('/api/favorites',{'id':self.movie,'favorite':'false'},self.viewer)[0],400)
    def test_own_password_invalidates_all_sessions(self):
        second=self.login('Viewer',self.viewer_password)
        self.assertEqual(self.call('/api/account/password',{'current_password':'wrong','new_password':'new-password-123'},self.viewer)[0],403)
        self.assertEqual(self.call('/api/account/password',{'current_password':self.viewer_password,'new_password':'new-password-123'},self.viewer)[0],200)
        for cookie in (second,self.viewer):self.assertEqual(self.call('/api/me',cookie=cookie)[0],401)
        self.assertEqual(self.call('/api/login',{'name':'Viewer','password':self.viewer_password})[0],401)
        self.login('Viewer','new-password-123')
    def test_admin_reset_requires_acting_admin_password(self):
        payload={'id':2,'current_password':self.viewer_password,'new_password':'reset-password-123'}
        self.assertEqual(self.call('/api/users/password',payload,self.viewer)[0],403)
        self.assertEqual(self.call('/api/users/password',payload,self.admin)[0],403)
        payload['current_password']=self.admin_password
        self.assertEqual(self.call('/api/users/password',payload,self.admin)[0],200)
        self.assertEqual(self.call('/api/me',cookie=self.viewer)[0],401)
        self.assertEqual(self.call('/api/me',cookie=self.admin)[0],200)
        self.login('Viewer','reset-password-123')
        payload['id']=1;self.assertTrue(self.call('/api/users/password',payload,self.admin)[1]['sign_in_required'])
        self.login('Admin','reset-password-123')
    def test_sensitive_attempts_throttled(self):
        for _ in range(8):self.assertEqual(self.call('/api/account/password',{'current_password':'bad','new_password':'valid-password'},self.viewer)[0],403)
        self.assertEqual(self.call('/api/account/password',{'current_password':self.viewer_password,'new_password':'valid-password'},self.viewer)[0],429)
    def test_delete_disabled_and_viewer_denied(self):
        with patch.dict(os.environ,{'ALLOW_MEDIA_DELETE':'false'}):self.assertEqual(self.preview()[0],409)
        with patch.dict(os.environ,{'ALLOW_MEDIA_DELETE':'true'}):
            self.assertEqual(self.preview(cookie=self.viewer)[0],403)
            self.assertEqual(self.delete('arbitrary',cookie=self.viewer)[0],403)
    def test_movie_delete_exact_file_password_and_single_use(self):
        other=self.add('nested/keep.mp4','movie');sub=self.media/'movie.srt';sub.write_text('keep')
        with patch.dict(os.environ,{'ALLOW_MEDIA_DELETE':'true'}):
            status,p,_=self.preview();self.assertEqual(status,200);self.assertEqual(p['count'],1)
            self.assertEqual(self.delete(p['token'],'wrong')[0],403);self.assertTrue((self.media/'movie.mp4').exists())
            status,result,_=self.delete(p['token']);self.assertEqual(status,200);self.assertEqual(result['deleted'],[self.movie])
            self.assertEqual(self.delete(p['token'])[0],409)
        self.assertFalse((self.media/'movie.mp4').exists());self.assertTrue((self.media/'nested/keep.mp4').exists());self.assertTrue(sub.exists())
        self.assertEqual([m['id'] for m in self.call('/api/library',cookie=self.admin)[1]],[other])
    def test_series_delete_only_group_not_parent_folder(self):
        a=self.add('show/S01E01.mp4');b=self.add('show/S02E01.mp4');keep=self.add('show/other-series.mp4',show='series-b')
        with patch.dict(os.environ,{'ALLOW_MEDIA_DELETE':'true'}):
            status,p,_=self.preview(a,'series');self.assertEqual(status,200);self.assertEqual(p['count'],2)
            self.assertEqual(set(self.delete(p['token'])[1]['deleted']),{a,b})
        self.assertTrue((self.media/'show/other-series.mp4').exists());self.assertTrue((self.media/'movie.mp4').exists())
    def test_preview_changed_or_expired_aborts(self):
        with patch.dict(os.environ,{'ALLOW_MEDIA_DELETE':'true'}):
            p=self.preview()[1];(self.media/'movie.mp4').write_bytes(b'changed')
            self.assertEqual(self.delete(p['token'])[0],409);self.assertTrue((self.media/'movie.mp4').exists())
            p=self.preview()[1];s.DELETE_PREVIEWS[p['token']]['expires']=0
            self.assertEqual(self.delete(p['token'])[0],409)
    def test_symlink_escape_and_readonly_denied(self):
        outside=self.root/'outside.mp4';outside.write_bytes(b'keep');(self.media/'movie.mp4').unlink();(self.media/'movie.mp4').symlink_to(outside)
        with patch.dict(os.environ,{'ALLOW_MEDIA_DELETE':'true'}):self.assertEqual(self.preview()[0],403)
        self.assertTrue(outside.exists())
        (self.media/'movie.mp4').unlink();(self.media/'movie.mp4').write_bytes(b'fake')
        with patch.dict(os.environ,{'ALLOW_MEDIA_DELETE':'true'}),patch.object(s.os,'access',return_value=False):self.assertEqual(self.preview()[0],409)
    def test_partial_delete_reports_failure_and_preserves_record(self):
        a=self.add('show/a.mp4');b=self.add('show/b.mp4');real=s.os.unlink
        def fail(path,*args,**kwargs):
            if path=='b.mp4':raise PermissionError('read only')
            return real(path,*args,**kwargs)
        with patch.dict(os.environ,{'ALLOW_MEDIA_DELETE':'true'}):
            p=self.preview(a,'series')[1]
            with patch.object(s.os,'unlink',side_effect=fail):status,r,_=self.delete(p['token'])
        self.assertEqual(status,200);self.assertFalse(r['ok']);self.assertEqual(r['deleted'],[a]);self.assertEqual(len(r['failed']),1)
        self.assertIn(b,[m['id'] for m in self.call('/api/library',cookie=self.admin)[1]])
    def test_preview_bound_to_admin_and_detects_added_episode(self):
        with s.database() as c:c.execute('INSERT INTO users VALUES (3,?,?,1)',('Other admin',s.hash_password('other-password-123')))
        other=self.login('Other admin','other-password-123');a=self.add('show/a.mp4')
        with patch.dict(os.environ,{'ALLOW_MEDIA_DELETE':'true'}):
            p=self.preview(a,'series')[1]
            self.assertEqual(self.delete(p['token'],'other-password-123',other)[0],409)
            self.add('show/new.mp4')
            self.assertEqual(self.delete(p['token'])[0],409)
            self.assertTrue((self.media/'show/a.mp4').exists())
    def test_parent_symlink_swap_after_preview_cannot_delete_outside(self):
        mid=self.add('nested/film.mp4','movie')
        outside=self.root/'outside';outside.mkdir();(outside/'film.mp4').write_bytes(b'keep')
        with patch.dict(os.environ,{'ALLOW_MEDIA_DELETE':'true'}):
            p=self.preview(mid)[1]
            (self.media/'nested').rename(self.media/'renamed');(self.media/'nested').symlink_to(outside,target_is_directory=True)
            self.assertEqual(self.delete(p['token'])[0],403)
        self.assertTrue((outside/'film.mp4').exists())
    def test_plays_are_personal_and_throttled(self):
        for _ in range(3):self.call('/api/played',{'id':self.movie},self.viewer)
        m=self.call('/api/library',cookie=self.viewer)[1][0];self.assertEqual(m['play_count'],1);self.assertGreater(m['last_played'],0)
        self.assertEqual(self.call('/api/library',cookie=self.admin)[1][0]['play_count'],0)

if __name__=='__main__':unittest.main()
