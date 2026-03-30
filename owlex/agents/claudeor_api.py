#!/usr/bin/env python3
"""
Standalone script to call OpenRouter's chat completions API.

Uses only Python stdlib (urllib) — no external dependencies.
Reads the prompt from stdin, prints the response to stdout.

Required env vars:
    OPENROUTER_API_KEY  — OpenRouter API key
    CLAUDEOR_MODEL      — Model identifier (e.g. "deepseek/deepseek-r1")
"""

import json
import os
import sys
import urllib.request
import urllib.error

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def main() -> int:
    api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("CLAUDEOR_API_KEY")
    if not api_key:
        print("Error: OPENROUTER_API_KEY or CLAUDEOR_API_KEY env var is required", file=sys.stderr)
        return 1

    model = os.environ.get("CLAUDEOR_MODEL")
    if not model:
        print("Error: CLAUDEOR_MODEL env var is required", file=sys.stderr)
        return 1

    prompt = sys.stdin.read().strip()
    if not prompt:
        print("Error: no prompt provided on stdin", file=sys.stderr)
        return 1

    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")

    req = urllib.request.Request(
        OPENROUTER_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        print(f"Error: OpenRouter API returned {e.code}: {error_body}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"Error: Could not connect to OpenRouter: {e.reason}", file=sys.stderr)
        return 1

    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        print(f"Error: Unexpected API response: {json.dumps(body)}", file=sys.stderr)
        return 1

    print(content)
    return 0


if __name__ == "__main__":
    sys.exit(main())
