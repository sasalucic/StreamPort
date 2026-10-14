#!/usr/bin/env bash
# Enable only the two video mounts; the container root stays read-only.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
if [[ ! -f compose.yaml || ! -f .env ]]; then
  echo 'Run this script in your installed StreamPort directory (compose.yaml and .env required).'; exit 1
fi
python3 - <<'PY'
from pathlib import Path
import re, shutil, datetime
p=Path('compose.yaml'); text=p.read_text(); original=text
for target in ('/media/movies','/media/tv'):
    pattern=r'(target:\s*'+re.escape(target)+r'\s*\n\s*read_only:)\s*(true|false)'
    text,n=re.subn(pattern,r'\1 false',text)
    if n!=1:raise SystemExit('Unsupported compose layout. No changes made. Set read_only: false only for /media/movies and /media/tv, and ALLOW_MEDIA_DELETE: "true" in environment manually.')
if re.search(r'^\s+ALLOW_MEDIA_DELETE:',text,re.M):
    text=re.sub(r'^(\s+ALLOW_MEDIA_DELETE:).*$',r'\1 "true"',text,flags=re.M)
else:
    text,n=re.subn(r'^(\s+)DATA_DIR:',r'\1ALLOW_MEDIA_DELETE: "true"\n\1DATA_DIR:',text,count=1,flags=re.M)
    if n!=1:raise SystemExit('Unsupported environment layout. No changes made.')
backup=p.with_name('compose.yaml.before-delete-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
shutil.copy2(p,backup);p.write_text(text)
print('Saved backup:',backup)
print('Video mounts are writable; container root remains read-only. No media is deleted by this script.')
PY
docker compose config --quiet
docker compose up -d --build --wait
echo 'Admin deletion enabled. Each deletion requires preview and your admin password.'
