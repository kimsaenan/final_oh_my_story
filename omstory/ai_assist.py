"""
ai_assist.py — 티키타카 구간의 AI 도움 (선택). 키가 없거나 실패하면 규칙 결과(cuts.interpret)를 그대로 써요.

AI가 하는 일 : 아이 말(한국어·서툰 영어) 이해 → "이런 표현은 어때요?" 문장, Wacky 반응, '책에는 이렇게 써요' 해설 문장 작성
AI가 못 하는 일: 4컷 줄거리·질문·그림 (고정). 그림에 쓰이는 값(활동·감정)은 미리 정한 목록 안에서만 고를 수 있어요.
결과는 길이·언어·안전 필터를 모두 통과해야 쓰이고, 하나라도 어긋나면 통째로 버리고 규칙 결과로 돌아가요.
"""
from __future__ import annotations

import json
import os
import re

from . import cuts
from .analysis import has_korean
from .guard import child_unsafe

MODEL = lambda: os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # noqa: E731


def available() -> bool:
    if not os.getenv("OPENAI_API_KEY"):
        return False
    try:
        import openai  # noqa: F401
        return True
    except ImportError:
        return False


def _system(cut: int, hero: str) -> str:
    h = cuts.HEROES[hero]
    return f"""You help a Korean elementary child (age 10-12) make a 4-cut mini picture book in English (Oh! My Speaking 6, Unit 01 'Let's have fun!').
The story is FIXED: hero {h['name']} ({h['pron']}) at the beach; cut 1 summer activity, cut 2 a big wave and crabs shout "Help us!", cut 3 the wave breaks the crabs' home and they feel sad, cut 4 the child suggests a way to help (e.g. building a sandcastle) and the crabs are happy.
Now it is cut {cut}. Wacky the robot asked: "{cuts.CUT_INFO[cut]['q_en']}"
The child answered (Korean, English or mixed). Understand the meaning, even if it is rough.
Return JSON only:
{{"model_en": "one short natural English sentence the child could say (max 10 words, textbook pattern: 'I enjoy ~ing.' / 'They are ~.' / 'How about ~ing?')",
 "model_ko": "its Korean meaning, friendly",
 "reaction_en": "Wacky's short reply to the child (max 14 words, kind, no correction, ends by moving the story on)",
 "reaction_ko": "Korean meaning",
 "narr_en": "1-3 simple sentences for the book page, in third person about {h['name']}/the crabs, reflecting what the child said (max 28 words)",
 "narr_ko": "Korean meaning",
 "activity": "one of {list(cuts.ACTIVITIES)} or null (cut 1 and 4 only)",
 "emotion": "one of {list(cuts.EMOTIONS)} or null (cut 3 only)"}}
Rules: easy words for grade 5-6, never correct or criticize the child, no scary or unkind content, no personal information, stay inside the fixed story."""


def _words(s: str) -> int:
    return len(re.findall(r"[A-Za-z']+", s))


def _ok_en(s, limit: int) -> bool:
    return isinstance(s, str) and 0 < _words(s) <= limit and not has_korean(s) and not child_unsafe(s)


def _ok_ko(s) -> bool:
    return isinstance(s, str) and 0 < len(s) <= 120 and not child_unsafe(s)


def validate(d: dict, cut: int) -> dict | None:
    """AI 결과 검사 → 통과하면 정리된 dict, 아니면 None."""
    if not isinstance(d, dict):
        return None
    if not (_ok_en(d.get("model_en"), 10) and _ok_en(d.get("reaction_en"), 14) and _ok_en(d.get("narr_en"), 28)):
        return None
    if not (_ok_ko(d.get("model_ko")) and _ok_ko(d.get("reaction_ko")) and _ok_ko(d.get("narr_ko"))):
        return None
    out = {k: d[k].strip() for k in ("model_en", "model_ko", "reaction_en", "reaction_ko", "narr_en", "narr_ko")}
    state = {}
    if cut in (1, 4) and d.get("activity") in cuts.ACTIVITIES:
        state["activity" if cut == 1 else "help"] = d["activity"]
    if cut == 3 and d.get("emotion") in cuts.EMOTIONS:
        state["emotion"] = d["emotion"]
    out["state"] = state
    return out


def refine(cut: int, hero: str, text: str, client=None) -> dict | None:
    """AI로 문장을 만든다. 실패·검사 탈락이면 None (→ 규칙 결과 사용)."""
    try:
        if client is None:
            from openai import OpenAI
            client = OpenAI()
        resp = client.chat.completions.create(
            model=MODEL(), temperature=0.6, max_tokens=500, timeout=20, response_format={"type": "json_object"},
            messages=[{"role": "system", "content": _system(cut, hero)}, {"role": "user", "content": text}])
        return validate(json.loads(resp.choices[0].message.content), cut)
    except Exception:
        return None
