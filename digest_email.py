"""
digest_email.py — the nightly digest's email layout (owner 2026-11-07:
"please format in a readable, world-class pro format").

The nightly job writes the digest as JSON (schema below) and this renders it
to email-safe HTML: table layout, inline styles, one 640px column that reads
on a phone, KPI tiles, decision cards with the exact reply to send, and
colour-coded results. Send the HTML ONLY (no plain-text part): some mail apps
show the text part when both exist. Stdlib only.

    python3 digest_email.py digest.json out.html     render
    python3 digest_email.py --selftest              smoke test

Worked example (the first nightly digest, 2026-11-07): digest_example.json

Schema
  {"date": "Sat 7 Nov 2026", "prepared": "23:10 UAE", "headline": "...",
   "kpis": [{"label", "value", "sub", "tone": "pos|neg|neutral"}],     # 2-4 tiles
   "decisions": [{"title", "detail", "reply"}],                       # [] = none
   "sections": [{"title", "blocks": [
       {"type": "para", "text"},
       {"type": "bullets", "items": [text, ...]},
       {"type": "table", "columns": [...], "align": ["l","r",...],
        "rows": [[cell, ...]]},            # cell = text or {"text", "tone"}
       {"type": "callout", "tone": "info|warn|good", "text"}]}],
   "links": [{"label", "url"}]}
Text supports **bold**. Tones: pos (green), neg (red), muted (grey),
pass / fail / near / info (badges).
"""

import html
import json
import re
import sys

INK, MUTED, LINE, BG, CARD = "#1a1f2b", "#6b7280", "#e5e7eb", "#f3f4f6", "#ffffff"
NAVY, GOLD = "#0f2742", "#c9a227"
GREEN, RED, AMBER, BLUE = "#0f7b3f", "#b42318", "#a15c07", "#1d4ed8"
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"

BADGE = {"pass": ("#e7f6ec", GREEN), "fail": ("#fdecec", RED), "near": ("#fff4e0", AMBER),
         "info": ("#e8efff", BLUE), "muted": ("#f1f2f4", MUTED)}
TONE = {"pos": GREEN, "neg": RED, "muted": MUTED, "neutral": INK}


def _t(text):
    """Escape, then allow **bold**."""
    s = html.escape(str(text if text is not None else ""))
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)


def _cell(c, align="l"):
    if isinstance(c, dict):
        text, tone = c.get("text", ""), c.get("tone")
    else:
        text, tone = c, None
    a = "right" if align == "r" else "center" if align == "c" else "left"
    inner = _t(text)
    if tone in BADGE:
        bg, fg = BADGE[tone]
        inner = (f'<span style="display:inline-block;padding:2px 8px;border-radius:10px;background:{bg};'
                 f'color:{fg};font-size:12px;font-weight:600;white-space:nowrap">{inner}</span>')
    elif tone in TONE:
        inner = f'<span style="color:{TONE[tone]};font-weight:600">{inner}</span>'
    return (f'<td style="padding:8px 6px;border-bottom:1px solid {LINE};text-align:{a};'
            f'vertical-align:top;font-size:13px;line-height:1.4">{inner}</td>')


def _block(b):
    k = b.get("type")
    if k == "para":
        return f'<p style="margin:0 0 12px;font-size:15px;line-height:1.55;color:{INK}">{_t(b["text"])}</p>'
    if k == "bullets":
        items = "".join(f'<li style="margin:0 0 8px">{_t(i)}</li>' for i in b["items"])
        return (f'<ul style="margin:0 0 12px;padding-left:20px;font-size:15px;line-height:1.5;'
                f'color:{INK}">{items}</ul>')
    if k == "callout":
        bg, fg = {"warn": ("#fff8e6", AMBER), "good": ("#ecf7f0", GREEN)}.get(b.get("tone"), ("#eef3ff", BLUE))
        return (f'<div style="margin:0 0 12px;padding:10px 12px;border-left:4px solid {fg};background:{bg};'
                f'font-size:14px;line-height:1.5;color:{INK}">{_t(b["text"])}</div>')
    if k == "table":
        al = b.get("align") or ["l"] * len(b["columns"])
        head = "".join(
            f'<th style="padding:6px;border-bottom:2px solid {INK};text-align:'
            f'{"right" if a == "r" else "center" if a == "c" else "left"};font-size:11px;'
            f'letter-spacing:.04em;text-transform:uppercase;color:{MUTED};font-weight:600">{_t(c)}</th>'
            for c, a in zip(b["columns"], al))
        rows = "".join("<tr>" + "".join(_cell(c, a) for c, a in zip(r, al)) + "</tr>" for r in b["rows"])
        return (f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
                f'style="border-collapse:collapse;margin:0 0 12px">'
                f'<tr>{head}</tr>{rows}</table>')
    raise ValueError(f"unknown block type {k!r}")


def _card(inner, pad="18px 18px 6px"):
    return (f'<tr><td style="padding:0 12px 14px"><table role="presentation" width="100%" cellspacing="0" '
            f'cellpadding="0" style="background:{CARD};border:1px solid {LINE};border-radius:10px">'
            f'<tr><td style="padding:{pad}">{inner}</td></tr></table></td></tr>')


def _h(n, title):
    return (f'<div style="margin:0 0 12px;font-size:12px;letter-spacing:.08em;text-transform:uppercase;'
            f'color:{MUTED};font-weight:700">{n} &nbsp;·&nbsp; {_t(title)}</div>')


def render(d):
    out = []
    # header band
    out.append(
        f'<tr><td style="padding:22px 22px 18px;background:{NAVY};border-radius:10px 10px 0 0">'
        f'<div style="font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:{GOLD};'
        f'font-weight:700">Logicon Capital · Daily Digest</div>'
        f'<div style="font-size:22px;line-height:1.3;color:#fff;font-weight:700;margin-top:6px">{_t(d["date"])}</div>'
        f'<div style="font-size:15px;line-height:1.45;color:#dbe4f0;margin-top:8px">{_t(d.get("headline", ""))}</div>'
        f'<div style="font-size:12px;color:#9fb0c6;margin-top:10px">Prepared {_t(d.get("prepared", ""))} · '
        f'recommendations only — every approval is yours</div></td></tr>')
    # KPI tiles (two per row: phone-safe)
    kp = d.get("kpis") or []
    if kp:
        rows = []
        for i in range(0, len(kp), 2):
            tds = ""
            for k in kp[i:i + 2]:
                col = TONE.get(k.get("tone", "neutral"), INK)
                tds += (f'<td width="50%" style="padding:6px"><table role="presentation" width="100%" '
                        f'cellspacing="0" cellpadding="0" style="background:{CARD};border:1px solid {LINE};'
                        f'border-radius:8px"><tr><td style="padding:12px">'
                        f'<div style="font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:{MUTED};'
                        f'font-weight:600">{_t(k["label"])}</div>'
                        f'<div style="font-size:22px;font-weight:700;color:{col};margin-top:4px">{_t(k["value"])}</div>'
                        f'<div style="font-size:12px;color:{MUTED};margin-top:2px">{_t(k.get("sub", ""))}</div>'
                        f'</td></tr></table></td>')
            if len(kp[i:i + 2]) == 1:
                tds += '<td width="50%"></td>'
            rows.append(f"<tr>{tds}</tr>")
        out.append(f'<tr><td style="padding:12px 6px 6px"><table role="presentation" width="100%" '
                   f'cellspacing="0" cellpadding="0">{"".join(rows)}</table></td></tr>')
    # decisions
    dec = d.get("decisions") or []
    inner = _h(1, f"Decisions for you ({len(dec)})")
    if not dec:
        inner += f'<p style="margin:0 0 12px;font-size:15px;color:{INK}">None tonight.</p>'
    for n, x in enumerate(dec, 1):
        inner += (f'<div style="margin:0 0 12px;padding:12px;border:1px solid {LINE};border-left:4px solid {GOLD};'
                  f'border-radius:6px">'
                  f'<div style="font-size:15px;font-weight:700;color:{INK}">{n}. {_t(x["title"])}</div>'
                  f'<div style="font-size:14px;line-height:1.5;color:{INK};margin-top:4px">{_t(x.get("detail", ""))}</div>'
                  + (f'<div style="margin-top:8px;font-size:13px;color:{MUTED}">Reply: <span style="display:inline-block;'
                     f'padding:2px 8px;border-radius:4px;background:{BG};color:{INK};font-family:Menlo,Consolas,monospace">'
                     f'{_t(x["reply"])}</span></div>' if x.get("reply") else "")
                  + '</div>')
    out.append(_card(inner))
    # sections
    for n, s in enumerate(d.get("sections") or [], 2):
        out.append(_card(_h(n, s["title"]) + "".join(_block(b) for b in s["blocks"])))
    # footer
    links = " &nbsp;·&nbsp; ".join(f'<a href="{html.escape(l["url"])}" style="color:{BLUE};text-decoration:none">'
                                   f'{_t(l["label"])}</a>' for l in d.get("links") or [])
    out.append(f'<tr><td style="padding:4px 18px 24px;font-size:12px;line-height:1.6;color:{MUTED};'
               f'text-align:center">{links}<br>Times in UAE (UTC+4). Sent nightly at 22:13 by your research '
               f'assistant.</td></tr>')
    return (f'<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" '
            f'content="width=device-width,initial-scale=1"><title>Daily Digest</title></head>'
            f'<body style="margin:0;padding:0;background:{BG}">'
            f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:{BG}">'
            f'<tr><td align="center" style="padding:12px 0">'
            f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
            f'style="max-width:640px;font-family:{FONT};color:{INK}">{"".join(out)}</table>'
            f'</td></tr></table></body></html>')


def _selftest():
    d = {"date": "Sat 7 Nov 2026", "prepared": "23:10 UAE", "headline": "One **bold** line",
         "kpis": [{"label": "A", "value": "+$1", "tone": "pos"}, {"label": "B", "value": "0"},
                  {"label": "C", "value": "-1", "tone": "neg"}],
         "decisions": [{"title": "T", "detail": "D <script>", "reply": "go X"}],
         "sections": [{"title": "S", "blocks": [
             {"type": "para", "text": "p"}, {"type": "bullets", "items": ["a", "b"]},
             {"type": "callout", "tone": "warn", "text": "c"},
             {"type": "table", "columns": ["x", "y"], "align": ["l", "r"],
              "rows": [["a", {"text": "PASS", "tone": "pass"}], ["b", {"text": "-$3", "tone": "neg"}]]}]}],
         "links": [{"label": "L", "url": "https://x"}]}
    h = render(d)
    assert "<b>bold</b>" in h and "&lt;script&gt;" in h and "<script>" not in h
    assert h.count("Decisions for you (1)") == 1 and "go X" in h and "max-width:640px" in h
    assert '<td width="50%"></td>' in h                      # odd KPI count padded
    print("digest_email selftest: ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        src, dst = sys.argv[1], sys.argv[2]
        open(dst, "w").write(render(json.load(open(src))))
        print("wrote", dst)
