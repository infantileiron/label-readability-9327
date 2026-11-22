import csv
import io


def pairing_csv(export):
    """Fixed-key snapshot rows, annotated with the completion that reaches each p bound."""
    result = export.get('result') or {}
    bounds = result.get('p_bounds') or {}
    witnesses = {}
    for side in ('completion_lower', 'completion_upper'):
        for row in (bounds.get(side) or {}).get('fills', []):
            witnesses.setdefault(row['visitor_code'], {})[side] = row
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow(['run_id', 'checksum', 'revision', 'visitor_code', 'reading_order', 'old_ok', 'new_ok',
                     'complete', 'lower_fill_old', 'lower_fill_new', 'upper_fill_old', 'upper_fill_new'])
    for row in export['snapshot']['pairs']:
        old, new = row['old_ok'], row['new_ok']
        witness = witnesses.get(row['visitor_code'], {})
        lower, upper = witness.get('completion_lower'), witness.get('completion_upper')
        writer.writerow([export['id'], export['checksum'], export['revision'], row['visitor_code'],
                         row['reading_order'], old, new, old is not None and new is not None,
                         lower['old_ok'] if lower else '', lower['new_ok'] if lower else '',
                         upper['old_ok'] if upper else '', upper['new_ok'] if upper else ''])
    return output.getvalue()
