-- migrations/0003_booking.sql
CREATE TABLE bookings(
  id BIGSERIAL PRIMARY KEY,
  bot_id UUID NOT NULL,
  user_id BIGINT NOT NULL,
  service TEXT NOT NULL,
  slot TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX ON bookings(bot_id, user_id);