import json
import unittest
from unittest.mock import patch
from test_features import Features, s

class Requests(Features):
    def setUp(self):
        super().setUp()
        s.set_settings({'seer_url':'http://seer:5055','seer_key':'private-seer-key'})
        self.sent=[];self.remote=[];self.fail_after=False
        def upstream(url,method='GET',payload=None,headers=None):
            self.assertEqual(headers['X-Api-Key'],'private-seer-key')
            if '/request?' in url:return {'results':self.remote}
            if url.endswith('/request') and method=='POST':
                self.sent.append(payload)
                row={'id':77,'status':2,'seasons':[{'seasonNumber':x} for x in payload.get('seasons',[])],'media':{'status':3}}
                self.remote.append(row)
                if self.fail_after:raise s.Problem(502,'timeout')
                return row
            detail={'id':123,'title':'Test Film','posterPath':'/test.jpg','seasons':[{'seasonNumber':1,'episodeCount':10},{'seasonNumber':2,'episodeCount':8}], 'mediaInfo':{'status':3 if any(r['status'] in (1,2) for r in self.remote) else 1,'requests':self.remote}}
            if '/search?' in url:return {'results':[dict(detail,mediaType='movie'),{'id':1,'mediaType':'person'}],'totalPages':2}
            return detail
        self.mock=patch.object(s,'request_json',side_effect=upstream);self.mock.start()
    def tearDown(self):self.mock.stop();super().tearDown()
    def test_viewer_approval_and_duplicate(self):
        body={'media_type':'movie','id':123}
        status,data,_=self.call('/api/requests',body,self.viewer);self.assertEqual(status,200);rid=data['id'];self.assertEqual(self.sent,[])
        self.assertEqual(self.call('/api/requests',body,self.viewer)[0],409)
        self.assertEqual(self.call('/api/requests/review',{'id':rid,'action':'approve'},self.viewer)[0],403)
        self.assertEqual(self.call('/api/requests/review',{'id':rid,'action':'approve'},self.admin)[0],200)
        self.assertEqual(len(self.sent),1)
        self.assertEqual(self.call('/api/requests/review',{'id':rid,'action':'approve'},self.admin)[0],409)
    def test_search_and_secrets(self):
        data=self.call('/api/requests/search?query=test',cookie=self.viewer)[1]
        self.assertEqual(len(data['results']),1)
        self.assertNotIn('private-seer-key',json.dumps(data))
        self.assertNotIn('seer_key',self.call('/api/settings',cookie=self.admin)[1])
        with s.database() as c:raw=c.execute("SELECT value FROM settings WHERE key='seer_key'").fetchone()[0]
        self.assertNotIn('private-seer-key',raw)
        self.assertEqual(self.call('/api/requests/search?query=test')[0],401)
    def test_admin_direct_and_timeout_reconcile(self):
        self.fail_after=True
        self.assertEqual(self.call('/api/requests',{'media_type':'tv','id':123,'seasons':[1]},self.admin)[0],502)
        data=self.call('/api/requests?all=1',cookie=self.admin)[1]['results'][0]
        self.assertEqual(data['state'],'check_required')
        self.assertEqual(self.call('/api/requests/review',{'id':data['id'],'action':'approve'},self.admin)[0],200)
        self.assertEqual(len(self.sent),1,'retry must reconcile before resending')
    def test_seasons_and_history_isolation(self):
        self.assertEqual(self.call('/api/requests',{'media_type':'tv','id':123,'seasons':[88]},self.viewer)[0],400)
        self.call('/api/requests',{'media_type':'tv','id':123,'seasons':[2,1,2]},self.admin)
        self.assertEqual(self.sent[0]['seasons'],[1,2])
        self.assertEqual(self.call('/api/requests?all=1',cookie=self.viewer)[1]['results'],[])
    def test_available_matches_type(self):
        with s.database() as c:c.execute('UPDATE media SET tmdb_id=123 WHERE id=?',(self.movie,))
        self.assertTrue(self.call('/api/requests/detail?type=movie&id=123',cookie=self.viewer)[1]['local'])
        self.assertEqual(self.call('/api/requests/detail?type=tv&id=123',cookie=self.viewer)[1]['local'],[])

    def test_global_duplicate_and_shared_badge(self):
        body={'media_type':'movie','id':123}
        self.assertEqual(self.call('/api/requests',body,self.viewer)[0],200)
        self.assertEqual(self.call('/api/requests',body,self.admin)[0],409)
        result=self.call('/api/requests/search?query=test',cookie=self.admin)[1]['results'][0]
        self.assertTrue(result['requested']);self.assertTrue(result['request_blocked'])
        self.assertNotIn('username',result)
        self.assertEqual(self.sent,[])

    def test_overlap_seasons_but_new_season_allowed(self):
        body={'media_type':'tv','id':123,'seasons':[1]}
        self.assertEqual(self.call('/api/requests',body,self.viewer)[0],200)
        item=self.call('/api/requests/detail?type=tv&id=123',cookie=self.admin)[1]
        self.assertEqual(item['requested_seasons'],[1]);self.assertFalse(item['request_blocked'])
        self.assertEqual(self.call('/api/requests',dict(body,seasons=[1,2]),self.admin)[0],409)
        self.assertEqual(self.call('/api/requests',dict(body,seasons=[2]),self.admin)[0],200)
        self.assertEqual(self.sent[0]['seasons'],[2])

    def test_seer_only_requests_blocked(self):
        self.remote=[{'id':88,'status':1,'seasons':[{'seasonNumber':1}]}]
        self.assertEqual(self.call('/api/requests',{'media_type':'movie','id':123},self.viewer)[0],409)
        self.assertEqual(self.call('/api/requests',{'media_type':'tv','id':123,'seasons':[1]},self.viewer)[0],409)
        self.assertEqual(self.sent,[])

    def test_simultaneous_users_one_record(self):
        import concurrent.futures
        import threading
        barrier=threading.Barrier(2)
        def submit(cookie):
            barrier.wait()
            return self.call('/api/requests',{'media_type':'movie','id':123},cookie)[0]
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            futures=[pool.submit(submit,cookie) for cookie in [self.viewer,self.admin]]
            codes=sorted(f.result() for f in futures)
        self.assertEqual(codes,[200,409])
        with s.database() as c:self.assertEqual(c.execute('SELECT count(*) FROM media_requests').fetchone()[0],1)
        self.assertLessEqual(len(self.sent),1)

    def test_decline_allows_new_request(self):
        body={'media_type':'movie','id':123}
        rid=self.call('/api/requests',body,self.viewer)[1]['id']
        self.call('/api/requests/review',{'id':rid,'action':'decline'},self.admin)
        self.assertEqual(self.call('/api/requests',body,self.viewer)[0],200)

if __name__=='__main__':unittest.main()
