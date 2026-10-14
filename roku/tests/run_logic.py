"""Execute production pure functions using the off-device brs interpreter (not a Roku emulator)."""
from pathlib import Path
import re, subprocess, sys, tempfile
root = Path(__file__).resolve().parents[1]
source=(root/'components/MainScene.brs').read_text()
names=['s','n','seriesKey','movieKey','selectItems','comesBefore','timecode','parseVtt','nextEpisode']
functions=[]
for name in names:
    match=re.search(r'^function '+name+r'\(.*?^end function', source, re.M|re.S)
    if not match: raise RuntimeError(name)
    functions.append(match.group())
with tempfile.TemporaryDirectory() as directory:
    path=Path(directory)/'logic.brs'
    path.write_text('\n\n'.join(functions)+'\n'+(root/'tests/logic.brs').read_text())
    result=subprocess.run([sys.argv[1] if len(sys.argv)>1 else 'brs',str(path)],capture_output=True,text=True,cwd=root)
    print(result.stdout,end=''); print(result.stderr,end='')
    if result.returncode or 'FAIL:' in result.stdout or 'PASS: Roku' not in result.stdout: sys.exit(1)
