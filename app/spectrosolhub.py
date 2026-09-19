"""
SpectroSolHub : sends the images of a processed scan to https://spectrosolhub.com, the sharing
platform of the spectroheliograph community.

Adapted from the SpectroSolHub client of INTI Partner (Cédric Champeau / Valérie Desnoux,
https://github.com/Vdesnoux/inti_partner), itself ported from JSol'Ex :

  1. POST /api/auth/token          login + password (+ TOTP code) -> API token, only the token is kept
  2. GET  /api/users/me/quota      checks the token and the room left on the account
  3. POST /api/sessions            one observation session per scan (line, date, instrument)
  4. POST /api/uploads/initiate    per image, then PUT /api/uploads/<id>/parts/<n> for each chunk
     POST /api/uploads/<id>/complete
  5. POST /api/sessions/<id>/publish   optional, the session stays a draft otherwise

The same goes for the stacks (JPEG) and the animations (GIF) made from the scans. Both reference
clients only ever send JPEG : whether the hub takes a GIF is not known, see the documentation.

INTI Partner is a desktop wizard, here the mobile app drives the same steps through the
/spectrosolhub/* routes of main.py and the upload runs in a background thread. Its progress is
published on the 'spectrosolhub_upload_<key>' WebSocket channel, see docs/envoi-spectrosolhub.md.

Only the standard library is used for HTTP : the devices in the field are updated with a zip
of the sources, no new Python package can be expected there.

The SunScan needs an internet access : it must be connected to a WiFi network (client mode of
network.py), nothing can be sent from its own hotspot.
"""

import calendar
import json
import logging
import math
import os
import re
import socket
import time
import urllib.error
import urllib.request
from threading import Lock, Thread

from config import LineDict
from scan_progress import ScanProgress, scan_key
from storage import images_type, read_sources, SPECTROSOLHUB_FILE

DEFAULT_BASE_URL = 'https://spectrosolhub.com'
# Other server, for the tests only
BASE_URL = os.environ.get('SUNSCAN_SPECTROSOLHUB_URL', DEFAULT_BASE_URL).rstrip('/')
USER_AGENT = 'SunScan'
# Socket timeout of each request, in seconds. It is not the duration of a request : a chunk
# going up slowly never times out as long as bytes keep moving
TIMEOUT = 30
# First contact with the hub (login, account check) : fails faster when the SunScan has no internet access
FIRST_TIMEOUT = 10
# A chunk that could not be sent is sent again, the WiFi of a SunScan in the field is not always steady
PART_RETRIES = 3
RETRY_DELAY = 3

CONFIG_FILE = os.path.expanduser('~/.config/sunscan/spectrosolhub.json')
# What can be sent : a scan (its SER file or its directory), a stack or an animation (their directory)
ROOTS = {'scan': os.path.realpath(os.path.join('storage', 'scans')),
         'stack': os.path.realpath(os.path.join('storage', 'stacking')),
         'animation': os.path.realpath(os.path.join('storage', 'animations'))}

# Instrument sent with the sessions and the images : entry 'Sunscan' of the spectroheliographs
# and SUNSCAN_INSTRU of INTI Partner (3.1 µm is the 2x2 Bayer cell of the IMX477 read as one pixel)
SPECTROHELIOGRAPH = {
    'name': 'Sunscan',
    'gratingDensity': 2400, 'gratingOrder': 1,
    'slitWidthMicrons': 10.0, 'slitHeightMillimeters': 6.0,
    'cameraFocalLength': 100.0, 'collimatorFocalLength': 75.0,
    'totalAngleDegrees': 34.0,
}
TELESCOPE = {'brand': 'Sunscan', 'model': 'lens', 'focalLengthMm': 200, 'apertureMm': 25}
CAMERA = {'brand': 'SONY', 'model': 'IMX477', 'pixelSizeUm': 3.1, 'binning': 1}
MOUNT = {'brand': 'Sunscan', 'model': 'azim', 'type': 'ALT-AZ'}
ENERGY_REJECTION_FILTER = 'ND0.9'

# SunScan line tag (config.LineDict) -> (SpectroSolHub label, wavelength in Å). The labels of the
# lines known by JSol'Ex are its SpectralRay labels, as in INTI Partner. The other lines are sent
# as custom lines : free label + wavelength.
HUB_LINES = {
    'halpha':   ('H-alpha', 6562.81),
    'hbeta':    ('H-beta', 4861.34),
    'hgamma':   ('H-gamma', 4340.48),
    'hdelta':   ('H-delta', 4101.75),
    'hepsilon': ('H-epsilon', 3970.08),
    'sodium':   ('Sodium (D1)', 5895.92),
    'feI':      ('Fe I', 6173.0),
    'feX':      ('Fe X', 6374.56),
    'feXIV':    ('Fe XIV (Cor)', 5302.86),
    'mgI1':     ('Mg I', 5167.0),
    'mgI2':     ('Mg I', 5172.0),
    'mgI3':     ('Magnesium (b1)', 5183.62),
    'heI':      ('Helium (D3)', 5875.62),
    'caIIK':    ('Calcium (K)', 3933.66),
    'caIIH':    ('Calcium (H)', 3968.47),
}
DEFAULT_LINE = 'halpha'

# Images that can be sent, in sending order :
# key of storage.images_type -> (image kind on the hub, title on the hub, line, sent by default).
# The line is 'scan' (line of the scan), None (continuum, no line) or a line tag when the image
# is always the same line. The kind is 'SUNSCAN_' + the sub kinds of INTI Partner where they exist.
HUB_IMAGES = {
    'clahe':           ('CLAHE', 'Disk', 'scan', True),
    'protus':          ('PROTUS', 'Prominences', 'scan', True),
    'color':           ('COLOR', 'Disk, artificial color', 'scan', True),
    'negative':        ('INV', 'Disk, negative', 'scan', True),
    'cont':            ('CONTINUUM', 'Continuum', None, True),
    'doppler':         ('DOPPLER', 'Doppler', 'scan', True),
    'protus_doppler':  ('PROTUS_DOPPLER', 'Prominences, Doppler', 'scan', False),
    'clahe_colour':    ('CLAHE_COLOR', 'Disk, artificial color', 'scan', False),
    'helium':          ('HELIUM', 'Helium', 'heI', True),
    'helium_cont':     ('HELIUM_CONTINUUM', 'Helium + continuum', 'heI', True),
    'hepsilon':        ('HEPSILON', 'H-epsilon disk', 'hepsilon', True),
    'hepsilon_color':  ('HEPSILON_COLOR', 'H-epsilon disk, artificial color', 'hepsilon', False),
    'hepsilon_protus': ('HEPSILON_PROTUS', 'H-epsilon prominences', 'hepsilon', True),
    'raw':             ('RAW', 'Raw disk', 'scan', False),
}
IMAGE_KIND_PREFIX = 'SUNSCAN_'

# Files of the stacks : stacked_<image>[_<number of scans>]_<raw|sharpen>.jpg, and of the animations :
# animated_<image>[_<raw|sharpen>].gif (main.py names the GIF of an animation of stacks 'stacked_...' but
# create_gif renames it, 'stacked' is only accepted in case that changes).
# The previews and anything else found in these directories are not sent.
_DERIVED_IMAGE = r'(helium_cont|helium|clahe|cont|negative|color|protus)'
_STACK_FILE = re.compile(r'stacked_' + _DERIVED_IMAGE + r'(?:_(\d+))?_(raw|sharpen)\.jpg')
_ANIMATION_FILE = re.compile(r'(?:animated|stacked)_' + _DERIVED_IMAGE + r'(?:_(raw|sharpen))?\.gif')
# image -> (image kind on the hub, title on the hub, line), as in HUB_IMAGES. The kind sent is
# SUNSCAN_STACK_<kind>[_<variant>] or SUNSCAN_ANIMATION_<kind>[_<variant>]
DERIVED_IMAGES = {
    'clahe':       ('CLAHE', 'Disk', 'scan'),
    'protus':      ('PROTUS', 'Prominences', 'scan'),
    'color':       ('COLOR', 'Disk, artificial color', 'scan'),
    'negative':    ('INV', 'Disk, negative', 'scan'),
    'cont':        ('CONTINUUM', 'Continuum', None),
    'helium':      ('HELIUM', 'Helium', 'heI'),
    'helium_cont': ('HELIUM_CONTINUUM', 'Helium + continuum', 'heI'),
}
# One file per image is sent by default : the sharpened one when it exists
_VARIANTS = ('sharpen', '', 'raw')

# Progress of the uploads, read by the WebSocket of main.py. Same message as the processing of a
# scan, followed by : index of the image being sent (from 1), number of images, url of the session
# on the hub once created, '1' when the session is published
progress = ScanProgress(channel='spectrosolhub_upload_',
                        extra={'image': 0, 'images': 0, 'url': '', 'published': 0})

_config_lock = Lock()
_config = None
_upload_lock = Lock()
_current = None  # upload being sent : {key, filename}


class HubError(Exception):
    """Error for the frontend : key to translate, raw message for the logs, HTTP status of our API."""

    def __init__(self, code, message, http_status=400):
        super().__init__(message)
        self.code = code
        self.http_status = http_status


# -- Account, kept in the home directory : storage/ is served by the API --

def _load_config():
    global _config
    if _config is None:
        _config = {'token': None, 'username': '', 'logged_at': None}
        try:
            with open(CONFIG_FILE) as f:
                _config.update(json.load(f))
        except (OSError, ValueError):
            pass
    return _config


def _save_config():
    try:
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        # The token gives access to the account : readable by the backend user only
        fd = os.open(CONFIG_FILE + '.tmp', os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump(_config, f)
        os.replace(CONFIG_FILE + '.tmp', CONFIG_FILE)
    except OSError as e:
        logging.warning(f'spectrosolhub : can not save the account : {e}')


def _set_account(token, username=''):
    with _config_lock:
        _load_config().update({'token': token, 'username': username,
                               'logged_at': int(time.time()) if token else None})
        _save_config()


def _token():
    with _config_lock:
        return _load_config()['token']


# -- HTTP --

def _hub_message(raw):
    """Message of an error answer of the hub : {"message": ..., "_embedded": {"errors": [{"message": ...}]}}"""
    text = raw.decode('utf-8', errors='replace').strip()
    try:
        body = json.loads(text)
        errors = (body.get('_embedded') or {}).get('errors') or []
        messages = [e.get('message') for e in errors if e.get('message')]
        return ' / '.join(messages) or body.get('message') or text
    except (ValueError, AttributeError):
        return text


def _request(method, path, token=None, payload=None, data=None, expected=200, timeout=TIMEOUT):
    """
    One request to the hub. Returns the decoded JSON answer, None when there is none.
    Raises HubError : hub_unreachable, token_expired, hub_rejected (4xx) or hub_error (5xx).
    """
    headers = {'User-Agent': USER_AGENT, 'Accept': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if data is not None:
        body = data
        headers['Content-Type'] = 'application/octet-stream'
    else:
        body = json.dumps(payload).encode() if payload is not None else (b'' if method == 'POST' else None)
        if method == 'POST':
            headers['Content-Type'] = 'application/json'
    request = urllib.request.Request(BASE_URL + path, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read()
    except (urllib.error.URLError, socket.timeout, OSError) as e:
        # No internet access (hotspot mode), DNS, TLS or connection lost
        reason = getattr(e, 'reason', e)
        raise HubError('hub_unreachable', f'{method} {path} : {reason}', 503)

    if status == expected:
        try:
            return json.loads(raw) if raw.strip() else None
        except ValueError:
            return None
    message = f'{method} {path} : HTTP {status} {_hub_message(raw)}'
    if status == 401 and token:
        raise HubError('token_expired', message, 401)
    error = HubError('hub_error' if status >= 500 else 'hub_rejected', message, 502)
    error.hub_status = status
    raise error


def _request_again(*args, **kwargs):
    """_request for the calls that can be repeated, tried again when the hub does not answer."""
    for attempt in range(PART_RETRIES):
        try:
            return _request(*args, **kwargs)
        except HubError as e:
            if e.code not in ('hub_unreachable', 'hub_error') or attempt == PART_RETRIES - 1:
                raise
            logging.warning(f'spectrosolhub : {e}, new attempt in {RETRY_DELAY} s')
            time.sleep(RETRY_DELAY)


def _forget_token_if_expired(error):
    if error.code == 'token_expired':
        with _config_lock:
            _load_config()['token'] = None
            _save_config()


# -- Account routes --

def login(username, password, totp_code=None):
    """
    Get an API token from the hub with the credentials of the user and keep it. The password
    is never stored. Raises HubError : missing_credentials, invalid_credentials, totp_required,
    invalid_totp, hub_unreachable, hub_rejected, hub_error.
    """
    username = (username or '').strip()
    totp_code = (totp_code or '').strip()
    if not username or not password:
        raise HubError('missing_credentials', 'Username and password are required', 400)
    body = {'username': username, 'password': password, 'tokenName': f'SunScan {socket.gethostname()}'}
    if totp_code:
        body['totpCode'] = totp_code
    try:
        answer = _request('POST', '/api/auth/token', payload=body, expected=201, timeout=FIRST_TIMEOUT)
    except HubError as e:
        hub_status = getattr(e, 'hub_status', None)
        if hub_status == 401:
            raise HubError('invalid_credentials', str(e), 401)
        if hub_status == 403:
            # Account protected by two-factor authentication
            if totp_code:
                raise HubError('invalid_totp', str(e), 403)
            raise HubError('totp_required', str(e), 403)
        raise
    token = (answer or {}).get('token')
    if not token:
        raise HubError('hub_error', 'No token in the answer of the hub', 502)
    _set_account(token, username)
    logging.info(f'spectrosolhub : logged in as {username}')
    return status()


def logout():
    """Forget the token. It stays listed in the account on the hub, where it can be revoked."""
    _set_account(None)
    return status()


def _quota(token):
    quota = _request('GET', '/api/users/me/quota', token=token, timeout=FIRST_TIMEOUT) or {}
    return {'storage_bytes': quota.get('quotaStorageBytes', 0),
            'used_storage_bytes': quota.get('usedStorageBytes', 0),
            'image_count': quota.get('quotaImageCount', 0),
            'used_image_count': quota.get('usedImageCount', 0)}


def status(verify=False):
    """
    Account known by the SunScan. With verify, the token is checked on the hub : 'verified' is
    True, or False with the reason in 'error' (hub_unreachable : no internet access, the account is
    kept ; token_expired : the account is forgotten, log in again).
    """
    with _config_lock:
        config = dict(_load_config())
    current = _current
    out = {'connected': bool(config['token']), 'username': config['username'] if config['token'] else '',
           'site': BASE_URL, 'verified': None, 'error': '', 'detail': '', 'quota': None,
           'upload': dict(current) if current else None}
    if verify and config['token']:
        try:
            out['quota'] = _quota(config['token'])
            out['verified'] = True
        except HubError as e:
            _forget_token_if_expired(e)
            out.update({'verified': False, 'error': e.code, 'detail': str(e)})
            if e.code == 'token_expired':
                out.update({'connected': False, 'username': ''})
    return out


# -- Scan, stack or animation --

def _item(filename):
    """
    ('scan' | 'stack' | 'animation', directory) from the path sent by the frontend : the SER file
    of a scan as everywhere in the API, or the directory of a stack or of an animation.
    """
    full = os.path.realpath(filename or '')
    directory = full if os.path.isdir(full) else os.path.dirname(full)
    for item, root in ROOTS.items():
        if directory.startswith(root + os.sep):
            if not os.path.isdir(directory):
                raise HubError('file_not_found', f'Not found : {filename}', 404)
            return item, directory
    raise HubError('invalid_path', f'Not a scan, a stack or an animation : {filename}', 400)


def _image(path, kind, label, default, hub_kind, title, line):
    """The fields starting with '_' are for the upload, the others go to the frontend."""
    return {'kind': kind, 'label': label, 'path': os.path.relpath(path), 'size': os.path.getsize(path),
            'default': default, '_path': path, '_hub_kind': IMAGE_KIND_PREFIX + hub_kind, '_title': title, '_line': line,
            '_content_type': 'image/gif' if path.endswith('.gif') else 'image/jpeg'}


def _scan_images(directory):
    images = []
    for kind, (hub_kind, title, line, default) in HUB_IMAGES.items():
        path = os.path.join(directory, f'sunscan_{kind}.jpg')
        if os.path.isfile(path):
            images.append(_image(path, kind, images_type.get(kind, kind), default, hub_kind, title, line))
    return images


def _derived_images(item, directory):
    """Images of a stack or of an animation, and the number of scans written in the names of the files of a stack."""
    found, count = {}, 0
    for name in sorted(os.listdir(directory)):
        match = (_STACK_FILE if item == 'stack' else _ANIMATION_FILE).fullmatch(name)
        if not match:
            continue
        image, variant = match.group(1), match.groups()[-1] or ''
        if item == 'stack' and match.group(2):
            count = int(match.group(2))
        found[(image, variant)] = os.path.join(directory, name)
    images = []
    for image, (hub_kind, title, line) in DERIVED_IMAGES.items():
        variants = [v for v in _VARIANTS if (image, v) in found]
        for variant in variants:
            suffix = f', stack of {count} scans' if item == 'stack' and count else f', {item}'
            images.append(_image(found[(image, variant)], image + ('_' + variant if variant else ''),
                                 title + (f' ({variant})' if variant else ''), variant == variants[0],
                                 f'{item.upper()}_{hub_kind}' + ('_' + variant.upper() if variant else ''),
                                 title + suffix + (', no sharpening' if variant == 'raw' else ''), line))
    return images, count


def _images(item, directory):
    """Images that can be sent, in sending order."""
    return _scan_images(directory) if item == 'scan' else _derived_images(item, directory)[0]


def _fits_header(directory):
    """Header written by INTI with the images, None for the scans that have none (helium)."""
    from astropy.io import fits
    for name in ('sunscan_clahe.fits', 'sunscan_raw.fits'):
        try:
            return fits.getheader(os.path.join(directory, name))
        except Exception:
            continue
    return None


def _observation_date(directory, header):
    """UTC date of the scan, ISO 8601 with milliseconds : FITS header, else INTI log, else directory name."""
    candidates = []
    if header is not None:
        candidates.append(str(header.get('DATE-OBS', '')))
    try:
        with open(os.path.join(directory, '_scan_log.txt'), encoding='latin-1') as f:
            candidates += [line.split('UTC :')[1] for line in f if 'UTC :' in line][:1]
    except (OSError, IndexError):
        pass
    for candidate in candidates:
        match = re.match(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(\.\d{1,3})?', candidate.strip().strip('"'))
        if match:
            return match.group(1) + (match.group(2) or '.0').ljust(4, '0') + 'Z'
    # The directories are named by the camera controller with the UTC time of the recording
    match = re.search(r'(\d{4})_(\d{2})_(\d{2})-(\d{2})_(\d{2})_(\d{2})', os.path.basename(directory))
    if match:
        return '{}-{}-{}T{}:{}:{}.000Z'.format(*match.groups())
    return None


def _scan_line(directory):
    """Line tag of the scan, '' when it has none."""
    tags = [f.split('_', 1)[-1] for f in os.listdir(directory) if f.startswith('tag_')]
    return tags[0] if tags and tags[0] in HUB_LINES else ''


def _iso(timestamp):
    return time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(timestamp)) + '.000Z'


def _timestamp(date):
    return calendar.timegm(time.strptime(date[:19], '%Y-%m-%dT%H:%M:%S'))


def _info(item, directory):
    """
    What is known about a scan, a stack or an animation : {date, line, header, count, notes}.

    The date of a stack is the middle of its scans, the one of an animation is its first scan. It is
    None for the stacks and animations made before their sources were recorded : their directory only
    tells when they were created, the frontend has to ask the date of the observation.
    """
    if item == 'scan':
        header = _fits_header(directory)
        return {'date': _observation_date(directory, header), 'line': _scan_line(directory),
                'header': header, 'count': 1, 'notes': ''}
    sources = read_sources(directory) or {}
    count = sources.get('count') or _derived_images(item, directory)[1]
    # Its own tag first : the one of its scans when it was created, or set by hand since (older stacks, wrong tag)
    info = {'date': None, 'line': _scan_line(directory) or (sources.get('line') if sources.get('line') in HUB_LINES else ''),
            'header': None, 'count': count, 'notes': ''}
    first, last = sources.get('date_first'), sources.get('date_last')
    try:
        if first and last:
            info['date'] = _iso(_timestamp(first) if item == 'animation' else (_timestamp(first) + _timestamp(last)) // 2)
            span = f'{first[:10]} {first[11:19]} to ' + (last[11:19] if last[:10] == first[:10] else f'{last[:10]} {last[11:19]}')
            info['notes'] = f'{item.capitalize()} of {count} scans, {span} UT'
    except (ValueError, TypeError):
        info['date'] = None
    return info


def _default_title(item, info, line):
    title = HUB_LINES[line or DEFAULT_LINE][0]
    if info['date']:
        title += f" - {info['date'][:10]}"
    if item == 'stack':
        title += f" - stack of {info['count']} scans" if info['count'] else ' - stack'
    return title + (' - animation' if item == 'animation' else '')


def _last_upload(directory):
    try:
        with open(os.path.join(directory, SPECTROSOLHUB_FILE)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def describe(filename):
    """What the frontend needs to propose an upload : images, default values, lines, last upload."""
    item, directory = _item(filename)
    info = _info(item, directory)
    return {
        'key': scan_key(filename),
        'type': item,
        'images': [{name: value for name, value in image.items() if not name.startswith('_')}
                   for image in _images(item, directory)],
        'defaults': {'title': _default_title(item, info, info['line']), 'line': info['line'] or DEFAULT_LINE,
                     'line_from_tag': bool(info['line']), 'observation_date': info['date'],
                     'date_known': info['date'] is not None, 'notes': info['notes'], 'publish': True},
        'lines': [{'key': key, 'label': LineDict.get(key, label), 'hub_label': label, 'wavelength': wavelength}
                  for key, (label, wavelength) in HUB_LINES.items()],
        'last_upload': _last_upload(directory),
    }


# -- Session and image metadata --

def _carrington_rotation(jd):
    """
    Same formula as JSol'Ex and INTI Partner : mean rotations of 27.2753 days since the first one (1853-11-09).
    Checked against _solar_angles : its rotation starts fall where L0 goes through 0, within 0.2 day
    (rotation 2000 on 2003-02-20, rotation 2315 on 2026-08-29).
    """
    return int((jd - 2398167.2763889) / 27.2753) + 1


def _solar_angles(jd):
    """
    P, B0 and L0 in degrees at a julian date : Meeus, Astronomical Algorithms, chapter 29.
    Checked against its example 29.a (1992-10-13 0h : P 26.27, B0 5.99, L0 238.63).

    angle_P_B0 of Inti_functions gives the same P and B0 but its L0 is about 30 degrees off
    (mean rotation of 27.2743 days instead of 27.2753, 214.47 on the example above), so it is
    not used here : these values go to a scientific archive.
    """
    theta = (jd - 2398220) * 360 / 25.38
    inclination = 7.25
    k = 73.6667 + 1.3958333 * (jd - 2396758) / 36525
    t = (jd - 2451545) / 36525
    mean_longitude = (0.0003032 * t + 36000.76983) * t + 280.46645
    anomaly = math.radians(((-0.00000048 * t - 0.0001559) * t + 35999.05030) * t + 357.52910)
    center = ((-0.000014 * t - 0.004817) * t + 1.914600) * math.sin(anomaly) \
        + (-0.000101 * t - 0.019993) * math.sin(2 * anomaly) + 0.000290 * math.sin(3 * anomaly)
    longitude = mean_longitude + center - 0.00569 - 0.00478 * math.sin(math.radians(125.04 - 1934.136 * t))
    from_node = math.radians(longitude - k)
    x = math.atan(-math.cos(math.radians(longitude + 0.004419)) * math.tan(math.radians(23.440144)))
    y = math.atan(-math.cos(from_node) * math.tan(math.radians(inclination)))
    b0 = math.asin(math.sin(from_node) * math.sin(math.radians(inclination)))
    eta = math.atan2(-math.sin(from_node) * math.cos(math.radians(inclination)), -math.cos(from_node))
    return math.degrees(x + y), math.degrees(b0), (math.degrees(eta) - theta) % 360


def _solar_metadata(date):
    """P, B0, L0 angles and Carrington rotation at the date of the scan. Never raises."""
    try:
        import astropy.time
        jd = astropy.time.Time(date.rstrip('Z')).jd
        p, b0, l0 = _solar_angles(jd)
        return {'solarP': round(p, 2), 'solarB0': round(b0, 2), 'solarL0': round(l0, 2),
                'carringtonRotation': _carrington_rotation(jd)}
    except Exception as e:
        logging.warning(f'spectrosolhub : no solar parameters for {date} : {e}')
        return {}


def _disk_geometry(path, header):
    """
    Center and radius of the disk in the image, from the FITS header. The images are flipped
    vertically compared to the FITS. Nothing when the image has not the size of the FITS.
    """
    try:
        from PIL import Image
        with Image.open(path) as image:
            width, height = image.size
        if (width, height) != (int(header['NAXIS1']), int(header['NAXIS2'])):
            return {}
        return {'centerX': int(header['CENTER_X']), 'centerY': height - 1 - int(header['CENTER_Y']),
                'solarRadius': int(header['SOLAR_R'])}
    except Exception:
        return {}


def _session_request(title, date, line, notes, software_version):
    label, wavelength = HUB_LINES[line]
    return {
        'title': title,
        'observationDate': date,
        'spectralLine': label,
        'customWavelengthAngstroms': wavelength,
        'spectroheliograph': dict(SPECTROHELIOGRAPH),
        'telescope': dict(TELESCOPE),
        'camera': dict(CAMERA),
        'mount': dict(MOUNT),
        'energyRejectionFilter': ENERGY_REJECTION_FILTER,
        'latitude': None,
        'longitude': None,
        'notes': notes or None,
        'softwareName': 'SunScan',
        'softwareVersion': software_version,
    }


def _image_metadata(path, image_line, date, header, solar):
    """Same fields as the ImageMetadata of JSol'Ex, as INTI Partner does."""
    metadata = dict(solar)
    if date:
        metadata['dateObs'] = date
    if header is not None:
        metadata.update(_disk_geometry(path, header))
        observer = str(header.get('OBSERVER', '')).strip()
        if observer:
            metadata['observer'] = observer
    if image_line:
        metadata['spectralLine'], metadata['wavelengthAngstroms'] = HUB_LINES[image_line]
    else:
        metadata['spectralLine'] = 'Other'
    metadata.update({
        'instrument': SPECTROHELIOGRAPH['name'],
        'cameraFocalLength': SPECTROHELIOGRAPH['cameraFocalLength'],
        'collimatorFocalLength': SPECTROHELIOGRAPH['collimatorFocalLength'],
        'grating': SPECTROHELIOGRAPH['gratingDensity'],
        'gratingOrder': SPECTROHELIOGRAPH['gratingOrder'],
        'shgAngle': SPECTROHELIOGRAPH['totalAngleDegrees'],
        'slitWidth': SPECTROHELIOGRAPH['slitWidthMicrons'] / 1000.0,  # mm
        'slitHeight': SPECTROHELIOGRAPH['slitHeightMillimeters'],
        'camera': f"{CAMERA['brand']} {CAMERA['model']}",
        'focalLength': float(TELESCOPE['focalLengthMm']),
        'aperture': TELESCOPE['apertureMm'],
        'pixelSizeMm': CAMERA['pixelSizeUm'] / 1000.0,
        'binning': CAMERA['binning'],
        'energyRejectionFilter': ENERGY_REJECTION_FILTER,
        # The SunScan images are never rotated by the P angle
        'pAngleCorrected': False,
    })
    return metadata


# -- Upload --

def _check_quota(quota, count, size):
    images_left = quota['image_count'] - quota['used_image_count']
    bytes_left = quota['storage_bytes'] - quota['used_storage_bytes']
    if quota['image_count'] > 0 and count > images_left:
        raise HubError('quota_exceeded', f'{count} images to send, {images_left} left on the account', 507)
    if quota['storage_bytes'] > 0 and size > bytes_left:
        raise HubError('quota_exceeded', f'{size} bytes to send, {bytes_left} left on the account', 507)


def _send_image(token, session_id, image, sent):
    """Send one image in chunks, 'sent' is called with the size of each chunk once it is on the hub."""
    with open(image['path'], 'rb') as f:
        data = f.read()
    upload = _request('POST', '/api/uploads/initiate', token=token, expected=201, payload={
        'sessionId': session_id,
        'title': image['title'],
        'description': None,
        'imageKind': image['hub_kind'],
        'imageMetadata': json.dumps(image['metadata']),
        'totalSize': len(data),
        'contentType': image['content_type'],
    }) or {}
    upload_id, chunk_size, parts = upload.get('uploadId'), upload.get('chunkSize', 0), upload.get('totalParts', 0)
    if not upload_id or chunk_size <= 0 or parts <= 0:
        raise HubError('hub_error', f'Unexpected answer to the upload request : {upload}', 502)
    for part in range(1, parts + 1):
        chunk = data[(part - 1) * chunk_size:part * chunk_size]
        _request_again('PUT', f'/api/uploads/{upload_id}/parts/{part}', token=token, data=chunk)
        sent(len(chunk))
    _request('POST', f'/api/uploads/{upload_id}/complete', token=token, expected=201)


def _upload_worker(job):
    global _current
    key, images = job['key'], job['images']
    url, published = '', 0
    try:
        progress.update(key, 'checking_account', 0, images=len(images))
        total = sum(image['size'] for image in images)
        _check_quota(_quota(job['token']), len(images), total)

        progress.update(key, 'creating_session', 2)
        session = _request('POST', '/api/sessions', token=job['token'], payload=job['session'], expected=201) or {}
        if session.get('id') is None:
            raise HubError('hub_error', f'No session id in the answer of the hub : {session}', 502)
        url = f"{BASE_URL}/observation/{session['id']}"

        # 5 to 95 % : the images, by bytes sent
        done = [0]
        for index, image in enumerate(images, 1):
            def sent(size, index=index):
                done[0] += size
                progress.update(key, 'uploading_images', 5 + 90 * done[0] // max(total, 1), image=index, url=url)
            progress.update(key, 'uploading_images', 5 + 90 * done[0] // max(total, 1), image=index, url=url)
            _send_image(job['token'], session['id'], image, sent)

        if job['publish']:
            progress.update(key, 'publishing', 96)
            try:
                _request('POST', f"/api/sessions/{session['id']}/publish", token=job['token'])
                published = 1
            except HubError as e:
                # The images are on the hub : the session stays a draft that can be published from the site
                logging.warning(f'spectrosolhub : session {session["id"]} not published : {e}')

        record = {'session_id': session['id'], 'url': url, 'published': bool(published),
                  'title': job['session']['title'], 'images': [image['kind'] for image in images],
                  'uploaded_at': int(time.time())}
        try:
            with open(os.path.join(job['directory'], SPECTROSOLHUB_FILE), 'w') as f:
                json.dump(record, f)
        except OSError as e:
            logging.warning(f'spectrosolhub : can not save the upload record : {e}')
        logging.info(f'spectrosolhub : {len(images)} images of {job["directory"]} sent to {url}')
        progress.finish(key, 'completed', url=url, published=published)
    except HubError as e:
        _forget_token_if_expired(e)
        logging.warning(f'spectrosolhub : upload failed : {e.code} {e}')
        # When the session exists, its url lets the user find the incomplete draft on the hub
        progress.finish(key, 'failed', e.code, str(e), url=url)
    except Exception as e:
        logging.exception('spectrosolhub : upload failed')
        progress.finish(key, 'failed', 'upload_failed', str(e), url=url)
    finally:
        _current = None
        _upload_lock.release()


def _checked_date(observation_date):
    """Date given by the frontend for a stack or an animation that does not know its own : ISO 8601, UTC."""
    observation_date = (observation_date or '').strip()
    if not observation_date:
        raise HubError('missing_observation_date', 'The date of the observation is not known, it must be given', 400)
    match = re.fullmatch(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(\.\d{1,3})?Z', observation_date)
    try:
        return _iso(_timestamp(match.group(1)))
    except (AttributeError, ValueError):
        raise HubError('invalid_observation_date', f'Expected YYYY-MM-DDTHH:MM:SSZ (UTC) : {observation_date}', 400)


def start_upload(filename, images=None, title='', notes='', line='', publish=True, software_version='',
                 observation_date=''):
    """
    Check the request and start the upload of the images of a scan, a stack or an animation in the background.

    Args:
        filename (str): Path of the SER file of the scan as everywhere in the API, or directory of a stack or an animation.
        images (list): Kinds of the images to send ('clahe', 'protus'...), None for the default ones.
        title (str): Title of the session on the hub, '<line> - <date>' when empty.
        notes (str): Free text shown with the session.
        line (str): Line tag (config.LineDict) when the tag of the scan is missing or wrong.
        publish (bool): Publish the session, it stays a draft of the account otherwise.
        software_version (str): Version of the backend, sent with the session.
        observation_date (str): Only used, and then required, when the date of the observation is not known.

    Raises HubError when the request can not be accepted.
    """
    global _current
    token = _token()
    if not token:
        raise HubError('not_connected', 'No SpectroSolHub account, log in first', 401)
    item, directory = _item(filename)
    available = {image['kind']: image for image in _images(item, directory)}
    if not available:
        raise HubError('not_processed', 'Nothing to send : no image here, a scan must be processed first', 409)
    if images is None:
        images = [kind for kind, image in available.items() if image['default']]
    unknown = [kind for kind in images if kind not in available]
    if unknown:
        raise HubError('invalid_image', f'Images not available for this scan : {", ".join(unknown)}', 400)
    if not images:
        raise HubError('no_image', 'No image to send', 400)
    info = _info(item, directory)
    line = line or info['line'] or DEFAULT_LINE
    if line not in HUB_LINES:
        raise HubError('invalid_line', f'Unknown line : {line}', 400)
    # Never a guess : the directory of an old stack tells when it was made, not when the Sun was observed
    date = info['date'] or _checked_date(observation_date)
    info = dict(info, date=date)
    if not _upload_lock.acquire(blocking=False):
        raise HubError('busy', 'An upload is already running', 409)

    try:
        # The solar angles of one date mean nothing for an animation, which can last for hours
        solar = _solar_metadata(date) if item != 'animation' else {}
        job_images = []
        # Sending order of the images, whatever the order of the request
        for kind, image in available.items():
            if kind not in images:
                continue
            image_line = line if image['_line'] == 'scan' else image['_line']
            job_images.append({'kind': kind, 'path': image['_path'], 'size': image['size'],
                               'hub_kind': image['_hub_kind'], 'title': image['_title'],
                               'content_type': image['_content_type'],
                               'metadata': _image_metadata(image['_path'], image_line, date, info['header'], solar)})
        key = scan_key(filename)
        job = {'key': key, 'token': token, 'directory': directory, 'images': job_images, 'publish': bool(publish),
               'session': _session_request((title or '').strip() or _default_title(item, info, line), date, line,
                                           (notes or '').strip(), software_version)}
        progress.start(key)
        _current = {'key': key, 'filename': filename}
        Thread(target=_upload_worker, args=(job,), name='spectrosolhub-upload', daemon=True).start()
    except Exception:
        _upload_lock.release()
        raise
    return {'status': 'started', 'key': key, 'images': [image['kind'] for image in job_images]}


def upload_status(filename):
    """Last known state of the upload of a scan, same fields as the WebSocket message."""
    key = scan_key(filename)
    state = progress.get(key)
    if state is None:
        state = {'key': key, 'status': 'unknown', 'percent': 0, 'step': '', 'error': '', 'detail': '',
                 'image': 0, 'images': 0, 'url': '', 'published': 0}
    names = ('key', 'status', 'percent', 'step', 'error', 'detail', 'image', 'images', 'url', 'published')
    return {name: state[name] for name in names}
