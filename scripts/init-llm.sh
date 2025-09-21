#!/bin/bash
# Test Docker Model Runner LLM service

set -e

echo "🤖 Testing LLM service..."

# Wait for service to start
echo "⏳ Waiting for LLM service..."
until curl -f http://localhost:11434/health >/dev/null 2>&1; do
    echo "   Waiting for LLM service..."
    sleep 5
done

echo "✅ LLM service is ready!"

# Test OpenAI-compatible endpoint
echo "🧪 Testing OpenAI-compatible API..."

# Test chat completions
curl -s http://localhost:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "microsoft/Phi-3-mini-4k-instruct",
    "messages": [
      {"role": "user", "content": "Привет! Сколько будет 2+2?"}
    ],
    "max_tokens": 100,
    "temperature": 0.2
  }' | jq '.choices[0].message.content' || echo "❌ Chat test failed"

# Test completions endpoint
curl -s http://localhost:11434/v1/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "microsoft/Phi-3-mini-4k-instruct",
    "prompt": "Translate to English: Привет мир",
    "max_tokens": 50,
    "temperature": 0.1
  }' | jq '.choices[0].text' || echo "❌ Completions test failed"

echo "🎉 LLM service tests complete!"