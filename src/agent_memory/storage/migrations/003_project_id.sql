-- Migration 003: project-level isolation for events + runs
-- No backfill: the user has no production data yet.
-- Historical rows (if any) will have project_id = NULL.

PRAGMA foreign_keys = ON;

-- Add project_id to events so we can filter / isolate by project.
ALTER TABLE events ADD COLUMN project_id TEXT;
CREATE INDEX idx_events_project ON events(project_id) WHERE project_id IS NOT NULL;

-- Add project_id to runs so per-project run stats are cheap.
-- The project is resolved via task → project_id, but we denormalize
-- here to keep reporting queries single-table.
ALTER TABLE runs ADD COLUMN project_id TEXT;
CREATE INDEX idx_runs_project ON runs(project_id) WHERE project_id IS NOT NULL;
