"""Safe, bounded GLB lookup from saved 3D artifacts (no extracted filesystem paths).
An AHOLO G1 ZIP may not contain a viewer-ready GLB; prefer its separate GLB output.
"""
import zipfile
from pathlib import Path

MAX_PREVIEW = 60_000_000


def _valid_glb_header(blob, header_only=False):
    return (len(blob) >= 12 and blob[:4] == b'glTF' and int.from_bytes(blob[4:8], 'little') == 2
            and 12 <= int.from_bytes(blob[8:12], 'little') <= MAX_PREVIEW
            and (header_only or int.from_bytes(blob[8:12], 'little') <= len(blob)))


def preview_blob(path, sidecar=None):
    """Return a viewer-safe GLB or None. Never unpack ZIP content onto disk."""
    path = Path(path)
    if sidecar is not None:
        sidecar = Path(sidecar)
        if sidecar.is_file():
            if sidecar.stat().st_size <= MAX_PREVIEW:
                blob = sidecar.read_bytes()
                if _valid_glb_header(blob):
                    return blob
    if not path.is_file():
        return None
    if path.suffix.lower() == '.glb':
        if path.stat().st_size > MAX_PREVIEW:
            return None
        blob = path.read_bytes()
        return blob if _valid_glb_header(blob) else None
    if path.suffix.lower() != '.zip':
        return None
    try:
        with zipfile.ZipFile(path) as z:
            members = [m for m in z.infolist() if not m.is_dir() and m.filename.lower().endswith('.glb')
                       and 12 <= m.file_size <= MAX_PREVIEW]
            for member in sorted(members, key=lambda m: m.file_size, reverse=True):
                with z.open(member) as stream:
                    blob = stream.read(MAX_PREVIEW + 1)
                if _valid_glb_header(blob):
                    return blob
    except (OSError, zipfile.BadZipFile, RuntimeError, ValueError):
        return None
    return None


def preview_is_ready(path, sidecar=None):
    """Check only bounded headers where possible, avoid loading a large model for listing."""
    path = Path(path)
    if sidecar is not None and Path(sidecar).is_file():
        with Path(sidecar).open('rb') as stream:
            header = stream.read(12)
        return (_valid_glb_header(header, header_only=True) and
                int.from_bytes(header[8:12], 'little') == Path(sidecar).stat().st_size)
    if not path.is_file():return False
    if path.suffix.lower() == '.glb':
        if path.stat().st_size > MAX_PREVIEW:return False
        with path.open('rb') as stream:header=stream.read(12)
        return (_valid_glb_header(header, header_only=True) and
                int.from_bytes(header[8:12], 'little') == path.stat().st_size)
    if path.suffix.lower() != '.zip':return False
    try:
        with zipfile.ZipFile(path) as z:
            return any((not m.is_dir() and m.filename.lower().endswith('.glb') and
                       12 <= m.file_size <= MAX_PREVIEW) for m in z.infolist())
    except (OSError, zipfile.BadZipFile, RuntimeError):
        return False
