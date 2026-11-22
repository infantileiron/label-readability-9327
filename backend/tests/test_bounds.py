"""Property tests for paper-total reconciliation and exact p-value bounds."""
import itertools
import random
from math import comb

from src.services.bounds import advance, reconcile
from src.services.statistics import exact_mcnemar


def p_value(b, c):
    m = b + c
    if not m:
        return 1.0
    return min(1.0, 2 * sum(comb(m, i) for i in range(min(b, c) + 1)) / (1 << m))


def brute(rows, old_paper, new_paper):
    """Enumerate every boolean completion reproducing both paper totals."""
    open_rows = [i for i, row in enumerate(rows) if row['old_ok'] is None or row['new_ok'] is None]
    results = set()
    for combo in itertools.product([(False, False), (False, True), (True, False), (True, True)],
                                   repeat=len(open_rows)):
        full = [dict(row) for row in rows]
        for index, value in zip(open_rows, combo):
            full[index]['old_ok'], full[index]['new_ok'] = value
        if any(rows[i]['old_ok'] is not None and full[i]['old_ok'] != rows[i]['old_ok'] for i in open_rows):
            continue
        if any(rows[i]['new_ok'] is not None and full[i]['new_ok'] != rows[i]['new_ok'] for i in open_rows):
            continue
        if sum(1 for row in full if row['old_ok']) != old_paper:
            continue
        if sum(1 for row in full if row['new_ok']) != new_paper:
            continue
        b = sum(1 for row in full if row['old_ok'] and not row['new_ok'])
        c = sum(1 for row in full if row['new_ok'] and not row['old_ok'])
        results.add((b, c))
    return results


def make(rows, order):
    return [{'visitor_code': f'{order}-{i}', 'reading_order': order,
             'old_ok': old, 'new_ok': new} for i, (old, new) in enumerate(rows)]


def test_seed_bounds_and_witnesses():
    rows = ([(True, True)] * 16 + [(True, False)] * 2 + [(False, True)] * 12 + [(False, False)] * 4
            + [(None, True), (True, None)])
    pairs = [{'visitor_code': f'PD-{i:02}', 'reading_order': 'old_first' if i % 2 else 'new_first',
              'old_ok': old, 'new_ok': new} for i, (old, new) in enumerate(rows, 1)]
    paper = {'old_first': {'old': 10, 'new': 15}, 'new_first': {'old': 10, 'new': 15}}
    result, _, done = advance(pairs, 95, paper, None, float('inf'))
    assert done
    assert result['reconciliation']['status'] == 'ok'
    assert result['complete'] == 34 and result['missing'] == 2
    # Every valid completion of the demo is forced, so both bounds coincide at 2/12 discordant.
    assert result['p_bounds']['lower'] == result['p_bounds']['upper'] == p_value(2, 12)
    assert result['p_bounds']['m_min'] == result['p_bounds']['m_max'] == 14
    for side in ('completion_lower', 'completion_upper'):
        fills = result['p_bounds'][side]['fills']
        assert sorted(f['visitor_code'] for f in fills) == ['PD-35', 'PD-36']
        assert all(f['old_ok'] and f['new_ok'] for f in fills)


def test_non_degenerate_bounds_use_different_witnesses():
    # Both sides of six pairs are missing; paper says old=2, new=4 correct.
    rows = [{'visitor_code': f'V{i}', 'reading_order': 'old_first', 'old_ok': None, 'new_ok': None}
            for i in range(6)]
    rows.append({'visitor_code': 'W1', 'reading_order': 'new_first', 'old_ok': True, 'new_ok': True})
    paper = {'old_first': {'old': 2, 'new': 4}, 'new_first': {'old': 1, 'new': 1}}
    result, _, done = advance(rows, 95, paper, None, float('inf'))
    assert done and result['bounds_status'] == 'ok'
    assert result['p_bounds']['lower'] < result['p_bounds']['upper']
    assert result['p_bounds']['lower'] == p_value(0, 2)
    assert result['p_bounds']['upper'] == p_value(2, 4)
    assert result['p_bounds']['completion_lower']['m'] == 2
    assert result['p_bounds']['completion_upper']['m'] == 6


def test_bounds_round_trip_against_brute_force():
    rng = random.Random(11)
    for _ in range(300):
        rows = [(rng.choice([None, True, False]), rng.choice([None, True, False]))
                for _ in range(rng.randint(1, 6))]
        old_paper = rng.randint(0, len(rows))
        new_paper = rng.randint(0, len(rows))
        pairs = [{**row, 'visitor_code': 'V', 'reading_order': 'old_first'} for row in
                 ({'old_ok': old, 'new_ok': new} for old, new in rows)]
        paper = {'old_first': {'old': old_paper, 'new': new_paper},
                 'new_first': {'old': 0, 'new': 0}}
        expected = brute(make(rows, 'old_first'), old_paper, new_paper)
        result, _, done = advance(pairs, 95, paper, None, float('inf'))
        if not expected:
            assert result['reconciliation']['status'] == 'conflict'
            assert result['p_bounds'] is None
            continue
        assert result['reconciliation']['status'] == 'ok'
        if not result['p_bounds']:
            # Feasible totals but too few complete pairs after filling: still no p bounds.
            assert result['bounds_status'] == 'no_complete_pairs'
            assert all(b + c == 0 for b, c in expected)
            continue
        values = [p_value(b, c) for b, c in expected]
        assert abs(result['p_bounds']['lower'] - min(values)) < 1e-15
        assert abs(result['p_bounds']['upper'] - max(values)) < 1e-15


def test_conflict_names_the_group_and_correctness_side():
    rows = make([(True, True), (True, False)], 'old_first') + make([(False, True) for _ in range(6)], 'new_first')
    paper = {'old_first': {'old': 5, 'new': 2}, 'new_first': {'old': 0, 'new': 6}}
    recon = reconcile(rows, paper)
    assert recon['status'] == 'conflict'
    assert [item['reading_order'] for item in recon['conflicts']] == ['old_first']
    assert '旧版答对 5 人' in recon['conflicts'][0]['message']

    paper = {'old_first': {'old': 2, 'new': 1}, 'new_first': {'old': 0, 'new': 9}}
    recon = reconcile(rows, paper)
    assert [item['reading_order'] for item in recon['conflicts']] == ['new_first']
    assert '样张答对 9 人' in recon['conflicts'][0]['message']


def test_missing_totals_blocks_bounds_without_conflict():
    rows = make([(True, True), (True, False)], 'old_first')
    paper = {'old_first': {'old': 2, 'new': 1}, 'new_first': {'old': None, 'new': None}}
    recon = reconcile(rows, paper)
    assert recon['status'] == 'missing_totals' and recon['consistent']
    result, _, done = advance(rows, 95, paper, None, float('inf'))
    assert done and result['p_bounds'] is None and result['bounds_status'] == 'missing_totals'


def test_batching_is_deterministic():
    rng = random.Random(3)
    rows = [(rng.choice([None, True, False, None]), rng.choice([None, True, False, None]))
            for _ in range(120)]
    pairs = [{'visitor_code': f'PD-{i:03}', 'reading_order': 'old_first' if i % 2 else 'new_first',
              'old_ok': old, 'new_ok': new} for i, (old, new) in enumerate(rows)]
    paper = {}
    for order in ('old_first', 'new_first'):
        group = [row for row in pairs if row['reading_order'] == order]
        paper[order] = {'old': sum(1 for row in group if row['old_ok'] is True)
                        + sum(1 for row in group if row['old_ok'] is None) // 2,
                        'new': sum(1 for row in group if row['new_ok'] is True)
                        + sum(1 for row in group if row['new_ok'] is None) // 2}
    reference, _, _ = advance(pairs, 95, paper, None, float('inf'))
    for budget in (1, 5, 37, 5000):
        state, batches, result = None, 0, None
        while result is None:
            result, state, done = advance(pairs, 95, paper, state, float('inf'), budget)
            batches += 1
        key = lambda r: (r['p_bounds']['lower'], r['p_bounds']['upper'],
                         r['p_bounds']['m_min'], r['p_bounds']['m_max'])
        assert key(result) == key(reference)
        assert batches >= 1
