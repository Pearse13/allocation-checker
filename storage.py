"""
Config storage.

On Vercel the config lives in Upstash Redis (env vars KV_REST_API_URL /
KV_REST_API_TOKEN, or UPSTASH_REDIS_REST_URL / _TOKEN), seeded from
config.json the first time it's read. Locally, without those env vars, it
lives in .local-config.json so edits don't touch the committed config.json.
"""
import json
import os
import urllib.request

ROOT = os.path.dirname(__file__)
SEED_PATH = os.path.join(ROOT, "config.json")
LOCAL_PATH = os.path.join(ROOT, ".local-config.json")
KEY = "sheetcheck:config"


def _redis_creds():
    url = os.environ.get("KV_REST_API_URL") or os.environ.get("UPSTASH_REDIS_REST_URL")
    token = os.environ.get("KV_REST_API_TOKEN") or os.environ.get("UPSTASH_REDIS_REST_TOKEN")
    return (url, token) if url and token else None


def _redis(*command):
    url, token = _redis_creds()
    req = urllib.request.Request(
        url,
        data=json.dumps(list(command)).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as res:
        return json.load(res)["result"]


def _seed():
    with open(SEED_PATH) as f:
        return json.load(f)


def load_config():
    if _redis_creds():
        raw = _redis("GET", KEY)
        if raw:
            return json.loads(raw)
        config = _seed()
        save_config(config)
        return config

    if os.path.exists(LOCAL_PATH):
        with open(LOCAL_PATH) as f:
            return json.load(f)
    return _seed()


def save_config(config):
    if _redis_creds():
        _redis("SET", KEY, json.dumps(config))
        return
    with open(LOCAL_PATH, "w") as f:
        json.dump(config, f, indent=2)
