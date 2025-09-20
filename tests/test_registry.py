def test_get_bot(client):
    r = client.get("/bots/c3b88b65-623c-41b5-a3c9-8d56fcbc4413")
    assert r.status_code==200 and "spec_json" in r.json()["bot"]