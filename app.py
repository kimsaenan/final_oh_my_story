"""
Oh! My Story — 아이의 말로 완성하는 4컷 미니 동화 (Oh! My Speaking 6 · Unit 01)
최종 디자인 시안을 그대로 옮긴 스트림릿 시제품.   실행:  streamlit run app.py
(이전 AI 이야기 버전은 app_v1_legacy.py)
"""
from __future__ import annotations

import base64
import hashlib
import json

import streamlit as st

import os
import time

from omstory import ai_assist, cuts, speech, ui, voice
from omstory import textbook_audio as tba
from omstory.guard import child_unsafe
from omstory.scene_html import SCENE_CSS, scene_html

UNIT = cuts.UNIT_ID
st.set_page_config(page_title="Oh! My Story", page_icon="📖", layout="wide")
st.markdown(ui.CSS + SCENE_CSS + """<style>
.narr{background:#fff;border:2px dashed #5BC8F0;border-radius:18px;padding:14px 18px;margin:10px 0}
.narr .t{font-weight:800;color:#3AA6CF;font-size:14px}.narr .en{font-size:21px;line-height:1.5;margin:4px 0}.narr .ko{color:#5A6680}
.wk{background:#F4F1FF;border-radius:18px;padding:14px 18px;margin:8px 0}.wk .t{font-weight:800;color:#6A4BD6;font-size:14px}
.wk .en{font-size:24px;margin:4px 0}.wk .ko{color:#5A6680}
.stage{display:inline-block;background:#fff;border:2px solid #F0E3C8;border-radius:14px;padding:2px 12px;font-weight:800}
.note{background:#E6F6FD;border-radius:14px;padding:6px 12px;margin:4px 0}
</style>""", unsafe_allow_html=True)

S = st.session_state
for k, v in {"screen": "shelf", "hero": "amy", "cut": 1, "ans": {}, "state": {}, "notes": [], "vault": {}, "cover": 4,
             "title": "", "library": [], "open_word": None, "play": None, "mic_seen": "", "msg": "", "followed": set(),
             "layout": cuts.load_layout(), "ai_on": False, "reports": [], "ai_text": {}, "ai_used": {}, "points": 0, "try": {}, "revealed": set(), "asked": set()}.items():
    S.setdefault(k, v)


# ------------------------------------------------------------------ 공통 도우미
def go(screen: str, **kw):
    S.screen = screen
    for k, v in kw.items():
        S[k] = v


OPENER = ("Shall we start our story?", "그러면 이야기를 시작해 볼까요?")


def say(text, label: str = "🔊 듣기", key: str = "", wide: bool = False, who: str = "narrator"):
    """선생님(narrator) 또는 Wacky(wacky) 목소리로 읽어 줘요. text 는 문장 하나, 또는 [(문장, 목소리), ...] 순서대로."""
    k = key or "say_" + hashlib.md5(str(text).encode()).hexdigest()[:8]
    if st.button(label, key=k, use_container_width=wide):
        S.play = (text, who) if isinstance(text, str) else list(text)


def _bytes(a) -> bytes:
    return open(a, "rb").read() if isinstance(a, str) else a


def flush_audio():
    """재생기는 화면 오른쪽 아래에 떠서 항상 보여요 (자동 재생이 막혀도 ▶ 를 누르면 돼요)."""
    if S.play:
        items = S.play if isinstance(S.play, list) else [S.play]
        items = [i if isinstance(i, tuple) else (i, "narrator") for i in items]
        parts = [p for p in (voice.get(t, w) for t, w in items) if p]
        if parts:
            S.aud_n = S.get("aud_n", 0) + 1  # 같은 문장을 또 눌러도 매번 새로 재생되게 해요
            st.markdown("<style>[class*='st-key-aud']{position:fixed;right:20px;bottom:20px;width:340px;z-index:9999;background:#fff;"
                        "border-radius:18px;padding:8px 10px;box-shadow:0 6px 18px rgba(0,0,0,.18)}</style>", unsafe_allow_html=True)
            with st.container(key=f"aud{S.aud_n}"):
                b64 = base64.b64encode(b"".join(_bytes(p) for p in parts)).decode()
                st.html(f'<audio controls autoplay src="data:audio/mp3;base64,{b64}" style="width:100%"></audio>')
        else:
            st.caption("🔇 소리를 만들 수 없어요 (tools/pregen_audio.py 를 한 번 실행하면 인터넷 없이도 들려요)")
        S.play = None


def on_word():
    w = S.get(f"wp{S.cut}")
    if w:
        S.open_word = w
        S[f"wp{S.cut}"] = None


@st.dialog("📌 단어 카드")
def word_card(w: str):
    ko, clip_id = cuts.WORDS.get(w, ("", None))
    st.markdown(f"<div class='en' style='font-size:34px'>{ui.E(w)}</div><div class='muted' style='font-size:18px'>{ui.E(ko)}</div>", unsafe_allow_html=True)
    p = tba.clip(UNIT, clip_id) if clip_id else None
    snd = str(p) if p else voice.get(w)
    if snd:
        st.audio(snd, format="audio/mp3", autoplay=True)
        st.caption("교재 원음" if p else "해설 목소리")
    else:
        st.caption("🔇 소리 파일이 아직 없어요 (tools/pregen_audio.py)")
    c1, c2 = st.columns(2)
    if c1.button("🎤 따라 말해 봤어요 (선택)", key=f"fw_{w}", use_container_width=True):
        st.success("좋아요! 점수는 없어요 😊")
    if w in S.vault:
        c2.success("보관함에 있어요")
    elif c2.button("📥 보관함에 담기", key=f"vt_{w}", type="primary", use_container_width=True):
        S.vault[w] = ko
        st.rerun()


def ai_panel():
    with st.sidebar:
        st.markdown("### 🤖 AI 도움 (선택)")
        if not os.getenv("OPENAI_API_KEY"):
            k = st.text_input("OpenAI API 키", type="password", help="이 세션에서만 쓰고 저장하지 않아요. 터미널에서 OPENAI_API_KEY 환경변수로 넣어도 돼요.")
            if k.strip():
                os.environ["OPENAI_API_KEY"] = k.strip()
                st.rerun()
        if ai_assist.available():
            S.ai_on = st.toggle("AI가 문장 만들기", value=S.ai_on, help="끄면 규칙 기반으로 돌아가요. AI가 실패해도 자동으로 규칙으로 전환돼요.")
            st.caption(f"모델: {ai_assist.MODEL()} · 줄거리·그림은 고정, 문장만 AI")
        else:
            S.ai_on = False
            st.caption("키가 없으면 규칙 기반(시연용)으로 동작해요.")


def layout_panel():
    with st.sidebar:
        st.markdown("### 🛠 배치 조정")
        on = st.toggle("그림 위치·크기 바꾸기", key="lay_on")
        if not on:
            return
        cut = st.selectbox("컷", [1, 2, 3, 4], index=(S.cut if S.screen == "cut" else 1) - 1, key="lay_cut")
        for key in cuts.KEYS_BY_CUT[cut]:
            st.markdown(f"**{cuts.LAYOUT_LABELS[key]}**")
            for a, lo, hi in [(a, 0 if a != "width" and a != "height" else 5, 100 if a in ("width", "height") else 90)
                              for a in S.layout[key]]:
                S.layout[key][a] = st.slider({"left": "← 왼쪽에서", "right": "→ 오른쪽에서", "bottom": "↑ 아래에서", "width": "↔ 너비", "height": "↕ 높이"}[a],
                                             lo, hi, int(S.layout[key][a]), key=f"lay_{key}_{a}")
        c1, c2 = st.columns(2)
        if c1.button("💾 저장", use_container_width=True):
            cuts.save_layout(S.layout)
            st.toast("assets/story/layout.json 에 저장했어요")
        if c2.button("↩ 처음 값", use_container_width=True):
            for k in [k for k in S if str(k).startswith("lay_") and k not in ("lay_on", "lay_cut")]:
                del S[k]
            S.layout = {k: dict(v) for k, v in cuts.DEFAULT_LAYOUT.items()}
            st.rerun()
        st.code(json.dumps(S.layout, ensure_ascii=False, indent=1), language="json")


@st.dialog("오늘의 이야기 기록", width="small")
def record_dialog():
    cur = S.screen != "book"
    n_expr = sum(len(b.get("notes", [])) for b in S.library) + (len(S.notes) if cur else 0)
    today = __import__("datetime").date.today().weekday()
    bars = [5, 0, 6, 3, 0, 9, 0]  # 시연용 예시 (디자인 시안과 같은 값)
    bars[today] += len(S.ans) + 4 * len(S.library)
    total = sum(bars)
    top_n = max(bars) or 1
    days = "".join(
        f"<div style='flex:1;text-align:center'><div style='font-size:12px;font-weight:800'>{v}</div>"
        f"<div style='height:{max(4, int(56 * v / top_n))}px;background:{'#5BC8F0' if v else '#F3E6CC'};border-radius:6px 6px 2px 2px;margin:2px 6px'></div>"
        f"<div style='font-size:12px;color:#5A6680;margin-top:2px'>{d}</div></div>"
        for v, d in zip(bars, "월화수목금토일"))
    tile = lambda n, t, bg: f"<div style='background:{bg};border-radius:16px;padding:10px 8px;text-align:center'><div class='en' style='font-size:26px'>{n}</div><div style='font-size:11px;color:#5A6680'>{t}</div></div>"
    books = len(S.library) + (1 if cur and len(S.ans) == 4 else 0)
    # 오늘 완성한 동화책 (가장 최근)
    if S.library:
        b = S.library[-1]; hero, state, cover, title = b["hero"], b["state"], b["cover"], b["title"]
    else:
        hero, state, cover = S.hero, S.state, S.cover
        title = cuts.title_candidates(S.hero, S.state)[0][0] if S.ans else "My Surfing Day"
    scene = scene_html(cover, hero, state, True, S.layout, False)
    exprs = []
    for n in (1, 3, 4):
        a_ = S.ans.get(n)
        if a_ and cur:
            tag = "한국어 → 영어" if any(ord(ch) > 127 for ch in a_["text"]) else "⭐ 주요 표현"
            exprs.append((a_["model_en"], tag))
    for b in S.library:
        for en, _ in b.get("notes", []):
            if all(en != e for e, _t in exprs):
                exprs.append((en, "⭐ 주요 표현"))
    if not exprs:
        exprs = [("동화를 만들면 여기에 쌓여요", "")]
    rows = "".join(f"<div style='display:flex;justify-content:space-between;gap:8px;font-size:13px;padding:3px 0'><b class='en'>{ui.E(e)}</b><span class='muted' style='font-size:12px'>{t}</span></div>" for e, t in exprs)
    st.markdown(f"""
<div style='font-size:12px;color:#5A6680'>Oh! My Story · 링크로 누구나 볼 수 있어요</div>
<div style='font-family:Jua,sans-serif;font-size:24px;margin:2px 0 10px'>Jenny의 오늘의 이야기 기록</div>
<div style='display:grid;grid-template-columns:repeat(3,1fr);gap:8px'>{tile(total,'영어로 말한 문장','#E6F6FD')}{tile(n_expr or 9,'새로 만든 표현','#FFF1D0')}{tile(books or 2,'만든 미니 동화','#E9E3FF')}</div>
<div style='background:#fff;border:2px solid #F0E3C8;border-radius:18px;padding:12px;margin-top:10px'><b style='font-size:13px'>요일별 말한 문장</b>
<div style='display:flex;align-items:flex-end;margin-top:6px'>{days}</div></div>
<div style='margin-top:10px;border-radius:18px;overflow:hidden;border:2px solid #F0E3C8'>{scene}
<div style='padding:8px 12px;background:#fff'><b>{ui.E(title)}</b><br><span class='muted' style='font-size:12px'>4컷 · Unit 01</span></div></div>
<div style='background:#fff;border:2px solid #F0E3C8;border-radius:18px;padding:12px;margin-top:10px'><b style='font-size:13px'>Jenny가 새로 만든 표현</b>{rows}</div>
<div style='background:#E6F6FD;border-radius:18px;padding:12px;margin-top:10px'><b style='font-size:12px;color:#1A6F94'>오늘 배운 표현 · 이 표현으로 이야기해 보세요</b>
<div class='en' style='font-size:16px;margin:4px 0'>I enjoy ~. / I like ~ best.</div>
<div class='en' style='font-size:15px'>“What do you like doing in the summer?”</div></div>
<div style='font-size:11px;color:#8A7550;margin-top:8px'>아이 목소리는 피드백에만 쓰고 30일 뒤 자동 삭제돼요. 보호자 동의 후 이용할 수 있어요. · 요일별 막대는 시연용 예시에 오늘 활동을 더한 값이에요.</div>
""", unsafe_allow_html=True)


def record_panel():
    """오늘의 이야기 기록 — 버튼을 누르면 부모 리포트 화면(9번 시안)이 떠요."""
    with st.sidebar:
        st.markdown("### 📖 오늘의 이야기 기록")
        if st.button("기록 열기 (링크로 누구나 볼 수 있어요)", use_container_width=True):
            S.open_record = True


def report_panel():
    if S.reports:
        with st.sidebar:
            st.markdown("### 🚩 신고한 문장")
            for r in S.reports:
                st.caption(f"{r['cut']}컷 · \"{r['text']}\" → {r['heard']}")
            st.caption("실제 서비스에서는 보호자 확인 후 해당 문장만 개선에 써요.")


def top(right: str = ""):
    st.markdown(ui.header(f'{ui.icon(34)} Oh! <span style="color:#3AA6CF">My Story</span>', right), unsafe_allow_html=True)


def reset_story():
    S.update(cut=1, ans={}, state={}, notes=[], reports=[], followed=set(), cover=4, title="", ai_text={}, ai_used={}, revealed=set(), asked=set(), **{"try": {}})


# ------------------------------------------------------------------ 화면들
UNITS = [("Unit 01", "I like swimming best."), ("Unit 02", "Where can I find the restroom?"), ("Unit 03", "How much is this?"),
         ("Unit 04", "How about playing table tennis?"), ("Unit 05", "Can I bring my dog?"), ("Unit 06", "You must be quiet in here."),
         ("Unit 07", "A coat is warmer than a jacket."), ("Unit 08", "She's the tallest member.")]


def shelf():
    n_exp = sum(len(b.get("notes", [])) for b in S.library)
    top(f'<span class="pill" style="background:#fff;color:#1E2A4A;border:2px solid #F0E3C8">Jenny 작가님 &nbsp;<span style="color:#B07A00">★ {128 + S.points}</span></span>')
    left, right = st.columns([5, 6], gap="large")
    with left:
        st.markdown("""<style>
.st-key-blue{background:#5BC8F0;border-radius:28px;padding:26px 28px 22px;box-shadow:0 12px 0 #3AA6CF;min-height:470px;color:#1E2A4A}
.st-key-blue .bubble{background:#fff;border-radius:16px;padding:10px 14px;font-family:'Nunito',sans-serif;font-weight:800;font-size:15px;line-height:1.3;margin-bottom:6px;display:inline-block}
</style>""", unsafe_allow_html=True)
        with st.container(key="blue"):
            st.markdown("""<span class='pill' style='background:#fff;color:#1E2A4A'>오늘 배운 단원</span>
        <div style='font-weight:800;margin-top:14px'>Unit 01</div>
        <div class='en' style='font-size:44px;line-height:1.1;margin:4px 0 8px;color:#fff;font-weight:900'>I like<br>swimming best.</div>
        <b>계절 활동 이야기</b>
        <p style='margin-top:10px'>오늘 배운 표현으로<br>Wacky랑 나만의 4컷 미니 동화를 만들어 볼까?</p>
        <div style='height:24px'></div>""", unsafe_allow_html=True)
            c1, c2 = st.columns([1, 1], vertical_alignment="bottom")
            with c1:
                if st.button("📖 4컷 미니 동화 만들기", type="primary"):
                    reset_story()
                    go("hero")
                    st.rerun()
            with c2:
                st.markdown(f"<div style='display:flex;align-items:flex-end;justify-content:flex-end;gap:8px'>"
                            f"<span class='bubble' style='text-align:left;white-space:nowrap;margin-bottom:110px'>Beep! Let's make<br>a story!</span>"
                            f"<img src='{wacky_img()}' style='height:150px'></div>", unsafe_allow_html=True)
    with right:
        with st.container(border=True):
            st.markdown("**6권 이야기 책장** &nbsp; <span class='muted'>단원마다 새 미니 동화가 열려요</span>", unsafe_allow_html=True)
            cols = st.columns(4)
            for i, (u, t) in enumerate(UNITS):
                with cols[i % 4]:
                    on = i == 0
                    st.markdown(f"<div style='border:2px solid {'#5BC8F0' if on else '#F0E3C8'};background:{'#E6F6FD' if on else '#FBF7EE'};border-radius:14px;padding:8px 10px;height:118px;margin-bottom:8px;display:flex;flex-direction:column;gap:2px'>"
                                f"<div class='en' style='font-size:12px;color:#5A6680'>{u}</div><div class='en' style='font-size:13px;line-height:1.25'>{ui.E(t)}</div>"
                                f"<span style='align-self:flex-start;margin-top:auto;white-space:nowrap;font-size:10.5px;font-weight:700;border-radius:99px;padding:1px 9px;background:{'#5BC8F0' if on else '#EEF0F4'};color:{'#08384C' if on else '#5A6680'}'>{'오늘 열림' if on else '수업 후 열려요'}</span></div>", unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown(f"**내가 만든 미니 동화** &nbsp; <span class='muted'>지금까지 {len(S.library)}권 · 영어 표현 {n_exp}개</span>", unsafe_allow_html=True)
            if S.library:
                cols = st.columns(3)
                for i, b in enumerate(S.library):
                    with cols[i % 3]:
                        st.markdown(scene_html(b["cover"], b["hero"], b["state"], True, S.layout, False), unsafe_allow_html=True)
                        if st.button(f"📘 {b['title']}", key=f"bk{i}", use_container_width=True):
                            go("book", book=i)
                            st.rerun()
            else:
                st.caption("아직 없어요. 왼쪽에서 첫 미니 동화를 만들어 봐요!")
    st.markdown("**🗂 내 단어 보관함**")
    if S.vault:
        cols = st.columns(6)
        for i, (w, ko) in enumerate(S.vault.items()):
            if cols[i % 6].button(f"🔊 {w}\n{ko}", key=f"v{i}", use_container_width=True):
                S.open_word = w
                st.rerun()
    else:
        st.caption("동화 속 단어를 눌러서 '보관함에 담기'를 하면 여기에 쌓여요.")


def hero_pick():
    top('<span class="pill" style="background:#fff;color:#1E2A4A;border:2px solid #F0E3C8">📖 4컷 이야기 · Wacky와 4번 주고받기</span>')
    if st.button("← 책장으로"):
        go("shelf")
        st.rerun()
    left, right = st.columns([2, 3], gap="large")
    with left:
        st.markdown("""<style>
.st-key-leftp{background:#fff;border-radius:26px;padding:18px 20px;min-height:640px}.st-key-exp0,.st-key-exp1{flex-shrink:0;min-height:96px}
.st-key-exp0,.st-key-exp1{border-radius:20px;padding:12px 16px}
.st-key-exp0{background:#E6F6FD}.st-key-exp1{background:#FFF1D0}
[class*="st-key-exb"] button{border-radius:50%;width:44px;height:44px;min-height:44px;padding:0;background:#fff;border:0;box-shadow:0 2px 6px rgba(0,0,0,.08)}
</style>""", unsafe_allow_html=True)
        with st.container(key="leftp"):
            st.markdown("<b style='color:#1A6F94'>Unit 01 · 오늘의 주요 표현</b><br><span class='muted'>오늘 이야기에서 이 표현으로 말하게 될 거야!</span>", unsafe_allow_html=True)
            for i, (en, ko, sample) in enumerate([("I enjoy ~.", "나는 ~하는 걸 즐겨.", "I enjoy surfing."), ("I like ~ best.", "나는 ~하는 게 제일 좋아.", "I like swimming best.")]):
                with st.container(key=f"exp{i}"):
                    c1, c2 = st.columns([5, 1], vertical_alignment="center")
                    c1.markdown(f"<div class='en' style='font-size:26px'>{ui.E(en)}</div><div class='muted'>{ko}</div>", unsafe_allow_html=True)
                    with c2.container(key=f"exb{i}"):
                        say(sample, "🔊", key=f"ex_{i}")
            d_path, d_text = tba.dialogue(UNIT)
            if d_path:
                with st.expander("🎧 교재 대화문 다시 듣기 (Jack & Amy)"):
                    st.caption(d_text.replace(" / ", "  \n"))
                    st.audio(str(d_path), format="audio/mp3")
            st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)
            with st.container(key="wkrow"):  # 로봇은 카드 맨 아래, 왼쪽
                c1, c2 = st.columns([1, 3], vertical_alignment="bottom")
                c1.image(str(cuts.ASSETS / "characters" / "wacky.png"), width=120)
                c2.markdown("<div class='wk'>먼저 오늘 이야기의 주인공을 골라 볼까?</div>", unsafe_allow_html=True)
    with right:
        st.markdown("### 오늘 이야기의 주인공을 골라요")
        st.caption("고른 친구가 4컷 속 나예요. Wacky가 물어보면 내가 영어로 대답해요.")
        cols = st.columns(2)
        for col, (k, h) in zip(cols, cuts.HEROES.items()):
            with col, st.container(border=True):
                st.image(str(cuts.ASSETS / h["file"]), width=200)
                if st.button(("✅ " if S.hero == k else "") + h["name"], key=f"h_{k}", use_container_width=True,
                             type="primary" if S.hero == k else "secondary"):
                    S.hero = k
                    st.rerun()
        with st.container(border=True):
            st.markdown("**오늘의 이야기는 4컷이에요**")
            st.markdown(" ".join(f"<span class='stage'>{cuts.CUT_INFO[i]['stage']}</span>" for i in range(1, 5)), unsafe_allow_html=True)
            st.caption("그림은 내 말에 따라 나타나요. 틀려도 괜찮고, 한국어로 말해도 Wacky가 영어로 바꿔 줘요.")
        if st.button("이 친구로 시작하기", type="primary"):
            go("cut", cut=1)
            st.rerun()


def accept(cut: int, text: str):
    text = text.strip()
    if not text:
        return
    if child_unsafe(text):
        S.msg = "다정한 말로 다시 말해 볼까요? 😊"
        return
    res = cuts.interpret(cut, text)
    S.ai_text.pop(cut, None)
    S.ai_used[cut] = False
    if S.ai_on and ai_assist.available():
        with st.spinner("Wacky가 생각하는 중…"):
            ai = ai_assist.refine(cut, S.hero, text)
        if ai:
            res.update(model_en=ai["model_en"], model_ko=ai["model_ko"], fallback=False,
                       reaction=(ai["reaction_en"], ai["reaction_ko"]))
            res["state"] = {**res["state"], **ai["state"]}
            S.ai_text[cut] = (ai["narr_en"], ai["narr_ko"])
            S.ai_used[cut] = True
    S.ans[cut] = {"text": text, **res}
    S.state.update(res["state"])
    S.msg = ""
    note = (res["model_en"], res["model_ko"])
    if cut != 2 and note not in S.notes:
        S.notes.append(note)
    S.play = [((S.ai_text.get(cut) or cuts.narration(cut, S.hero, S.state))[0], "narrator"), (S.ans[cut].get("reaction", cuts.REACTIONS[cut])[0], "wacky")]  # 말하면 바로 나레이션이 나와요


BOOK_CSS = """<style>
[data-testid="stApp"]{background:#FCEFD6!important}
.ch-title{font-family:'Jua',sans-serif;font-size:28px}
.pillw{background:#fff;border-radius:999px;padding:4px 12px;font-weight:700;font-size:14px;color:#5A6680;display:inline-block}
.prog{display:inline-flex;align-items:center;gap:8px;background:#fff;border-radius:999px;padding:6px 14px;font-size:13px;font-weight:700}
.prog .bar{width:120px;height:12px;border-radius:99px;background:#F3E6CC;overflow:hidden;display:inline-block}.prog .bar i{display:block;height:12px;background:#FFC21A}
.pg{text-align:center;font-family:'Jua',sans-serif;color:#B49A6A;font-size:18px;margin-top:6px}
.wq{display:grid;grid-template-columns:44px 1fr;gap:10px;margin-bottom:10px}
.wq img{width:44px;height:44px;object-fit:contain;border-radius:50%;background:#EFEAFF}
.wq .b{background:#F4F1FF;border-radius:4px 18px 18px 18px;padding:10px 14px}.wq .b .e{font-family:'Nunito',sans-serif;font-weight:800;font-size:16px}.wq .b .k{font-size:12px;color:#5A6680}
.mine{display:flex;flex-direction:column;align-items:flex-end;gap:4px;margin-bottom:8px}
.mine .b{background:#5BC8F0;color:#08384C;border-radius:18px 4px 18px 18px;padding:10px 14px;font-family:'Nunito',sans-serif;font-weight:900;font-size:16px}
.mine .b.g{background:#EEF0F4;color:#1E2A4A;font-family:'Noto Sans KR',sans-serif;font-size:17px;font-weight:700}
.mine .s{font-size:12px;color:#5A6680}
.chip2{font-size:12px;font-weight:700;background:#E6F6FD;color:#1E6E8E;border-radius:99px;padding:2px 10px}
.nbox{background:#FFF6E0;border:2px dashed #E3C27A;border-radius:16px;padding:9px 14px;display:flex;gap:10px;align-items:flex-start;margin:8px 0}
.nbox .t{font-size:11px;font-weight:800;color:#8A6A1F;margin-bottom:2px}.nbox .e{font-family:'Nunito',sans-serif;font-weight:800;font-size:16px;line-height:1.4}.nbox .k{font-size:12px;color:#5A6680}
.ycard{background:#FFF6D6;border:3px solid #FFD34E;border-radius:24px;padding:16px 18px;margin:8px 0}
.ycard .h{display:flex;align-items:center;gap:8px;font-weight:700;font-size:16px}.ycard .h img{width:36px;height:36px;object-fit:contain}
.ycard .big{font-family:'Nunito',sans-serif;font-weight:900;font-size:27px;line-height:1.25;margin:6px 0}
.ycard .cp{background:#fff;border-radius:10px;padding:3px 10px;font-size:13px;margin-right:6px;display:inline-block;margin-bottom:6px}
.flow{display:flex;align-items:center;gap:8px;font-size:13px;color:#5A6680;margin:8px 0;flex-wrap:wrap}
.flow span.p{border-radius:99px;padding:3px 10px;font-weight:700}
.nnote{background:#fff;border:2px solid #F0E3C8;border-radius:20px;padding:12px 14px;margin-top:8px}
.nnote .r{display:flex;justify-content:space-between;gap:10px;font-size:14px}
</style>"""

CHIP_KO = {"They": "꽃게들은", "How about ~ing?": "~하는 건 어때?", "I enjoy ~.": "나는 ~하는 걸 즐겨.", "build": "짓다·쌓다", "crab": "꽃게"}


def wacky_img() -> str:
    return ui.b64(str(cuts.ASSETS / "characters" / "wacky.png"))


def wq(en: str, ko: str) -> str:
    return f"<div class='wq'><img src='{wacky_img()}' alt='Wacky'><div class='b'><div class='e'>{ui.E(en)}</div><div class='k'>{ui.E(ko)}</div></div></div>"


def narr_box(en: str, ko: str) -> str:
    return f"<div class='nbox'><span style='font-size:22px;line-height:1'>📖</span><div><div class='t'>스토리 흐름 🔊</div><div class='e'>{ui.E(en)}</div><div class='k'>{ui.E(ko)}</div></div></div>"


def progress_pill(done: int) -> str:
    return f"<span class='prog'>말한 문장 <span class='bar'><i style='width:{int(100 * done / 4)}%'></i></span><span class='en'>{done} / 4 ⭐</span></span>"


def cut_screen():
    st.markdown(BOOK_CSS, unsafe_allow_html=True)
    n, hero = S.cut, S.hero
    info = cuts.CUT_INFO[n]
    a = S.ans.get(n)
    done = len(S.ans)
    if not a and n not in S.asked:  # 컷이 시작되면 Wacky의 질문을 선생님 목소리로 한 번 읽어 줘요
        S.asked.add(n)
        S.play = ([(OPENER[0], "wacky")] if n == 1 else []) + [(info["q_en"], "wacky")]
    h1, h2, h3 = st.columns([5, 4, 2], vertical_alignment="center")
    with h1:
        b1, b2 = st.columns([1, 6], vertical_alignment="center")
        if b1.button("←", key="back", help="이전 화면"):
            if n > 1:
                S.cut = n - 1
            else:
                go("hero")
            st.rerun()
        b2.markdown(f"<span class='ch-title'>신나는 여름 방학</span> &nbsp; <span class='pillw'>{n} / 4 컷 · {info['stage']}</span>", unsafe_allow_html=True)
    h2.markdown(progress_pill(done), unsafe_allow_html=True)
    with h3:
        if st.button("이야기 마치기", disabled=done < 4):
            go("cover")
            st.rerun()
    with st.container(border=True):
        left, right = st.columns(2, gap="large")
        with left:
            st.markdown(scene_html(n, hero, S.state, bool(a), S.layout), unsafe_allow_html=True)
            st.markdown(f"<div class='pg'>— {n} —</div>", unsafe_allow_html=True)
        with right:
            if n == 1:
                st.markdown(wq(*OPENER), unsafe_allow_html=True)
            st.markdown(wq(info["q_en"], info["q_ko"]), unsafe_allow_html=True)
            say(([(OPENER[0], "wacky")] if n == 1 else []) + [(info["q_en"], "wacky")], "🔊 Wacky 말 다시 듣기", key=f"q{n}")
            if not a:
                ask_area(n, info)
            else:
                answered_area(n, a, hero)
    if a:
        st.caption("눌러 보고 싶은 단어를 골라요 👇")
        st.pills("단어", cuts.narration_words(n, S.state), key=f"wp{n}", on_change=on_word, label_visibility="collapsed")


def pic_cards(items: list[str]):
    """그림은 '보고 말하는' 힌트예요 (누르는 버튼이 아니에요). 글자 없이 그림만 보여 줘요."""
    cols = st.columns(len(items))
    for col, f in zip(cols, items):
        col.markdown(f"<div style='height:112px;display:flex;align-items:center;justify-content:center;background:#fff;border:2px solid #F0E3C8;border-radius:18px;margin-bottom:16px'>"
                     f"<img src='{ui.b64(str(cuts.ASSETS / f))}' style='max-height:92px;max-width:86%;object-fit:contain'></div>", unsafe_allow_html=True)


def ask_area(n: int, info: dict):
    if n == 1:  # 이번 단원 어휘 그림: 보고 소리 내어 말해요
        st.markdown("**그림을 보고 뭘 좋아하는지 말해 봐요 🎤**", unsafe_allow_html=True)
        pic_cards(["story/surfboard_up.png"] + [cuts.ACTIVITIES[a]["sticker"] for a in ["swimming", "sunbathing", "snorkeling"]])
    if n == 2:  # 누가 외쳤을까? 그림을 보고 말해요 (시연에서는 꽃게 이야기로 이어져요)
        st.markdown("**누가 외쳤을까? 그림을 보고 말해 봐요 🎤**", unsafe_allow_html=True)
        pic_cards(["stickers/crab.png", "stickers/turtle.png", "stickers/dolphin.png"])
    st.markdown("**🎤 소리 내어 말해 봐!** <span class='muted'>틀려도 괜찮아. 한국어로 말해도 돼. 막히면 💡 도움을 눌러 봐!</span>", unsafe_allow_html=True)
    if speech.stt_available():
        audio = st.audio_input("말하기", key=f"mic{n}", label_visibility="collapsed")
        if audio is not None:
            data = audio.getvalue()
            h = hashlib.md5(data).hexdigest()
            if h != S.mic_seen:
                S.mic_seen = h
                with st.spinner("듣고 있어요…"):
                    heard = speech.transcribe(data, list(cuts.WORDS)[:8])
                if heard:
                    accept(n, heard)
                else:
                    S.msg = "잘 못 알아들었어요. 다시 말하거나 아래 '글자로 쓰기'로 이어 가요 😊"
                st.rerun()
    with st.form(f"f{n}", clear_on_submit=True):
        t = st.text_input("✏️ 글자로 쓰기", placeholder={1: "예) 서핑 좋아해 / I enjoy surfing.", 2: "예) 꽃게!", 3: "예) 슬퍼 / They are sad.",
                                                        4: "예) 모래성 쌓자 / How about building a sandcastle?"}[n])
        if st.form_submit_button("보내기", type="primary") and t.strip():
            accept(n, t)
            st.rerun()
    with st.expander("💡 도움"):
        st.caption(f"이렇게 말해 볼 수 있어요: **{info['hint']}**")
        st.markdown("<div style='display:flex;gap:8px;flex-wrap:wrap'>" + "".join(
            f"<span class='en' style='background:#fff;border:2px solid #EED9B0;border-radius:99px;padding:4px 14px'>{ui.E(c)}</span>" for c in info["chips_hint"])
            + "</div><div class='muted' style='font-size:12px;margin-top:6px'>눌러서 고르는 게 아니라, 소리 내어 연습해 보는 표현이에요.</div>", unsafe_allow_html=True)
    if S.msg:
        st.warning(S.msg)
    if S.ai_on:
        st.caption("🤖 AI 도움 켜짐 — 아이 말에 맞춰 문장을 만들어요")


def chips_html(n: int, a: dict) -> str:
    chips = list(a.get("chips", []))
    if n == 4 and a["state"].get("help") == "building sandcastles":
        chips.append("build")
    out = []
    for c in chips:
        if c in ("I enjoy ~.", "crab"):
            continue
        ko = CHIP_KO.get(c) or cuts.WORDS.get(c, ("", None))[0]
        out.append(f"<span class='cp'><b class='en'>{ui.E(c)}</b> {ui.E(ko)}</span>")
    return "".join(out)


def _norm(t: str) -> list[str]:
    return [w for w in "".join(ch.lower() if ch.isalnum() or ch == " " else " " for ch in t).split() if w]


def follow_score(heard: str, target: str) -> float:
    import difflib
    return difflib.SequenceMatcher(None, _norm(heard), _norm(target)).ratio()


def follow_area(n: int, a: dict, primary: bool):
    """① 듣기 → ② 따라 말해 볼까요? → 잘 따라 말하면 포인트 ⭐"""
    target = a["model_en"]
    c1, c2 = st.columns([6, 5])
    with c1:
        say(target, "🔊 이런 표현은 어때요?", key=f"m{n}", wide=True, who="wacky")
    if n in S.followed:
        with c2:
            st.success("잘했어요! ⭐ +10 포인트")
        return
    with c2:
        if speech.stt_available():
            rec = st.audio_input("🎤 따라 말하기", key=f"fm{n}_{S['try'].get(n, 0)}")
            if rec is not None:
                data = rec.getvalue()
                h = hashlib.md5(data).hexdigest()
                if S.get(f"fseen{n}") != h:
                    S[f"fseen{n}"] = h
                    with st.spinner("듣고 있어요…"):
                        heard = speech.transcribe(data, _norm(target))
                    sc = follow_score(heard, target) if heard else 0.0
                    if sc >= 0.7:
                        S.followed.add(n)
                        S.points += 10
                        S.fmsg = ""
                    else:
                        S.fmsg = ("거의 다 됐어요! 한 번 더 말해 볼까요?" if sc >= 0.4 else "다시 한 번 들어 보고 따라 말해 볼까요? 😊")
                        S["try"][n] = S["try"].get(n, 0) + 1  # 녹음기를 새로 열어 다시 말하게 해요
                    st.rerun()
        elif st.button("🎤 따라 말하기 (마이크 없이 · 시연용)", key=f"fl{n}", type="primary" if primary else "secondary", use_container_width=True):
            S.followed.add(n)
            S.points += 10
            st.rerun()
    st.markdown("<div class='muted' style='font-size:12px;margin:-4px 0 8px'>새로 알게 된 표현, 따라 말하면 내 표현이 돼요! ⭐</div>", unsafe_allow_html=True)
    if speech.stt_available() and S.get("fmsg"):
        st.info(S.fmsg)


def narr_show(n: int, en: str, ko: str):
    """스토리 흐름: 처음 나올 때는 '적는 중…' 잠깐 뒤 한 단어씩 써지며 해설 목소리가 읽어 줘요."""
    ph = st.empty()
    if n in S.revealed:
        ph.markdown(narr_box(en, ko), unsafe_allow_html=True)
        return
    S.revealed.add(n)
    ph.markdown(narr_box("✍️ 이야기에 적는 중…", ""), unsafe_allow_html=True)
    time.sleep(float(os.environ.get("OMS_THINK", "1.0")))
    flush_audio()  # 쓰기 시작과 함께 읽어 줘요
    words = en.split(" ")
    for i in range(1, len(words) + 1):
        ph.markdown(narr_box(" ".join(words[:i]), ""), unsafe_allow_html=True)
        time.sleep(0.14)
    ph.markdown(narr_box(en, ko), unsafe_allow_html=True)


def answered_area(n: int, a: dict, hero: str):
    en, ko = S.ai_text.get(n) or cuts.narration(n, hero, S.state)
    react = a.get("reaction", cuts.REACTIONS[n])
    ai_note = "🤖 AI가 도와서 만든 문장 (안전 검사 통과)" if S.ai_used.get(n) else ""
    reported = any(r["cut"] == n and r["text"] == a["text"] for r in S.reports)
    if n in (1, 2):  # 채팅 스타일 (Story1, Story)
        st.markdown(f"<div class='mine'><div class='b'>{ui.E(a['model_en'])}</div><div class='s'>🗣️ 내 말 확인 · {ui.E(a['text'])}</div>"
                    f"<span class='chip2'>내가 만든 장면 ✨</span></div>", unsafe_allow_html=True)
        follow_area(n, a, False)
        narr_show(n, en, ko)
        say(en, "🔊 스토리 흐름 다시 듣기", key=f"nar{n}")
        st.markdown(wq(*react), unsafe_allow_html=True)
        say(react[0], "🔊 Wacky 말 듣기", key=f"rx{n}", who="wacky")
    else:  # 노란 카드 스타일 (Korean, Story4)
        st.markdown(f"<div class='mine'><span class='s'>내가 한 말</span><div class='b g'>{ui.E(a['text'])}</div></div>", unsafe_allow_html=True)
        label = "(감정 표현)" if n == 3 else "(제안 표현)"
        st.markdown(f"<div class='ycard'><div class='h'><img src='{wacky_img()}'> Wacky가 영어로 바꿔 봤어! {label}</div>"
                    f"<div class='big'>{ui.E(a['model_en'])}</div><div>{chips_html(n, a)}</div></div>", unsafe_allow_html=True)
        follow_area(n, a, True)
        narr_show(n, en, ko)
        say(en, "🔊 스토리 흐름 다시 듣기", key=f"nar{n}")
        st.markdown(wq(*react), unsafe_allow_html=True)
        say(react[0], "🔊 Wacky 말 듣기", key=f"rx{n}", who="wacky")
    if ai_note:
        st.caption(ai_note)
    if reported:
        st.caption("🚩 신고했어요. 보호자가 확인한 문장만 개선에 쓰고, 나머지는 30일 뒤 지워져요.")
    elif st.button("🚩 내 말이 다르게 알아들어졌어요", key=f"rp{n}"):
        S.reports.append({"cut": n, "text": a["text"], "heard": a["model_en"]})
        st.rerun()
    c1, c2 = st.columns(2)
    if c1.button("🔁 다시 말할래", key=f"re{n}", use_container_width=True):
        S.ans.pop(n, None)
        S.followed.discard(n)
        S.revealed.discard(n)
        S.pop('fmsg', None)
        st.rerun()
    last = n == cuts.TOTAL_CUTS
    if c2.button("📕 이야기 마치기" if last else "다음 컷 ▶", key=f"nx{n}", type="primary", use_container_width=True):
        if last:
            go("cover")
        else:
            S.cut = n + 1
        st.rerun()
    rows = "".join(f"<div class='r'><span class='en'>{ui.E(e)}</span><span class='muted'>{ui.E(k)}</span></div>" for e, k in S.notes)
    st.markdown(f"<div class='nnote'><div class='r'><b>내가 만든 표현 노트</b><b class='en' style='color:#1E6E8E'>오늘 {len(S.notes)}개</b></div>{rows}</div>", unsafe_allow_html=True)


def cover_pick():
    st.markdown(BOOK_CSS, unsafe_allow_html=True)
    h1, h2 = st.columns([5, 3], vertical_alignment="center")
    h1.markdown("<span class='ch-title'>이야기 완성! 🎉 표지로 쓸 장면을 골라 봐</span><br><span class='muted'>내가 Wacky와 함께 쓴 4컷 이야기 · 신나는 여름 방학</span>", unsafe_allow_html=True)
    h2.markdown(progress_pill(len(S.ans)), unsafe_allow_html=True)
    cols = st.columns(4)
    for i, col in enumerate(cols, start=1):
        a = S.ans.get(i) or {"model_en": "", "model_ko": ""}
        with col, st.container(border=True):
            st.markdown(scene_html(i, S.hero, S.state, True, S.layout, False), unsafe_allow_html=True)
            st.markdown(f"**{i} · {cuts.CUT_INFO[i]['stage']}**" + ("  ✓ 표지" if S.cover == i else ""))
            st.markdown(f"<div style='font-size:13px'><span style='color:#6A4BD6;font-weight:700'>Wacky:</span> {ui.E(cuts.CUT_INFO[i]['q_en'])}</div>"
                        f"<div class='en' style='font-size:15px;margin-top:4px'>{ui.E(a['model_en'])}</div><div class='muted' style='font-size:13px'>{ui.E(a['model_ko'])}</div>", unsafe_allow_html=True)
            if st.button("✓ 표지로" if S.cover == i else "표지로 고르기", key=f"cv{i}", use_container_width=True, type="primary" if S.cover == i else "secondary"):
                S.cover = i
                st.rerun()
    c1, c2 = st.columns(2)
    if c1.button("← 다시 읽어 보기"):
        go("cut", cut=1)
        st.rerun()
    if c2.button("4컷 미니 동화 완성하기 →", type="primary"):
        go("finish")
        st.rerun()


@st.dialog("📖 책 읽어 주기", width="large")
def read_book(hero: str, state: dict, narr: dict, title: str):
    """1컷 → 4컷이 영상처럼 이어져요: 장면이 바뀌고, 글이 나타나고, 선생님 목소리가 읽어 줘요."""
    import streamlit.components.v1 as components
    slides = []
    for i in range(1, 5):
        en, ko = narr.get(i) or cuts.narration(i, hero, state)
        snd = voice.get(en, "narrator")
        a = "data:audio/mp3;base64," + base64.b64encode(_bytes(snd)).decode() if snd else ""
        slides.append({"scene": scene_html(i, hero, state, True, S.layout, False), "en": en, "ko": ko, "audio": a})
    html = f"""{SCENE_CSS}<style>
    body{{margin:0;font-family:'Nunito','Noto Sans KR',sans-serif;background:#FFF8EA;color:#1E2A4A}}
    #w{{position:relative;max-width:560px;margin:0 auto}}
    #stage{{transition:opacity .5s}} .fade{{opacity:0}}
    #txt{{background:#FFF6E0;border:2px dashed #E3C27A;border-radius:16px;padding:12px 18px;margin-top:12px;min-height:84px}}
    #en{{font-size:21px;font-weight:800;line-height:1.35}} #ko{{font-size:14px;color:#5A6680;margin-top:4px}}
    #bar{{display:flex;gap:6px;margin-top:10px}} #bar i{{flex:1;height:8px;border-radius:9px;background:#F0E3C8}} #bar i.on{{background:#FFC21A}}
    #go{{position:absolute;inset:0;display:grid;place-items:center;background:rgba(255,248,234,.82);border-radius:22px;z-index:5}}
    #go button,#again button{{border:0;border-radius:999px;background:#FFD34E;box-shadow:0 5px 0 #D8A91F;font-size:20px;font-weight:800;padding:14px 30px;cursor:pointer;color:#1E2A4A}}
    #again{{display:none;text-align:center;margin-top:10px}}
    h3{{margin:0 0 8px;font-size:24px}}</style>
    <div id="w"><h3>{ui.E(title)}</h3><div id="go"><button onclick="start()">▶ 이야기 시작</button></div>
    <div id="stage"></div><div id="txt"><div id="en"></div><div id="ko"></div></div><div id="bar"><i></i><i></i><i></i><i></i></div>
    <div id="again"><button onclick="start()">🔁 처음부터 다시</button></div></div>
    <script>
    const SL={json.dumps(slides)};let tok=0;
    const sleep=ms=>new Promise(r=>setTimeout(r,ms));
    async function start(){{const t=++tok;document.getElementById('go').style.display='none';document.getElementById('again').style.display='none';
      for(let i=0;i<4;i++){{if(t!==tok)return;const s=SL[i],st=document.getElementById('stage');st.classList.add('fade');await sleep(350);
        st.innerHTML=s.scene;document.getElementById('en').textContent='';document.getElementById('ko').textContent='';
        document.querySelectorAll('#bar i').forEach((b,j)=>b.className=j<=i?'on':'');st.classList.remove('fade');await sleep(500);
        let a=null,done=Promise.resolve();if(s.audio){{a=new Audio(s.audio);done=new Promise(r=>{{a.onended=r;a.onerror=r}});a.play().catch(()=>{{}})}}
        const w=s.en.split(' ');const per=a?170:140;for(let k=1;k<=w.length;k++){{if(t!==tok)return;document.getElementById('en').textContent=w.slice(0,k).join(' ');await sleep(per)}}
        document.getElementById('ko').textContent=s.ko;
        if(a){{await Promise.race([done,sleep(15000)])}}else{{await sleep(2200)}}await sleep(700)}}
      document.getElementById('en').textContent='The End 🎉';document.getElementById('ko').textContent='끝';document.getElementById('again').style.display='block'}}
    </script>"""
    components.html(html, height=600)


def finish():
    st.markdown(BOOK_CSS, unsafe_allow_html=True)
    cands = cuts.title_candidates(S.hero, S.state)
    labels = [t for t, _ in cands] + ["🎤 내가 짓기"]
    st.markdown("<span class='ch-title'>나의 4컷 미니 동화 완성! 📖</span>", unsafe_allow_html=True)
    left, right = st.columns([5, 6], gap="large")
    with right:
        sa, sb = st.columns(2)
        sa.metric("영어로 말한 문장", len(S.ans))
        sb.metric("내가 만든 표현", len(S.notes))
        with st.container(border=True):
            st.markdown("**⭐ 내가 만든 표현**")
            tags = {1: "오늘의 표현", 3: "감정 표현", 4: "제안 표현"}
            for n in (1, 3, 4):
                a = S.ans.get(n)
                if a:
                    st.markdown(f"<b class='en'>{ui.E(a['model_en'])}</b> <span class='muted' style='font-size:12px'>{tags[n]}</span>", unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown("**✏️ 책 제목 고르기**")
            pick = st.pills("제목", labels, key="title_pick", selection_mode="single", default=labels[0], label_visibility="collapsed")
            title, ko = cands[0]
            if pick == "🎤 내가 짓기":
                with st.form("ct"):
                    t = st.text_input("영어로 짓거나 말해 봐요 (5단어 이하)", placeholder="Amy and the Happy Crabs")
                    ok = st.form_submit_button("이 제목으로 확인")
                if ok:
                    chk, msg = cuts.check_custom_title(t)
                    (st.success if chk else st.warning)(msg)
                    S.custom_title = chk
                title, ko = (S.get("custom_title") or cands[0][0]), ""
            elif pick:
                title, ko = pick, dict(cands)[pick]
            st.caption("🔊 고른 제목을 읽어 보며 따라 말해요 · 안 고르면 첫 번째 제목이 돼요 · 직접 지은 제목은 개인정보·부적절한 말을 걸러요")
            say(title, "🔊 제목 듣기", key="tt")
        with st.container(border=True):
            st.markdown("**📖 안쪽 페이지**")
            tc = st.columns(4)
            for i, c in enumerate(tc, start=1):
                c.markdown(scene_html(i, S.hero, S.state, True, S.layout, False), unsafe_allow_html=True)
        b1, b2, b3 = st.columns(3)
        with b1:
            if st.button("▶ 책 읽어 주기", key="readall", use_container_width=True):
                read_book(S.hero, dict(S.state), dict(S.ai_text), S.get("custom_title") or title)
        with b2:
            if st.button("📚 내 책장에 꽂기", type="primary", use_container_width=True):
                S.library.append({"title": title, "cover": S.cover, "hero": S.hero, "state": dict(S.state), "narr": dict(S.ai_text), "notes": list(S.notes)})
                S.custom_title = None
                go("book", book=len(S.library) - 1)
                st.rerun()
        with b3:
            if st.button("🔗 기록 공유하기", use_container_width=True):
                st.toast("링크로 누구나 볼 수 있어요 (시연에서는 복사되지 않아요)")
    with left:
        cover = scene_html(S.cover, S.hero, S.state, True, S.layout, False)
        st.markdown(f"<div style='background:#6A4BD6;border-radius:12px 28px 28px 12px;border-left:20px solid #4A33A8;padding:22px;color:#fff;min-height:560px'>"
                    f"<div style='font-size:14px;opacity:.9'>Oh! My Story · Book 6 Unit 01</div>"
                    f"<div style='border:6px solid #fff;border-radius:18px;overflow:hidden;margin:12px 0'>{cover}</div>"
                    f"<div class='en' style='font-size:34px;line-height:1.1'>{ui.E(title)}</div><div style='margin-top:6px'>{ui.E(ko)}</div>"
                    f"<div style='margin-top:40px;font-size:13px;opacity:.9'>글 · Jenny</div></div>", unsafe_allow_html=True)


def book():
    b = S.library[S.get("book", 0)]
    top()
    if S.get("celebrated") != S.get("book"):
        st.balloons()
        S.celebrated = S.get("book")
    st.markdown(f"## 📘 {b['title']}")
    st.caption("링크로 누구나 볼 수 있어요 · 아이 목소리는 피드백에만 쓰고 30일 뒤 자동 삭제돼요 (보호자 동의 후 이용)")
    cols = st.columns(4)
    for i, col in enumerate(cols, start=1):
        with col:
            st.markdown(scene_html(i, b["hero"], b["state"], True, S.layout, False), unsafe_allow_html=True)
            en, ko = b.get("narr", {}).get(i) or cuts.narration(i, b["hero"], b["state"])
            st.markdown(f"<div class='narr' style='padding:8px 12px'><div class='en' style='font-size:15px'>{ui.E(en)}</div><div class='ko' style='font-size:13px'>{ui.E(ko)}</div></div>", unsafe_allow_html=True)
            say(en, "🔊", key=f"bk_nar{i}")
    if st.button("▶ 책 읽어 주기", key="readbook"):
        read_book(b["hero"], dict(b["state"]), dict(b.get("narr", {})), b["title"])
    st.markdown("**📝 내가 만든 표현**")
    for en, ko in S.notes:
        st.markdown(f"- **{en}** — {ko}")
    c1, c2 = st.columns(2)
    if c1.button("📚 책장으로"):
        go("shelf")
        st.rerun()
    if c2.button("✨ 새 동화 만들기", type="primary"):
        reset_story()
        go("hero")
        st.rerun()


# ------------------------------------------------------------------ 실행
record_panel()
if os.environ.get("OMS_DEV") == "1":  # 개발용 패널(배치 조정·코드)은 숨겨요
    layout_panel()
ai_panel()
report_panel()
{"shelf": shelf, "hero": hero_pick, "cut": cut_screen, "cover": cover_pick, "finish": finish, "book": book}[S.screen]()
if S.pop("open_record", False):
    record_dialog()
if S.open_word:
    w, S.open_word = S.open_word, None
    word_card(w)
flush_audio()
