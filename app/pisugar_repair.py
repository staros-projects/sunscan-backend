"""
PiSugar 3 firmware repair : puts the PiSugar back on its application firmware when its
microcontroller is stuck in bootloader mode.

The PiSugar 3 microcontroller (I2C 0x57) runs an application firmware that handles the
button (long press to power off), the battery gauge and the RTC. When that firmware is
missing or corrupted, the microcontroller stays in its bootloader : the battery still
powers the Pi, but the long press does nothing, the voltage reads 0 and pisugar-server
reports a fake 100 % battery.

Register 0x00 holds the PiSugar version (3) and register 0x01 the running mode. This module
reads them, and reflashes the application firmware shipped in app/firmware with the official
pisugar-programmer (installed by pi-gen), the same way as PiSugar's PiSugarUpdate.sh :
pisugar-server stopped during the upgrade and started again afterwards.

Only a PiSugar that is not running its application (bootloader or bootapp mode) is
reflashed, a working PiSugar is never touched.
"""

import hashlib
import logging
import os
import re
import shutil
import subprocess
import time
from threading import Lock, Thread

from power import PowerHelper, PiSugarError

I2C_BUS = 1
I2C_ADDR = 0x57
REG_VERSION = 0x00
REG_MODE = 0x01
PISUGAR_VERSION = 3
MODES = {0x0f: 'application', 0xf0: 'bootloader', 0xba: 'bootapp'}
REPAIRABLE_MODES = ('bootloader', 'bootapp')

# Official firmware, from https://cdn.pisugar.com/release/PiSugar3Firmware/fm33lc023n/pisugar-3-application.bin
# (the SunScan has no internet access in the field). pisugar-programmer wants 'application' in the file name.
FIRMWARE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'firmware', 'pisugar-3-application.bin')
FIRMWARE_VERSION = '1.3.8'
FIRMWARE_SHA256 = 'c1e18e9d4e3c29b7d1c765f4f74edabb76136ec85944482abc98cf2021414c9e'

# pisugar-programmer retries forever on I2C errors, it is killed after this delay
FLASH_TIMEOUT = 300
# Time given to the PiSugar to jump to its application after the upgrade
BOOT_TIMEOUT = 15
# Time given to pisugar-server to answer again after its restart
SERVER_TIMEOUT = 15
CMD_TIMEOUT = 20

_SEG_RE = re.compile(r'Seg offset: (\d+)/(\d+)')

_repair_lock = Lock()
_state_lock = Lock()
_repair = {'state': 'idle', 'percent': 0, 'error': '', 'detail': '',
           'started_at': None, 'finished_at': None}
_last_mode = None


class RepairError(Exception):
    def __init__(self, code, message, http_status=400):
        super().__init__(message)
        self.code = code
        self.http_status = http_status


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


def _i2c_needs_root():
    return not os.access(f'/dev/i2c-{I2C_BUS}', os.R_OK | os.W_OK)


def _read_register(reg):
    """One byte from the PiSugar, None when nothing answers."""
    ok, out, _ = _run(['i2cget', '-y', str(I2C_BUS), hex(I2C_ADDR), hex(reg)], as_root=_i2c_needs_root())
    try:
        return int(out, 16) if ok else None
    except ValueError:
        return None


def _detect():
    """'application', 'bootloader', 'bootapp', 'absent' (nothing on the bus) or 'unknown'."""
    global _last_mode
    version = _read_register(REG_VERSION)
    if version is None:
        mode = 'absent'
    elif version != PISUGAR_VERSION:
        mode = 'unknown'
    else:
        mode = MODES.get(_read_register(REG_MODE), 'unknown')
    _last_mode = mode
    return mode


def _running_firmware_version():
    try:
        out = PowerHelper.send_command_to_pisugar('get firmware_version')
    except PiSugarError:
        return None
    return out.partition(':')[2].strip() or None


def _firmware_ok():
    try:
        with open(FIRMWARE_FILE, 'rb') as f:
            return hashlib.sha256(f.read()).hexdigest() == FIRMWARE_SHA256
    except OSError:
        return False


# -- Status --

def status():
    """
    Mode of the PiSugar microcontroller and last repair. The registers are not read during
    a repair (the programmer owns the bus) : mode is then the one seen before it started.
    """
    with _state_lock:
        repair = dict(_repair)
    mode = _last_mode if repair['state'] == 'running' else _detect()
    return {
        'mode': mode,
        'needs_repair': mode in REPAIRABLE_MODES,
        'firmware_version': _running_firmware_version() if mode == 'application' else None,
        'bundled_firmware_version': FIRMWARE_VERSION,
        'repair': repair,
    }


# -- Repair --

def _set_percent(percent):
    with _state_lock:
        _repair['percent'] = percent


def _finish(state, error='', detail=''):
    with _state_lock:
        _repair.update({'state': state, 'error': error, 'detail': detail,
                        'finished_at': int(time.time())})
        if state == 'success':
            _repair['percent'] = 100
    logging.info(f'pisugar : repair {state} {error} {detail}'.rstrip())


def _flash():
    """Run pisugar-programmer, return (success, detail). Its log goes to stderr."""
    cmd = ['timeout', '-k', '5', str(FLASH_TIMEOUT), 'pisugar-programmer', FIRMWARE_FILE]
    if _i2c_needs_root():
        cmd = ['sudo', '-n'] + cmd
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            universal_newlines=True)
    # The programmer asks for a confirmation before starting
    proc.stdin.write('y\n')
    proc.stdin.close()
    last, finished = '', False
    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue
        last = line
        match = _SEG_RE.search(line)
        if match and int(match[2]):
            _set_percent(int(match[1]) * 100 // int(match[2]))
        if 'Upgrade finished' in line:
            finished = True
    proc.wait()
    if proc.returncode == 124:
        return False, f'timeout after {FLASH_TIMEOUT} s, last output : {last}'
    if proc.returncode != 0 or not finished:
        return False, f'exit code {proc.returncode}, last output : {last}'
    return True, ''


def _wait_application():
    deadline = time.time() + BOOT_TIMEOUT
    while True:
        mode = _detect()
        if mode == 'application' or time.time() > deadline:
            return mode
        time.sleep(0.5)


def _upgrade():
    """Return (state, error, detail)."""
    ok, _, err = _run(['systemctl', 'stop', 'pisugar-server'], as_root=True)
    if not ok:
        return 'failed', 'service_error', f'can not stop pisugar-server : {err}'
    ok, detail = _flash()
    if not ok:
        return 'failed', 'flash_failed', detail
    mode = _wait_application()
    if mode != 'application':
        return 'failed', 'still_in_bootloader', f'PiSugar mode after the upgrade : {mode}'
    return 'success', '', ''


def _restart_server(repaired):
    """
    Start pisugar-server again. After a repair, wait for it to answer and apply again the
    battery input protection that PowerHelper sets at startup : the PiSugar ignored it while
    it was in bootloader.
    """
    ok, _, err = _run(['systemctl', 'start', 'pisugar-server'], as_root=True)
    if not ok:
        logging.warning(f'pisugar : can not start pisugar-server : {err}')
        return
    deadline = time.time() + SERVER_TIMEOUT
    while repaired and time.time() < deadline:
        try:
            PowerHelper.send_command_to_pisugar('set_battery_input_protect true')
            return
        except PiSugarError:
            time.sleep(0.5)


def _repair_worker():
    state, error, detail = 'failed', 'flash_failed', ''
    try:
        state, error, detail = _upgrade()
    except Exception as e:
        detail = str(e)
    finally:
        _restart_server(state == 'success')
        _finish(state, error, detail)
        _repair_lock.release()


def repair():
    """
    Check that the PiSugar needs it and start the firmware upgrade in the background.
    Raises RepairError when the request can not be accepted.
    """
    if not shutil.which('pisugar-programmer'):
        raise RepairError('not_supported', 'pisugar-programmer is not installed', 501)
    if not _repair_lock.acquire(blocking=False):
        raise RepairError('busy', 'A repair is already running', 409)
    try:
        mode = _detect()
        if mode == 'absent':
            raise RepairError('pisugar_not_found', 'No PiSugar 3 answers on the I2C bus', 404)
        if mode == 'application':
            raise RepairError('not_needed', 'The PiSugar firmware is running', 409)
        if mode not in REPAIRABLE_MODES:
            raise RepairError('unknown_mode', 'The PiSugar is in an unknown mode', 409)
        if not _firmware_ok():
            raise RepairError('firmware_missing', f'{FIRMWARE_FILE} is missing or damaged', 500)
    except RepairError:
        _repair_lock.release()
        raise

    with _state_lock:
        _repair.update({'state': 'running', 'percent': 0, 'error': '', 'detail': '',
                        'started_at': int(time.time()), 'finished_at': None})
    logging.info(f'pisugar : repair started, mode {mode}, firmware {FIRMWARE_VERSION}')
    Thread(target=_repair_worker, name='pisugar-repair', daemon=True).start()
    return {'status': 'running', 'firmware_version': FIRMWARE_VERSION, 'timeout': FLASH_TIMEOUT}
