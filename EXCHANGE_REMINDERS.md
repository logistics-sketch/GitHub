# Exchange reminder integration

Status: prepared for review; NOT enabled or deployed. This branch targets the source repository configured on Railway. Runtime files may have been modified through SSH; compare before a production release.

The existing consultant keeps its menu and handlers. An opt-in worker sends exchange reminders every two local calendar days after 09:10 Europe/Kyiv. It requires a fresh complete snapshot of all open exchange candidates across month boundaries. It does not scrape a browser session and never treats the metrics count as receipt evidence.

## Activation prerequisites

- A protected HTTPS JSON feed built from the authorized service-metrics/Laravel sources. No feed endpoint is configured on the live service.
- Bearer authentication stored as a sealed secret, not in this repository or URL.
- A persistent Railway volume mounted on the existing service. The live service currently has no volume.
- Existing SERVICE_TELEGRAM_USER_IDS must include the authorized people. Each intended recipient uses /exchange_reminders in a private chat once; Telegram provides and verifies their username and numeric ID. No guessed IDs.
- Check the current live bot before deploying: this PR was based on the configured GitHub main source, not a downloaded runtime filesystem.
- Execute a controlled Telegram delivery check only after prerequisites are complete.

Variables: EXCHANGE_REMINDERS_ENABLED=true, EXCHANGE_FEED_URL, EXCHANGE_FEED_TOKEN. RAILWAY_VOLUME_MOUNT_PATH is supplied by the mounted Railway volume. Existing TELEGRAM_TOKEN and SERVICE_TELEGRAM_USER_IDS are reused inside the service, never copied into chat.

Defaults: disabled. If explicitly enabled with missing prerequisites, the reminder worker stays inactive. No service configuration was changed by preparing this PR.

## Feed contract

All identifiers and SKU are strings; preserve leading zeros. Only include the required service fields; no client contacts. Complete means the payload includes every open candidate in the controlled register, including prior months.

```json
{
  "complete": true,
  "generated_at": "2026-11-16T10:00:00+02:00",
  "items": [
    {
      "request_number": "0000123",
      "sku": "001234",
      "appeal": "Обмін",
      "classification": "особисті обставини після 14 днів",
      "draft": false,
      "received": null,
      "credited": null
    }
  ]
}
```

received/credited null means unknown; booleans require an evidence reference. cancelled=true explicitly closes an item. Feed snapshots older than 48 hours, future-dated snapshots, malformed rows and duplicates are rejected before delivery. Never infer receipt from a current location alone.

The worker handles receipt and accounting as separate facts. Confirmed received items get a credit-check message; confirmed received+credited items and explicitly cancelled items get no reminder.

SQLite stores the scheduling anchor, verified recipients and delivery ledger on the mounted volume. Every attempt is reserved before send. Ambiguous send failures are not retried within that two-day cycle, to avoid duplicate delivery. A failed recipient does not resend to successful recipients. Pending attempts must be reviewed in the ledger when investigating transport uncertainty.

## Verification

python -m unittest -v test_exchange_reminders.py
python -m py_compile bot.py exchange_reminders.py

Nine tests cover the evidence states, missing SKU, stale/incomplete snapshots, exclusions, repeat cycles, restart/month boundary and partial delivery failure. These are local tests; no Telegram message has been sent and production has not been deployed.

## Remaining work

Connect and validate the actual protected data feed, verify current runtime code, mount durable state, verify recipients, then enable and verify production delivery. Feed-access errors are currently logged without secrets; administrator alerts and direct initiator routing remain to be wired once verified recipient/source mappings exist.
