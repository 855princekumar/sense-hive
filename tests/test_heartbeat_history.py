"""Heartbeat history: every verified heartbeat is kept, breaks are found, charts
get their data for 1 minute to 30 days, CSV export works for one, some or all
nodes, and a node that floods is held back."""
import csv
import io
import time

import pytest
from test_heartbeat import MASTER, TOKEN, api, sealed


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def hist(make_app):
    hive = make_app(HEARTBEAT_MASTER_KEY=MASTER.hex(), HEARTBEAT_API_TOKEN=TOKEN)
    clock = Clock(time.time() - 3000)
    hive.heartbeat_receiver.clock = clock
    return hive, clock


def beat(hive, clock, node='pi-01', kind='hb', session=None):
    t = clock.t
    return hive.heartbeat_receiver.handle(*sealed(node=node, kind=kind, t=t, s=session or t))


def run_node(hive, clock, node='pi-01', seconds=600, every=10, gap_at=None, gap=0):
    session = clock.t
    assert beat(hive, clock, node, 'birth', session)
    elapsed = 0
    while elapsed < seconds:
        step = every + (gap if gap_at is not None and elapsed == gap_at else 0)
        clock.t += step
        elapsed += step
        assert beat(hive, clock, node, 'hb', session)


def rows(text):
    return list(csv.reader(io.StringIO(text)))


def test_every_heartbeat_is_kept_and_breaks_are_found(hist):
    hive, clock = hist
    run_node(hive, clock, seconds=600, gap_at=300, gap=90)
    h = api(hive, '/api/heartbeat/history?node=pi-01&range=1h').get_json()
    assert h['kind'] == 'beats'
    assert h['received'] == len([p for p in h['points'] if p[1] != 2]) >= 50
    assert h['interval'] == 10
    assert len(h['breaks']) == 1 and h['breaks'][0]['seconds'] == 100
    assert h['longest_break'] == 100
    assert 0 < h['uptime'] <= 100


def test_short_ranges_and_long_ranges(hist):
    hive, clock = hist
    run_node(hive, clock, seconds=120)
    one_min = api(hive, '/api/heartbeat/history?node=pi-01&range=1m').get_json()
    assert one_min['kind'] == 'beats' and 5 <= len(one_min['points']) <= 7
    week = api(hive, '/api/heartbeat/history?node=pi-01&range=7d').get_json()
    assert week['kind'] == 'hours' and len(week['points']) >= 7 * 24
    assert sum(p[1] for p in week['points']) >= 2                         # online minutes are counted


def test_a_node_that_floods_is_held_back(hist):
    hive, clock = hist
    run_node(hive, clock, seconds=20)
    before = api(hive, '/api/heartbeat/history?node=pi-01&range=1h').get_json()['received']
    clock.t += 0.5                                     # authentic, but far too soon (a stolen key)
    assert not beat(hive, clock)
    assert hive.heartbeat_receiver.flooded == 1
    assert api(hive, '/api/heartbeat/history?node=pi-01&range=1h').get_json()['received'] == before


def test_csv_export_for_one_some_or_all_nodes(hist):
    hive, clock = hist
    run_node(hive, clock, 'pi-01', seconds=60)
    run_node(hive, clock, 'pi-02', seconds=60)
    run_node(hive, clock, 'gw-03', seconds=60)
    since = int(clock.t - 3600)
    one = api(hive, f'/api/heartbeat/export.csv?nodes=pi-01&what=beats&since={since}')
    assert one.status_code == 200 and one.mimetype == 'text/csv'
    assert 'heartbeats-beats-pi-01-' in one.headers['Content-Disposition']
    data = rows(one.get_data(as_text=True))
    assert data[0] == ['node', 'time_utc', 'unix_time', 'kind', 'delay_ms']
    assert {r[0] for r in data[1:]} == {'pi-01'} and len(data) > 5
    some = rows(api(hive, f'/api/heartbeat/export.csv?nodes=pi-01,gw-03&since={since}').get_data(as_text=True))
    assert {r[0] for r in some[1:]} == {'pi-01', 'gw-03'}
    every = rows(api(hive, f'/api/heartbeat/export.csv?nodes=all&what=minutes&since={since}').get_data(as_text=True))
    assert every[0] == ['node', 'minute_utc', 'unix_time'] and {r[0] for r in every[1:]} == {'pi-01', 'pi-02', 'gw-03'}
    events = rows(api(hive, f'/api/heartbeat/export.csv?what=events&since={since}').get_data(as_text=True))
    assert events[0] == ['node', 'time_utc', 'unix_time', 'status'] and len(events) >= 4


def test_csv_cells_never_become_spreadsheet_formulas(hist):
    hive, clock = hist
    run_node(hive, clock, '=HYPERLINK("http://evil")', seconds=20)
    text = api(hive, '/api/heartbeat/export.csv?nodes=all').get_data(as_text=True)
    assert "'=HYPERLINK" in text and '\n=HYPERLINK' not in text


def test_history_input_is_checked(hist):
    hive, clock = hist
    run_node(hive, clock, seconds=20)
    assert api(hive, '/api/heartbeat/history?node=pi-01&range=1y').status_code == 400
    assert api(hive, '/api/heartbeat/history?node=nobody&range=1h').status_code == 404
    assert api(hive, '/api/heartbeat/export.csv?what=passwords').status_code == 400
    assert api(hive, '/api/heartbeat/export.csv?nodes=nobody').status_code == 404
    assert api(hive, '/api/heartbeat/export.csv?since=nan&until=inf').status_code == 200
    assert api(hive, '/api/heartbeat/history?node=pi-01&range=1h', token=None).status_code == 401
    assert api(hive, '/api/heartbeat/export.csv', token=None).status_code == 401


def test_wrong_tokens_lock_the_address_out(hist):
    hive, _ = hist
    for _ in range(20):
        assert api(hive, '/api/heartbeat/status', token='y' * 40).status_code == 401
    assert api(hive, '/api/heartbeat/status').status_code == 401        # even the right token, for a while


def test_old_heartbeats_are_pruned(hist):
    hive, clock = hist
    run_node(hive, clock, seconds=60)
    rx = hive.heartbeat_receiver
    clock.t += rx.beats_hours * 3600 + 60
    rx.prune()
    with hive.get_db() as conn:
        assert conn.execute('SELECT COUNT(*) FROM hb_beats').fetchone()[0] == 0
