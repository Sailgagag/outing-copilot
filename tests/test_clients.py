import httpx

from outing_copilot import clients

EXPECTED_UA = "outing-copilot (+https://github.com/Sailgagag/outing-copilot; https://github.com/Sailgagag/outing-copilot/issues)"


async def test_nws_request_sends_identifying_user_agent():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["ua"] = request.headers.get("user-agent")
        seen["accept"] = request.headers.get("accept")
        return httpx.Response(200, json={"features": []})

    async with clients.make_http_client(httpx.MockTransport(handler)) as http:
        assert await clients.nws_alerts(http, 47.6, -122.3) == []
    assert seen["ua"] == EXPECTED_UA
    assert seen["accept"] == "application/geo+json"
