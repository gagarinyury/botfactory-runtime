def test_preview_start(client):  # фикстура client для FastAPI TestClient
    r = client.post("/preview/send", json={"bot_id":"c3b88b65-623c-41b5-a3c9-8d56fcbc4413","text":"/start"})
    assert r.json()["bot_reply"].startswith("Привет")