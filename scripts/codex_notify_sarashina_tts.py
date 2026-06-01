import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
QUEUE_DIR = Path(os.environ.get("TEMP", ".")) / "sarashina_tts_queue"
LOG_PATH = Path(os.environ.get("TEMP", ".")) / "codex_notify_sarashina_tts.log"
PID_PATH = Path(os.environ.get("TEMP", ".")) / "sarashina_tts_daemon.pid"
DEDUPE_PATH = Path(os.environ.get("TEMP", ".")) / "sarashina_tts_last_request.json"


def log(message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    try:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")
    except OSError:
        pass


def is_process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"if (Get-Process -Id {pid} -ErrorAction SilentlyContinue) {{ exit 0 }} else {{ exit 1 }}",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def daemon_running() -> bool:
    try:
        if not PID_PATH.exists():
            return False
        pid_text = PID_PATH.read_text(encoding="ascii", errors="ignore").strip()
        return bool(pid_text) and is_process_alive(int(pid_text))
    except Exception:
        return False


def resolve_python() -> str:
    root = Path(os.environ.get("SARASHINA_TTS_ROOT", Path.home() / "tools" / "sarashina2.2-tts"))
    venv_python = root / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def start_daemon() -> None:
    if daemon_running():
        return

    daemon = SKILL_ROOT / "scripts" / "sarashina_tts_daemon.py"
    python_exe = resolve_python()
    try:
        subprocess.Popen(
            [python_exe, str(daemon)],
            cwd=str(SKILL_ROOT),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            close_fds=True,
        )
        log(f"daemon start requested: {python_exe}")
    except Exception as exc:
        log(f"daemon start failed: {exc}")


def extract_message(payload: str) -> str:
    try:
        data = json.loads(payload) if payload else {}
    except Exception as exc:
        log(f"payload parse failed: {exc}")
        return payload.strip() if payload and payload.strip() else "Codexのターンが完了しました。"
    return data.get("last-assistant-message") or data.get("last_assistant_message") or "Codexのターンが完了しました。"


def enqueue(message: str) -> None:
    dedupe_seconds = int(os.environ.get("SARASHINA_TTS_DEDUPE_SECONDS", "20"))
    message_hash = hashlib.sha256(message.encode("utf-8")).hexdigest()
    now = time.time()
    try:
        if DEDUPE_PATH.exists():
            last = json.loads(DEDUPE_PATH.read_text(encoding="utf-8"))
            if last.get("hash") == message_hash and now - float(last.get("time", 0)) <= dedupe_seconds:
                log(f"duplicate skipped: {len(message)} chars")
                return
    except Exception as exc:
        log(f"dedupe read failed: {exc}")

    try:
        DEDUPE_PATH.write_text(json.dumps({"hash": message_hash, "time": now}, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        log(f"dedupe write failed: {exc}")

    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    request_id = f"{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
    request = {
        "id": request_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "message": message,
        "cwd": os.getcwd(),
    }
    tmp_path = QUEUE_DIR / f"{request_id}.tmp"
    req_path = QUEUE_DIR / f"{request_id}.json"
    tmp_path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
    tmp_path.replace(req_path)
    log(f"queued: {req_path.name} ({len(message)} chars)")


def main() -> int:
    payload = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read()
    message = extract_message(payload)
    enqueue(message)
    start_daemon()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

