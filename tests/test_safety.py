from lovecash.safety import SafetyState


async def test_panic_blocks_commands():
    s = SafetyState(min_interval_s=0)
    assert await s.allow() is True
    s.panic_stop()
    assert await s.allow() is False
    s.resume()
    assert await s.allow() is True


async def test_rate_limit():
    s = SafetyState(min_interval_s=10)
    assert await s.allow() is True
    assert await s.allow() is False  # too soon
