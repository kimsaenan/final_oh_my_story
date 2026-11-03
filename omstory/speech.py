"""
speech.py — STT(음성→글자)와 TTS(글자→음성)

STT: faster-whisper(로컬). 단원 어휘를 initial_prompt로 넣어 아이가 말할 법한 단어를 더 잘 알아듣게 한다.
     → RAG로 꺼낸 단원 정보가 음성 인식도 돕는 구조.
TTS: edge-tts (PoC용). 캐릭터마다 다른 목소리(VOICES). 정식 서비스에서는 사용 조건이 분명한 공식 TTS(예: Azure Speech)나 교재 MP3로 교체.
"""
from __future__ import annotations

import asyncio
import os
import tempfile

_whisper = None


def stt_available() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def _wav_to_array(audio_bytes: bytes):
    """wav bytes → 16kHz mono float32 (PyAV/ffmpeg 없이도 돌아가도록 직접 읽어요)."""
    import io
    import wave

    import numpy as np

    with wave.open(io.BytesIO(audio_bytes), "rb") as w:
        n, ch, rate, width = w.getnframes(), w.getnchannels(), w.getframerate(), w.getsampwidth()
        raw = w.readframes(n)
    dt = {1: np.uint8, 2: np.int16, 4: np.int32}[width]
    a = np.frombuffer(raw, dtype=dt).astype(np.float32)
    a = (a - 128) / 128 if width == 1 else a / float(2 ** (8 * width - 1))
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    if rate != 16000 and len(a):
        a = np.interp(np.linspace(0, len(a) - 1, int(len(a) * 16000 / rate)), np.arange(len(a)), a).astype(np.float32)
    return a


def transcribe(audio_bytes: bytes, hint_words: list[str] | None = None, model_size: str | None = None) -> str:
    """녹음(wav bytes) → 텍스트. 영어·한국어 섞인 말도 받기 위해 언어 자동 감지. 실패하면 빈 문자열."""
    global _whisper
    try:
        from faster_whisper import WhisperModel

        if _whisper is None:
            _whisper = WhisperModel(model_size or os.getenv("WHISPER_MODEL", "base"), device="cpu", compute_type="int8")
        try:
            audio = _wav_to_array(audio_bytes)
        except Exception:
            audio = None
        prompt = ("Kids English practice. Words: " + ", ".join(hint_words)) if hint_words else None
        if audio is not None:
            segments, _ = _whisper.transcribe(audio, initial_prompt=prompt, vad_filter=True, beam_size=5)
            return " ".join(s.text.strip() for s in segments).strip()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_bytes)
            path = f.name
        try:
            segments, _ = _whisper.transcribe(path, initial_prompt=prompt, vad_filter=True, beam_size=5)
            return " ".join(s.text.strip() for s in segments).strip()
        finally:
            os.unlink(path)
    except Exception:
        return ""


def tts_available() -> bool:
    try:
        import edge_tts  # noqa: F401
        return True
    except ImportError:
        return False


# 캐릭터별 목소리 (edge-tts 음성 + 높낮이·빠르기). 정식 서비스에서는 성우 녹음 또는 캐릭터 전용 TTS 음성으로 교체.
VOICES = {
    "wacky": {"voice": "en-US-AnaNeural", "pitch": "+25Hz", "rate": "+0%"},         # 로봇: 높고 통통 튀는 목소리
    "jack": {"voice": "en-US-AndrewNeural", "pitch": "+35Hz", "rate": "-5%"},       # 남자아이
    "amy": {"voice": "en-US-AnaNeural", "pitch": "+0Hz", "rate": "-10%"},           # 여자아이
    "tom": {"voice": "en-US-ChristopherNeural", "pitch": "+30Hz", "rate": "-5%"},   # 남자아이 (Jack과 다르게)
    "narrator": {"voice": "en-US-JennyNeural", "pitch": "-3Hz", "rate": "-8%"},     # 동화 읽어 주는 선생님 목소리 (질문·되받아 말하기·해설·단어 전부 이 목소리)
    "mom": {"voice": "en-US-JennyNeural", "pitch": "+0Hz", "rate": "-10%"},         # 엄마
}
DEFAULT_VOICE = VOICES["wacky"]


def voice_for(speaker: str | None) -> dict:
    v = dict(VOICES.get((speaker or "").lower(), DEFAULT_VOICE))
    if os.getenv("TTS_VOICE") and not speaker:  # 환경변수로 기본 목소리만 바꿀 수 있음
        v["voice"] = os.getenv("TTS_VOICE")
    return v


async def _tts(text: str, voice: str, rate: str, pitch: str = "+0Hz") -> bytes:
    import edge_tts

    out = b""
    async for chunk in edge_tts.Communicate(text, voice=voice, rate=rate, pitch=pitch).stream():
        if chunk["type"] == "audio":
            out += chunk["data"]
    return out


def synthesize(text: str, speaker: str | None = None) -> bytes | None:
    """영어 문장 → mp3 bytes. speaker(wacky/jack/amy/tom/mom)에 따라 목소리가 달라짐. 실패하면 None (글자만 보여줌)."""
    if not text.strip() or not tts_available():
        return None
    v = voice_for(speaker)
    try:
        return asyncio.run(_tts(text, v["voice"], v["rate"], v["pitch"])) or None
    except Exception:
        return None
