-- migrations/0006_bot_events.sql
CREATE TABLE bot_events(
  id BIGSERIAL PRIMARY KEY,
  ts TIMESTAMPTZ DEFAULT now(),
  bot_id UUID NOT NULL,
  user_id BIGINT NOT NULL,
  type TEXT NOT NULL,
  data JSONB
);