#!/usr/bin/env python3
"""Inline web/*.html into src/page.h as PROGMEM strings (run before build).

Keeps the HTML as real .html files (editable, syntax-highlighted) while still
embedding them in the firmware. A conservative minifier shrinks them (CSS/HTML
aggressive; JS safe — no strings/ASI broken).

  web/index.html  -> const char PAGE[]       (dashboard)
  web/blocked.html-> const char BLOCK_TMPL[] (block page; {{HOST}}/{{REASON}} tokens)

Set env MINIFY=0 to disable minification.
"""
import os
import re

try:
    Import("env")                       # noqa: F821  (PlatformIO SCons context)
    ROOT = env.subst("$PROJECT_DIR")    # noqa: F821
except Exception:
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

WEB = os.path.join(ROOT, "web")
OUT = os.path.join(ROOT, "src", "page.h")
MINIFY = os.environ.get("MINIFY", "1") not in ("0", "false", "no")


def min_css(css: str) -> str:
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    css = re.sub(r"\s+", " ", css)
    css = re.sub(r"\s*([{}:;,>])\s*", r"\1", css)
    return css.replace(";}", "}").strip()


def min_js(js: str) -> str:
    # Safe: drop block comments + full-line // comments + indentation/blank lines.
    # Newlines are kept (ASI-safe); strings are never touched.
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    out = []
    for ln in js.split("\n"):
        s = ln.strip()
        if s.startswith("//"):
            continue
        if s:
            out.append(s)
    return "\n".join(out)


def min_html(html: str) -> str:
    stash = []

    def keep(m):
        stash.append(m.group(0))
        return "\x00%d\x00" % (len(stash) - 1)

    html = re.sub(r"<style[^>]*>.*?</style>", keep, html, flags=re.S | re.I)
    html = re.sub(r"<script[^>]*>.*?</script>", keep, html, flags=re.S | re.I)
    html = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    html = html.replace("\n", " ")
    html = re.sub(r"\s{2,}", " ", html)
    html = re.sub(r">\s+<", "><", html)
    html = html.strip()

    def restore(m):
        blk = stash[int(m.group(1))]
        head = re.match(r"<(style|script)([^>]*)>", blk, re.I)
        tag, attrs = head.group(1).lower(), head.group(2)
        inner = blk[head.end(): blk.lower().rfind("</" + tag + ">")]
        return "<%s%s>%s</%s>" % (tag, attrs, min_css(inner) if tag == "style" else min_js(inner), tag)

    return re.sub(r"\x00(\d+)\x00", restore, html)


def read(name):
    p = os.path.join(WEB, name)
    return open(p, encoding="utf-8").read() if os.path.exists(p) else ""


def emit(var, delim, text):
    return 'const char %s[] PROGMEM = R"%s(%s)%s";\n\n' % (var, delim, text, delim)


def main():
    idx = read("index.html")
    blk = read("blocked.html")
    if MINIFY:
        idx, blk = min_html(idx), min_html(blk)
    # Inline the vendored VanJS (web/van.min.js) so the UI works offline. If the file is
    # absent, the CDN <script src> in index.html is left as-is (requires internet).
    van = read("van.min.js")
    if van:
        before = idx
        idx = re.sub(r'<script[^>]*src="[^"]*van[^"]*"[^>]*></script>', lambda m: "<script>" + van + "</script>", idx)
        if idx == before:
            print("[build_web] WARN: van.min.js present but no CDN <script src=...van...> found to inline")
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("#pragma once\n// GENERATED from web/*.html by tools/build_web.py — do not edit.\n\n")
        f.write(emit("PAGE", "PAGEHTML", idx))
        f.write(emit("BLOCK_TMPL", "BLKHTML", blk))
    print("[build_web] src/page.h: index=%dB blocked=%dB (minify=%s, vanjs=%s)" % (len(idx), len(blk), MINIFY, "inline" if van else "cdn"))


main()
