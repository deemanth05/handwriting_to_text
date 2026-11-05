"""Utility script to verify and connect FreeLLMAPI router.

Discovers the local FreeLLMAPI database, reads the unified_api_key,
tests connectivity to http://127.0.0.1:3001/v1, and writes backend/.env.
"""
import argparse
import os
import sqlite3
import sys
from pathlib import Path
import urllib.request
import urllib.error
import json

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
ENV_PATH = BACKEND_DIR / ".env"

CANDIDATE_DB_PATHS = [
    Path("C:/Users/deema/Desktop/projects/Exam_Revision_Planner/.cache/freellmapi/server/data/freellmapi.db"),
    ROOT / ".cache" / "freellmapi" / "server" / "data" / "freellmapi.db",
]


def find_freellmapi_db() -> Path | None:
    for candidate in CANDIDATE_DB_PATHS:
        if candidate.exists():
            return candidate
    return None


def get_unified_key(db_path: Path) -> str | None:
    try:
        with sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True) as conn:
            row = conn.execute("SELECT value FROM settings WHERE key='unified_api_key'").fetchone()
            if row and row[0]:
                return row[0]
    except Exception as e:
        print(f"[!] Error accessing FreeLLMAPI SQLite database: {e}", file=sys.stderr)
    return None


def get_enabled_providers(db_path: Path) -> list[str]:
    try:
        with sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True) as conn:
            rows = conn.execute("SELECT platform FROM api_keys WHERE enabled=1").fetchall()
            return [r[0] for r in rows]
    except Exception:
        return []


def test_freellmapi_connection(base_url: str, api_key: str) -> bool:
    models_url = f"{base_url.rstrip('/')}/models"
    req = urllib.request.Request(
        models_url,
        headers={"Authorization": f"Bearer {api_key}", "User-Agent": "PaperExtractionEngine/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode())
                model_count = len(data.get("data", []))
                print(f"[+] FreeLLMAPI router online at {base_url} ({model_count} models listed)")
                return True
    except urllib.error.URLError as e:
        print(f"[-] FreeLLMAPI router not responding at {base_url} ({e.reason})")
    except Exception as e:
        print(f"[-] FreeLLMAPI request error: {e}")
    return False


def update_backend_env(base_url: str, api_key: str):
    env_content = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env_content[k.strip()] = v.strip()

    env_content["FREELLM_BASE_URL"] = base_url
    env_content["FREELLM_API_KEY"] = api_key
    if "FREELLM_MODEL_A" not in env_content:
        env_content["FREELLM_MODEL_A"] = "google/gemini-2.0-flash-exp:free"
    if "FREELLM_MODEL_B" not in env_content:
        env_content["FREELLM_MODEL_B"] = "qwen/qwen-2.5-vl-72b-instruct:free"
    if "FREELLM_MODEL_C_STRUCT" not in env_content:
        env_content["FREELLM_MODEL_C_STRUCT"] = "auto"

    lines = [f"{k}={v}" for k, v in env_content.items()]
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[+] Saved FreeLLMAPI configuration to {ENV_PATH}")


def main():
    parser = argparse.ArgumentParser(description="Connect FreeLLMAPI router to Paper-to-Structured-Data Engine")
    parser.add_argument("--verify", action="store_true", help="Verify connection only")
    parser.add_argument("--base-url", default="http://127.0.0.1:3001/v1", help="FreeLLMAPI base URL")
    args = parser.parse_args()

    print("[*] Checking for FreeLLMAPI installation...")
    db_path = find_freellmapi_db()
    if not db_path:
        print("[-] FreeLLMAPI database not found in known locations.")
        sys.exit(1)

    print(f"[+] Found FreeLLMAPI database: {db_path}")
    api_key = get_unified_key(db_path)
    if not api_key:
        print("[-] Unified API key not found in FreeLLMAPI database.")
        sys.exit(1)

    providers = get_enabled_providers(db_path)
    print(f"[+] Active providers in FreeLLMAPI pool: {', '.join(providers) if providers else 'None'}")

    is_online = test_freellmapi_connection(args.base_url, api_key)

    if not args.verify or not ENV_PATH.exists():
        update_backend_env(args.base_url, api_key)

    if is_online:
        print("[+] FreeLLMAPI is connected and ready.")
    else:
        print("[!] FreeLLMAPI router process is not running. Start it on port 3001 when running live inference.")


if __name__ == "__main__":
    main()
