import unittest,time,threading
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from test_features import s
class Session(unittest.TestCase):
    def setUp(self):
        self.saved={'os_token':'old','os_expires':time.time()+3600,'os_username':'test','os_password':'not-real','os_key':'key','os_host':'api.opensubtitles.com'}
        self.logins=0;self.calls=[]
        self.patches=[patch.object(s,'settings',side_effect=lambda:dict(self.saved)),patch.object(s,'set_settings',side_effect=self.saved.update)]
        for p in self.patches:p.start()
        self.addCleanup(lambda:[p.stop() for p in reversed(self.patches)])
    def failure(self,code):
        e=s.Problem(502,'provider error');e.upstream_status=code;return e
    def request(self,url,method='GET',payload=None,headers=None):
        self.calls.append((url,method,payload,headers))
        if url.endswith('/login'):
            self.logins+=1;return {'token':'new','base_url':'vip-api.opensubtitles.com'}
        if headers['Authorization']=='Bearer old':raise self.failure(401)
        return {'link':'https://dl.opensubtitles.com/test'}
    def test_early_revocation_refreshes_token_host_and_same_payload(self):
        with patch.object(s,'request_json',side_effect=self.request):
            result=s.os_authenticated_request('/download','POST',{'file_id':123})
        self.assertIn('link',result);self.assertEqual(self.logins,1)
        self.assertEqual(len(self.calls),3)
        self.assertEqual(self.calls[-1][0],'https://vip-api.opensubtitles.com/api/v1/download')
        self.assertEqual(self.calls[0][2],self.calls[-1][2])
    def test_second_401_does_not_loop(self):
        def reject(url,method='GET',payload=None,headers=None):
            if url.endswith('/login'):return self.request(url,method,payload,headers)
            self.calls.append((url,));raise self.failure(401)
        with patch.object(s,'request_json',side_effect=reject),self.assertRaises(s.Problem) as caught:
            s.os_authenticated_request('/download','POST',{'file_id':123})
        self.assertEqual(caught.exception.status,401);self.assertEqual(self.logins,1);self.assertEqual(len(self.calls),3)
    def test_no_retry_on_quota_server_errors_or_timeout(self):
        for failure in [self.failure(429),self.failure(403),self.failure(500),s.Problem(502,'timeout'),TimeoutError()]:
            with patch.object(s,'request_json',side_effect=failure) as req,self.assertRaises(Exception):
                s.os_authenticated_request('/download','POST',{'file_id':123})
            self.assertEqual(req.call_count,1)
    def test_login_rejected_and_missing_credentials(self):
        with patch.object(s,'request_json',side_effect=self.failure(401)) as req,self.assertRaises(s.Problem) as caught:
            s.os_authenticated_request('/download','POST',{})
        self.assertEqual(req.call_count,2);self.assertEqual(caught.exception.status,401)
        self.saved.pop('os_password')
        with patch.object(s,'request_json',side_effect=self.failure(401)) as req,self.assertRaises(s.Problem):s.os_authenticated_request('/download')
        self.assertEqual(req.call_count,1)
    def test_parallel_rejections_share_one_refresh(self):
        barrier=threading.Barrier(2)
        def request(url,method='GET',payload=None,headers=None):
            if not url.endswith('/login') and headers['Authorization']=='Bearer old':barrier.wait(timeout=3)
            return self.request(url,method,payload,headers)
        with patch.object(s,'request_json',side_effect=request),ThreadPoolExecutor(2) as pool:
            results=list(pool.map(lambda _:s.os_authenticated_request('/infos/user'),range(2)))
        self.assertEqual(len(results),2);self.assertEqual(self.logins,1)
    def test_missing_token_future_expiry_logs_in(self):
        self.saved.pop('os_token')
        with patch.object(s,'request_json',side_effect=self.request):
            headers=s.os_headers(True)
        self.assertEqual(headers['Authorization'],'Bearer new');self.assertEqual(self.logins,1)
    def test_download_refresh_then_cache_avoids_repeat_api_call(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);(data/'subtitles').mkdir()
            with patch.object(s,'DATA',data),patch.object(s,'request_json',side_effect=self.request),patch.object(s,'fetch_subtitle',return_value=b'WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nTest\n') as fetch:
                first=s.download_subtitle({'id':12},123,'en')
                second=s.download_subtitle({'id':12},123,'en')
                self.assertFalse(first['cached']);self.assertTrue(second['cached'])
                self.assertTrue((data/'subtitles'/first['key']).exists())
                self.assertEqual(self.logins,1);self.assertEqual(fetch.call_count,1);self.assertEqual(len(self.calls),3)
