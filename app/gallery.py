"""
Gallery API used by the web app: browse, preview, download and delete what is stored in storage/.

Everything goes through resolve() / resolve_storage_path(), which resolve '..' and symlinks
and refuse any path leaving its section: os.path.commonpath() is purely lexical and let
'storage/scans/../../..' through.

Downloads are streamed: several files or folders are sent as a zip built on the fly (stored,
no compression, the SER files don't compress), so nothing is ever written on the SD card
whatever the size of the selection. A download is still capped at MAX_DOWNLOAD_BYTES.

The disk work (zip, thumbnails, deletion) runs in a small pool of low priority threads:
the backend threads inherit a raised CPU / I/O priority (system_tuning), and a gallery
download must never compete with the capture or the SER writer during a scan.
"""

import asyncio
import hashlib
import logging
import os
import shutil
import subprocess
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Iterable, Iterator, List, Optional, Tuple
from urllib.parse import quote

import numpy as np
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from PIL import Image

STORAGE_ROOT = os.path.realpath('storage')

SECTIONS = {
    'scans': os.path.join(STORAGE_ROOT, 'scans'),
    'stacking': os.path.join(STORAGE_ROOT, 'stacking'),
    'animations': os.path.join(STORAGE_ROOT, 'animations'),
    'snapshots': os.path.join(STORAGE_ROOT, 'snapshots'),
}

# Depths (1 = directly in the section) at which an entry can be deleted from the gallery.
# In a scan, files are never deleted one by one: the mobile app expects a scan to be complete.
DELETABLE_DEPTHS = {'scans': (1, 2), 'stacking': (1,), 'animations': (1,), 'snapshots': (1,)}

MAX_DOWNLOAD_BYTES = int(float(os.environ.get('SUNSCAN_MAX_DOWNLOAD_GB', '10')) * 1024**3)

THUMBS_DIR = os.path.join(STORAGE_ROOT, 'tmp', 'thumbs')
# 1280: preview of a FITS in the viewer, which can't display the file itself
THUMB_WIDTHS = (160, 320, 640, 1280)
# below this free space the thumbnails are still served but no longer cached
THUMB_CACHE_MIN_FREE = 512 * 1024**2

IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.gif', '.bmp')
FITS_EXTS = ('.fits', '.fit', '.fts')
# files with a JPEG thumbnail
THUMB_EXTS = IMAGE_EXTS + FITS_EXTS

# Image shown on the card of a folder, by order of preference
PREVIEW_CANDIDATES = (
    'sunscan_clahe.jpg', 'sunscan_color.jpg', 'sunscan_preview.jpg', 'sunscan_cont.jpg',
    'stacked_clahe_preview.jpg', 'animated_preview.gif',
)

ZIP_CHUNK = 4 * 1024 * 1024

GALLERY_NICE = 10


# -- Low priority worker threads --

def _lower_thread_priority():
    """Nice and I/O priority are per thread on Linux: only the pool threads are affected."""
    tid = threading.get_native_id()
    try:
        os.setpriority(os.PRIO_PROCESS, tid, GALLERY_NICE)
    except (OSError, AttributeError):
        pass
    if shutil.which('ionice'):
        # lowering its own priority never needs root
        subprocess.run(['ionice', '-c', '2', '-n', '7', '-p', str(tid)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix='gallery', initializer=_lower_thread_priority)


def run_in_background(fn, *args):
    """Fire and forget in the low priority pool, errors are logged."""
    def log_error(future):
        if future.exception():
            logging.warning(f'gallery: {fn.__name__} failed: {future.exception()}')
    _POOL.submit(fn, *args).add_done_callback(log_error)


async def run_low(fn, *args):
    return await asyncio.get_running_loop().run_in_executor(_POOL, fn, *args)


async def _iterate_low(gen: Iterator[bytes]):
    """Consume a blocking generator from the low priority pool, without blocking the event loop."""
    done = object()
    try:
        while True:
            chunk = await run_low(next, gen, done)
            if chunk is done:
                break
            if chunk:
                yield chunk
    finally:
        # also reached when the client goes away: closes the files being read
        await run_low(gen.close)


# -- Paths --

def section_root(section: str) -> str:
    root = SECTIONS.get(section)
    if root is None:
        raise HTTPException(status_code=404, detail=f"Unknown section '{section}'")
    return root


def _inside(path: str, root: str) -> bool:
    return path == root or path.startswith(root + os.sep)


def resolve(section: str, relpath: str = '') -> str:
    """Absolute path of relpath inside the section, 400 if it leaves it."""
    root = section_root(section)
    full = os.path.realpath(os.path.join(root, relpath or ''))
    if not _inside(full, root):
        raise HTTPException(status_code=400, detail="Invalid path")
    return full


def resolve_existing(section: str, relpath: str) -> str:
    full = resolve(section, relpath)
    if not os.path.exists(full):
        raise HTTPException(status_code=404, detail=f"Not found: {relpath}")
    return full


def resolve_storage_path(path: str, allow_section_root: bool = False) -> str:
    """
    For the routes of the mobile app, which send paths relative to the backend directory
    ('storage/scans/2025_01_02/sunscan_...'): must stay inside storage/, and by default
    can't be storage/ or a section root itself.
    """
    full = os.path.realpath(path)
    if not _inside(full, STORAGE_ROOT) or full == STORAGE_ROOT:
        raise HTTPException(status_code=400, detail="Invalid path")
    if not allow_section_root and full in SECTIONS.values():
        raise HTTPException(status_code=400, detail="Invalid path")
    return full


def _relpath(full: str, section: str) -> str:
    rel = os.path.relpath(full, SECTIONS[section])
    return '' if rel == '.' else rel


def _depth(full: str, section: str) -> int:
    rel = _relpath(full, section)
    return len(rel.split(os.sep)) if rel else 0


# -- Listing --

def _visible(name: str) -> bool:
    return not name.startswith('.') and not name.startswith('tag_') and not name.endswith('.zip')


def _has_content(path: str) -> bool:
    """True when the folder holds at least one real file, at any depth (tags, hidden files and zips don't count)."""
    for _, _, files in os.walk(path):
        if any(_visible(f) for f in files):
            return True
    return False


def _visible_count(path: str) -> int:
    try:
        entries = list(os.scandir(path))
    except OSError:
        return 0
    return sum(1 for e in entries if _visible(e.name) and (not e.is_dir() or _has_content(e.path)))


def _folder_preview(path: str, depth: int = 0) -> Optional[str]:
    """Absolute path of the image representing a folder, looking into the newest sub-folders."""
    try:
        entries = sorted(os.scandir(path), key=lambda e: e.name, reverse=True)
    except OSError:
        return None
    names = {e.name for e in entries}
    for candidate in PREVIEW_CANDIDATES:
        if candidate in names:
            return os.path.join(path, candidate)
    for e in entries:
        if e.is_file() and e.name.lower().endswith(('.jpg', '.jpeg', '.gif')):
            return e.path
    if depth < 2:
        for e in entries:
            if e.is_dir() and _visible(e.name):
                found = _folder_preview(e.path, depth + 1)
                if found:
                    return found
    return None


def _folder_tag(path: str) -> str:
    try:
        tags = [n for n in os.listdir(path) if n.startswith('tag_')]
    except OSError:
        return ''
    return tags[0][len('tag_'):] if tags else ''


def _thumb_url(section: str, full: str) -> str:
    return f"/gallery/thumb/{section}/{quote(_relpath(full, section))}?v={int(os.path.getmtime(full))}"


def _shown(e: os.DirEntry) -> bool:
    return _visible(e.name) and (not e.is_dir() or _has_content(e.path))


def _entry(section: str, e: os.DirEntry) -> dict:
    st = e.stat()
    item = {
        'name': e.name,
        'path': _relpath(e.path, section),
        'mtime': int(st.st_mtime),
        'deletable': _depth(e.path, section) in DELETABLE_DEPTHS[section],
    }
    if e.is_dir():
        preview = _folder_preview(e.path)
        item.update(kind='dir', count=_visible_count(e.path), tag=_folder_tag(e.path),
                    thumb=_thumb_url(section, preview) if preview else None)
    else:
        ext = os.path.splitext(e.name)[1].lower()
        item.update(kind='file', size=st.st_size, ext=ext.lstrip('.'),
                    thumb=_thumb_url(section, e.path) if ext in THUMB_EXTS else None)
    return item


def list_all_scans() -> dict:
    """Every scan folder of every date, so the gallery opens a scan in one click."""
    root = SECTIONS['scans']
    entries = []
    for date in os.scandir(root):
        if date.is_dir() and _shown(date):
            entries += [_entry('scans', e) for e in os.scandir(date.path) if e.is_dir() and _shown(e)]
    return {'section': 'scans', 'path': '', 'tag': '', 'flat': True, 'entries': entries}


def list_folder(section: str, relpath: str) -> dict:
    full = resolve_existing(section, relpath)
    if not os.path.isdir(full):
        raise HTTPException(status_code=400, detail="Not a folder")

    entries = [_entry(section, e) for e in os.scandir(full) if _shown(e)]
    return {
        'section': section,
        'path': _relpath(full, section),
        'tag': _folder_tag(full) if full != SECTIONS[section] else '',
        'entries': entries,
    }


# -- Sizes and zip streaming --

def _ext(name: str) -> str:
    return os.path.splitext(name)[1].lower().lstrip('.')


def _walk_files(full: str, exts: Optional[Iterable[str]] = None) -> Iterator[str]:
    """Files of a selected item, restricted to the extensions exts (without dot) when given."""
    if os.path.isfile(full):
        if not exts or _ext(full) in exts:
            yield full
        return
    for root, dirs, files in os.walk(full):
        dirs.sort()
        for f in sorted(files):
            if not f.endswith('.zip') and (not exts or _ext(f) in exts):
                yield os.path.join(root, f)


def selection_size(paths: Iterable[str], exts: Optional[Iterable[str]] = None) -> Tuple[int, int, dict]:
    """Total size, file count, and size per extension ({'ser': {'bytes', 'files'}, ...})."""
    total, count, by_ext = 0, 0, {}
    for p in paths:
        for f in _walk_files(p, exts):
            try:
                size = os.path.getsize(f)
            except OSError:
                continue
            total += size
            count += 1
            stat = by_ext.setdefault(_ext(f), {'bytes': 0, 'files': 0})
            stat['bytes'] += size
            stat['files'] += 1
    return total, count, by_ext


def zip_entries(paths: Iterable[str], base: Optional[str] = None,
                exts: Optional[Iterable[str]] = None) -> List[Tuple[str, str]]:
    """
    (file, name in the archive) for every file of the selection. By default the names are
    relative to the parent of each selected item, so a selected folder keeps its name.
    """
    entries = []
    for p in paths:
        rel_to = base or os.path.dirname(p)
        for f in _walk_files(p, exts):
            entries.append((f, os.path.relpath(f, rel_to)))
    return entries


class _Sink:
    """Write-only, non seekable file object: zipfile then writes data descriptors after each file."""

    def __init__(self):
        self._chunks = []

    def write(self, data):
        self._chunks.append(bytes(data))
        return len(data)

    def flush(self):
        pass

    def take(self) -> bytes:
        data = b''.join(self._chunks)
        self._chunks.clear()
        return data


def zip_stream(entries: List[Tuple[str, str]]) -> Iterator[bytes]:
    """Zip archive (stored, zip64 when needed) produced chunk by chunk, never held in memory nor on disk."""
    sink = _Sink()
    with zipfile.ZipFile(sink, 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as zf:
        for path, arcname in entries:
            zinfo = zipfile.ZipInfo.from_file(path, arcname, strict_timestamps=False)
            zinfo.compress_type = zipfile.ZIP_STORED
            with open(path, 'rb') as src, zf.open(zinfo, 'w') as dst:
                while True:
                    chunk = src.read(ZIP_CHUNK)
                    if not chunk:
                        break
                    dst.write(chunk)
                    yield sink.take()
            yield sink.take()
    # central directory
    yield sink.take()


def _check_download_size(paths: List[str], exts: Optional[List[str]] = None):
    total, count, _ = selection_size(paths, exts)
    if count == 0:
        raise HTTPException(status_code=404, detail="Nothing to download")
    if total > MAX_DOWNLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Selection too large: {total / 1024**3:.1f} GB, limit {MAX_DOWNLOAD_BYTES / 1024**3:.0f} GB. "
                   f"Select fewer items.")


def _download_name(section: str, full: str) -> str:
    name = os.path.basename(full)
    parent = os.path.basename(os.path.dirname(full))
    # every scan holds a sunscan_clahe.png: prefix files with their scan
    if section == 'scans' and os.path.isfile(full) and parent.startswith('sunscan_'):
        return parent.replace('sunscan_', '') + '-' + name
    return name


def _attachment(filename: str) -> dict:
    return {'Content-Disposition': f"attachment; filename*=UTF-8''{quote(filename)}"}


async def download_response(paths: List[str], zip_name: str, section: Optional[str] = None,
                            base: Optional[str] = None, exts: Optional[List[str]] = None):
    """
    A single file is sent as is, anything else as a streamed zip.
    exts keeps only these file types (e.g. only the SER of a scan).
    """
    await run_low(_check_download_size, paths, exts)
    entries = await run_low(zip_entries, paths, base, exts)
    if len(entries) == 1:
        path = entries[0][0]
        name = _download_name(section, path) if section else os.path.basename(path)
        return FileResponse(path, filename=name)
    if exts:
        zip_name = f"{zip_name[:-4]}_{'-'.join(sorted(exts))}.zip"
    return StreamingResponse(_iterate_low(zip_stream(entries)), media_type='application/zip',
                             headers=_attachment(zip_name))


def _default_zip_name(section: str, fulls: List[str]) -> str:
    if len(fulls) == 1:
        return os.path.basename(fulls[0]) + '.zip'
    parents = {os.path.dirname(f) for f in fulls}
    if len(parents) == 1 and parents != {SECTIONS[section]}:
        return os.path.basename(parents.pop()) + '_selection.zip'
    return f"sunscan_{section}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"


# -- Deletion --

def delete_paths(fulls: List[str]):
    """All the paths must have been checked before: nothing is deleted if one of them is invalid."""
    for full in fulls:
        if os.path.isdir(full):
            shutil.rmtree(full)
        else:
            os.remove(full)
    for parent in {os.path.dirname(f) for f in fulls}:
        _prune_emptied_parents(parent)


def _prune_emptied_parents(path: str):
    """
    Remove the folders a deletion has left empty (a date without scan anymore), up to the section.
    Today's date folder (UTC, as named by the camera) is kept: a scan can be starting in it.
    """
    today = datetime.utcnow().strftime('%Y_%m_%d')
    while path not in SECTIONS.values() and _inside(path, STORAGE_ROOT) and os.path.basename(path) != today:
        if _has_content(path):
            return
        shutil.rmtree(path, ignore_errors=True)
        path = os.path.dirname(path)


# Removed only when untouched for that long: a folder just created by a recording
# or a processing is empty for a moment before being filled
EMPTY_FOLDER_MIN_AGE = 3600


def _newest_mtime(path: str) -> float:
    newest = os.path.getmtime(path)
    for root, dirs, files in os.walk(path):
        for name in dirs + files:
            try:
                newest = max(newest, os.path.getmtime(os.path.join(root, name)))
            except OSError:
                pass
    return newest


def remove_empty_folders(min_age: float = EMPTY_FOLDER_MIN_AGE) -> List[str]:
    """
    Delete the folders of the gallery that hold no real file (dates without scan, empty BASS2000/,
    Clahe/... sub-folders, aborted scans) and haven't changed for min_age seconds.
    Called at startup, before any processing can run: the processing only creates its
    sub-folders when they are missing.
    """
    now = time.time()
    removed = []
    for root_dir in SECTIONS.values():
        if not os.path.isdir(root_dir):
            continue
        for root, dirs, _ in os.walk(root_dir):
            for d in list(dirs):
                path = os.path.join(root, d)
                if _has_content(path):
                    continue
                dirs.remove(d)  # removed or kept, nothing to look at inside
                if now - _newest_mtime(path) >= min_age:
                    shutil.rmtree(path, ignore_errors=True)
                    removed.append(path)
    if removed:
        logging.info(f'gallery: {len(removed)} empty folders removed')
    return removed


# -- Thumbnails --

def _render_fits(src: str, width: int) -> Image.Image:
    """
    Grayscale preview of the first image of a FITS, stretched between its 0.5 and 99.9
    percentiles. Row 0 is shown at the top, as in the JPEG written by the processing.
    """
    from astropy.io import fits  # slow import, only paid by the first FITS thumbnail

    # memmap=False: the SUNSCAN FITS have BZERO, which astropy can't memory map
    with fits.open(src, memmap=False) as hdul:
        data = next((h.data for h in hdul if h.data is not None and h.data.ndim >= 2), None)
    if data is None:
        raise ValueError('no image in this FITS')
    while data.ndim > 2:
        data = data[0]
    # decimate to about twice the target size first: the stretch then works on few pixels
    step = max(1, max(data.shape) // (2 * width))
    a = np.asarray(data[::step, ::step], dtype=np.float32)
    lo, hi = np.nanpercentile(a, (0.5, 99.9))
    a = np.nan_to_num((a - lo) * (255.0 / max(hi - lo, 1e-6)))
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    im.thumbnail((width, width), Image.LANCZOS)
    return im


def _render_thumb(src: str, width: int) -> Image.Image:
    if src.lower().endswith(FITS_EXTS):
        return _render_fits(src, width)
    # the processing writes a .jpg next to most .png: much faster to decode
    base, ext = os.path.splitext(src)
    if ext.lower() == '.png' and os.path.exists(base + '.jpg'):
        src = base + '.jpg'
    im = Image.open(src)
    if im.format == 'JPEG':
        # DCT scaling: decodes directly at a reduced size
        im.draft(im.mode, (width, width))
    if im.mode in ('I', 'I;16', 'I;16B', 'I;16L', 'F'):
        a = np.asarray(im, dtype=np.float32)
        top = float(a.max()) or 1.0
        im = Image.fromarray(np.clip(a * (255.0 / top), 0, 255).astype(np.uint8))
    elif im.mode not in ('L', 'RGB'):
        im = im.convert('RGB')
    im.thumbnail((width, width))
    return im


def thumbnail(src: str, width: int):
    """Path of the cached JPEG thumbnail, or its bytes when the disk is almost full."""
    st = os.stat(src)
    key = hashlib.sha1(f"{src}|{st.st_mtime_ns}|{st.st_size}|{width}".encode()).hexdigest()
    cached = os.path.join(THUMBS_DIR, key + '.jpg')
    if os.path.exists(cached):
        return cached

    im = _render_thumb(src, width)
    if shutil.disk_usage(STORAGE_ROOT).free < THUMB_CACHE_MIN_FREE:
        from io import BytesIO
        buf = BytesIO()
        im.save(buf, 'JPEG', quality=80)
        return buf.getvalue()

    os.makedirs(THUMBS_DIR, exist_ok=True)
    tmp = f"{cached}.{threading.get_native_id()}.tmp"
    im.save(tmp, 'JPEG', quality=80)
    os.replace(tmp, cached)
    return cached


# -- Routes --

router = APIRouter(prefix='/gallery', tags=['gallery'])

CACHE_FOREVER = {'Cache-Control': 'public, max-age=31536000, immutable'}


@router.get('/list/{section}')
async def gallery_list_root(section: str, flat: bool = False):
    """flat (scans only): every scan of every date instead of the date folders."""
    if flat and section == 'scans':
        return await run_low(list_all_scans)
    return await run_low(list_folder, section, '')


@router.get('/list/{section}/{path:path}')
async def gallery_list(section: str, path: str):
    """Content of a folder: sub-folders (with count, tag and preview) and files (with size)."""
    return await run_low(list_folder, section, path)


@router.get('/file/{section}/{path:path}')
async def gallery_file(section: str, path: str):
    full = resolve_existing(section, path)
    if not os.path.isfile(full):
        raise HTTPException(status_code=400, detail="Not a file")
    return FileResponse(full)


@router.get('/thumb/{section}/{path:path}')
async def gallery_thumb(section: str, path: str, w: int = 320):
    full = resolve_existing(section, path)
    if not os.path.isfile(full) or not full.lower().endswith(THUMB_EXTS):
        raise HTTPException(status_code=400, detail="No thumbnail for this file")
    if full.lower().endswith('.gif'):
        # the animated previews are small, served as is so they keep moving
        return FileResponse(full, headers=CACHE_FOREVER)
    width = min(THUMB_WIDTHS, key=lambda x: abs(x - w))
    try:
        result = await run_low(thumbnail, full, width)
    except Exception as e:
        logging.warning(f'gallery: thumbnail of {full} failed: {e}')
        if full.lower().endswith(FITS_EXTS):
            # the web app then shows the file icon
            raise HTTPException(status_code=415, detail="Can't preview this FITS")
        return FileResponse(full)
    if isinstance(result, bytes):
        return Response(result, media_type='image/jpeg')
    return FileResponse(result, media_type='image/jpeg', headers=CACHE_FOREVER)


@router.get('/size/{section}')
async def gallery_size(section: str, paths: List[str] = Query(...), exts: Optional[List[str]] = Query(None)):
    """Size of a selection (total and per file type), shown before downloading it."""
    fulls = [resolve_existing(section, p) for p in paths]
    total, count, by_ext = await run_low(selection_size, fulls, _norm_exts(exts))
    return {'bytes': total, 'files': count, 'by_ext': by_ext, 'max_bytes': MAX_DOWNLOAD_BYTES}


@router.get('/download/{section}')
async def gallery_download(section: str, paths: List[str] = Query(...), exts: Optional[List[str]] = Query(None)):
    fulls = [resolve_existing(section, p) for p in paths]
    return await download_response(fulls, _default_zip_name(section, fulls), section=section, exts=_norm_exts(exts))


def _norm_exts(exts: Optional[List[str]]) -> Optional[List[str]]:
    return sorted({e.lower().lstrip('.') for e in exts if e}) or None if exts else None


@router.delete('/{section}')
async def gallery_delete(section: str, paths: List[str] = Query(...)):
    fulls = [resolve_existing(section, p) for p in paths]
    for p, full in zip(paths, fulls):
        if _depth(full, section) not in DELETABLE_DEPTHS[section]:
            raise HTTPException(status_code=403, detail=f"'{p}' can't be deleted from the gallery")
    await run_low(delete_paths, fulls)
    return JSONResponse({'deleted': len(fulls)})
