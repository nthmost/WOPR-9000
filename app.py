"""
WOPR-9000
A document-grounded Claude terminal interface.

Point it at a directory of markdown files.
It reads everything. It answers anything.
Shall we play a game?
"""

import os
import json
import hashlib
import urllib.request
import urllib.parse
from pathlib import Path
from functools import wraps
from flask import Flask, request, jsonify, session, redirect, url_for, render_template, Response
from werkzeug.middleware.proxy_fix import ProxyFix
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change-this-in-production-wopr9000')
app.wsgi_app = ProxyFix(app.wsgi_app, x_prefix=1)

# ── Configuration ──────────────────────────────────────────────────────────

DOCS_DIR      = Path(os.environ.get('DOCS_DIR', './docs'))
MODEL         = os.environ.get('WOPR_MODEL', 'claude-sonnet-4-6')
MAX_TOKENS    = int(os.environ.get('WOPR_MAX_TOKENS', '16000'))
TITLE         = os.environ.get('WOPR_TITLE', 'WOPR-9000 // DOCUMENT INTERFACE')
PORT          = int(os.environ.get('PORT', '8090'))
REQUIRE_AUTH  = os.environ.get('REQUIRE_AUTH', 'false').lower() in ('true', '1', 'yes')
MEDIAWIKI_URL = os.environ.get('MEDIAWIKI_URL', '')

ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

# Parse AUTH_USERS: "user1:sha256hash,user2:sha256hash"
def _parse_users():
    raw = os.environ.get('AUTH_USERS', '')
    users = {}
    for entry in raw.split(','):
        entry = entry.strip()
        if ':' in entry:
            u, h = entry.split(':', 1)
            users[u.strip()] = h.strip()
    return users

USERS = _parse_users()

# ── Document Loading ────────────────────────────────────────────────────────

def load_documents():
    """Load all .md and .txt files from DOCS_DIR recursively."""
    docs = {}
    if not DOCS_DIR.exists():
        print(f"Warning: DOCS_DIR {DOCS_DIR} does not exist")
        return docs
    for ext in ('*.md', '*.txt'):
        for f in sorted(DOCS_DIR.rglob(ext)):
            key = str(f.relative_to(DOCS_DIR))
            try:
                docs[key] = f.read_text(encoding='utf-8')
            except Exception as e:
                print(f"Could not read {f}: {e}")
    return docs


def build_system_prompt(docs):
    """
    Build the system prompt from SYSTEM_PROMPT.md and FILES/OVERVIEW.md only.
    All other documents are fetched on demand via the fetch_document tool.
    """
    parts = []
    system_file = DOCS_DIR / 'SYSTEM_PROMPT.md'
    if system_file.exists():
        parts.append(system_file.read_text(encoding='utf-8').strip())
    else:
        parts.append(
            "You are a knowledgeable assistant. "
            "Use the fetch_document tool to retrieve source material as needed."
        )
    overview_file = DOCS_DIR / 'FILES' / 'OVERVIEW.md'
    if overview_file.exists():
        parts.append('\n\n---\n\n# OVERVIEW\n\n' + overview_file.read_text(encoding='utf-8'))
    parts.append(
        "\n\n---\n\n"
        "You have access to a fetch_document tool to retrieve specific documents from the corpus. "
        "Use it when you need source material to answer a question accurately. "
        "Fetch only what is relevant to the specific question. "
        "The document index in OVERVIEW.md lists all available files and what each contains."
    )
    return '\n'.join(parts)


def fetch_document_content(path):
    """Safely fetch a document from DOCS_DIR by relative path."""
    target = (DOCS_DIR / path).resolve()
    if not str(target).startswith(str(DOCS_DIR.resolve())):
        return "Error: invalid path"
    if not target.exists():
        return f"Error: document not found: {path}"
    try:
        return target.read_text(encoding='utf-8')
    except Exception as e:
        return f"Error reading document: {e}"


TOOLS = [
    {
        "name": "fetch_document",
        "description": (
            "Fetch the full content of a specific document from the corpus. "
            "Use this when you need primary source material to answer a question accurately. "
            "Fetch only the documents relevant to the specific question being asked."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "Relative path within docs/, exactly as listed in the document index. "
                        "Examples: 'DNS_Episode_Feb7_2026.md', "
                        "'semipublic/admin-chat__2026-01.md', "
                        "'private/DM_mcint_nthmost__2026-02.md'"
                    )
                }
            },
            "required": ["path"]
        }
    }
]


def _reload():
    global DOCUMENTS, SYSTEM_PROMPT
    DOCUMENTS = load_documents()
    SYSTEM_PROMPT = build_system_prompt(DOCUMENTS)
    doc_count = len([k for k in DOCUMENTS if k != 'SYSTEM_PROMPT.md'])
    print(f"Loaded {doc_count} documents · {len(SYSTEM_PROMPT):,} chars in system prompt")
    return doc_count


DOCUMENTS = {}
SYSTEM_PROMPT = ''
_reload()

# ── Auth ────────────────────────────────────────────────────────────────────

def check_local_password(username, password):
    expected = USERS.get(username)
    if not expected:
        return False
    return hashlib.sha256(password.encode()).hexdigest() == expected


def check_wiki_password(username, password):
    if not MEDIAWIKI_URL:
        return False
    try:
        req = urllib.request.Request(
            MEDIAWIKI_URL + '?' + urllib.parse.urlencode({
                'action': 'query', 'meta': 'tokens', 'type': 'login', 'format': 'json'
            }),
            headers={'User-Agent': 'wopr9000-login/1.0'}
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
        token = data['query']['tokens']['logintoken']
        payload = urllib.parse.urlencode({
            'action': 'login', 'lgname': username,
            'lgpassword': password, 'lgtoken': token, 'format': 'json',
        }).encode()
        req2 = urllib.request.Request(
            MEDIAWIKI_URL, data=payload,
            headers={'User-Agent': 'wopr9000-login/1.0',
                     'Content-Type': 'application/x-www-form-urlencoded'}
        )
        with urllib.request.urlopen(req2, timeout=8) as r:
            result = json.loads(r.read())
        return result.get('login', {}).get('result') == 'Success'
    except Exception:
        return False


def auth_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if REQUIRE_AUTH and not session.get('authenticated'):
            if request.is_json or request.path.startswith('/chat'):
                return jsonify({'error': 'Unauthorized'}), 401
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# ── Routes ──────────────────────────────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    if not REQUIRE_AUTH:
        return redirect(url_for('index'))
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        auth_type = request.form.get('auth_type', 'local')
        if auth_type == 'wiki' and MEDIAWIKI_URL:
            if check_wiki_password(username, password):
                session['authenticated'] = True
                session['username'] = username + ' (wiki)'
                return redirect(url_for('index'))
            error = 'Wiki login failed.'
        else:
            if check_local_password(username, password):
                session['authenticated'] = True
                session['username'] = username
                return redirect(url_for('index'))
            error = 'Bad command or file name.'
    return render_template('login.html', error=error, mediawiki_url=MEDIAWIKI_URL)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login') if REQUIRE_AUTH else url_for('index'))


@app.route('/')
@auth_required
def index():
    username = session.get('username', '') if REQUIRE_AUTH else ''
    return render_template('index.html', title=TITLE, username=username,
                           require_auth=REQUIRE_AUTH)


@app.route('/config')
def config():
    return jsonify({'title': TITLE})


@app.route('/chat', methods=['POST'])
@auth_required
def chat():
    data = request.get_json()
    messages = data.get('messages', [])
    if not messages:
        return jsonify({'error': 'No messages provided'}), 400
    if not ANTHROPIC_API_KEY:
        return jsonify({'error': 'ANTHROPIC_API_KEY not set'}), 500

    client = Anthropic(api_key=ANTHROPIC_API_KEY)

    def generate():
        try:
            internal_messages = list(messages)
            input_tokens = 0
            output_tokens = 0

            while True:
                response = client.messages.create(
                    model=MODEL,
                    max_tokens=MAX_TOKENS,
                    thinking={'type': 'enabled', 'budget_tokens': 5000},
                    system=SYSTEM_PROMPT,
                    tools=TOOLS,
                    messages=internal_messages,
                )

                input_tokens += response.usage.input_tokens
                output_tokens += response.usage.output_tokens

                if response.stop_reason != 'tool_use':
                    for block in response.content:
                        if getattr(block, 'type', None) == 'text':
                            yield f"data: {json.dumps({'text': block.text})}\n\n"
                    break

                # Process tool calls
                tool_results = []
                for block in response.content:
                    if getattr(block, 'type', None) == 'tool_use':
                        path = block.input.get('path', '')
                        yield f"data: {json.dumps({'status': f'[ LOADING: {path} ]'})}\n\n"
                        content = fetch_document_content(path)
                        tool_results.append({
                            'type': 'tool_result',
                            'tool_use_id': block.id,
                            'content': content,
                        })

                internal_messages.append({
                    'role': 'assistant',
                    'content': [b.model_dump() for b in response.content],
                })
                internal_messages.append({
                    'role': 'user',
                    'content': tool_results,
                })

            yield f"data: {json.dumps({'done': True, 'usage': {'input': input_tokens, 'output': output_tokens}})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


@app.route('/files')
@auth_required
def list_files():
    """Return list of files available for direct viewing.
    Only shows files inside docs/FILES/ — everything else under docs/
    is Claude context data, not human-browsable.
    """
    files_dir = DOCS_DIR / 'FILES'
    if not files_dir.exists():
        return jsonify([])
    files = []
    for ext in ('*.md', '*.txt'):
        for f in sorted(files_dir.glob(ext)):
            files.append({'name': f.name, 'path': str(f.relative_to(DOCS_DIR))})
    return jsonify(files)


@app.route('/file', methods=['POST'])
@auth_required
def get_file():
    """Return the content of a specific file."""
    data = request.get_json()
    path = data.get('path', '')
    target = (DOCS_DIR / path).resolve()
    if not str(target).startswith(str(DOCS_DIR.resolve())):
        return jsonify({'error': 'Invalid path'}), 400
    if not target.exists():
        return jsonify({'error': 'File not found'}), 404
    return jsonify({'content': target.read_text(encoding='utf-8'), 'name': target.name})


@app.route('/reload', methods=['POST'])
@auth_required
def reload_route():
    """Hot-reload documents without restarting."""
    doc_count = _reload()
    return jsonify({'status': 'ok', 'documents': doc_count})


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=PORT, debug=False)
