from test_features import Features,s
class SubtitleShift(Features):
    def prepare(self):
        self.sub=self.media/'movie.en.srt';self.sub.write_text('1\n00:00:01,000 --> 00:00:02,000\nHello 00:00:01,000\n')
        return {'id':self.movie,'key':self.sub.name,'version':s.subtitle_version(self.sub),'seconds':1.5}
    def test_shift_requires_admin_preserves_text_and_backup(self):
        body=self.prepare()
        self.assertEqual(self.call('/api/subtitles/shift',body,self.viewer)[0],403)
        status,result,_=self.call('/api/subtitles/shift',body,self.admin);self.assertEqual(status,200,result)
        self.assertIn('00:00:02,500 --> 00:00:03,500',self.sub.read_text())
        self.assertIn('Hello 00:00:01,000',self.sub.read_text())
        self.assertIn('00:00:01,000 -->',self.sub.with_name(result['backup']).read_text())
        self.assertEqual(self.call('/api/subtitles/shift',body,self.admin)[0],409)
    def test_invalid_selection_offset_and_readonly(self):
        from unittest.mock import patch
        body=self.prepare()
        self.assertEqual(self.call('/api/subtitles/shift',{**body,'key':'../../other.srt'},self.admin)[0],409)
        self.assertEqual(self.call('/api/subtitles/shift',{**body,'seconds':999},self.admin)[0],400)
        original=self.sub.read_bytes()
        with patch.object(s.shutil,'copy2',side_effect=PermissionError):
            self.assertEqual(self.call('/api/subtitles/shift',body,self.admin)[0],409)
        self.assertEqual(self.sub.read_bytes(),original)
    def test_negative_vtt_and_version_in_listing(self):
        self.sub=self.media/'movie.en.vtt';self.sub.write_text('WEBVTT\n\n00:01.000 --> 00:02.000 align:start\nHi\n')
        body={'id':self.movie,'key':self.sub.name,'version':s.subtitle_version(self.sub),'seconds':-1.5}
        code,data,_=self.call('/api/media/'+str(self.movie)+'/subtitles',cookie=self.viewer)
        self.assertEqual(data[0]['version'],body['version'])
        self.assertEqual(self.call('/api/subtitles/shift',body,self.admin)[0],200)
        self.assertIn('00:00:00.000 --> 00:00:00.500 align:start',self.sub.read_text())
    def test_sync_assets_are_served(self):
        import urllib.request
        for name in ('subtitle-sync.js','subtitle-sync.css'):
            with urllib.request.urlopen(self.url+'/'+name) as response:
                self.assertEqual(response.status,200)
                self.assertIn(b'subtitle',response.read())
