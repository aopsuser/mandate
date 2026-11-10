# Three-minute demo script

Presentation is 20% of the judging score, and the video is the artefact judges
actually watch. Treat this as a shoot, not a screen recording.

## Pre-flight (do this before recording)

1. `python3 app.py` → open <http://127.0.0.1:3000>
2. Click **Reset demo** so the mandate is `active`, spent `$0.00`, ledger empty.
3. Use a window at **1440×900 or larger** and browser zoom at **100%**. The
   layout is designed for this size.
4. Close other tabs, hide the bookmarks bar, mute notifications.
5. Run all three acts once to warm up, then **Reset demo** again.
6. Payment mode is fine either way. Mock mode is clearly labelled `PayPal · mock`.
   If you have sandbox credentials, record with them — the header shows
   `PayPal · sandbox` and the ledger shows real sandbox order IDs.
7. Record at 1080p, 30 or 60 fps. Capture the whole browser window.

## Timeline

| Time | Beat | Action |
|---|---|---|
| 0:00–0:18 | Hook: agents can decide, but not spend | Talk to camera over the UI |
| 0:18–0:38 | The mandate | Hover the left panel |
| 0:38–1:05 | Act ① Inside the rails | Click **①**, let the trace run |
| 1:05–1:55 | Act ② Hit the wall + approval | Click **②**, then **Approve & pay** |
| 1:55–2:25 | Act ③ Pull the plug | Click **Revoke mandate**, then **③** |
| 2:25–2:48 | Tamper test | Click **Tamper test** |
| 2:48–3:00 | Close | Back to the full UI |

## Narration

> **0:00 — Hook.**
> AI agents can plan, browse, and decide. But there is one thing we still do not
> let them do: spend money. Because a credit card has no idea what an agent is
> allowed to buy.

> **0:12 — The idea.**
> Mandate is the authorization layer between an agent and a payment method.
> A human grants a signed, scoped, revocable budget. The agent can pay with
> PayPal — but only inside those rails.

> **0:22 — The mandate.**
> This is Scout's mandate. Four hundred dollars in total, one hundred and
> fifty per transaction, and anything under one hundred is auto-approved.
> It can only shop at Stride Run and Runner's Depot, only for footwear, and the
> authority expires in twenty-four hours.

> **0:40 — Act ①.**
> Inside the rails. I ask for running shoes under a hundred dollars.
> Scout plans, searches the catalog, and the gateway checks six rules:
> status, expiry, merchant, category, per-transaction cap, and remaining budget.
> All pass. It opens a PayPal order and captures it. Eighty-nine dollars.
> No human involved.

> **1:05 — Act ②.**
> Now a harder request: the cheapest Aero Tempo I can find.
> The cheapest listing is on a marketplace. The gateway blocks it — that
> merchant is not on the allowlist. So Scout falls back to an authorized store.
> But this one is a hundred and eighteen dollars, above the hundred-dollar
> approval threshold. The agent stops.

> **1:30 — Human in the loop.**
> This is the moment that matters. The agent has the money, the item is in
> stock, and it still cannot proceed. I am the human — I approve.
> The gateway re-checks the mandate before charging, then captures the payment.
> One hundred and eighteen dollars.

> **1:55 — Act ③.**
> Now the part that matters most: cutting it off. I revoke the mandate.
> Scout tries to buy again. The token is still cryptographically valid — but the
> revocation check stops it. Nothing is charged. Instantly.

> **2:25 — Tamper test.**
> The agent holds a signed token. If it tries to rewrite its own budget —
> the signature fails. It cannot edit its own limits, because it never holds the
> signing key.

> **2:48 — Close.**
> Mandate. Scoped authority for autonomous agents. Signed, explainable,
> revocable — and settled through PayPal.

## Edit notes

- Cut the dead air between clicking and the first trace step; speed-ramp the
  step animation 2–4× so each act lands in 20–30 seconds.
- Zoom-punch the approval card, the blocked marketplace check, and the tamper
  result. Those three frames are the whole story.
- Add a lower-third per act: `① Autonomous inside limits`, `② Blocked, then
  escalated`, `③ Revoked instantly`.
- Keep the ledger visible when it fills — judges should see the payment records.
- Do **not** let the final cut exceed 3:00. Judges are not required to watch
  past that point.

## Submission checklist

- [ ] Video under 3 minutes, public on YouTube, link on the Devpost form
- [ ] Video shows the project actually running
- [ ] Repo public on GitHub with the **license visible in the About section**
- [ ] README has complete setup and run instructions
- [ ] Text description written (problem, what it does, how PayPal + AI are used)
- [ ] Tools listed on the form (LLM endpoint or "heuristic planner"; PayPal Orders v2)
- [ ] Demo is genuinely runnable, not a mockup
