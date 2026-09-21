"""
Linux desktop on demand : the Pi boots without its graphical session, the app starts it
when somebody needs it.

The SunScan is driven from the phone, nothing uses the desktop in the field : the display
manager, the compositor, the panel and the file manager only take memory (about 70 MB
measured on Bookworm / labwc) and some CPU. The desktop is only useful to develop on the
Pi itself.

Off by default : each time the backend starts, apply_default() sets the systemd default
target to multi-user.target, so the desktop is not started at the next boots. This also
covers the devices updated in the field, where only the application files change. A
desktop that is running is left alone : the backend restarts much more often than the Pi
(code change, crash), stopping the session there would close the editor of whoever is
developing on the Pi.

switch() starts or stops the desktop for the current boot, and can ask to keep it at
boot : that choice is a flag file, which apply_default() respects. A default target set by
hand (systemctl, raspi-config) without the flag is reverted at the next backend start.

Stopping the display manager ends the graphical session and every application opened in
it : unsaved work is lost. The backend is a system service, it is not affected.

Goes through the display-manager.service alias, so it does not depend on the display
manager in use. On an image without a desktop (Lite) every call reports 'supported': False.
"""

import logging
import os
import shutil
import subprocess

DISPLAY_MANAGER = 'display-manager.service'
TARGET_DESKTOP = 'graphical.target'
TARGET_CONSOLE = 'multi-user.target'

# Present when the desktop was asked to start at boot. Outside the application folder :
# it is a choice made on this device, an update must not overwrite it
AT_BOOT_FLAG = os.path.expanduser('~/.config/sunscan/desktop_at_boot')

# Stopping waits for the applications of the session to end
CMD_TIMEOUT = 45


class DesktopError(Exception):
    def __init__(self, code, detail='', http_status=500):
        super().__init__(detail or code)
        self.code = code
        self.http_status = http_status


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


def is_supported():
    """True when systemd knows a display manager."""
    if not shutil.which('systemctl'):
        return False
    _, out, _ = _run(['systemctl', 'show', '-p', 'LoadState', '--value', DISPLAY_MANAGER])
    return out == 'loaded'


def _boot_target():
    _, target, _ = _run(['systemctl', 'get-default'])
    return target


def status():
    """
    State of the desktop :
    - running : the display manager is up (or starting)
    - state : systemd state of the display manager (active, inactive, activating, deactivating, failed)
    - at_boot : the desktop starts with the Pi
    """
    if not is_supported():
        return {'supported': False, 'running': False, 'state': 'unsupported', 'at_boot': False}
    # is-active exits with a non zero code when the unit is not active, the state is still printed
    _, state, _ = _run(['systemctl', 'is-active', DISPLAY_MANAGER])
    return {
        'supported': True,
        'running': state in ('active', 'activating', 'reloading'),
        'state': state or 'unknown',
        'at_boot': _boot_target() == TARGET_DESKTOP,
    }


def _set_at_boot(at_boot):
    # The flag is written before the desktop target and removed after it : if a step fails, the
    # desktop target is never left without its flag, apply_default() would silently undo the choice
    if at_boot:
        os.makedirs(os.path.dirname(AT_BOOT_FLAG), exist_ok=True)
        open(AT_BOOT_FLAG, 'w').close()
    ok, _, err = _run(['systemctl', 'set-default', TARGET_DESKTOP if at_boot else TARGET_CONSOLE], as_root=True)
    if not ok:
        raise DesktopError('set_default_failed', err)
    if not at_boot and os.path.exists(AT_BOOT_FLAG):
        os.remove(AT_BOOT_FLAG)


def switch(running=None, at_boot=None):
    """
    Start or stop the desktop (running) and / or choose whether it starts with the Pi (at_boot),
    None leaves that part as it is. Returns the new status. The boot choice is saved first, so
    it is kept even when stopping the desktop ends the caller.
    """
    if not is_supported():
        raise DesktopError('unsupported', 'no display manager on this system', 501)
    if at_boot is not None:
        try:
            _set_at_boot(at_boot)
        except OSError as e:
            raise DesktopError('set_default_failed', str(e))
    if running is not None:
        ok, _, err = _run(['systemctl', 'start' if running else 'stop', DISPLAY_MANAGER], as_root=True)
        if not ok:
            raise DesktopError('start_failed' if running else 'stop_failed', err)
    return status()


def apply_default():
    """
    Called when the backend starts : make the Pi boot without the desktop, unless it was asked
    to stay at boot. Only the next boots change, a running desktop is not stopped. Never raises.
    """
    try:
        if os.path.exists(AT_BOOT_FLAG) or not is_supported() or _boot_target() != TARGET_DESKTOP:
            return
        ok, _, err = _run(['systemctl', 'set-default', TARGET_CONSOLE], as_root=True)
        logging.info(f'desktop : off at the next boots : {"ok" if ok else "failed : " + err}')
    except Exception as e:
        logging.info(f'desktop : default not applied : {e}')
