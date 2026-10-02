"""
Tests for the proxy check that guards account proxies. A fake fetcher
stands in for the network: what's verified is that sticky proxies pass,
rotating ones (the cause of LinkedIn sign-outs) and dead ones are refused
with a plain message, and that credentials never reach the API response.
"""

import pytest

from src.accounts import proxy_check
from src.accounts.service import _proxy_summary

STICKY = "http://login__cr.in:secret@gw.dataimpulse.com:10000"


def _fetcher(*answers):
    answers = list(answers)

    async def fetch(proxy_url):
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    return fetch


async def test_sticky_proxy_passes_and_records_its_exit():
    ip = {"ip": "103.1.1.1", "country": "IN", "city": "Ambala"}

    result = await proxy_check.check(STICKY, fetch=_fetcher(ip, ip))

    assert result["url"] == STICKY
    assert (result["ip"], result["country"], result["city"]) == ("103.1.1.1", "IN", "Ambala")
    assert result["checked_at"]


async def test_rotating_proxy_is_refused():
    with pytest.raises(proxy_check.ProxyCheckError, match="changes its address"):
        await proxy_check.check(
            STICKY,
            fetch=_fetcher({"ip": "1.1.1.1", "country": "RO"}, {"ip": "2.2.2.2", "country": "BR"}),
        )


async def test_dead_proxy_is_refused_without_leaking_the_password():
    with pytest.raises(proxy_check.ProxyCheckError) as err:
        await proxy_check.check(STICKY, fetch=_fetcher(ConnectionError(STICKY)))
    assert "secret" not in str(err.value)


@pytest.mark.parametrize("bad", ["gw.dataimpulse.com:823", "ftp://h:1", "http://host"])
def test_malformed_urls_are_refused(bad):
    with pytest.raises(proxy_check.ProxyCheckError):
        proxy_check.normalize(bad)


def test_blank_means_no_proxy():
    assert proxy_check.normalize("  ") is None
    assert proxy_check.normalize(None) is None


def test_summary_never_includes_credentials():
    summary = _proxy_summary({"url": STICKY, "ip": "103.1.1.1", "country": "IN"})
    assert summary["host"] == "gw.dataimpulse.com:10000"
    assert "secret" not in str(summary) and "login" not in str(summary)
    assert _proxy_summary(None) is None


async def test_proxy_timezone_is_recorded():
    ip = {"ip": "103.1.1.1", "country": "IN", "timezone": "Asia/Kolkata"}
    result = await proxy_check.check(STICKY, fetch=_fetcher(ip, ip))
    assert result["timezone"] == "Asia/Kolkata"
