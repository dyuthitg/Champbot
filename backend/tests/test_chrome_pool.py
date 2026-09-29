"""
Tests for ChromePool -- the per-account Chrome lifecycle behind the
browser-harness fallback. A fake launcher and probe stand in for real
processes, so nothing is spawned: what's verified is the launch argv, the
proxy/forwarder decision, reuse, relaunch after a crash, and idle reaping.
"""

import types

import pytest

from src.infrastructure.transports.base import TransportUnavailable
from src.infrastructure.transports.chrome_pool import ChromePool, proxy_plan


class FakeProc:
    def __init__(self, argv):
        self.argv = argv
        self.returncode = None
        self.terminated = False

    def terminate(self):
        self.terminated = True
        self.returncode = 0

    def kill(self):
        self.returncode = -9

    async def wait(self):
        return self.returncode


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def _account(account_id="acct-1", proxy=None):
    return types.SimpleNamespace(id=account_id, proxy=proxy)


def _pool(tmp_path, **kwargs):
    launched = []

    async def launcher(argv):
        proc = FakeProc(argv)
        launched.append(proc)
        return proc

    async def probe(cdp_url):
        return True

    pool = ChromePool(
        data_dir=tmp_path,
        launcher=launcher,
        probe=probe,
        chrome_bin="chrome",
        headless=True,
        **kwargs,
    )
    return pool, launched


def test_proxy_plan_without_credentials_goes_direct():
    assert proxy_plan("http://10.0.0.1:8080") == ("http://10.0.0.1:8080", None)


def test_proxy_plan_with_credentials_needs_a_forwarder():
    assert proxy_plan("http://us%40r:p%3Ass@10.0.0.1:8080") == (
        None,
        "http://10.0.0.1:8080#us@r:p:ss",
    )


def test_proxy_plan_none():
    assert proxy_plan(None) == (None, None)


async def test_launches_one_chrome_per_account_and_reuses_it(tmp_path):
    pool, launched = _pool(tmp_path)

    first = await pool.get(_account())
    again = await pool.get(_account())
    other = await pool.get(_account("acct-2"))

    assert first is again
    assert other is not first
    assert len(launched) == 2
    argv = launched[0].argv
    assert "--headless=new" in argv
    assert any(a.startswith("--remote-debugging-port=") for a in argv)
    assert any(a.startswith("--user-data-dir=") and "acct-1" in a for a in argv)
    assert not any(a.startswith("--proxy-server") for a in argv)
    assert first.cdp_url.startswith("http://127.0.0.1:")
    assert first.bu_name == "acct-acct-1"


async def test_plain_proxy_is_passed_straight_to_chrome(tmp_path):
    pool, launched = _pool(tmp_path)

    await pool.get(_account(proxy={"url": "http://10.0.0.1:8080"}))

    assert len(launched) == 1
    assert "--proxy-server=http://10.0.0.1:8080" in launched[0].argv


async def test_authenticated_proxy_goes_through_a_local_forwarder(tmp_path):
    pool, launched = _pool(tmp_path)

    handle = await pool.get(_account(proxy={"url": "http://user:secret@10.0.0.1:8080"}))

    forwarder, chrome = launched
    assert "pproxy" in forwarder.argv
    assert "http://10.0.0.1:8080#user:secret" in forwarder.argv
    local = forwarder.argv[forwarder.argv.index("-l") + 1]
    assert local.startswith("http://127.0.0.1:")
    # Chrome only ever sees the credential-free loopback forwarder.
    assert f"--proxy-server={local}" in chrome.argv
    assert not any("secret" in a for a in chrome.argv)
    assert handle.forwarder is forwarder


async def test_dead_chrome_is_relaunched(tmp_path):
    pool, launched = _pool(tmp_path)

    first = await pool.get(_account())
    first.chrome.returncode = 1  # crashed
    second = await pool.get(_account())

    assert second is not first
    assert len(launched) == 2


async def test_idle_chromes_are_reaped(tmp_path):
    clock = FakeClock()
    pool, launched = _pool(tmp_path, idle_ttl=60, clock=clock)

    await pool.get(_account())
    clock.now += 30
    assert await pool.reap_idle() == []
    clock.now += 31
    assert await pool.reap_idle() == ["acct-1"]
    assert launched[0].terminated
    assert pool.handles() == []


async def test_touch_keeps_a_busy_chrome_alive(tmp_path):
    clock = FakeClock()
    pool, _ = _pool(tmp_path, idle_ttl=60, clock=clock)

    handle = await pool.get(_account())
    clock.now += 59
    pool.touch(handle)
    clock.now += 59
    assert await pool.reap_idle() == []


async def test_close_stops_chrome_and_forwarder(tmp_path):
    pool, launched = _pool(tmp_path)

    await pool.get(_account(proxy={"url": "http://u:p@10.0.0.1:8080"}))
    await pool.close()

    assert all(p.terminated for p in launched)


async def test_no_chrome_binary_is_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "src.infrastructure.transports.chrome_pool.find_chrome", lambda: None
    )
    pool = ChromePool(data_dir=tmp_path, launcher=None, probe=None)

    with pytest.raises(TransportUnavailable, match="CHROME_BIN"):
        await pool.get(_account())


async def test_chrome_that_never_gets_ready_is_unavailable(tmp_path, monkeypatch):
    clock = FakeClock()
    launched = []

    async def launcher(argv):
        proc = FakeProc(argv)
        launched.append(proc)
        return proc

    async def probe(cdp_url):
        clock.now += 30  # each probe "takes" 30s
        return False

    async def no_sleep(_):
        return None

    monkeypatch.setattr("src.infrastructure.transports.chrome_pool.asyncio.sleep", no_sleep)
    pool = ChromePool(
        data_dir=tmp_path, launcher=launcher, probe=probe, chrome_bin="chrome", clock=clock
    )

    with pytest.raises(TransportUnavailable, match="DevTools"):
        await pool.get(_account())
    assert launched[0].terminated
