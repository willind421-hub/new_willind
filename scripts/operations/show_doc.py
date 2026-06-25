"""운영자이 사용자에게 보여줄 문서(md/html 등)를 화면에 자동으로 띄운다.

사용: python scripts/operations/show_doc.py <파일경로>

동작:
  - .html / .htm  → 기본 브라우저로 바로 띄움
  - .md / .markdown → marked.js로 렌더링한 임시 HTML을 만들어 브라우저로 띄움
  - 그 외(.txt 등) → OS 기본 연결 프로그램으로 띄움

사용자이 파일 경로를 찾아 헤매지 않게, 문서를 만들면 곧바로 눈앞에 띄우는 게 목적.
"""
import sys
import os
import html
import webbrowser
from pathlib import Path

_ROOT = next((p for p in Path(__file__).resolve().parents if (p / "registry" / "_index.yaml").exists()), Path(__file__).resolve().parent)
RUNTIME_DIR = _ROOT / "runtime" / "show-doc"

MD_TEMPLATE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  body {{ max-width: 820px; margin: 40px auto; padding: 0 20px;
    font-family: "Pretendard","Malgun Gothic",system-ui,sans-serif;
    line-height: 1.7; color: #222; }}
  h1,h2,h3 {{ line-height: 1.3; margin-top: 1.6em; }}
  h1 {{ border-bottom: 2px solid #eee; padding-bottom: .3em; }}
  h2 {{ border-bottom: 1px solid #eee; padding-bottom: .2em; }}
  code {{ background:#f4f4f4; padding:2px 5px; border-radius:4px; font-size:.9em; }}
  pre code {{ display:block; padding:14px; overflow-x:auto; }}
  blockquote {{ border-left:4px solid #ddd; margin:1em 0; padding:.4em 1em; color:#555; background:#fafafa; }}
  table {{ border-collapse: collapse; }}
  th,td {{ border:1px solid #ddd; padding:6px 12px; }}
  a {{ color:#0a66c2; }}
  .src {{ display:none; }}
</style></head><body>
<textarea class="src" id="src">{escaped}</textarea>
<div id="out">렌더링 중...</div>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<script>
  var raw = document.getElementById('src').value;
  try {{
    document.getElementById('out').innerHTML = marked.parse(raw);
  }} catch (e) {{
    document.getElementById('out').innerText = raw;  // CDN 실패 시 원문이라도 보이게
  }}
</script></body></html>
"""


def open_in_browser(path: Path):
    webbrowser.open(path.resolve().as_uri())


def show(target: str):
    src = Path(target)
    if not src.exists():
        print(f"ERROR: 파일 없음 -> {src}")
        return 1
    ext = src.suffix.lower()

    if ext in (".html", ".htm"):
        open_in_browser(src)
        print(f"띄움(브라우저): {src}")
        return 0

    if ext in (".md", ".markdown"):
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        md_text = src.read_text(encoding="utf-8")
        out_html = RUNTIME_DIR / (src.stem + ".html")
        out_html.write_text(
            MD_TEMPLATE.format(title=src.stem, escaped=html.escape(md_text)),
            encoding="utf-8",
        )
        open_in_browser(out_html)
        print(f"띄움(md 렌더링): {src} -> {out_html}")
        return 0

    # 그 외: OS 기본 프로그램
    try:
        os.startfile(str(src.resolve()))  # type: ignore[attr-defined]
        print(f"띄움(기본 프로그램): {src}")
        return 0
    except Exception as e:
        print(f"ERROR: 띄우기 실패 -> {e}")
        return 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용: python scripts/operations/show_doc.py <파일경로>")
        sys.exit(2)
    sys.exit(show(sys.argv[1]))


