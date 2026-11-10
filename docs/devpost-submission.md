# Devpost submission draft

Fill in the links, then paste each section into the matching field. Written in
first-person plural — swap “we” for “I” if you are submitting solo.

---

## Project name

**Mandate**

## Elevator pitch (≤ 200 characters)

Mandate gives AI agents a signed, scoped, revocable budget — so they can pay
with PayPal autonomously, but never outside the limits a human set.

## Inspiration

Agents can already browse, plan, and decide. The one thing we still do not let
them do is spend money — because a card number is all-or-nothing. It cannot say
“up to $150 per purchase, only at these merchants, only for footwear, ask me
above $100, and stop the moment I say so.”

That is not a model problem. It is an authorization problem. Mandate is the
missing primitive: delegated spending authority that an AI agent can carry and a
payment gateway can verify.

## What it does

A human issues a mandate: total budget, per-transaction cap, approval threshold,
merchant allowlist, authorized categories, velocity limit, and expiry.

The agent receives an HMAC-SHA256 signed capability token. On every purchase
attempt, the gateway:

1. verifies the token signature — the agent cannot edit its own limits;
2. runs the policy engine: status, expiry, merchant, category, per-transaction
   cap, remaining budget, and velocity;
3. if the amount is above the approval threshold, stops and asks the human;
4. otherwise creates and captures a PayPal Orders v2 payment;
5. writes an auditable ledger entry for every check and every order.

When the human approves, the mandate is re-checked before capture, so a
revocation or expiry that happened while the request was pending still wins.
Revocation itself is server-side and instant: the token remains cryptographically
valid, but the gateway refuses it.

The demo storefront is arranged to show all three outcomes in one minute: an
autonomous purchase inside the rails, a cheaper listing blocked because the
marketplace is not on the allowlist followed by a human approval, and an instant
block after revocation.

## How we built it

- **Backend:** Python 3 standard library only. `python3 app.py` and it runs —
  no `pip install`, no build step, no database, no framework.
- **Payments:** PayPal Orders v2 — create order, capture order, plus a webhook
  receiver with signature verification. Runs against the PayPal sandbox when
  credentials are set, and falls back to a clearly labelled mock so judges can
  run it with zero setup.
- **Authority:** HMAC-SHA256 signed capability tokens. Token limits are the
  authority; revocation lives server-side so it can change independently.
- **Policy:** a pure, fully unit-tested engine that returns a verdict *and* a
  human-readable reason for every rule it checked.
- **AI:** an OpenAI-compatible planner converts a goal into a structured search
  plan, with a deterministic heuristic fallback. The model proposes; the policy
  engine disposes.
- **Frontend:** hand-written HTML/CSS/JS with a live decision trace, approval
  queue, and ledger. No framework and no build step.

## Challenges we ran into

- **Explainability over booleans.** A blocked payment is useless to a user
  unless they can see which rule fired. We rebuilt the policy output as a
  per-check audit trail, and that became the core of the UI.
- **The model must never be the security boundary.** It was tempting to let the
  LLM judge whether a purchase was allowed. We kept every authorization decision
  in deterministic code and let the model only plan the search.
- **Approval races.** Between “agent asks” and “human approves”, the mandate can
  be revoked, expire, or run out of budget. The gateway re-evaluates before
  capture.
- **Zero dependencies.** Without a web framework we wrote the HTTP routing,
  JSON persistence, and token layer ourselves — which made the security model
  easier to explain and the whole thing trivial to run.

## Accomplishments we are proud of

- A genuinely working prototype that runs with a single command and no setup.
- Tamper-evident spending limits: rewriting the budget in the token fails
  signature verification.
- Human-in-the-loop that is actually enforced, not decorative.
- 16 unit tests covering every policy rail and the token layer.
- A demo that tells the whole story — autonomy, escalation, revocation — in
  under three minutes.

## What we learned

- Agentic commerce is an authorization problem before it is a UX problem.
- Users and merchants will need explainable decisions, not risk scores.
- The right split is: the model proposes, deterministic policy disposes.
- A capability token plus a server-side revocation list is a surprisingly small
  amount of code for a large amount of trust.

## What's next for Mandate

- Vault a funding instrument per mandate, so agents never see payment details.
- A merchant-side SDK to accept a `mandate_token` at checkout.
- Sub-mandates: an agent delegating a narrower budget to a specialist agent.
- Exportable audit packs and spend analytics for finance teams.
- Replace the mock catalog with a real merchant feed.

## Built with

`python` · `paypal-orders-v2` · `hmac-sha256` · `html` · `css` · `javascript` ·
`llm` · `openai-compatible`

## Try it out

- **GitHub repository:** <https://github.com/aopsuser/mandate>
- **Demo video:** `<add public YouTube URL, under 3 minutes>`
- **Run locally:** `python3 app.py` → <http://127.0.0.1:3000>

---

## Publishing status

**Done — repository is live:** <https://github.com/aopsuser/mandate>

Verified through the GitHub API:

- Public repository, default branch `main`.
- 28 files committed; `.env` and `data/` are not present.
- Description and all six topics set.
- GitHub reports the license as **MIT** (it appears in the About sidebar).

The remaining work is the video and the Devpost form.

### 1. Record and upload the video

Follow [`demo-script.md`](demo-script.md). Reset the demo first, record at
1440×900 or larger, keep the final cut under 3:00, and upload to YouTube as
**Public** (not Unlisted — judges need to open it without an account).

### 2. Substitute the video link

| Placeholder | Replace with |
|---|---|
| `<add public YouTube URL, under 3 minutes>` | your public YouTube URL |

### 3. Fill the Devpost form

Paste each section above into the matching field:

- **Project name** → “Mandate”
- **Elevator pitch** → the ≤200-character line
- **Inspiration / What it does / How we built it / Challenges / Accomplishments /
  What we learned / What's next** → the matching sections
- **Built with** → the tag list
- **Try it out** → the repository URL above and the video URL
- **AI tools used** → the LLM endpoint and model if you set `LLM_API_KEY`,
  otherwise “deterministic heuristic planner (no model required)” — plus
  **PayPal Orders v2** as the payments integration.

---

### Before you submit

- [x] Repository is public and opens without authentication.
- [x] About sidebar shows **MIT license**.
- [x] `data/` and `.env` are absent from the repository.
- [ ] Video is public on YouTube and under 3:00.
- [ ] Video URL replaces the placeholder in “Try it out”.
- [ ] AI tools listed on the form.
- [ ] Demo reset in the recording so the ledger starts empty.
- [ ] Re-check eligibility rules for every team member (Section 3).
