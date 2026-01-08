#!/bin/bash
# Decrypt project secrets using SOPS and age
# Requires SOPS_AGE_KEY environment variable to be set

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SECRETS_FILE="$SCRIPT_DIR/secrets.enc.yaml"

if [ -z "$SOPS_AGE_KEY" ]; then
    echo "Error: SOPS_AGE_KEY environment variable not set"
    echo "Please set it to the age secret key for this project"
    exit 1
fi

if [ ! -f "$SECRETS_FILE" ]; then
    echo "Error: Encrypted secrets file not found at $SECRETS_FILE"
    exit 1
fi

# Decrypt and output to stdout (for piping to other commands)
# Use: eval $(./decrypt-secrets.sh --env) to export as environment variables
if [ "$1" == "--env" ]; then
    sops -d "$SECRETS_FILE" | python3 -c "
import sys, yaml
data = yaml.safe_load(sys.stdin)
def flatten(d, prefix=''):
    for k, v in d.items():
        key = f'{prefix}_{k}'.upper() if prefix else k.upper()
        if isinstance(v, dict):
            flatten(v, key)
        else:
            print(f'export {key}=\"{v}\"')
flatten(data)
"
elif [ "$1" == "--json" ]; then
    sops -d --output-type json "$SECRETS_FILE"
elif [ "$1" == "--get" ] && [ -n "$2" ]; then
    # Get a specific key using yq-style path
    sops -d "$SECRETS_FILE" | python3 -c "
import sys, yaml
data = yaml.safe_load(sys.stdin)
keys = '$2'.split('.')
for k in keys:
    data = data.get(k, {})
print(data if data else '')
"
else
    sops -d "$SECRETS_FILE"
fi
