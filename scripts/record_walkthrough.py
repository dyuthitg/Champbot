"""
Record the end-to-end walkthrough against the staging run.

Drives the real UI over the real API over the staging-run database — the same
comments the loop generated in ``scripts/staging_run.py``, replying to the same
scraped posts. Nothing on screen is a mock.

The captions are written against the queue as it actually is: the script reads
the queue from the API first and picks a genuinely flagged item to skip and a
genuinely clean one to approve, then names them. The first take of this video
narrated "this one earns it" over an approval of a comment carrying a Generic
phrase flag, because the script clicked whatever was on top. A demo whose
voiceover disagrees with its own screen is worse than no demo.

Narration is burned in as captions rather than voice; the words and timings
live in docs/DEMO_NARRATION.md for a human to read over the top.

Needs the API on :8010 and the SPA on :3000, both pointed at
staging_run/staging.db.

    python scripts/record_walkthrough.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VIDEO_DIR = REPO / "staging_run" / "video"
FINAL_WEBM = REPO / "Week2_Demo_Walkthrough.webm"
FINAL_MP4 = REPO / "Week2_Demo_Walkthrough.mp4"

API = "http://127.0.0.1:8010/api/v1"
APP = "http://localhost:3000"
WIDTH, HEIGHT = 1440, 900

CAPTION_CSS = """
/* Top, not bottom, and click-through. The reject-reason prompt and the undo
   toast are both anchored to the bottom of the viewport, so a caption bar
   down there covered the controls and then swallowed the clicks aimed at
   them -- the first take failed on "<div id=demo-caption> intercepts pointer
   events". */
#demo-caption {
  position: fixed; left: 0; right: 0; top: 0; z-index: 99999;
  pointer-events: none;
  background: rgba(11,15,25,0.96); border-bottom: 2px solid #a855f7;
  color: #e2e8f0; font: 500 21px/1.5 system-ui, -apple-system, sans-serif;
  padding: 16px 40px 18px;
  box-shadow: 0 12px 40px rgba(0,0,0,0.6);
}
body { padding-top: 104px; }
#demo-caption b { color: #f59e0b; font-weight: 600; }
#demo-caption .tag {
  display: block; font-size: 12px; letter-spacing: .14em; text-transform: uppercase;
  color: #94a3b8; margin-bottom: 6px;
}
"""

CAPTION_JS = """
(payload) => {
  let el = document.getElementById('demo-caption');
  if (!el) {
    const style = document.createElement('style');
    style.textContent = payload.css;
    document.head.appendChild(style);
    el = document.createElement('div');
    el.id = 'demo-caption';
    document.body.appendChild(el);
  }
  el.innerHTML = '<span class="tag">' + payload.tag + '</span>' + payload.text;
}
"""


def beat(page, tag: str, text: str, seconds: float) -> None:
    page.evaluate(CAPTION_JS, {"css": CAPTION_CSS, "tag": tag, "text": text})
    page.wait_for_timeout(int(seconds * 1000))


def read_queue() -> list:
    with urllib.request.urlopen(f"{API}/outreach/suggestions?status=pending&limit=25") as r:
        return json.loads(r.read())["suggestions"]


def pick(queue: list):
    """One item with a real problem, one with none. Either may be missing."""
    flagged = next((s for s in queue if s.get("quality_flags")), None)
    clean = next((s for s in queue if not s.get("quality_flags")), None)
    return flagged, clean


def open_row(page, name: str) -> bool:
    row = page.locator(f"button:has-text('{name}')").first
    if not row.count():
        return False
    row.click()
    page.wait_for_timeout(1500)
    return True


def main() -> int:
    from playwright.sync_api import sync_playwright

    queue = read_queue()
    if not queue:
        print("the staging queue is empty; run scripts/staging_run.py first")
        return 1
    flagged, clean = pick(queue)
    print(f"queue: {len(queue)} pending")
    print(f"  flagged pick: {flagged and flagged['target']['full_name']}")
    print(f"  clean pick:   {clean and clean['target']['full_name']}")

    if VIDEO_DIR.exists():
        shutil.rmtree(VIDEO_DIR)
    VIDEO_DIR.mkdir(parents=True)

    started = time.time()
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        context = browser.new_context(
            viewport={"width": WIDTH, "height": HEIGHT},
            record_video_dir=str(VIDEO_DIR),
            record_video_size={"width": WIDTH, "height": HEIGHT},
        )
        page = context.new_page()
        page.goto(f"{APP}/approvals")
        page.wait_for_selector("text=Approvals", timeout=20000)
        page.wait_for_timeout(2200)

        beat(
            page, "the queue",
            f"{len(queue)} comments the bot wrote this morning, against {len(queue)} posts it went "
            "and found on its own. <b>None of them are on LinkedIn.</b> Nothing is, until I say so.",
            10,
        )

        beat(
            page, "what I read first",
            "I don't read the comment first. I read the line under it — <b>the thing they actually "
            "posted</b>. If I can't tell what this is replying to, that's already my answer.",
            10,
        )

        if flagged:
            labels = ", ".join(f["label"] for f in flagged["quality_flags"])
            beat(
                page, "the flags",
                f"The labels are the machine admitting what it already knows. {flagged['target']['full_name']}'s "
                f"is carrying <b>{labels}</b>. I haven't read a word of it yet and I know where to look.",
                10,
            )

        # ------------------------------------------------ batch by failure
        try:
            page.get_by_role("button", name="Failure type").click()
            page.wait_for_timeout(1200)
            beat(
                page, "how I actually work",
                "Grouped by what's wrong instead of by best match. If the same rule failed four "
                "times, <b>that's one decision, not four</b> — I'd rather make it once than meet "
                "it four times in date order.",
                8,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"sort control not found: {exc}")

        # ------------------------------------------------ skip the bad one
        if flagged and open_row(page, flagged["target"]["full_name"]):
            beat(
                page, "the one I won't send",
                "Here it is up close. It opens by agreeing with her, then asks the question every "
                "one of these wants to ask. <b>It reads fine on its own</b> — which is exactly how "
                "43 of 58 of them got past us in August.",
                12,
            )
            skip = page.get_by_role("button", name="Skip").first
            if skip.count():
                skip.click()
                page.wait_for_timeout(1200)
                beat(
                    page, "why it needs a reason",
                    "Skipping makes me type why. Not to make me feel bad — <b>the reasons are the "
                    "training data</b> for the next version of the prompt. A silent reject teaches "
                    "the system nothing.",
                    10,
                )
                box = page.locator("input[placeholder='Reason, then Enter']")
                if box.count():
                    box.fill("Validation opener plus the formula question — same shape as August")
                    page.wait_for_timeout(1600)
                    box.press("Enter")
                    # Sit out the full undo window before going anywhere. The
                    # first take navigated away after 1.8s and the skip was
                    # silently discarded -- see BREAK_LIST.md #9. Waiting here
                    # is not padding; it is the bug being avoided on camera.
                    page.wait_for_timeout(6500)

        # ------------------------------------------------ approve the good one
        if clean:
            page.goto(f"{APP}/approvals")
            page.wait_for_selector("text=Approvals", timeout=20000)
            page.wait_for_timeout(1800)
            name = clean["target"]["full_name"]
            if open_row(page, name):
                beat(
                    page, "the one I will send",
                    f"{name}'s is clean — no labels at all, and it names the specific thing she "
                    "wrote about rather than the topic in general. <b>That's the whole test: would "
                    "I be happy to have sent this under my own name?</b>",
                    12,
                )
                approve = page.get_by_role("button", name="Approve & schedule").first
                if not approve.count():
                    approve = page.get_by_role("button", name="Approve edit & schedule").first
                if approve.count():
                    approve.click()
                    page.wait_for_timeout(2200)
                    beat(
                        page, "the five seconds",
                        "Approving hands it to the pacer, which picks a send time that doesn't look "
                        "like a machine's. And there's five seconds to take it back — <b>not a "
                        "confirm box</b>, because those get clicked through without reading.",
                        10,
                    )

        # ------------------------------------------------ the far end
        page.goto(f"{APP}/")
        page.wait_for_timeout(2400)
        beat(
            page, "all the way through",
            "And here's this morning's, which went the whole way: found, written, flagged, read by "
            "a human, paced, and sent — <b>a real HTTP request built by the real transport</b>, "
            "logged with what it contained.",
            11,
        )

        beat(
            page, "what isn't real yet",
            "The honest part: that request went to a local stand-in for LinkedIn's API, not to "
            "linkedin.com. <b>Nothing in this system has ever run against a live LinkedIn "
            "session.</b> That's the top of next week's list, not a footnote.",
            13,
        )

        page.wait_for_timeout(1000)
        context.close()
        browser.close()

    webm = sorted(VIDEO_DIR.glob("*.webm"))
    if not webm:
        print("no video was produced")
        return 1
    shutil.copyfile(webm[0], FINAL_WEBM)
    print(f"recorded {FINAL_WEBM}  ({time.time() - started:.0f}s of walkthrough)")

    if _to_mp4(FINAL_WEBM, FINAL_MP4):
        print(f"also wrote {FINAL_MP4}")
    else:
        print("no mp4 encoder available -- the .webm plays in any browser and in VLC")
    return 0


def _to_mp4(src: Path, dst: Path) -> bool:
    """
    Convert if a full ffmpeg is on the machine.

    Playwright ships its own ffmpeg, but it is a cut-down build with no mp4
    muxer at all -- it can read webm and nothing else. Checked, not assumed.
    """
    found = shutil.which("ffmpeg")
    if not found:
        return False
    try:
        subprocess.run(
            [found, "-y", "-i", str(src), "-c:v", "libx264", "-pix_fmt", "yuv420p",
             "-crf", "23", "-movflags", "+faststart", str(dst)],
            check=True, capture_output=True,
        )
        return True
    except Exception:  # noqa: BLE001
        return False


if __name__ == "__main__":
    raise SystemExit(main())
