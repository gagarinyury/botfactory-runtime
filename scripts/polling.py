#!/usr/bin/env python3
"""
Simple Telegram polling script for botfactory-runtime
Usage: python polling.py <BOT_TOKEN> <BOT_ID>
"""

import asyncio
import sys
import httpx
import os


async def get_updates(token: str, offset: int = 0):
    """Get updates from Telegram API"""
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    params = {"offset": offset, "timeout": 10}

    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)
        return response.json()


async def send_to_runtime(bot_id: str, update: dict):
    """Send update to botfactory runtime"""
    runtime_url = os.getenv("RUNTIME_URL", "http://localhost:8000")
    url = f"{runtime_url}/tg/{bot_id}"

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=update)
        return response.json()


async def polling_loop(token: str, bot_id: str):
    """Main polling loop"""
    offset = 0
    print(f"Starting polling for bot {bot_id}")

    while True:
        try:
            result = await get_updates(token, offset)

            if not result.get("ok"):
                print(f"Error from Telegram: {result}")
                await asyncio.sleep(5)
                continue

            updates = result.get("result", [])

            for update in updates:
                update_id = update.get("update_id")
                print(f"Processing update {update_id}")

                try:
                    response = await send_to_runtime(bot_id, update)
                    print(f"Runtime response: {response}")
                except Exception as e:
                    print(f"Error sending to runtime: {e}")

                offset = max(offset, update_id + 1)

        except Exception as e:
            print(f"Polling error: {e}")
            await asyncio.sleep(5)


def main():
    if len(sys.argv) != 3:
        print("Usage: python polling.py <BOT_TOKEN> <BOT_ID>")
        sys.exit(1)

    token = sys.argv[1]
    bot_id = sys.argv[2]

    asyncio.run(polling_loop(token, bot_id))


if __name__ == "__main__":
    main()