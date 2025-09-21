-- Add daily budget limit for bots (in tokens)
ALTER TABLE bots ADD COLUMN daily_budget_limit INTEGER DEFAULT 10000;

-- Add index for budget queries
CREATE INDEX idx_bots_daily_budget_limit ON bots(daily_budget_limit) WHERE daily_budget_limit IS NOT NULL;

-- Set reasonable defaults based on llm_enabled status
UPDATE bots SET daily_budget_limit = CASE
    WHEN llm_enabled = true THEN 10000  -- 10k tokens/day for LLM-enabled bots
    ELSE 5000                           -- 5k tokens/day for regular bots
END;

-- Add comment
COMMENT ON COLUMN bots.daily_budget_limit IS 'Daily budget limit in tokens (10000 = ~$0.02 for Phi-3-mini)';