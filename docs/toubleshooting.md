# Troubleshooting

Find your symptom below. Run with `-v` (verbose) to see detailed logs,
e.g. `uv run lovecash run -v`.

## The doctor check fails



### "Electrum server: unreachable"

lovecash can't reach the blockchain server.

- Check your internet connection.
- The default server may be down. Try a different one in `config.yaml`:

```yaml
bch:
  electrum_host: fulcrum.jettscythe.xyz
  electrum_port: 50002
```

### "Lovense Connect: not found"

Your toy app isn't sharing its connection.

- Open the Lovense Connect app (not Lovense Remote).
- Make sure your phone and computer are on the same Wi-Fi network.
- Only one app can control the toy at once. Close Stream Master or
  Lovense Remote if either is holding the toy.

## The toy doesn't respond to tips

1. Confirm tips arrive: with `-v` running, you should see "Tip received"
   in the logs when a payment lands. If you don't, it's a payment/
   blockchain issue, not a toy issue.
2. Confirm the action matches your toy. A vibrator needs `Vibrate`; a
   thrusting toy needs `Thrusting`. See the
   [Tip Rules Guide](tip-rules.md).
3. Test the toy directly with a curl command (see Tip Rules Guide) to
   isolate whether it's lovecash or the toy connection.

## Tips arrive but the toy barely moves

Your `max_strength` is probably capping it. If you set
`max_strength: 3` during testing, every tip is limited to strength 3.
Raise it in `config.yaml` once you've confirmed the panic stop works.

## "Your config.yaml has a problem"

The config file has a formatting error. The message names the field.
The most common cause: rules missing their leading dash (`-`). Each rule
must look like:

```yaml
rules:
  - name: tease
    min_sats: 1000
```

Easiest fix: run`uv run lovecash init` again to regenerate a clean
config.

## The overlay shows "reconnecting" in OBS

The relay isn't running or OBS can't reach it.

- Make sure`uv run lovecash serve` is running.
- Confirm the URL in OBS matches the address it printed.
- If running OBS and lovecash on different computers, use the actual IP,
  not`localhost`.

## Tips stop triggering partway through a long stream

The connection to the blockchain server may have dropped. Restart
lovecash. (Automatic reconnection is a known area for improvement.)

## The toy keeps running after I close the terminal

Always stop with Ctrl-C, which sends a stop command to the toy. If the
terminal was force-closed, open the Lovense app and stop the toy there,
then restart lovecash cleanly.

## Still stuck?

Run with`-v`, reproduce the problem, and capture the log output. That
log is what's needed to diagnose anything not covered here.
