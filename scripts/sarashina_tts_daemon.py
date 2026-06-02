import json
import os
import re
import subprocess
import sys
import time
import traceback
import urllib.request
from datetime import datetime
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
QUEUE_DIR = Path(os.environ.get("TEMP", ".")) / "sarashina_tts_queue"
LOG_PATH = Path(os.environ.get("TEMP", ".")) / "sarashina_tts_debug.log"
PID_PATH = Path(os.environ.get("TEMP", ".")) / "sarashina_tts_daemon.pid"
PLAYING_PID_PATH = Path(os.environ.get("TEMP", ".")) / "sarashina_tts_playing.pid"
SETTINGS_PATH = SKILL_ROOT / "settings.json"
DEFAULT_PROMPT_URL = "https://huggingface.co/sbintuitions/sarashina2.2-tts/resolve/main/samples/zero_shot/synthesized_A.wav"
DEFAULT_PROMPT_TEXT = "東京から金沢までは新幹線を利用するのが便利で、所要時間は約２時間半です。"
DEFAULT_MAX_CHARS = 750
DEFAULT_MAX_TOKENS = 512
DEFAULT_CHUNK_CHARS = 45
DEFAULT_MIN_TOKENS = 96
DEFAULT_TOKENS_PER_CHAR = 8
DEFAULT_TEMPERATURE = 0.9
DEFAULT_TOP_P = 0.95


def log(message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    try:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")
    except OSError:
        pass


def beep() -> None:
    try:
        subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", "[Console]::Beep(800,500); Start-Sleep -Milliseconds 150; [Console]::Beep(1000,500)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        pass


def show_toast(title: str, body: str) -> None:
    escaped_title = title.replace("'", "''")
    escaped_body = body.replace("'", "''")
    command = (
        "try { "
        "Import-Module BurntToast -ErrorAction Stop; "
        f"New-BurntToastNotification -Text '{escaped_title}', '{escaped_body}' | Out-Null "
        "} catch { }"
    )
    try:
        subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", command],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        pass


def is_process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", f"if (Get-Process -Id {pid} -ErrorAction SilentlyContinue) {{ exit 0 }} else {{ exit 1 }}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def playback_active() -> bool:
    try:
        if not PLAYING_PID_PATH.exists():
            return False
        pid_text = PLAYING_PID_PATH.read_text(encoding="ascii", errors="ignore").strip()
        return bool(pid_text) and is_process_alive(int(pid_text))
    except Exception:
        return False


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`[^`]*`", "", text)
    text = re.sub(r"(?m)^#+\s+", "", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\[([^\]]*)\]\([^\)]*\)", r"\1", text)
    text = re.sub(r"\*\*([^*]*)\*\*", r"\1", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\1", text)
    text = re.sub(r"(?m)^[\s]*[-*]\s+", "", text)
    text = re.sub(r"(?m)^\|.*\|$", "", text)
    text = re.sub(r"[\U0001F000-\U0001FFFF]", "", text)
    text = re.sub(r"[⌀-➿─-▟■-◿]", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = [line.strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line).strip()


def truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    for mark in ("。", "！", "？", ". ", "、"):
        idx = text.rfind(mark, 0, max_chars)
        if idx >= int(max_chars * 0.3):
            return text[: idx + len(mark)].strip()
    return text[:max_chars].strip()


def prepare_tts_text(message: str) -> str:
    max_chars = int(os.environ.get("SARASHINA_TTS_MAX_CHARS", str(DEFAULT_MAX_CHARS)))
    text = truncate_text(clean_text(message), max_chars)
    text = re.sub(r"([^、。！？])\n", r"\1、", text)
    text = text.replace("\n", "")
    if text and text[-1] not in "。！？.!?":
        text += "。"
    return text


def split_tts_text(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    current = ""
    parts = re.findall(r".+?[。！？.!?]+|.+$", text)

    def push(value: str) -> None:
        value = value.strip()
        if value:
            chunks.append(value)

    for part in parts:
        part = part.strip()
        while len(part) > max_chars:
            cut = -1
            for mark in ("。", "！", "？", ". ", "、", " "):
                idx = part.rfind(mark, 0, max_chars)
                if idx > int(max_chars * 0.35):
                    cut = idx + len(mark)
                    break
            if cut < 0:
                cut = max_chars
            segment = part[:cut].strip()
            if current:
                push(current)
                current = ""
            push(segment)
            part = part[cut:].strip()

        if not part:
            continue
        if not current:
            current = part
        elif len(current) + len(part) <= max_chars:
            current += part
        else:
            push(current)
            current = part

    push(current)
    return chunks


def ensure_default_prompt(path: Path) -> None:
    if path.exists() and path.stat().st_size > 1000:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    log(f"downloading default prompt: {DEFAULT_PROMPT_URL}")
    urllib.request.urlretrieve(DEFAULT_PROMPT_URL, str(path))
    log(f"default prompt saved: {path}")


def load_settings() -> dict:
    if not SETTINGS_PATH.exists():
        return {}
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
        log(f"settings ignored because root is not object: {SETTINGS_PATH}")
    except Exception as exc:
        log(f"settings load failed: {exc}")
    return {}


def resolve_path(value: str, base: Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return base / path


def combine_audio_files(paths: list[str], output_path: Path, sample_rate: int) -> Path:
    import numpy as np
    import soundfile as sf

    arrays = []
    for i, path in enumerate(paths):
        data, sr = sf.read(path, dtype="float32", always_2d=True)
        if sr != sample_rate:
            raise RuntimeError(f"unexpected sample rate: {path}: {sr} != {sample_rate}")
        arrays.append(data)
        if i < len(paths) - 1:
            arrays.append(np.zeros((int(sample_rate * 0.08), data.shape[1]), dtype="float32"))

    combined = np.concatenate(arrays, axis=0)
    sf.write(str(output_path), combined, sample_rate)
    return output_path


def play_audio(path: Path) -> bool:
    if playback_active():
        log("playback already active; skip new playback")
        return True
    try:
        proc = subprocess.Popen(
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "error", "-volume", "100", str(path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        PLAYING_PID_PATH.write_text(str(proc.pid), encoding="ascii")
        log(f"ffplay spawned: {proc.pid}")
        return True
    except Exception as exc:
        log(f"ffplay failed: {exc}")
        return False


class SarashinaSpeaker:
    def __init__(self) -> None:
        settings = load_settings()
        root = Path(os.environ.get("SARASHINA_TTS_ROOT", Path.home() / "tools" / "sarashina2.2-tts"))
        if not root.exists():
            raise RuntimeError(f"SARASHINA_TTS_ROOT not found: {root}")
        sys.path.insert(0, str(root))

        self.root = root
        self.output_dir = Path(os.environ.get("TEMP", ".")) / "sarashina_tts_outputs"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        prompt_file_value = os.environ.get("SARASHINA_TTS_PROMPT_FILE") or settings.get("prompt_file")
        if prompt_file_value:
            prompt_file = resolve_path(str(prompt_file_value), SKILL_ROOT)
        else:
            prompt_file = SKILL_ROOT / "assets" / "prompt_sarashina_zero_shot_A.wav"
            ensure_default_prompt(prompt_file)
        if prompt_file.name == "prompt_sarashina_zero_shot_A.wav":
            ensure_default_prompt(prompt_file)
        if not prompt_file.exists():
            raise RuntimeError(f"prompt file not found: {prompt_file}")
        self.prompt_file = prompt_file
        self.prompt_text = os.environ.get("SARASHINA_TTS_PROMPT_TEXT") or str(settings.get("prompt_text") or DEFAULT_PROMPT_TEXT)

        from sarashina_tts.flow_matching.decoder import FlowDecoder
        from sarashina_tts.generate.generate import SarashinaTTSGenerator

        self.sample_rate = FlowDecoder.sample_rate
        model_dir = os.environ.get("SARASHINA_TTS_MODEL_DIR", str(root / "pretrained_models"))
        model_id = os.environ.get("SARASHINA_TTS_MODEL_ID", "sbintuitions/sarashina2.2-tts")
        use_vllm = os.environ.get("SARASHINA_TTS_USE_VLLM", "0") == "1"
        watermark = os.environ.get("SARASHINA_TTS_WATERMARK", "1") != "0"

        log(f"initializing generator: model_dir={model_dir}, model_id={model_id}, watermark={watermark}")
        self.generator = SarashinaTTSGenerator(
            model_dir=model_dir,
            model_id=model_id,
            use_vllm=use_vllm,
            watermark=watermark,
        )
        log(f"using prompt file: {self.prompt_file}")
        log(f"using prompt text: {self.prompt_text}")
        log("extracting prompt features")
        self.flow_embedding = self.generator._extract_zero_shot_embedding(str(self.prompt_file))
        self.audio_prompt_tokens = self.generator._extract_audio_prompt_tokens(str(self.prompt_file))
        self.audio_prompt_feat = self.generator._extract_audio_prompt_feat(str(self.prompt_file))
        log("speaker ready")

    def synthesize(self, text: str, request_id: str) -> Path:
        chunk_chars = int(os.environ.get("SARASHINA_TTS_CHUNK_CHARS", str(DEFAULT_CHUNK_CHARS)))
        chunks = split_tts_text(text, chunk_chars)
        log(f"chunked {request_id}: {len(chunks)} chunks, lengths={[len(chunk) for chunk in chunks]}")
        max_tokens_cap = int(os.environ.get("SARASHINA_TTS_MAX_TOKENS", str(DEFAULT_MAX_TOKENS)))
        min_tokens = int(os.environ.get("SARASHINA_TTS_MIN_TOKENS", str(DEFAULT_MIN_TOKENS)))
        tokens_per_char = int(os.environ.get("SARASHINA_TTS_TOKENS_PER_CHAR", str(DEFAULT_TOKENS_PER_CHAR)))
        base_gen_kwargs = {
            "temperature": float(os.environ.get("SARASHINA_TTS_TEMPERATURE", str(DEFAULT_TEMPERATURE))),
            "top_p": float(os.environ.get("SARASHINA_TTS_TOP_P", str(DEFAULT_TOP_P))),
            "repetition_penalty": float(os.environ.get("SARASHINA_TTS_REPETITION_PENALTY", "1.0")),
        }
        wavs = []
        for index, chunk in enumerate(chunks, start=1):
            gen_kwargs = dict(base_gen_kwargs)
            gen_kwargs["max_tokens"] = min(max_tokens_cap, max(min_tokens, len(chunk) * tokens_per_char))
            log(f"generating chunk {index}/{len(chunks)} ({gen_kwargs['max_tokens']} tokens): {chunk}")
            wavs.extend(
                self.generator.generate(
                    [chunk],
                    flow_embedding=self.flow_embedding,
                    audio_prompt_text=self.prompt_text,
                    audio_prompt_tokens=self.audio_prompt_tokens,
                    audio_prompt_feat=self.audio_prompt_feat,
                    audio_prompt_path=str(self.prompt_file),
                    flow_embedding_only=False,
                    watermark=os.environ.get("SARASHINA_TTS_WATERMARK", "1") != "0",
                    gen_kwargs=gen_kwargs,
                )
            )
        paths = self.generator.save_audios(wavs, output_dir=str(self.output_dir), prefix=f"{request_id}_")
        if len(paths) == 1:
            return Path(paths[0])
        return combine_audio_files(paths, self.output_dir / f"{request_id}_combined.wav", self.sample_rate)


def next_request() -> Path | None:
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(QUEUE_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime)
    return files[0] if files else None


def handle_request(speaker: SarashinaSpeaker, path: Path) -> None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        request_id = str(data.get("id") or path.stem)
        text = prepare_tts_text(str(data.get("message") or "Codexのターンが完了しました。"))
        if not text:
            log(f"empty text after cleaning: {path.name}")
            return
        log(f"generating {request_id}: {len(text)} chars: {text}")
        wav_path = speaker.synthesize(text, request_id)
        log(f"wav saved: {wav_path} ({wav_path.stat().st_size} bytes)")
        show_toast("Codex", text[:180])
        if not play_audio(wav_path):
            beep()
    except Exception:
        log(f"request failed: {path.name}\n{traceback.format_exc()}")
        show_toast("Codex", "Sarashina2.2-TTS failed.")
        beep()
    finally:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def cleanup_old_outputs() -> None:
    output_dir = Path(os.environ.get("TEMP", ".")) / "sarashina_tts_outputs"
    if not output_dir.exists():
        return
    cutoff = time.time() - 3600
    for path in output_dir.glob("*.wav"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            pass


def main() -> int:
    PID_PATH.write_text(str(os.getpid()), encoding="ascii")
    log("daemon started")
    idle_timeout = int(os.environ.get("SARASHINA_TTS_IDLE_TIMEOUT", "900"))
    last_work = time.time()
    speaker = None
    try:
        while True:
            request = next_request()
            if request is None:
                if speaker is not None and time.time() - last_work > idle_timeout:
                    log("idle timeout; daemon exit")
                    return 0
                time.sleep(1)
                continue
            last_work = time.time()
            if speaker is None:
                speaker = SarashinaSpeaker()
            handle_request(speaker, request)
            cleanup_old_outputs()
    except Exception:
        log(f"daemon crashed\n{traceback.format_exc()}")
        beep()
        return 0
    finally:
        try:
            if PID_PATH.read_text(encoding="ascii", errors="ignore").strip() == str(os.getpid()):
                PID_PATH.unlink(missing_ok=True)
        except OSError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
