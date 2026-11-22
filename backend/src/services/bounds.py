"""Reconcile paper-sheet totals with paired records and bound the exact McNemar p value.

The paper sheet kept, per reading order, only how many visitors answered the old
label and the new specimen correctly.  Some paired records have one or both
observations missing.  A *completion* fills every missing observation with a
boolean so that each reading-order group reproduces the paper counts.

For a fixed difference ``d = new_success - old_success`` the exact McNemar
p value depends only on the number of discordant pairs ``m = b + c`` and is
non-decreasing in ``m``.  Every completion reproduces the same ``d`` (it is
fixed by the paper totals), so the smallest/largest attainable ``m`` give the
p bounds.  A witness completion is returned for each bound.

The search is split into resumable batches: ``advance`` takes a time budget and
a cursor, so hundreds of missing observations never hold up an ordinary run for
long.  The result is identical no matter how many batches were used.
"""

from time import monotonic

from src.services.statistics import analyze, exact_mcnemar

ORDERS = ('old_first', 'new_first')
ORDER_NAMES = {'old_first': '先读旧版组', 'new_first': '先读样张组'}


def _counts(rows):
    """Bucket a group of paired rows by which cells are observed and missing.

    a1/a0: old missing, new true/false; b1/b0: new missing, old true/false;
    k: both missing; p11/p10/p01/p00: complete cells (old true/false × new true/false).
    """
    counts = {'p11': 0, 'p10': 0, 'p01': 0, 'p00': 0,
              'a1': 0, 'a0': 0, 'b1': 0, 'b0': 0, 'k': 0}
    for row in rows:
        old, new = row['old_ok'], row['new_ok']
        if old is None and new is None:
            counts['k'] += 1
        elif old is None:
            counts['a1' if new else 'a0'] += 1
        elif new is None:
            counts['b1' if old else 'b0'] += 1
        elif old and new:
            counts['p11'] += 1
        elif old:
            counts['p10'] += 1
        elif new:
            counts['p01'] += 1
        else:
            counts['p00'] += 1
    return counts


def _group_summary(rows, paper_group):
    counts = _counts(rows)
    observed_old = counts['p11'] + counts['p10'] + counts['b1']
    observed_new = counts['p11'] + counts['p01'] + counts['a1']
    missing_old = counts['a1'] + counts['a0'] + counts['k']
    missing_new = counts['b1'] + counts['b0'] + counts['k']
    old_total = (paper_group or {}).get('old')
    new_total = (paper_group or {}).get('new')
    old_ok = old_total is None or observed_old <= old_total <= observed_old + missing_old
    new_ok = new_total is None or observed_new <= new_total <= observed_new + missing_new
    return {
        'counts': counts,
        'observed_old': observed_old, 'observed_new': observed_new,
        'missing_old': missing_old, 'missing_new': missing_new,
        'old_min': observed_old, 'old_max': observed_old + missing_old,
        'new_min': observed_new, 'new_max': observed_new + missing_new,
        'paper_old': old_total, 'paper_new': new_total,
        'registered': old_total is not None and new_total is not None,
        'old_ok': old_ok, 'new_ok': new_ok,
        'conflict': not (old_ok and new_ok),
    }


def _conflict_message(order, summary):
    if summary['old_ok'] and summary['new_ok']:
        return None
    problems = []
    if not summary['old_ok']:
        problems.append('旧版答对 %s 人，现有记录只支持 %d–%d 人'
                        % (_number(summary['paper_old']), summary['old_min'], summary['old_max']))
    if not summary['new_ok']:
        problems.append('样张答对 %s 人，现有记录只支持 %d–%d 人'
                        % (_number(summary['paper_new']), summary['new_min'], summary['new_max']))
    return '%s：%s' % (ORDER_NAMES[order], '；'.join(problems))


def _number(value):
    return '未登记' if value is None else value


def reconcile(pairs, paper_totals):
    """Check every reading-order group against the paper totals (cheap, O(rows))."""
    paper_totals = paper_totals or {}
    groups = []
    conflicts = []
    for order in ORDERS:
        rows = [row for row in pairs if row['reading_order'] == order]
        summary = _group_summary(rows, paper_totals.get(order))
        message = _conflict_message(order, summary)
        if message:
            conflicts.append({'reading_order': order, 'message': message})
        groups.append({
            'reading_order': order,
            'total': len(rows),
            'complete': sum(1 for row in rows
                            if row['old_ok'] is not None and row['new_ok'] is not None),
            'observed_old': summary['observed_old'], 'observed_new': summary['observed_new'],
            'missing_old': summary['missing_old'], 'missing_new': summary['missing_new'],
            'old_range': [summary['old_min'], summary['old_max']],
            'new_range': [summary['new_min'], summary['new_max']],
            'paper_old': summary['paper_old'], 'paper_new': summary['paper_new'],
            'registered': summary['registered'],
            'conflict': summary['conflict'],
        })
    registered = all(group['registered'] for group in groups)
    if conflicts:
        status = 'conflict'
    elif not registered:
        status = 'missing_totals'
    else:
        status = 'ok'
    return {
        'status': status,
        'ready': status == 'ok',
        'registered': registered,
        'consistent': not conflicts,
        'conflicts': conflicts,
        'groups': groups,
    }


def _meta(pairs, paper_totals, order):
    rows = [row for row in pairs if row['reading_order'] == order]
    summary = _group_summary(rows, (paper_totals or {}).get(order))
    c = summary['counts']
    xo = summary['paper_old'] - summary['observed_old']
    xn = summary['paper_new'] - summary['observed_new']
    return {
        'order': order, 'counts': c, 'xo': xo, 'xn': xn,
        'olo': max(0, xo - c['a1'] - c['a0']), 'ohi': min(c['k'], xo),
        'nlo': max(0, xn - c['b1'] - c['b0']), 'nhi': min(c['k'], xn),
        'base': c['p10'] + c['p01'] + c['a1'] + c['b1'],
    }


def _init_state(metas):
    groups = []
    for meta in metas:
        groups.append({
            'order': meta['order'], 'o': meta['olo'],
            'best_f': None, 'best_g': None, 'arg_f': None, 'arg_g': None,
            'm_min': None, 'm_max': None, 'done': False,
        })
    return {
        'stage': 'bounds',
        'ops_done': 0,
        'ops_total': sum((meta['ohi'] - meta['olo'] + 1) * (meta['nhi'] - meta['nlo'] + 1)
                         for meta in metas),
        'groups': groups,
    }


def _scan_group(group, meta, deadline, step_budget):
    """Scan the outer completion count ``o`` until exhausted or out of budget.

    Returns the number of inner steps taken and whether the group finished.
    """
    c = meta['counts']
    xo, xn = meta['xo'], meta['xn']
    steps = 0
    while group['o'] <= meta['ohi']:
        o = group['o']
        imax = min(c['a1'], xo - o)
        imin = max(0, xo - o - c['a0'])
        for n in range(meta['nlo'], meta['nhi'] + 1):
            lmax = min(c['b1'], xn - n)
            lmin = max(0, xn - n - c['b0'])
            high = imax + lmax + min(o, n)
            low = imin + lmin + max(0, o + n - c['k'])
            if group['best_f'] is None or high > group['best_f']:
                group['best_f'], group['arg_f'] = high, [o, n]
            if group['best_g'] is None or low < group['best_g']:
                group['best_g'], group['arg_g'] = low, [o, n]
        group['o'] += 1
        steps += meta['nhi'] - meta['nlo'] + 1
        if step_budget is not None and steps >= step_budget:
            if group['o'] <= meta['ohi']:
                return steps, False
        if monotonic() >= deadline and group['o'] <= meta['ohi']:
            return steps, False
    group['m_min'] = meta['base'] + xo + xn - 2 * group['best_f']
    group['m_max'] = meta['base'] + xo + xn - 2 * group['best_g']
    group['done'] = True
    return steps, True


def _fill_plan(meta, args, mode):
    """Counts per completion bucket that attain the minimal or maximal discordant total.

    ``o`` double-missing rows get the old answer right; ``n`` get the new answer right.
    """
    c = meta['counts']
    o, n = args
    xo, xn = meta['xo'], meta['xn']
    if mode == 'min':
        # Maximise both-off-both-on pairs (old-only and new-only under single missing).
        i = min(c['a1'], xo - o)
        l = min(c['b1'], xn - n)
        tt = min(o, n)
    else:
        # Maximise one-side-wrong pairs and split the double-missing rows apart.
        i = max(0, xo - o - c['a0'])
        l = max(0, xn - n - c['b0'])
        tt = max(0, o + n - c['k'])
    plan = {'a1': i, 'a0': xo - o - i, 'b1': l, 'b0': xn - n - l,
            'tt': tt, 'tf': o - tt, 'ft': n - tt, 'ff': c['k'] - o - n + tt}
    assert min(plan.values()) >= 0, (plan, meta, args)
    return plan


def _rows_with_index(pairs, order):
    return [(index, row) for index, row in enumerate(pairs) if row['reading_order'] == order]


def _group_fills(indexed, meta, args, mode):
    plan = _fill_plan(meta, args, mode)
    cats = {'a1': [], 'a0': [], 'b1': [], 'b0': [], 'k': []}
    for index, row in indexed:
        old, new = row['old_ok'], row['new_ok']
        if old is None and new is None:
            cats['k'].append((index, row))
        elif old is None:
            cats['a1' if new else 'a0'].append((index, row))
        elif new is None:
            cats['b1' if old else 'b0'].append((index, row))
    fills = {}
    for category in ('a1', 'a0'):
        # plan[category] counts how many rows in this bucket get old_ok=True.
        for position, (index, row) in enumerate(cats[category]):
            fills[index] = (position < plan[category], row['new_ok'])
    for category in ('b1', 'b0'):
        # plan[category] counts how many rows in this bucket get new_ok=True.
        for position, (index, row) in enumerate(cats[category]):
            fills[index] = (row['old_ok'], position < plan[category])
    pattern = ([(True, True)] * plan['tt'] + [(True, False)] * plan['tf'] +
               [(False, True)] * plan['ft'] + [(False, False)] * plan['ff'])
    for (index, _), value in zip(cats['k'], pattern):
        fills[index] = value
    return fills


def _completion(pairs, fills):
    b = c = complete = 0
    changed = []
    for index, row in enumerate(pairs):
        old, new = row['old_ok'], row['new_ok']
        if index in fills:
            old, new = fills[index]
            changed.append({'visitor_code': row['visitor_code'], 'reading_order': row['reading_order'],
                            'old_ok': old, 'new_ok': new})
        if old is not None and new is not None:
            complete += 1
            if old and not new:
                b += 1
            elif new and not old:
                c += 1
    return {
        'b': b, 'c': c, 'm': b + c, 'complete': complete,
        'p_value': exact_mcnemar(b, c) if complete else None,
        'fills': changed,
    }


def _completion_for(pairs, paper_totals, groups, mode):
    """Build the witness completion; recompute its m so p is guaranteed consistent."""
    fills = {}
    for order, group in zip(ORDERS, groups):
        meta = _meta(pairs, paper_totals, order)
        args = group['arg_f'] if mode == 'min' else group['arg_g']
        fills.update(_group_fills(_rows_with_index(pairs, order), meta, args, mode))
    return _completion(pairs, fills)


def _finish(pairs, confidence, paper_totals, state):
    recon = reconcile(pairs, paper_totals)
    base = analyze(pairs, confidence)
    groups = state['groups']
    candidate_min = _completion_for(pairs, paper_totals, groups, 'min')
    candidate_max = _completion_for(pairs, paper_totals, groups, 'max')
    # A completion is "empty" for the test only when no pair is complete. A completion
    # with complete pairs but m=0 is a legitimate witness (p=1), so use `complete` here.
    if not candidate_min['complete'] or not candidate_max['complete']:
        return {**base, 'paper_totals': paper_totals or None, 'reconciliation': recon,
                'p_bounds': None, 'bounds_status': 'no_complete_pairs',
                'batches': state.get('batches', 1), 'ops_total': state['ops_total']}
    ordered = sorted((candidate_min, candidate_max), key=lambda item: item['p_value'])
    lower, upper = ordered
    # m_min / m_max describe the discordant totals of the two witnesses actually returned.
    bounds = {
        'lower': lower['p_value'], 'upper': upper['p_value'],
        'm_min': lower['m'], 'm_max': upper['m'],
        'completion_lower': lower, 'completion_upper': upper,
    }
    return {**base, 'paper_totals': paper_totals or None,
            'reconciliation': recon, 'p_bounds': bounds, 'bounds_status': 'ok',
            'batches': state.get('batches', 1), 'ops_total': state['ops_total']}


def advance(pairs, confidence, paper_totals, state, deadline, step_budget=None):
    """Advance analysis by at most one batch, bounded by time and a step budget.

    Returns ``(result, state, done)``.  When ``done`` is false the caller must
    persist ``state`` and call again later; ``result`` is then ``None``.  Because
    the cursor lives in ``state``, any number of batches gives the same result.
    """
    recon = reconcile(pairs, paper_totals)
    if not recon['ready']:
        base = analyze(pairs, confidence)
        return {**base, 'paper_totals': paper_totals or None, 'reconciliation': recon,
                'p_bounds': None, 'bounds_status': recon['status'], 'batches': 1}, None, True
    metas = [_meta(pairs, paper_totals, order) for order in ORDERS]
    if state is None or state.get('stage') != 'bounds' or len(state.get('groups', [])) != len(metas):
        state = _init_state(metas)
    state['batches'] = state.get('batches', 0) + 1
    for group, meta in zip(state['groups'], metas):
        if group['done']:
            continue
        steps, finished = _scan_group(group, meta, deadline, step_budget)
        state['ops_done'] += steps
        if step_budget is not None:
            step_budget -= steps
        if not finished:
            return None, state, False
        if monotonic() >= deadline or (step_budget is not None and step_budget <= 0):
            if not all(g['done'] for g in state['groups']):
                return None, state, False
    return _finish(pairs, confidence, paper_totals, state), None, True
