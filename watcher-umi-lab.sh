#!/usr/bin/env bash
# UMI LAB ZIP release watcher / macOS. Install at root of umi-lab Git repository.
# Usage: ./watcher-umi-lab.sh [--dry-run|--once|--status|--tail|--logs] [--interval 3]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 - "$ROOT" "$@" <<'UMI_WATCH_PY'
import argparse
import datetime as dt
import getpass
import fcntl
import hashlib
import json
import os
import re
import secrets
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

ROOT=Path(sys.argv[1]).resolve()
sys.argv=[sys.argv[0]]+sys.argv[2:]
UPDATES=ROOT/'updates'
STATE=ROOT/'.umi-lab'
EXPECTED_REMOTE='git@github.com:sylwesterdigital/umi-lab.git'
SITE='https://umi-lab.top/'
# Connection settings survive new terminals, reboots and watcher upgrades.
# No credentials are ever written to this JSON file.
CONFIG_PATH=STATE/'watcher-config.json'
DEFAULT_CONFIG={
    'ssh_host':'root@46.62.232.64',
    'ssh_port':333,
    'server_ip':'46.62.232.64',
    'certbot_email':'',
}

def validate_config(data):
    if not isinstance(data,dict) or set(data)!=set(DEFAULT_CONFIG):
        raise ReleaseError('Invalid UMI watcher config fields')
    host=data['ssh_host']
    port=data['ssh_port']
    ip=data['server_ip']
    mail=data['certbot_email']
    if not isinstance(host,str) or not re.fullmatch(r'[a-zA-Z0-9_.-]+@[a-zA-Z0-9_.-]+',host):
        raise ReleaseError('Invalid configured SSH host (user@host expected)')
    if type(port) is not int or not 1<=port<=65535:
        raise ReleaseError('Invalid configured SSH port (1-65535 expected)')
    try:socket.inet_pton(socket.AF_INET,ip)
    except (OSError,TypeError):raise ReleaseError('Invalid configured server IPv4 address')
    if not isinstance(mail,str) or len(mail)>256 or ('\n' in mail or '\r' in mail) or (mail and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',mail)):
        raise ReleaseError('Invalid configured Certbot contact email')
    return data

def load_config():
    if CONFIG_PATH.is_symlink():raise ReleaseError('Refusing symlink for local watcher config')
    if not CONFIG_PATH.is_file():return dict(DEFAULT_CONFIG)
    try:config=json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
    except (OSError,ValueError) as exc:raise ReleaseError('Cannot read UMI config: '+str(exc)) from exc
    validate_config(config)
    if CONFIG_PATH.stat().st_mode & 0o077:CONFIG_PATH.chmod(0o600)
    return config

def save_config(config):
    validate_config(config)
    STATE.mkdir(mode=0o700,exist_ok=True)
    if CONFIG_PATH.is_symlink():raise ReleaseError('Refusing symlink for local watcher config')
    fd,temp=tempfile.mkstemp(prefix='.watcher-config-',dir=STATE)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            json.dump(config,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
        os.chmod(temp,0o600)
        os.replace(temp,CONFIG_PATH)
    finally:
        if os.path.exists(temp):os.unlink(temp)

def ask_terminal(label,default):
    # The watcher runs Python from a bash heredoc, so stdin is NOT a terminal.
    # Read /dev/tty explicitly rather than input(), which would consume the heredoc.
    try:
        fd=os.open('/dev/tty',os.O_RDWR)
        try:
            os.write(fd,f'{label} [{default}]: '.encode('utf-8'))
            chunks=[]
            while True:
                chunk=os.read(fd,1)
                if not chunk:raise ReleaseError('Configuration cancelled')
                if chunk==b'\n':break
                chunks.append(chunk)
                if len(chunks)>512:raise ReleaseError('Config input too long')
            result=b''.join(chunks).decode('utf-8').strip()
            return result or str(default)
        finally:os.close(fd)
    except OSError as exc:
        raise ReleaseError('Interactive configuration requires a terminal') from exc

def configure():
    current=load_config()
    log('One-time UMI watcher configuration; Enter keeps the displayed setting','STEP')
    updated={
        'ssh_host':ask_terminal('SSH host (user@host)',current['ssh_host']),
        'ssh_port':int(ask_terminal('SSH port',current['ssh_port'])),
        'server_ip':ask_terminal('Server IPv4 / DNS target',current['server_ip']),
        'certbot_email':ask_terminal('Certbot email (optional; enter - to clear)',current['certbot_email'] or '-'),
    }
    if updated['certbot_email']=='-':updated['certbot_email']=''
    save_config(updated)
    log('Saved persistent settings to '+str(CONFIG_PATH)+' (mode 0600)','PASS')
    log('Future terminal sessions need no export commands. Admin password is never saved in this file.','PASS')

def admin_password():
    prior=os.environ.get('UMI_ADMIN_PASSWORD','')
    if len(prior)>=12:return prior  # Backward-compatible optional override.
    if not sys.stderr.isatty():
        raise ReleaseError('Fresh server needs an initial admin password. Run ./watcher-umi-lab.sh --once interactively; no export needed.')
    log('New UMI installation detected; choose the first admin password (not stored locally)','STEP')
    first=getpass.getpass('UMI initial admin password (12+ chars): ')
    if len(first)<12:raise ReleaseError('Admin password must contain at least 12 characters')
    again=getpass.getpass('Confirm initial admin password: ')
    if first!=again:raise ReleaseError('Admin passwords do not match; no changes made')
    return first

VERSION_RE=re.compile(r'^\d+\.\d+\.\d+$')
ZIP_RE=re.compile(r'^UMI_LAB_(?:UPDATE|RELEASE)_v(\d+\.\d+\.\d+)\.zip$')
WATCHER_BUILD='0.1.4'
LOG=None
VERBOSE=False
COLOR='auto'
ANSI={'STEP':'\033[1;34m','PASS':'\033[1;32m','INFO':'\033[1;36m','WARN':'\033[1;33m','FAIL':'\033[1;97;41m','START':'\033[1;97;44m','END':'\033[1;97;42m'}

class ReleaseError(Exception):pass
class ArchiveError(ReleaseError):pass

SETTINGS=load_config()
SSH_HOST=os.environ.get('UMI_SSH_HOST',SETTINGS['ssh_host'])
SSH_PORT=str(os.environ.get('UMI_SSH_PORT',SETTINGS['ssh_port']))
SERVER_IP=os.environ.get('UMI_SERVER_IP',SETTINGS['server_ip'])
CERTBOT_EMAIL=os.environ.get('UMI_CERTBOT_EMAIL',SETTINGS['certbot_email'])
BOOTSTRAP_PASSWORD=''

def h(data):return hashlib.sha256(data).hexdigest()
def now():return dt.datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')
def elapsed(t):return f'{time.monotonic()-t:.1f}s'
def colorize(msg,level):
    enabled=COLOR=='always' or (COLOR=='auto' and sys.stdout.isatty() and os.getenv('NO_COLOR') is None)
    return ANSI.get(level,'')+msg+'\033[0m' if enabled and level in ANSI else msg

def log(msg,level='INFO'):
    for fragment in str(msg).splitlines() or ['']:
        raw=f'{now()} [{level:5}] {fragment}'
        print(colorize(raw,level),flush=True)
        if LOG:
            with LOG.open('a',encoding='utf8') as f:f.write(raw+'\n')

def banner(phase,version,detail=''):
    line='━'*70
    lines=['',line,f'  {"▶ RELEASE START" if phase=="START" else "■ RELEASE END"}  v{version}  |  {now()}',
           f'  {detail}',line,'']
    for x in lines:
        print(colorize(x,phase),flush=True)
        if LOG:
            with LOG.open('a',encoding='utf8') as f:f.write(x+'\n')

def run(argv,*,cwd=None,timeout=100,check=True,stdin=None):
    if VERBOSE:log('RUN '+str(argv[0])+' '+(' '.join(str(x) for x in argv[1:4])),'INFO')
    try:r=subprocess.run([str(x) for x in argv],cwd=cwd,timeout=timeout,
                         input=stdin,text=True,capture_output=True,
                         env={**os.environ,'GIT_TERMINAL_PROMPT':'0'})
    except subprocess.TimeoutExpired:raise ReleaseError(str(argv[0])+' timed out')
    if check and r.returncode:
        raise ReleaseError(str(argv[0])+' failed: '+((r.stderr or r.stdout)[-1800:]))
    return r

def ssh(script,*,timeout=100):
    # Never print, store, or log the script: it can include bootstrap credentials.
    return run(['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
                '-o','ConnectTimeout=10','-p',SSH_PORT,SSH_HOST,'bash','-se'],
               timeout=timeout,stdin='set -euo pipefail\n'+script+'\n').stdout.strip()

def vt(version):return tuple(int(n) for n in version.split('.'))
def last_version():
    try:return json.loads((STATE/'deployed.json').read_text()).get('version','0.0.0')
    except (ValueError,OSError):return '0.0.0'

def local_validate_watcher(data):
    text=data.decode('utf-8')
    m=re.search(r"^WATCHER_BUILD='([0-9]+\.[0-9]+\.[0-9]+)'$",text,re.M)
    if not m or vt(m.group(1))<vt(WATCHER_BUILD):raise ArchiveError('Watcher version invalid or downgraded')
    current=ROOT/'watcher-umi-lab.sh'
    if current.is_file() and m.group(1)==WATCHER_BUILD and current.read_bytes()!=data:
        raise ArchiveError('Watcher modification requires a version bump')
    with tempfile.TemporaryDirectory(prefix='umi-watch-') as t:
        file=Path(t)/'watcher.sh';file.write_bytes(data)
        run(['bash','-n',file],timeout=15)
        body=re.search(r"<<'UMI_WATCH_PY'\n(.*?)\nUMI_WATCH_PY\s*$",text,re.S)
        if not body:raise ArchiveError('Watcher Python body missing')
        p=Path(t)/'watcher.py';p.write_text(body.group(1)+'\n')
        run(['python3','-m','py_compile',p],timeout=15)
    for term in ('StrictHostKeyChecking=yes','sha256','git_preflight','verify_public','rollback','--dry-run','recover_partial_release','Staged release file is missing'):
        if term not in text:raise ArchiveError('Watcher regression guard absent: '+term)

def validate(archive,stage):
    try:z=zipfile.ZipFile(archive)
    except (zipfile.BadZipFile,OSError) as e:raise ArchiveError('ZIP is invalid: '+str(e))
    with z:
        infos=z.infolist()
        if len(infos)>85 or sum(i.file_size for i in infos)>30*1024*1024:raise ArchiveError('ZIP exceeds safety limits')
        names=[i.filename for i in infos if not i.is_dir()]
        if len(names)!=len(set(names)) or 'manifest.json' not in names:raise ArchiveError('Duplicate or missing manifest')
        for info in infos:
            path=PurePosixPath(info.filename)
            if (info.filename.startswith('/') or '\\' in info.filename or '..' in path.parts
                or (info.external_attr>>16 & 0o170000)==0o120000):
                raise ArchiveError('Unsafe ZIP entry '+info.filename)
        data=json.loads(z.read('manifest.json'))
        version=data.get('version','')
        match=ZIP_RE.fullmatch(archive.name)
        if not match or match.group(1)!=version or not VERSION_RE.fullmatch(version):
            raise ArchiveError('ZIP name and manifest version mismatch')
        if vt(version)<=vt(last_version()):raise ArchiveError(f'v{version} is not newer than last deployed v{last_version()}')
        files=data.get('sha256')
        if not isinstance(files,dict) or len(files)<14:raise ArchiveError('Missing application file list')
        required={'app/backend/app.py','app/backend/db.py','app/backend/providers.py','app/frontend/index.html',
                  'app/frontend/css/styles.css','app/frontend/js/app.js','app/frontend/js/viewer.js',
                  'app/deploy/install.py','app/parts.json','app/version.json','app/README.md'}
        if not required.issubset(files):raise ArchiveError('Release missing critical source files')
        expected={'manifest.json'}|set(files)
        watcher=data.get('watcher')
        if watcher is not None:expected.add('watcher-umi-lab.sh')
        if set(names)!=expected:raise ArchiveError('Unexpected or missing release files')
        for name,digest in files.items():
            if ('__pycache__' in PurePosixPath(name).parts or name.endswith(('.pyc','.pyo'))):
                raise ArchiveError('Compiled Python/cache files are not allowed in releases: '+name)
            if not name.startswith('app/') or not re.fullmatch(r'[a-zA-Z0-9_./-]+',name):
                raise ArchiveError('Unexpected release path '+name)
            if not re.fullmatch(r'[0-9a-f]{64}',str(digest)):raise ArchiveError('Invalid digest '+name)
            content=z.read(name)
            if h(content)!=digest:raise ArchiveError('SHA-256 mismatch: '+name)
            target=stage/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(content)
        if watcher is not None:
            if not isinstance(watcher,dict) or watcher.get('path')!='watcher-umi-lab.sh':
                raise ArchiveError('Invalid watcher update entry')
            content=z.read('watcher-umi-lab.sh')
            if h(content)!=watcher.get('sha256'):raise ArchiveError('Watcher SHA-256 mismatch')
            local_validate_watcher(content)
            (stage/'watcher-umi-lab.sh').write_bytes(content)
        v=json.loads((stage/'app/version.json').read_text())
        if v.get('version')!=version or v.get('project')!='umi-lab':raise ArchiveError('Version marker mismatch')
        html=(stage/'app/frontend/index.html').read_text()
        if '<meta name="umi-version" content="'+version+'">' not in html:
            raise ArchiveError('HTML version mismatch')
        if not all(x in html for x in ('galleryGrid','settingsDrawer','promptForm','partsPane','viewerPane')):
            raise ArchiveError('Missing studio interface elements')
        # Compile in a single interpreter, avoiding dozens of slow process
        # startups on constrained hosts while still checking every source file.
        run(['python3','-m','compileall','-q',stage/'app'],timeout=60)
        for p in (stage/'app/frontend/js').glob('*.js'):
            run(['node','--check',p],timeout=20)
        # The no-dependency DB and deployment tests run locally; any skipped Flask
        # tests are mandatory on the Ubuntu server after pip install.
        tests=run(['python3','-m','unittest','discover','-s','tests','-v'],cwd=stage/'app',timeout=60)
        # `run` already rejects a nonzero exit status. An expected failure
        # deliberately exercised by a passing regression test must not invalidate
        # an otherwise successful release. Require the actual unittest summary.
        if not re.search(r'(?m)^Ran [0-9]+ tests? in ',tests.stderr) or not re.search(r'(?m)^OK(?: \(skipped=[0-9]+\))?$',tests.stderr):
            raise ArchiveError('Local unittest summary missing despite exit code 0')
        log('Python, JavaScript, checksums, ontology and local tests passed','PASS')
        if 'skipped=' in tests.stderr:log('Flask integration tests skipped locally (no Flask); server must pass all','WARN')
        for cache in (stage/'app').rglob('__pycache__'):
            shutil.rmtree(cache,ignore_errors=True)
        return version,data

def recover_partial_release(version):
    """Recover only verified bytes left behind by a previously failed watcher copy.

    No user changes are reset: every candidate must be byte-identical to a
    release listed in updates/ or updates/superseded/, and a timestamped backup
    is retained even for that narrowly verified case.
    """
    candidates=[]
    for folder in (UPDATES, UPDATES/'superseded'):
        if folder.is_dir():candidates.extend(sorted(folder.glob('UMI_LAB_UPDATE_v*.zip')))
    known={}
    for archive in candidates:
        match=ZIP_RE.fullmatch(archive.name)
        if not match or vt(match.group(1))>=vt(version):continue
        try:
            with zipfile.ZipFile(archive) as z:
                meta=json.loads(z.read('manifest.json'))
                if meta.get('version')!=match.group(1):continue
                for name,digest in meta.get('sha256',{}).items():
                    if name.startswith('app/') and not name.endswith(('.pyc','.pyo')) and '__pycache__' not in PurePosixPath(name).parts:
                        known.setdefault(name[4:],set()).add(digest)
        except (OSError,ValueError,KeyError,zipfile.BadZipFile):continue
    status=run(['git','status','--porcelain=v1','--untracked-files=all'],cwd=ROOT).stdout.splitlines()
    changed=[]
    for line in status:
        rel=line[3:]
        if line.startswith('?? ') and (rel.startswith('updates/') or rel.startswith('.umi-lab/') or Path(rel).name=='.DS_Store'):
            continue
        if rel=='watcher-umi-lab.sh' and 'D' not in line[:2] and (ROOT/rel).is_file():continue
        # Only pre-existing unstaged edits and verified untracked copies are recoverable.
        if line[:2] not in (' M','??') or not known.get(rel):return
        file=ROOT/rel
        if not file.is_file() or file.is_symlink() or h(file.read_bytes()) not in known[rel]:return
        changed.append((rel,line.startswith('?? ')))
    if not changed:return
    token=dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup=STATE/'recovered-partial-releases'/token
    for rel,_ in changed:
        dest=backup/'files'/rel
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(ROOT/rel,dest)
    tracked=[rel for rel,untracked in changed if not untracked]
    if tracked:run(['git','restore','--',*tracked],cwd=ROOT)
    for rel,untracked in changed:
        if untracked:(ROOT/rel).unlink()
    log('Recovered '+str(len(changed))+' failed-release file(s); original bytes backed up to '+str(backup),'PASS')

def git_preflight(version):
    global BOOTSTRAP_PASSWORD
    if not (ROOT/'.git').exists():raise ReleaseError('Watcher must be in a Git clone')
    if run(['git','branch','--show-current'],cwd=ROOT).stdout.strip()!='main':raise ReleaseError('Only Git main can deploy')
    origin=run(['git','remote','get-url','origin'],cwd=ROOT).stdout.strip()
    if origin not in (EXPECTED_REMOTE,'ssh://git@github.com/sylwesterdigital/umi-lab.git'):
        raise ReleaseError('Unexpected Git origin: '+origin)
    recover_partial_release(version)
    status=run(['git','status','--porcelain=v1','--untracked-files=all'],cwd=ROOT).stdout.splitlines()
    for line in status:
        path=line[3:]
        if line.startswith('?? ') and (path.startswith('updates/') or path.startswith('.umi-lab/') or Path(path).name=='.DS_Store'):
            continue
        if path=='watcher-umi-lab.sh' and 'D' not in line[:2] and (ROOT/path).is_file():continue
        raise ReleaseError('Protecting local changes; commit or stash first: '+line)
    remote=run(['git','ls-remote','origin','refs/heads/main'],cwd=ROOT,timeout=65).stdout.strip()
    if remote:
        run(['git','fetch','--no-tags','origin','main'],cwd=ROOT,timeout=75)
        if run(['git','merge-base','--is-ancestor','FETCH_HEAD','HEAD'],cwd=ROOT,check=False).returncode:
            raise ReleaseError('Git remote is ahead/diverged; reconcile main manually')
    if not re.fullmatch(r'[a-zA-Z0-9_.-]+@[a-zA-Z0-9_.-]+',SSH_HOST):
        raise ReleaseError('UMI_SSH_HOST must be user@host')
    if not SSH_PORT.isdigit() or not 1<=int(SSH_PORT)<=65535:raise ReleaseError('Invalid SSH port')
    # Guard DNS before certbot tries the new domain.
    try:
        ipset={x[4][0] for x in socket.getaddrinfo('umi-lab.top',80,family=socket.AF_INET)}
    except socket.gaierror as exc:raise ReleaseError('DNS resolution for umi-lab.top failed: '+str(exc))
    if SERVER_IP not in ipset:raise ReleaseError('umi-lab.top must point to '+SERVER_IP+'; observed '+str(sorted(ipset)))
    remote_info=ssh('''test "$(id -u)" -eq 0
      command -v nginx >/dev/null
      command -v systemctl >/dev/null
      command -v python3 >/dev/null
      command -v sha256sum >/dev/null
      nginx -t >/dev/null 2>&1
      if test -f /etc/letsencrypt/live/umi-lab.top/fullchain.pem && test -f /etc/letsencrypt/live/umi-lab.top/privkey.pem; then
        echo TLS_READY
      elif command -v certbot >/dev/null 2>&1; then
        echo TLS_CERTBOT
      else echo TLS_UNAVAILABLE; fi
      if test -f /var/lib/umi-lab/umi.sqlite3; then
        python3 - <<'CHECK_UMI_ADMIN'
import sqlite3
try:
    con=sqlite3.connect('file:/var/lib/umi-lab/umi.sqlite3?mode=ro',uri=True)
    try:count=con.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    except sqlite3.Error:count=0
    finally:con.close()
    print('EXISTING' if count else 'NEW')
except sqlite3.Error:print('NEW')
CHECK_UMI_ADMIN
      else echo NEW; fi''')
    if 'TLS_UNAVAILABLE' in remote_info:
        raise ReleaseError('Ubuntu needs certbot installed or an existing umi-lab.top TLS certificate before deployment')
    if 'NEW' in remote_info:
        BOOTSTRAP_PASSWORD=admin_password()
    log(f'Git main, DNS, SSH ({SSH_HOST}:{SSH_PORT}) and nginx preflight passed','PASS')

def push_git(stage,version,manifest):
    names=sorted(manifest['sha256'])
    # Reject missing/changed stage members and untracked collisions BEFORE ANY copy.
    # The v0.1.9 regression came from validating bytecode then deleting it, so
    # the old watcher copied a few source files before hitting a missing .pyc.
    preflight=[]
    for name in names:
        relative=name[4:]
        source=stage/name
        target=ROOT/relative
        if (not source.is_file() or source.is_symlink() or
            h(source.read_bytes())!=manifest['sha256'][name]):
            raise ReleaseError('Staged release file is missing or changed: '+name)
        if target.is_symlink():raise ReleaseError('Refusing local symlink '+relative)
        tracked=run(['git','ls-files','--error-unmatch','--',relative],cwd=ROOT,check=False).returncode==0
        if target.exists() and not tracked:
            raise ReleaseError('Refusing to overwrite untracked local file '+relative)
        preflight.append((source,target,tracked))
    watcher=stage/'watcher-umi-lab.sh'
    if watcher.exists() and h(watcher.read_bytes())!=manifest.get('watcher',{}).get('sha256'):
        raise ReleaseError('Watcher staged checksum mismatch')
    committed=False
    with tempfile.TemporaryDirectory(prefix='umi-local-release-backup-',dir=STATE) as backup_dir:
        backup=Path(backup_dir)
        originals=[]
        for _,target,_ in preflight:
            if target.exists():
                old=backup/target.relative_to(ROOT)
                old.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(target,old)
                originals.append((target,old))
            else:originals.append((target,None))
        current=ROOT/'watcher-umi-lab.sh'
        if watcher.is_file() and current.is_file():
            old=backup/'watcher-umi-lab.sh'
            shutil.copy2(current,old)
            originals.append((current,old))
        try:
            for source,target,_ in preflight:
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(source,target)
            if watcher.is_file():
                current=ROOT/'watcher-umi-lab.sh'
                if current.is_symlink():raise ReleaseError('Refusing watcher symlink')
                if not current.exists() or current.read_bytes()!=watcher.read_bytes():
                    backups=STATE/'watcher-backups';backups.mkdir(exist_ok=True)
                    if current.exists():shutil.copy2(current,backups/(dt.datetime.now().strftime('%Y%m%d-%H%M%S')+'.sh'))
                    temp=current.with_suffix('.new');temp.write_bytes(watcher.read_bytes());temp.chmod(0o755);os.replace(temp,current)
                    log('Updated watcher after checksum and syntax validation','PASS')
            files=[name[4:] for name in names]+['watcher-umi-lab.sh']
            run(['git','add','--',*files],cwd=ROOT)
            changed=run(['git','diff','--cached','--quiet'],cwd=ROOT,check=False)
            if changed.returncode==1:
                run(['git','commit','-m','Release UMI LAB v'+version],cwd=ROOT)
            elif changed.returncode:raise ReleaseError('Git index verification failed')
            committed=True
        except Exception:
            if not committed:
                for target,old in originals:
                    if old and old.is_file():
                        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(old,target)
                    elif target.is_file():target.unlink()
                # Git index had been clean before processing this release.
                run(['git','reset','--quiet','--',*[n[4:] for n in names],'watcher-umi-lab.sh'],cwd=ROOT,check=False)
                log('Local copy/staging failed; original repository files restored','WARN')
            raise
    head=run(['git','rev-parse','HEAD'],cwd=ROOT).stdout.strip()
    pushed=run(['git','push','-u','origin','main'],cwd=ROOT,timeout=140,check=False)
    remote=run(['git','ls-remote','origin','refs/heads/main'],cwd=ROOT,timeout=65).stdout
    if not remote.startswith(head+'\t'):raise ReleaseError('GitHub commit verification failed: '+pushed.stderr[-300:])
    log('GitHub main verified at '+head[:12],'PASS')

def deploy(stage,version,manifest):
    token=version+'-'+str(int(time.time()))+'-'+secrets.token_hex(4)
    remote='/var/www/.umi-lab-staging-'+token
    qr=shlex.quote(remote)
    ssh('mkdir -m 700 -p '+qr)
    try:
        run(['scp','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-P',SSH_PORT,
             '-r',str(stage/'app'),str(stage/'manifest.json'),SSH_HOST+':'+remote+'/'],timeout=180)
        # Stage-side digest verification: no trust in transport alone.
        check='''python3 - <<'VERIFY_STAGE'
import hashlib,json,pathlib
root=pathlib.Path('''+repr(remote)+''')
data=json.loads((root/'manifest.json').read_text())
for path,expected in data['sha256'].items():
    file=root/path
    if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest()!=expected:
        raise SystemExit('Remote SHA-256 mismatch for '+path)
print('SERVER SHA-256 PASSED')
VERIFY_STAGE'''
        log(ssh(check),'PASS')
        # Bootstrap secret is passed only to the remote shell via SSH stdin.
        password=BOOTSTRAP_PASSWORD
        email=CERTBOT_EMAIL
        script=("export UMI_ADMIN_PASSWORD="+shlex.quote(password)+'\n'+
                "export UMI_CERTBOT_EMAIL="+shlex.quote(email)+'\n'+
                'python3 '+qr+'/app/deploy/install.py --stage '+qr+' --version '+shlex.quote(version)+
                ' --id '+shlex.quote(token))
        result=ssh(script,timeout=440)
        for line in result.splitlines():
            if line.startswith(('SERVER UNIT TESTS','DEPLOYED','PUBLIC URL')):log('Remote installer: '+line,'PASS')
    finally:
        try:ssh('rm -rf -- '+qr,timeout=50)
        except Exception as exc:log('Remote staging cleanup failed: '+str(exc),'WARN')

def public_get(path):
    url=SITE+path+'?umi_release_check='+str(int(time.time()))
    req=urllib.request.Request(url,headers={'Cache-Control':'no-cache','User-Agent':'UMI-LAB-Release/0.1'})
    with urllib.request.urlopen(req,timeout=25) as resp:
        if resp.status!=200:raise ReleaseError(f'HTTP {resp.status} for {path}')
        return resp.read(1000000)

def verify_public(version):
    v=json.loads(public_get('version.json'))
    health=json.loads(public_get('api/health'))
    if v.get('version')!=version or v.get('project')!='umi-lab':raise ReleaseError('Public version mismatch')
    if health.get('version')!=version or health.get('storage')!='sqlite' or not health.get('ok'):
        raise ReleaseError('Public Flask/SQLite health mismatch')
    html=public_get('').decode('utf-8')
    if '<meta name="umi-version" content="'+version+'">' not in html:raise ReleaseError('Public interface version mismatch')
    return True

def install_version(version,public_ok):
    dest=STATE/'deployed.json';tmp=dest.with_suffix('.tmp')
    tmp.write_text(json.dumps({'version':version,'publicVerified':public_ok,'utc':dt.datetime.now(dt.timezone.utc).isoformat()},indent=2)+'\n')
    os.replace(tmp,dest)

def process(archive,dry_run):
    begin=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='umi-verify-',dir=STATE) as temp:
        stage=Path(temp)
        log('[1/4] VERIFY ZIP, SHA-256, PYTHON, JS, TESTS','STEP')
        version,manifest=validate(archive,stage)
        (stage/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        log(f'[1/4] VERIFIED v{version}: {len(manifest["sha256"])} app files ({elapsed(begin)})','PASS')
        if dry_run:
            log('[2/4] Git/SSH preflight skipped (dry run)')
            log('[3/4] GitHub push skipped (dry run)')
            log('[4/4] Ubuntu deploy skipped (dry run)')
            return 'DRY RUN / LOCAL VALIDATION ONLY'
        log('[2/4] GIT + SSH + DNS PREFLIGHT','STEP')
        git_preflight(version)
        log('[3/4] COMMIT + PUSH GITHUB MAIN','STEP')
        push_git(stage,version,manifest)
        log('[4/4] DEPLOY FLASK + SQLITE + NGINX + HTTPS','STEP')
        deploy(stage,version,manifest)
        try:
            verify_public(version)
            ok=True
            log(f'PUBLIC VERIFIED: {SITE} · Flask · SQLite · HTTPS','PASS')
        except Exception as e:
            ok=False
            log('ORIGIN DEPLOYED but public HTTPS UNVERIFIED: '+str(e),'WARN')
        install_version(version,ok)
        return 'SUCCESS / LIVE' if ok else 'PARTIAL / ORIGIN DEPLOYED / HTTPS UNVERIFIED'

def latest_logs():return sorted((STATE/'logs').glob('*.log'),key=lambda p:p.stat().st_mtime,reverse=True)

def main():
    global LOG,VERBOSE,COLOR
    p=argparse.ArgumentParser(description='UMI LAB verified ZIP watcher')
    g=p.add_mutually_exclusive_group()
    g.add_argument('--once',action='store_true');g.add_argument('--dry-run',action='store_true')
    g.add_argument('--status',action='store_true');g.add_argument('--logs',action='store_true')
    g.add_argument('--tail',action='store_true')
    g.add_argument('--configure',action='store_true',help='Save SSH and TLS contact settings once')
    g.add_argument('--show-config',action='store_true',help='Display persistent connection settings')
    p.add_argument('--interval',type=int,default=3);p.add_argument('--verbose',action='store_true')
    p.add_argument('--color',choices=('auto','always','never'),default='auto')
    args=p.parse_args();VERBOSE=args.verbose;COLOR=args.color
    if args.interval<1:p.error('Interval must be >= 1')
    UPDATES.mkdir(exist_ok=True);STATE.mkdir(mode=0o700,exist_ok=True)
    STATE.chmod(0o700)
    if not CONFIG_PATH.exists():save_config(dict(DEFAULT_CONFIG))
    if args.configure:
        configure();return 0
    if args.show_config:
        for key,value in SETTINGS.items():log(f'{key} = {value or "(not set)"}')
        log('Local settings file: '+str(CONFIG_PATH));return 0
    for folder in ('processed','failed','superseded'):(UPDATES/folder).mkdir(exist_ok=True)
    (STATE/'logs').mkdir(exist_ok=True,mode=0o700)
    if args.status:
        log('Watcher build '+WATCHER_BUILD,'PASS');log('Last deployed '+last_version())
        try:
            response=json.loads(public_get('api/health'))
            log('Public health '+str(response),'PASS')
        except Exception as e:log('Public verification unavailable: '+str(e),'WARN')
        return 0
    if args.logs:
        for f in latest_logs()[:15]:log(str(f))
        return 0
    if args.tail:
        logs=latest_logs()
        if not logs:log('No release logs','WARN');return 1
        log('LATEST LOG '+str(logs[0]))
        for line in logs[0].read_text().splitlines()[-120:]:print(line)
        return 0
    lock=(STATE/'watch.lock').open('w')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise ReleaseError('Another UMI watcher is already running')
    log('UMI LAB WATCHER v'+WATCHER_BUILD+' ACTIVE','PASS')
    log('Watching '+str(UPDATES)+' · '+EXPECTED_REMOTE+' · '+SSH_HOST+':'+SSH_PORT)
    log('Settings persist at '+str(CONFIG_PATH)+'; run --configure only to change them')
    retry={}
    while True:
        # Newest candidate first. A previously failed release must never delay
        # a corrected ZIP that has already arrived in the updates directory.
        candidates=sorted(UPDATES.glob('*.zip'),key=lambda p: vt(ZIP_RE.fullmatch(p.name).group(1)) if ZIP_RE.fullmatch(p.name) else (0,0,0),reverse=True)
        if (args.once or args.dry_run) and not candidates:
            log('No UMI LAB update ZIP in updates/','WARN');return 1
        failed=False
        for archive in candidates:
            m=ZIP_RE.fullmatch(archive.name)
            if not m:
                log('Ignoring unrelated ZIP '+archive.name,'WARN');continue
            if vt(m.group(1))<=vt(last_version()):
                archive.rename(UPDATES/'superseded'/archive.name)
                log('Superseded archive stored: '+archive.name,'WARN');continue
            if not (args.once or args.dry_run) and (time.time()-archive.stat().st_mtime<4 or time.time()<retry.get(archive.name,0)):continue
            stamp=dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
            LOG=STATE/'logs'/(stamp+'-'+archive.stem+'.log');LOG.touch(mode=0o600)
            started=time.monotonic();banner('START',m.group(1),'ZIP '+archive.name+' | WATCHER '+WATCHER_BUILD)
            outcome='FAILED / RELEASE NOT LIVE'
            try:
                outcome=process(archive,args.dry_run)
                if not args.dry_run:
                    archive.rename(UPDATES/'processed'/archive.name)
                    retry.pop(archive.name,None)
            except ArchiveError as e:
                failed=True;log('ARCHIVE REJECTED: '+str(e),'FAIL')
                if not args.dry_run:archive.rename(UPDATES/'failed'/archive.name)
            except Exception as e:
                failed=True;log('RELEASE FAILED: '+str(e),'FAIL')
                if not args.dry_run:
                    retry[archive.name]=time.time()+60
                    log('ZIP retained; retry in at least 60s after the issue is fixed','WARN')
            banner('END',m.group(1),'RESULT '+outcome+' | DURATION '+elapsed(started)+' | LOG '+str(LOG))
            LOG=None
        if args.once or args.dry_run:return 1 if failed else 0
        time.sleep(args.interval)

if __name__=='__main__':
    try:sys.exit(main())
    except KeyboardInterrupt:print('\nUMI LAB watcher stopped');sys.exit(0)
    except Exception as e:log(str(e),'FAIL');sys.exit(1)
UMI_WATCH_PY
