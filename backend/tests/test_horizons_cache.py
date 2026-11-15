from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import io
import json
from threading import Lock
import time

import pytest
from app.data import horizons_cache as cache
from fastapi.testclient import TestClient
from app.main import create_app

PARAMS = {'COMMAND': '399', 'TLIST': '2461359.5', 'CENTER': '500@0'}
PAYLOAD = {'result': '$$SOE\n2461359.5,date,1,2,3,4,5,6\n$$EOE'}


@pytest.fixture(autouse=True)
def isolated_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, 'CACHE_PATH', tmp_path / 'horizons.sqlite3')


def test_concurrent_identical_requests_download_once(monkeypatch):
    calls = []
    def download(*args, **kwargs):
        calls.append(1)
        time.sleep(.03)
        return io.StringIO(json.dumps(PAYLOAD))
    monkeypatch.setattr(cache, 'urlopen', download)
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _: cache.load_payload(PARAMS), range(6)))
    assert results == [PAYLOAD] * 6
    assert len(calls) == 1
    monkeypatch.setattr(cache, 'urlopen', lambda *a, **kw: pytest.fail('disk cache must survive without network'))
    assert cache.load_payload(PARAMS) == PAYLOAD


def test_distinct_queries_never_overlap_at_nasa(monkeypatch):
    lock = Lock()
    active = 0
    maximum = 0
    def download(*args, **kwargs):
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
        time.sleep(.02)
        with lock: active -= 1
        return io.StringIO(json.dumps(PAYLOAD))
    monkeypatch.setattr(cache, 'urlopen', download)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda code: cache.load_payload({**PARAMS, 'COMMAND': str(code)}), range(4)))
    assert maximum == 1


def test_failed_response_is_not_cached(monkeypatch):
    monkeypatch.setattr(cache, 'urlopen', lambda *a, **kw: io.StringIO('{"error":"unavailable"}'))
    with pytest.raises(ValueError): cache.load_payload(PARAMS)
    monkeypatch.setattr(cache, 'urlopen', lambda *a, **kw: io.StringIO(json.dumps(PAYLOAD)))
    assert cache.load_payload(PARAMS) == PAYLOAD


def test_stream_tables_have_utc_day_and_all_bodies(monkeypatch):
    calls = []
    def table(body, start, stop, intervals, center):
        calls.append((body.id, start, stop, intervals, center))
        return list(range(0, 86401, 3600)), [[1,2,3]]*25, [[4,5,6]]*25
    monkeypatch.setattr('app.data.ephemeris.get_body_state_table', table)
    response = TestClient(create_app()).get('/ephemeris/solar-day', params={'date':'2026-11-15T01:00:00+02:00'})
    rows = [json.loads(line) for line in response.text.splitlines()]
    assert response.status_code == 200
    assert len(rows) == len(calls) == 10
    assert rows[0]['body_id'] == 'sun'
    assert all(c[1] == datetime(2026,11,14,tzinfo=timezone.utc) for c in calls)
    assert all(c[3:] == (24,'500@0') for c in calls)


def test_stream_stops_on_nasa_error(monkeypatch):
    from app.data.ephemeris import EphemerisError
    def fail(*args, **kwargs): raise EphemerisError('NASA unavailable')
    monkeypatch.setattr('app.data.ephemeris.get_body_state_table', fail)
    response = TestClient(create_app()).get('/ephemeris/solar-day', params={'date':'2026-11-15T00:00:00Z'})
    assert [json.loads(line) for line in response.text.splitlines()] == [{'error':'NASA unavailable'}]
