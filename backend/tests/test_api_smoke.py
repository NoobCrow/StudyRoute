def test_health_is_public_and_labelled_sandbox(world) -> None:
    body = world.client.get("/health").json()
    assert body["status"] == "ok"
    assert "no real money" in body["banner"]


def test_login_quote_and_draft_flow(world) -> None:
    quote = world.quote()
    assert [r["provider_id"] for r in quote["results"]] == ["prov_b", "prov_c", "prov_a"]
    payment = world.draft(quote)
    assert payment["state"] == "QUOTED"
    assert payment["uetr"] is None
