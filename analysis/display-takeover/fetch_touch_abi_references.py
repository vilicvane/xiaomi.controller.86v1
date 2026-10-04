"""Fetch only small public ABI headers; no hardware interaction."""
import hashlib
import json
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEST = HERE / 'reference'

def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'mi-panel-offline-abi-review'})
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read()

refs = {}
for repo, branch in [('apache/nuttx', 'master'), ('open-vela/nuttx', 'dev')]:
    meta = json.loads(fetch(f'https://api.github.com/repos/{repo}/commits/{branch}'))
    refs[repo] = meta['sha']

requests = [
    ('touch-apache-master.h', 'apache/nuttx', refs['apache/nuttx'], 'include/nuttx/input/touchscreen.h'),
    ('touch-open-vela-dev.h', 'open-vela/nuttx', refs['open-vela/nuttx'], 'include/nuttx/input/touchscreen.h'),
    ('touch-fcntl-open-vela-dev.h', 'open-vela/nuttx', refs['open-vela/nuttx'], 'include/fcntl.h'),
    ('touch-fcntl-apache-master.h', 'apache/nuttx', refs['apache/nuttx'], 'include/fcntl.h'),
    ('touch-fcntl-apache-12.7.0.h', 'apache/nuttx', 'nuttx-12.7.0', 'include/fcntl.h'),
]
manifest = {'scope': 'Public header download only; no hardware interaction', 'resolved_commits': refs, 'files': []}
DEST.mkdir(parents=True, exist_ok=True)
for name, repo, ref, path in requests:
    url = f'https://raw.githubusercontent.com/{repo}/{ref}/{path}'
    data = fetch(url)
    if len(data) > 30000:
        raise RuntimeError(f'Unexpectedly large ABI reference: {name}')
    target = DEST / name
    if target.exists() and target.read_bytes() != data:
        raise RuntimeError(f'Refusing to overwrite a different reference: {target}')
    target.write_bytes(data)
    manifest['files'].append({'file': str(target.relative_to(HERE)), 'url': url,
                              'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})

path = HERE / 'touch-abi-reference-manifest.json'
path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
print(json.dumps(manifest, indent=2))
