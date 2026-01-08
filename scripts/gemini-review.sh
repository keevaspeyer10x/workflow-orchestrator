#!/bin/bash
# Gemini Code Review via OpenRouter
# Usage: ./scripts/gemini-review.sh <file>

FILE="$1"
if [ -z "$FILE" ]; then
    echo "Usage: gemini-review.sh <file>"
    exit 1
fi

if [ ! -f "$FILE" ]; then
    echo "File not found: $FILE"
    exit 1
fi

# Load secrets if available
if [ -n "$SECRETS_PASSWORD" ] && [ -f ".secrets.enc" ]; then
    eval $(echo "$SECRETS_PASSWORD" | openssl enc -aes-256-cbc -pbkdf2 -d -in .secrets.enc -pass stdin 2>/dev/null | \
        grep -E "^[A-Z_]+:" | while IFS=': ' read -r key value; do
            value="${value%\"}"
            value="${value#\"}"
            echo "export $key='$value'"
        done)
fi

if [ -z "$OPENROUTER_API_KEY" ]; then
    echo "Error: OPENROUTER_API_KEY not set"
    exit 1
fi

CONTENT=$(cat "$FILE" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))")

python3 << EOF
import urllib.request
import json
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

file_content = $CONTENT

data = json.dumps({
    "model": "google/gemini-2.0-flash-001",
    "messages": [{
        "role": "user",
        "content": f"Review this code for security issues, bugs, and improvements. Be concise.\n\nFile: $FILE\n\n\`\`\`\n{file_content}\n\`\`\`"
    }]
}).encode()

req = urllib.request.Request(
    'https://openrouter.ai/api/v1/chat/completions',
    data=data,
    headers={
        'Authorization': 'Bearer $OPENROUTER_API_KEY',
        'Content-Type': 'application/json'
    }
)

with urllib.request.urlopen(req, context=ctx, timeout=60) as resp:
    result = json.loads(resp.read().decode())
    print(result['choices'][0]['message']['content'])
EOF
