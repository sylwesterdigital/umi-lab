#!/usr/bin/env python3
"""UMI LAB isolated Ubuntu installer. Run as root ONLY after watcher validation.

Never edits unrelated nginx files, services or apps. Keeps UMI-specific rollback artifacts.
"""
import argparse
import json
import os
import pwd
import re
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

BASE=Path('/opt/umi-lab')
DATA=Path('/var/lib/umi-lab')
CONFIG=Path('/etc/umi-lab')
UNIT=Path('/etc/systemd/system/umi-lab.service')
VHOST=Path('/etc/nginx/sites-available/umi-lab.top')
ENABLED=Path('/etc/nginx/sites-enabled/umi-lab.top')
ACME=Path('/var/www/umi-lab-acme')
DOMAIN='umi-lab.top'
CERT=Path('/etc/letsencrypt/live/umi-lab.top/fullchain.pem')
KEY=Path('/etc/letsencrypt/live/umi-lab.top/privkey.pem')
BACKUPS=DATA/'deploy-backups'
SERVICE='umi-lab.service'

class InstallError(RuntimeError):pass

def run(args,*,timeout=160,check=True,env=None,cwd=None):
    result=subprocess.run([str(a) for a in args],capture_output=True,text=True,timeout=timeout,env=env,cwd=cwd)
    if check and result.returncode:
        # Never include environment values or secrets in error output.
        raise InstallError(f'{args[0]} exited {result.returncode}: '+(result.stderr or result.stdout)[-1000:])
    return result


def write_atomic(path,data,mode=0o644):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(prefix='.'+path.name+'.',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as handle:handle.write(data);handle.flush();os.fsync(handle.fileno())
        os.chmod(temp,mode);os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)


def check_binary(name):
    if not shutil.which(name):raise InstallError(f'Missing {name}. Install it before deployment.')


def port_open(port):
    # A bind attempt catches current listeners; a separate nginx reference guard
    # prevents selecting ports already reserved but temporarily idle.
    for addr in ('127.0.0.1','0.0.0.0'):
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as sock:
            try:sock.bind((addr,port))
            except OSError:return True
    return False


def used_by_nginx(port):
    for root in [Path('/etc/nginx/sites-enabled'),Path('/etc/nginx/conf.d')]:
        if not root.exists():continue
        for f in root.glob('*.conf') if root.name=='conf.d' else root.iterdir():
            try:
                if f.is_file() and f.resolve()!=VHOST.resolve() and re.search(r':'+str(port)+r'\b',f.read_text()):return True
            except (OSError,UnicodeError):pass
    return False


def choose_port():
    if UNIT.exists():
        match=re.search(r'--bind\s+127\.0\.0\.1:(\d+)',UNIT.read_text())
        if match:
            port=int(match.group(1))
            if not 1024<=port<=65535:raise InstallError('Invalid existing UMI port')
            return port
    for port in range(5057,5100):
        if not port_open(port) and not used_by_nginx(port):return port
    raise InstallError('No free UMI application port in 5057–5099; no port was changed')


def http_nginx(port):
    return f'''# UMI LAB isolated vhost - managed by UMI watcher
server {{
    listen 80;
    server_name {DOMAIN};
    client_max_body_size 70m;
    location /.well-known/acme-challenge/ {{ root {ACME}; default_type text/plain; }}
    location / {{
        proxy_pass http://127.0.0.1:{port};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 230s;
        proxy_connect_timeout 10s;
    }}
}}
'''


def https_nginx(port):
    return f'''# UMI LAB isolated HTTPS vhost - managed by UMI watcher
server {{
    listen 80;
    server_name {DOMAIN};
    location /.well-known/acme-challenge/ {{ root {ACME}; default_type text/plain; }}
    location / {{ return 301 https://$host$request_uri; }}
}}
server {{
    listen 443 ssl;
    server_name {DOMAIN};
    ssl_certificate {CERT};
    ssl_certificate_key {KEY};
    ssl_protocols TLSv1.2 TLSv1.3;
    client_max_body_size 70m;
    add_header Strict-Transport-Security "max-age=31536000" always;
    location / {{
        proxy_pass http://127.0.0.1:{port};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 230s;
        proxy_connect_timeout 10s;
    }}
}}
'''


def unit_source(port):
    return f'''[Unit]
Description=UMI LAB Flask API and studio
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=umi-lab
Group=umi-lab
WorkingDirectory={BASE}/current
Environment=UMI_DATA_DIR={DATA}
Environment=UMI_HTTPS=1
Environment=PYTHONUNBUFFERED=1
Environment=UMI_ENABLE_BLENDER=1
ExecStart={BASE}/current/.venv/bin/gunicorn --workers 1 --threads 4 --timeout 220 --bind 127.0.0.1:{port} backend.wsgi:app
Restart=on-failure
RestartSec=2
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths={DATA}
ProtectHome=true
UMask=0077

[Install]
WantedBy=multi-user.target
'''


def prepare_blender():
    """Install Blender via Ubuntu APT only when absent, then verify headless bpy.

    This intentionally does not upgrade other packages or touch other services.
    Run before switching the current UMI release to keep deployment atomic.
    """
    binary=shutil.which('blender')
    if not binary:
        if not shutil.which('apt-get'):
            raise InstallError('Blender missing; APT is unavailable on this server')
        if shutil.disk_usage('/var').free < 900*1024*1024:
            raise InstallError('Not enough free disk space for Blender installation (900 MB required)')
        print('BLENDER: installing Ubuntu Blender package (UMI 3D optimisation)',flush=True)
        apt_env={**os.environ,'DEBIAN_FRONTEND':'noninteractive','APT_LISTCHANGES_FRONTEND':'none'}
        cmd=['apt-get','-o','DPkg::Lock::Timeout=45','install','--no-install-recommends','-y','blender']
        first=run(cmd,timeout=205,check=False,env=apt_env)
        if first.returncode:
            # Stale/missing APT indexes are common on a newly provisioned host.
            # Do not perform a global upgrade; update package indexes only.
            run(['apt-get','update','-qq'],timeout=75,env=apt_env)
            run(cmd,timeout=205,env=apt_env)
        binary=shutil.which('blender')
        if not binary:raise InstallError('Blender package installation finished but binary was not found')
    # A version string alone does not establish that headless Python/GLB works.
    check=run([binary,'--background','--factory-startup','--disable-autoexec',
               '--python-expr','import bpy; assert hasattr(bpy.ops.import_scene, "gltf") and hasattr(bpy.ops.export_scene, "gltf"); print("UMI_BLENDER_OK")'],
              timeout=45,check=False)
    if check.returncode or 'UMI_BLENDER_OK' not in check.stdout:
        raise InstallError('Blender headless GLB capability check failed: '+(check.stderr or check.stdout)[-500:])
    print('BLENDER: headless GLB import/export verified; optimisation enabled',flush=True)
    return binary


def prepare_gltf_transform():
    """Install optional advanced GLB codecs into UMI-only tools directory.

    Unavailable npm / unsupported Node must not break Blender-only releases.
    Never changes system npm global packages or unrelated applications.
    """
    destination=BASE/'tools'/'gltf-transform'
    existing=destination/'node_modules'/'.bin'/'gltf-transform'
    if existing.is_file() or shutil.which('gltf-transform'):
        print('GLTF: optional texture/mesh codecs available',flush=True)
        return True
    node=shutil.which('node');npm=shutil.which('npm')
    if not node or not npm:
        print('GLTF: optional codec tools unavailable (Node/npm absent); Blender presets remain enabled',flush=True)
        return False
    try:
        version=run([node,'--version'],timeout=10,check=False)
        import re as _re
        match=_re.match(r'v(\d+)',version.stdout.strip())
        if not match or int(match.group(1))<20:
            print('GLTF: Node 20+ needed for optional codecs; Blender presets remain enabled',flush=True)
            return False
        destination.mkdir(parents=True,exist_ok=True)
        result=run([npm,'--prefix',str(destination),'install','--no-save','--no-audit','--no-fund',
                    '@gltf-transform/cli@4.5.0'],timeout=140,check=False)
        if result.returncode or not existing.is_file():
            print('GLTF: optional codec installation skipped; Blender presets remain enabled',flush=True)
            return False
        print('GLTF: optional compression codecs ready',flush=True)
        return True
    except (OSError,subprocess.TimeoutExpired):
        print('GLTF: optional CLI install unavailable; Blender presets remain enabled',flush=True)
        return False

def _blender_sample_glb():
    """Return a tiny valid glTF 2.0 triangle for end-to-end importer/exporter testing."""
    import struct
    vertices=struct.pack('<9f',0.0,0.0,0.0,1.0,0.0,0.0,0.0,1.0,0.0)
    indices=struct.pack('<3H',0,1,2)+b'\0\0'
    binary=vertices+indices
    scene={'asset':{'version':'2.0'},'scene':0,'scenes':[{'nodes':[0]}],
           'nodes':[{'mesh':0}],'meshes':[{'primitives':[{'attributes':{'POSITION':0},'indices':1}]}],
           'buffers':[{'byteLength':len(binary)}],
           'bufferViews':[{'buffer':0,'byteOffset':0,'byteLength':36,'target':34962},
                          {'buffer':0,'byteOffset':36,'byteLength':6,'target':34963}],
           'accessors':[{'bufferView':0,'componentType':5126,'count':3,'type':'VEC3',
                         'min':[0,0,0],'max':[1,1,0]},
                        {'bufferView':1,'componentType':5123,'count':3,'type':'SCALAR'}]}
    doc=json.dumps(scene,separators=(',',':')).encode('utf-8')
    doc+=b' '*((-len(doc))%4)
    return (struct.pack('<4sII',b'glTF',2,12+8+len(doc)+8+len(binary))+
            struct.pack('<I4s',len(doc),b'JSON')+doc+
            struct.pack('<I4s',len(binary),b'BIN\x00')+binary)

def verify_blender_optimiser(release):
    """Exercise the actual UMI script as the same user that runs the service.

    A `bpy` import check alone does not detect broken GLTF addons or missing
    Python modules. This check runs before switching the active release.
    """
    # The installer runs outside the Flask virtualenv; load the release's
    # stdlib-only Blender helpers by file path rather than relying on PYTHONPATH.
    import importlib.util
    helper=importlib.util.spec_from_file_location('_umi_blender_helper',str(release/'backend/mesh_optimize.py'))
    runtime=importlib.util.module_from_spec(helper)
    helper.loader.exec_module(runtime)
    blender_error_details=runtime.blender_error_details
    blender_missing_module=runtime.blender_missing_module
    blender_runtime_env=runtime.blender_runtime_env
    binary=shutil.which('blender')
    if not binary:raise InstallError('Blender binary missing before optimisation smoke check')
    with tempfile.TemporaryDirectory(prefix='blender-smoke-',dir=DATA) as temp:
        folder=Path(temp)
        account=pwd.getpwnam('umi-lab')
        os.chown(folder,account.pw_uid,account.pw_gid)
        os.chmod(folder,0o700)
        source=folder/'triangle.glb';result=folder/'triangle-optimised.glb'
        source.write_bytes(_blender_sample_glb())
        os.chown(source,account.pw_uid,account.pw_gid)
        cmd=[binary,'--background','--factory-startup','--disable-autoexec','--python',
             str(release/'backend/blender_clean.py'),'--',str(source),str(result),'0.65','1.0']
        # Run as UMI rather than root; detect missing modules and filesystem ACLs.
        if shutil.which('runuser'):
            cmd=['runuser','-u','umi-lab','--',*cmd]
        else:
            raise InstallError('runuser unavailable: cannot verify Blender under UMI account')
        attempt=run(cmd,timeout=90,check=False,env=blender_runtime_env())
        if attempt.returncode or not result.is_file() or result.stat().st_size<12:
            missing=blender_missing_module(attempt)
            if missing:
                # Only known standard modules may be installed. No arbitrary
                # Python package names from a model file are ever executed.
                known={'numpy':'python3-numpy','PIL':'python3-pil','yaml':'python3-yaml'}
                package=known.get(missing.split('.')[0])
                if package and shutil.which('apt-get'):
                    apt_env={**os.environ,'DEBIAN_FRONTEND':'noninteractive'}
                    print('BLENDER: repairing missing dependency '+missing,flush=True)
                    run(['apt-get','-o','DPkg::Lock::Timeout=45','install','--no-install-recommends','-y',package],
                        timeout=200,env=apt_env)
                    attempt=run(cmd,timeout=90,check=False,env=blender_runtime_env())
                if attempt.returncode:
                    raise InstallError('Blender optimisation cannot start; missing module '+missing+
                                       '. '+blender_error_details(attempt))
            if attempt.returncode or not result.is_file() or result.stat().st_size<12:
                raise InstallError('Blender optimisation smoke test failed: '+blender_error_details(attempt))
        if result.open('rb').read(4)!=b'glTF':
            raise InstallError('Blender optimiser produced an invalid GLB')
        print('BLENDER: real GLB import, optimise and export PASSED as umi-lab',flush=True)
        # Native Blender Draco is independent of the optional glTF Transform CLI.
        # Probe the actual exported GLB as the service user. Do not block a
        # deployment with unsupported Draco builds: the UI will disable it.
        draco_file=folder/'draco-probe.glb'
        draco_cmd=[binary,'--background','--factory-startup','--disable-autoexec','--python',
                   str(release/'backend/blender_draco_probe.py'),'--',str(draco_file)]
        draco_cmd=['runuser','-u','umi-lab','--',*draco_cmd]
        try:
            draco_run=run(draco_cmd,timeout=60,check=False,env=blender_runtime_env())
            if draco_run.returncode==0 and draco_file.is_file() and 'UMI_DRACO_OK' in (draco_run.stdout or ''):
                print('BLENDER: native Draco GLB compression level 6 VERIFIED as umi-lab',flush=True)
            else:
                print('BLENDER: native Draco exporter UNAVAILABLE; optimizer will disable this codec ('+
                      blender_error_details(draco_run)[:180]+')',flush=True)
        except (OSError,subprocess.TimeoutExpired):
            print('BLENDER: native Draco exporter probe could not finish; optimization remains available without Draco',flush=True)

def snapshot(token):
    path=BACKUPS/token
    if path.exists():raise InstallError('Snapshot name already exists')
    path.mkdir(parents=True,mode=0o700)
    current=BASE/'current'
    record={'token':token,'old_current':str(current.resolve()) if current.is_symlink() else None,
            'had_unit':UNIT.exists(),'had_vhost':VHOST.exists(),
            'was_enabled':ENABLED.is_symlink(),'was_active':run(['systemctl','is-active','--quiet',SERVICE],check=False).returncode==0,
            'timestamp':int(time.time())}
    if UNIT.exists():shutil.copy2(UNIT,path/'unit.prev')
    if VHOST.exists():shutil.copy2(VHOST,path/'nginx.prev')
    db=DATA/'umi.sqlite3'
    if db.is_file():
        with sqlite3.connect(str(db)) as conn,sqlite3.connect(str(path/'database.backup.sqlite3')) as backup:conn.backup(backup)
        os.chmod(path/'database.backup.sqlite3',0o600)
    write_atomic(path/'receipt.json',json.dumps(record,indent=2),0o600)
    return path,record


def rollback(snapshot_path,record):
    """Roll back UMI service and nginx config only. Never erase database or media."""
    active=BASE/'current'
    old=record.get('old_current')
    if old and Path(old).is_dir():
        tmp=BASE/'.rollback-current'
        tmp.unlink(missing_ok=True);tmp.symlink_to(old);os.replace(tmp,active)
    elif active.is_symlink():active.unlink()
    if record.get('had_unit') and (snapshot_path/'unit.prev').exists():
        shutil.copy2(snapshot_path/'unit.prev',UNIT)
    else:UNIT.unlink(missing_ok=True)
    if record.get('had_vhost') and (snapshot_path/'nginx.prev').exists():
        shutil.copy2(snapshot_path/'nginx.prev',VHOST)
    else:VHOST.unlink(missing_ok=True)
    if record.get('was_enabled'):
        if not ENABLED.exists() and not ENABLED.is_symlink():ENABLED.symlink_to(VHOST)
    else:
        if ENABLED.is_symlink():ENABLED.unlink()
    run(['systemctl','daemon-reload'])
    if record.get('was_active'):run(['systemctl','restart',SERVICE],check=False)
    else:run(['systemctl','stop',SERVICE],check=False)
    run(['nginx','-t']);run(['systemctl','reload','nginx'])
    print('UMI rollback complete; SQLite and media retained',flush=True)


def prepare_identity():
    if not shutil.which('useradd'):raise InstallError('useradd is required')
    try:pwd.getpwnam('umi-lab')
    except KeyError:run(['useradd','--system','--home-dir',str(DATA),'--shell','/usr/sbin/nologin','umi-lab'])
    DATA.mkdir(parents=True,exist_ok=True,mode=0o700)
    ACME.mkdir(parents=True,exist_ok=True)
    for path in (DATA,DATA/'media'):
        path.mkdir(parents=True,exist_ok=True,mode=0o700)
        user=pwd.getpwnam('umi-lab')
        os.chown(path,user.pw_uid,user.pw_gid)
        os.chmod(path,0o700)
    BACKUPS.mkdir(parents=True,mode=0o700,exist_ok=True)
    os.chmod(BACKUPS,0o700)


def prepare_release(stage,version):
    release=BASE/'releases'/version
    if release.exists():
        current=BASE/'current'
        if current.is_symlink() and current.resolve()==release.resolve():
            raise InstallError('Refusing to overwrite the active release')
        # Failed attempts may leave an orphaned release tree. Rebuild it from the
        # newly validated stage; never reuse half-installed dependencies.
        shutil.rmtree(release)
    release.parent.mkdir(parents=True,exist_ok=True)
    shutil.copytree(stage/'app',release,ignore=shutil.ignore_patterns('__pycache__','*.pyc'),symlinks=False)
    run(['python3','-m','venv',str(release/'.venv')],timeout=90)
    py=release/'.venv/bin/python'
    pip=release/'.venv/bin/pip'
    run([pip,'install','--no-input','--disable-pip-version-check','-r',str(release/'backend/requirements.txt')],timeout=240)
    # Verify Python and the full Flask regression suite on Ubuntu before activating.
    result=run([py,'-m','unittest','discover','-s','tests','-v'],timeout=90,check=False,
               env={**os.environ,'PYTHONPATH':str(release),'UMI_DATA_DIR':str(DATA/'test-sandbox')},cwd=release)
    if result.returncode or 'skipped' in result.stderr.lower():
        raise InstallError('Server full unit/integration tests failed or skipped: '+result.stderr[-1300:])
    shutil.rmtree(DATA/'test-sandbox',ignore_errors=True)
    print('SERVER UNIT TESTS PASSED: OK',flush=True)
    return release


def seed_admin(release):
    pw=os.environ.get('UMI_ADMIN_PASSWORD','')
    check_script='''import os
from backend import db
path=os.environ['UMI_DATA_DIR']
db.init(path)
with db.connect(path) as con:
    count=con.execute('SELECT count(*) FROM users').fetchone()[0]
    if count==0:
        password=os.environ.get('UMI_ADMIN_PASSWORD','')
        if len(password)<12:raise SystemExit('Set UMI_ADMIN_PASSWORD (12+ chars) for first deployment')
        db.create_user(con,'admin',password,'UMI Creator',role='admin')
    else:
        print('Existing UMI accounts preserved')
'''
    cmd=[str(release/'.venv/bin/python'),'-c',check_script]
    run(cmd,env={**os.environ,'PYTHONPATH':str(release),'UMI_DATA_DIR':str(DATA)},timeout=25)
    user=pwd.getpwnam('umi-lab')
    # Account provisioning creates DB files, lock them down for service access.
    for item in DATA.iterdir():
        if item.name=='deploy-backups':continue
        if item.is_file():os.chown(item,user.pw_uid,user.pw_gid);os.chmod(item,0o600)


def http_health(port,version):
    from urllib.request import urlopen
    problem='no successful health response'
    for i in range(18):
        try:
            with urlopen(f'http://127.0.0.1:{port}/api/health',timeout=4) as res:
                body=json.loads(res.read(4096))
            if body.get('ok') and body.get('version')==version and body.get('storage')=='sqlite':return
            problem=('health payload mismatch: expected release '+version+
                     ', got version='+repr(str(body.get('version'))[:32])+
                     ', storage='+repr(str(body.get('storage'))[:32]))
        except Exception as exc:
            problem=type(exc).__name__+': '+str(exc)[:160]
        time.sleep(1)
    raise InstallError(f'UMI service failed local health check on port {port}: {problem}')


def configure_nginx(port):
    VHOST.parent.mkdir(parents=True,exist_ok=True)
    if ENABLED.exists() and not ENABLED.is_symlink():raise InstallError('Existing nginx enabled entry is not a symlink; refusing overwrite')
    if ENABLED.is_symlink() and ENABLED.resolve()!=VHOST.resolve():
        raise InstallError('umi-lab.top nginx link points to an unexpected config')
    write_atomic(VHOST,http_nginx(port))
    if not ENABLED.is_symlink():ENABLED.symlink_to(VHOST)
    run(['nginx','-t']);run(['systemctl','reload','nginx'])
    if not (CERT.is_file() and KEY.is_file()):
        if not shutil.which('certbot'):
            raise InstallError('certbot is missing. Install certbot for HTTPS, then retry ZIP')
        email=os.environ.get('UMI_CERTBOT_EMAIL','').strip()
        args=['certbot','certonly','--webroot','-w',str(ACME),'-d',DOMAIN,
              '--non-interactive','--agree-tos','--keep-until-expiring']
        if email:args+=['--email',email]
        else:args+=['--register-unsafely-without-email']
        run(args,timeout=210)
    if not (CERT.is_file() and KEY.is_file()):raise InstallError('TLS certificate not available')
    write_atomic(VHOST,https_nginx(port))
    run(['nginx','-t']);run(['systemctl','reload','nginx'])


def install(stage,version,token):
    if os.geteuid()!=0:raise InstallError('Installer must run as root')
    if not re.fullmatch(r'0\.\d+\.\d+|[1-9]\d*\.\d+\.\d+',version):raise InstallError('Invalid semver')
    if not re.fullmatch(r'[A-Za-z0-9_.-]{8,90}',token):raise InstallError('Invalid release token')
    for name in ('python3','nginx','systemctl','git'):check_binary(name)
    stage=Path(stage).resolve()
    if not (stage/'app/version.json').is_file():raise InstallError('Missing stage files')
    version_info=json.loads((stage/'app/version.json').read_text())
    if version_info.get('version')!=version or version_info.get('project')!='umi-lab':raise InstallError('Stage version mismatch')
    port=choose_port()
    prepare_identity()
    snap,record=snapshot(token)
    release=None
    try:
        release=prepare_release(stage,version)
        prepare_blender()
        verify_blender_optimiser(release)
        seed_admin(release)
        prepare_gltf_transform()
        write_atomic(UNIT,unit_source(port))
        link=BASE/'current';temp=BASE/'.next-current'
        temp.unlink(missing_ok=True);temp.symlink_to(release)
        os.replace(temp,link)
        run(['systemctl','daemon-reload']);run(['systemctl','enable',SERVICE]);run(['systemctl','restart',SERVICE])
        http_health(port,version)
        configure_nginx(port)
        print(f'DEPLOYED {version}; Flask healthy; SQLite preserved; port={port}; backup={snap}',flush=True)
        print('PUBLIC URL: https://umi-lab.top',flush=True)
    except Exception:
        try:rollback(snap,record)
        except Exception as error:print('ROLLBACK WARNING: '+str(error),file=sys.stderr)
        # Only dispose of this failed attempt, never the restored prior release.
        if release and release.is_dir() and record.get('old_current')!=str(release):
            shutil.rmtree(release,ignore_errors=True)
        raise


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--stage');parser.add_argument('--version');parser.add_argument('--id');parser.add_argument('--rollback')
    args=parser.parse_args()
    if args.rollback:
        path=Path(args.rollback).resolve()
        if path.parent!=BACKUPS or not (path/'receipt.json').is_file():raise InstallError('Invalid UMI rollback path')
        record=json.loads((path/'receipt.json').read_text())
        rollback(path,record)
    else:
        if not (args.stage and args.version and args.id):parser.error('--stage, --version and --id are required')
        install(args.stage,args.version,args.id)

if __name__=='__main__':
    try:main()
    except (InstallError,subprocess.TimeoutExpired,OSError) as e:
        print('INSTALL FAILED: '+str(e),file=sys.stderr);sys.exit(1)
