"""Independent movie/TV metadata adapters. No Jellyfin dependency."""
import difflib, json, re, threading, time, unicodedata, urllib.parse

IMAGE='https://image.tmdb.org/t/p/'
def picture(path,size='w500'):
    return IMAGE+size+path if isinstance(path,str) and path.startswith('/') else ''
def norm(value):
    return re.sub(r'[^a-z0-9]+','',unicodedata.normalize('NFKD',value).encode('ascii','ignore').decode().lower())

class Engine:
    def __init__(self,settings,request,database,error):
        self.settings,self.request,self.db,self.Error=settings,request,database,error
        self.lock=threading.Lock()
        self.status={'running':False,'done':0,'total':0,'matched':0,'review':0,'errors':0,'message':'Not started'}
    def tmdb(self,path,**params):
        s=self.settings();token=s.get('tmdb_key','')
        if not token:raise self.Error(400,'Add your TMDb API Read Access Token (or v3 API key) in Settings → Metadata providers.')
        params={'language':s.get('metadata_language','en-US'),**params};headers={}
        if len(token)>40:headers['Authorization']='Bearer '+token
        else:params['api_key']=token
        return self.request('https://api.themoviedb.org/3/'+path+'?'+urllib.parse.urlencode(params),headers=headers)
    def search(self,query,kind,year=''):
        kind='tv' if kind=='episode' else 'movie'
        params={'query':query,'include_adult':'false'}
        # Year is used for ranking, not filtering: filenames sometimes use episode year.
        rows=self.tmdb('search/'+kind,**params).get('results',[])
        return [{'id':r['id'],'kind':'episode' if kind=='tv' else 'movie','title':r.get('title') or r.get('name',''),'original':r.get('original_title') or r.get('original_name',''),'year':(r.get('release_date') or r.get('first_air_date') or '')[:4],'overview':r.get('overview',''),'poster':picture(r.get('poster_path'))} for r in rows[:20]]
    def identify(self,item):
        kind='tv' if item['kind']=='episode' else 'movie'
        if item.get('tmdb_id'):return int(item['tmdb_id'])
        if item.get('imdb'):
            matches=self.tmdb('find/'+item['imdb'],external_source='imdb_id').get(kind+'_results',[])
            if len(matches)==1:return matches[0]['id']
        query=item['series'] if item['kind']=='episode' else item['title']
        results=self.search(query,item['kind'],item.get('year',''))
        scores=[]
        for r in results:
            score=max(difflib.SequenceMatcher(None,norm(query),norm(r['title'])).ratio(),difflib.SequenceMatcher(None,norm(query),norm(r['original'])).ratio())
            if item.get('year') and r['year']:
                if str(item['year'])==r['year']:score+=.15
                elif item['kind']=='movie':score-=.25
            scores.append((score,r['id']))
        scores.sort(reverse=True)
        if scores and scores[0][0]>=.92 and (len(scores)==1 or scores[0][0]-scores[1][0]>=.12):return scores[0][1]
        return None
    def apply(self,item,tmdb_id,kind=None):
        kind=kind or item['kind'];api_kind='tv' if kind=='episode' else 'movie'
        if not 0<int(tmdb_id)<100000000:raise self.Error(400,'Invalid TMDb ID.')
        detail=self.tmdb(f'{api_kind}/{int(tmdb_id)}',append_to_response='credits,external_ids')
        title=detail.get('title') or detail.get('name') or item['title']
        overview=detail.get('overview') or ''
        if not overview and self.settings().get('metadata_language','en-US')!='en-US':
            overview=self.tmdb(f'{api_kind}/{int(tmdb_id)}',language='en-US').get('overview','')
        ext=detail.get('external_ids',{});collection=detail.get('belongs_to_collection') or {}
        values={'release_date':detail.get('release_date') or detail.get('first_air_date') or '', 'kind':kind,'tmdb_id':int(tmdb_id),'year':(detail.get('release_date') or detail.get('first_air_date') or '')[:4],
          'poster':picture(detail.get('poster_path')),'backdrop':picture(detail.get('backdrop_path'),'w1280'),
          'genres':', '.join(g['name'] for g in detail.get('genres',[])), 'rating':str(round(detail.get('vote_average',0),1)),
          'imdb':detail.get('imdb_id') or ext.get('imdb_id') or item.get('imdb',''), 'source':'tmdb',
          'cast_json':json.dumps([{'name':r.get('name',''),'character':r.get('character',''),'image':picture(r.get('profile_path'),'w185')} for r in detail.get('credits',{}).get('cast',[])[:16]]),
          'studios_json':json.dumps([{'name':r.get('name',''),'image':picture(r.get('logo_path'),'w185')} for r in detail.get('production_companies',[])]),
          'collection_id':str(collection.get('id','')),'collection_name':collection.get('name',''),
          'metadata_status':'matched','metadata_checked':time.time()}
        warning=[];s=self.settings()
        if s.get('omdb_key') and values['imdb']:
            try:
                o=self.request('https://www.omdbapi.com/?'+urllib.parse.urlencode({'apikey':s['omdb_key'],'i':values['imdb'],'plot':'full'}))
                if o.get('Response')=='True':
                    if o.get('imdbRating') not in (None,'N/A'):values['rating']=o['imdbRating']
                    if o.get('Rated') not in (None,'N/A'):values['parental_rating']=o['Rated']
                    if o.get('Metascore') not in (None,'N/A'):values['critic_rating']=o['Metascore']
                    if not overview and o.get('Plot') not in (None,'N/A'):overview=o['Plot']
                else:warning.append('OMDb: '+o.get('Error','No data'))
            except self.Error as e:warning.append('OMDb: '+e.message)
        if s.get('fanart_key'):
            fan_id=ext.get('tvdb_id') if kind=='episode' else tmdb_id
            if fan_id:
                try:
                    f=self.request('https://webservice.fanart.tv/v3/'+('tv/' if kind=='episode' else 'movies/')+str(fan_id)+'?'+urllib.parse.urlencode({'api_key':s['fanart_key']}))
                    for field,keys in [('backdrop',['showbackground','moviebackground']),('logo',['hdtvlogo','hdmovielogo','clearlogo','movielogo'])]:
                        images=next((f[k] for k in keys if f.get(k)),[])
                        images=sorted(images,key=lambda x:(x.get('lang') not in ('en','00',''),-int(x.get('likes',0) or 0)))
                        if images:
                            url=images[0].get('url','')
                            if url.startswith('https://'):values[field]=url
                except self.Error as e:warning.append('Fanart: '+e.message)
        if kind=='episode':
            with self.db() as c:rows=[dict(r) for r in c.execute("SELECT * FROM media WHERE kind='episode' AND show_key=?",(item['show_key'],))] if item['show_key'] else [item]
            if not rows:rows=[item]
            values.update(series=title,show_key=item['show_key'],show_overview=overview)
            seasons={}
            for row in rows:
                season=row['season']
                if season not in seasons:
                    try:seasons[season]={e['episode_number']:e for e in self.tmdb(f'tv/{tmdb_id}/season/{season}').get('episodes',[])}
                    except self.Error as e:seasons[season]={};warning.append(f'Season {season}: '+e.message)
                ep=seasons[season].get(row['episode'],{})
                extra={**values}
                if ep:extra.update(episode_title=ep.get('name',''),overview=ep.get('overview',''),still=picture(ep.get('still_path'),'w500'))
                self.update(row['id'],extra)
        else:
            self.update(item['id'],{**values,'title':title,'overview':overview,'series':'','show_key':'','season':0,'episode':0,'episode_title':''})
        return {'ok':True,'title':title,'warnings':warning}
    def update(self,mid,values):
        with self.db() as c:c.execute('UPDATE media SET '+','.join(k+'=?' for k in values)+' WHERE id=?',(*values.values(),mid))
    def start(self,force=False):
        if not self.settings().get('tmdb_key'):raise self.Error(400,'Configure TMDb in Settings first.')
        if not self.lock.acquire(blocking=False):return {'ok':True,'running':True}
        self.status.update(running=True,done=0,total=0,matched=0,review=0,errors=0,message='Preparing library')
        threading.Thread(target=self.run,args=(force,),daemon=True).start();return {'ok':True}
    def run(self,force):
        try:
            with self.db() as c:rows=[dict(r) for r in c.execute('SELECT * FROM media WHERE available=1 ORDER BY id')]
            seen=set();work=[]
            for r in rows:
                key=r['show_key'] if r['kind']=='episode' else str(r['id'])
                if key in seen:continue
                seen.add(key)
                if not force and r['metadata_checked']>time.time()-86400:continue
                work.append(r)
            self.status['total']=len(work)
            for r in work:
                self.status['message']=r['series'] or r['title']
                try:
                    mid=self.identify(r)
                    if mid:self.apply(r,mid);self.status['matched']+=1
                    else:
                        self.update(r['id'],{'metadata_status':'needs identification','metadata_checked':time.time()});self.status['review']+=1
                except Exception as e:
                    self.update(r['id'],{'metadata_status':e.message if isinstance(e,self.Error) else 'Metadata request failed','metadata_checked':time.time()});self.status['errors']+=1
                    if isinstance(e,self.Error) and getattr(e,'upstream_status',None) in (401,403,429):
                        self.status['message']=e.message;break
                self.status['done']+=1
                time.sleep(.25)
            else:self.status['message']='Finished. Use Identify for unmatched titles.'
        finally:self.status['running']=False;self.lock.release()
