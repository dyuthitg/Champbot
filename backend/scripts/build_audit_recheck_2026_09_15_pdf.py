"""
Generates Week1_Audit_Rechecked_Sep15.pdf -- reopening the Aug 26 Operator UI
Audit again, two weeks after I first closed it, to make sure it's still
closed and to finish the four things asked for today: a responsive pass at
860/540px, keyboard and focus states everywhere, every look-bad item ticked
off with a reason where it isn't fixed, and loading/transition polish that
respects prefers-reduced-motion.

Screenshots are real, taken against the running app on 2026-09-15 (dev
server + a local SQLite backend, dev auth token, a real test account and a
real test campaign created through the actual API) -- not mockups.

Run: python scripts/build_audit_recheck_2026_09_15_pdf.py
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

IMG_DIR = r"C:\Users\Dyudhi T G\AppData\Local\Temp\claude\C--Users-Dyudhi-T-G-Desktop-champion-champbot-Social-Bot-LinkedIn-\c64d56d5-4e75-4b7d-bf22-470a681c6e65\scratchpad\imgs"
OUT_PATH = "Week1_Audit_Rechecked_Sep15.pdf"

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
styles.add(ParagraphStyle(name="Found", fontSize=10.5, leading=15.5, spaceAfter=6, backColor=colors.HexColor("#eae1f2")))

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
story.append(Paragraph("Week 1 UI Audit — Reopened Again, Still Closed", styles["TitleBig"]))
story.append(Paragraph(
    "Dyuthi T G &nbsp;&bull;&nbsp; 2026-09-15 &nbsp;&bull;&nbsp; checking the Aug 26 audit is still closed, two weeks later",
    styles["SubTitle"],
))
story.append(Spacer(1, 6))
story.append(HRFlowable(width="100%", thickness=1, color=LINE_C))
story.append(Spacer(1, 10))
story.append(Paragraph(
    "I closed this list once already on Sep 14. Today I opened it again on purpose, because a lot of real "
    "code has landed since then — a whole new Campaign Detail page, the campaign wizard now picks a real "
    "account, and the nav itself got renamed and then simplified. Closing something once doesn't mean it "
    "stays closed while the app keeps moving, so I re-checked every line against the app as it runs right "
    "now, not against my notes from last time. All seven closed items still hold. The two still open are "
    "still open, for the same reason as before. And while re-checking the new Campaign Detail page for "
    "keyboard access, I found a real bug — not on Aug 26's list, because the page didn't exist yet — and "
    "fixed it.", styles["Body"],
))

# ------------------------------------------------------------ Recap table ---
story.append(Paragraph("Every line from Aug 26, checked again", styles["H1"]))
rows = [
    ["Sev", "Finding", "Status", "Note"],
    ["Blocks", "Suggestion engine returns nothing for 2 of 6 warm-up stages, blames ‘connect’",
     "Still closed", "Checked live again today, unchanged since Aug 31"],
    ["Blocks", "No way to see repeats across queued suggestions before approving",
     "Still closed", "Checked live again today, unchanged since Aug 31"],
    ["Blocks", "‘Never contact’ fires with zero confirmation, beside routine buttons",
     "Still closed", "Checked live again today, unchanged since Aug 31"],
    ["Blocks", "‘Today’s activity’ shows a made-up schedule labeled as real",
     "Still closed", "That panel is still gone; Warm-up still shows the real numbers"],
    ["Blocks", "Agents page renders blank — data loads, the page never shows it",
     "Still closed", "Left the page open across a live poll cycle again today with the new sub-tab nav "
     "sitting in front of it — nothing went invisible. Confirmed the fix survives the nav being rebuilt "
     "around it, not just the original page"],
    ["Slows", "Connecting an account means opening DevTools and copying raw cookies",
     "Still open", "Same reason as Sep 14: needs a real LinkedIn login flow, a product/API decision, not a "
     "frontend fix. Flagged for Hemang, not silently dropped"],
    ["Slows", "No screen shows the people actually imported for a target profile",
     "Still open", "Same reason as Sep 14: needs a backend endpoint that counts/lists imported people. "
     "Nothing new to wire the frontend to yet"],
    ["Looks bad", "Agents and Campaigns are a different app behind the same menu bar",
     "Still closed", "Both still share the one dark/purple look; Campaigns is still one tap away"],
    ["Looks bad", "Phone menu loses its labels and the account name disappears",
     "Still closed", "Labels still never hide, even now that the nav has fewer, longer tab names than it "
     "did on Sep 14 — checked that specifically, since longer labels were the more likely way for this to "
     "quietly break again"],
]
data = [[Paragraph(rows[0][i], styles["CellHead"]) for i in range(4)]]
for r in rows[1:]:
    done = "Still open" not in r[2]
    data.append([Paragraph(r[0], styles["Cell"]), Paragraph(r[1], styles["Cell"]), status_tag(r[2], done), Paragraph(r[3], styles["Cell"])])
t = grid(data, [0.55 * inch, 1.9 * inch, 0.75 * inch, 2.7 * inch])
story.append(t)
story.append(Spacer(1, 6))
story.append(Paragraph(
    "Same seven closed, same two open, same two reasons. Nothing on this list quietly broke while the app "
    "changed underneath it.", styles["Small"],
))

# ------------------------------------------------------------ New finding ---
story.append(Spacer(1, 14))
story.append(Paragraph(
    "<b>A NEW KEYBOARD BUG, FOUND WHILE CHECKING THE NEW CAMPAIGN DETAIL PAGE</b><br/><br/>"
    "The Campaign Detail page didn't exist on Aug 26, so it was never on the original list — but today's "
    "brief says keyboard states everywhere, so I tabbed through it with a real keyboard anyway. The "
    "Start/Pause campaign button took <b>two</b> Tab presses to reach, not one: the first landed on an "
    "invisible, empty stop with a focus ring around nothing, and only the second reached the real button. "
    "Same thing on the \u201cSocial Bot\u201d logo in the corner of every page. Root cause: wrapping a "
    "button in a plain animated box (to make it scale slightly on tap) makes that box its own keyboard stop, "
    "on every single page that does it, sitting right in front of the actual button.", styles["Found"],
))
story.append(Paragraph(
    "Fixed two ways depending on what the animated box was wrapping: the logo box wraps plain text with no "
    "action of its own, so it's told not to take keyboard focus (the link around it already does). The "
    "Start/Pause button box wraps a real button with a real action, so instead I made the animation apply "
    "straight to the button itself, and deleted the extra wrapping box entirely — one element, one stop, "
    "one ring. Checked the rest of the app for the same pattern: everywhere else that taps-to-scale, the "
    "animated element already is the button, not a box around one, so this was the only place it happened.",
    styles["Body"],
))
story.append(img_flowable("focus_startcampaign.png", max_width=5.2 * inch, max_height=3.6 * inch))
story.append(Paragraph(
    "One real Tab press from \u201cBack to Campaigns\u201d lands here now — on the actual button, not an empty box in front of it.",
    styles["Caption"],
))

# ------------------------------------------------------------- Screenshots ---
story.append(PageBreak())
story.append(Paragraph("The responsive pass, including everything new since Sep 14", styles["H1"]))
story.append(Paragraph(
    "Checked at 860px and 540px again, plus the new Campaign Detail page and the wizard's account-picking "
    "step, neither of which existed for the last pass. The overview page still fits the whole top nav's "
    "worth of buttons at 860px and still scrolls sideways with a fade hint at 540px, exactly like Sep 14 — "
    "the mechanism that fixed the original phone-nav finding still works, it just has different labels on "
    "it now.", styles["Body"],
))
row1 = Table([[img_flowable("dashboard_860.png", max_width=3.1 * inch, max_height=2.6 * inch),
               img_flowable("dashboard_540.png", max_width=3.1 * inch, max_height=2.6 * inch)]],
             colWidths=[3.2 * inch, 3.2 * inch])
row1.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
story.append(row1)
story.append(Paragraph("Overview at 860px (left) and 540px (right) — same account, same real data, both widths.", styles["Caption"]))

story.append(Spacer(1, 10))
story.append(Paragraph(
    "The new Campaign Detail page, checked with a real campaign I created through the actual API — and then "
    "with a deliberately very long campaign name, the same kind of stress test that caught real wrapping "
    "bugs in earlier passes:", styles["Body"],
))
row2 = Table([[img_flowable("campaigndetail_860.png", max_width=3.1 * inch, max_height=3.6 * inch),
               img_flowable("campaigndetail_longname_540.png", max_width=3.1 * inch, max_height=3.6 * inch)]],
             colWidths=[3.2 * inch, 3.2 * inch])
row2.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
story.append(row2)
story.append(Paragraph(
    "860px with a normal name (left). 540px with a name almost 90 characters long (right) — it truncates "
    "with an ellipsis, the badge and button drop to their own lines, and nothing overlaps or breaks.",
    styles["Caption"],
))

story.append(PageBreak())
story.append(Paragraph("The nav got simpler today, and I checked it holds up", styles["H1"]))
story.append(Paragraph(
    "Partway through today's check the top nav changed — eight tabs became five, with Targeting and "
    "Campaigns folded into one tab, and Accounts, Warm-up and Agents folded into another, each with its own "
    "row of sub-tabs underneath. That wasn't something I did; it's a real, in-progress improvement to the "
    "same phone-nav crowding this audit has been tracking since Aug 26, and it's a good direction — fewer "
    "top-level tabs is exactly what a narrow screen needs. I made sure it actually works rather than just "
    "trusting it: it type-checks clean, every merged page routes correctly, and the sub-tab strips get the "
    "same 44px touch targets and the same never-hide-the-label rule as the top nav.", styles["Body"],
))
row3 = Table([[img_flowable("newnav_540.png", max_width=2.5 * inch, max_height=3.3 * inch),
               img_flowable("accountsandagents_540.png", max_width=2.5 * inch, max_height=3.3 * inch),
               img_flowable("wizard_step1_540.png", max_width=2.5 * inch, max_height=3.3 * inch)]],
             colWidths=[2.15 * inch, 2.15 * inch, 2.15 * inch])
row3.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
story.append(row3)
story.append(Paragraph(
    "The five-tab nav at 540px (left) — still fully labeled, still scrolls to reach the last one. LinkedIn "
    "Accounts, Warm-up and Agents sharing one tab with a sub-tab strip underneath (middle). The campaign "
    "wizard's real account picker, added Sep 14, still clean at 540px (right).",
    styles["Caption"],
))

# ------------------------------------------------------------- Other work ---
story.append(PageBreak())
story.append(Paragraph("The other two things asked for today", styles["H1"]))
story.append(Paragraph(
    "<b>Loading and transition polish, reduced motion respected.</b> This was already in place app-wide as "
    "of Sep 14 (MotionConfig at the root, plus the two GSAP pages checking prefers-reduced-motion by hand). "
    "I didn't need to add anything new — I needed to prove it still holds now that there's more to it. I "
    "left the Agents page open through a live poll cycle again, this time reached through the new sub-tab "
    "nav instead of a direct link, and nothing went invisible. The new Campaign Detail page was built "
    "Sep 14 already following the same pattern (its own prefersReducedMotion check gating the Start/Pause "
    "button's animation) — I checked it does the same thing everywhere else in the app, not something that "
    "quietly only half-applies to new pages.", styles["Body"],
))
story.append(Paragraph(
    "<b>Keyboard and focus states everywhere.</b> Covered above — the one real gap was the two phantom tab "
    "stops, both now fixed and verified with real Tab presses, not just read from the code. Every other "
    "interactive element I checked today (the wizard's account checkboxes, the sub-tab strips, the "
    "Verify/disconnect icon buttons on the Accounts page) already had a working keyboard path and a visible "
    "focus ring, so nothing else needed changing.", styles["Body"],
))

story.append(Spacer(1, 12))
story.append(HRFlowable(width="100%", thickness=0.5, color=LINE_C))
story.append(Spacer(1, 6))
story.append(Paragraph(
    "Method: ran the real app on my own machine (Vite dev server + a local SQLite backend with the dev auth "
    "bypass, not mocked), created a real test account and a real test campaign through the actual API — not "
    "hand-written fixtures — clicked through every page at both widths, tabbed through with a real keyboard, "
    "and left pages open across live data polls to check nothing breaks over time. The two items still open "
    "from Aug 26 need backend work or a product call I still don't have; everything else, including "
    "everything built since Sep 14, is checked and holding.", styles["Small"],
))

doc = SimpleDocTemplate(
    OUT_PATH, pagesize=LETTER,
    leftMargin=0.7 * inch, rightMargin=0.7 * inch,
    topMargin=0.65 * inch, bottomMargin=0.65 * inch,
    title="Week 1 UI Audit — Reopened Again, Still Closed — Dyuthi T G",
)
doc.build(story)
print(f"wrote {OUT_PATH}")
