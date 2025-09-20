-- migrations/0001_init.sql
CREATE TABLE bots(
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text, token text, status text DEFAULT 'active');
CREATE TABLE bot_specs(
  id bigserial PRIMARY KEY, bot_id uuid REFERENCES bots(id),
  version int, spec_json jsonb, created_at timestamptz default now());
CREATE INDEX ON bot_specs(bot_id, version);