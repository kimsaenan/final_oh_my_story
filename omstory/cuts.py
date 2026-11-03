"""
cuts.py — 최종 시나리오(고정 4컷) · 배치값 · 한국어→영어 변환 · 단어 카드

디자인 캔버스 "Oh! My Story 앱 디자인"의 최종 설계를 그대로 옮긴 데이터 모듈이에요.
- 질문은 항상 Wacky(고정 대본), 아이 대답은 자유. 아이가 한 말은 틀려도 지적하지 않고 '이런 표현은 어때요?'로 되받아 말해 줘요.
- AI 없이 규칙만으로 끝까지 동작해요. (AI는 나중에 '아이 말 → 영어 문장' 단계에만 꽂으면 돼요)
- 그림은 미리 그린 자산만 써요. 위치·크기는 LAYOUT 값으로 조절해요 (앱의 '배치 조정' 패널에서 바꾸고 저장 가능).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .analysis import has_korean

ASSETS = Path(__file__).resolve().parent.parent / "assets"
UNIT_ID = "b6_u01"
LAYOUT_FILE = ASSETS / "story" / "layout.json"

# ----------------------------------------------------------------------------------------
# 주인공 (교재 친구)
# ----------------------------------------------------------------------------------------
HEROES = {
    "amy": {"name": "Amy", "ko": "에이미", "topic": "에이미는", "ga": "에이미가", "pron": "she", "file": "characters/amy.png"},
    "jack": {"name": "Jack", "ko": "잭", "topic": "잭은", "ga": "잭이", "pron": "he", "file": "characters/jack.png"},
}

# ----------------------------------------------------------------------------------------
# 여름 활동 (Unit 01 단어) — 한국어 말·영어 말 모두 여기서 찾아요
# ----------------------------------------------------------------------------------------
# key: 영어 표현(문장에 들어가는 형태) / pat: 영어 입력에서 찾을 정규식 / ko_words: 한국어 입력에서 찾을 말
ACTIVITIES = {
    "surfing": {"pat": r"surf", "ko_words": ["서핑"], "ko": "서핑하는 것", "sticker": None},
    "swimming": {"pat": r"swim", "ko_words": ["수영"], "ko": "수영하는 것", "sticker": "stickers/swimming.png"},
    "sunbathing": {"pat": r"sunbath", "ko_words": ["일광욕"], "ko": "일광욕하는 것", "sticker": "stickers/sunbathing.png"},
    "diving": {"pat": r"\bdiv", "ko_words": ["다이빙"], "ko": "다이빙하는 것", "sticker": "stickers/diving.png"},
    "snorkeling": {"pat": r"snorkel", "ko_words": ["스노클"], "ko": "스노클링 하는 것", "sticker": "stickers/snorkeling.png"},
    "building sandcastles": {"pat": r"sand\s*castle|building sand", "ko_words": ["모래성"], "ko": "모래성을 쌓는 것",
                             "sticker": "stickers/sandcastle.png"},
    "collecting seashells": {"pat": r"seashell|sea shell|shell", "ko_words": ["조개"], "ko": "조개껍데기를 모으는 것",
                             "sticker": "stickers/seashell.png"},
    "playing beach volleyball": {"pat": r"volley", "ko_words": ["비치발리볼", "배구"], "ko": "비치발리볼을 하는 것",
                                 "sticker": "stickers/volleyball.png"},
}
DEFAULT_ACTIVITY = "surfing"
DEFAULT_HELP_ACTIVITY = "building sandcastles"

EMOTIONS = {
    "sad": {"pat": r"\bsad|unhappy|cry", "ko_words": ["슬퍼", "슬픈", "슬프", "울상", "울고"], "ko": "슬픈", "pred": "슬퍼"},
    "scared": {"pat": r"scared|afraid", "ko_words": ["무서", "겁"], "ko": "무서운", "pred": "무서워"},
    "angry": {"pat": r"angry|mad\b", "ko_words": ["화나", "화가"], "ko": "화난", "pred": "화났어"},
    "upset": {"pat": r"upset", "ko_words": ["속상"], "ko": "속상한", "pred": "속상해"},
    "worried": {"pat": r"worr", "ko_words": ["걱정"], "ko": "걱정되는", "pred": "걱정돼"},
}

# ----------------------------------------------------------------------------------------
# 단어 카드 (눌러 보기 · 보관함) — word: (한국어 뜻, 교재 원음 clip id 또는 None)
# ----------------------------------------------------------------------------------------
WORDS = {
    "surfing": ("서핑하는 것", "word.surfing"), "swimming": ("수영하는 것", "word.swimming"),
    "sunbathing": ("일광욕하는 것", "word.sunbathing"), "diving": ("다이빙하는 것", "word.diving"),
    "snorkeling": ("스노클링 하는 것", "word.snorkeling"),
    "building sandcastles": ("모래성을 쌓는 것", "word.building_sandcastles"),
    "collecting seashells": ("조개껍데기를 모으는 것", "word.collecting_seashells"),
    "playing beach volleyball": ("비치발리볼을 하는 것", "word.playing_beach_volleyball"),
    "beach": ("바닷가", None), "sea": ("바다", None), "wave": ("파도", None), "crab": ("꽃게", None),
    "help": ("도와주다", None), "home": ("집", None), "sad": ("슬픈", None), "scared": ("무서운", None),
    "angry": ("화난", None), "upset": ("속상한", None), "worried": ("걱정되는", None),
    "sandcastle": ("모래성", None), "build": ("짓다 · 쌓다", None), "thank you": ("고마워요", None),
    "How about ~ing?": ("~하는 건 어때?", None),
}


def pretty(activity: str) -> str:
    """'building sandcastles' → 'building a sandcastle' 처럼 문장에 자연스럽게."""
    return {"building sandcastles": "building a sandcastle"}.get(activity, activity)


# ----------------------------------------------------------------------------------------
# 배치값 (%) — 앱의 '배치 조정' 패널에서 바꾸면 assets/story/layout.json 에 저장돼요
#   hero      : left / bottom / height  (장면 가로·세로 대비 %, 정사각 상자)
#   hero_item : 주인공 상자 안에 붙는 소품(서핑보드) left / bottom / height
#   나머지    : right / bottom / width
# ----------------------------------------------------------------------------------------
DEFAULT_LAYOUT = {
    "hero": {"left": 14, "bottom": 3, "height": 60},
    "surfboard": {"left": 38, "bottom": 3, "height": 48},
    "act1": {"right": 8, "bottom": 7, "width": 26},
    "crab_help": {"right": 8, "bottom": 7, "width": 38},
    "broken": {"right": 8, "bottom": 7, "width": 40},
    "crab_sad": {"right": 52, "bottom": 7, "width": 38},
    "crab_happy": {"right": 34, "bottom": 7, "width": 30},
    "act4": {"right": 3, "bottom": 7, "width": 30},
}
LAYOUT_LABELS = {
    "hero": "주인공", "surfboard": "서핑보드(주인공 옆)", "act1": "1컷 활동 스티커", "crab_help": "2컷 외치는 꽃게들",
    "broken": "3컷 부서진 모래성", "crab_sad": "3컷 울상 꽃게들", "crab_happy": "4컷 행복한 꽃게들", "act4": "4컷 활동 스티커(모래성 등)",
}
KEYS_BY_CUT = {1: ["hero", "surfboard", "act1"], 2: ["hero", "crab_help"], 3: ["broken", "crab_sad"], 4: ["hero", "crab_happy", "act4"]}


def load_layout() -> dict:
    lay = {k: dict(v) for k, v in DEFAULT_LAYOUT.items()}
    if LAYOUT_FILE.exists():
        try:
            for k, v in json.loads(LAYOUT_FILE.read_text(encoding="utf-8")).items():
                if k in lay and isinstance(v, dict):
                    lay[k].update({a: b for a, b in v.items() if a in lay[k]})
        except (ValueError, OSError):
            pass
    return lay


def save_layout(lay: dict) -> None:
    LAYOUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    LAYOUT_FILE.write_text(json.dumps(lay, ensure_ascii=False, indent=2), encoding="utf-8")


# ----------------------------------------------------------------------------------------
# 컷 기본 정보
# ----------------------------------------------------------------------------------------
CUT_INFO = {
    1: {"stage": "🌱 시작", "bg": "story/bg_beach.png", "q_en": "The weather is nice! What do you like doing in the summer?",
        "q_ko": "날씨 좋다! 여름에 뭐 하는 걸 좋아해?", "hint": "I enjoy ~.", "chips_hint": ["surfing", "swimming", "building sandcastles"]},
    2: {"stage": "⚡ 사건", "bg": "story/bg_storm.jpg", "q_en": 'Listen! Someone shouts, "Help us!" Who is it?',
        "q_ko": '들어 봐! 누가 "도와줘요!"라고 외쳐. 누굴까?', "hint": "Crabs!", "chips_hint": ["Crabs!"]},
    3: {"stage": "🔑 해결", "bg": "story/bg_mid.jpg", "q_en": "The wave broke their home. How do they feel?",
        "q_ko": "파도가 꽃게들의 집을 부쉈어. 기분이 어떨까?", "hint": "They are sad.", "chips_hint": ["They are sad.", "They are scared."]},
    4: {"stage": "🌈 결말", "bg": "story/bg_calm.jpg", "q_en": "Hmm, let me think. What can we do for the crabs?",
        "q_ko": "음, 생각해 보자. 꽃게들을 위해 뭘 할 수 있을까?", "hint": "How about ~ing?",
        "chips_hint": ["How about building a sandcastle?", "How about collecting seashells?"]},
}
TOTAL_CUTS = 4

# Wacky가 아이 대답을 받은 뒤 하는 말 (고정)
REACTIONS = {
    1: ("Wow! A big wave is coming! What happens next?", "와! 큰 파도가 오고 있어! 무슨 일이 생길까?"),
    2: ('Crabs! They shout, "Help us!" Let\'s listen to them.', '꽃게들이야! "도와줘요!"래. 같이 들어 보자.'),
    3: ("Oh no. Poor crabs! Let's help them.", "저런. 불쌍한 꽃게들! 같이 도와주자."),
    4: ("Great idea! The crabs are happy!", "좋은 생각이야! 꽃게들이 행복해해!"),
}


# ----------------------------------------------------------------------------------------
# 아이 말 → 영어 문장 (규칙 기반). 못 알아들으면 '모범 문장'을 되받아 말해 줘요 (지적 없음)
# ----------------------------------------------------------------------------------------
def _find(table: dict, text: str) -> str | None:
    t = text.lower()
    best, pos = None, -1
    for key, v in table.items():
        for m in re.finditer(v["pat"], t):
            if m.start() > pos:
                best, pos = key, m.start()
        for w in v["ko_words"]:
            i = text.rfind(w)
            if i > pos:
                best, pos = key, i
    return best


def find_activity(text: str) -> str | None:
    return _find(ACTIVITIES, text)


def find_emotion(text: str) -> str | None:
    return _find(EMOTIONS, text)


def _is_crab(text: str) -> bool:
    return bool(re.search(r"crab", text.lower()) or "꽃게" in text or re.search(r"(^|\s)게($|\s|들|야|가)", text))


def interpret(cut: int, text: str) -> dict:
    """아이가 한 말을 받아서 {model_en, model_ko, state, fallback, korean}을 돌려준다.
    model_en은 'Wacky가 들려주는 올바른 영어 문장'이고, 아이가 이미 맞게 말했어도 같은 문장을 보여 줘요(되받아 말하기)."""
    text = text.strip()
    out = {"korean": has_korean(text), "fallback": False, "state": {}}
    if cut == 1:
        act = find_activity(text)
        if act is None:
            out["fallback"], act = True, DEFAULT_ACTIVITY
        out["state"] = {"activity": act}
        out["model_en"] = f"I enjoy {act}."
        out["model_ko"] = f"나는 {ACTIVITIES[act]['ko'].replace('것', '걸')} 즐겨."
        out["chips"] = ["I enjoy ~.", act]
    elif cut == 2:
        out["fallback"] = not _is_crab(text)
        out["model_en"], out["model_ko"] = "Crabs!", "꽃게들이야!"
        out["chips"] = ["crab"]
    elif cut == 3:
        emo = find_emotion(text)
        if emo is None:
            out["fallback"], emo = True, "sad"
        out["state"] = {"emotion": emo}
        out["model_en"] = f"They are {emo}."
        out["model_ko"] = f"꽃게들은 {EMOTIONS[emo]['pred']}."
        out["chips"] = ["They", emo]
    else:
        act = find_activity(text)
        if act is None:
            out["fallback"], act = True, DEFAULT_HELP_ACTIVITY
        out["state"] = {"help": act}
        out["model_en"] = f"How about {pretty(act)}?"
        ko = ACTIVITIES[act]["ko"]
        out["model_ko"] = f"{ko.replace('것', '건')} 어때?" if "것" in ko else f"{ko} 어때?"
        out["chips"] = ["How about ~ing?", "sandcastle" if act == "building sandcastles" else act]
    return out


# ----------------------------------------------------------------------------------------
# 이 컷의 스티커·배경 이미지, 책에는 이렇게 써요 (해설), 단어 칩
# ----------------------------------------------------------------------------------------
def scene_items(cut: int, hero: str, state: dict, answered: bool) -> list[dict]:
    """장면에 올릴 그림 목록. answered=False면 아직 아이가 말하기 전이라 사건 그림만 보여 줘요."""
    items: list[dict] = []
    act1 = state.get("activity")
    if cut == 1:
        items.append({"key": "hero", "kind": "hero", "file": HEROES[hero]["file"], "label": f"나 ({HEROES[hero]['name']})"})
        if answered and act1:
            if act1 == "surfing":
                items.append({"key": "surfboard", "kind": "hero_item", "file": "story/surfboard_up.png"})
            elif ACTIVITIES[act1]["sticker"]:
                items.append({"key": "act1", "kind": "abs", "file": ACTIVITIES[act1]["sticker"]})
    elif cut == 2:
        file = "story/amy_surprised.png" if hero == "amy" else HEROES[hero]["file"]
        items.append({"key": "hero", "kind": "hero", "file": file, "label": f"나 ({HEROES[hero]['name']})"})
        if answered:
            items.append({"key": "crab_help", "kind": "abs", "file": "story/pair_help.png"})
    elif cut == 3:
        items.append({"key": "broken", "kind": "abs", "file": "story/sandcastle_broken.png"})
        if answered:
            items.append({"key": "crab_sad", "kind": "abs", "file": "story/pair_sad.png"})
    else:
        items.append({"key": "hero", "kind": "hero", "file": HEROES[hero]["file"], "label": f"나 ({HEROES[hero]['name']})"})
        if answered:
            items.append({"key": "crab_happy", "kind": "abs", "file": "story/pair_happy.png"})
            act = state.get("help")
            if act and ACTIVITIES[act]["sticker"]:
                items.append({"key": "act4", "kind": "abs", "file": ACTIVITIES[act]["sticker"]})
    return items


def sticker_badge(cut: int, state: dict) -> str:
    if cut == 1:
        act = state.get("activity")
        return "서핑보드" if act == "surfing" else (act or "")
    return {2: "외치는 꽃게들", 3: "울상 꽃게들 · 부서진 모래성", 4: "행복한 꽃게들 · " + (state.get("help") or "새 집")}[cut]


def narration(cut: int, hero: str, state: dict) -> tuple[str, str]:
    """'책에는 이렇게 써요' 문장 (영어, 한글). 동화책 본문이 돼요."""
    h = HEROES[hero]
    if cut == 1:
        act = state.get("activity") or DEFAULT_ACTIVITY
        return (f"{h['name']} enjoys {act}, so {h['pron']} goes to the beach today. The sea is quiet. But wait!",
                f"{h['topic']} {ACTIVITIES[act]['ko'].replace('하는 것', '을').replace('는 것', '을').replace('것', '을')} 즐겨서, 오늘 바닷가에 가. 바다는 조용해. 그런데 잠깐!")
    if cut == 2:
        return ('Oh no! A big wave comes! The crabs say, "Help us!"', '이런! 큰 파도가 와! 꽃게들이 "도와줘요!"라고 해.')
    if cut == 3:
        emo = state.get("emotion") or "sad"
        return (f"The wave breaks their home. The crabs are very {emo}.", f"파도가 꽃게들의 집을 부숴. 꽃게들은 아주 {EMOTIONS[emo]['pred']}.")
    act = state.get("help") or DEFAULT_HELP_ACTIVITY
    if act == "building sandcastles":
        return (f'{h["name"]} says, "How about building a sandcastle?" So {h["pron"]} builds a sandcastle home. The crabs say, "Thank you!"',
                f'{h["ga"]} "모래성을 쌓는 건 어때?"라고 말해. 그래서 모래성 집을 지어. 꽃게들이 말해: "고마워요!"')
    return (f'{h["name"]} says, "How about {pretty(act)}?" The crabs smile and say, "Thank you!"',
            f'{h["ga"]} "{ACTIVITIES[act]["ko"].replace("것", "건")} 어때?"라고 말해. 꽃게들이 웃으며 말해: "고마워요!"')


def narration_words(cut: int, state: dict) -> list[str]:
    """해설 속에서 눌러 볼 수 있는 단어 (단어 카드)."""
    if cut == 1:
        return [state.get("activity") or DEFAULT_ACTIVITY, "beach", "sea"]
    if cut == 2:
        return ["wave", "crab", "help"]
    if cut == 3:
        return ["home", state.get("emotion") or "sad", "wave"]
    act = state.get("help") or DEFAULT_HELP_ACTIVITY
    if act == "building sandcastles":
        return ["sandcastle", "build", "thank you"]
    return [act, "thank you"]


def hero_name_en(hero: str) -> str:
    return HEROES[hero]["name"]


# ----------------------------------------------------------------------------------------
# 책 제목 (후보 3개 + 내가 짓기)
# ----------------------------------------------------------------------------------------
def title_candidates(hero: str, state: dict) -> list[tuple[str, str]]:
    name = HEROES[hero]["name"]
    act = state.get("activity") or DEFAULT_ACTIVITY
    first = f"My {act.split()[-1].capitalize()} Day" if act != "building sandcastles" else "My Sandcastle Day"
    ko_act = ACTIVITIES[act]["ko"].replace("하는 것", "").replace("는 것", "").replace("을 쌓", "").strip()
    return [(first, f"나의 {ko_act} 하루" if ko_act else "나의 여름 하루"),
            (f"{name} and the Crabs", f"{HEROES[hero]['ko']}와 꽃게들" if hero == "jack" else "에이미와 꽃게들"),
            ("A Home for the Crabs", "꽃게들의 집")]


def check_custom_title(text: str) -> tuple[str | None, str]:
    """내가 지은 제목 검사 → (통과한 제목 또는 None, 안내 메시지). 5단어 이하, 영어, 안전 단어·개인정보 걸러요."""
    from .guard import child_unsafe

    t = " ".join(text.strip().split())
    if not t:
        return None, "제목을 말하거나 써 주세요."
    if has_korean(t):
        return None, "영어로 지어 볼까? 한국어면 후보 제목 중에서 골라도 좋아요."
    if child_unsafe(t):
        return None, "다정한 말로 다시 지어 볼까요?"
    if re.search(r"\d{3,}|@|https?:|\.com", t):
        return None, "전화번호나 주소 같은 건 제목에 쓰지 않아요."
    if len(t.split()) > 5:
        return None, "제목은 다섯 단어까지만 쓸 수 있어요."
    if len(t) > 40:
        return None, "조금만 더 짧게 지어 볼까요?"
    return t[0].upper() + t[1:], "좋은 제목이에요!"


# ----------------------------------------------------------------------------------------
# 미리 만들어 둘 소리 목록 (tools/pregen_audio.py)
# ----------------------------------------------------------------------------------------
def all_audio_lines() -> list[str]:
    lines: list[str] = []
    for n, c in CUT_INFO.items():
        lines.append(c["q_en"])
        lines.append(REACTIONS[n][0])
    for hero in HEROES:
        for act in ACTIVITIES:
            lines.append(narration(1, hero, {"activity": act})[0])
            lines.append(f"I enjoy {act}.")
            lines.append(narration(4, hero, {"help": act})[0])
            lines.append(f"How about {pretty(act)}?")
        lines.append(narration(2, hero, {})[0])
        for emo in EMOTIONS:
            lines.append(narration(3, hero, {"emotion": emo})[0])
            lines.append(f"They are {emo}.")
    lines.append("Shall we start our story?")
    lines.append("Crabs!")
    lines.append("I like swimming best.")
    lines += [w for w in WORDS if w != "How about ~ing?"]
    lines += [t for hero in HEROES for t, _ in title_candidates(hero, {"activity": "surfing"})]
    return list(dict.fromkeys(lines))
