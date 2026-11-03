"""4컷 최종 시나리오 테스트:  python -m pytest -q tests/test_cuts.py"""
from omstory import cuts


def test_cut1_korean_and_english():
    assert cuts.interpret(1, "서핑 좋아해")["model_en"] == "I enjoy surfing."
    assert cuts.interpret(1, "I like swimming")["model_en"] == "I enjoy swimming."
    r = cuts.interpret(1, "음...")
    assert r["fallback"] and r["model_en"] == "I enjoy surfing."


def test_cut2_crabs():
    assert not cuts.interpret(2, "꽃게!")["fallback"]
    assert not cuts.interpret(2, "crabs")["fallback"]
    assert cuts.interpret(2, "고양이")["fallback"]


def test_cut3_emotion():
    assert cuts.interpret(3, "슬퍼")["model_en"] == "They are sad."
    assert cuts.interpret(3, "They are scared")["model_en"] == "They are scared."


def test_cut4_help_any_activity():
    assert cuts.interpret(4, "모래성 쌓는 건 어때?")["model_en"] == "How about building a sandcastle?"
    assert cuts.interpret(4, "조개 줍자")["model_en"] == "How about collecting seashells?"


def test_narration_final_script():
    s = {"activity": "surfing", "help": "building sandcastles", "emotion": "sad"}
    assert cuts.narration(1, "amy", s)[0] == "Amy enjoys surfing, so she goes to the beach today. The sea is quiet. But wait!"
    assert cuts.narration(2, "amy", s)[0] == 'Oh no! A big wave comes! The crabs say, "Help us!"'
    assert cuts.narration(3, "amy", s)[0] == "The wave breaks their home. The crabs are very sad."
    assert cuts.narration(4, "jack", s)[0].startswith('Jack says, "How about building a sandcastle?" So he builds')


def test_scene_items_and_layout_keys():
    for n in range(1, 5):
        for it in cuts.scene_items(n, "amy", {"activity": "surfing", "help": "building sandcastles"}, True):
            assert it["key"] in cuts.DEFAULT_LAYOUT and (cuts.ASSETS / it["file"]).exists(), it
    assert [i["key"] for i in cuts.scene_items(3, "amy", {}, True)] == ["broken", "crab_sad"]  # 3컷엔 주인공 없음


def test_titles_and_filter():
    t = cuts.title_candidates("amy", {"activity": "surfing"})
    assert [x[0] for x in t] == ["My Surfing Day", "Amy and the Crabs", "A Home for the Crabs"]
    assert cuts.check_custom_title("Amy and the Happy Crabs")[0]
    assert cuts.check_custom_title("one two three four five six")[0] is None
    assert cuts.check_custom_title("엄마")[0] is None
    assert cuts.check_custom_title("call 01012345678")[0] is None


def test_audio_lines_cover_everything():
    L = cuts.all_audio_lines()
    for h in cuts.HEROES:
        for a in cuts.ACTIVITIES:
            assert cuts.narration(1, h, {"activity": a})[0] in L
            assert cuts.narration(4, h, {"help": a})[0] in L
    assert all(w in L for w in cuts.narration_words(4, {"help": "surfing"}))


# ---- AI 도움 (가짜 클라이언트) ----
import json as _json
from types import SimpleNamespace

from omstory import ai_assist


def _fake(payload):
    def create(**kw):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=_json.dumps(payload)))])
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


GOOD = {"model_en": "I enjoy swimming.", "model_ko": "수영을 좋아해.", "reaction_en": "Wow! Here comes a big wave!",
        "reaction_ko": "와! 큰 파도가 와!", "narr_en": "Amy enjoys swimming. She goes to the beach.", "narr_ko": "에이미는 수영을 좋아해.",
        "activity": "swimming", "emotion": None}


def test_ai_accepts_valid_and_limits_state():
    r = ai_assist.refine(1, "amy", "수영!", client=_fake(GOOD))
    assert r["model_en"] == "I enjoy swimming." and r["state"] == {"activity": "swimming"}
    r = ai_assist.refine(1, "amy", "x", client=_fake({**GOOD, "activity": "skydiving"}))
    assert r["state"] == {}  # 목록 밖 값은 무시


def test_ai_rejects_unsafe_korean_long_or_broken():
    assert ai_assist.refine(1, "amy", "x", client=_fake({**GOOD, "model_en": "나는 수영"})) is None
    assert ai_assist.refine(1, "amy", "x", client=_fake({**GOOD, "narr_en": "word " * 40})) is None
    assert ai_assist.refine(1, "amy", "x", client=_fake({**GOOD, "reaction_en": "I will kill you"})) is None

    def boom(**kw):
        raise RuntimeError("network")
    bad = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=boom)))
    assert ai_assist.refine(1, "amy", "x", client=bad) is None
