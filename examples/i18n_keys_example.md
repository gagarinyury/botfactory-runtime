# I18n Keys Examples

This file contains example localization keys for the i18n demo bot.

## Russian (ru) Keys

```json
{
  "welcome": "🏠 Добро пожаловать!\nВыберите действие:\n/register - Регистрация\n/profile - Профиль\n/survey - Оценить сервис\n/stats - Статистика\n/help - Помощь\n/lang - Сменить язык",

  "help_message": "📋 Доступные команды:\n\n/start - Главное меню\n/register - Зарегистрироваться в системе\n/profile - Посмотреть свой профиль\n/survey - Оставить отзыв\n/stats - Статистика бота\n/lang - Сменить язык интерфейса\n\nДля получения поддержки напишите @support",

  "lang_selector": "🌐 Выберите язык:\n/lang ru - Русский\n/lang en - English\n\nТекущий язык: Русский",

  "enter_name": "👤 Введите ваше имя:",
  "invalid_name": "❌ Имя должно содержать от 2 до 50 символов и состоять только из букв",

  "enter_age": "🎂 Введите ваш возраст:",
  "invalid_age": "❌ Возраст должен быть числом от 1 до 999",

  "enter_email": "📧 Введите ваш email:",
  "invalid_email": "❌ Неверный формат email. Пример: user@example.com",

  "registration_complete": "✅ Регистрация завершена!\n\nДобро пожаловать, {name}!\nВозраст: {age} лет\n\nТеперь вы можете:\n/profile - Посмотреть профиль\n/survey - Оценить сервис",

  "profile_info": "👤 Ваш профиль:\n\n📝 Имя: {name}\n🎂 Возраст: {age} лет\n📧 Email: {email}\n📅 Дата регистрации: {joined}",

  "profile_not_found": "❌ Профиль не найден.\nПожалуйста, сначала зарегистрируйтесь: /register",

  "edit_profile": "✏️ Редактировать",
  "back_to_menu": "🔙 В меню",

  "rate_service": "⭐ Оцените наш сервис от 1 до 5:",
  "invalid_rating": "❌ Оценка должна быть от 1 до 5",

  "leave_feedback": "💬 Оставьте комментарий (необязательно):",

  "feedback_thanks": "🙏 Спасибо за отзыв!\n\nВаша оценка: {rating} ⭐\n\nМы ценим ваше мнение и стремимся стать лучше!",

  "statistics": "📊 Статистика бота:\n\n👥 Всего пользователей: {total}\n⭐ Средняя оценка: {average_rating}/5"
}
```

## English (en) Keys

```json
{
  "welcome": "🏠 Welcome!\nChoose an action:\n/register - Registration\n/profile - Profile\n/survey - Rate service\n/stats - Statistics\n/help - Help\n/lang - Change language",

  "help_message": "📋 Available commands:\n\n/start - Main menu\n/register - Register in the system\n/profile - View your profile\n/survey - Leave feedback\n/stats - Bot statistics\n/lang - Change interface language\n\nFor support contact @support",

  "lang_selector": "🌐 Choose language:\n/lang ru - Русский\n/lang en - English\n\nCurrent language: English",

  "enter_name": "👤 Enter your name:",
  "invalid_name": "❌ Name must be 2-50 characters long and contain only letters",

  "enter_age": "🎂 Enter your age:",
  "invalid_age": "❌ Age must be a number from 1 to 999",

  "enter_email": "📧 Enter your email:",
  "invalid_email": "❌ Invalid email format. Example: user@example.com",

  "registration_complete": "✅ Registration complete!\n\nWelcome, {name}!\nAge: {age} years old\n\nNow you can:\n/profile - View profile\n/survey - Rate service",

  "profile_info": "👤 Your profile:\n\n📝 Name: {name}\n🎂 Age: {age} years old\n📧 Email: {email}\n📅 Registration date: {joined}",

  "profile_not_found": "❌ Profile not found.\nPlease register first: /register",

  "edit_profile": "✏️ Edit",
  "back_to_menu": "🔙 Back to menu",

  "rate_service": "⭐ Rate our service from 1 to 5:",
  "invalid_rating": "❌ Rating must be from 1 to 5",

  "leave_feedback": "💬 Leave a comment (optional):",

  "feedback_thanks": "🙏 Thank you for your feedback!\n\nYour rating: {rating} ⭐\n\nWe appreciate your opinion and strive to be better!",

  "statistics": "📊 Bot statistics:\n\n👥 Total users: {total}\n⭐ Average rating: {average_rating}/5"
}
```

## API Usage Examples

### Set Russian Keys
```bash
curl -X POST http://localhost:8000/bots/demo-bot/i18n/keys \
  -H "Content-Type: application/json" \
  -d '{
    "locale": "ru",
    "keys": {
      "welcome": "🏠 Добро пожаловать!",
      "help_message": "📋 Доступные команды:",
      "enter_name": "👤 Введите ваше имя:"
    }
  }'
```

### Set English Keys
```bash
curl -X POST http://localhost:8000/bots/demo-bot/i18n/keys \
  -H "Content-Type: application/json" \
  -d '{
    "locale": "en",
    "keys": {
      "welcome": "🏠 Welcome!",
      "help_message": "📋 Available commands:",
      "enter_name": "👤 Enter your name:"
    }
  }'
```

### Set User Locale
```bash
# Set user 123456 to use English
curl -X POST http://localhost:8000/bots/demo-bot/i18n/locale \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 123456,
    "locale": "en"
  }'

# Set chat 789 to use Russian
curl -X POST http://localhost:8000/bots/demo-bot/i18n/locale \
  -H "Content-Type: application/json" \
  -d '{
    "chat_id": 789,
    "locale": "ru"
  }'
```

### Get Keys for Locale
```bash
curl "http://localhost:8000/bots/demo-bot/i18n/keys?locale=en"
```

## Usage in Templates

### Simple Key
```json
{
  "type": "action.reply_template.v1",
  "params": {
    "text": "t:welcome"
  }
}
```

### Key with Placeholders
```json
{
  "type": "action.reply_template.v1",
  "params": {
    "text": "t:registration_complete {name={{username}}, age={{user_age}}}"
  }
}
```

### Mixed Templates
```json
{
  "type": "action.reply_template.v1",
  "params": {
    "text": "t:profile_info {name={{user_name}}, email={{user_email}}}",
    "empty_text": "t:profile_not_found"
  }
}
```

## Translation Key Naming Conventions

- Use snake_case: `registration_complete`, `invalid_email`
- Group by feature: `profile_*`, `survey_*`, `stats_*`
- Use descriptive names: `enter_name` not `name`
- Include context: `invalid_email` not `invalid`
- Keep keys stable - don't change them frequently