import unittest,tempfile,subprocess,json
from pathlib import Path
from unittest.mock import patch
from test_features import s
class DirectStream(unittest.TestCase):
    def test_eac3_converts_only_audio_and_keeps_video_packets(self):
        with tempfile.TemporaryDirectory() as tmp:
            inp=Path(tmp)/'source.mkv';out=Path(tmp)/'output.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=160x90:rate=24','-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','3','-c:v','libx264','-g','24','-c:a','eac3',str(inp)],check=True)
            cmd=s.playback_command({'path':str(inp)},0,0,'audio')
            self.assertEqual(cmd[cmd.index('-c:v')+1],'copy');self.assertNotIn('-vf',cmd)
            with out.open('wb') as f:subprocess.run(cmd,stdout=f,stderr=subprocess.PIPE,check=True)
            data=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(out)]))
            self.assertEqual([x['codec_name'] for x in data['streams']],['h264','aac'])
            self.assertEqual(data['streams'][1]['channels'],2)
            # Compare decoded video frames, not container headers or changed timestamps.
            def frames(p):
                raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(p),'-map','0:v:0','-f','framemd5','-'])
                return [line.rsplit(b',',1)[-1].strip() for line in raw.splitlines() if not line.startswith(b'#')]
            self.assertEqual(frames(inp),frames(out))
            seek=Path(tmp)/'seek.mp4'
            with seek.open('wb') as f:subprocess.run(s.playback_command({'path':str(inp)},1,0,'audio'),stdout=f,stderr=subprocess.PIPE,check=True)
            subprocess.run(['ffmpeg','-v','error','-i',str(seek),'-f','null','-'],check=True,stderr=subprocess.PIPE)
    def test_aac_copies_both_streams_and_hevc_tag(self):
        with patch.object(s,'probe',return_value={'streams':[{'codec_type':'video','codec_name':'hevc'},{'codec_type':'audio','codec_name':'aac'}]}):
            cmd=s.playback_command({'path':'test.mkv'},0,0,'audio')
            self.assertEqual(cmd[cmd.index('-c:a')+1],'copy');self.assertIn('hvc1',cmd)
            with self.assertRaises(s.Problem):s.playback_command({'path':'test.mkv'},0,9,'audio')
    def test_compatible_still_encodes_video(self):
        cmd=s.playback_command({'path':'test.mkv'},60,0,'720')
        self.assertEqual(cmd[cmd.index('-c:v')+1],'libx264');self.assertIn('-vf',cmd)
