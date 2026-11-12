"""UMI LAB bounded multimedia transformations and optional HLS derivatives.

No subprocess shell, remote input URLs, user-provided ffmpeg filters, or mutable source files.
Every output is written to an isolated temporary directory and validated by size.
"""
import io
import math
import shutil
import subprocess
import tempfile
from pathlib import Path
from PIL import Image, ImageOps
from .media_tools import ffmpeg_binary, MediaError

MAX_RESULT=35*1024*1024


def number(value, low, high, default):
    try:
        n=float(value)
        return min(max(n,low),high) if math.isfinite(n) else default
    except (TypeError, ValueError):return default


def runner(args, timeout=55):
    try:
        p=subprocess.run(args, stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout,check=False)
    except (OSError, subprocess.TimeoutExpired):raise MediaError('Media processing unavailable or timed out')
    if p.returncode:raise MediaError('Media processing failed: '+p.stderr.decode('utf-8','replace')[-240:].strip())


def hls_from_file(source, directory, mime):
    """Create a bounded VOD HLS playlist, manifest references relative segments only."""
    binary=ffmpeg_binary()
    if not binary:return False
    directory=Path(directory);directory.mkdir(parents=True, exist_ok=True,mode=0o700)
    segment=directory/'seg_%04d.ts';playlist=directory/'index.m3u8'
    cmd=[binary,'-nostdin','-hide_banner','-loglevel','error','-y','-i',str(source)]
    if mime.startswith('video/'):
        cmd += ['-map','0:v:0','-map','0:a:0?','-t','180','-c:v','libx264','-preset','veryfast','-crf','28','-pix_fmt','yuv420p','-g','48','-keyint_min','48','-sc_threshold','0','-c:a','aac','-b:a','96k']
    else:
        cmd += ['-vn','-map','0:a:0','-t','600','-c:a','aac','-b:a','96k']
    cmd+=['-f','hls','-hls_time','4','-hls_playlist_type','vod','-hls_list_size','0','-hls_segment_filename',str(segment),str(playlist)]
    try:
        runner(cmd,60)
        files=list(directory.glob('*'))
        if len(files)>250 or sum(f.stat().st_size for f in files)>35*1024*1024:raise MediaError('HLS exceeds file limit')
        if not playlist.is_file():raise MediaError('No playlist')
        return True
    except MediaError:
        shutil.rmtree(directory,ignore_errors=True)
        return False


def transform_media(blob,mime,operation,opts):
    """Return (bytes, output_mime, extension, label). All actions are local and non-destructive."""
    if mime.startswith('image/'):
        if operation not in ('webp','jpeg','png','shrink'):raise MediaError('Unsupported image operation')
        try:
            im=Image.open(io.BytesIO(blob))
            if im.width*im.height>20_000_000:raise MediaError('Image too large')
            im=ImageOps.exif_transpose(im)
            if operation=='shrink':
                ratio=number(opts.get('scale'),.1,1,.5); im.thumbnail((max(1,int(im.width*ratio)),max(1,int(im.height*ratio))))
                ext='webp';target='image/webp'
            else:ext={'jpeg':'jpg','png':'png','webp':'webp'}[operation];target={'jpeg':'image/jpeg','png':'image/png','webp':'image/webp'}[operation]
            out=io.BytesIO()
            if ext=='webp':im.save(out,'WEBP',quality=int(number(opts.get('quality'),30,95,80)),method=5)
            elif ext=='jpg':im.convert('RGB').save(out,'JPEG',quality=int(number(opts.get('quality'),30,95,82)),optimize=True)
            else:im.save(out,'PNG',optimize=True)
            result=out.getvalue()
            if len(result)>MAX_RESULT:raise MediaError('Processed image exceeds size limit')
            return result,target,ext,operation
        except (OSError,ValueError) as e:raise MediaError('Could not process image') from e
    if not mime.startswith(('audio/','video/')):raise MediaError('This operation requires audio or video')
    video=mime.startswith('video/')
    allowed_video={'trim','speed','resize','gif','compress','audio-replace','audio-mix','mute','mp4','webm'}
    allowed_audio={'trim','speed','denoise','compress','mp3','m4a'}
    if operation not in (allowed_video if video else allowed_audio):raise MediaError('Unsupported operation for this media type')
    executable=ffmpeg_binary()
    if not executable:raise MediaError('FFmpeg is unavailable on the server')
    start=number(opts.get('start'),0,10000,0);end=number(opts.get('end'),0,10000,0)
    speed=number(opts.get('speed'),.25,4,1)
    if end and end<=start:raise MediaError('End timestamp must be after start')
    ratio=number(opts.get('scale'),.1,1,.75)
    quality=int(number(opts.get('quality'),20,42,27))
    with tempfile.TemporaryDirectory(prefix='umi-process-') as root:
        directory=Path(root)
        source=directory/'source.dat';source.write_bytes(blob)
        if operation in ('audio-replace','audio-mix'):
            secondary=opts.get('_audio_bytes')
            if not isinstance(secondary,bytes) or not secondary:raise MediaError('Select an audio file from your project')
            audio_input=directory/'replacement.dat';audio_input.write_bytes(secondary)
        if operation=='gif':ext='gif';outmime='image/gif'
        elif not video:ext='m4a' if operation=='m4a' else 'mp3';outmime='audio/mp4' if ext=='m4a' else 'audio/mpeg'
        else:ext='webm' if operation=='webm' else 'mp4';outmime='video/webm' if ext=='webm' else 'video/mp4'
        out=directory/('out.'+ext)
        args=[executable,'-nostdin','-hide_banner','-loglevel','error','-y','-i',str(source)]
        if operation=='trim':
            if start:args+=['-ss',str(start)]
            if end:args+=['-t',str(min(end-start,180 if video else 600))]
        else:args+=['-t',str(180 if video else 600)]
        if operation=='gif':
            if start:args+=['-ss',str(start)]
            args+=['-t',str(min(8,end-start) if end else 8),'-vf',"fps=10,scale='min(640,iw)':-2:flags=lanczos",'-loop','0',str(out)]
        elif video:
            if operation in ('audio-replace','audio-mix'):
                args+=['-i',str(audio_input)]
                if operation=='audio-replace':
                    args+=['-map','0:v:0','-map','1:a:0','-t','180','-c:v','libx264','-crf','26','-pix_fmt','yuv420p','-c:a','aac','-b:a','128k','-shortest','-movflags','+faststart',str(out)]
                else:
                    args+=['-filter_complex','[0:a:0][1:a:0]amix=inputs=2:duration=first:dropout_transition=1[a]','-map','0:v:0','-map','[a]','-t','180','-c:v','libx264','-crf','26','-pix_fmt','yuv420p','-c:a','aac','-b:a','128k','-shortest','-movflags','+faststart',str(out)]
                runner(args,55)
                if not out.is_file() or out.stat().st_size>MAX_RESULT:raise MediaError('Processed video missing or too large')
                return out.read_bytes(),outmime,ext,operation
            filters=[]
            if operation in ('resize','compress'):filters.append(f"scale=trunc(iw*{ratio}/2)*2:trunc(ih*{ratio}/2)*2")
            if operation=='speed':filters.append(f'setpts=PTS/{speed}')
            args+=['-map','0:v:0','-map','0:a:0?']
            if filters:args+=['-vf',','.join(filters)]
            if ext=='webm':args+=['-c:v','libvpx-vp9','-b:v','0','-crf',str(quality+5),'-c:a','libopus','-b:a','96k']
            else:args+=['-c:v','libx264','-preset','veryfast','-crf',str(quality),'-pix_fmt','yuv420p','-c:a','aac','-b:a','112k','-movflags','+faststart']
            if operation=='speed':
                # `atempo` supports 0.5..2.0; chain for wider requested rates.
                atr=[];current=speed
                while current>2:atr.append('atempo=2');current/=2
                while current<.5:atr.append('atempo=0.5');current*=2
                atr.append('atempo='+str(round(current,5)))
                args+=['-filter:a',','.join(atr)]
            if operation=='mute':args+=['-an']
            args+=[str(out)]
        else:
            args+=['-map','0:a:0','-vn']
            if operation=='speed':
                chain=[];current=speed
                while current>2:chain.append('atempo=2');current/=2
                while current<.5:chain.append('atempo=0.5');current*=2
                chain.append('atempo='+str(round(current,5)));args+=['-af',','.join(chain)]
            if operation=='denoise':args+=['-af','afftdn=nf=-25']
            if ext=='m4a':args+=['-c:a','aac','-b:a','128k']
            else:args+=['-c:a','libmp3lame','-b:a','96k' if operation=='compress' else '160k']
            args+=[str(out)]
        runner(args,55)
        if not out.is_file() or out.stat().st_size>MAX_RESULT:raise MediaError('Processed result missing or too large')
        return out.read_bytes(),outmime,ext,operation
