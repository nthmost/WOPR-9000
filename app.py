"""
WOPR-9000
A document-grounded Claude terminal interface.

Point it at a directory of markdown files.
It reads everything. It answers anything.
Shall we play a game?
"""

import os
import json
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, static_folder='.')
client = Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])

# ── Configuration ──────────────────────────────────────────────────────────

DOCS_DIR   = Path(os.environ.get('DOCS_DIR', './docs'))
MODEL      = os.environ.get('WOPR_MODEL', 'claude-sonnet-4-6')
MAX_TOKENS = int(os.environ.get('WOPR_MAX_TOKENS', '8192'))
TITLE      = os.environ.get('WOPR_TITLE', 'WOPR-9000 // DOCUMENT INTERFACE')
PORT       = int(os.environ.get('PORT', '8090'))

# ── Document Loading ────────────────────────────────────────────────────────

def load_documents():
    """Load all .md and .txt files from DOCS_DIR recursively."""
    docs = {}
    if not DOCS_DIR.exists():
        print(f"Warning: DOCS_DIR {DOCS_DIR} does not exist")
        return docs

    for ext in ('*.md', '*.txt'):
        for f in sorted(DOCS_DIR.rglob(ext)):
            # Use path relative to DOCS_DIR as key
            key = str(f.relative_to(DOCS_DIR))
            try:
                docs[key] = f.read_text(encoding='utf-8')
            except Exception as e:
                print(f"Could not read {f}: {e}")

    return docs


def build_system_prompt(docs):
    """
    Build the system prompt from:
    1. SYSTEM_PROMPT.md in DOCS_DIR (if present) — sets the persona/framing
    2. All other documents appended as context
    """
    parts = []

    # Check for custom system prompt file
    system_file = DOCS_DIR / 'SYSTEM_PROMPT.md'
    if system_file.exists():
        parts.append(system_file.read_text(encoding='utf-8').strip())
        parts.append('\n\n---\n\n# DOCUMENTS\n')
    else:
        parts.append(
            "You are a knowledgeable assistant grounded in the documents provided below. "
            "Answer questions accurately and thoroughly from the source material. "
            "Be as detailed as the question warrants. Do not artificially truncate responses."
        )
        parts.append('\n\n---\n\n# DOCUMENTS\n')

    # Append all docs except SYSTEM_PROMPT.md
    for name, content in docs.items():
        if name == 'SYSTEM_PROMPT.md':
            continue
        parts.append(f"\n## {name}\n\n{content}\n")

    return '\n'.join(parts)


def reload():
    global DOCUMENTS, SYSTEM_PROMPT
    DOCUMENTS = load_documents()
    SYSTEM_PROMPT = build_system_prompt(DOCUMENTS)
    doc_count = len([k for k in DOCUMENTS if k != 'SYSTEM_PROMPT.md'])
    print(f"Loaded {doc_count} documents · {len(SYSTEM_PROMPT):,} chars in system prompt")
    return doc_count


DOCUMENTS = {}
SYSTEM_PROMPT = ''
reload()

# ── Routes ──────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/styles.css')
def styles():
    return send_from_directory('.', 'styles.css')

@app.route('/config')
def config():
    """Return UI configuration."""
    return jsonify({'title': TITLE})

@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json()
    messages = data.get('messages', [])

    if not messages:
        return jsonify({'error': 'No messages provided'}), 400

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
        return jsonify({
            'content': response.content[0].text,
            'usage': {
                'input': response.usage.input_tokens,
                'output': response.usage.output_tokens,
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/files')
def list_files():
    """Return list of files available for direct viewing.
    Only shows files at the root of DOCS_DIR — subdirectories are
    data sources for Claude context, not human-browsable documents.
    """
    if not DOCS_DIR.exists():
        return jsonify([])
    files = []
    for ext in ('*.md', '*.txt'):
        for f in sorted(DOCS_DIR.glob(ext)):  # glob not rglob — root only
            if f.name in ('SYSTEM_PROMPT.md',):
                continue
            files.append({
                'name': f.name,
                'path': str(f.relative_to(DOCS_DIR)),
            })
    return jsonify(files)


@app.route('/file', methods=['POST'])
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
def reload_route():
    """Hot-reload documents without restarting."""
    doc_count = reload()
    return jsonify({'status': 'ok', 'documents': doc_count})

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=PORT, debug=False)
