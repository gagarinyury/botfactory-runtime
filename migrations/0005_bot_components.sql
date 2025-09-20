-- migrations/0005_bot_components.sql
CREATE TABLE bot_components(
  bot_id UUID NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
  component_id BIGINT NOT NULL REFERENCES components(id) ON DELETE CASCADE,
  overrides JSONB,
  PRIMARY KEY(bot_id, component_id)
);