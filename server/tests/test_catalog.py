import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import importlib.util, sqlite3, tempfile, unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('catalogserver',Path(__file__).resolve().parents[1]/'server.py')
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
class Catalog(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);s.ROOTS=[self.root/'movies',self.root/'tv'];s.DATA=self.root/'data'
        for root in s.ROOTS:root.mkdir()
        s.init()
    def tearDown(self):self.tmp.cleanup()
    def test_requested_release_name(self):
        p=s.ROOTS[1]/'The Lord of the Rings The Rings of Power (2022)'/'Season 01'/'The.Lord.of.the.Rings.The.Rings.of.Power.S01E02.1080p.WEBRip.x265-RARBG[eztv.re].mkv'
        m=s.infer(p)
        self.assertEqual(m['series'],'The Lord of the Rings The Rings of Power');self.assertEqual((m['season'],m['episode']),(1,2));self.assertEqual(m['year'],'2022')
        self.assertNotIn('1080',m['title']);self.assertNotIn('WEBRip',m['title'])
    def test_same_folder_different_release_names_one_show(self):
        base=s.ROOTS[1]/'Tulsa King (2022)'
        a=s.infer(base/'Season 1'/'Tulsa.King.S01E01.mkv');b=s.infer(base/'Season 2'/'Tulsa.King.2022.S02E01.1080p.mkv')
        self.assertEqual(a['show_key'],b['show_key']);self.assertEqual(a['series'],b['series'])
    def test_same_title_different_physical_folders_stay_separate(self):
        a=s.infer(s.ROOTS[1]/'The Office (2001)'/'Season 1'/'S01E01.mkv');b=s.infer(s.ROOTS[1]/'The Office (2005)'/'Season 1'/'S01E01.mkv')
        self.assertNotEqual(a['show_key'],b['show_key']);self.assertEqual(a['year'],'2001');self.assertEqual(b['year'],'2005')
    def test_season_folder_not_a_show(self):
        m=s.infer(s.ROOTS[1]/'Supernatural (2005)'/'Season 8'/'02.mkv')
        self.assertEqual(m['series'],'Supernatural');self.assertEqual((m['season'],m['episode']),(8,2))
    def test_release_subfolder(self):
        m=s.infer(s.ROOTS[1]/'Band of Brothers'/'Band.Of.Brothers.S01.YG'/'S01E01.mkv')
        self.assertEqual(m['series'],'Band of Brothers')
    def test_nfo_artwork_and_progress_preserved_on_rescan(self):
        directory=s.ROOTS[1]/'Test Show'/'Season 1';directory.mkdir(parents=True);p=directory/'Test.Show.S01E02.1080p.mkv';p.write_bytes(b'not video')
        (directory.parent/'tvshow.nfo').write_text('<tvshow><title>Canonical Show</title><plot>Series synopsis</plot><genre>Drama</genre><year>2020</year></tvshow>')
        p.with_suffix('.nfo').write_text('<episodedetails><title>Episode Name</title><plot>Episode synopsis</plot><season>1</season><episode>2</episode></episodedetails>')
        poster=directory.parent/'poster.jpg';poster.write_bytes(b'test image');s.scan()
        with s.database() as c:
            first=dict(c.execute('SELECT * FROM media').fetchone());c.execute("INSERT INTO users VALUES (1,'viewer','hash',0)");c.execute('INSERT INTO progress VALUES (1,?,80,100,0)',(first['id'],))
        s.scan()
        with s.database() as c:
            after=dict(c.execute('SELECT * FROM media').fetchone());progress=c.execute('SELECT position FROM progress').fetchone()[0]
        self.assertEqual(first['id'],after['id']);self.assertEqual(progress,80);self.assertEqual(after['series'],'Canonical Show');self.assertEqual(after['episode_title'],'Episode Name');self.assertEqual(s.artwork(after),poster)
    def test_dangerous_nfo_ignored(self):
        p=s.ROOTS[0]/'movie.nfo';p.write_text('<!DOCTYPE x [<!ENTITY a SYSTEM "file:///etc/passwd">]><movie><title>&a;</title></movie>')
        self.assertIsNone(s.read_nfo(p))
    def test_upgrade_existing_database(self):
        # Exercise ALTER migration against the exact v0.1 media schema.
        with s.database() as c:
            c.execute('DROP TABLE progress');c.execute('DROP TABLE media')
            c.execute("CREATE TABLE media(id INTEGER PRIMARY KEY,path TEXT UNIQUE NOT NULL,title TEXT,kind TEXT,series TEXT DEFAULT '',season INTEGER DEFAULT 0,episode INTEGER DEFAULT 0,year TEXT DEFAULT '',overview TEXT DEFAULT '',poster TEXT DEFAULT '',imdb TEXT DEFAULT '',duration REAL DEFAULT 0,size INTEGER,mtime REAL,added REAL,available INTEGER DEFAULT 1)")
            c.execute("INSERT INTO media(id,path,title) VALUES (45,'/preserve','Preserve me')")
        s.init();s.init()
        with s.database() as c:row=dict(c.execute('SELECT * FROM media WHERE id=45').fetchone())
        self.assertEqual(row['title'],'Preserve me');self.assertIn('show_key',row)
if __name__=='__main__':unittest.main()
