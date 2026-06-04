from lovecash.bch.electrum import ElectrumClient


def _client() -> ElectrumClient:
    return ElectrumClient("h", 50002)


def test_dsproof_notification_fires_event_not_queue():
    c = _client()
    ev = c.watch_dsproof("txid123")
    c._dispatch(
        {
            "method": "blockchain.transaction.dsproof.subscribe",
            "params": ["txid123", {"dspid": "x"}],
        }
    )
    assert ev.is_set()
    assert c._notifications.empty()  # did NOT leak to scripthash queue


def test_scripthash_notification_goes_to_queue_not_dsproof():
    c = _client()
    ev = c.watch_dsproof("txid123")
    c._dispatch(
        {
            "method": "blockchain.scripthash.subscribe",
            "params": ["somescripthash", "status"],
        }
    )
    assert not ev.is_set()  # dsproof event untouched
    assert not c._notifications.empty()


def test_dsproof_for_unwatched_txid_is_ignored():
    c = _client()
    c._dispatch(
        {
            "method": "blockchain.transaction.dsproof.subscribe",
            "params": ["unknown", {}],
        }
    )
    assert c._notifications.empty()  # not queued, not crashed
