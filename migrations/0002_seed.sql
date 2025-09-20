INSERT INTO bots(id, name, token) VALUES
  ('c3b88b65-623c-41b5-a3c9-8d56fcbc4413', 'test-bot', 'TEST_TOKEN'),
  (gen_random_uuid(), 'demo', 'DEMO_TOKEN');

INSERT INTO bot_specs(bot_id,version,spec_json) VALUES
  ('c3b88b65-623c-41b5-a3c9-8d56fcbc4413', 1, '{"intents":[{"cmd":"/start","reply":"Привет! Это тестовый бот."},{"cmd":"/help","reply":"Доступные команды: /start, /help"}],"flows":[]}'::jsonb);

INSERT INTO bot_specs(bot_id,version,spec_json)
SELECT id,1,'{"intents":[],"flows":[]}'::jsonb FROM bots WHERE name='demo';