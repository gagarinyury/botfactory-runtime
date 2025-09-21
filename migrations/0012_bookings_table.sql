CREATE TABLE IF NOT EXISTS bookings (
    bot_id UUID NOT NULL,
    user_id BIGINT NOT NULL,
    service TEXT,
    slot TIMESTAMPTZ,
    PRIMARY KEY (bot_id, user_id, slot)
);
