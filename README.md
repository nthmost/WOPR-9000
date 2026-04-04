# WOPR-9000

> Shall we play a game?

A document-grounded Claude terminal interface. Point it at a directory of markdown files. It reads everything. It answers anything.

Retro CRT terminal aesthetic. Pink phosphor. Chunky buttons. No nonsense.

---

## How it works

1. Put markdown files in `docs/`
2. Optionally add `docs/SYSTEM_PROMPT.md` to set Claude's persona and framing
3. Run the app
4. Ask anything

Claude answers from the documents. Full context. No truncation.

---

## Setup

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt

cp .env.example .env
# edit .env — add your ANTHROPIC_API_KEY and DOCS_DIR

python3 app.py
```

Then open `http://localhost:8090`

---

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | required | Your Anthropic API key |
| `DOCS_DIR` | `./docs` | Directory of markdown files to load |
| `WOPR_TITLE` | `WOPR-9000 // DOCUMENT INTERFACE` | Terminal bezel title |
| `WOPR_MODEL` | `claude-sonnet-4-6` | Claude model |
| `WOPR_MAX_TOKENS` | `8192` | Max response tokens |
| `PORT` | `8090` | Server port |

---

## SYSTEM_PROMPT.md

If `docs/SYSTEM_PROMPT.md` exists, it becomes the opening of the system prompt — setting Claude's persona, framing, and instructions. All other documents are appended as context after it.

Example:
```markdown
You are a knowledgeable guide to the documents below. 
Answer questions accurately and with full detail.
You can speak from multiple analytical frames.
```

---

## Hot reload

POST to `/reload` to reload all documents without restarting:

```bash
curl -X POST http://localhost:8090/reload
```

---

## Deploy

Behind Apache with basic auth:

```apache
<Location /wopr/>
    AuthType Basic
    AuthName "Restricted"
    AuthUserFile /path/to/.htpasswd
    Require valid-user
</Location>

ProxyPass /wopr/ http://127.0.0.1:8090/
ProxyPassReverse /wopr/ http://127.0.0.1:8090/
```

Run with gunicorn:
```bash
venv/bin/gunicorn app:app -b 127.0.0.1:8090 -w 2
```
