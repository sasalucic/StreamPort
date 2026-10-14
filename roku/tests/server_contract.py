"""Test Roku's HTTP contract against an isolated instance of the actual StreamPort backend.
Usage: python3 tests/server_contract.py /path/to/StreamPort
Uses disposable data and fixture bytes, not a playback test. No real media modified.
"""
import importlib.util,json,sys,tempfile,threading,time,urllib.request,urllib.error
from pathlib import Path
backend=Path(sys.argv[1]).resolve()
sys.path.insert(0,str(backend))
spec=importlib.util.spec_from_file_location('roku_test_server',backend/'server.py')
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
with tempfile.TemporaryDirectory() as temporary:
    root=Path(temporary);s.DATA=root/'data';media=root/'media';media.mkdir();s.ROOTS=[media];s.init()
    with s.database() as c:
        c.execute('INSERT INTO users(name,password,admin) VALUES (?,?,0)',('RokuTest',s.hash_password('fixture-password-123')))
        for i,extension in enumerate(['mp4','mkv'],1):
            file=media/f'fixture.{extension}';file.write_bytes(b'fixture bytes - not a real video')
            c.execute('INSERT INTO media(id,path,title,kind,size,mtime,added,duration) VALUES (?,?,?,?,?,?,?,?)',(i,str(file),'Test','movie',file.stat().st_size,time.time(),time.time(),120))
    (media/'fixture.vtt').write_text('WEBVTT\n\n00:00:01.000 --> 00:00:02.500\nHello Roku!\n')
    http=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler)
    thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{http.server_port}';cookie=''
    def call(path,body=None,extra=None,raw=False):
        headers={'X-StreamPort':'1','Content-Type':'application/json','Cookie':cookie};headers.update(extra or {})
        req=urllib.request.Request(base+path,data=None if body is None else json.dumps(body).encode(),headers=headers)
        try: response=urllib.request.urlopen(req,timeout=5)
        except urllib.error.HTTPError as error: response=error
        with response:
            data=response.read()
            return response.status, data if raw else json.loads(data), response.headers
    try:
        assert call('/api/library')[0]==401
        code,_,headers=call('/api/login',{'name':'RokuTest','password':'fixture-password-123'})
        assert code==200;cookie=headers['Set-Cookie'].split(';')[0];assert cookie.startswith('streamport=')
        assert call('/api/me')[1]['name']=='RokuTest'
        rows=call('/api/library')[1];assert len(rows)==2
        assert not any(key in rows[0] for key in ['path','folder','size'])
        for i,mime in [(1,'video/mp4'),(2,'video/matroska')]:
            code,data,headers=call(f'/api/media/{i}/stream',extra={'Range':'bytes=0-0'},raw=True)
            assert (code,len(data))==(206,1)
            assert headers['Content-Type']==mime,headers
        assert call('/api/favorites',{'id':1,'favorite':True})[0]==200
        assert next(r for r in call('/api/library')[1] if r['id']==1)['favorite']==1
        assert call('/api/progress',{'id':1,'position':42.5,'duration':120})[0]==200
        assert next(r for r in call('/api/library')[1] if r['id']==1)['position']==42.5
        assert call('/api/played',{'id':1})[0]==200
        assert call('/api/media/1/subtitles')[1][0]['index']==0
        assert b'Hello Roku!' in call('/api/media/1/subtitle?index=0',raw=True)[1]
        assert call('/api/logout',{})[0]==200
        assert call('/api/me')[0]==401
        print('PASS: authenticated viewer, cookie, library, range/MIME, favorites, progress, played, WebVTT and logout')
    finally:
        http.shutdown();http.server_close();thread.join()
