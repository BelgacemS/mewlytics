import threading

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

# argon2id with the OWASP minimum (19 MiB, 2 passes, 1 lane). The library
# default (RFC 9106 low memory) needs 64 MiB per hash, too much for a pod
# limited to 256 Mi.
_hasher = PasswordHasher(time_cost=2, memory_cost=19 * 1024, parallelism=1)

# Each hash allocates memory_cost. Without a cap, a burst of requests on the
# 40 threads of the threadpool would need about 760 MiB.
_slots = threading.BoundedSemaphore(2)


def hash_password(password: str) -> str:
    with _slots:
        return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    with _slots:
        try:
            return _hasher.verify(password_hash, password)
        except VerifyMismatchError:
            return False
