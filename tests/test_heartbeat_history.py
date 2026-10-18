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


def history(hive, rng='1h', node='pi-01'):
    return api(hive, f'/api/heartbeat/history?node={node}&range={rng}').get_json()


def test_an_offline_node_shows_its_break_even_when_it_began_before_the_range(hist):
    hive, clock = hist
    run_node(hive, clock, seconds=120)
    last = clock.t
    clock.t += 40
    assert beat(hive, clock, kind='lwt', session=last - 120)       # the broker publishes the last will
    clock.t += 2 * 3600                                            # two hours later, viewed over 1 hour
    h = history(hive, '1h')
    assert h['received'] == 0
    assert len(h['breaks']) == 1
    b = h['breaks'][0]
    assert b['to'] is None and b['from'] == pytest.approx(last) and b['from'] < h['since']
    assert b['status'] == 'offline' and b['lwt_at'] == pytest.approx(last + 40)
    assert b['seconds'] == pytest.approx(2 * 3600 + 40, abs=1) == h['longest_break']
    assert h['current_break'] == b
    week = history(hive, '7d')                                     # hourly view: the outage is reported too
    assert week['kind'] == 'hours' and week['current_break']['from'] == pytest.approx(last)


def test_a_break_is_found_with_a_single_heartbeat_in_the_range(hist):
    hive, clock = hist
    run_node(hive, clock, seconds=0)                               # one birth message, then nothing
    clock.t += 300
    h = history(hive, '1h')
    assert h['interval'] is None and h['received'] == 1
    assert len(h['breaks']) == 1 and h['breaks'][0]['status'] == 'silent' and h['breaks'][0]['seconds'] == 300


def test_heartbeats_no_longer_kept_still_give_the_ongoing_break(hist):
    hive, clock = hist
    run_node(hive, clock, seconds=60)
    last = clock.t
    with hive.heartbeat_receiver.db() as conn:                    # as before heartbeat history existed
        conn.execute('DELETE FROM hb_beats')
        conn.commit()
    clock.t += 600
    h = history(hive, '1h')
    assert h['points'] == [] and h['breaks'][0]['from'] == pytest.approx(last)
    assert h['breaks'][0]['status'] == 'silent'


def test_a_last_will_inside_an_outage_does_not_split_it(hist):
    hive, clock = hist
    run_node(hive, clock, seconds=60)
    session, last = clock.t - 60, clock.t
    clock.t += 30
    assert beat(hive, clock, kind='lwt', session=session)
    clock.t += 200
    run_node(hive, clock, seconds=30)                              # back with a new session
    h = history(hive, '1h')
    assert len(h['breaks']) == 1
    b = h['breaks'][0]
    assert b['from'] == pytest.approx(last) and b['seconds'] == pytest.approx(230, abs=0.5)
    assert b['lwt_at'] == pytest.approx(last + 30)
    assert h['current_break'] is None


def test_an_online_node_has_no_current_break(hist):
    hive, clock = hist
    run_node(hive, clock, seconds=60)
    clock.t += 5
    assert history(hive, '1h')['current_break'] is None
    assert history(hive, '30d')['current_break'] is None


# ---------------------------------------------------------------- recycle bin (1.7)

def bin_call(hive, action, names, **kw):
    c = hive.app.test_client()
    c.post('/api/login', json={'username': 'admin', 'password': 'admin123'})
    return c.post('/api/heartbeat/bin', json={'action': action, 'names': names, **kw})


def test_a_binned_node_is_hidden_checked_but_not_stored_and_can_come_back(hist):
    hive, clock = hist
    run_node(hive, clock, 'dead-pi', seconds=60)
    run_node(hive, clock, 'live-pi', seconds=60)
    assert bin_call(hive, 'bin', ['dead-pi']).get_json()['changed'] == 1
    names = [n['name'] for n in api(hive, '/api/heartbeat/nodes').get_json()['nodes']]
    assert names == ['live-pi']                                   # hidden from the token API (EdgeShell) too
    c = hive.app.test_client()
    c.post('/api/login', json={'username': 'admin', 'password': 'admin123'})
    binned = c.get('/api/heartbeat/bin').get_json()
    assert [b['name'] for b in binned['nodes']] == ['dead-pi'] and binned['nodes'][0]['days_left'] == 30
    assert binned['nodes'][0]['came_back_at'] is None
    with hive.get_db() as conn:
        before = conn.execute('SELECT COUNT(*) FROM hb_beats').fetchone()[0]
    session = clock.t - 60
    clock.t += 10
    assert beat(hive, clock, 'dead-pi', 'hb', session)            # it is alive after all
    with hive.get_db() as conn:
        assert conn.execute('SELECT COUNT(*) FROM hb_beats').fetchone()[0] == before   # nothing stored
    assert c.get('/api/heartbeat/bin').get_json()['nodes'][0]['came_back_at']        # "came back"
    assert bin_call(hive, 'restore', ['dead-pi']).get_json()['changed'] == 1
    assert {n['name'] for n in api(hive, '/api/heartbeat/nodes').get_json()['nodes']} == {'dead-pi', 'live-pi'}


def test_delete_forever_only_from_the_bin_and_the_bin_empties_itself(hist):
    hive, clock = hist
    run_node(hive, clock, 'gone-pi', seconds=60)
    run_node(hive, clock, 'old-pi', seconds=60)
    assert bin_call(hive, 'delete', ['gone-pi']).get_json()['changed'] == 0      # not in the bin: kept
    bin_call(hive, 'bin', ['gone-pi', 'old-pi'])
    assert bin_call(hive, 'delete', ['gone-pi']).get_json()['changed'] == 1
    with hive.get_db() as conn:
        assert not conn.execute("SELECT 1 FROM hb_minutes WHERE name = 'gone-pi'").fetchone()
        assert not conn.execute("SELECT 1 FROM hb_events WHERE name = 'gone-pi'").fetchone()
        assert not conn.execute("SELECT 1 FROM hb_nodes WHERE name = 'gone-pi'").fetchone()
    clock.t += 31 * 86400                                          # 30 days in the bin
    hive.heartbeat_receiver.prune()
    with hive.get_db() as conn:
        assert not conn.execute("SELECT 1 FROM hb_nodes WHERE name = 'old-pi'").fetchone()


def test_the_bin_needs_a_sign_in_and_checks_its_input(hist):
    hive, clock = hist
    run_node(hive, clock, 'pi', seconds=20)
    c = hive.app.test_client()
    assert c.get('/api/heartbeat/bin', headers={'Authorization': 'Bearer ' + TOKEN}).status_code == 401
    assert c.post('/api/heartbeat/bin', json={'action': 'bin', 'names': ['pi']}).status_code in (401, 403)
    for body in ({'action': 'bin', 'names': 'pi'}, {'action': 'bin', 'names': []}, {'action': 'burn', 'names': ['pi']},
                 {'action': 'bin', 'names': [1]}, {'action': 'bin', 'names': ['x' * 300]}):
        r = bin_call(hive, body['action'], body['names'])
        assert r.status_code == 400, body
