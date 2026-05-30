#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request


BASE_URL = "http://127.0.0.1:5000/api/power-mode"


def request(method: str, payload: dict | None = None) -> dict:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE_URL, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    action = "status"
    if len(sys.argv) > 1:
        action = sys.argv[1].strip().lower()

    if action == "status":
        result = request("GET")
    elif action in {"standby", "wake", "toggle"}:
        result = request("POST", {"action": action})
    else:
        print("usage: standby_cli.py [status|standby|wake|toggle]")
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
