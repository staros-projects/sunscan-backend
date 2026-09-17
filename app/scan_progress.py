"""
Processing progress of the scans.

The processing threads write the state of each scan here and the WebSocket
connections read it. Only the latest state of a scan is kept, so a slow or
late client never gets a backlog of old percentages, it gets the current state.
"""
import threading
import time
from hashlib import md5

# Seconds a finished state (completed or failed) is kept, so that a client which
# reconnects after the end of a processing still learns how it ended
FINISHED_TTL = 30 * 60


def scan_key(filename):
    """
    Key identifying a scan in the WebSocket channels.

    Args:
        filename (str): Path of the SER file, as sent by the frontend.

    Returns:
        str: md5 of the path, same key as the 'scan_process_<key>' channel.
    """
    return md5(filename.encode()).hexdigest()


class ScanProgress:
    """Thread-safe store of the latest processing state of each scan."""

    def __init__(self):
        self._lock = threading.Lock()
        self._states = {}
        self._seq = 0

    def _set(self, key, **fields):
        # Must be called with the lock held
        state = self._states.get(key)
        if state is None:
            state = self._states[key] = {'key': key, 'status': 'processing', 'percent': 0,
                                         'step': 'starting', 'error': '', 'detail': ''}
        elif all(state[name] == value for name, value in fields.items()):
            # Nothing new, the clients already have this state
            return
        state.update(fields)
        self._seq += 1
        state['seq'] = self._seq
        state['updated'] = time.time()

    def start(self, key):
        """Register a new processing, the state of a previous processing of the same scan is dropped."""
        with self._lock:
            now = time.time()
            for k in [k for k, s in self._states.items()
                      if s['status'] != 'processing' and now - s['updated'] > FINISHED_TTL]:
                del self._states[k]
            self._states.pop(key, None)
            self._set(key, status='processing', percent=0, step='starting', error='', detail='')

    def update(self, key, step, percent):
        """Set the current step and the global percentage of a processing."""
        with self._lock:
            self._set(key, status='processing', step=step, percent=int(percent))

    def finish(self, key, status, error='', detail=''):
        """
        Set the final state of a processing.

        Args:
            key (str): Key of the scan.
            status (str): 'completed' or 'failed'.
            error (str): Error key for the frontend, empty when completed.
            detail (str): Raw error message, for debugging only.
        """
        # The detail must stay on one line and must not contain the field separator
        detail = ' '.join(str(detail).replace(';#;', ' ').split())[:200]
        with self._lock:
            if status == 'completed':
                self._set(key, status=status, percent=100, step='done', error='', detail='')
            else:
                self._set(key, status=status, error=error, detail=detail)

    def get(self, key):
        """Return a copy of the state of a scan, or None if nothing is known about it."""
        with self._lock:
            state = self._states.get(key)
            return dict(state) if state else None

    def changes_since(self, seq):
        """Return copies of the states modified after the sequence number seq, oldest first."""
        with self._lock:
            states = [dict(s) for s in self._states.values() if s['seq'] > seq]
        return sorted(states, key=lambda s: s['seq'])

    @staticmethod
    def to_message(state):
        """Format a state as a WebSocket message: scan_progress_<key>;#;status;#;percent;#;step;#;error;#;detail"""
        return ';#;'.join(['scan_progress_' + state['key'], state['status'], str(state['percent']),
                           state['step'], state['error'], state['detail']])
