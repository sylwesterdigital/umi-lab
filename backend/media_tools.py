"""Bounded and intentionally conservative media validation, extraction and conversion.

External processors receive filenames in a temporary directory, never shell strings.
No external URLs, document macros, HTML, or embedded SVG scripts are allowed.
"""
import io
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET

MEDIA_TYPES = {
    '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
    '.webp': 'image/webp', '.gif': 'image/gif', '.svg': 'image/svg+xml',
    '.pdf': 'application/pdf', '.mp4': 'video/mp4', '.webm': 'video/webm',
    '.mov': 'video/quicktime', '.m4v': 'video/x-m4v',
    '.mp3': 'audio/mpeg', '.wav': 'audio/wav', '.ogg': 'audio/ogg',
    '.m4a': 'audio/mp4', '.flac': 'audio/flac',
}
MAX_UPLOAD = 22 * 1024 * 1024

class MediaError(ValueError):
    pass

def media_type(name, supplied=''):
    """Select MIME by extension rather than trusting a browser claim."""
    mime = MEDIA_TYPES.get(Path(name or '').suffix.lower())
    if not mime or (supplied and supplied != mime and supplied not in ('application/octet-stream', '')):
        # Some browsers submit unusual or empty MIME for SVG, MOV and M4A.
        if not mime or (supplied and supplied not in ('application/octet-stream',
            'video/mp4' if mime == 'video/x-m4v' else mime,
            'audio/x-m4a' if mime == 'audio/mp4' else mime,
            'image/svg+xml' if mime == 'image/svg+xml' else mime)):
            raise MediaError('Unsupported or mismatched media type')
    return mime

def clean_svg(blob):
    """Strict whitelist of SVG drawing primitives; rejects scripts and external resources."""
    if len(blob) > 2_000_000 or re.search(br'<!DOCTYPE|<!ENTITY|<\s*script\b', blob, re.I):
        raise MediaError('Unsafe SVG file')
    try: root = ET.fromstring(blob)
    except ET.ParseError: raise MediaError('Invalid SVG')
    ns = '{http://www.w3.org/2000/svg}'
    if root.tag not in ('svg', ns + 'svg'): raise MediaError('Invalid SVG root')
    allowed = {'svg','g','path','rect','circle','ellipse','line','polyline','polygon','text','tspan','defs',
               'linearGradient','radialGradient','stop','clipPath','mask','use','pattern','title','desc'}
    attrs = {'xmlns','viewBox','width','height','x','y','x1','x2','y1','y2','cx','cy','r','rx','ry',
             'd','points','transform','fill','stroke','stroke-width','stroke-linecap','stroke-linejoin',
             'stroke-dasharray','opacity','fill-opacity','stroke-opacity','id','offset','stop-color',
             'stop-opacity','font-family','font-size','font-weight','text-anchor','clip-path','mask',
             'gradientUnits','gradientTransform','preserveAspectRatio','href'}
    for el in root.iter():
        tag = el.tag.rsplit('}',1)[-1]
        if tag not in allowed:raise MediaError('SVG contains unsupported active content')
        for key,value in el.attrib.items():
            name = key.rsplit('}',1)[-1]
            if name not in attrs or name.startswith('on') or 'url(' in value.lower() or 'javascript:' in value.lower():
                raise MediaError('SVG contains unsafe attributes')
            if name=='href' and not re.fullmatch(r'#[A-Za-z_][\w.-]*', value):
                raise MediaError('SVG external references are blocked')
    return ET.tostring(root,encoding='utf-8',xml_declaration=True)

def validate_gif(blob):
    try:
        from PIL import Image, UnidentifiedImageError
        img=Image.open(io.BytesIO(blob))
        if img.format!='GIF' or img.width*img.height>20_000_000 or getattr(img,'n_frames',1)>200:
            raise MediaError('GIF exceeds dimensions or frame limit')
        img.verify()
    except (OSError, ValueError):raise MediaError('Invalid GIF')
    return blob

def pdf_text(blob):
    if not blob.startswith(b'%PDF-'):raise MediaError('Invalid PDF')
    try:
        from pypdf import PdfReader
        reader=PdfReader(io.BytesIO(blob), strict=True)
        if reader.is_encrypted:raise MediaError('Password-protected PDFs are not supported')
        if len(reader.pages)>120:raise MediaError('PDF exceeds 120 pages')
        chunks=[];remaining=120_000
        for page in reader.pages:
            if remaining<=0:break
            value=(page.extract_text() or '')[:remaining]
            chunks.append(value);remaining-=len(value)
        return '\n\n'.join(chunks)
    except MediaError:raise
    except Exception:raise MediaError('Could not read PDF')

def pdf_thumbnail(blob):
    """Optional first-page preview using Poppler; PDF still imports without it."""
    if not shutil.which('pdftoppm'):return None
    with tempfile.TemporaryDirectory(prefix='umi-pdf-') as work:
        source=Path(work)/'doc.pdf';source.write_bytes(blob)
        try:
            result=subprocess.run(['pdftoppm','-f','1','-l','1','-singlefile','-scale-to','650','-png',str(source),str(Path(work)/'cover')],
                                  capture_output=True,timeout=15,check=False)
            output=Path(work)/'cover.png'
            if result.returncode==0 and output.is_file() and output.stat().st_size<2_000_000:return output.read_bytes()
        except (OSError,subprocess.TimeoutExpired):pass
    return None

def ffmpeg_binary():
    binary=shutil.which('ffmpeg')
    if binary:return binary
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError,RuntimeError,OSError):return None

def transcode(blob,mime):
    """Return (browser MIME, extension, bytes); never treat submitted media as executable."""
    executable=ffmpeg_binary()
    if not executable:raise MediaError('FFmpeg is required for audio and video uploads')
    video=mime.startswith('video/')
    target_ext='mp4' if video else 'mp3'
    target_mime='video/mp4' if video else 'audio/mpeg'
    with tempfile.TemporaryDirectory(prefix='umi-ffmpeg-') as work:
        source=Path(work)/'input.bin';out=Path(work)/('output.'+target_ext)
        source.write_bytes(blob)
        command=[executable,'-nostdin','-hide_banner','-loglevel','error','-y','-i',str(source)]
        if video:
            command+=['-map','0:v:0','-map','0:a:0?','-t','180','-vf',"scale='min(1280,iw)':'min(720,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1",'-c:v','libx264','-preset','veryfast','-crf','26','-pix_fmt','yuv420p','-c:a','aac','-b:a','128k','-movflags','+faststart',str(out)]
        else:
            command+=['-map','0:a:0','-t','600','-vn','-c:a','libmp3lame','-b:a','128k',str(out)]
        try:result=subprocess.run(command,capture_output=True,timeout=50,check=False)
        except subprocess.TimeoutExpired:raise MediaError('Media conversion exceeded time limit')
        except OSError:raise MediaError('FFmpeg is unavailable')
        if result.returncode or not out.exists():raise MediaError('Could not convert media to browser playback format')
        if out.stat().st_size>22*1024*1024:raise MediaError('Converted media exceeds 22 MB')
        return target_mime,target_ext,out.read_bytes()
