#!/usr/bin/env python3
"""StreamPort: self-hosted media server. Python 3.11+, FFmpeg, cryptography. No Jellyfin dependency."""
import xml.etree.ElementTree as ET
import gzip, io, zipfile
import metadata
import seer
import contextlib, hashlib, hmac, http.cookies, json, math, mimetypes, os, re, secrets
import shutil, sqlite3, subprocess, threading, time, urllib.error, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from cryptography.fernet import Fernet

BASE = Path(__file__).resolve().parent
DATA = Path(os.getenv('DATA_DIR', str(BASE / 'data'))).resolve()
ROOTS = [Path(p).resolve() for p in os.getenv('MEDIA_DIRS', '/media/movies:/media/tv').split(':') if p]
PORT = int(os.getenv('PORT', '8097'))
COOKIE_SECURE = os.getenv('COOKIE_SECURE', 'false').lower() == 'true'
VIDEO = {'.mkv', '.mp4', '.m4v', '.avi', '.mov', '.webm', '.ts', '.m2ts'}
LOCK = threading.Lock()
SCAN = {'running': False, 'count': 0, 'error': '', 'finished': None}
TRANSCODES = threading.BoundedSemaphore(int(os.getenv('MAX_TRANSCODES', '1')))
ACTIVE = {}; ACTIVE_LOCK = threading.Lock()
ATTEMPTS = {}; AUTH_LOCK = threading.Lock()
SUB_BASE = 'https://api.opensubtitles.com/api/v1'
OS_LOGIN_LOCK = threading.Lock()
THUMBNAIL_LOCK = threading.Lock()
DELETE_PREVIEWS = {}; DELETE_LOCK = threading.Lock()
SECRET_SETTINGS = {'seer_key','radarr_key','sonarr_key','os_key','os_token','os_password','tmdb_key','omdb_key','fanart_key'}

class Problem(Exception):
    def __init__(self, status, message): self.status, self.message = status, message

def public_media(item, admin):
    result=dict(item)
    result.pop('path',None)
    if not admin:
        for field in ('folder','library_root','size'):
            result.pop(field,None)
    return result

def thumbnail(item):
    path=safe_path(item['path'])
    stat=path.stat()
    key=hashlib.sha256(f'{item["id"]}:{stat.st_mtime_ns}:{stat.st_size}'.encode()).hexdigest()[:24]
    directory=DATA/'thumbnails'
    directory.mkdir(exist_ok=True,mode=0o700)
    target=directory/(key+'.jpg')
    if target.is_file():return target
    if not THUMBNAIL_LOCK.acquire(timeout=22):raise Problem(503,'Thumbnail generation is busy. Retry shortly.')
    try:
        if target.is_file():return target
        temporary=target.with_suffix('.tmp.jpg')
        seconds=min(90,max(0,float(item.get('duration') or 0)*.15))
        try:
            subprocess.run(['ffmpeg','-nostdin','-v','error','-threads','1','-ss',str(seconds),'-i',str(path),
                '-map','0:v:0','-frames:v','1','-vf','scale=480:270:force_original_aspect_ratio=decrease,pad=480:270:(ow-iw)/2:(oh-ih)/2',
                '-threads','1','-q:v','4','-y',str(temporary)],capture_output=True,timeout=12,check=True)
            if not temporary.is_file() or temporary.stat().st_size<100:raise Problem(422,'Could not generate thumbnail.')
            temporary.replace(target)
        except (OSError,subprocess.SubprocessError):raise Problem(422,'Could not generate thumbnail.')
        finally:temporary.unlink(missing_ok=True)
        return target
    finally:THUMBNAIL_LOCK.release()

def db():
    c = sqlite3.connect(DATA / 'streamport.db', timeout=30)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    return c

@contextlib.contextmanager
def database():
    c = db()
    try:
        with c: yield c
    finally: c.close()

def init():
    DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
    (DATA / 'subtitles').mkdir(exist_ok=True, mode=0o700)
    key_path=DATA/'secret.key'
    if not key_path.exists():
        with key_path.open('xb') as f: f.write(Fernet.generate_key())
    os.chmod(key_path,0o600)
    with database() as c:
        c.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, password TEXT NOT NULL, admin INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id INTEGER REFERENCES users(id) ON DELETE CASCADE, expires REAL);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS media(id INTEGER PRIMARY KEY, path TEXT UNIQUE NOT NULL, title TEXT, kind TEXT, series TEXT DEFAULT '', season INTEGER DEFAULT 0, episode INTEGER DEFAULT 0, year TEXT DEFAULT '', overview TEXT DEFAULT '', poster TEXT DEFAULT '', imdb TEXT DEFAULT '', duration REAL DEFAULT 0, size INTEGER, mtime REAL, added REAL, available INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS progress(user_id INTEGER REFERENCES users(id) ON DELETE CASCADE, media_id INTEGER REFERENCES media(id) ON DELETE CASCADE, position REAL, duration REAL, updated REAL, PRIMARY KEY(user_id,media_id));
        ''')
        c.executescript('''
        CREATE TABLE IF NOT EXISTS favorites(user_id INTEGER REFERENCES users(id) ON DELETE CASCADE, media_id INTEGER REFERENCES media(id) ON DELETE CASCADE, PRIMARY KEY(user_id,media_id));
        CREATE TABLE IF NOT EXISTS plays(user_id INTEGER REFERENCES users(id) ON DELETE CASCADE, media_id INTEGER REFERENCES media(id) ON DELETE CASCADE, count INTEGER DEFAULT 0, played REAL DEFAULT 0, PRIMARY KEY(user_id,media_id));
        ''')
        columns={r['name'] for r in c.execute('PRAGMA table_info(media)')}
        for name,kind in {'show_key':"TEXT DEFAULT ''",'folder':"TEXT DEFAULT ''",'library_root':"TEXT DEFAULT ''",'episode_title':"TEXT DEFAULT ''",'show_overview':"TEXT DEFAULT ''",'genres':"TEXT DEFAULT ''",'rating':"TEXT DEFAULT ''",'source':"TEXT DEFAULT ''",'codec':"TEXT DEFAULT ''",'resolution':"TEXT DEFAULT ''", 'kind_override':"TEXT DEFAULT ''",'tmdb_id':'INTEGER DEFAULT 0','backdrop':"TEXT DEFAULT ''",'logo':"TEXT DEFAULT ''",'still':"TEXT DEFAULT ''",'cast_json':"TEXT DEFAULT '[]'",'studios_json':"TEXT DEFAULT '[]'",'collection_id':"TEXT DEFAULT ''",'collection_name':"TEXT DEFAULT ''",'metadata_status':"TEXT DEFAULT ''",'metadata_checked':'REAL DEFAULT 0','release_date':"TEXT DEFAULT ''",'critic_rating':"TEXT DEFAULT ''",'parental_rating':"TEXT DEFAULT ''"}.items():
            if name not in columns: c.execute(f'ALTER TABLE media ADD COLUMN {name} {kind}')
    seer.initialize(database)
    os.chmod(DATA / 'streamport.db', 0o600)

def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    return salt + ':' + hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()

def valid_password(password):
    if not isinstance(password,str) or not 10 <= len(password) <= 256:
        raise Problem(400, 'Password must be 10–256 characters.')

def verify_sensitive(user, password):
    # Account-wide throttling also covers resets and deletion, across sessions.
    key='sensitive:'+str(user['id'])
    with AUTH_LOCK:
        history=[t for t in ATTEMPTS.get(key,[]) if t>time.time()-300]
        if len(history)>=8: raise Problem(429,'Too many password attempts. Wait five minutes.')
        history.append(time.time()); ATTEMPTS[key]=history
    if not isinstance(password,str) or len(password)>256: raise Problem(400,'Invalid password.')
    with database() as c: row=c.execute('SELECT password FROM users WHERE id=?',(user['id'],)).fetchone()
    if not row or not hmac.compare_digest(hash_password(password,row['password'].split(':')[0]),row['password']):
        raise Problem(403,'Incorrect current password.')
    with AUTH_LOCK: ATTEMPTS.pop(key,None)

def deletion_files(mid, scope):
    item=media_item(mid)
    if scope not in ('movie','series'): raise Problem(400,'Choose a movie or a whole series.')
    if scope=='movie':
        if item['kind']!='movie': raise Problem(400,'This item is not a movie.')
        rows=[item]
    else:
        if item['kind']!='episode': raise Problem(400,'This item is not a series.')
        key=item['show_key'] or item['series']
        if not key: raise Problem(400,'Identify this series first.')
        with database() as c:
            rows=[dict(r) for r in c.execute("SELECT * FROM media WHERE available=1 AND kind='episode' AND COALESCE(NULLIF(show_key,''),series)=? ORDER BY id",(key,))]
    result=[]
    for row in rows:
        raw=Path(row['path'])
        path=safe_path(raw)
        if raw.absolute()!=path or path.suffix.lower() not in VIDEO:
            raise Problem(403,'Deletion of symbolic links or non-video files is not supported.')
        st=path.stat()
        result.append({'id':row['id'],'path':str(path),'size':st.st_size,'mtime':st.st_mtime_ns,'inode':st.st_ino,'device':st.st_dev})
    return item,result

def prepare_deletion(user, mid, scope):
    if not user['admin']: raise Problem(403,'Administrator required.')
    if os.getenv('ALLOW_MEDIA_DELETE','false').lower()!='true':
        raise Problem(409,'Server deletion is disabled. Run: sudo bash enable-deletion.sh')
    if not LOCK.acquire(blocking=False): raise Problem(409,'Library scan is running. Try again shortly.')
    try: item,files=deletion_files(mid,scope)
    finally: LOCK.release()
    if not files: raise Problem(404,'No files to delete.')
    if not all(os.access(Path(f['path']).parent,os.W_OK) for f in files):
        raise Problem(409,'Media folders are read-only. Enable writable media mounts and check folder permissions.')
    token=secrets.token_urlsafe(32)
    with DELETE_LOCK:
        for key in list(DELETE_PREVIEWS):
            if DELETE_PREVIEWS[key]['expires']<time.time() or DELETE_PREVIEWS[key]['user']==user['id']: DELETE_PREVIEWS.pop(key)
        DELETE_PREVIEWS[token]={'user':user['id'],'expires':time.time()+180,'mid':mid,'scope':scope,'files':files}
    return {'token':token,'title':item['series'] if scope=='series' else item['title'],'count':len(files),
            'bytes':sum(f['size'] for f in files),'files':[f['path'] for f in files],'expires_in':180}

def confirm_deletion(user, token, password):
    if not user['admin']: raise Problem(403,'Administrator required.')
    if os.getenv('ALLOW_MEDIA_DELETE','false').lower()!='true': raise Problem(409,'Server deletion is disabled.')
    verify_sensitive(user,password)
    with DELETE_LOCK:
        preview=DELETE_PREVIEWS.get(str(token))
        if not preview or preview['user']!=user['id'] or preview['expires']<time.time():
            raise Problem(409,'Confirmation expired. Open the deletion preview again.')
        DELETE_PREVIEWS.pop(str(token))
    if not LOCK.acquire(blocking=False): raise Problem(409,'Library scan is running. Open a new preview shortly.')
    deleted=[]; failed=[]
    try:
        _,files=deletion_files(preview['mid'],preview['scope'])
        if files!=preview['files']: raise Problem(409,'Files changed since preview. Review a new preview before deleting.')
        for f in files:
            try:
                # Walk from a trusted root with O_NOFOLLOW directory descriptors.
                # Never follow a replaced parent symlink between preview and unlink.
                path=Path(f['path']); root,rel=location(path)
                fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                try:
                    for component in rel.parts[:-1]:
                        nxt=os.open(component,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
                        os.close(fd);fd=nxt
                    st=os.stat(rel.name,dir_fd=fd,follow_symlinks=False)
                    if (st.st_ino,st.st_dev,st.st_size,st.st_mtime_ns)!=(f['inode'],f['device'],f['size'],f['mtime']):
                        raise OSError('File changed')
                    os.unlink(rel.name,dir_fd=fd)
                finally:os.close(fd)
                with database() as c:c.execute('DELETE FROM media WHERE id=?',(f['id'],))
                deleted.append(f['id'])
            except OSError: failed.append(f['path'])
    finally:LOCK.release()
    return {'deleted':deleted,'failed':failed,'ok':not failed}

def cipher():
    return Fernet((DATA/'secret.key').read_bytes())

def settings():
    with database() as c: values={r['key']: json.loads(r['value']) for r in c.execute('SELECT * FROM settings')}
    for key in SECRET_SETTINGS:
        value=values.get(key,'')
        if isinstance(value,str) and value.startswith('enc:'): values[key]=cipher().decrypt(value[4:].encode()).decode()
    return values

def set_settings(values):
    with database() as c:
        for key, val in values.items():
            if key in SECRET_SETTINGS and val: val='enc:'+cipher().encrypt(str(val).encode()).decode()
            c.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (key, json.dumps(val)))


def safe_path(p):
    p = Path(p).resolve()
    if not any(p.is_relative_to(root) for root in ROOTS): raise Problem(403, 'File is outside mounted media libraries.')
    if not p.is_file(): raise Problem(404, 'Media file is unavailable. Check mounts and scan again.')
    return p

def media_item(mid):
    with database() as c: row = c.execute('SELECT * FROM media WHERE id=?', (mid,)).fetchone()
    if not row: raise Problem(404, 'Media not found.')
    item = dict(row); safe_path(item['path']); return item

def probe(path):
    try:
        p = subprocess.run(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(path)], capture_output=True, timeout=25, check=True)
        return json.loads(p.stdout)
    except (OSError, subprocess.SubprocessError, ValueError): return {'streams': [], 'format': {}}

def clean_title(text):
    text=re.sub(r'(?i)\{(?:tvdb|tmdb|imdb)[^}]*\}|\[[^]]*\]',' ',text)
    text=re.sub(r'[._]+',' ',text)
    text=re.split(r'(?i)\b(?:S\d{1,3}(?:E\d{1,3})?|\d{1,2}x\d{2}|480p|720p|1080[pi]|2160p|4k|WEB[ -]?(?:DL|Rip)|BluRay|BDRip|BRRip|HDTV|DVDRip|x26[45]|h[ .]?26[45]|HEVC|AV1)\b',text,maxsplit=1)[0]
    year=re.search(r'\b(19\d{2}|20\d{2})\b',text)
    if year and year.start()>0 and int(year[1])<=time.gmtime().tm_year+3:text=text[:year.start()]
    return re.sub(r'\s+',' ',text).strip(' -()[]')

def location(path):
    root=next((r for r in sorted(ROOTS,key=lambda x:len(x.parts),reverse=True) if path.is_relative_to(r)),path.parent)
    rel=path.relative_to(root)
    return root,rel

def show_directory(path):
    root,rel=location(path)
    parent=path.parent
    while parent!=root:
        name=parent.name
        if re.fullmatch(r'(?i)(?:season|series|s)[ ._-]*\d+|specials',name): parent=parent.parent;continue
        # Release folders have episode/season or codec suffixes; prefer their real show parent.
        if re.search(r'(?i)S\d+(?:E\d+)?|(?:720|1080|2160)p',name) and parent.parent!=root:
            parent=parent.parent;continue
        break
    return parent if parent!=root else None

def infer(path):
    stem=path.stem
    match=re.search(r'(?i)(?<![a-z0-9])S(\d{1,3})[ ._-]*E(\d{1,3})(?!\d)',stem)
    if not match: match=re.search(r'(?i)\b(\d{1,2})x(\d{2,3})\b',stem)
    root,rel=location(path)
    season_match=re.fullmatch(r'(?i)(?:season|s)[ ._-]*(\d+)',path.parent.name)
    episode_nfo=read_nfo(path.with_suffix('.nfo'))
    is_tv=bool(match or season_match or (episode_nfo is not None and episode_nfo.tag=='episodedetails'))
    directory=show_directory(path) if is_tv else None
    series=clean_title(directory.name) if directory else clean_title(stem)
    year=re.search(r'\b(19\d{2}|20\d{2})\b',directory.name if directory else stem)
    episode=int(match[2]) if match else 0
    if not match and is_tv:
        ep=re.match(r'(?i)(?:episode[ ._-]*|e)?(\d{1,3})(?:[ ._-]|$)',stem)
        if ep: episode=int(ep[1])
    return {'title':clean_title(stem) or series or 'Untitled','kind':'episode' if is_tv else 'movie','series':series if is_tv else '',
            'season':int(match[1]) if match else int(season_match[1]) if season_match else 0,'episode':episode,'year':year[1] if year else '',
            'show_key':'folder:'+hashlib.sha256(str(directory or root).encode()).hexdigest()[:24] if is_tv and directory else 'name:'+series.casefold() if is_tv else '',
            'folder':str(rel.parent) if str(rel.parent)!='.' else '', 'library_root':str(ROOTS.index(root)) if root in ROOTS else '0'}

def read_nfo(path):
    try:
        safe_path(path)
        if path.stat().st_size>2_000_000:return None
        raw=path.read_bytes()
        if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():return None
        return ET.fromstring(raw)
    except (OSError,ET.ParseError,Problem):return None

def local_metadata(path,meta):
    directory=show_directory(path) if meta['kind']=='episode' else path.parent
    show=read_nfo(directory/'tvshow.nfo') if directory and meta['kind']=='episode' else None
    detail=read_nfo(path.with_suffix('.nfo'))
    if detail is None and meta['kind']=='movie':detail=read_nfo(path.parent/'movie.nfo')
    data={}
    if show is not None:
        data.update(series=show.findtext('title') or meta['series'],show_overview=show.findtext('plot') or '')
    main=show if show is not None else detail
    if main is not None:
        data.update(year=main.findtext('year') or meta['year'],genres=', '.join(x.text or '' for x in main.findall('genre')),rating=main.findtext('rating') or '',release_date=main.findtext('premiered') or main.findtext('releasedate') or '',parental_rating=main.findtext('mpaa') or '',critic_rating=main.findtext('criticrating') or '')
    if detail is not None:
        data['overview']=detail.findtext('plot') or ''
        if meta['kind']=='episode':data['episode_title']=detail.findtext('title') or ''
        else:data['title']=detail.findtext('title') or meta['title']
        for key in ('season','episode'):
            text=detail.findtext(key)
            if text and text.isdigit():data[key]=int(text)
    if data:data['source']='nfo'
    return data

def update_catalog(path,media_id,probed=None):
    meta=infer(path)
    with database() as c:
        old=dict(c.execute('SELECT * FROM media WHERE id=?',(media_id,)).fetchone())
        update={k:meta[k] for k in ('folder','library_root')}
        if old['source'] not in ('radarr','sonarr','tmdb'):
            update.update(meta);update.update(local_metadata(path,meta))
        if old.get('kind_override'):
            update['kind']=old['kind_override']
            if old['kind_override']=='movie':update.update(series='',show_key='',season=0,episode=0,episode_title='')
        if probed:
            v=next((v for v in probed.get('streams',[]) if v.get('codec_type')=='video'),{})
            update.update(codec=v.get('codec_name','').upper(),resolution=str(v.get('height',''))+'p' if v.get('height') else '')
        c.execute('UPDATE media SET '+','.join(k+'=?' for k in update)+' WHERE id=?',(*update.values(),media_id))

def artwork(item):
    try:path=safe_path(item['path'])
    except Problem:return None
    directory=show_directory(path) if item['kind']=='episode' else path.parent
    candidates=[]
    for parent in [directory,path.parent]:
        if parent:
            for stem in ('poster','folder','cover'):
                for ext in ('.jpg','.png','.jpeg','.webp'):candidates.append(parent/(stem+ext))
    for ext in ('.jpg','.png','.jpeg','.webp'):candidates.append(path.with_name(path.stem+'-poster'+ext))
    for candidate in candidates:
        try:return safe_path(candidate)
        except Problem:continue
    return None


def scan():
    if not LOCK.acquire(blocking=False): return
    SCAN.update(running=True, count=0, error='')
    seen = []
    try:
        if not all(root.is_dir() for root in ROOTS):
            raise Problem(400, 'A media directory is missing. Check your Docker mounts.')
        for root in ROOTS:
            for p in root.rglob('*'):
                if p.suffix.lower() not in VIDEO or not p.is_file(): continue
                try: p = safe_path(p)
                except Problem: continue
                probed=None
                st = p.stat(); path = str(p); seen.append(path)
                with database() as c: old = c.execute('SELECT id,mtime,size FROM media WHERE path=?', (path,)).fetchone()
                if old and old['mtime'] == st.st_mtime and old['size'] == st.st_size:
                    with database() as c: c.execute('UPDATE media SET available=1 WHERE id=?', (old['id'],))
                else:
                    meta = infer(p); probed=probe(p); duration = float(probed.get('format',{}).get('duration',0) or 0)
                    with database() as c:
                        if old: c.execute('UPDATE media SET duration=?,size=?,mtime=?,available=1 WHERE id=?', (duration,st.st_size,st.st_mtime,old['id']))
                        else: c.execute('INSERT INTO media(path,title,kind,series,season,episode,year,duration,size,mtime,added) VALUES (?,?,?,?,?,?,?,?,?,?,?)', (path,meta['title'],meta['kind'],meta['series'],meta['season'],meta['episode'],meta['year'],duration,st.st_size,st.st_mtime,time.time()))
                with database() as c: mid=c.execute('SELECT id FROM media WHERE path=?',(path,)).fetchone()['id']
                update_catalog(p,mid,probed)
                SCAN['count'] += 1
        with database() as c:
            # Temp table avoids SQLite parameter limits for large libraries.
            c.execute('CREATE TEMP TABLE scanned(path TEXT PRIMARY KEY)')
            c.executemany('INSERT OR IGNORE INTO scanned VALUES (?)', ((p,) for p in seen))
            c.execute('UPDATE media SET available=0 WHERE path NOT IN (SELECT path FROM scanned)')
        SCAN['finished'] = time.time()
    except Exception as e: SCAN['error'] = e.message if isinstance(e,Problem) else 'Scan failed. Check media permissions and server logs.'
    finally: SCAN['running'] = False; LOCK.release()

def request_json(url, method='GET', payload=None, headers=None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method, headers={'Accept':'application/json','Content-Type':'application/json', **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=25) as r:
            blob = r.read(8_000_001)
            if len(blob)>8_000_000: raise Problem(502, 'Upstream response is too large.')
            return json.loads(blob)
    except urllib.error.HTTPError as e:
        error=Problem(502, f'Provider returned HTTP {e.code}. Check credentials, API key and download/rate limits.')
        error.upstream_status=e.code
        raise error
    except (urllib.error.URLError, TimeoutError, ValueError):
        raise Problem(502, 'Integration is unavailable or returned invalid data. Check its URL and connection.')

def arr(service, resource):
    if service not in ('radarr','sonarr'): raise Problem(404, 'Unknown integration.')
    s = settings(); url = s.get(service+'_url','').rstrip('/'); key = s.get(service+'_key','')
    if not url or not key: raise Problem(400, f'Configure {service.title()} URL and API key first.')
    return request_json(url+'/api/v3/'+resource, headers={'X-Api-Key':key})

def mapped_path(path, service, s):
    old = s.get(service+'_remote_path','').rstrip('/'); new = s.get(service+'_local_path','').rstrip('/')
    if old and new and (path == old or path.startswith(old+'/')): return new+path[len(old):]
    return path

def poster(meta):
    for im in meta.get('images',[]):
        u=im.get('remoteUrl','')
        if im.get('coverType') == 'poster' and u.startswith('https://'): return u
    return ''

def sync_arr(service):
    s=settings();updates=[];missing=0
    records=arr(service,'movie' if service=='radarr' else 'series')
    for rec in records:
        episodes={}
        if service=='radarr':
            f=rec.get('movieFile') or {};files=[f] if f.get('path') else []
        else:
            files=arr(service,'episodefile?seriesId='+str(int(rec['id'])))
            for ep in arr(service,'episode?seriesId='+str(int(rec['id']))):
                if ep.get('episodeFileId'):episodes.setdefault(ep['episodeFileId'],[]).append(ep)
        for f in files:
            if not f.get('path'):continue
            local=str(Path(mapped_path(f['path'],service,s)).resolve())
            with database() as c:
                row=c.execute('SELECT * FROM media WHERE path=?',(local,)).fetchone()
                if not row:missing+=1;continue
                if row['source']=='tmdb' or row['kind_override']:continue
                update={'year':str(rec.get('year','')),'poster':poster(rec),'imdb':rec.get('imdbId',''),'genres':', '.join(rec.get('genres',[])),'source':service}
                rating=rec.get('ratings',{})
                if 'value' in rating:update['rating']=str(rating['value'])
                elif isinstance(rating.get('imdb'),dict):update['rating']=str(rating['imdb'].get('value',''))
                if service=='radarr':update.update(tmdb_id=int(rec.get('tmdbId',0) or 0),title=rec.get('title',''),overview=rec.get('overview',''),kind='movie')
                else:
                    update.update(series=rec.get('title',''),show_key=infer(Path(local))['show_key'],show_overview=rec.get('overview',''),kind='episode')
                    eps=sorted(episodes.get(f.get('id'),[]),key=lambda e:e.get('episodeNumber',0))
                    if eps:
                        update.update(episode_title=' / '.join(e.get('title','') for e in eps),overview='\n\n'.join(e.get('overview','') for e in eps),season=eps[0].get('seasonNumber',row['season']),episode=eps[0].get('episodeNumber',row['episode']))
                    else:update.update(episode_title=row['episode_title'],overview=row['overview'])
                c.execute('UPDATE media SET '+','.join(k+'=?' for k in update)+' WHERE id=?',(*update.values(),row['id']))
                updates.append(row['id'])
    return {'updated':len(updates),'unmatched':missing}


def os_headers(auth=False):
    s=settings(); key=s.get('os_key') or os.getenv('OPENSUBTITLES_API_KEY','')
    if not key: raise Problem(400,'Add an OpenSubtitles application API key in Settings first.')
    headers={'Api-Key':key,'User-Agent':os.getenv('OPENSUBTITLES_USER_AGENT','StreamPort v0.1.0')}
    if auth:
        if not s.get('os_token') or s.get('os_expires',0)<time.time():
            with OS_LOGIN_LOCK:
                s=settings()
                if not s.get('os_token') or s.get('os_expires',0)<time.time():
                    if not s.get('os_username') or not s.get('os_password'): raise Problem(401,'Sign in to OpenSubtitles in Settings.')
                    os_login(s['os_username'],s['os_password'])
                s=settings()
        headers['Authorization']='Bearer '+s['os_token']
    return headers

def os_login(username,password):
    result=request_json(SUB_BASE+'/login','POST',{'username':username,'password':password},os_headers())
    if not result.get('token'): raise Problem(502,'OpenSubtitles did not return a session token.')
    host=result.get('base_url','api.opensubtitles.com')
    if host.startswith('https://'): host=urllib.parse.urlsplit(host).hostname
    if not isinstance(host,str) or not re.fullmatch(r'(?:[a-z0-9-]+\.)*opensubtitles\.com',host): host='api.opensubtitles.com'
    set_settings({'os_token':result['token'],'os_expires':time.time()+23*3600,'os_host':host,'os_username':username,'os_password':password})

def os_base():
    host=settings().get('os_host','api.opensubtitles.com')
    if not re.fullmatch(r'(?:[a-z0-9-]+\.)*opensubtitles\.com',host): host='api.opensubtitles.com'
    return 'https://'+host+'/api/v1'

def os_authenticated_request(resource,method='GET',payload=None):
    """Retry an explicit authentication rejection once, never ambiguous failures."""
    headers=os_headers(True)
    try:
        return request_json(os_base()+resource,method,payload,headers)
    except Problem as e:
        if getattr(e,'upstream_status',None)!=401:raise
    rejected=headers.get('Authorization')
    with OS_LOGIN_LOCK:
        saved=settings()
        # Another request may already have refreshed the rejected token.
        if not saved.get('os_token') or 'Bearer '+saved['os_token']==rejected:
            if not saved.get('os_username') or not saved.get('os_password'):
                raise Problem(401,'OpenSubtitles session expired. Sign in again under Settings → OpenSubtitles.')
            try:os_login(saved['os_username'],saved['os_password'])
            except Problem as e:
                if getattr(e,'upstream_status',None)==401:
                    raise Problem(401,'OpenSubtitles sign-in was rejected. Check your saved account credentials and application API key in Settings.')
                raise
    # Rebuild the base URL too: login can return a different download API host.
    try:
        return request_json(os_base()+resource,method,payload,os_headers(True))
    except Problem as e:
        if getattr(e,'upstream_status',None)==401:
            raise Problem(401,'OpenSubtitles rejected the renewed session. Check your account and application API key in Settings.')
        raise

def number(v, lo=0, hi=864000):
    try: value=float(v)
    except (ValueError,TypeError): raise Problem(400,'Invalid number.')
    if not math.isfinite(value) or not lo<=value<=hi: raise Problem(400,'Number is outside permitted range.')
    return value

def subtitles(item):
    p=safe_path(item['path']); found=[]
    for f in sorted(p.parent.iterdir()):
        if f.suffix.lower() not in ('.srt','.vtt','.ass','.ssa'): continue
        if f.stem==p.stem or f.stem.startswith(p.stem+'.'):
            try: safe_path(f)
            except Problem: continue
            found.append({'label':f.name,'path':str(f)})
    for f in sorted((DATA/'subtitles').glob(str(item['id'])+'.*.vtt')):
        found.append({'label':f.name.split('.',1)[1],'path':str(f)})
    return found

def subtitle_version(path):
    stat=path.stat()
    return f'{stat.st_mtime_ns}:{stat.st_size}'

SUB_SHIFT_LOCK=threading.Lock()
def save_subtitle_shift(item,b):
    delta=number(b.get('seconds'),-600,600)
    with SUB_SHIFT_LOCK:
        matches=[Path(x['path']) for x in subtitles(item) if Path(x['path']).name==b.get('key')]
        if len(matches)!=1:raise Problem(409,'Select the subtitle again before saving.')
        path=matches[0]
        if path.is_symlink():raise Problem(400,'Cannot replace a linked subtitle.')
        if path.suffix.lower() not in ('.srt','.vtt'):raise Problem(400,'Save to file supports SRT and VTT only. Live sync still works.')
        if subtitle_version(path)!=b.get('version'):raise Problem(409,'Subtitle changed. Reopen it before saving.')
        blob=path.read_bytes()
        if len(blob)>5_000_000:raise Problem(413,'Subtitle is too large.')
        for encoding in ('utf-8-sig','cp1250','latin-1'):
            try:text=blob.decode(encoding);break
            except UnicodeDecodeError:continue
        stamp=r'(?:\d{1,3}:)?\d{2}:\d{2}[.,]\d{3}'
        pattern=re.compile(r'^(?P<lead>[ \t]*)(?P<a>'+stamp+r')(?P<arrow>[ \t]+-->[ \t]+)(?P<b>'+stamp+r')(?P<tail>[^\r\n]*)',re.M)
        def shift(raw):
            parts=raw.replace(',', '.').split(':');t=float(parts[-1])+int(parts[-2])*60+(int(parts[0])*3600 if len(parts)==3 else 0)
            ms=max(0,round((t+delta)*1000));h,ms=divmod(ms,3600000);m,ms=divmod(ms,60000);sec,ms=divmod(ms,1000)
            sep=',' if ',' in raw else '.'
            return f'{h:02}:{m:02}:{sec:02}{sep}{ms:03}'
        result,count=pattern.subn(lambda m:m['lead']+shift(m['a'])+m['arrow']+shift(m['b'])+m['tail'],text)
        if not count:raise Problem(422,'No subtitle timings found.')
        backup=path.with_name(path.name+'.'+str(time.time_ns())+'.bak')
        temp=path.with_name('.'+path.name+'.'+secrets.token_hex(8)+'.tmp')
        try:
            shutil.copy2(path,backup)
            with temp.open('xb') as f:
                f.write(result.encode('utf-8'));f.flush();os.fsync(f.fileno())
            shutil.copymode(path,temp);os.replace(temp,path)
        except OSError:raise Problem(409,'Cannot write subtitle. Check the media mount permissions. Live sync is still available.')
        finally:temp.unlink(missing_ok=True)
        return {'ok':True,'version':subtitle_version(path),'backup':backup.name}

SUB_LOCK=threading.Lock()
def subtitle_url(url):
    u=urllib.parse.urlsplit(url)
    allowed=('opensubtitles.com','opensubtitles.org')
    if u.scheme!='https' or not u.hostname or u.username or u.password or u.port not in (None,443) or not any(u.hostname==d or u.hostname.endswith('.'+d) for d in allowed):
        raise Problem(502,'Subtitle provider returned an unsupported download host. No file was saved.')
    return url

def fetch_subtitle(link):
    class CheckedRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,req,fp,code,msg,headers,newurl):
            subtitle_url(newurl)
            return super().redirect_request(req,fp,code,msg,headers,newurl)
    try:
        request=urllib.request.Request(subtitle_url(link),headers={
            'User-Agent':os.getenv('OPENSUBTITLES_USER_AGENT','StreamPort v0.1.0'),
            'Accept':'application/x-subrip, text/vtt, text/plain, application/octet-stream, */*',
        })
        with urllib.request.build_opener(CheckedRedirect).open(request,timeout=30) as response:
            blob=response.read(5_000_001)
    except urllib.error.HTTPError as e:
        host=urllib.parse.urlsplit(e.url).hostname or 'unknown host'
        if e.code==403:
            detail='The file server refused the download after the API supplied a link. This does not confirm a quota problem.'
        elif e.code==429:
            detail='The file server is rate limiting downloads. Wait before trying again.'
        elif e.code in (404,410):
            detail='The download link is unavailable or expired. Search again and retry.'
        else:detail='The subtitle file server could not complete the download.'
        raise Problem(502,f'Subtitle file download returned HTTP {e.code} from {host}. {detail}')
    except (urllib.error.URLError,TimeoutError):raise Problem(502,'Could not retrieve the subtitle file. Check server internet access.')
    if len(blob)>5_000_000:raise Problem(413,'Subtitle file exceeds 5 MB.')
    try:
        if blob.startswith(b'\x1f\x8b'):
            with gzip.GzipFile(fileobj=io.BytesIO(blob)) as f:blob=f.read(5_000_001)
        elif blob.startswith(b'PK'):
            with zipfile.ZipFile(io.BytesIO(blob)) as z:
                candidate=next((x for x in z.infolist() if x.filename.lower().endswith(('.srt','.vtt')) and not x.is_dir()),None)
                if not candidate:raise Problem(422,'Downloaded archive contains no text subtitles.')
                if candidate.file_size>5_000_000:raise Problem(413,'Expanded subtitle is too large.')
                with z.open(candidate) as f:blob=f.read(5_000_001)
    except (OSError,zipfile.BadZipFile):raise Problem(422,'Invalid subtitle archive.')
    if len(blob)>5_000_000:raise Problem(413,'Expanded subtitle is too large.')
    return blob

def to_vtt(blob,language='en'):
    encoding='utf-16' if blob.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig'
    try:text=blob.decode(encoding)
    except UnicodeDecodeError:text=blob.decode('cp1251' if language=='ru' else 'cp1250',errors='replace')
    text=text.lstrip('\ufeff \r\n').replace('\r\n','\n')
    if text.startswith('WEBVTT'):out=text.encode('utf-8')
    else:
        try:out=subprocess.run(['ffmpeg','-v','error','-f','srt','-i','pipe:0','-f','webvtt','pipe:1'],input=text.encode('utf-8'),capture_output=True,check=True,timeout=20).stdout
        except (OSError,subprocess.SubprocessError):raise Problem(422,'Provider returned a subtitle format that could not be converted.')
    if not out.startswith(b'WEBVTT') or b'-->' not in out:raise Problem(422,'Downloaded file contains no valid subtitle cues.')
    return out

def download_subtitle(item,file_id,language):
    if not re.fullmatch('[a-z]{2,3}(?:-[a-z]{2})?',language) or file_id<=0:raise Problem(400,'Invalid subtitle selection.')
    dest=DATA/'subtitles'/f'{item["id"]}.{language}.{file_id}.vtt'
    # Serialize downloads and check existing files before consuming another quota.
    with SUB_LOCK:
        if dest.is_file() and 10<dest.stat().st_size<=5_000_000 and b'-->' in dest.read_bytes():return {'ok':True,'key':dest.name,'cached':True}
        result=os_authenticated_request('/download','POST',{'file_id':file_id,'sub_format':'srt'})
        blob=to_vtt(fetch_subtitle(result.get('link','')),language)
        temporary=dest.with_name(dest.name+'.'+secrets.token_hex(4)+'.tmp')
        try:
            temporary.write_bytes(blob);os.replace(temporary,dest)
        except OSError:raise Problem(500,'Subtitle could not be saved. Check the data/subtitles directory permissions.')
        finally:temporary.unlink(missing_ok=True)
        return {'ok':True,'key':dest.name,'remaining':result.get('remaining'),'cached':False}

class Handler(BaseHTTPRequestHandler):
    server_version='StreamPort/0.3'
    def log_message(self, fmt, *args): pass # Avoid credentials and query strings in logs.
    def headers_common(self):
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' https: data:; style-src 'self'; script-src 'self'; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        self.send_header('Cache-Control','no-store')
    def send_json(self, value, status=200, cookie=None):
        payload=json.dumps(value).encode(); self.send_response(status); self.headers_common()
        self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(payload)))
        if cookie: self.send_header('Set-Cookie',cookie)
        self.end_headers(); self.wfile.write(payload)
    def body(self):
        size=int(self.headers.get('Content-Length','0'))
        if size<0: raise Problem(400,'Invalid content length.')
        if size>65536: raise Problem(413,'Request too large.')
        if self.headers.get('Content-Type','').split(';')[0]!='application/json': raise Problem(415,'JSON required.')
        try: data=json.loads(self.rfile.read(size))
        except (ValueError,UnicodeError): raise Problem(400,'Invalid JSON.')
        if not isinstance(data,dict): raise Problem(400,'Expected a JSON object.')
        return data
    def user(self, admin=False):
        cookie=http.cookies.SimpleCookie()
        try: cookie.load(self.headers.get('Cookie',''))
        except http.cookies.CookieError: raise Problem(401,'Sign in required.')
        token=cookie.get('streamport')
        if not token: raise Problem(401,'Sign in required.')
        with database() as c:
            row=c.execute('SELECT u.id,u.name,u.admin FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires>?',(hashlib.sha256(token.value.encode()).hexdigest(),time.time())).fetchone()
        if not row: raise Problem(401,'Session expired. Sign in again.')
        if admin and not row['admin']: raise Problem(403,'Administrator required.')
        return dict(row)
    def csrf(self):
        if self.headers.get('X-StreamPort')!='1': raise Problem(403,'Missing request protection header.')
        origin=self.headers.get('Origin')
        if origin and urllib.parse.urlsplit(origin).netloc != self.headers.get('Host'): raise Problem(403,'Cross-origin request rejected.')
    def setup(self):
        super().setup()
        self.connection.settimeout(30)
    def do_GET(self): self.run(False)
    def do_POST(self): self.run(True)
    def run(self, write):
        try:
            parsed=urllib.parse.urlsplit(self.path); path=parsed.path; q=urllib.parse.parse_qs(parsed.query)
            if write: self.csrf(); self.post(path,self.body())
            else: self.get(path,q)
        except Problem as e: self.send_json({'error':e.message},e.status)
        except (BrokenPipeError,ConnectionResetError): pass
        except (ValueError,TypeError,KeyError,OverflowError): self.send_json({'error':'Invalid request parameters.'},400)
        except Exception as e:
            print('Server error:',type(e).__name__,flush=True)
            self.send_json({'error':'Server error. Check server logs and filesystem permissions.'},500)
    def get(self,path,q):
        if path=='/api/health': return self.send_json({'status':'ok','version':'0.7.5'})
        if path=='/api/bootstrap':
            with database() as c: exists=bool(c.execute('SELECT 1 FROM users LIMIT 1').fetchone())
            return self.send_json({'setup':not exists})
        if path in ('/','/app.js','/enhancements.js','/search.js','/features.js','/features.css','/polish.css','/polish.js','/modern.css','/modern.js','/requests.js','/requests.css','/playback-extra.js','/subtitle-sync.js','/subtitle-sync.css','/style.css','/icon.svg','/manifest.webmanifest'):
            p=BASE/'static'/('index.html' if path=='/' else path[1:]); return self.file(p)
        user=self.user()
        if path.startswith('/api/requests'):
            return self.send_json(seer.get(path,q,user,database,settings,request_json,Problem))
        if path=='/api/me':
            user['subtitle_language']=settings().get('subtitle_language','sr')
            return self.send_json(user)
        if path=='/api/library':
            with database() as c:
                rows=c.execute('SELECT m.*,COALESCE(p.position,0) position,COALESCE(p.duration,0) watched_duration,p.updated,EXISTS(SELECT 1 FROM favorites f WHERE f.user_id=puser.id AND f.media_id=m.id) favorite,COALESCE((SELECT count FROM plays WHERE user_id=puser.id AND media_id=m.id),0) play_count,(SELECT played FROM plays WHERE user_id=puser.id AND media_id=m.id) last_played FROM media m CROSS JOIN (SELECT ? id) puser LEFT JOIN progress p ON p.media_id=m.id AND p.user_id=? WHERE m.available=1 ORDER BY m.added DESC',(user['id'],user['id'])).fetchall()
            data=[]
            for row in rows:
                r=dict(row); r['poster']='/api/media/'+str(r['id'])+'/artwork' if artwork(r) else r['poster']; data.append(public_media(r,user['admin']))
            return self.send_json(data)
        if path=='/api/metadata/status':
            self.user(True)
            return self.send_json(dict(provider.status))
        if path=='/api/dashboard':
            self.user(True)
            with database() as c:
                counts=dict(c.execute("SELECT COUNT(*) files,COALESCE(SUM(size),0) bytes,COALESCE(SUM(kind='movie'),0) movies,COUNT(DISTINCT CASE WHEN kind='episode' THEN series END) shows FROM media WHERE available=1").fetchone())
            counts.update(scan=dict(SCAN))
            if user['admin']:
                counts.update(disk_free=shutil.disk_usage(DATA).free, active_streams=len(ACTIVE), ffmpeg=bool(shutil.which('ffmpeg')), roots=[str(p) for p in ROOTS])
            return self.send_json(counts)
        if path=='/api/settings':
            self.user(True); s=settings()
            public={k:v for k,v in s.items() if not any(secret in k for secret in ('key','token','password'))}
            public.update({k+'_set':bool(s.get(k) or (os.getenv('OPENSUBTITLES_API_KEY') if k=='os_key' else '')) for k in ('seer_key','radarr_key','sonarr_key','os_key','tmdb_key','omdb_key','fanart_key')})
            public['os_connected']=bool(s.get('os_username') and s.get('os_password'))
            return self.send_json(public)
        if path=='/api/users':
            self.user(True)
            with database() as c: return self.send_json([dict(r) for r in c.execute('SELECT id,name,admin FROM users')])
        m=re.fullmatch(r'/api/media/(\d+)(?:/(probe|subtitles|subtitle|stream|transcode|artwork|thumbnail))?',path)
        if m:
            item=media_item(int(m[1])); action=m[2]
            if action=='thumbnail':return self.file(thumbnail(item),'image/jpeg')
            if action=='artwork':
                art=artwork(item)
                if not art:raise Problem(404,'No local artwork.')
                return self.file(art)
            if action=='probe':
                result=probe(item['path'])
                if not user['admin']:
                    result={'streams':[{k:v for k,v in stream.items() if k in ('index','codec_name','codec_type','width','height','channels','sample_rate','disposition')} | {'tags':{'language':stream.get('tags',{}).get('language','')}} for stream in result.get('streams',[])],
                            'format':{'duration':result.get('format',{}).get('duration','')}}
                return self.send_json(result)
            if action=='subtitles': return self.send_json([{'index':i,'label':s['label'],'key':Path(s['path']).name,'version':subtitle_version(Path(s['path']))} for i,s in enumerate(subtitles(item))])
            if action=='subtitle':
                idx=int(q.get('index',['0'])[0]); subs=subtitles(item)
                if not 0<=idx<len(subs): raise Problem(404,'Subtitle not found.')
                f=Path(subs[idx]['path'])
                if f.suffix.lower()=='.vtt': return self.file(f,'text/vtt; charset=utf-8')
                try: result=subprocess.run(['ffmpeg','-v','error','-i',str(f),'-f','webvtt','pipe:1'],capture_output=True,timeout=20,check=True)
                except (OSError,subprocess.SubprocessError): raise Problem(422,'Could not convert this subtitle to WebVTT.')
                self.send_response(200); self.headers_common(); self.send_header('Content-Type','text/vtt; charset=utf-8'); self.send_header('Content-Length',str(len(result.stdout))); self.end_headers(); self.wfile.write(result.stdout); return
            if action=='stream': return self.file(safe_path(item['path']),media=True)
            if action=='transcode': return self.transcode(item,q,user)
            return self.send_json(public_media(item,user['admin']))
        raise Problem(404,'Not found.')
    def post(self,path,b):
        if path in ('/api/setup','/api/login'):
            name=str(b.get('name','')).strip(); password=b.get('password','')
            if not isinstance(password,str) or len(password)>256 or not 1<=len(name)<=60: raise Problem(400,'Invalid name or password.')
            key=self.client_address[0]
            with AUTH_LOCK:
                history=[t for t in ATTEMPTS.get(key,[]) if t>time.time()-300]
                if len(history)>=15: raise Problem(429,'Too many attempts. Wait five minutes.')
                history.append(time.time()); ATTEMPTS[key]=history
            with database() as c:
                if path=='/api/setup':
                    valid_password(password)
                    c.execute('BEGIN IMMEDIATE')
                    if c.execute('SELECT 1 FROM users LIMIT 1').fetchone(): raise Problem(409,'Already configured.')
                    c.execute('INSERT INTO users(name,password,admin) VALUES (?,?,1)',(name,hash_password(password)))
                row=c.execute('SELECT * FROM users WHERE name=?',(name,)).fetchone()
                digest=hash_password(password,row['password'].split(':')[0] if row else '00'*16)
                if not row or not hmac.compare_digest(digest,row['password']): raise Problem(401,'Incorrect username or password.')
                token=secrets.token_urlsafe(32); token_hash=hashlib.sha256(token.encode()).hexdigest()
                c.execute('DELETE FROM sessions WHERE expires<?',(time.time(),))
                c.execute('INSERT INTO sessions VALUES (?,?,?)',(token_hash,row['id'],time.time()+7*86400))
            with AUTH_LOCK: ATTEMPTS.pop(key,None)
            cookie='streamport='+token+'; HttpOnly; SameSite=Strict; Path=/; Max-Age=604800'+('; Secure' if COOKIE_SECURE else '')
            return self.send_json({'ok':True},cookie=cookie)
        user=self.user()
        if path.startswith('/api/requests'):
            return self.send_json(seer.post(path,b,user,database,settings,request_json,Problem))
        if path=='/api/logout':
            cookie=http.cookies.SimpleCookie(self.headers.get('Cookie','')); token=cookie.get('streamport')
            if token:
                with database() as c: c.execute('DELETE FROM sessions WHERE token=?',(hashlib.sha256(token.value.encode()).hexdigest(),))
            return self.send_json({'ok':True},cookie='streamport=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
        if path=='/api/account/password':
            verify_sensitive(user,b.get('current_password'))
            password=b.get('new_password');valid_password(password)
            with database() as c:
                c.execute('UPDATE users SET password=? WHERE id=?',(hash_password(password),user['id']))
                c.execute('DELETE FROM sessions WHERE user_id=?',(user['id'],))
            return self.send_json({'ok':True},cookie='streamport=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
        if path=='/api/favorites':
            item=media_item(int(b['id']))
            if item['kind']!='movie':raise Problem(400,'Only movies can be added to favorites.')
            if type(b.get('favorite')) is not bool:raise Problem(400,'Expected favorite true or false.')
            with database() as c:
                if b['favorite']:c.execute('INSERT OR IGNORE INTO favorites VALUES (?,?)',(user['id'],item['id']))
                else:c.execute('DELETE FROM favorites WHERE user_id=? AND media_id=?',(user['id'],item['id']))
            return self.send_json({'ok':True,'favorite':b['favorite']})
        if path=='/api/played':
            item=media_item(int(b['id']))
            with database() as c:
                row=c.execute('SELECT played FROM plays WHERE user_id=? AND media_id=?',(user['id'],item['id'])).fetchone()
                if not row or time.time()-row['played']>60:
                    c.execute('INSERT INTO plays VALUES (?,?,1,?) ON CONFLICT(user_id,media_id) DO UPDATE SET count=count+1,played=excluded.played',(user['id'],item['id'],time.time()))
            return self.send_json({'ok':True})
        if path=='/api/progress':
            item=media_item(int(b['id'])); position=number(b['position']); duration=number(b.get('duration',item['duration']))
            if duration: position=min(position,duration)
            with database() as c: c.execute('INSERT OR REPLACE INTO progress VALUES (?,?,?,?,?)',(user['id'],item['id'],position,duration,time.time()))
            return self.send_json({'ok':True})
        if path=='/api/subtitles/shift':
            self.user(True)
            return self.send_json(save_subtitle_shift(media_item(int(b['id'])),b))
        if path=='/api/subtitles/search':
            item=media_item(int(b['id'])); language=str(b.get('language','en'))
            if not re.fullmatch('[a-z]{2,3}(?:-[a-z]{2})?',language): raise Problem(400,'Invalid subtitle language.')
            query={'languages':language,'query':item['series'] or item['title'],'order_by':'download_count','order_direction':'desc'}
            if item['imdb']: query['imdb_id']=item['imdb'].removeprefix('tt')
            if item['kind']=='episode': query.update(season_number=item['season'],episode_number=item['episode'],type='episode')
            else: query['type']='movie'
            result=request_json(os_base()+'/subtitles?'+urllib.parse.urlencode(query),headers=os_headers())
            return self.send_json(result.get('data',[]))
        if path=='/api/subtitles/download':
            return self.send_json(download_subtitle(media_item(int(b['id'])),int(b['file_id']),str(b.get('language','en'))))
        self.user(True)
        if path=='/api/users/password':
            verify_sensitive(user,b.get('current_password'))
            password=b.get('new_password');valid_password(password);uid=int(b['id'])
            with database() as c:
                if not c.execute('SELECT 1 FROM users WHERE id=?',(uid,)).fetchone():raise Problem(404,'User not found.')
                c.execute('UPDATE users SET password=? WHERE id=?',(hash_password(password),uid))
                c.execute('DELETE FROM sessions WHERE user_id=?',(uid,))
            return self.send_json({'ok':True,'sign_in_required':uid==user['id']})
        if path=='/api/media/delete-preview':return self.send_json(prepare_deletion(user,int(b['id']),b.get('scope')))
        if path=='/api/media/delete':return self.send_json(confirm_deletion(user,b.get('token'),b.get('password')))
        if path=='/api/metadata/refresh':return self.send_json(provider.start(bool(b.get('force',False))))
        if path=='/api/metadata/search':
            item=media_item(int(b['id']));kind=b.get('kind',item['kind'])
            if kind not in ('movie','episode'):raise Problem(400,'Invalid media type.')
            return self.send_json(provider.search(str(b.get('query') or item['series'] or item['title']),kind))
        if path=='/api/metadata/apply':
            item=media_item(int(b['id']));kind=b.get('kind',item['kind'])
            if kind not in ('movie','episode'):raise Problem(400,'Invalid media type.')
            if kind=='episode' and not item['show_key']:item['show_key']='folder:'+hashlib.sha256(str(Path(item['path']).parent).encode()).hexdigest()[:24]
            result=provider.apply(item,int(b['tmdb_id']),kind)
            provider.update(item['id'],{'kind_override':kind})
            return self.send_json(result)
        if path=='/api/media/classify':
            item=media_item(int(b['id']));kind=b.get('kind')
            if kind not in ('movie','episode'):raise Problem(400,'Choose Movie or TV episode.')
            values={'kind_override':kind,'kind':kind,'source':'','tmdb_id':0,'metadata_checked':0,'metadata_status':'','poster':'','backdrop':'','overview':'','collection_id':'','collection_name':'','cast_json':'[]','studios_json':'[]','logo':'','still':'','show_overview':'','rating':'','genres':'','release_date':'','critic_rating':'','parental_rating':''}
            if kind=='movie':values.update(series='',show_key='',season=0,episode=0,episode_title='')
            else:
                values.update(series=str(b.get('series') or clean_title(Path(item['path']).parent.name)),season=int(number(b.get('season',1),0,999)),episode=int(number(b.get('episode',1),0,999)),show_key='folder:'+hashlib.sha256(str(Path(item['path']).parent).encode()).hexdigest()[:24])
            provider.update(item['id'],values)
            return self.send_json({'ok':True})
        if path=='/api/scan':
            threading.Thread(target=scan,daemon=True).start(); return self.send_json({'ok':True})
        if path=='/api/settings':
            allowed={'seer_url','seer_key','radarr_url','radarr_key','radarr_remote_path','radarr_local_path','sonarr_url','sonarr_key','sonarr_remote_path','sonarr_local_path','os_key','subtitle_language','tmdb_key','omdb_key','fanart_key','metadata_language'}
            result={}
            for k,v in b.items():
                if k not in allowed: continue
                if not isinstance(v,str) or len(v)>2048: raise Problem(400,'Invalid setting.')
                if k.endswith('_url') and v:
                    u=urllib.parse.urlsplit(v)
                    if u.scheme not in ('http','https') or not u.hostname or u.username or u.password or u.query or u.fragment: raise Problem(400,'Use an HTTP(S) server URL without credentials or a query.')
                if k.endswith('_key') and not v: continue # Empty means keep stored secret.
                result[k]=v.strip()
            set_settings(result); return self.send_json({'ok':True})
        if path=='/api/opensubtitles/login':
            os_login(str(b.get('username','')),str(b.get('password','')))
            return self.send_json({'ok':True})
        if path=='/api/opensubtitles/logout':
            set_settings({'os_token':'','os_expires':0,'os_username':'','os_password':''}); return self.send_json({'ok':True})
        m=re.fullmatch(r'/api/integrations/(radarr|sonarr)/(test|sync|queue)',path)
        if m:
            if m[2]=='sync': return self.send_json(sync_arr(m[1]))
            if m[2]=='queue':
                r=arr(m[1],'queue?pageSize=20'); return self.send_json({'totalRecords':r.get('totalRecords',0),'records':[{'title':x.get('title',''),'status':x.get('status',''),'size':x.get('size',0),'sizeleft':x.get('sizeleft',0)} for x in r.get('records',[])]})
            result=arr(m[1],'system/status'); return self.send_json({'ok':True,'version':result.get('version','')})
        if path=='/api/users':
            name=str(b.get('name','')).strip(); password=b.get('password',''); valid_password(password)
            if not 1<=len(name)<=60: raise Problem(400,'Name must be 1–60 characters.')
            try:
                with database() as c: c.execute('INSERT INTO users(name,password,admin) VALUES (?,?,0)',(name,hash_password(password)))
            except sqlite3.IntegrityError: raise Problem(409,'Username already exists.')
            return self.send_json({'ok':True})
        if path=='/api/users/delete':
            uid=int(b['id'])
            if uid==user['id']: raise Problem(400,'Cannot delete your current account.')
            with database() as c: c.execute('DELETE FROM users WHERE id=? AND admin=0',(uid,))
            return self.send_json({'ok':True})
        raise Problem(404,'Not found.')
    def file(self,p,content_type=None,media=False):
        if not p.is_file(): raise Problem(404,'File not found.')
        size=p.stat().st_size; start=0; end=size-1; partial=False
        raw=self.headers.get('Range') if media else None
        if raw:
            m=re.fullmatch(r'bytes=(\d*)-(\d*)',raw)
            if not m or not any(m.groups()): raise Problem(416,'Invalid byte range.')
            if m[1]: start=int(m[1]); end=min(int(m[2]),size-1) if m[2] else size-1
            else: start=max(0,size-int(m[2]))
            if start>=size or end<start:
                self.send_response(416); self.send_header('Content-Range',f'bytes */{size}'); self.send_header('Content-Length','0'); self.end_headers(); return
            partial=True
        length=max(0,end-start+1)
        self.send_response(206 if partial else 200); self.headers_common()
        self.send_header('Content-Type',content_type or mimetypes.guess_type(p.name)[0] or 'application/octet-stream')
        self.send_header('Content-Length',str(length))
        if media: self.send_header('Accept-Ranges','bytes')
        if partial: self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
        self.end_headers()
        with p.open('rb') as f:
            f.seek(start)
            while length:
                chunk=f.read(min(256*1024,length))
                if not chunk: break
                self.wfile.write(chunk); length-=len(chunk)
    def transcode(self,item,q,user):
        if not shutil.which('ffmpeg'): raise Problem(503,'FFmpeg is not installed.')
        offset=number(q.get('start',['0'])[0]); audio=int(number(q.get('audio',['0'])[0],0,50))
        quality=q.get('quality',['720'])[0]
        if quality not in ('480','720','1080','audio'): raise Problem(400,'Invalid quality.')
        if not TRANSCODES.acquire(timeout=3): raise Problem(429,'Transcoding is busy. Use Direct Play or wait for the current stream.')
        sid=secrets.token_hex(8); process=None
        try:
            cmd=playback_command(item,offset,audio,quality)
            process=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
            # Validate FFmpeg actually started producing media before sending status 200.
            first=process.stdout.read(1024)
            if not first: raise Problem(422,'FFmpeg could not decode this file or audio track.')
            with ACTIVE_LOCK: ACTIVE[sid]={'user':user['name'],'title':item['title']}
            self.send_response(200); self.headers_common(); self.send_header('Content-Type','video/mp4'); self.send_header('Connection','close'); self.end_headers()
            self.close_connection=True; self.wfile.write(first)
            while True:
                chunk=process.stdout.read(64*1024)
                if not chunk: break
                self.wfile.write(chunk)
        finally:
            if process:
                process.terminate()
                try: process.wait(timeout=3)
                except subprocess.TimeoutExpired: process.kill(); process.wait()
                if process.stdout: process.stdout.close()
            with ACTIVE_LOCK: ACTIVE.pop(sid,None)
            TRANSCODES.release()

def playback_command(item,offset,audio,quality):
    cmd=['ffmpeg','-v','error','-nostdin','-ss',str(offset),'-i',item['path'],'-map','0:v:0','-map',f'0:a:{audio}?','-sn']
    if quality=='audio':
        streams=probe(item['path']).get('streams',[])
        video=next((x for x in streams if x.get('codec_type')=='video'),{})
        if video.get('codec_name') not in ('h264','hevc','av1','vp9','mpeg4'):
            raise Problem(422,'This video cannot be copied to the browser stream. Select Compatible mode.')
        cmd+=['-c:v','copy']
        if video.get('codec_name')=='hevc':cmd+=['-tag:v','hvc1']
        tracks=[x for x in streams if x.get('codec_type')=='audio']
        if tracks and audio>=len(tracks):raise Problem(400,'Audio track not found.')
        # AAC can be remuxed as-is; EAC3 and other formats are converted to stereo AAC.
        if tracks and tracks[audio].get('codec_name')=='aac':cmd+=['-c:a','copy']
        else:cmd+=['-c:a','aac','-ac','2','-b:a','192k','-threads','2']
        cmd+=['-avoid_negative_ts','make_zero']
    else:
        rate={'480':'1200k','720':'2500k','1080':'5000k'}[quality]
        cmd+=['-vf',f'scale=w=-2:h=min({quality}\\,ih)','-c:v','libx264','-preset','veryfast','-pix_fmt','yuv420p','-b:v',rate,'-threads','2','-c:a','aac','-ac','2','-b:a','160k']
    return cmd+['-movflags','frag_keyframe+empty_moov+default_base_moof','-f','mp4','pipe:1']

def maintenance():
    while True:
        scan()
        for service in ('radarr','sonarr'):
            if settings().get(service+'_url'):
                try: sync_arr(service)
                except Exception: pass
        if settings().get('tmdb_key'):
            try:provider.start()
            except Exception:pass
        time.sleep(300)

def main():
    os.umask(0o077); init()
    threading.Thread(target=maintenance,daemon=True).start()
    print(f'StreamPort listening on port {PORT}',flush=True)
    ThreadingHTTPServer(('0.0.0.0',PORT),Handler).serve_forever()

provider=metadata.Engine(settings,request_json,database,Problem)

if __name__=='__main__': main()
