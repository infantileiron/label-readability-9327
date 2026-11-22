import logging
from time import monotonic, sleep

from psycopg.types.json import Jsonb

from src.config.settings import BATCH_SECONDS, HEARTBEAT, STEP_BUDGET
from src.constants.enums import METHOD
from src.models.database import cache, connect
from src.services.audit import record
from src.services.bounds import advance
from src.services.runs import snapshot_digest

logger = logging.getLogger(__name__)


def _claim(db):
    """Claim one queued run, keeping any accumulated batch progress.

    ``FOR UPDATE SKIP LOCKED`` takes the row lock; the transaction is committed
    only after a batch is persisted, so a killed worker rolls back the claim and
    the row becomes claimable again.  To keep ordinary runs from waiting behind
    a many-batch run, an unfinished run with progress yields to untouched runs:
    we only resume it when no queued run without progress exists.
    """
    fresh = db.execute('''SELECT * FROM analysis_runs
                          WHERE status='queued' AND progress IS NULL
                          ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED''').fetchone()
    if fresh:
        return fresh
    return db.execute('''SELECT * FROM analysis_runs
                         WHERE status='queued'
                         ORDER BY progress_at, id LIMIT 1 FOR UPDATE SKIP LOCKED''').fetchone()


def execute_one():
    with connect() as db:
        run = _claim(db)
        if not run:
            return False
        try:
            snapshot = run['snapshot']
            if snapshot_digest(snapshot) != run['checksum'] or run['method'] != METHOD:
                raise ValueError('invalid input checksum or method')
            paper_totals = snapshot.get('paper_totals') or {}
            result, state, done = advance(snapshot['pairs'], run['confidence'], paper_totals,
                                          run['progress'], monotonic() + BATCH_SECONDS, STEP_BUDGET)
        except Exception:
            logger.exception('Run %s failed', run['id'])
            db.execute("UPDATE analysis_runs SET status='failed', error=%s, progress=NULL, finished_at=now() "
                       "WHERE id=%s", ('分析失败，请检查样本后重新运行', run['id']))
            record(db, 'worker', 'analysis.failed', str(run['id']))
        else:
            if done:
                db.execute("UPDATE analysis_runs SET status='succeeded', result=%s, progress=NULL, finished_at=now() "
                           "WHERE id=%s", (Jsonb(result), run['id']))
                record(db, 'worker', 'analysis.completed', str(run['id']),
                       {'complete': result['complete'], 'batches': result.get('batches', 1)})
            else:
                db.execute("UPDATE analysis_runs SET progress=%s, progress_at=now() WHERE id=%s",
                           (Jsonb(state), run['id']))
                record(db, 'worker', 'analysis.progress', str(run['id']),
                       {'ops_done': state['ops_done'], 'ops_total': state['ops_total']})
    return True


def main():
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            worked = execute_one()
            cache.set(HEARTBEAT, 'ready', ex=8)
            if not worked:
                sleep(0.65)
        except Exception:
            logger.exception('Worker poll failed')
            sleep(2)


if __name__ == '__main__':
    main()
