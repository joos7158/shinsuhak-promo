# -*- coding: utf-8 -*-
"""홈페이지 주소를 새 도메인으로 일괄 교체 (2026-09-29).
사용: venv python set_domain.py shinsuhak.kr
  - docs/CNAME 생성(GitHub Pages 커스텀 도메인)
  - docs/*.html, docs/posts/*.html, robots.txt, llms.txt, sitemap.xml, gen_post.py 안의 옛 주소 → https://<도메인>
  - git add/commit/push 는 하지 않는다(확인 뒤 수동)."""
import re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OLD = "https://joos7158.github.io/shinsuhak-promo"
domain = sys.argv[1].strip().lower().replace("https://", "").replace("http://", "").strip("/")
NEW = f"https://{domain}"
(ROOT / "docs" / "CNAME").write_text(domain + "\n", encoding="utf-8")
n = 0
for p in list((ROOT / "docs").rglob("*.html")) + [ROOT / "docs" / "robots.txt", ROOT / "docs" / "llms.txt",
                                                   ROOT / "docs" / "sitemap.xml", ROOT / "gen_post.py"]:
    if not p.exists(): continue
    s = p.read_text(encoding="utf-8")
    t = s.replace(OLD + "/", NEW + "/").replace(OLD, NEW)
    if t != s:
        p.write_text(t, encoding="utf-8"); n += 1; print("교체", p.relative_to(ROOT))
print(f"완료: {n}개 파일, CNAME={domain}")
print("다음: git add docs gen_post.py && git commit && git push → 가비아 DNS 반영 뒤 https 확인")
