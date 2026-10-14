import sys, json, tempfile, unittest, gzip, io, zipfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server as s
import metadata
class MetadataAndSubtitles(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();root=Path(self.temp.name);s.DATA=root/'data';s.ROOTS=[root/'movies',root/'tv']
        for p in s.ROOTS:p.mkdir()
        s.init();s.set_settings({'tmdb_key':'a'*50})
    def tearDown(self):self.temp.cleanup()
    def item(self,path):
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'test')
        info=s.infer(path)
        with s.database() as c:
            c.execute('INSERT INTO media(path,title,kind,series,show_key,season,episode,year,available) VALUES (?,?,?,?,?,?,?,?,1)',(str(path),info['title'],info['kind'],info['series'],info['show_key'],info['season'],info['episode'],info['year']))
            return dict(c.execute('SELECT * FROM media WHERE path=?',(str(path),)).fetchone())
    def test_movies_in_tv_mount_are_movies(self):
        for title in ('Rio 2','Kralj Lavova','Macak u Cizmama','Panfilovs 28'):
            m=s.infer(s.ROOTS[1]/title/(title+'.mkv'));self.assertEqual(m['kind'],'movie',title)
    def test_movie_with_letter_s_digits_not_season(self):
        self.assertEqual(s.infer(s.ROOTS[1]/'Cars 2'/'Cars 2.mkv')['kind'],'movie')
    def test_release_cleanup_after_year(self):self.assertEqual(s.clean_title('Madagaskar.2.2008.HR.x264'),'Madagaskar 2')
    def test_metadata_movie_collections_cast_and_studios(self):
        item=self.item(s.ROOTS[0]/'Movie.2020.mkv')
        response={'title':'Correct Movie','release_date':'2020-02-01','overview':'Plot','poster_path':'/poster.jpg','backdrop_path':'/back.jpg','vote_average':7.45,'genres':[{'name':'Drama'}],'imdb_id':'tt123','belongs_to_collection':{'id':10,'name':'Test Collection'},'credits':{'cast':[{'name':'Actor','character':'Hero','profile_path':'/actor.jpg'}]},'production_companies':[{'name':'Studio','logo_path':'/studio.png'}]}
        calls=[]
        def request(url,**kwargs):calls.append((url,kwargs));return response
        engine=metadata.Engine(s.settings,request,s.database,s.Problem);engine.apply(item,7)
        with s.database() as c:row=dict(c.execute('SELECT * FROM media WHERE id=?',(item['id'],)).fetchone())
        self.assertEqual(row['title'],'Correct Movie');self.assertEqual(row['collection_id'],'10');self.assertIn('Actor',row['cast_json']);self.assertIn('Studio',row['studios_json']);self.assertEqual(row['source'],'tmdb');self.assertIn('Bearer ',calls[0][1]['headers']['Authorization'])
        s.update_catalog(Path(item['path']),item['id'])
        with s.database() as c:self.assertEqual(c.execute('SELECT title FROM media WHERE id=?',(item['id'],)).fetchone()[0],'Correct Movie')
    def test_tv_metadata_applies_season_episode_to_group(self):
        first=self.item(s.ROOTS[1]/'Show'/'Season 1'/'Show.S01E01.mkv');second=self.item(s.ROOTS[1]/'Show'/'Season 1'/'Show.S01E02.mkv')
        def request(url,**kwargs):
            if '/season/1?' in url:return {'episodes':[{'episode_number':1,'name':'Pilot','overview':'Pilot plot','still_path':'/still.jpg'},{'episode_number':2,'name':'Second'}]}
            return {'name':'Canonical Show','overview':'Series plot','first_air_date':'2021-01-01'}
        metadata.Engine(s.settings,request,s.database,s.Problem).apply(first,9)
        with s.database() as c:rows=[dict(r) for r in c.execute('SELECT * FROM media ORDER BY id')]
        self.assertEqual(rows[0]['episode_title'],'Pilot');self.assertEqual(rows[1]['episode_title'],'Second');self.assertEqual(rows[1]['series'],'Canonical Show')
    def test_ambiguous_search_requires_identification(self):
        item=self.item(s.ROOTS[0]/'Same.mkv')
        response={'results':[{'id':1,'title':'Same','release_date':'2000'},{'id':2,'title':'Same','release_date':'2010'}]}
        engine=metadata.Engine(s.settings,lambda *a,**kw:response,s.database,s.Problem)
        self.assertIsNone(engine.identify(item))
    def test_year_breaks_tie(self):
        item=self.item(s.ROOTS[0]/'Same.2010.mkv')
        response={'results':[{'id':1,'title':'Same','release_date':'2000'},{'id':2,'title':'Same','release_date':'2010'}]}
        engine=metadata.Engine(s.settings,lambda *a,**kw:response,s.database,s.Problem)
        self.assertEqual(engine.identify(item),2)
    def test_fanart_and_omdb_enrichment(self):
        s.set_settings({'omdb_key':'omdb','fanart_key':'fanart'});item=self.item(s.ROOTS[0]/'Film.mkv')
        def request(url,**kw):
            if 'omdbapi' in url:return {'Response':'True','imdbRating':'8.7','Plot':'Extra plot'}
            if 'fanart.tv' in url:return {'moviebackground':[{'url':'https://assets.fanart.tv/back.jpg','likes':'3'}],'hdmovielogo':[{'url':'https://assets.fanart.tv/logo.png'}]}
            return {'title':'Film','imdb_id':'tt777'}
        metadata.Engine(s.settings,request,s.database,s.Problem).apply(item,6)
        with s.database() as c:r=dict(c.execute('SELECT * FROM media').fetchone())
        self.assertEqual(r['rating'],'8.7');self.assertEqual(r['overview'],'Extra plot');self.assertIn('fanart.tv',r['logo'])
    def test_srt_and_bom_vtt_conversion(self):
        v=s.to_vtt(b'1\r\n00:00:01,000 --> 00:00:03,000\r\nHello\r\n');self.assertTrue(v.startswith(b'WEBVTT'));self.assertIn(b'Hello',v)
        self.assertEqual(s.to_vtt(b'\xef\xbb\xbf'+v),v)
    def test_invalid_subtitle_rejected(self):
        with self.assertRaises(s.Problem):s.to_vtt(b'<html>Access denied</html>')
    def test_download_saved_listed_and_cached(self):
        item=self.item(s.ROOTS[0]/'Movie.mkv');vtt=b'WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nSaved\n'
        with patch.object(s,'os_headers',return_value={}),patch.object(s,'request_json',return_value={'link':'https://dl.opensubtitles.com/a'}) as request,patch.object(s,'fetch_subtitle',return_value=vtt):
            first=s.download_subtitle(item,99,'sr');second=s.download_subtitle(item,99,'sr')
            self.assertFalse(first['cached']);self.assertTrue(second['cached']);self.assertEqual(request.call_count,1)
            self.assertEqual(Path(s.subtitles(item)[0]['path']).name,first['key'])
    def test_download_host_validation(self):
        for url in ('https://dl.opensubtitles.com/a','https://dl.opensubtitles.org/a'):self.assertEqual(s.subtitle_url(url),url)
        for url in ('http://dl.opensubtitles.com/a','https://opensubtitles.com.evil.test/a','https://127.0.0.1/a','file:///etc/passwd'):
            with self.assertRaises(s.Problem):s.subtitle_url(url)
    def test_gzip_subtitle(self):
        blob=gzip.compress(b'1\n00:00:01,000 --> 00:00:03,000\nHello\n')
        class Opener:
            def open(self,*a,**kw):return io.BytesIO(blob)
        with patch.object(s.urllib.request,'build_opener',return_value=Opener()):self.assertIn(b'Hello',s.fetch_subtitle('https://dl.opensubtitles.com/a'))
    def test_file_download_identity_and_redirect_without_secrets(self):
        captured=[]
        class Opener:
            def open(self,request,**kw):
                captured.append(request)
                return io.BytesIO(b'WEBVTT\n')
        with patch.dict(s.os.environ,{'OPENSUBTITLES_USER_AGENT':'StreamPortTest v1.0'}),patch.object(s.urllib.request,'build_opener',return_value=Opener()) as factory:
            s.fetch_subtitle('https://dl.opensubtitles.com/a?token=private')
            redirect=factory.call_args.args[0]()
        request=captured[0]
        self.assertEqual(request.get_header('User-agent'),'StreamPortTest v1.0')
        redirected=redirect.redirect_request(request,None,302,'Found',{},'https://dl.opensubtitles.org/file')
        self.assertEqual(redirected.get_header('User-agent'),'StreamPortTest v1.0')
        for key in ('Authorization','Api-key'):
            self.assertIsNone(redirected.get_header(key))
        with self.assertRaises(s.Problem):redirect.redirect_request(request,None,302,'Found',{},'https://evil.test/file')
    def test_download_403_diagnostic_does_not_expose_link(self):
        error=s.urllib.error.HTTPError('https://dl.opensubtitles.com/a?token=secret',403,'Forbidden',{},None)
        with patch.object(s.urllib.request,'build_opener') as factory:
            factory.return_value.open.side_effect=error
            with self.assertRaises(s.Problem) as caught:s.fetch_subtitle(error.url)
        self.assertIn('does not confirm a quota problem',str(caught.exception))
        self.assertIn('dl.opensubtitles.com',str(caught.exception))
        self.assertNotIn('secret',str(caught.exception))
    def test_manual_classification_survives_scan(self):
        item=self.item(s.ROOTS[1]/'A'/'A.S01E01.mkv')
        s.provider.update(item['id'],{'kind_override':'movie','kind':'movie'})
        s.update_catalog(Path(item['path']),item['id'])
        with s.database() as c:self.assertEqual(c.execute('SELECT kind FROM media').fetchone()[0],'movie')
if __name__=='__main__':unittest.main()
