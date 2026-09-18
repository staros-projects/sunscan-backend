"""
WiFi provisioning : lets the mobile app move the SunScan from its own hotspot to the
home WiFi network, and back.

By default the SunScan is a WiFi access point (NetworkManager profile in 'ap' mode,
SSID sunscan-<last 6 hex digits of the MAC>). The app lists the networks seen by the
Pi, sends the SSID and password, and the Pi joins that network. The home network
profile gets a higher autoconnect priority than the hotspot, so NetworkManager picks it
at boot when it is in range and falls back to the hotspot otherwise (in the field).

The Pi 4 has a single WiFi radio : joining the home network stops the hotspot, so the
phone loses the link during the switch. connect() therefore answers right away and does
the switch in a background thread after a short delay. When the home network can not be
joined, the new profile is removed and the previous connection (the hotspot) is restored,
and the result is kept for the app to read once it is back on the hotspot.

Needs NetworkManager (Bookworm and later). On older releases every call reports
'supported': False.

On the home network the backend is announced over mDNS as a '_sunscan._tcp' service,
with the device id in the TXT record, so the app finds it whatever its IP address.

Set SUNSCAN_NO_NETWORK_MONITOR=1 to disable the background monitor (mDNS announce and
automatic return to the home network).
"""

import ctypes
import json
import logging
import os
import re
import shutil
import signal
import subprocess
import time
from threading import Lock, Thread

HOTSPOT_IP = '10.42.0.1'  # NetworkManager 'shared' mode address
API_PORT = 8000
MDNS_SERVICE_TYPE = '_sunscan._tcp'

# The home network profiles created by the app, above the hotspot (priority 0)
CLIENT_PRIORITY = 10
CLIENT_NAME_PREFIX = 'sunscan-wifi-'
NM_POWERSAVE_DISABLE = '2'

# Delay before switching, so the HTTP response reaches the phone before the hotspot stops
SWITCH_DELAY = 2
# Maximum time given to NetworkManager to join the network and get an address
CONNECT_TIMEOUT = 45

# In hotspot mode, look for a saved home network at this interval (seconds), when no phone
# is connected to the hotspot
RETURN_HOME_INTERVAL = 120
MONITOR_PERIOD = 15

CMD_TIMEOUT = 20

# The backend runs as a service, without a login session : polkit refuses it the NetworkManager
# settings by default. This rule gives them to the netdev group (the backend user). sudo nmcli
# is not an option, the WiFi password would end up in the sudo log.
# Must sort before 49-polkit-pkla-compat.rules, whose NetworkManager .pkla answers 'no' to
# processes without an active session and stops the evaluation.
POLKIT_RULE_FILE = '/etc/polkit-1/rules.d/40-sunscan-network.rules'
POLKIT_RULE = '''// SunScan backend : WiFi provisioning from the mobile app (see docs/provisioning-wifi.md)
polkit.addRule(function(action, subject) {
    if (subject.isInGroup("netdev") && (
            action.id == "org.freedesktop.NetworkManager.settings.modify.system" ||
            action.id == "org.freedesktop.NetworkManager.network-control" ||
            action.id == "org.freedesktop.NetworkManager.wifi.scan" ||
            action.id == "org.freedesktop.NetworkManager.wifi.share.protected" ||
            action.id == "org.freedesktop.NetworkManager.wifi.share.open")) {
        return polkit.Result.YES;
    }
});
'''
STATE_FILE = os.path.expanduser('~/.config/sunscan/network.json')

_attempt_lock = Lock()
_state_lock = Lock()
_scan_cache = {'networks': [], 'scanned_at': None}
_attempt = {'state': 'idle', 'ssid': '', 'error': '', 'detail': '', 'ip': '',
            'started_at': None, 'finished_at': None}
_last_client = None  # last successful connection to a home network : {ssid, ip, at}


# -- Helpers --

def _run(cmd, as_root=False, timeout=CMD_TIMEOUT):
    """Run a command and return (success, stdout, stderr). Never raises."""
    if as_root and os.geteuid() != 0:
        cmd = ['sudo', '-n'] + cmd
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             timeout=timeout, universal_newlines=True)
        return res.returncode == 0, res.stdout.strip(), res.stderr.strip()
    except subprocess.TimeoutExpired:
        return False, '', 'timeout'
    except Exception as e:
        return False, '', str(e)


def _split_terse(line):
    """Split a 'nmcli -t' line : fields separated by ':', with '\\:' and '\\\\' escaped."""
    fields, cur, i = [], [], 0
    while i < len(line):
        c = line[i]
        if c == '\\' and i + 1 < len(line):
            cur.append(line[i + 1])
            i += 2
            continue
        if c == ':':
            fields.append(''.join(cur))
            cur = []
        else:
            cur.append(c)
        i += 1
    fields.append(''.join(cur))
    return fields


def _nm_values(args):
    """'nmcli -t -f a,b ...' in multiline mode, as a dict {field: value}."""
    ok, out, _ = _run(['nmcli', '-t'] + args)
    values = {}
    if ok:
        for line in out.splitlines():
            key, _, value = line.partition(':')
            values.setdefault(key, value.replace('\\:', ':').replace('\\\\', '\\'))
    return values


def is_supported():
    if not shutil.which('nmcli'):
        return False
    ok, out, _ = _run(['nmcli', '-t', '-f', 'RUNNING', 'general'])
    return ok and out == 'running'


def _wifi_device():
    ok, out, _ = _run(['nmcli', '-t', '-f', 'DEVICE,TYPE', 'device'])
    if ok:
        for line in out.splitlines():
            device, dtype = (_split_terse(line) + [''])[:2]
            if dtype == 'wifi':
                return device
    return 'wlan0'


def device_id():
    """Last 6 hex digits of the WiFi MAC address, as in the hotspot SSID."""
    try:
        with open(f'/sys/class/net/{_wifi_device()}/address') as f:
            return f.read().strip().replace(':', '')[-6:]
    except OSError:
        return ''


def _profiles():
    """WiFi profiles of NetworkManager : [{uuid, name, ssid, mode, priority}]."""
    ok, out, _ = _run(['nmcli', '-t', '-f', 'UUID,TYPE,NAME', 'connection', 'show'])
    profiles = []
    if not ok:
        return profiles
    for line in out.splitlines():
        uuid, ctype, name = (_split_terse(line) + ['', ''])[:3]
        if ctype != '802-11-wireless':
            continue
        v = _nm_values(['-f', '802-11-wireless.mode,802-11-wireless.ssid,connection.autoconnect-priority',
                        'connection', 'show', uuid])
        try:
            priority = int(v.get('connection.autoconnect-priority', '0'))
        except ValueError:
            priority = 0
        profiles.append({'uuid': uuid, 'name': name, 'ssid': v.get('802-11-wireless.ssid', ''),
                         'mode': v.get('802-11-wireless.mode', ''), 'priority': priority})
    return profiles


def _hotspot_profile(profiles=None):
    for p in profiles if profiles is not None else _profiles():
        if p['mode'] == 'ap':
            return p
    return None


def _client_profiles(profiles=None):
    return [p for p in (profiles if profiles is not None else _profiles()) if p['mode'] != 'ap']


def _device_state(device):
    """{state (NM numeric state), uuid, ip} of the WiFi device."""
    v = _nm_values(['-f', 'GENERAL.STATE,GENERAL.CON-UUID,IP4.ADDRESS', 'device', 'show', device])
    try:
        state = int(v.get('GENERAL.STATE', '0').split()[0])
    except (ValueError, IndexError):
        state = 0
    return {'state': state, 'uuid': v.get('GENERAL.CON-UUID', ''),
            'ip': v.get('IP4.ADDRESS[1]', '').split('/')[0]}


def _hotspot_has_clients(device):
    ok, out, _ = _run(['iw', 'dev', device, 'station', 'dump'], as_root=True)
    return not ok or 'Station' in out  # unknown : assume yes, nobody gets disconnected


def _load_state():
    global _last_client
    try:
        with open(STATE_FILE) as f:
            data = json.load(f)
        _last_client = data.get('last_client')
        saved = data.get('attempt')
        if saved and saved.get('state') != 'connecting':  # interrupted by a reboot : forget it
            _attempt.update(saved)
    except (OSError, ValueError):
        pass


def _save_state():
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE + '.tmp', 'w') as f:
            json.dump({'last_client': _last_client, 'attempt': _attempt}, f)
        os.replace(STATE_FILE + '.tmp', STATE_FILE)
    except OSError as e:
        logging.warning(f'network : can not save state : {e}')


# -- Scan --

def _signal_from_dbm(dbm):
    """Same scale as NetworkManager : -100 dBm = 0 %, -50 dBm = 100 %."""
    return max(0, min(100, int(round(2 * (dbm + 100)))))


def _decode_iw_ssid(raw):
    data = re.sub(rb'\\x([0-9a-fA-F]{2})', lambda m: bytes([int(m.group(1), 16)]), raw.encode('latin-1'))
    return data.decode('utf-8', errors='replace')


def _parse_iw_scan(out):
    """Parse 'iw dev <dev> scan' into the same entries as the nmcli scan."""
    networks, bss = [], None

    def flush():
        if bss is None:
            return
        sec = []
        if bss['wpa']:
            sec.append('WPA1')
        if bss['rsn_psk'] or bss['eap']:
            sec.append('WPA2')
        if bss['sae']:
            sec.append('WPA3')
        if bss['eap']:
            sec.append('802.1X')
        if not sec and bss['privacy']:
            sec.append('WEP')
        networks.append({'ssid': bss['ssid'], 'signal': bss['signal'], 'freq': bss['freq'],
                         'security': ' '.join(sec), 'in_use': False})

    for line in out.splitlines():
        if line.startswith('BSS '):
            flush()
            bss = {'ssid': '', 'signal': 0, 'freq': 0, 'wpa': False, 'rsn_psk': False,
                   'sae': False, 'eap': False, 'privacy': False, 'block': ''}
            continue
        if bss is None:
            continue
        s = line.strip()
        if s.startswith('SSID:'):
            bss['ssid'] = _decode_iw_ssid(line.split('SSID:', 1)[1][1:])
        elif s.startswith('signal:'):
            try:
                bss['signal'] = _signal_from_dbm(float(s.split()[1]))
            except (ValueError, IndexError):
                pass
        elif s.startswith('freq:'):
            try:
                bss['freq'] = int(float(s.split()[1]))
            except (ValueError, IndexError):
                pass
        elif s.startswith('capability:'):
            bss['privacy'] = 'Privacy' in s
        elif s.startswith('WPA:'):
            bss['wpa'], bss['block'] = True, 'wpa'
        elif s.startswith('RSN:'):
            bss['block'] = 'rsn'
        elif s.startswith('* Authentication suites:'):
            suites = s.split(':', 1)[1]
            if 'IEEE 802.1X' in suites:
                bss['eap'] = True
            if 'SAE' in suites:
                bss['sae'] = True
            if 'PSK' in suites and bss['block'] == 'rsn':
                bss['rsn_psk'] = True
    flush()
    return networks


def _scan_nmcli(device):
    ok, out, err = _run(['nmcli', '-t', '-f', 'IN-USE,SSID,SIGNAL,SECURITY,FREQ',
                         'device', 'wifi', 'list', 'ifname', device, '--rescan', 'yes'], timeout=30)
    if not ok:
        # rescans are rate limited by NetworkManager, the recent results are good enough
        ok, out, err = _run(['nmcli', '-t', '-f', 'IN-USE,SSID,SIGNAL,SECURITY,FREQ',
                             'device', 'wifi', 'list', 'ifname', device, '--rescan', 'no'])
    if not ok:
        return None, err
    networks = []
    for line in out.splitlines():
        in_use, ssid, sig, security, freq = (_split_terse(line) + [''] * 4)[:5]
        try:
            sig, freq = int(sig), int(freq.split()[0])
        except (ValueError, IndexError):
            sig, freq = 0, 0
        networks.append({'ssid': ssid, 'signal': sig, 'freq': freq,
                         'security': security.strip(), 'in_use': in_use.strip() == '*'})
    return networks, ''


def _scan_iw(device):
    """In access point mode NetworkManager does not scan, the driver does with 'ap-force'."""
    ok, out, err = _run(['iw', 'dev', device, 'scan', 'ap-force'], as_root=True, timeout=30)
    if not ok:
        return None, err or 'iw scan failed'
    return _parse_iw_scan(out), ''


def _security_kind(security):
    """'open', 'wep', 'psk', 'sae' (WPA3 only), or 'enterprise'."""
    if '802.1X' in security:
        return 'enterprise'
    if 'WPA3' in security and 'WPA2' not in security and 'WPA1' not in security:
        return 'sae'
    if 'WPA' in security:
        return 'psk'
    if 'WEP' in security:
        return 'wep'
    return 'open'


def scan(refresh=True):
    """
    Networks seen by the Pi, one entry per SSID (best signal), strongest first.
    When the scan is not possible, the last results are returned with 'cached': True.
    """
    if not is_supported():
        return {'supported': False, 'networks': [], 'scanned_at': None, 'cached': False}

    error = ''
    if refresh:
        device = _wifi_device()
        profiles = _profiles()
        dev = _device_state(device)
        hotspot = _hotspot_profile(profiles)
        in_ap = bool(hotspot and dev['uuid'] == hotspot['uuid'])
        networks, error = _scan_iw(device) if in_ap else _scan_nmcli(device)
        if networks is not None:
            saved = {p['ssid'] for p in _client_profiles(profiles)}
            own = hotspot['ssid'] if hotspot else None
            best = {}
            for n in networks:
                if not n['ssid'] or n['ssid'] == own:
                    continue
                if n['ssid'] not in best or n['signal'] > best[n['ssid']]['signal'] or n['in_use']:
                    best[n['ssid']] = dict(n, in_use=n['in_use'] or best.get(n['ssid'], {}).get('in_use', False))
            result = []
            for n in sorted(best.values(), key=lambda n: -n['signal']):
                result.append({'ssid': n['ssid'], 'signal': n['signal'],
                               'band': '5GHz' if n['freq'] >= 4900 else '2.4GHz',
                               'security': _security_kind(n['security']),
                               'saved': n['ssid'] in saved, 'in_use': n['in_use']})
            with _state_lock:
                _scan_cache['networks'] = result
                _scan_cache['scanned_at'] = int(time.time())
            return {'supported': True, 'networks': result, 'scanned_at': _scan_cache['scanned_at'], 'cached': False}
        logging.warning(f'network : WiFi scan failed : {error}')

    with _state_lock:
        return {'supported': True, 'networks': list(_scan_cache['networks']),
                'scanned_at': _scan_cache['scanned_at'], 'cached': True, 'error': error}


# -- Status --

def status():
    if not is_supported():
        return {'supported': False}
    device = _wifi_device()
    profiles = _profiles()
    dev = _device_state(device)
    hotspot = _hotspot_profile(profiles)
    active = next((p for p in profiles if p['uuid'] == dev['uuid']), None) if dev['uuid'] else None

    if active and active['mode'] == 'ap':
        mode = 'hotspot'
    elif active and dev['state'] == 100:
        mode = 'client'
    elif 40 <= dev['state'] < 100:
        mode = 'connecting'
    else:
        mode = 'disconnected'

    with _state_lock:
        attempt = dict(_attempt)
        last_client = dict(_last_client) if _last_client else None
    return {
        'supported': True,
        'device_id': device_id(),
        'hostname': os.uname().nodename,
        'mode': mode,
        'ssid': active['ssid'] if active else '',
        'ip': dev['ip'],
        'hotspot': {'ssid': hotspot['ssid'] if hotspot else '', 'ip': HOTSPOT_IP},
        'saved_networks': sorted({p['ssid'] for p in _client_profiles(profiles) if p['ssid']}),
        'attempt': attempt,
        'last_client': last_client,
    }


# -- Connect --

class ProvisioningError(Exception):
    def __init__(self, code, message, http_status=400):
        super().__init__(message)
        self.code = code
        self.http_status = http_status


def _error_from_nmcli(err):
    e = err.lower()
    if 'secrets were required' in e or 'no secrets' in e:
        return 'wrong_password'
    if 'no network with ssid' in e or 'not found' in e:
        return 'network_not_found'
    if 'timeout' in e or 'timed out' in e:
        return 'timeout'
    return 'connection_failed'


def _finish(state, error='', detail='', ip=''):
    global _last_client
    with _state_lock:
        _attempt.update({'state': state, 'error': error, 'detail': detail, 'ip': ip,
                         'finished_at': int(time.time())})
        if state == 'connected':
            _last_client = {'ssid': _attempt['ssid'], 'ip': ip, 'at': _attempt['finished_at']}
        _save_state()


def _activate(uuid, timeout=CONNECT_TIMEOUT):
    return _run(['nmcli', '--wait', str(timeout), 'connection', 'up', 'uuid', uuid], timeout=timeout + 10)


def _activate_client(uuid, timeout=CONNECT_TIMEOUT):
    """
    Like _activate, but a wrong password is detected right away : NetworkManager then asks
    nmcli for the password again, nmcli can not ask and would wait until the timeout.
    """
    try:
        proc = subprocess.Popen(['nmcli', '--wait', str(timeout), 'connection', 'up', 'uuid', uuid],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    except Exception as e:
        return False, '', str(e)
    err = []
    for line in proc.stderr:
        err.append(line.strip())
        if 'password for' in line and 'not given' in line:
            proc.kill()
            proc.wait()
            return False, '', 'Secrets were required, but not provided. ' + line.strip()
    try:
        out = proc.stdout.read()
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        return False, '', 'timeout'
    return proc.returncode == 0, out.strip(), ' '.join(err)


def _restore(previous_uuid):
    """Bring back the connection active before the attempt, the hotspot if there was none."""
    target = previous_uuid
    if not target:
        hotspot = _hotspot_profile()
        target = hotspot['uuid'] if hotspot else None
    if target:
        ok, _, err = _activate(target, timeout=30)
        logging.info(f'network : previous connection restored : {"ok" if ok else err}')


def _connect_worker(ssid, password, hidden, kind):
    device = _wifi_device()
    try:
        time.sleep(SWITCH_DELAY)
        previous_uuid = _device_state(device)['uuid']
        old_profiles = [p for p in _client_profiles() if p['ssid'] == ssid]

        name = f'{CLIENT_NAME_PREFIX}{ssid}'
        args = ['nmcli', 'connection', 'add', 'type', 'wifi', 'ifname', device, 'con-name', name,
                'ssid', ssid, 'connection.autoconnect', 'yes',
                'connection.autoconnect-priority', str(CLIENT_PRIORITY),
                '802-11-wireless.powersave', NM_POWERSAVE_DISABLE]
        if hidden:
            args += ['802-11-wireless.hidden', 'yes']
        if password:
            args += ['wifi-sec.key-mgmt', 'sae' if kind == 'sae' else 'wpa-psk', 'wifi-sec.psk', password]
        ok, out, err = _run(args)
        uuid = re.search(r'\(([0-9a-f-]{36})\)', out)
        if not ok or not uuid:
            _finish('failed', 'connection_failed', err)
            return
        uuid = uuid.group(1)

        logging.info(f'network : joining "{ssid}"')
        ok, _, err = _activate_client(uuid)
        dev = _device_state(device)
        if ok and dev['state'] == 100 and dev['uuid'] == uuid and dev['ip']:
            # the new profile works : the older ones for the same SSID would compete with it
            for p in old_profiles:
                _run(['nmcli', 'connection', 'delete', 'uuid', p['uuid']])
            logging.info(f'network : connected to "{ssid}", address {dev["ip"]}')
            _finish('connected', ip=dev['ip'])
            return

        error = _error_from_nmcli(err) if not ok else 'no_address'
        logging.warning(f'network : can not join "{ssid}" : {error} {err}')
        _run(['nmcli', 'connection', 'delete', 'uuid', uuid])
        _restore(previous_uuid)
        _finish('failed', error, err)
    except Exception as e:
        logging.exception('network : connection attempt failed')
        _restore(None)
        _finish('failed', 'connection_failed', str(e))
    finally:
        _attempt_lock.release()


def connect(ssid, password='', hidden=False):
    """
    Validate the request and start the switch to the given network in the background.
    Raises ProvisioningError when the request can not be accepted.
    """
    if not is_supported():
        raise ProvisioningError('not_supported', 'NetworkManager is not available', 501)
    ssid = ssid or ''
    password = password or ''
    if not 1 <= len(ssid.encode('utf-8')) <= 32:
        raise ProvisioningError('invalid_ssid', 'The SSID must be 1 to 32 bytes long')

    with _state_lock:
        known = next((n for n in _scan_cache['networks'] if n['ssid'] == ssid), None)
    kind = known['security'] if known else ('psk' if password else 'open')
    if kind in ('enterprise', 'wep'):
        raise ProvisioningError('unsupported_security', f'{kind} networks are not supported')
    if kind == 'open':
        password = ''
    elif not (8 <= len(password) <= 63 or re.fullmatch(r'[0-9a-fA-F]{64}', password)):
        raise ProvisioningError('invalid_password', 'The password must be 8 to 63 characters long')

    hotspot = _hotspot_profile()
    if hotspot and ssid == hotspot['ssid']:
        raise ProvisioningError('invalid_ssid', 'This is the SunScan hotspot')

    if not _attempt_lock.acquire(blocking=False):
        raise ProvisioningError('busy', 'A connection attempt is already running', 409)
    with _state_lock:
        _attempt.update({'state': 'connecting', 'ssid': ssid, 'error': '', 'detail': '', 'ip': '',
                         'started_at': int(time.time()), 'finished_at': None})
        _save_state()
    Thread(target=_connect_worker, args=(ssid, password, hidden, kind), name='wifi-connect', daemon=True).start()
    return {'status': 'connecting', 'ssid': ssid, 'switch_in': SWITCH_DELAY, 'timeout': CONNECT_TIMEOUT}


# -- Forget / hotspot --

def _switch_later(uuid):
    def worker():
        try:
            time.sleep(SWITCH_DELAY)
            ok, _, err = _activate(uuid, timeout=30)
            logging.info(f'network : switch to {uuid} : {"ok" if ok else err}')
        finally:
            _attempt_lock.release()

    if not _attempt_lock.acquire(blocking=False):
        raise ProvisioningError('busy', 'A connection attempt is already running', 409)
    Thread(target=worker, name='wifi-switch', daemon=True).start()


def start_hotspot():
    """Switch to the hotspot now. The saved networks are kept and used again at the next boot."""
    if not is_supported():
        raise ProvisioningError('not_supported', 'NetworkManager is not available', 501)
    hotspot = _hotspot_profile()
    if not hotspot:
        raise ProvisioningError('no_hotspot', 'No hotspot profile found', 500)
    if _device_state(_wifi_device())['uuid'] == hotspot['uuid']:
        return {'status': 'ok', 'switching': False}
    _switch_later(hotspot['uuid'])
    return {'status': 'ok', 'switching': True, 'switch_in': SWITCH_DELAY}


def forget(ssid):
    """Delete the saved profiles of a network. When it is the active one, go back to the hotspot."""
    if not is_supported():
        raise ProvisioningError('not_supported', 'NetworkManager is not available', 501)
    profiles = _profiles()
    targets = [p for p in _client_profiles(profiles) if p['ssid'] == ssid]
    if not targets:
        raise ProvisioningError('not_found', 'No saved network with this SSID', 404)
    active_uuid = _device_state(_wifi_device())['uuid']
    was_active = any(p['uuid'] == active_uuid for p in targets)
    hotspot = _hotspot_profile(profiles)

    if was_active and hotspot:
        # delete once the hotspot is up, deleting the active profile first would drop the link now
        def worker():
            try:
                time.sleep(SWITCH_DELAY)
                _activate(hotspot['uuid'], timeout=30)
                for p in targets:
                    _run(['nmcli', 'connection', 'delete', 'uuid', p['uuid']])
            finally:
                _attempt_lock.release()

        if not _attempt_lock.acquire(blocking=False):
            raise ProvisioningError('busy', 'A connection attempt is already running', 409)
        Thread(target=worker, name='wifi-forget', daemon=True).start()
        return {'status': 'ok', 'switching': True, 'switch_in': SWITCH_DELAY}

    for p in targets:
        _run(['nmcli', 'connection', 'delete', 'uuid', p['uuid']])
    return {'status': 'ok', 'switching': False}


# -- Background monitor : mDNS announce, return to the home network --

def _set_pdeathsig():
    """Kill the child with the backend, so the announce never outlives it."""
    try:
        ctypes.CDLL('libc.so.6').prctl(1, signal.SIGTERM)  # PR_SET_PDEATHSIG
    except Exception:
        pass


def _start_announce(version):
    if not shutil.which('avahi-publish-service'):
        return None
    ident = device_id()
    try:
        return subprocess.Popen(
            ['avahi-publish-service', f'SunScan {ident}', MDNS_SERVICE_TYPE, str(API_PORT),
             f'id={ident}', f'version={version}'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=_set_pdeathsig)
    except Exception as e:
        logging.warning(f'network : mDNS announce failed : {e}')
        return None


def _try_return_home():
    """
    In hotspot mode with nobody connected, join a saved home network when it is in range again
    (after a reboot of the box, NetworkManager falls back to the hotspot and stays there).
    """
    device = _wifi_device()
    profiles = _profiles()
    hotspot = _hotspot_profile(profiles)
    clients = [p for p in _client_profiles(profiles) if p['ssid']]
    if not hotspot or not clients or _device_state(device)['uuid'] != hotspot['uuid']:
        return
    if _hotspot_has_clients(device):
        return
    networks, _ = _scan_iw(device)
    if not networks:
        return
    visible = {n['ssid'] for n in networks}
    candidates = sorted((p for p in clients if p['ssid'] in visible), key=lambda p: -p['priority'])
    if not candidates or not _attempt_lock.acquire(blocking=False):
        return
    try:
        target = candidates[0]
        logging.info(f'network : saved network "{target["ssid"]}" in range, leaving the hotspot')
        ok, _, err = _activate(target['uuid'])
        if not ok:
            logging.warning(f'network : can not join "{target["ssid"]}" : {err}')
            _activate(hotspot['uuid'], timeout=30)
    finally:
        _attempt_lock.release()


def _monitor(version):
    announce = None
    last_return_home = time.monotonic()
    while True:
        try:
            if announce is None or announce.poll() is not None:
                announce = _start_announce(version)
            if time.monotonic() - last_return_home >= RETURN_HOME_INTERVAL:
                last_return_home = time.monotonic()
                _try_return_home()
        except Exception:
            logging.exception('network : monitor')
        time.sleep(MONITOR_PERIOD)


def _ensure_polkit_rule():
    """
    Install or update the polkit rule. Done at startup so the devices updated with the
    backend zip get it too. polkitd reloads its rules by itself.
    """
    ok, current, _ = _run(['cat', POLKIT_RULE_FILE], as_root=True)
    if ok and current == POLKIT_RULE.strip():
        return
    cmd = ['tee', POLKIT_RULE_FILE] if os.geteuid() == 0 else ['sudo', '-n', 'tee', POLKIT_RULE_FILE]
    try:
        res = subprocess.run(cmd, input=POLKIT_RULE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             universal_newlines=True, timeout=CMD_TIMEOUT)
        ok = res.returncode == 0 and _run(['chmod', '644', POLKIT_RULE_FILE], as_root=True)[0]
    except Exception:
        ok = False
    logging.warning(f'network : polkit rule for NetworkManager {"installed" if ok else "NOT installed, WiFi provisioning will fail"}')


def start_network_monitor(version):
    _load_state()
    if is_supported():
        _ensure_polkit_rule()
    if os.environ.get('SUNSCAN_NO_NETWORK_MONITOR') == '1' or not is_supported():
        return
    Thread(target=_monitor, args=(version,), name='network-monitor', daemon=True).start()
