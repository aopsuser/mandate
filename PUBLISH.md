# Publish to GitHub

**Status: published** — <https://github.com/aopsuser/mandate>

The repository was pushed with `scripts/publish_api.py`, which uses the GitHub
REST API directly (this machine has no git binary and no Xcode Command Line
Tools). Re-running it is safe: it creates a new commit on top of `main` with the
current working tree.

```bash
GITHUB_TOKEN=... SSL_CERT_FILE=/etc/ssl/cert.pem python3 scripts/publish_api.py
```

`SSL_CERT_FILE` is only needed because the python.org build on this machine
ships without a CA bundle; the app now sets it automatically at startup
(`mandate/config.py`).

The notes below are kept for the alternative git-based path.

## Alternative: push with git

Everything is ready to push. This machine has no `git` binary (Xcode Command
Line Tools are not installed) and no GitHub credentials, so this path has to run
on your side.

### 1. Install git (one time, ~2 minutes)

```bash
xcode-select --install
```

Accept the dialog, wait for the install to finish, then confirm:

```bash
git --version
```

### 2. Run the publish script

```bash
./scripts/publish.sh <your-github-username>
```

The script:

- initializes the repository on `main`,
- commits with a local identity derived from your username,
- creates the public repo with GitHub CLI if `gh` is installed and authenticated,
  otherwise pushes to `https://github.com/<username>/mandate` (create an empty
  public repo with that name on github.com first),
- sets the description and topics.

If you prefer to do it by hand:

```bash
git init -b main
git add -A
git commit -m "Mandate: spend authority for autonomous agents"
git remote add origin https://github.com/<username>/mandate.git
git push -u origin main
```

## Verify the submission requirements

Open the repository and check:

- [ ] The **About** sidebar shows **MIT license** (GitHub detects the root
      `LICENSE` file automatically — do not rename it).
- [ ] The repository is **public**.
- [ ] The README renders with the architecture diagram.
- [ ] `data/` and `.env` are **not** in the repository (they are gitignored).

## Add credentials locally (never commit them)

```bash
cp .env.example .env     # already created for you
```

Then edit `.env`:

- `PAYPAL_CLIENT_ID` / `PAYPAL_CLIENT_SECRET` — from
  <https://developer.paypal.com/dashboard/applications/sandbox>
- `LLM_API_KEY` — any OpenAI-compatible endpoint (optional)

Verify in one command:

```bash
python3 scripts/check_setup.py
```

Restart the app and the header badge changes from `PayPal · mock` to
`PayPal · sandbox`. If the header still says mock, the `.env` file is not being
found or the keys are empty.

## Last step

Record the three-minute demo (see `docs/demo-script.md`), upload it to YouTube,
then fill the Devpost form from `docs/devpost-submission.md`.
