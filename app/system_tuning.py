"""
Best-effort system tuning applied when the backend starts.

- raise the CPU and I/O priority of the backend so the capture and SER writer threads
  win against any other activity on the Pi
- turn off WiFi power saving, which adds latency and jitter on the preview WebSocket
- disable the periodic maintenance timers (apt, man-db) that can saturate the SD card during a scan
- restrict the SunScan hotspot to WPA2 / CCMP without PMF : the default NetworkManager
  profile advertises a WPA1+WPA2 / TKIP+CCMP mixed mode that some phones (Xiaomi) can not join

Everything here must work on every Raspberry Pi OS release the SunScan runs on
(dhcpcd + wpa_supplicant on Buster/Bullseye, NetworkManager on Bookworm and later),
so each step only relies on tools that may be missing and never raises : a failure is
logged and the backend starts normally.

Set SUNSCAN_NO_TUNING=1 to skip everything.
"""

import logging
import os
import shutil
import subprocess
import sys
import time
from threading import Thread

BACKEND_NICE = -10
BACKEND_IONICE_LEVEL = 0  # best-effort class, highest level

# NetworkManager value for 802-11-wireless.powersave : 2 = disable
NM_POWERSAVE_DISABLE = '2'

# NetworkManager may bring the WiFi up (and restore power saving) after the backend has started,
# so the state is checked again at these delays (seconds since startup)
WIFI_CHECK_DELAYS = (0, 5, 15, 30, 60, 120, 300)

# Hotspot security accepted by every phone : WPA2 only (rsn), CCMP only, PMF disabled
# (brcmfmac handles PMF badly in AP mode). Values as printed by 'nmcli -g', pmf 1 = disable
HOTSPOT_SECURITY = {
    '802-11-wireless-security.proto': 'rsn',
    '802-11-wireless-security.pairwise': 'ccmp',
    '802-11-wireless-security.group': 'ccmp',
    '802-11-wireless-security.pmf': '1',
}

MAINTENANCE_TIMERS = ('apt-daily.timer', 'apt-daily-upgrade.timer', 'man-db.timer')

CMD_TIMEOUT = 10


def _run(cmd, as_root=False):
    """
    Run a command and return (success, stdout). Never raises.
    as_root uses non-interactive sudo, so a missing sudoers rule fails instead of blocking on a prompt.
    """
    if as_root and os.geteuid() != 0:
        if not shutil.which('sudo'):
            return False, ''
        cmd = ['sudo', '-n'] + cmd
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             timeout=CMD_TIMEOUT, universal_newlines=True)
        return res.returncode == 0, res.stdout.strip()
    except Exception as e:
        logging.debug(f'system tuning : {cmd[0]} failed : {e}')
        return False, ''


# -- Process priority --

def raise_backend_priority():
    """
    Nice and I/O priority are per thread on Linux and inherited at thread creation :
    applied to every existing thread now, the threads started later (capture, SER writer,
    threadpool) get them for free. So this must run before the camera is started.
    """
    try:
        tids = [int(t) for t in os.listdir('/proc/self/task')]
    except OSError:
        tids = [os.getpid()]

    try:
        # works directly when running as root or with CAP_SYS_NICE
        for tid in tids:
            os.setpriority(os.PRIO_PROCESS, tid, BACKEND_NICE)
        ok = True
    except OSError:
        ok = False
        if shutil.which('renice'):
            ok, _ = _run(['renice', '-n', str(BACKEND_NICE), '-p'] + [str(t) for t in tids], as_root=True)
    logging.info(f'system tuning : backend nice {BACKEND_NICE} : {"ok" if ok else "not applied"}')

    if shutil.which('ionice'):
        ok, _ = _run(['ionice', '-c', '2', '-n', str(BACKEND_IONICE_LEVEL), '-p'] + [str(t) for t in tids], as_root=True)
        logging.info(f'system tuning : backend I/O priority : {"ok" if ok else "not applied"}')


# -- WiFi power saving --

def _wifi_interfaces():
    try:
        return [i for i in os.listdir('/sys/class/net')
                if os.path.isdir(f'/sys/class/net/{i}/wireless') or os.path.exists(f'/sys/class/net/{i}/phy80211')]
    except OSError:
        return []


def _wifi_power_save_is_on(iface):
    """True / False, or None when the state can not be read."""
    if shutil.which('iw'):
        ok, out = _run(['iw', 'dev', iface, 'get', 'power_save'])
        if ok and 'power save' in out.lower():
            return out.lower().rstrip().endswith('on')
    if shutil.which('iwconfig'):
        ok, out = _run(['iwconfig', iface])
        if ok and 'Power Management' in out:
            return 'Power Management:on' in out
    return None


def _wifi_power_save_off(iface):
    """Immediate, does not drop the link, lost at the next reboot or interface reset."""
    if shutil.which('iw'):
        ok, _ = _run(['iw', 'dev', iface, 'set', 'power_save', 'off'], as_root=True)
        if ok:
            return True
    if shutil.which('iwconfig'):
        ok, _ = _run(['iwconfig', iface, 'power', 'off'], as_root=True)
        return ok
    return False


def _nm_persist_power_save_off():
    """
    With NetworkManager, also store the setting in the active WiFi profiles so it survives
    reconnections. 'connection modify' does not reactivate the connection, the link stays up.
    No-op on systems without NetworkManager (dhcpcd based releases).
    """
    if not shutil.which('nmcli'):
        return
    ok, out = _run(['nmcli', '-t', '-f', 'UUID,TYPE', 'connection', 'show', '--active'])
    if not ok:
        return  # NetworkManager installed but not running
    for line in out.splitlines():
        uuid, _, ctype = line.partition(':')
        if 'wireless' not in ctype:
            continue
        ok, current = _run(['nmcli', '-g', '802-11-wireless.powersave', 'connection', 'show', uuid])
        # older nmcli print the value as "2 (disable)" or "disable"
        if ok and (current.startswith(NM_POWERSAVE_DISABLE) or 'disable' in current):
            continue
        ok, _ = _run(['nmcli', 'connection', 'modify', uuid, '802-11-wireless.powersave', NM_POWERSAVE_DISABLE], as_root=True)
        logging.info(f'system tuning : WiFi power save disabled in NetworkManager profile {uuid} : {"ok" if ok else "failed"}')


def disable_wifi_power_save():
    for iface in _wifi_interfaces():
        if _wifi_power_save_is_on(iface) is False:
            continue
        ok = _wifi_power_save_off(iface)
        logging.info(f'system tuning : WiFi power save off on {iface} : {"ok" if ok else "failed"}')
    _nm_persist_power_save_off()


# -- Hotspot security --

def _hotspot_has_clients(device):
    if not device or not shutil.which('iw'):
        return True  # unknown, assume yes so nobody gets disconnected
    ok, out = _run(['iw', 'dev', device, 'station', 'dump'], as_root=True)
    return not ok or 'Station' in out


def fix_hotspot_security():
    """
    Rewrite the WPA-PSK access point profiles of NetworkManager with HOTSPOT_SECURITY.
    The new settings are used at the next activation : the hotspot is restarted right away
    only when no phone is connected to it, otherwise the change waits for the next boot.
    No-op without NetworkManager (older releases), on open hotspots and once already applied.
    """
    if not shutil.which('nmcli'):
        return
    ok, out = _run(['nmcli', '-t', '-f', 'UUID,TYPE,DEVICE', 'connection', 'show'])
    if not ok:
        return
    fields = ['802-11-wireless.mode', '802-11-wireless-security.key-mgmt'] + list(HOTSPOT_SECURITY)
    for line in out.splitlines():
        uuid, ctype, device = (line.split(':') + ['', ''])[:3]
        if 'wireless' not in ctype:
            continue
        ok, values = _run(['nmcli', '-g', ','.join(fields), 'connection', 'show', uuid], as_root=True)
        values = values.split('\n') if ok else []
        if len(values) != len(fields) or values[0] != 'ap' or values[1] != 'wpa-psk':
            continue
        current = dict(zip(fields[2:], values[2:]))
        if all(current[k] == v for k, v in HOTSPOT_SECURITY.items()):
            continue
        args = []
        for key, value in HOTSPOT_SECURITY.items():
            args += [key, 'disable' if key.endswith('.pmf') else value]
        ok, _ = _run(['nmcli', 'connection', 'modify', uuid] + args, as_root=True)
        logging.info(f'system tuning : hotspot {uuid} set to WPA2/CCMP without PMF : {"ok" if ok else "failed"}')
        if not ok or not device:
            continue  # not active : the new settings apply when NetworkManager brings it up
        if _hotspot_has_clients(device):
            logging.info('system tuning : hotspot in use, new security settings apply at next boot')
            continue
        ok, _ = _run(['nmcli', '--wait', '0', 'connection', 'up', uuid], as_root=True)
        logging.info(f'system tuning : hotspot restarted : {"ok" if ok else "failed"}')


# -- Maintenance timers --

def disable_maintenance_timers():
    """
    Only the timers are stopped, never the services : killing a running unattended upgrade
    could leave dpkg in a broken state.
    """
    if not shutil.which('systemctl'):
        return
    for timer in MAINTENANCE_TIMERS:
        _, enabled = _run(['systemctl', 'is-enabled', timer])
        _, active = _run(['systemctl', 'is-active', timer])
        if enabled != 'enabled' and active != 'active':
            continue  # already disabled, or not installed on this release
        ok, _ = _run(['systemctl', 'disable', '--now', timer], as_root=True)
        logging.info(f'system tuning : {timer} disabled : {"ok" if ok else "failed"}')


def _background_tuning():
    try:
        disable_maintenance_timers()
    except Exception as e:
        logging.warning(f'system tuning : timers : {e}')

    try:
        fix_hotspot_security()
    except Exception as e:
        logging.warning(f'system tuning : hotspot : {e}')

    start = time.monotonic()
    for delay in WIFI_CHECK_DELAYS:
        time.sleep(max(0, delay - (time.monotonic() - start)))
        try:
            disable_wifi_power_save()
        except Exception as e:
            logging.warning(f'system tuning : wifi : {e}')


def apply_system_tuning():
    """Call once, as early as possible in the backend startup. Never raises."""
    if not sys.platform.startswith('linux') or os.environ.get('SUNSCAN_NO_TUNING') == '1':
        return
    try:
        raise_backend_priority()
    except Exception as e:
        logging.warning(f'system tuning : priority : {e}')
    # the rest waits on the network and systemd, keep it out of the startup path
    Thread(target=_background_tuning, name='system-tuning', daemon=True).start()
