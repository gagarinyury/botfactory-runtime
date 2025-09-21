-- Migration for i18n.fluent.v1 - Internationalization support

-- User/chat locale preferences
CREATE TABLE IF NOT EXISTS locales (
    user_id BIGINT,
    chat_id BIGINT,
    bot_id UUID NOT NULL,
    locale TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY(bot_id, COALESCE(user_id, 0), COALESCE(chat_id, 0))
);

-- Localization keys and values
CREATE TABLE IF NOT EXISTS i18n_keys (
    bot_id UUID NOT NULL,
    locale TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY(bot_id, locale, key)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_locales_bot_user ON locales(bot_id, user_id) WHERE user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_locales_bot_chat ON locales(bot_id, chat_id) WHERE chat_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_i18n_keys_bot_locale ON i18n_keys(bot_id, locale);

-- Comments for documentation
COMMENT ON TABLE locales IS 'User and chat locale preferences for i18n.fluent.v1';
COMMENT ON TABLE i18n_keys IS 'Localization keys and translations for i18n.fluent.v1';

COMMENT ON COLUMN locales.user_id IS 'Telegram user ID for user-level locale strategy';
COMMENT ON COLUMN locales.chat_id IS 'Telegram chat ID for chat-level locale strategy';
COMMENT ON COLUMN locales.bot_id IS 'Bot identifier';
COMMENT ON COLUMN locales.locale IS 'Language code (e.g., "ru", "en")';

COMMENT ON COLUMN i18n_keys.key IS 'Localization key (e.g., "menu.title")';
COMMENT ON COLUMN i18n_keys.value IS 'Translated text value with Fluent syntax support';