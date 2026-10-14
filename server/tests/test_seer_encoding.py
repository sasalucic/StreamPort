import unittest,urllib.parse
from test_features import s
class Encoding(unittest.TestCase):
    def test_search_encoding_at_upstream_boundary(self):
        for query in ['what','silicon valley','Law & Order','A+B','100%','Čovjek Spider-Man','三体']:
            with self.subTest(query=query):
                calls=[]
                def upstream(url,**kwargs):
                    calls.append(url)
                    encoded=urllib.parse.urlsplit(url).query
                    self.assertNotIn('+',encoded)
                    self.assertEqual(urllib.parse.parse_qs(encoded),{'query':[query],'page':['2']})
                    if ' ' in query:self.assertIn('%20',encoded)
                    return {'results':[],'totalPages':3}
                result=s.seer.get('/api/requests/search',{'query':[query],'page':['2']},{'admin':False},None,lambda:{'seer_url':'http://seer:5055','seer_key':'test'},upstream,s.Problem)
                self.assertEqual(len(calls),1);self.assertEqual(result,{'results':[],'pages':3})
