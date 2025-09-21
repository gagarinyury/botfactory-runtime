-- migrations/0010_bot_llm_settings.sql
-- Add per-bot LLM settings

ALTER TABLE bots ADD COLUMN llm_enabled BOOLEAN DEFAULT false;
ALTER TABLE bots ADD COLUMN llm_preset TEXT DEFAULT 'neutral';

-- Create index for LLM-enabled bots
CREATE INDEX idx_bots_llm_enabled ON bots(llm_enabled) WHERE llm_enabled = true;

-- Add comment explaining the fields
COMMENT ON COLUMN bots.llm_enabled IS 'Enable LLM text improvements for this bot';
COMMENT ON COLUMN bots.llm_preset IS 'LLM style preset: short, neutral, detailed';