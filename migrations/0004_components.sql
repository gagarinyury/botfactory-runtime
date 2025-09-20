-- migrations/0004_components.sql
CREATE TABLE components(
  id BIGSERIAL PRIMARY KEY,
  type TEXT NOT NULL,
  version TEXT NOT NULL,
  params_schema JSONB,
  graph JSONB,
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(type, version)
);