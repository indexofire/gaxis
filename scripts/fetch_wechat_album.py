"""Fetch every article of a WeChat album and collect its figures.

WeChat blocks desktop UAs (it returns a captcha page); a mobile UA plus a mp.weixin.qq.com
Referer works. The album list itself is a JSON endpoint; each article's body is JS-rendered,
so figures are taken from the image URLs embedded in the HTML.

    pixi run python scripts/fetch_wechat_album.py --out data/corpus/wechat-series

Output:
    <out>/<NN>-<slug>/article.json      title, url, figures[]
    <out>/<NN>-<slug>/img-XX.<ext>
    <out>/index.json                    all articles, figure counts, dedupe map
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import time
from pathlib import Path

UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
BIZ = "MzcwNzQ5NzI1Ng=="
ALBUM = "4766029750777905158"
ALBUM_API = (
    "https://mp.weixin.qq.com/mp/appmsgalbum?action=getalbum&__biz={biz}"
    "&album_id={album}&f=json&count=20&begin_msgid={msgid}&begin_itemidx={itemidx}"
)
MIN_BYTES = 40_000
MIN_SIDE = 400


def _curl(
    url: str, target: Path | None = None, referer: str = "https://mp.weixin.qq.com/"
) -> bytes:
    command = ["curl", "-sSL", "--max-time", "60", "-A", UA, "-H", f"Referer: {referer}"]
    if target is not None:
        command += ["-o", str(target)]
    command.append(url)
    completed = subprocess.run(command, capture_output=True, text=True)
    if target is not None:
        return b""
    return completed.stdout.encode("utf-8", errors="replace")


def list_articles() -> list[dict]:
    articles: list[dict] = []
    msgid, itemidx = "", ""
    for _ in range(20):
        url = ALBUM_API.format(biz=BIZ, album=ALBUM, msgid=msgid, itemidx=itemidx)
        payload = json.loads(_curl(url).decode("utf-8", errors="replace"))
        response = payload.get("getalbum_resp") or {}
        batch = response.get("article_list") or []
        articles.extend(batch)
        if not response.get("has_more") or not batch:
            break
        last = batch[-1]
        msgid, itemidx = str(last.get("msgid", "")), str(last.get("itemidx", ""))
        if not msgid:
            break
        time.sleep(1.0)
    return articles


def figure_urls(html: str) -> list[str]:
    urls: list[str] = []
    for match in re.finditer(r"https?://mmbiz\.qpic\.cn/[A-Za-z0-9_./?=&%\-]+", html):
        url = match.group(0).rstrip("\\").rstrip('"').rstrip("'")
        if ("mmbiz_png" in url or "mmbiz_jpg" in url) and url not in urls:
            urls.append(url)
    return urls


def _slug(title: str) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff]+", "-", title).strip("-")
    return cleaned[:60] or "article"


def _image_ok(path: Path) -> bool:
    from PIL import Image

    try:
        with Image.open(path) as handle:
            width, height = handle.size
            return path.stat().st_size >= MIN_BYTES and min(width, height) >= MIN_SIDE
    except Exception:
        return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("data/corpus/wechat-series"))
    parser.add_argument("--max-articles", type=int, default=40)
    parser.add_argument("--max-images", type=int, default=40)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    articles = list_articles()[: args.max_articles]
    print(f"album: {len(articles)} article(s) found")
    index: list[dict] = []
    seen_hashes: dict[str, str] = {}
    for number, article in enumerate(articles, start=1):
        title = str(article.get("title") or "untitled").strip()
        url = str(article.get("url") or "")
        slug = _slug(title)
        folder = args.out / f"{number:02d}-{slug}"
        folder.mkdir(parents=True, exist_ok=True)
        if not url.startswith("http"):
            print(f"[{number:02d}] no url: {title[:50]}")
            continue
        html = _curl(url).decode("utf-8", errors="replace")
        urls = figure_urls(html)[: args.max_images]
        figures: list[dict] = []
        for position, image_url in enumerate(urls, start=1):
            suffix = ".jpg" if "mmbiz_jpg" in image_url or "wx_fmt=jpeg" in image_url else ".png"
            target = folder / f"img-{position:02d}{suffix}"
            if not target.exists():
                _curl(image_url, target)
                time.sleep(0.3)
            if not _image_ok(target):
                target.unlink(missing_ok=True)
                continue
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            duplicate_of = seen_hashes.get(digest)
            if duplicate_of is None:
                seen_hashes[digest] = f"{folder.name}/{target.name}"
            figures.append(
                {
                    "file": f"{folder.name}/{target.name}",
                    "sha256": digest,
                    "duplicate_of": duplicate_of,
                }
            )
        metadata = {"number": number, "title": title, "url": url, "figures": figures}
        (folder / "article.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        index.append(metadata)
        unique = len([figure for figure in figures if not figure["duplicate_of"]])
        print(f"[{number:02d}] {unique:>2} unique figure(s)  {title[:50]}")

    (args.out / "index.json").write_text(
        json.dumps({"articles": index, "unique": len(seen_hashes)}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    print(f"total unique figures: {len(seen_hashes)}")


if __name__ == "__main__":
    main()
