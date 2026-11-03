"""scene_html.py — 장면(배경 + 주인공 + 스티커)을 HTML/CSS로 그려요. 위치·크기는 cuts.LAYOUT 값(%)을 따라가서 슬라이더로 조절할 수 있어요."""
from __future__ import annotations

from html import escape

from . import cuts, ui


def scene_html(cut: int, hero: str, state: dict, answered: bool, layout: dict, show_label: bool = False) -> str:
    bg = ui.b64(str(cuts.ASSETS / cuts.CUT_INFO[cut]["bg"].replace("story/", "story/")))
    parts = [f'<div class="sc-bg" style="position:absolute;inset:0;background:url({bg}) center bottom/cover no-repeat"></div>']
    for it in cuts.scene_items(cut, hero, state, answered):
        L = layout[it["key"]]
        src = ui.b64(str(cuts.ASSETS / it["file"]))
        if it["kind"] in ("hero", "hero_item"):
            style = f"left:{L['left']}%;bottom:{L['bottom']}%;height:{L['height']}%"
            parts.append(f'<img class="sc-it sc-h" style="{style}" src="{src}" alt="">')
        else:
            style = f"right:{L['right']}%;bottom:{L['bottom']}%;width:{L['width']}%"
            parts.append(f'<img class="sc-it sc-a" style="{style}" src="{src}" alt="">')
    if cut == 2 and not answered:  # 누가 외치는지 모르는 상태에서도 'Help us!' 말풍선은 먼저 보여 줘요
        parts.append('<div class="sc-say">Help us!</div>')
    return f'<div class="sc">{"".join(parts)}</div>'


SCENE_CSS = """<style>
.sc{position:relative;width:100%;aspect-ratio:1.6/1;border-radius:22px;overflow:hidden;background:#BFE9F7;box-shadow:0 4px 16px rgba(30,42,74,.12)}
.sc-bg{position:absolute;inset:0;width:100%!important;height:100%!important;max-width:none!important;object-fit:cover!important}
.sc-say{position:absolute;right:8%;top:30%;background:#fff;color:#1E2A4A;border-radius:18px 18px 4px 18px;padding:8px 16px;font-family:'Nunito',sans-serif;font-weight:900;font-size:20px;box-shadow:0 3px 8px rgba(0,0,0,.18)}
.sc-it{position:absolute;object-fit:contain;object-position:bottom;max-width:none!important}
.sc-h{aspect-ratio:1/1;width:auto}
.sc-a{height:auto}
.sc-tag{position:absolute;background:#fff;color:#1E2A4A;font-weight:800;font-size:13px;padding:2px 10px;border-radius:12px;transform:translateY(100%)}
</style>"""
