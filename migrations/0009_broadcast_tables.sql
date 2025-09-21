-- Migration for ops.broadcast.v1 - Mass messaging system

-- Bot users table for audience targeting
CREATE TABLE IF NOT EXISTS bot_users (
    bot_id UUID NOT NULL,
    user_id BIGINT NOT NULL,
    last_active TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    segment_tags TEXT[] DEFAULT '{}',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY(bot_id, user_id)
);

-- Broadcast campaigns
CREATE TABLE IF NOT EXISTS broadcasts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bot_id UUID NOT NULL,
    audience TEXT NOT NULL, -- 'all', 'active_7d', 'segment:tag_name'
    message JSONB NOT NULL, -- Message template with variables
    throttle JSONB NOT NULL DEFAULT '{"per_sec": 30}', -- Rate limiting config
    status TEXT NOT NULL DEFAULT 'pending', -- 'pending', 'running', 'completed', 'failed'
    total_users INTEGER DEFAULT 0,
    sent_count INTEGER DEFAULT 0,
    failed_count INTEGER DEFAULT 0,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Individual broadcast delivery events
CREATE TABLE IF NOT EXISTS broadcast_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    broadcast_id UUID NOT NULL REFERENCES broadcasts(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL,
    status TEXT NOT NULL, -- 'sent', 'failed', 'blocked'
    error_code TEXT, -- API error code if failed
    error_message TEXT, -- API error message if failed
    sent_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_bot_users_bot_last_active ON bot_users(bot_id, last_active);
CREATE INDEX IF NOT EXISTS idx_bot_users_bot_segments ON bot_users USING GIN(bot_id, segment_tags);
CREATE INDEX IF NOT EXISTS idx_bot_users_bot_active ON bot_users(bot_id, is_active) WHERE is_active = true;

CREATE INDEX IF NOT EXISTS idx_broadcasts_bot_status ON broadcasts(bot_id, status);
CREATE INDEX IF NOT EXISTS idx_broadcasts_created_at ON broadcasts(created_at);
CREATE INDEX IF NOT EXISTS idx_broadcasts_status ON broadcasts(status) WHERE status IN ('pending', 'running');

CREATE INDEX IF NOT EXISTS idx_broadcast_events_broadcast_id ON broadcast_events(broadcast_id);
CREATE INDEX IF NOT EXISTS idx_broadcast_events_user_status ON broadcast_events(user_id, status);
CREATE INDEX IF NOT EXISTS idx_broadcast_events_sent_at ON broadcast_events(sent_at);

-- Comments for documentation
COMMENT ON TABLE bot_users IS 'Bot users with activity tracking and segmentation for broadcast targeting';
COMMENT ON TABLE broadcasts IS 'Broadcast campaigns with configuration and progress tracking';
COMMENT ON TABLE broadcast_events IS 'Individual message delivery events for broadcast campaigns';

COMMENT ON COLUMN bot_users.last_active IS 'Last interaction timestamp for activity-based targeting';
COMMENT ON COLUMN bot_users.segment_tags IS 'Array of tags for segment-based targeting';
COMMENT ON COLUMN bot_users.is_active IS 'Whether user is active (not blocked bot)';

COMMENT ON COLUMN broadcasts.audience IS 'Target audience: all, active_7d, segment:tag_name';
COMMENT ON COLUMN broadcasts.message IS 'Message template with i18n key and variables';
COMMENT ON COLUMN broadcasts.throttle IS 'Rate limiting configuration';
COMMENT ON COLUMN broadcasts.status IS 'Campaign status: pending, running, completed, failed';

COMMENT ON COLUMN broadcast_events.status IS 'Delivery status: sent, failed, blocked';
COMMENT ON COLUMN broadcast_events.error_code IS 'Telegram API error code if delivery failed';