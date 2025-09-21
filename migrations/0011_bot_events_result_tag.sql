-- Add result_tag column to bot_events for A/B testing tracking
-- Tracks whether LLM was used for each interaction

ALTER TABLE bot_events
ADD COLUMN result_tag JSONB;

-- Index for efficient queries on result tags
CREATE INDEX idx_bot_events_result_tag ON bot_events USING GIN (result_tag);

-- Example result_tag values:
-- {"llm": "yes", "variant": "treatment"}
-- {"llm": "no", "variant": "control"}
-- {"llm": "error", "reason": "timeout"}
-- null (for events that don't involve LLM)