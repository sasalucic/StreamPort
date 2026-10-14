#!/usr/bin/env python3
"""Fail on common accidental secrets/identifiers in tracked public source.
This is a guardrail, NOT a substitute for full review or external secret scanning.
"""
import pathlib, re, subprocess, sys
root=pathlib.Path(__file__).resolve().parents[1]
try:
    files=subprocess.run(['git','ls-files','-z'],cwd=root,capture_output=True,check=True).stdout.split(b'\x00')
    paths=[root/p.decode() for p in files if p]
except (OSError, subprocess.CalledProcessError):
    paths=[p for p in root.rglob('*') if p.is_file() and '.git' not in p.parts]

bad_names=[re.compile(x,re.I) for x in (r'(^|/)\.env$',r'(^|/)data/',r'(^|/)signing/',r'\.(?:jks|keystore|p12|pfx|apk|aab|db|pem|key)$')]
patterns={
    'common access token':re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16})'),
    'private IPv4':re.compile(r'\b(?:10\.(?:\d{1,3}\.){2}\d{1,3}|192\.168\.(?:\d{1,3}\.)\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.(?:\d{1,3}\.)\d{1,3}|100\.(?:\d{1,3}\.){2}\d{1,3})\b'),
    'home user path':re.compile(r'/(?:home|Users)/(?!your-user\b|user\b|example\b|username\b)[A-Za-z][\w.-]+/'),
}
failures=[]
for p in paths:
    if not p.is_file():continue
    name=p.relative_to(root).as_posix()
    if any(pattern.search(name) for pattern in bad_names):failures.append((name,'private/generated filename'));continue
    try:s=p.read_text()
    except (UnicodeError,OSError):continue
    for title,pattern in patterns.items():
        for m in pattern.finditer(s):failures.append((f'{name}:{s.count(chr(10),0,m.start())+1}',title))
if failures:
    for where,why in failures:print(f'BLOCKED: {where} — {why}')
    sys.exit(1)
print(f'PASS: {len(paths)} tracked/source files checked (basic public-source hygiene).')
