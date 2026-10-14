import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import importlib.util, json, os, subprocess, tempfile, threading, unittest, urllib.request, urllib.error
from pathlib import Path
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('streamport',Path(__file__).resolve().parents[1]/'server.py')
s=importlib.util.module_from_spec(spec); spec.loader.exec_module(s)

class Integration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(); root=Path(cls.temp.name)
        s.DATA=root/'data'; media=root/'media'; media.mkdir(); s.ROOTS=[media]
        cls.movie=media/'Test.Movie.2025.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=320x180:r=10','-f','lavfi','-i','sine=frequency=440','-t','3','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart',str(cls.movie)],check=True)
        (media/'Test.Movie.2025.srt').write_text('1\n00:00:00,000 --> 00:00:02,000\nHello StreamPort!\n')
        s.init(); s.scan()
        cls.http=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler)
        cls.url='http://127.0.0.1:'+str(cls.http.server_port)
        cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True); cls.thread.start()
        cls.cookie=''
        status,body,headers=cls.call('/api/setup',{'name':'admin','password':'test-password-123'},auth=False)
        assert status==200, body
        cls.cookie=headers['Set-Cookie'].split(';')[0]
        cls.mid=cls.call('/api/library')[1][0]['id']
    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown();cls.http.server_close();cls.temp.cleanup()
    @classmethod
    def call(cls,path,body=None,auth=True,extra=None,raw=False):
        headers={'X-StreamPort':'1','Content-Type':'application/json'}
        if auth: headers['Cookie']=cls.cookie
        headers.update(extra or {})
        req=urllib.request.Request(cls.url+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
        try: r=urllib.request.urlopen(req,timeout=20)
        except urllib.error.HTTPError as e: r=e
        with r:
            blob=r.read(); result=blob if raw else json.loads(blob)
            return r.status,result,r.headers
    def test_frontend_entrypoints_available(self):
        status,html,_=self.call('/',auth=False,raw=True)
        self.assertEqual(status,200);self.assertIn(b'/enhancements.js',html)
        status,script,_=self.call('/enhancements.js',auth=False,raw=True)
        self.assertEqual(status,200);self.assertIn(b'boot();',script)
    def test_auth_required(self): self.assertEqual(self.call('/api/library',auth=False)[0],401)
    def test_setup_only_once(self): self.assertEqual(self.call('/api/setup',{'name':'x','password':'test-password-123'},auth=False)[0],409)
    def test_scan_metadata(self):
        m=self.call('/api/library')[1][0]; self.assertEqual(m['title'],'Test Movie'); self.assertGreater(m['duration'],2); self.assertNotIn('path',m)
    def test_range_and_suffix(self):
        path=f'/api/media/{self.mid}/stream'; data=self.movie.read_bytes()
        status,b,h=self.call(path,extra={'Range':'bytes=10-39'},raw=True)
        self.assertEqual((status,b),(206,data[10:40]));self.assertEqual(h['Content-Length'],'30')
        self.assertEqual(self.call(path,extra={'Range':'bytes=-15'},raw=True)[1],data[-15:])
        self.assertEqual(self.call(path,extra={'Range':'bytes=999999999-'},raw=True)[0],416)
    def test_progress_persists(self):
        self.assertEqual(self.call('/api/progress',{'id':self.mid,'position':1.25,'duration':3})[0],200)
        self.assertEqual(self.call('/api/library')[1][0]['position'],1.25)
    def test_invalid_progress(self): self.assertEqual(self.call('/api/progress',{'id':self.mid,'position':float('nan')})[0],400)
    def test_csrf(self):
        self.assertEqual(self.call('/api/scan',{},extra={'X-StreamPort':''})[0],403)
        self.assertEqual(self.call('/api/scan',{},extra={'Origin':'http://attacker.test'})[0],403)
    def test_viewer_permissions_and_separate_history(self):
        self.assertEqual(self.call('/api/users',{'name':'viewer','password':'viewer-password-123'})[0],200)
        _,_,h=self.call('/api/login',{'name':'viewer','password':'viewer-password-123'},auth=False)
        cookie=h['Set-Cookie'].split(';')[0]
        self.assertEqual(self.call('/api/settings',extra={'Cookie':cookie})[0],403)
        self.assertEqual(self.call('/api/scan',{},extra={'Cookie':cookie})[0],403)
        self.assertEqual(self.call('/api/library',extra={'Cookie':cookie})[1][0]['position'],0)
        for endpoint in ('/api/library',f'/api/media/{self.mid}'):
            payload=self.call(endpoint,extra={'Cookie':cookie})[1]
            item=payload[0] if isinstance(payload,list) else payload
            for key in ('path','folder','library_root','size'):self.assertNotIn(key,item)
        self.assertIn('size',self.call(f'/api/media/{self.mid}')[1])
        self.assertIn('folder',self.call('/api/library')[1][0])
        payload=self.call(f'/api/media/{self.mid}/probe',extra={'Cookie':cookie})[1]
        self.assertNotIn('filename',payload['format']);self.assertNotIn('size',payload['format'])
        self.assertEqual(self.call('/api/dashboard',extra={'Cookie':cookie})[0],403)
        self.assertEqual(self.call(f'/api/media/{self.mid}/thumbnail',extra={'Cookie':cookie},raw=True)[0],200)
        self.assertEqual(self.call('/api/logout',{},extra={'Cookie':cookie})[0],200)
        self.assertEqual(self.call('/api/me',extra={'Cookie':cookie})[0],401)
    def test_subtitle_conversion(self):
        self.assertGreater(len(self.call(f'/api/media/{self.mid}/subtitles')[1]),0)
        status,blob,_=self.call(f'/api/media/{self.mid}/subtitle?index=0',raw=True)
        self.assertEqual(status,200); self.assertTrue(blob.startswith(b'WEBVTT')); self.assertIn(b'Hello StreamPort',blob)
    def test_actual_transcoding(self):
        status,blob,_=self.call(f'/api/media/{self.mid}/transcode?start=1&quality=480',raw=True)
        self.assertEqual(status,200);self.assertIn(b'ftyp',blob[:32]);self.assertGreater(len(blob),1000)
        dest=Path(self.temp.name)/'transcoded.mp4';dest.write_bytes(blob)
        p=s.probe(dest);self.assertTrue(any(x.get('codec_name')=='h264' for x in p['streams']))
    def test_actual_thumbnail_and_cache(self):
        route=f'/api/media/{self.mid}/thumbnail'
        self.assertEqual(self.call(route,auth=False,raw=True)[0],401)
        status,blob,headers=self.call(route,raw=True)
        self.assertEqual(status,200);self.assertTrue(blob.startswith(b'\xff\xd8'))
        self.assertEqual(headers['Content-Type'],'image/jpeg')
        image=Path(self.temp.name)/'frame.jpg';image.write_bytes(blob)
        info=s.probe(image)['streams'][0]
        self.assertEqual((info['width'],info['height']),(480,270))
        with patch.object(s.subprocess,'run',side_effect=AssertionError('Cache should be used')):
            self.assertEqual(self.call(route,raw=True)[1],blob)
    def test_secrets_not_returned(self):
        self.call('/api/settings',{'radarr_key':'secret123','radarr_url':'http://localhost:7878'})
        result=self.call('/api/settings')[1];self.assertNotIn('radarr_key',result);self.assertTrue(result['radarr_key_set']);self.assertNotIn('secret123',json.dumps(result))
    def test_radarr_sync_contract(self):
        self.call('/api/settings',{'radarr_remote_path':'/movies','radarr_local_path':str(self.movie.parent),'radarr_key':'secret123','radarr_url':'http://localhost:7878'})
        fixture=[{'title':'Test Movie','year':2025,'imdbId':'tt123','overview':'A test','images':[{'coverType':'poster','remoteUrl':'https://example.org/poster.jpg'}],'movieFile':{'path':'/movies/'+self.movie.name}}]
        with patch.object(s,'request_json',return_value=fixture) as mock:
            result=self.call('/api/integrations/radarr/sync',{})
            self.assertEqual(result[1]['updated'],1)
            self.assertIn('/api/v3/movie',mock.call_args.args[0]);self.assertEqual(mock.call_args.kwargs['headers']['X-Api-Key'],'secret123')
    def test_opensubtitles_login_password_encrypted(self):
        self.call('/api/settings',{'os_key':'os-key'})
        with patch.object(s,'request_json',return_value={'token':'session-token','base_url':'api.opensubtitles.com'}) as mock:
            result=self.call('/api/opensubtitles/login',{'username':'sample','password':'sensitive-pass'})
            self.assertEqual(result[0],200)
            self.assertEqual(mock.call_args.args[3]['Api-Key'],'os-key')
        with s.database() as c:
            raw=str([tuple(r) for r in c.execute('SELECT * FROM settings')])
        self.assertNotIn('sensitive-pass',raw)
        self.assertEqual(s.settings()['os_password'],'sensitive-pass')
        self.assertNotIn('session-token',json.dumps(self.call('/api/settings')[1]))
    def test_sonarr_metadata_and_path_mapping(self):
        episode=self.movie.parent/'Test.Show.S02E03.mkv';episode.write_bytes(self.movie.read_bytes());s.scan()
        self.call('/api/settings',{'sonarr_url':'http://localhost:8989','sonarr_key':'sonarr-secret','sonarr_remote_path':'/tv','sonarr_local_path':str(self.movie.parent)})
        records=[{'id':7,'title':'Test Show','imdbId':'tt777','overview':'Series overview','images':[]}]
        with patch.object(s,'request_json',side_effect=[records,[{'id':44,'path':'/tv/'+episode.name}],[{'episodeFileId':44,'seasonNumber':2,'episodeNumber':3,'title':'A real episode name','overview':'Episode plot'}]]) as mock:
            response=self.call('/api/integrations/sonarr/sync',{})
            self.assertEqual(response[1]['updated'],1)
            self.assertIn('episode?seriesId=7',mock.call_args.args[0])
            match=next(m for m in self.call('/api/library')[1] if m['kind']=='episode')
            self.assertEqual(match['episode_title'],'A real episode name')
            self.assertEqual(match['overview'],'Episode plot')
        episode.unlink();s.scan()
    def test_opensubtitles_refresh_and_search(self):
        s.set_settings({'os_key':'key','os_username':'user','os_password':'pass','os_expires':0,'os_token':''})
        with patch.object(s,'request_json',return_value={'token':'renewed'}) as mock:
            self.assertEqual(s.os_headers(True)['Authorization'],'Bearer renewed')
            self.assertEqual(mock.call_count,1)
            s.os_headers(True)
            self.assertEqual(mock.call_count,1)
        with patch.object(s,'request_json',return_value={'data':[{'id':'result'}]}) as mock:
            status,result,_=self.call('/api/subtitles/search',{'id':self.mid,'language':'sr'})
            self.assertEqual(status,200);self.assertEqual(result[0]['id'],'result')
            self.assertIn('languages=sr',mock.call_args.args[0])
    def test_opensubtitles_download_contract(self):
        import io
        s.set_settings({'os_key':'key','os_username':'user','os_password':'pass','os_token':'download-token','os_expires':9999999999})
        provider={'link':'https://api.opensubtitles.com/download/test','remaining':5}
        fake=unittest.mock.MagicMock()
        fake.open.return_value=io.BytesIO(b'WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nDownloaded subtitle\n')
        with patch.object(s,'request_json',return_value=provider) as mock, patch.object(s.urllib.request,'build_opener',return_value=fake):
            status,result,_=self.call('/api/subtitles/download',{'id':self.mid,'file_id':123,'language':'sr'})
            self.assertEqual(status,200);self.assertEqual(result['remaining'],5)
            self.assertEqual(mock.call_args.args[2],{'file_id':123,'sub_format':'srt'})
        self.assertIn('Downloaded subtitle',(s.DATA/'subtitles'/f'{self.mid}.sr.123.vtt').read_text())
    def test_no_symlink_escape(self):
        outside=Path(self.temp.name)/'outside.mp4';outside.write_bytes(b'no')
        link=self.movie.parent/'escape.mp4';link.symlink_to(outside)
        with self.assertRaises(s.Problem): s.safe_path(link)
        s.scan();self.assertFalse(any(m['title']=='escape' for m in self.call('/api/library')[1]))
    def test_missing_files_marked_unavailable(self):
        p=self.movie.parent/'Temporary.2026.mp4';p.write_bytes(self.movie.read_bytes());s.scan()
        self.assertTrue(any(x['title']=='Temporary' for x in self.call('/api/library')[1]));p.unlink();s.scan()
        self.assertFalse(any(x['title']=='Temporary' for x in self.call('/api/library')[1]))

if __name__=='__main__':unittest.main(verbosity=2)
