"""Seerr gateway. Only admins configure secrets or forward requests upstream.
Viewer requests are persisted locally until explicitly approved by an admin.
"""
import json
import threading
import time
import urllib.parse

LOCK = threading.Lock()


def initialize(database):
    with database() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS media_requests (
            id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            media_type TEXT NOT NULL, tmdb_id INTEGER NOT NULL, seasons TEXT NOT NULL,
            title TEXT NOT NULL, poster TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending',
            upstream_id INTEGER, created REAL NOT NULL,
            UNIQUE(user_id,media_type,tmdb_id,seasons))''')


def gateway(settings, request_json, Problem):
    s = settings()
    url, key = s.get('seer_url', '').rstrip('/'), s.get('seer_key', '')
    if not url or not key:
        raise Problem(400, 'An administrator must configure the Seer URL and API key in Settings.')
    def call(path, payload=None):
        return request_json(url + '/api/v1' + path, method='POST' if payload is not None else 'GET',
                            payload=payload, headers={'X-Api-Key': key})
    return call


def positive(value, Problem):
    if isinstance(value, bool): raise Problem(400, 'Invalid media ID.')
    value = int(value)
    if not 0 < value < 2147483647: raise Problem(400, 'Invalid media ID.')
    return value


def kind(value, Problem):
    if value not in ('movie', 'tv'): raise Problem(400, 'Choose a movie or TV series.')
    return value


def local_media(database, media_type, mid):
    with database() as c:
        rows = c.execute('SELECT id,season,episode FROM media WHERE available=1 AND tmdb_id=? AND kind=? ORDER BY season,episode,id',
                         (mid, 'movie' if media_type == 'movie' else 'episode')).fetchall()
    return [{'id':r['id'],'season':r['season'],'episode':r['episode']} for r in rows]


def request_state(data, media_type, database):
    """Public shared status, without exposing another user's name or request ID."""
    info=data.get('mediaInfo') or {}
    remote=[r for r in info.get('requests',[]) if not r.get('is4k') and r.get('status') in (1,2)]
    with database() as c:
        # A confirmed Seer decline releases the local request for resubmission.
        for r in info.get('requests',[]):
            if r.get('status')==3:
                c.execute("UPDATE media_requests SET state='declined' WHERE upstream_id=? AND media_type=? AND tmdb_id=?",(r['id'],media_type,data['id']))
        rows=c.execute("SELECT seasons FROM media_requests WHERE media_type=? AND tmdb_id=? AND state!='declined'",(media_type,data['id'])).fetchall()
    requested=set()
    for r in rows:requested.update(json.loads(r['seasons']))
    for r in remote:requested.update(x['seasonNumber'] for x in r.get('seasons',[]) if 'seasonNumber' in x)
    for season in info.get('seasons',[]):
        if season.get('status') in (2,3,4,5):requested.add(season['seasonNumber'])
    available=info.get('status')==5
    if media_type=='movie':
        available=available or bool(local_media(database,media_type,data['id']))
        return {'requested':bool(rows or remote or info.get('status') in (2,3)), 'request_blocked':bool(available or rows or remote or info.get('status') in (2,3)), 'requested_seasons':[], 'available':available}
    all_seasons={x['seasonNumber'] for x in data.get('seasons',[]) if x.get('episodeCount',0)>0}
    if available:requested.update(all_seasons)
    return {'requested':bool(rows or remote or requested or info.get('status') in (2,3,4)), 'request_blocked':bool(available or (all_seasons and all_seasons.issubset(requested))), 'requested_seasons':sorted(requested), 'available':available}


def clean(data, media_type, database):
    mid = int(data['id'])
    info = data.get('mediaInfo') or {}
    poster = data.get('posterPath') or ''
    return dict(**request_state(data,media_type,database),id=mid, media_type=media_type, title=data.get('title') or data.get('name') or 'Untitled',
                overview=data.get('overview') or '', year=(data.get('releaseDate') or data.get('firstAirDate') or '')[:4],
                rating=data.get('voteAverage') or 0,
                poster='https://image.tmdb.org/t/p/w342'+poster if poster.startswith('/') else '',
                media_status=info.get('status', 1),
                request_statuses=[r.get('status') for r in info.get('requests',[])],
                seasons=[{'number':s['seasonNumber'],'episodes':s.get('episodeCount',0)} for s in data.get('seasons',[]) if s.get('episodeCount',0)>0],
                local=local_media(database,media_type,mid))


def get(path, q, user, database, settings, request_json, Problem):
    if path == '/api/requests/config':
        s = settings()
        return {'configured':bool(s.get('seer_url') and s.get('seer_key'))}
    call = gateway(settings, request_json, Problem)
    if path == '/api/requests/search':
        query = str(q.get('query',[''])[0]).strip()[:200]
        page = max(1,min(500,int(q.get('page',['1'])[0])))
        if not query: return {'results':[], 'pages':0}
        data = call('/search?'+urllib.parse.urlencode({'query':query,'page':page},quote_via=urllib.parse.quote))
        # Search API uses camelCase mediaType; no people or arbitrary upstream URLs.
        return {'results':[clean(r,r['mediaType'],database) for r in data.get('results',[]) if r.get('mediaType') in ('movie','tv')],
                'pages':data.get('totalPages',1)}
    if path == '/api/requests/detail':
        media_type = kind(q.get('type',[''])[0],Problem)
        mid = positive(q.get('id',['0'])[0],Problem)
        return clean(call('/'+media_type+'/'+str(mid)),media_type,database)
    if path == '/api/requests':
        all_users = user['admin'] and q.get('all',['0'])[0]=='1'
        with database() as c:
            rows=c.execute('SELECT r.*,u.name username FROM media_requests r JOIN users u ON u.id=r.user_id '+
                ('' if all_users else 'WHERE r.user_id=? ')+'ORDER BY r.created DESC LIMIT 100', () if all_users else (user['id'],)).fetchall()
        # Batch status lookup prevents a remote roundtrip per history entry.
        upstream={}; warning=''
        if any(r['upstream_id'] for r in rows):
            try:
                data=call('/request?take=100&skip=0&sort=modified')
                upstream={r['id']:r for r in data.get('results',[])}
            except Exception: warning='Seer is unavailable. Showing saved request status.'
        result=[]
        for r in rows:
            item=dict(r); item['seasons']=json.loads(item['seasons'])
            item['local']=local_media(database,r['media_type'],r['tmdb_id'])
            remote=upstream.get(r['upstream_id'])
            if remote:
                item['state']={1:'seer_pending',2:'approved',3:'declined'}.get(remote.get('status'),'submitted')
                item['media_status']=(remote.get('media') or {}).get('status',1)
            if r['media_type']=='movie' and item['local']:item['state']='available'
            if r['media_type']=='tv' and item['local']:item['has_local_episodes']=True
            result.append(item)
        return {'results':result,'warning':warning}
    raise Problem(404,'Unknown Requests endpoint.')


def forward(row, call, database, Problem):
    # Reconcile first: a previous HTTP timeout may have been accepted by Seer.
    detail=call('/'+row['media_type']+'/'+str(row['tmdb_id']))
    seasons=json.loads(row['seasons'])
    for r in (detail.get('mediaInfo') or {}).get('requests',[]):
        requested={s.get('seasonNumber') for s in r.get('seasons',[])}
        if not r.get('is4k') and r.get('status') in (1,2) and (row['media_type']=='movie' or set(seasons).issubset(requested)):
            with database() as c:c.execute("UPDATE media_requests SET state='submitted',upstream_id=? WHERE id=?",(r['id'],row['id']))
            return
    info=detail.get('mediaInfo') or {}
    covered={x['seasonNumber'] for x in info.get('seasons',[]) if x.get('status') in (2,3,4,5)}
    for existing in info.get('requests',[]):
        if not existing.get('is4k') and existing.get('status') in (1,2):covered.update(x['seasonNumber'] for x in existing.get('seasons',[]))
    if info.get('status')==5 or (row['media_type']=='tv' and set(seasons).issubset(covered)):
        with database() as c:c.execute("UPDATE media_requests SET state='submitted' WHERE id=?",(row['id'],))
        return
    if row['media_type']=='tv':seasons=sorted(set(seasons)-covered)
    payload={'mediaType':row['media_type'],'mediaId':row['tmdb_id'],'is4k':False}
    if row['media_type']=='tv':payload['seasons']=seasons
    with database() as c:c.execute("UPDATE media_requests SET state='sending' WHERE id=?",(row['id'],))
    try:
        remote=call('/request',payload)
        rid=remote['id']
    except Exception:
        with database() as c:c.execute("UPDATE media_requests SET state='check_required' WHERE id=?",(row['id'],))
        raise Problem(502,'Seer did not confirm this request. An admin can use Check / retry; existing requests are checked before retrying.')
    with database() as c:c.execute("UPDATE media_requests SET state='submitted',upstream_id=? WHERE id=?",(rid,row['id']))


def post(path, b, user, database, settings, request_json, Problem):
    call=gateway(settings,request_json,Problem)
    if path=='/api/requests/test':
        if not user['admin']:raise Problem(403,'Administrator required.')
        call('/request?take=1');return {'ok':True}
    if path=='/api/requests':
        media_type=kind(b.get('media_type'),Problem);mid=positive(b.get('id',0),Problem)
        detail=call('/'+media_type+'/'+str(mid))
        seasons=[]
        if media_type=='tv':
            supplied=b.get('seasons')
            if not isinstance(supplied,list) or not supplied or len(supplied)>200:raise Problem(400,'Select at least one season.')
            valid={s['seasonNumber'] for s in detail.get('seasons',[]) if s.get('episodeCount',0)>0}
            if any(type(s) is not int or s not in valid for s in supplied):raise Problem(400,'Invalid season selection.')
            seasons=sorted(set(supplied))
        title=detail.get('title') or detail.get('name') or 'Untitled'
        poster=clean(detail,media_type,database)['poster']
        with LOCK:
            # Refresh under the same lock used for insertion and forwarding:
            # simultaneous users cannot both pass the duplicate check.
            detail=call('/'+media_type+'/'+str(mid))
            shared=request_state(detail,media_type,database)
            overlap=set(seasons)&set(shared['requested_seasons'])
            if shared['request_blocked'] or overlap:
                reason='Already available or requested.'
                if overlap:reason='Already requested: seasons '+', '.join(map(str,sorted(overlap)))+'. Select only unrequested seasons.'
                raise Problem(409,reason)
            with database() as c:
                count=c.execute('SELECT COUNT(*) FROM media_requests WHERE user_id=? AND created>?',(user['id'],time.time()-3600)).fetchone()[0]
                if count>=30:raise Problem(429,'Request limit reached. Try again later.')
                c.execute('INSERT OR IGNORE INTO media_requests(user_id,media_type,tmdb_id,seasons,title,poster,created) VALUES (?,?,?,?,?,?,?)',
                          (user['id'],media_type,mid,json.dumps(seasons),title,poster,time.time()))
                row=dict(c.execute('SELECT * FROM media_requests WHERE user_id=? AND media_type=? AND tmdb_id=? AND seasons=?',
                                   (user['id'],media_type,mid,json.dumps(seasons))).fetchone())
            if row['state']=='declined':
                with database() as c:c.execute("UPDATE media_requests SET state='pending',upstream_id=NULL,created=? WHERE id=?",(time.time(),row['id']))
                row['state']='pending'
            if user['admin'] and row['state']=='pending':forward(row,call,database,Problem)
        return {'ok':True,'id':row['id'],'message':'Request saved in Seer.' if user['admin'] or row['state']!='pending' else 'Request saved. Waiting for administrator approval.'}
    if path=='/api/requests/review':
        if not user['admin']:raise Problem(403,'Administrator required.')
        rid=positive(b.get('id',0),Problem)
        if b.get('action') not in ('approve','decline'):raise Problem(400,'Invalid action.')
        with LOCK:
            with database() as c:row=c.execute('SELECT * FROM media_requests WHERE id=?',(rid,)).fetchone()
            if not row:raise Problem(404,'Request not found.')
            if row['state'] not in ('pending','check_required','sending'):raise Problem(409,'This request has already been reviewed.')
            if b['action']=='decline':
                if row['state']!='pending':raise Problem(409,'Check this request in Seer before declining; it may have been sent.')
                with database() as c:c.execute("UPDATE media_requests SET state='declined' WHERE id=?",(rid,))
            else:forward(dict(row),call,database,Problem)
        return {'ok':True}
    raise Problem(404,'Unknown Requests endpoint.')
