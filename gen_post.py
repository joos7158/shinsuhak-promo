# -*- coding: utf-8 -*-
"""블로그 초안(.md) → 홈페이지 글 페이지 생성 + 목록/사이트맵 갱신 (2026-09-29, 원장 "홈페이지 글은 자동으로 올려도 돼").

사용:  venv python gen_post.py <초안.md> [--date YYYY-MM-DD] [--no-push]
  - 초안 형식: 첫 줄(또는 '제목:' 줄 / 첫 '#' 헤딩) = 제목, '태그' 로 시작하는 줄 이후 = 태그, 나머지 = 본문
  - 산출: docs/posts/<date>-<slug>.html, docs/posts/index.html(목록), docs/sitemap.xml 갱신, git add/commit/push
  - 레드라인은 초안 단계에서 지켜져 있어야 한다(실명·학교+학년+반·성적 사례·도구명). 여기서는 금칙어만 한 번 더 막는다.
"""
import re, sys, json, html, subprocess, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOCS = ROOT / "docs"
POSTS = DOCS / "posts"
SITE = "https://joos7158.github.io/shinsuhak-promo"
FORBIDDEN = ["최고의", "1등 학원", "100점으로", "→ 100점", "점 상승", "등급 상승 보장", "MathDNA", "클로드", "Claude", "GPT"]

def parse(md: str):
    """주간 초안 형식: `# 제목` / `# 본문` / `# 태그 (N개)` / 그 밖의 `# 그림`·`# 출처…` 절은 버린다.
    절 헤더가 없는 옛 형식(첫 줄=제목, '태그:' 줄 이후=태그)도 받는다."""
    lines = md.splitlines()
    sections, cur = {}, None
    has_headers = any(re.match(r"^#\s*(제목|본문)\b", ln.strip()) for ln in lines)
    if has_headers:
        for ln in lines:
            m = re.match(r"^#\s*([^\s(（]+)", ln.strip())
            if m and not ln.startswith("##"):
                cur = m.group(1); sections.setdefault(cur, []); continue
            if cur: sections[cur].append(ln)
        title = next((s.strip().lstrip("#").strip() for s in sections.get("제목", []) if s.strip() and s.strip() != "---"), None)
        body = "\n".join(l for l in sections.get("본문", []) if l.strip() != "---").strip()
        tag_src = " ".join(l for l in sections.get("태그", []) if not l.strip().startswith(">"))
        tags = [t for t in re.findall(r"#([^\s#,]+)", tag_src)]
        return title, body, tags
    title, body, tags, mode = None, [], [], "body"
    for ln in lines:
        s = ln.strip()
        if title is None:
            if not s: continue
            title = re.sub(r"^(제목\s*[:：]\s*|#+\s*)", "", s).strip(); continue
        if re.match(r"^(태그|#태그|해시태그)\s*[:：]?", s):
            mode = "tags"; s = re.sub(r"^(태그|#태그|해시태그)\s*[:：]?", "", s).strip()
        if mode == "tags":
            tags += [t.strip("#, ") for t in re.split(r"[,\s]+", s) if t.strip("#, ")]
        else:
            body.append(ln)
    return title, "\n".join(body).strip(), [t for t in tags if t]

def md_to_html(md: str) -> str:
    out, para, in_list, table = [], [], False, []
    def flush_para():
        nonlocal para
        if para:
            out.append("<p>" + "<br>".join(inline(x) for x in para) + "</p>"); para = []
    def flush_table():
        nonlocal table
        if table:
            rows = [r for r in table if not re.match(r"^\|?\s*:?-{2,}", r)]
            cells = [[inline(c.strip()) for c in r.strip().strip("|").split("|")] for r in rows]
            if cells:
                h = "".join(f"<th>{c}</th>" for c in cells[0])
                b = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in cells[1:])
                out.append(f"<table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table>")
            table = []
    def inline(s):
        s = html.escape(s, quote=False)
        s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"\[(.+?)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', s)
        return s
    for ln in md.splitlines():
        s = ln.rstrip()
        if s.startswith("|"):
            flush_para(); table.append(s); continue
        else:
            flush_table()
        m = re.match(r"^(#{1,4})\s+(.*)", s)
        if m:
            flush_para()
            if in_list: out.append("</ul>"); in_list = False
            lvl = min(len(m.group(1)) + 1, 4)
            out.append(f"<h{lvl}>{inline(m.group(2))}</h{lvl}>"); continue
        if re.match(r"^\s*[-*•]\s+", s):
            flush_para()
            if not in_list: out.append("<ul>"); in_list = True
            out.append("<li>" + inline(re.sub(r"^\s*[-*•]\s+", "", s)) + "</li>"); continue
        if in_list and s.strip() == "":
            out.append("</ul>"); in_list = False; continue
        if s.strip() == "":
            flush_para(); continue
        para.append(s.strip())
    flush_para(); flush_table()
    if in_list: out.append("</ul>")
    return "\n".join(out)

def slugify(title: str) -> str:
    s = re.sub(r"[^\w가-힣]+", "-", title).strip("-")
    return s[:40] or "post"

PAGE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} | 신수학학원 후곡캠퍼스</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{url}">
<meta property="og:title" content="{title}"><meta property="og:description" content="{desc}"><meta property="og:type" content="article"><meta property="og:url" content="{url}">
<script type="application/ld+json">{ld}</script>
<style>
:root{{--camel:#8A6A3C;--cream:#F5EDDD;--deep:#4A3826;--ink:#1a1a1a;--muted:#6b5f52}}
body{{margin:0;font-family:"Noto Sans KR","Apple SD Gothic Neo","Malgun Gothic",sans-serif;color:var(--ink);background:#fff;line-height:1.75}}
header{{background:var(--cream);padding:18px 16px;font-size:14px}} header a{{color:var(--deep);text-decoration:none;font-weight:700}}
main{{max-width:720px;margin:0 auto;padding:24px 16px 48px}} h1{{font-size:24px;color:var(--deep);line-height:1.35}} h2{{font-size:19px;color:var(--deep);margin-top:28px}} h3{{font-size:17px}}
.meta{{color:var(--muted);font-size:13px;margin-bottom:20px}} table{{border-collapse:collapse;width:100%;font-size:15px}} td,th{{border-bottom:1px solid #eee;padding:8px 6px;text-align:left}}
.cta{{margin-top:36px;padding:18px;background:var(--cream);border-radius:14px}} .cta a{{display:inline-block;margin:6px 8px 0 0;padding:10px 14px;border-radius:10px;background:var(--camel);color:#fff;text-decoration:none;font-weight:700}} .cta a.s{{background:#fff;color:var(--camel);border:1px solid var(--camel)}}
.tags{{color:var(--muted);font-size:13px;margin-top:24px}} footer{{font-size:13px;color:var(--muted);text-align:center;padding:24px 16px}}
</style></head><body>
<header><a href="../">신수학학원 후곡캠퍼스</a> · <a href="./">학교별 시험 정보</a></header>
<main>
<h1>{title}</h1>
<div class="meta">{date} · 신수학학원 후곡캠퍼스 (일산 후곡 학원가)</div>
{body}
<div class="tags">{tags}</div>
<div class="cta"><strong>우리 아이 지금 어디서 막혀 있을까요?</strong><br>일산 후곡 학원가 신수학학원 — 20년 경력 원장이 직접 손풀이를 읽습니다. 한 반 5~6명.<br>
<a href="https://booking.naver.com/booking/12/bizes/1596630">입학 상담 예약 (40분, 무료)</a><a class="s" href="https://m.place.naver.com/place/1096140891/home">네이버 지도</a><a class="s" href="../">학원 소개</a></div>
</main>
<footer>신수학학원 후곡캠퍼스 · 경기도 고양시 일산서구 일산로 574, 301호 · 010-5392-3917</footer>
</body></html>"""

def build_index():
    items = []
    for p in sorted(POSTS.glob("*.html"), reverse=True):
        if p.name == "index.html": continue
        t = re.search(r"<title>(.*?) \| ", p.read_text(encoding="utf-8"))
        d = p.name[:10]
        items.append(f'<li><a href="{p.name}">{html.escape(t.group(1)) if t else p.stem}</a> <span class="d">{d}</span></li>')
    POSTS.joinpath("index.html").write_text(f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>학교별 시험 정보 | 신수학학원 후곡캠퍼스</title><meta name="description" content="일산 지역 고등학교·중학교 시험 일정, 출제 경향, 내신 대비 글 모음. 신수학학원 후곡캠퍼스."><link rel="canonical" href="{SITE}/posts/">
<style>body{{margin:0;font-family:"Noto Sans KR","Malgun Gothic",sans-serif;line-height:1.7;color:#1a1a1a}}header{{background:#F5EDDD;padding:18px 16px;font-size:14px}}header a{{color:#4A3826;text-decoration:none;font-weight:700}}main{{max-width:720px;margin:0 auto;padding:24px 16px 48px}}h1{{color:#4A3826;font-size:22px}}li{{margin:10px 0}}a{{color:#8A6A3C}}.d{{color:#6b5f52;font-size:13px;margin-left:8px}}</style></head>
<body><header><a href="../">신수학학원 후곡캠퍼스</a></header><main><h1>학교별 시험 정보</h1><p>일산 지역 학교의 시험 일정·출제 경향·내신 대비 글입니다. 매주 한 편씩 올립니다.</p><ul>{''.join(items)}</ul></main></body></html>""", encoding="utf-8")
    return len(items)

def build_sitemap():
    today = datetime.date.today().isoformat()
    urls = [f"<url><loc>{SITE}/</loc><lastmod>{today}</lastmod><changefreq>weekly</changefreq></url>",
            f"<url><loc>{SITE}/posts/</loc><lastmod>{today}</lastmod><changefreq>weekly</changefreq></url>"]
    for p in sorted(POSTS.glob("*.html")):
        if p.name != "index.html":
            urls.append(f"<url><loc>{SITE}/posts/{p.name}</loc><lastmod>{p.name[:10]}</lastmod></url>")
    DOCS.joinpath("sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(urls) + "\n</urlset>\n", encoding="utf-8")

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    date = next((sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == "--date"), datetime.date.today().isoformat())
    push = "--no-push" not in sys.argv
    src = Path(args[0]); md = src.read_text(encoding="utf-8-sig")
    title, body_md, tags = parse(md)
    if not title or len(body_md) < 200:
        raise SystemExit("제목 또는 본문(200자 미만) 부족 — 생성 중단")
    bad = [w for w in FORBIDDEN if w in title + body_md]
    if bad:
        raise SystemExit(f"금칙어 발견 {bad} — 초안을 고친 뒤 다시")
    POSTS.mkdir(parents=True, exist_ok=True)
    fname = f"{date}-{slugify(title)}.html"; url = f"{SITE}/posts/{fname}"
    desc = re.sub(r"\s+", " ", re.sub(r"[#*|>\-]", " ", body_md))[:150].strip()
    ld = json.dumps({"@context": "https://schema.org", "@type": "Article", "headline": title, "datePublished": date, "inLanguage": "ko",
                     "author": {"@type": "Organization", "name": "신수학학원 후곡캠퍼스"}, "publisher": {"@type": "Organization", "name": "신수학학원 후곡캠퍼스"},
                     "mainEntityOfPage": url, "about": tags[:10]}, ensure_ascii=False)
    page = PAGE.format(title=html.escape(title), desc=html.escape(desc), url=url, ld=ld, date=date, body=md_to_html(body_md),
                       tags=" ".join("#" + t for t in tags[:30]))
    POSTS.joinpath(fname).write_text(page, encoding="utf-8")
    n = build_index(); build_sitemap()
    print(f"생성 {fname} · 목록 {n}편 · sitemap 갱신")
    if push:
        subprocess.run(["git", "add", "docs"], cwd=ROOT, check=True)
        subprocess.run(["git", "commit", "-q", "-m", f"post: {title} ({date})\n\nCo-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"], cwd=ROOT, check=True)
        subprocess.run(["git", "push", "-q", "origin", "HEAD"], cwd=ROOT, check=True)
        print("push 완료 →", url)

if __name__ == "__main__":
    main()
