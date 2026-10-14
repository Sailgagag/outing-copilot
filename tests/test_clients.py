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


async def test_transient_failure_is_retried_once():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("tls hiccup", request=request)
        return httpx.Response(200, json={"features": []})

    async with clients.make_http_client(httpx.MockTransport(handler)) as http:
        assert await clients.nws_alerts(http, 47.6, -122.3) == []
    assert calls["n"] == 2


async def test_upstream_failure_message_is_speakable():
    def handler(request):
        raise httpx.ConnectError("[SSL: WRONG_VERSION_NUMBER]", request=request)

    async with clients.make_http_client(httpx.MockTransport(handler)) as http:
        try:
            await clients.forecast(http, 1, 2)
        except clients.UpstreamError as exc:
            assert str(exc).startswith("I couldn't reach the weather service")
            assert "SSL" in exc.detail and "http" not in str(exc)
        else:
            raise AssertionError("expected UpstreamError")
