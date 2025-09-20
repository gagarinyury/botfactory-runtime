-- migrations/0007_indexes.sql
-- Индексы для bot_components
CREATE INDEX ON bot_components(bot_id);

-- Индексы для bot_events
CREATE INDEX ON bot_events(bot_id, ts DESC);
CREATE INDEX ON bot_events(type);
CREATE INDEX ON bot_events(ts DESC);