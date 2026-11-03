"""
voice.py — 목소리 두 가지: 해설(선생님) · Wacky(로봇 친구)

1) assets/audio/narrator/<md5>.mp3 에 미리 만들어 둔 소리가 있으면 그걸 재생 (tools/pregen_audio.py)
2) 없으면 그 자리에서 TTS로 만들어 재생 (edge-tts, 네트워크 필요)
3) 둘 다 안 되면 None → 앱은 글자만 보여 줘요
선생님은 스토리 흐름·제목·단어를 읽고, Wacky는 질문과 '이런 표현은 어때요?'를 말해요.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import streamlit as st

from . import speech

ROOT = Path(__file__).resolve().parent.parent / "assets" / "audio"
DIR = ROOT / "narrator"          # 선생님(해설) 목소리
WHO = ("narrator", "wacky")      # wacky = 로봇 친구 목소리 (omstory/speech.py VOICES 에서 바꿔요)


def audio_name(text: str) -> str:
    return hashlib.md5(text.strip().encode("utf-8")).hexdigest()[:16] + ".mp3"


def folder(who: str = "narrator") -> Path:
    return ROOT / who


def pregenerated(text: str, who: str = "narrator") -> Path | None:
    p = folder(who) / audio_name(text)
    return p if p.exists() else None


@st.cache_data(show_spinner=False, max_entries=300)
def _live(text: str, who: str) -> bytes | None:
    return speech.synthesize(text, who)


def get(text: str, who: str = "narrator") -> bytes | str | None:
    """st.audio에 넣을 수 있는 값(경로 또는 bytes) 또는 None."""
    p = pregenerated(text, who)
    if p:
        return str(p)
    return _live(text, who)
