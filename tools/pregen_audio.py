"""
pregen_audio.py — 해설(선생님) 목소리 mp3를 미리 만들어 둬요 (한 번만 실행)

    python tools/pregen_audio.py          # 없는 것만 만들기
    python tools/pregen_audio.py --force  # 전부 다시 만들기

결과: assets/audio/narrator/<md5>.mp3  (앱이 문장 글자의 md5로 찾아서 재생해요)
edge-tts 가 인터넷에 연결돼 있어야 해요. 목소리는 omstory/speech.py 의 VOICES['narrator'] 에서 바꿔요.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from omstory import cuts, speech  # noqa: E402
from omstory.voice import WHO, audio_name, folder  # noqa: E402


def main(force: bool = False) -> int:
    lines = cuts.all_audio_lines()
    made = skipped = failed = 0
    for who in WHO:  # 선생님 목소리 + Wacky 목소리
        folder(who).mkdir(parents=True, exist_ok=True)
        for i, t in enumerate(lines, 1):
            p = folder(who) / audio_name(t)
            if p.exists() and not force:
                skipped += 1
                continue
            data = speech.synthesize(t, who)
            if data:
                p.write_bytes(data)
                made += 1
            else:
                failed += 1
                print(f"  ✗ 실패({who}): {t}")
            if i % 10 == 0:
                print(f"  {who} {i}/{len(lines)}")
    print(f"완료: 새로 {made}개, 이미 있음 {skipped}개, 실패 {failed}개 (총 {len(lines)}문장 × {len(WHO)}목소리)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main("--force" in sys.argv))
