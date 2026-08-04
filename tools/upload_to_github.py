import base64, json, os, sys, time, urllib.request

TOKEN = os.environ['GITHUB_TOKEN']
OWNER = 'aciderix'
REPO = 'disney-heroes-spine-viewer'
API = f'https://api.github.com/repos/{OWNER}/{REPO}'

def api_call(url, method='GET', data=None):
    headers = {
        'Authorization': f'token {TOKEN}',
        'Content-Type': 'application/json',
        'Accept': 'application/vnd.github.v3+json'
    }
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read())
        except Exception as e:
            if attempt < 2:
                time.sleep(2)
            else:
                raise

def create_blob(file_path):
    with open(file_path, 'rb') as f:
        content = base64.b64encode(f.read()).decode()
    result = api_call(f'{API}/git/blobs', 'POST', {
        'content': content,
        'encoding': 'base64'
    })
    return result['sha']

def get_main_sha():
    result = api_call(f'{API}/git/refs/heads/main')
    return result['object']['sha']

def get_tree_sha(commit_sha):
    result = api_call(f'{API}/git/commits/{commit_sha}')
    return result['tree']['sha']

def create_tree(base_tree_sha, items):
    result = api_call(f'{API}/git/trees', 'POST', {
        'base_tree': base_tree_sha,
        'tree': items
    })
    return result['sha']

def create_commit(tree_sha, parent_sha, message):
    result = api_call(f'{API}/git/commits', 'POST', {
        'message': message,
        'tree': tree_sha,
        'parents': [parent_sha]
    })
    return result['sha']

def update_ref(sha):
    api_call(f'{API}/git/refs/heads/main', 'PATCH', {'sha': sha})

# Collect all files
files_to_upload = []
files_to_upload.append(('index.html', 'index.html'))
files_to_upload.append(('spine-canvas.js', 'spine-canvas.js'))
files_to_upload.append(('spine-webgl.js', 'spine-webgl.js'))

for char_dir in sorted(os.listdir('characters')):
    char_path = f'characters/{char_dir}'
    for fname in ['skeleton.json', 'atlas.atlas', 'texture.png']:
        fpath = f'{char_path}/{fname}'
        if os.path.exists(fpath):
            files_to_upload.append((fpath, fpath))

print(f'Total files to upload: {len(files_to_upload)}')

# Upload blobs
tree_items = []
for i, (local_path, repo_path) in enumerate(files_to_upload):
    sz = os.path.getsize(local_path)
    mb = sz / 1024 / 1024
    sha = create_blob(local_path)
    tree_items.append({
        'path': repo_path,
        'mode': '100644',
        'type': 'blob',
        'sha': sha
    })
    print(f'  [{i+1}/{len(files_to_upload)}] {repo_path} ({mb:.1f}MB) → {sha[:8]}')

# Get current main branch
main_sha = get_main_sha()
base_tree = get_tree_sha(main_sha)
print(f'Base tree: {base_tree[:8]}')

# Create new tree
new_tree = create_tree(base_tree, tree_items)
print(f'New tree: {new_tree[:8]}')

# Create commit
commit_sha = create_commit(new_tree, main_sha, 'Upload all viewer files (HTML + spine runtime + 15 characters)')
print(f'Commit: {commit_sha[:8]}')

# Update ref
update_ref(commit_sha)
print(f'Updated main branch → {commit_sha[:8]}')
print('DONE!')
