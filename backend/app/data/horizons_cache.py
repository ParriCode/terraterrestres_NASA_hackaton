"""Persistent cache and single-flight access to JPL's public vector API."""
from contextlib import contextmanager
import csv
import errno
import hashlib
import io
import json
import math
import os
from pathlib import Path
import sqlite3
from threading import Lock
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

# Cross-process file locking: fcntl is unavailable on Windows.
if os.name == 'nt':
    import msvcrt
else:
    import fcntl

from app.config.bodies import HORIZONS_API_URL, HORIZONS_TIMEOUT_S

CACHE_PATH = Path(os.getenv('ORBITAL_HORIZONS_CACHE', str(Path(__file__).parents[2] / '.cache/horizons.sqlite3')))
TTL_S = 7 * 86400
_lock = Lock()


@contextmanager
def _connect():
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(CACHE_PATH, timeout=30)
    db.execute('CREATE TABLE IF NOT EXISTS responses (key TEXT PRIMARY KEY, created REAL, payload TEXT)')
    try:
        with db:
            yield db
    finally:
        db.close()


def _read(key):
    with _connect() as db:
        row = db.execute('SELECT payload FROM responses WHERE key=? AND created>?', (key, time.time()-TTL_S)).fetchone()
    if row:
        try:
            return json.loads(row[0])
        except ValueError:
            return None
    return None


def _write(key, payload):
    with _connect() as db:
        db.execute('INSERT OR REPLACE INTO responses VALUES (?, ?, ?)', (key, time.time(), json.dumps(payload)))
        db.execute('DELETE FROM responses WHERE created<?', (time.time()-TTL_S,))
        db.execute('DELETE FROM responses WHERE key NOT IN (SELECT key FROM responses ORDER BY created DESC LIMIT 64)')


@contextmanager
def _one_request():
    # Threads and multiple server processes share the same limit.
    with _lock:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        # Use a dedicated file so concurrent processes also serialize JPL requests.
        # Windows msvcrt.locking() locks bytes, so the file must contain one byte.
        with CACHE_PATH.with_suffix('.lock').open('a+b') as lockfile:
            if os.name == 'nt':
                lockfile.seek(0, os.SEEK_END)
                if lockfile.tell() == 0:
                    lockfile.write(b'\0')
                    lockfile.flush()
                lockfile.seek(0)
                # LK_LOCK only retries briefly. Keep trying while a slow NASA
                # request holds the lock, without hiding unrelated I/O errors.
                while True:
                    try:
                        msvcrt.locking(lockfile.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError as exc:
                        if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                            raise
                        time.sleep(0.1)
            else:
                fcntl.flock(lockfile.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if os.name == 'nt':
                    lockfile.seek(0)
                    msvcrt.locking(lockfile.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lockfile.fileno(), fcntl.LOCK_UN)


def load_payload(params):
    key = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()
    cached = _read(key)
    if cached is not None:
        return cached
    with _one_request():
        cached = _read(key)
        if cached is not None:
            return cached
        request = Request(f'{HORIZONS_API_URL}?{urlencode(params)}', headers={
            'User-Agent': 'ORBITAL4B/0.1 (+https://github.com/ParriCode/terraterrestres_NASA_hackaton)',
        })
        with urlopen(request, timeout=HORIZONS_TIMEOUT_S) as response:
            payload = json.load(response)
        # Never persist errors, incomplete tables or malformed numeric data.
        if not isinstance(payload, dict) or payload.get('error'):
            raise ValueError(payload.get('error', 'Respuesta NASA inválida') if isinstance(payload, dict) else 'Respuesta NASA inválida')
        try:
            table = payload['result'].split('$$SOE', 1)[1].split('$$EOE', 1)[0].strip()
            rows = list(csv.reader(io.StringIO(table)))
            expected = int(params['STEP_SIZE']) + 1 if 'STEP_SIZE' in params else 1
            if len(rows) != expected:
                raise ValueError('Tabla NASA incompleta')
            for row in rows:
                values = [float(v.replace('D', 'E')) for v in row[2:8]]
                if len(values) != 6 or not all(math.isfinite(v) for v in values):
                    raise ValueError('Estado NASA inválido')
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError('Tabla NASA inválida') from exc
        _write(key, payload)
        return payload
