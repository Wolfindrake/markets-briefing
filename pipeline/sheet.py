"""One-page Markets Briefing sheet (PDF + XLSX) in the course format:

  header (title, date, data-as-of time) | 35-instrument table | source note |
  Market performance (Equities / Fixed income / Others) |
  Market commentary (Overview + Highlights) | Week ahead | S&P 500 view
"""
from __future__ import annotations

from datetime import date
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .compute import PERF_KEYS, display
from .config import GROUPS

HEAD = ["Name", "Symbol", "Last", "Open", "Prev.", "Chg.", "Chg. %", "Daily", "1 Week", "1 Month", "YTD", "1 Year", "3 Years"]
FIELDS = ["name", "symbol", "last", "open", "prev", "chg", "chg_pct", "daily"] + PERF_KEYS
GREEN, RED, INK, MUTED, BAND = "#1a7f37", "#c62828", "#111827", "#6b7280", "#eef2f7"


def _ddmmyyyy(iso: str) -> str:
    d = date.fromisoformat(iso)
    return d.strftime("%d/%m/%Y")


def _color(s: str):
    if s.startswith("+") and s.strip("+0.%bp ,") != "":
        return GREEN
    if s.startswith("-") and s.strip("-0.%bp ,") != "":
        return RED
    return INK


# --------------------------------------------------------------------------- PDF

def _pdf_story(meta, rows, brief, fs):
    small = ParagraphStyle("s", fontName="Helvetica", fontSize=fs, leading=fs * 1.22, textColor=colors.HexColor(INK))
    note = ParagraphStyle("n", parent=small, fontName="Helvetica-Oblique", textColor=colors.HexColor(MUTED), fontSize=fs * 0.9)
    h1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=fs * 2.0, leading=fs * 2.3, textColor=colors.HexColor(INK))
    h2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=fs * 1.25, leading=fs * 1.6, spaceBefore=fs * 0.6, textColor=colors.HexColor(INK))
    h3 = ParagraphStyle("h3", parent=small, fontName="Helvetica-Bold")

    story = [Paragraph(escape(meta["title"]), h1)]
    hdr = Table(
        [["Date", _ddmmyyyy(meta["market_date"])], ["Data as of", meta["as_of"]]],
        colWidths=[70, 300], hAlign="LEFT",
    )
    hdr.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), "Helvetica", fs), ("FONT", (0, 0), (0, -1), "Helvetica-Bold", fs),
                             ("BOTTOMPADDING", (0, 0), (-1, -1), 1), ("TOPPADDING", (0, 0), (-1, -1), 0)]))
    story += [hdr, Spacer(1, fs * 0.6)]

    data = [HEAD]
    tfs = fs * 0.88  # table font: slightly smaller so 13 columns fit on A4 portrait
    styles = [
        ("FONT", (0, 0), (-1, -1), "Helvetica", tfs),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", tfs),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(INK)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 0.6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0.6),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ]
    for gkey, glabel in GROUPS:
        r0 = len(data)
        data.append([glabel] + [""] * (len(HEAD) - 1))
        styles += [("SPAN", (0, r0), (-1, r0)), ("FONT", (0, r0), (-1, r0), "Helvetica-Bold", tfs),
                   ("BACKGROUND", (0, r0), (-1, r0), colors.HexColor(BAND))]
        for row in [r for r in rows if r["group"] == gkey]:
            d = display(row)
            ri = len(data)
            data.append([d[f] for f in FIELDS])
            for ci, f in enumerate(FIELDS):
                if ci >= 5:
                    styles.append(("TEXTCOLOR", (ci, ri), (ci, ri), colors.HexColor(_color(d[f]))))
    widths = [118, 58] + [39] * 3 + [33.25] * 8
    t = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle(styles))
    story += [t, Spacer(1, 2), Paragraph(escape(meta["source_note"]), note)]

    def bullets(items, mark):
        return [Paragraph(f"{mark} {escape(str(x))}", small) for x in items or []]

    perf = brief.get("performance") or {}
    story.append(Paragraph("Market performance", h2))
    for key, label in (("equities", "Equities"), ("fixed_income", "Fixed income"), ("others", "Others")):
        if perf.get(key):
            story.append(Paragraph(label, h3))
            story += bullets(perf[key], "-")

    story.append(Paragraph("Market commentary: what happened since the last session", h2))
    if brief.get("overview"):
        story.append(Paragraph("Overview", h3))
        story += bullets([brief["overview"]], "•")   # the professor writes the overview as one bullet
    if brief.get("highlights"):
        story.append(Paragraph("Highlights", h3))
        story += bullets(brief["highlights"], "•")

    wa = brief.get("week_ahead") or []
    if wa:
        story.append(Paragraph("Week ahead", h2))
        rows_wa = [["Day", "Region", "Event", "Consensus", "Previous"]]
        cell = ParagraphStyle("c", parent=small)
        for e in wa:
            rows_wa.append([e.get("day", ""), e.get("region", ""), Paragraph(escape(str(e.get("event", ""))), cell),
                            e.get("consensus", "") or "", e.get("previous", "") or ""])
        tw = Table(rows_wa, colWidths=[52, 44, 333, 65, 65], hAlign="LEFT")
        tw.setStyle(TableStyle([
            ("FONT", (0, 0), (-1, -1), "Helvetica", fs), ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", fs),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor(INK)), ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 0.6), ("BOTTOMPADDING", (0, 0), (-1, -1), 0.6),
            ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ]))
        story.append(tw)

    view = brief.get("sp500_view") or {}
    if view.get("call"):
        story.append(Spacer(1, fs * 0.5))
        txt = f"<b>S&amp;P 500 view:</b> {escape(str(view.get('call')))}"
        if view.get("reason"):
            txt += f". {escape(str(view['reason']))}"
        story.append(Paragraph(txt, small))
    if meta.get("team_label"):
        story.append(Paragraph(escape(meta["team_label"]), note))
    return story


def build_pdf(path: Path, meta, rows, brief) -> float:
    """Shrinks the font until everything fits on one A4 page. Returns the font size used."""
    for fs in (7.6, 7.2, 6.8, 6.4, 6.0, 5.6, 5.2, 4.8):
        buf = BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18, rightMargin=18, topMargin=18, bottomMargin=16,
                                title=meta["title"], author="")
        doc.build(_pdf_story(meta, rows, brief, fs))
        if getattr(doc, "page", 1) <= 1 or fs == 4.8:
            path.write_bytes(buf.getvalue())
            return fs
    return fs


# --------------------------------------------------------------------------- XLSX

def build_xlsx(path: Path, meta, rows, brief) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Briefing"
    thin = Side(style="thin", color="CBD5E1")
    bold = Font(name="Calibri", bold=True, size=9)
    base = Font(name="Calibri", size=9)
    r = 1
    ws.cell(r, 1, meta["title"]).font = Font(name="Calibri", bold=True, size=16)
    r += 1
    ws.cell(r, 1, "Date").font = bold
    ws.cell(r, 3, _ddmmyyyy(meta["market_date"])).font = base
    r += 1
    ws.cell(r, 1, "Data as of").font = bold
    ws.cell(r, 3, meta["as_of"]).font = base
    r += 2
    for ci, h in enumerate(HEAD, 1):
        c = ws.cell(r, ci, h)
        c.font = Font(name="Calibri", bold=True, size=9, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor=INK.lstrip("#"))
        c.alignment = Alignment(horizontal="right" if ci > 2 else "left")
    r += 1
    for gkey, glabel in GROUPS:
        c = ws.cell(r, 1, glabel)
        c.font = bold
        for ci in range(1, len(HEAD) + 1):
            ws.cell(r, ci).fill = PatternFill("solid", fgColor=BAND.lstrip("#"))
        r += 1
        for row in [x for x in rows if x["group"] == gkey]:
            d = display(row)
            for ci, f in enumerate(FIELDS, 1):
                c = ws.cell(r, ci, d[f])
                c.font = Font(name="Calibri", size=9, color=_color(d[f]).lstrip("#") if ci >= 6 else INK.lstrip("#"))
                c.alignment = Alignment(horizontal="right" if ci > 2 else "left")
                c.border = Border(bottom=thin)
            r += 1
    ws.cell(r, 1, meta["source_note"]).font = Font(name="Calibri", italic=True, size=8, color=MUTED.lstrip("#"))
    r += 2

    def section(title):
        nonlocal r
        ws.cell(r, 1, title).font = Font(name="Calibri", bold=True, size=11)
        r += 1

    def lines(items, mark):
        nonlocal r
        for x in items or []:
            c = ws.cell(r, 1, f"{mark} {x}")
            c.font = base
            c.alignment = Alignment(wrap_text=False)
            r += 1

    perf = brief.get("performance") or {}
    section("Market performance")
    for key, label in (("equities", "Equities"), ("fixed_income", "Fixed income"), ("others", "Others")):
        if perf.get(key):
            ws.cell(r, 1, label).font = bold
            r += 1
            lines(perf[key], "-")
    r += 1
    section("Market commentary: what happened since the last session")
    if brief.get("overview"):
        ws.cell(r, 1, "Overview").font = bold
        r += 1
        lines([brief["overview"]], "•")
    if brief.get("highlights"):
        ws.cell(r, 1, "Highlights").font = bold
        r += 1
        lines(brief["highlights"], "•")
    r += 1
    wa = brief.get("week_ahead") or []
    if wa:
        section("Week ahead")
        for ci, h in enumerate(["Day", "Region", "Event", "", "", "", "", "", "", "", "Consensus", "", "Previous"], 1):
            if h:
                ws.cell(r, ci, h).font = bold
        r += 1
        for e in wa:
            ws.cell(r, 1, e.get("day", "")).font = base
            ws.cell(r, 2, e.get("region", "")).font = base
            ws.cell(r, 3, e.get("event", "")).font = base
            ws.cell(r, 11, e.get("consensus", "") or "").font = base
            ws.cell(r, 13, e.get("previous", "") or "").font = base
            r += 1
    view = brief.get("sp500_view") or {}
    if view.get("call"):
        r += 1
        ws.cell(r, 1, f"S&P 500 view: {view.get('call')}. {view.get('reason', '')}".strip()).font = bold

    widths = [34, 14] + [11] * 11
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.page_setup.orientation = "portrait"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_options.horizontalCentered = True
    ws.page_margins.left = ws.page_margins.right = 0.3
    ws.page_margins.top = ws.page_margins.bottom = 0.3

    # raw numbers for anyone who wants to calculate
    raw = wb.create_sheet("Data")
    cols = ["key", "name", "group", "unit", "date", "last", "open", "prev", "chg", "chg_pct"] + [f"perf_{k}" for k in PERF_KEYS] + ["source"]
    raw.append(cols)
    for row in rows:
        raw.append([row["key"], row["name"], row["group"], row["unit"], row["date"], row["last"], row["open"], row["prev"],
                    row["chg"], row["chg_pct"]] + [row["perf"][k] for k in PERF_KEYS] + [row["source"]])
    wb.properties.creator = ""
    wb.save(path)
