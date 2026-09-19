"""
Processing progress of the scans.

The processing threads write the state of each scan here and the WebSocket
connections read it. Only the latest state of a scan is kept, so a slow or
late client never gets a backlog of old percentages, it gets the current state.

The same store follows the other long tasks tied to a scan (upload to SpectroSolHub),
each one on its own WebSocket channel and with its own additional fields.
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

    def __init__(self, channel='scan_progress_', extra=None):
        """
        Args:
            channel (str): Prefix of the WebSocket channel, followed by the key of the scan.
            extra (dict): Additional fields of the states and their initial values. They are
                sent at the end of the message, in this order.
        """
        self._lock = threading.Lock()
        self._states = {}
        self._seq = 0
        self._channel = channel
        self._extra = dict(extra or {})

    def _set(self, key, **fields):
        # Must be called with the lock held
        state = self._states.get(key)
        if state is None:
            state = self._states[key] = {'key': key, 'status': 'processing', 'percent': 0,
                                         'step': 'starting', 'error': '', 'detail': '', **self._extra}
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

    def update(self, key, step, percent, **extra):
        """Set the current step and the global percentage of a processing, and additional fields if any."""
        with self._lock:
            self._set(key, status='processing', step=step, percent=int(percent), **extra)

    def finish(self, key, status, error='', detail='', **extra):
        """
        Set the final state of a processing.

        Args:
            key (str): Key of the scan.
            status (str): 'completed' or 'failed'.
            error (str): Error key for the frontend, empty when completed.
            detail (str): Raw error message, for debugging only.
            extra: Additional fields to set with the final state.
        """
        # The detail must stay on one line and must not contain the field separator
        detail = ' '.join(str(detail).replace(';#;', ' ').split())[:200]
        with self._lock:
            if status == 'completed':
                self._set(key, status=status, percent=100, step='done', error='', detail='', **extra)
            else:
                self._set(key, status=status, error=error, detail=detail, **extra)

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

    def to_message(self, state):
        """
        Format a state as a WebSocket message: <channel><key>;#;status;#;percent;#;step;#;error;#;detail
        followed by the additional fields of the store.
        """
        fields = [self._channel + state['key'], state['status'], str(state['percent']),
                  state['step'], state['error'], state['detail']]
        fields += [str(state[name]).replace(';#;', ' ') for name in self._extra]
        return ';#;'.join(fields)
