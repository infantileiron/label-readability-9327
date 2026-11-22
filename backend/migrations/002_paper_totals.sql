ALTER TABLE studies ADD COLUMN paper_totals jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE analysis_runs ADD COLUMN progress jsonb;
ALTER TABLE analysis_runs ADD COLUMN progress_at timestamptz NOT NULL DEFAULT now();
CREATE INDEX analysis_queue_progress ON analysis_runs(progress_at, id) WHERE status = 'queued';
