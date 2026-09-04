#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
promo_post.py — 신수학학원 쓰레드(Threads)·인스타그램 자동 게시기

실행: C:\\Users\\신수학\\dev\\MathDNA\\venv\\Scripts\\python.exe promo_post.py <명령> [옵션]

명령
  init      원장님이 앱 ID/시크릿·토큰을 직접 입력해 저장 (클로드는 값을 보지 않음)
  auth      토큰 생성기가 없을 때: 로그인 주소를 띄우고 되돌아온 주소를 붙여넣어 토큰 발급
  whoami    저장된 토큰으로 계정 확인 (user_id 자동 채움)
  refresh   장기 토큰 갱신 (만료 10일 전이면 post 때도 자동으로 함)
  post      초안 폴더의 post.json 을 읽어 게시 (--channel threads|instagram|both, --dry-run)
  status    posted.json 최근 기록 출력

post.json 형식 (초안 폴더 안):
{
  "threads":   {"text": "…500자 이내…", "images": ["01.png"]},        # images 0~20장
  "instagram": {"caption": "…", "images": ["01.png", "02.png"]}       # images 1~10장 (필수)
}
이미지는 site/img/ 로 복사·JPEG 변환 후 GitHub Pages 로 push → 공개 URL 로 Meta 에 전달.
"""
import argparse, json, os, sys, time, shutil, subprocess, datetime as dt, getpass, re, urllib.parse
from pathlib import Path

import requests
from PIL import Image

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

HERE = Path(__file__).resolve().parent
SITE = HERE / "docs"
IMG_DIR = SITE / "img"
POSTED = HERE / "posted.json"
SECRETS = Path(os.environ.get("USERPROFILE", str(Path.home()))) / ".claude" / "secrets" / "meta_tokens.json"
PAGES_BASE = "https://joos7158.github.io/shinsuhak-promo"
REDIRECT_URI = f"{PAGES_BASE}/auth.html"

TH_API = "https://graph.threads.net/v1.0"
TH_HOST = "https://graph.threads.net"
IG_API = "https://graph.instagram.com/v25.0"
IG_HOST = "https://graph.instagram.com"

# ───────────────────────── 공통 ─────────────────────────
def log(msg):
    print(f"[{dt.datetime.now():%H:%M:%S}] {msg}", flush=True)

def load_secrets():
    if not SECRETS.exists():
        return {}
    return json.loads(SECRETS.read_text(encoding="utf-8"))

def save_secrets(d):
    SECRETS.parent.mkdir(parents=True, exist_ok=True)
    SECRETS.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(SECRETS, 0o600)
    except Exception:
        pass

def _get(url, **params):
    r = requests.get(url, params=params, timeout=60)
    try:
        j = r.json()
    except Exception:
        j = {"raw": r.text}
    if r.status_code >= 400 or "error" in j:
        raise RuntimeError(f"GET {url.split('?')[0]} → {r.status_code} {json.dumps(j, ensure_ascii=False)[:400]}")
    return j

def _post(url, **data):
    r = requests.post(url, data=data, timeout=120)
    try:
        j = r.json()
    except Exception:
        j = {"raw": r.text}
    if r.status_code >= 400 or "error" in j:
        raise RuntimeError(f"POST {url.split('?')[0]} → {r.status_code} {json.dumps(j, ensure_ascii=False)[:400]}")
    return j

def _expires_at(days):
    return (dt.datetime.now() + dt.timedelta(days=days)).strftime("%Y-%m-%d")

# ───────────────────────── init / auth ─────────────────────────
def cmd_init(args):
    """원장님이 터미널에서 직접 값을 입력. 클로드 세션에서는 실행하지 말 것(입력 불가)."""
    d = load_secrets()
    print("신수학 SNS 연결 설정 — 값은 이 PC 의", SECRETS, "에만 저장됩니다.\n(비워두고 Enter 하면 기존 값 유지)")
    for ch, label in (("threads", "쓰레드"), ("instagram", "인스타그램")):
        print(f"\n■ {label}")
        cur = d.get(ch, {})
        app_id = input(f"  앱 ID [{'저장됨' if cur.get('app_id') else '없음'}]: ").strip() or cur.get("app_id", "")
        secret = getpass.getpass(f"  앱 시크릿 [{'저장됨' if cur.get('app_secret') else '없음'}] (입력 안 보임): ").strip() or cur.get("app_secret", "")
        token = getpass.getpass(f"  액세스 토큰 [{'저장됨' if cur.get('access_token') else '없음'}] (입력 안 보임, 없으면 Enter): ").strip() or cur.get("access_token", "")
        cur.update({"app_id": app_id, "app_secret": secret, "access_token": token})
        if token and not cur.get("expires_at"):
            cur["expires_at"] = _expires_at(60)
        d[ch] = cur
    save_secrets(d)
    print("\n저장 완료. 이어서 whoami 로 계정 확인:")
    print(f"  {sys.executable} {__file__} whoami")

def cmd_auth(args):
    """토큰 생성기 대신 OAuth 로 발급. 원장님이 브라우저에서 로그인 → auth.html 주소를 붙여넣음."""
    d = load_secrets()
    ch = args.channel
    if ch not in ("threads", "instagram"):
        sys.exit("--channel threads 또는 instagram 하나만")
    cur = d.get(ch, {})
    if not cur.get("app_id") or not cur.get("app_secret"):
        sys.exit(f"{ch} 앱 ID/시크릿이 없습니다. 먼저 init 을 실행하세요.")
    if ch == "threads":
        url = "https://threads.net/oauth/authorize?" + urllib.parse.urlencode({
            "client_id": cur["app_id"], "redirect_uri": REDIRECT_URI,
            "scope": "threads_basic,threads_content_publish", "response_type": "code"})
    else:
        url = "https://www.instagram.com/oauth/authorize?" + urllib.parse.urlencode({
            "client_id": cur["app_id"], "redirect_uri": REDIRECT_URI,
            "scope": "instagram_business_basic,instagram_business_content_publish", "response_type": "code"})
    print("\n1) 아래 주소를 브라우저에 붙여넣고 학원 계정으로 로그인·허용:\n\n" + url + "\n")
    back = input("2) 되돌아온 페이지의 주소 전체를 붙여넣으세요: ").strip()
    m = re.search(r"[?&]code=([^&#]+)", back)
    if not m:
        sys.exit("주소에서 code= 를 찾지 못했습니다.")
    code = urllib.parse.unquote(m.group(1)).rstrip("#_")
    if ch == "threads":
        j = _post(f"{TH_HOST}/oauth/access_token", client_id=cur["app_id"], client_secret=cur["app_secret"],
                  grant_type="authorization_code", redirect_uri=REDIRECT_URI, code=code)
        short = j["access_token"]
        j2 = _get(f"{TH_HOST}/access_token", grant_type="th_exchange_token",
                  client_secret=cur["app_secret"], access_token=short)
    else:
        j = _post("https://api.instagram.com/oauth/access_token", client_id=cur["app_id"], client_secret=cur["app_secret"],
                  grant_type="authorization_code", redirect_uri=REDIRECT_URI, code=code)
        short = j["access_token"]
        j2 = _get(f"{IG_HOST}/access_token", grant_type="ig_exchange_token",
                  client_secret=cur["app_secret"], access_token=short)
    cur["access_token"] = j2["access_token"]
    cur["expires_at"] = _expires_at(max(1, int(j2.get("expires_in", 60 * 86400)) // 86400))
    d[ch] = cur
    save_secrets(d)
    print(f"장기 토큰 저장 완료 (만료 {cur['expires_at']}). whoami 로 확인하세요.")

# ───────────────────────── whoami / refresh ─────────────────────────
def whoami(ch, cur):
    if ch == "threads":
        j = _get(f"{TH_API}/me", fields="id,username,threads_profile_picture_url", access_token=cur["access_token"])
        return j["id"], j.get("username", "")
    j = _get(f"{IG_API}/me", fields="user_id,username,account_type", access_token=cur["access_token"])
    return str(j.get("user_id") or j.get("id")), j.get("username", "")

def cmd_whoami(args):
    d = load_secrets()
    ok = False
    for ch in ("threads", "instagram"):
        cur = d.get(ch, {})
        if not cur.get("access_token"):
            print(f"{ch:10s} 토큰 없음")
            continue
        try:
            uid, uname = whoami(ch, cur)
            cur["user_id"], cur["username"] = uid, uname
            print(f"{ch:10s} OK  @{uname}  id={uid}  만료={cur.get('expires_at','?')}")
            ok = True
        except Exception as e:
            print(f"{ch:10s} 실패: {e}")
    d and save_secrets(d)
    return ok

def refresh(ch, cur):
    if ch == "threads":
        j = _get(f"{TH_HOST}/refresh_access_token", grant_type="th_refresh_token", access_token=cur["access_token"])
    else:
        j = _get(f"{IG_HOST}/refresh_access_token", grant_type="ig_refresh_token", access_token=cur["access_token"])
    cur["access_token"] = j["access_token"]
    cur["expires_at"] = _expires_at(max(1, int(j.get("expires_in", 60 * 86400)) // 86400))
    return cur

def maybe_refresh(d, ch, force=False):
    cur = d.get(ch, {})
    if not cur.get("access_token"):
        return cur
    try:
        exp = dt.datetime.strptime(cur.get("expires_at", "2000-01-01"), "%Y-%m-%d")
    except ValueError:
        exp = dt.datetime(2000, 1, 1)
    if force or (exp - dt.datetime.now()).days <= 10:
        log(f"{ch} 토큰 갱신 중 (만료 {cur.get('expires_at')})")
        d[ch] = refresh(ch, cur)
        save_secrets(d)
        log(f"{ch} 토큰 갱신 완료 → 만료 {d[ch]['expires_at']}")
    return d[ch]

def cmd_refresh(args):
    d = load_secrets()
    for ch in ("threads", "instagram"):
        if d.get(ch, {}).get("access_token"):
            try:
                maybe_refresh(d, ch, force=True)
            except Exception as e:
                print(f"{ch} 갱신 실패: {e}")

# ───────────────────────── 이미지 호스팅 ─────────────────────────
def _git(*a):
    return subprocess.run(["git", "-C", str(HERE), *a], capture_output=True, text=True, encoding="utf-8")

def host_images(folder: Path, names, tag):
    """PNG/JPG → JPEG 로 변환해 site/img/ 에 넣고 push. 공개 URL 목록 반환."""
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    urls, added = [], []
    for i, n in enumerate(names, 1):
        src = folder / n
        if not src.exists():
            raise FileNotFoundError(src)
        im = Image.open(src)
        if im.mode in ("RGBA", "P", "LA"):
            bg = Image.new("RGB", im.size, (255, 255, 255))
            bg.paste(im.convert("RGBA"), mask=im.convert("RGBA").split()[-1])
            im = bg
        else:
            im = im.convert("RGB")
        if im.width > 1440:  # Threads 최대폭 1440
            im = im.resize((1440, round(im.height * 1440 / im.width)), Image.LANCZOS)
        out = IMG_DIR / f"{tag}_{i:02d}.jpg"
        im.save(out, "JPEG", quality=90, optimize=True)
        added.append(out)
        urls.append(f"{PAGES_BASE}/img/{out.name}")
    _git("add", "-A", "docs/img")
    c = _git("-c", "user.name=joos7158", "-c", "user.email=dunggrun@gmail.com", "commit", "-qm", f"img {tag}")
    if c.returncode == 0:
        p = _git("push", "-q", "origin", "main")
        if p.returncode != 0:
            raise RuntimeError("git push 실패: " + p.stderr[-400:])
    # Pages 배포 대기 (최대 6분)
    for u in urls:
        for _ in range(36):
            try:
                if requests.head(u, timeout=15).status_code == 200:
                    break
            except Exception:
                pass
            time.sleep(10)
        else:
            raise RuntimeError(f"이미지 공개 URL 이 6분 안에 열리지 않음: {u}")
    log(f"이미지 {len(urls)}장 공개 완료")
    return urls

# ───────────────────────── 게시 ─────────────────────────
def _wait_container(url_fn, cid, timeout=180):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = url_fn(cid)
        st = j.get("status") or j.get("status_code")
        if st in ("FINISHED", "PUBLISHED"):
            return
        if st in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"컨테이너 실패: {json.dumps(j, ensure_ascii=False)}")
        time.sleep(5)
    log("상태 확인 시간 초과 — 그대로 publish 시도")

def post_threads(cur, text, urls, dry):
    uid, tok = cur["user_id"], cur["access_token"]
    if len(text.encode("utf-8")) > 500 * 4 or len(text) > 500:
        raise ValueError(f"쓰레드 본문 500자 초과 ({len(text)}자)")
    if dry:
        log(f"[dry] threads @{cur.get('username')} text={len(text)}자 images={len(urls)}")
        return {"id": "dry", "permalink": ""}
    if not urls:
        c = _post(f"{TH_API}/{uid}/threads", media_type="TEXT", text=text, access_token=tok)
    elif len(urls) == 1:
        c = _post(f"{TH_API}/{uid}/threads", media_type="IMAGE", image_url=urls[0], text=text, access_token=tok)
    else:
        kids = []
        for u in urls:
            k = _post(f"{TH_API}/{uid}/threads", media_type="IMAGE", image_url=u, is_carousel_item="true", access_token=tok)
            kids.append(k["id"])
        c = _post(f"{TH_API}/{uid}/threads", media_type="CAROUSEL", children=",".join(kids), text=text, access_token=tok)
    cid = c["id"]
    _wait_container(lambda i: _get(f"{TH_API}/{i}", fields="status,error_message", access_token=tok), cid)
    time.sleep(5)
    pub = _post(f"{TH_API}/{uid}/threads_publish", creation_id=cid, access_token=tok)
    mid = pub["id"]
    try:
        link = _get(f"{TH_API}/{mid}", fields="permalink", access_token=tok).get("permalink", "")
    except Exception:
        link = ""
    return {"id": mid, "permalink": link}

def post_instagram(cur, caption, urls, dry):
    uid, tok = cur["user_id"], cur["access_token"]
    if not urls:
        raise ValueError("인스타그램은 이미지가 최소 1장 필요")
    if dry:
        log(f"[dry] instagram @{cur.get('username')} caption={len(caption)}자 images={len(urls)}")
        return {"id": "dry", "permalink": ""}
    if len(urls) == 1:
        c = _post(f"{IG_API}/{uid}/media", image_url=urls[0], caption=caption, access_token=tok)
    else:
        kids = []
        for u in urls[:10]:
            k = _post(f"{IG_API}/{uid}/media", image_url=u, is_carousel_item="true", access_token=tok)
            kids.append(k["id"])
        c = _post(f"{IG_API}/{uid}/media", media_type="CAROUSEL", children=",".join(kids), caption=caption, access_token=tok)
    cid = c["id"]
    _wait_container(lambda i: _get(f"{IG_API}/{i}", fields="status_code,status", access_token=tok), cid)
    pub = _post(f"{IG_API}/{uid}/media_publish", creation_id=cid, access_token=tok)
    mid = pub["id"]
    try:
        link = _get(f"{IG_API}/{mid}", fields="permalink", access_token=tok).get("permalink", "")
    except Exception:
        link = ""
    return {"id": mid, "permalink": link}

def record(entry):
    hist = json.loads(POSTED.read_text(encoding="utf-8")) if POSTED.exists() else []
    hist.append(entry)
    POSTED.write_text(json.dumps(hist, ensure_ascii=False, indent=2), encoding="utf-8")

def cmd_post(args):
    folder = Path(args.folder).resolve()
    spec = json.loads((folder / "post.json").read_text(encoding="utf-8"))
    d = load_secrets()
    channels = ["threads", "instagram"] if args.channel == "both" else [args.channel]
    tag = f"{dt.datetime.now():%Y%m%d}_{re.sub(r'[^0-9A-Za-z가-힣]+', '', folder.name)[:24]}"
    results = {}
    for ch in channels:
        s = spec.get(ch)
        if not s:
            log(f"{ch}: post.json 에 항목 없음 — 건너뜀")
            continue
        cur = d.get(ch, {})
        if not cur.get("access_token"):
            if args.dry_run:
                cur = {"user_id": "dry", "username": "dry", "access_token": "dry"}
            else:
                log(f"{ch}: 토큰 없음 — 건너뜀 (init/auth 필요)")
                continue
        if not args.dry_run:
            cur = maybe_refresh(d, ch)
            if not cur.get("user_id"):
                cur["user_id"], cur["username"] = whoami(ch, cur)
                d[ch] = cur
                save_secrets(d)
        imgs = s.get("images", [])
        urls = []
        if imgs:
            urls = [f"{PAGES_BASE}/img/{tag}_{i:02d}.jpg" for i in range(1, len(imgs) + 1)] if args.dry_run \
                else host_images(folder, imgs, tag + ("" if ch == "threads" else "_ig"))
        text = s.get("text") or s.get("caption") or ""
        try:
            r = post_threads(cur, text, urls, args.dry_run) if ch == "threads" else post_instagram(cur, text, urls, args.dry_run)
            log(f"{ch} 게시 완료 id={r['id']} {r['permalink']}")
            results[ch] = r
            if not args.dry_run:
                record({"date": dt.datetime.now().isoformat(timespec="minutes"), "channel": ch, "folder": str(folder),
                        "id": r["id"], "permalink": r["permalink"], "chars": len(text), "images": len(urls)})
        except Exception as e:
            log(f"{ch} 게시 실패: {e}")
            results[ch] = {"error": str(e)}
            if not args.dry_run:
                record({"date": dt.datetime.now().isoformat(timespec="minutes"), "channel": ch, "folder": str(folder),
                        "error": str(e)[:300]})
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return all("error" not in v for v in results.values()) and bool(results)

def cmd_status(args):
    hist = json.loads(POSTED.read_text(encoding="utf-8")) if POSTED.exists() else []
    for e in hist[-args.n:]:
        print(f"{e['date']}  {e['channel']:9s}  {e.get('permalink') or e.get('error','')}")
    if not hist:
        print("게시 기록 없음")

# ───────────────────────── main ─────────────────────────
def main():
    ap = argparse.ArgumentParser(description="신수학 SNS 자동 게시기")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    a = sub.add_parser("auth"); a.add_argument("--channel", required=True)
    sub.add_parser("whoami")
    sub.add_parser("refresh")
    p = sub.add_parser("post"); p.add_argument("--folder", required=True); p.add_argument("--channel", default="both")
    p.add_argument("--dry-run", action="store_true")
    s = sub.add_parser("status"); s.add_argument("-n", type=int, default=10)
    args = ap.parse_args()
    fn = {"init": cmd_init, "auth": cmd_auth, "whoami": cmd_whoami, "refresh": cmd_refresh, "post": cmd_post, "status": cmd_status}[args.cmd]
    ok = fn(args)
    sys.exit(0 if ok in (None, True) else 1)

if __name__ == "__main__":
    main()
