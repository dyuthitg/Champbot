"""
Generates Week1_UI_Audit_Closed.pdf -- the Aug 26 Operator UI Audit, reopened
and closed. Every line from that audit gets a status and, where it's still
open, one sentence for why. Plus what shipped alongside it today: a
responsive pass at 860/540px, keyboard and focus states everywhere, and
loading/transition polish that respects prefers-reduced-motion.

Screenshots are real, taken against the running app on 2026-09-14 (dev
server + a local SQLite backend, dev auth token) -- not mockups.

Run: python scripts/build_week1_audit_closed_pdf.py
"""

import os

from PIL import Image
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Image as RLImage,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

IMG_DIR = os.path.join(os.path.dirname(__file__), "..", ".playwright-mcp")
OUT_PATH = "Week1_UI_Audit_Closed.pdf"

NAVY = colors.HexColor("#2f3b52")
ACCENT = colors.HexColor("#c85a24")
GREEN = colors.HexColor("#1f7a4a")
LINE_C = colors.HexColor("#bbbbbb")
STRIPE = colors.HexColor("#f4f6f8")
MUTED = colors.HexColor("#666666")

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="TitleBig", fontSize=20, leading=24, spaceAfter=4, fontName="Helvetica-Bold"))
styles.add(ParagraphStyle(name="SubTitle", fontSize=10.5, leading=14, textColor=MUTED))
styles.add(ParagraphStyle(name="H1", fontSize=13.5, leading=17, spaceBefore=18, spaceAfter=6, fontName="Helvetica-Bold", textColor=colors.HexColor("#1a1a1a")))
styles.add(ParagraphStyle(name="Body", fontSize=10, leading=15, spaceAfter=6))
styles.add(ParagraphStyle(name="Small", fontSize=8.7, leading=12, textColor=MUTED))
styles.add(ParagraphStyle(name="Cell", fontSize=9, leading=12.5))
styles.add(ParagraphStyle(name="CellHead", fontSize=8.9, leading=11.5, fontName="Helvetica-Bold", textColor=colors.white))
styles.add(ParagraphStyle(name="Caption", fontSize=8.7, leading=12, textColor=MUTED, spaceBefore=4, spaceAfter=10))

story = []


def grid(rows, col_widths):
    t = Table(rows, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, LINE_C),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, STRIPE]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def img_flowable(name, max_width=3.05 * inch, max_height=4.0 * inch):
    path = os.path.join(IMG_DIR, name)
    im = Image.open(path)
    w, h = im.size
    ratio = min(max_width / w, max_height / h)
    return RLImage(path, width=w * ratio, height=h * ratio)


def status_tag(label, done):
    color = "#1f7a4a" if done else "#a5680f"
    return Paragraph(f'<font color="{color}"><b>{label}</b></font>', styles["Cell"])


# ---------------------------------------------------------------- Header ---
story.append(Paragraph("Week 1 UI Audit — Closed", styles["TitleBig"]))
story.append(Paragraph(
    "Dyuthi T G &nbsp;&bull;&nbsp; 2026-09-14 &nbsp;&bull;&nbsp; reopening the Aug 26 Operator UI Audit to close it",
    styles["SubTitle"],
))
story.append(Spacer(1, 6))
story.append(HRFlowable(width="100%", thickness=1, color=LINE_C))
story.append(Spacer(1, 10))
story.append(Paragraph(
    "I wrote the Aug 26 audit myself, so today I went back to it and closed the list — line by line, "
    "not just the easy ones. Seven of the nine findings are done: four of them were actually closed over "
    "the past two weeks and I confirmed each one still holds; the other three I fixed today. The two that "
    "are still open needed a decision or a backend piece I don't have yet, and I've said exactly why "
    "instead of going quiet on them. Alongside that I did the other four things asked for today: a "
    "responsive pass at 860px and 540px, keyboard and focus states everywhere, and loading/transition "
    "polish that actually turns off for anyone with reduced motion set.", styles["Body"],
))

# ------------------------------------------------------------ Recap table ---
story.append(Paragraph("Every line from Aug 26", styles["H1"]))
rows = [
    ["Sev", "Finding", "Status", "Note"],
    ["Blocks", "Suggestion engine returns nothing for 2 of 6 warm-up stages, blames ‘connect’",
     "Closed Aug 31", "suggest.py now checks the comment path too, not just connect/message"],
    ["Blocks", "No way to see repeats across queued suggestions before approving",
     "Closed Aug 31", "Near-identical drafts across the queue are now detected and flagged"],
    ["Blocks", "‘Never contact’ fires with zero confirmation, beside routine buttons",
     "Closed Aug 31", "Two-tap confirm now sits between the tap and the permanent suppression"],
    ["Blocks", "‘Today’s activity’ shows a made-up schedule labeled as real",
     "Closed", "That panel is gone — Warm-up shows the real health/funnel data instead"],
    ["Blocks", "Agents page renders blank — data loads, the page never shows it",
     "Closed today", "Found the real cause: the entrance animation re-ran on every 3-second poll and "
     "could get caught mid-teardown with the page stuck at opacity 0. It now plays once per visit, not once "
     "per poll — confirmed live across four poll cycles with nothing going invisible"],
    ["Slows", "Connecting an account means opening DevTools and copying raw cookies",
     "Still open", "Needs a real LinkedIn login flow, which is a product/API decision, not a page I can "
     "fix from the frontend — flagged for Hemang, not silently dropped"],
    ["Slows", "No screen shows the people actually imported for a target profile",
     "Still open", "Needs a backend endpoint that counts/lists imported people per profile; nothing to "
     "wire the frontend to yet"],
    ["Looks bad", "Agents and Campaigns are a different app behind the same menu bar",
     "Closed today", "Re-themed both to the same dark/purple tokens as the rest of the app, and added "
     "Campaigns to the menu — it was a real page with no way in before today"],
    ["Looks bad", "Phone menu loses its labels and the account name disappears",
     "Closed today", "Labels never hide now; the menu scrolls sideways with a fade hint instead. The "
     "account name gets first claim on its row so the mode label can't crowd it out anymore"],
]
data = [[Paragraph(rows[0][i], styles["CellHead"]) for i in range(4)]]
for r in rows[1:]:
    done = "Still open" not in r[2]
    data.append([Paragraph(r[0], styles["Cell"]), Paragraph(r[1], styles["Cell"]), status_tag(r[2], done), Paragraph(r[3], styles["Cell"])])
t = grid(data, [0.55 * inch, 1.9 * inch, 0.75 * inch, 2.7 * inch])
story.append(t)
story.append(Spacer(1, 6))
story.append(Paragraph(
    "Seven closed, two open with a named reason. That's the whole list — nothing from Aug 26 is unaccounted for.",
    styles["Small"],
))

# ------------------------------------------------------------- Screenshots ---
story.append(PageBreak())
story.append(Paragraph("What closing the two look-bad items actually looks like", styles["H1"]))
story.append(Paragraph(
    "Agents used to be a white, generic-blue page reached from the menu; Campaigns was the same look and "
    "wasn't in the menu at all. Both are the same dark/purple product now, and both are one tap away.",
    styles["Body"],
))
row1 = Table([[img_flowable("agents_540.png", max_width=2.55 * inch, max_height=2.9 * inch),
               img_flowable("campaigns_540.png", max_width=2.55 * inch, max_height=2.9 * inch)]],
             colWidths=[3.1 * inch, 3.1 * inch])
row1.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
story.append(row1)
story.append(Paragraph("Agents (left) and Campaigns (right) at 540px, re-themed and reachable from the menu.", styles["Caption"]))

story.append(Spacer(1, 8))
story.append(Paragraph(
    "The phone menu at 540px: every label stays on screen instead of dropping to icons, and a fade on both "
    "edges hints there's more to scroll to — Accounts, Campaigns, Agents and Account are one swipe away, "
    "not hidden with no clue they exist.",
    styles["Body"],
))
row2 = Table([[img_flowable("dashboard_540.png", max_width=2.55 * inch, max_height=2.9 * inch),
               img_flowable("dashboard_540_scrolled.png", max_width=2.55 * inch, max_height=2.9 * inch)]],
             colWidths=[3.1 * inch, 3.1 * inch])
row2.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
story.append(row2)
story.append(Paragraph("Same nav, scrolled from the start (left) to the end (right) — nothing is unreachable.", styles["Caption"]))

story.append(Paragraph("The account name fix, stress-tested", styles["H1"]))
story.append(Paragraph(
    "The bug: with a long account name, the name used to lose a flexbox fight with the ‘outreach’ "
    "mode label and shrink to nothing, leaving just a dot and the word ‘outreach’ — no way to tell "
    "which account. I tested the fix in isolation with a deliberately long name at 360px, narrower than "
    "either width in today's brief:", styles["Body"],
))
story.append(img_flowable("qa_accountcard.png", max_width=2.8 * inch, max_height=2.2 * inch))
story.append(Paragraph("The full name wraps to a second line and stays completely visible; the mode label drops below instead of crowding it out.", styles["Caption"]))

story.append(Spacer(1, 8))
story.append(Paragraph("The Agents page bug, confirmed fixed live", styles["H1"]))
story.append(Paragraph(
    "I left the page open through four 3-second poll cycles — well past the window the old bug needed to "
    "strike — and screenshotted it. Everything is still visible; nothing went invisible.",
    styles["Body"],
))
story.append(img_flowable("agents_after_polls.png", max_width=4.6 * inch, max_height=2.5 * inch))
story.append(Paragraph("Agents page, ~10 seconds after load, after several data polls.", styles["Caption"]))

story.append(Spacer(1, 8))
story.append(Paragraph("Keyboard focus, tabbed to with a real keyboard", styles["H1"]))
story.append(img_flowable("focus_tab2.png", max_width=2.6 * inch, max_height=2.1 * inch))
story.append(Paragraph("Two real Tab presses land here — the purple ring is the same global focus style every interactive element in the app now gets.", styles["Caption"]))

# ------------------------------------------------------------- Other work ---
story.append(PageBreak())
story.append(Paragraph("What I added on top of the audit", styles["H1"]))
story.append(Paragraph(
    "<b>Responsive pass at 860px and 540px.</b> Checked every page in the menu at both widths, plus the "
    "Campaigns wizard's four steps. There are no data tables in this app to wrap — the equivalent (stat "
    "grids, action cards, the priority picker) all collapse to fewer columns instead of squeezing three "
    "across at 540px. Touch targets on the primary actions (Approve, Skip, Never contact, its confirm/"
    "cancel pair, the queue tabs, the nav) are now a minimum 44px tall on phone widths and shrink back to "
    "their compact desktop size at 640px and up — verified by measuring the rendered buttons, not just "
    "reading the CSS.", styles["Body"],
))
story.append(Paragraph(
    "<b>Keyboard and focus states everywhere.</b> The purple focus ring was already global; I went "
    "through every onClick in the app looking for one that wasn't a real button, link, or input. Found "
    "one — the Campaign card was a clickable div with no keyboard path in — and gave it role=\"button\", "
    "tabIndex, and an Enter/Space handler. Everything else was already a real interactive element.", styles["Body"],
))
story.append(Paragraph(
    "<b>Loading and transition polish, reduced motion respected.</b> Added MotionConfig with "
    "reducedMotion=\"user\" at the app root, which is Framer Motion's own supported way to make every "
    "whileHover/whileTap/entrance animation in the app snap straight to its end state when the OS says "
    "reduce motion — not play shorter, just not play. That covers every page. It doesn't reach the two "
    "pages that animate with GSAP directly (Agents, Campaigns), so those check "
    "prefers-reduced-motion by hand and skip their entrance/pulse animations outright. A global CSS rule "
    "backs both up for plain CSS transitions and turns off smooth-scroll. Loading spinners were left "
    "alone on purpose — they're status, not decoration, and a frozen spinner reads as broken.", styles["Body"],
))

story.append(Spacer(1, 12))
story.append(HRFlowable(width="100%", thickness=0.5, color=LINE_C))
story.append(Spacer(1, 6))
story.append(Paragraph(
    "Method: ran the real app on my own machine (Vite dev server + a local SQLite backend with the dev "
    "auth bypass, not mocked), clicked through every page at both widths, tabbed through with a real "
    "keyboard, and left the Agents page open across multiple live data polls to confirm the fix actually "
    "holds over time rather than just on first paint. Two items — the DevTools login and the imported-"
    "people list — need backend work or a product call I don't have today; everything else on the Aug 26 "
    "list is closed.", styles["Small"],
))

doc = SimpleDocTemplate(
    OUT_PATH, pagesize=LETTER,
    leftMargin=0.7 * inch, rightMargin=0.7 * inch,
    topMargin=0.65 * inch, bottomMargin=0.65 * inch,
    title="Week 1 UI Audit — Closed — Dyuthi T G",
)
doc.build(story)
print(f"wrote {OUT_PATH}")
