# Safety Guide

Your safety comes first. lovecash is built so that nothing — no tip, no
viewer, no software glitch — can override your control. This guide
explains the protections and how to test them.


## Connection status

The overlay shows whether lovecash is connected to the Bitcoin Cash
network. If the connection drops, the status flips to "tips paused —
reconnecting" and lovecash automatically retries. Tips that arrive once
it reconnects are still detected. Keep an eye on this indicator — if it
stays red, check your internet or Electrum server.

`lovecash doctor` also reports whether each toy is online. Note that
Lovense may disconnect an idle toy on its own; if a toy drops mid-session
you'll need to reconnect it in the Lovense app.


## The panic stop

The panic stop halts your toy and blocks all further commands until you
choose to resume. No incoming tip can clear it.

- Running locally: press Ctrl-C in the terminal.
- Using the relay: send a request to the `/panic` endpoint.

Once engaged, the toy stops and stays stopped. This is the single most
important feature. Test it every session.

## Hard limits

In `config.yaml`, two settings are your ceiling and cannot be exceeded
by any tip:

```yaml
limits:
  max_strength: 12      # 0 to 20; your maximum intensity
  max_duration_s: 30    # longest any single tip can run
```

Even if a viewer sends a huge tip mapped to maximum strength, the toy
never goes above`max_strength` or runs longer than`max_duration_s`.

## Rate limiting

```yaml
limits:
  min_seconds_between_commands: 0.5
```

This prevents rapid-fire tips from overdriving your toy. Commands closer
together than this are dropped.

## The safe first-time test routine

Do this before your first real session, and any time you change toys or
settings.

1. Set a low cap while testing:

```yaml
limits:
  max_strength: 3
  max_duration_s: 5
```

2. Place the toy on a desk, NOT on your body.

3. Start lovecash:

```bash
uv run lovecash run -v
```

4. Fire a test command and confirm the toy reacts gently.

5. While it's running, press Ctrl-C. Confirm the toy stops immediately.

6. Only after you've personally seen the panic stop work, raise your
   limits to your real preferences.

## Test the panic stop mid-action

The real test is stopping a toy that's actively running:

1. Temporarily set`max_duration_s: 10`.
2. Trigger a tip so the toy runs for several seconds.
3. While it's running, press Ctrl-C.
4. Confirm it cuts off instantly, not after the 10 seconds finish.

If it stops cleanly, you can trust the system. If it doesn't, stop using
lovecash and see [Troubleshooting](troubleshooting.md).

## Good habits during a stream

- Keep the terminal window visible and reachable for Ctrl-C.
- Set limits you're comfortable with even at the maximum tip.
- Start each session with the doctor check and a quick panic-stop test.
- If anything feels wrong, Ctrl-C first, investigate second.

## What lovecash will never do

- It never holds, moves, or has access to your money.
- It never has your wallet password, seed phrase, or private keys.
- It never lets a tip override your panic stop or your hard limits.
- It never sends toy commands above the strength you set.
