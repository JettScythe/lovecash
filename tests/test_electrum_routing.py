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


def test_tls_verify_builds_verifying_context():
    import ssl

    c = ElectrumClient("h", 50002, tls_verify=True)
    ctx = c._ssl_context()
    assert ctx.check_hostname
    assert ctx.verify_mode == ssl.CERT_REQUIRED


def test_tls_verify_off_warns_and_disables():
    import ssl

    c = ElectrumClient("h", 50002, tls_verify=False)
    ctx = c._ssl_context()
    assert not ctx.check_hostname
    assert ctx.verify_mode == ssl.CERT_NONE


def test_server_config_verifies_tls_by_default():
    from lovecash.config import ElectrumServer

    assert ElectrumServer(host="h").tls_verify is True
