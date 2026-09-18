"""
Background SER writer.

The capture thread must never wait for the SD card: a single write() can stall
for several seconds, and picamera2 only keeps one frame queued, so any stall
longer than a frame period silently drops frames. This writer decouples both:
the capture thread only enqueues frames, a dedicated thread writes them.
"""
import os
import time
import queue
from threading import Thread, Lock


class SerWriter:
    """
    Writes frames to a Serfile from a dedicated thread.

    - put() never blocks; if the queue is full the frame is counted as dropped.
    - the file is kept open by Serfile.addFrame(), data is fdatasync'ed about once
      per second so writes reach the card continuously instead of in large bursts.
    - finish() asks the thread to drain the queue and close the file, wait() blocks
      until that is done.
    """

    def __init__(self, serfile, max_bytes=110 * 1024 * 1024, sync_interval=1.0):
        """
        :param serfile: Serfile object opened with NEW=True and header already set
        :param max_bytes: RAM budget of the queue. 110 MB is about 200 frames of 2028x130 uint16,
                          i.e. 30 s at 6.67 fps. Bounded in bytes so that large (uncropped) frames
                          cannot exhaust the memory.
        :param sync_interval: seconds between two fdatasync calls
        """
        self._serfile = serfile
        self._queue = queue.Queue()
        self._max_bytes = max_bytes
        self._queued_bytes = 0
        self._bytes_lock = Lock()
        self._shape = None
        self._sync_interval = sync_interval
        self._thread = Thread(target=self._run, name="ser-writer", daemon=True)
        self.written = 0
        self.dropped = 0
        self.max_depth = 0
        self.max_write_s = 0.0
        self.error = None
        self._finishing = False
        self._thread.start()

    def put(self, frame):
        """
        Enqueue a frame (called from the capture thread, never blocks).
        The frame must not be modified by the caller afterwards.

        :return: True if queued, False if the queue was full and the frame was dropped
        """
        if self._finishing or self.error is not None:
            self.dropped += 1
            return False
        if self._shape is None:
            self._shape = frame.shape
        elif frame.shape != self._shape:
            # e.g. crop toggled while recording: a SER file only holds frames of one size
            if self.dropped == 0:
                print(f"SerWriter: frame shape {frame.shape} differs from first frame {self._shape}, dropped")
            self.dropped += 1
            return False
        with self._bytes_lock:
            if self._queued_bytes + frame.nbytes > self._max_bytes:
                self.dropped += 1
                return False
            self._queued_bytes += frame.nbytes
        self._queue.put_nowait(frame)
        depth = self._queue.qsize()
        if depth > self.max_depth:
            self.max_depth = depth
        return True

    def finish(self):
        """Ask the writer to drain the queue then close the file. Does not block."""
        self._finishing = True  # put() now refuses frames; the thread exits once the queue is empty

    def wait(self, timeout=None):
        """Block until the file is fully written and closed. Returns True when done."""
        self._thread.join(timeout)
        return not self._thread.is_alive()

    def is_done(self):
        return not self._thread.is_alive()

    def _sync(self):
        f = getattr(self._serfile, '_write_file', None)
        if f is not None:
            f.flush()
            os.fdatasync(f.fileno())

    def _run(self):
        last_sync = time.monotonic()
        try:
            while True:
                try:
                    frame = self._queue.get(timeout=0.2)
                except queue.Empty:
                    if self._finishing:
                        break
                    continue
                t0 = time.monotonic()
                try:
                    self._serfile.addFrame(frame)
                finally:
                    with self._bytes_lock:
                        self._queued_bytes -= frame.nbytes
                now = time.monotonic()
                if now - last_sync >= self._sync_interval:
                    self._sync()
                    now = time.monotonic()
                    last_sync = now
                self.written += 1
                if now - t0 > self.max_write_s:
                    self.max_write_s = now - t0
        except Exception as e:  # disk full, I/O error...
            self.error = e
            print(f"SerWriter error: {e!r}")
        finally:
            try:
                self._serfile.closeWriteFile()
            except Exception as e:
                self.error = self.error or e
                print(f"SerWriter close error: {e!r}")
