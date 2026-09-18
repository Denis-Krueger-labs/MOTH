"""Track bounded in-process capacity for concurrent flag submissions."""

import threading


DEFAULT_MAX_ACTIVE_SUBMISSIONS = 64


class SubmissionCapacity:
    """Provide a thread-safe upper bound for active flag-submission work."""

    def __init__(
        self,
        limit: int = DEFAULT_MAX_ACTIVE_SUBMISSIONS,
    ) -> None:
        """Create a capacity guard with a strictly positive concurrent-work limit."""
        if limit <= 0:
            raise ValueError(
                "MORI requires positive submission capacity"
            )

        self.limit = limit

        self._active = 0
        self._lock = threading.Lock()

    @property
    def active(self) -> int:
        """Return the number of submission slots that are currently acquired."""
        with self._lock:
            return self._active

    def try_acquire(self) -> bool:
        """Acquire one slot when capacity remains; otherwise return false."""
        with self._lock:
            if self._active >= self.limit:
                return False

            self._active += 1

            return True

    def release(self) -> None:
        """Release one acquired slot and reject unmatched releases."""
        with self._lock:
            if self._active <= 0:
                raise RuntimeError(
                    "MORI found an impossible submission release"
                )

            self._active -= 1
