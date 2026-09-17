import threading


DEFAULT_MAX_ACTIVE_SUBMISSIONS = 64


class SubmissionCapacity:
    def __init__(
        self,
        limit: int = DEFAULT_MAX_ACTIVE_SUBMISSIONS,
    ) -> None:
        if limit <= 0:
            raise ValueError(
                "MORI requires positive submission capacity"
            )

        self.limit = limit

        self._active = 0
        self._lock = threading.Lock()

    @property
    def active(self) -> int:
        with self._lock:
            return self._active

    def try_acquire(self) -> bool:
        with self._lock:
            if self._active >= self.limit:
                return False

            self._active += 1

            return True

    def release(self) -> None:
        with self._lock:
            if self._active <= 0:
                raise RuntimeError(
                    "MORI found an impossible submission release"
                )

            self._active -= 1