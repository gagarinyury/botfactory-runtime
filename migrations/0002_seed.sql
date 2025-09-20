INSERT INTO bots(name, token) VALUES ('demo','TEST_TOKEN');
INSERT INTO bot_specs(bot_id,version,spec_json)
SELECT id,1,'{"intents":[],"flows":[]}'::jsonb FROM bots WHERE name='demo';