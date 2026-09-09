# Demo narration — Week 2 walkthrough

**Video:** `Week2_Demo_Walkthrough.webm` · **Length:** 2:19 · **Re-record with:**
`python scripts/record_walkthrough.py`

The video has these words burned in as captions. They're written as what an
operator is *thinking*, not what the buttons do — nobody needs to be told that
a button labelled Approve approves something. If you'd rather have voice than
captions, read these over the top. Timings are to the nearest few seconds —
they were taken off the recording, not planned in advance.

Everything on screen is real: the comments were written by the model during
`scripts/staging_run.py`, replying to posts the system went and found itself.

---

**0:00 — the queue**

> Four comments the bot wrote this morning, against four posts it went and found
> on its own. **None of them are on LinkedIn.** Nothing is, until I say so.

**0:12 — what I read first**

> I don't read the comment first. I read the line under it — **the thing they
> actually posted**. If I can't tell what this is replying to, that's already my
> answer.

**0:24 — the flags**

> The labels are the machine admitting what it already knows. Marcus Bell's is
> carrying **Generic phrase, Formula question**. I haven't read a word of it yet
> and I know where to look.

**0:41 — how I actually work**

> Grouped by what's wrong instead of by best match. If the same rule failed four
> times, **that's one decision, not four** — I'd rather make it once than meet it
> four times in date order.

**0:53 — the one I won't send**

> Here it is up close. It opens by agreeing with her, then asks the question
> every one of these wants to ask. **It reads fine on its own** — which is
> exactly how 43 of 58 of them got past us in August.

**1:05 — why it needs a reason**

> Skipping makes me type why. Not to make me feel bad — **the reasons are the
> training data** for the next version of the prompt. A silent reject teaches the
> system nothing.

**1:17 — the one I will send**

> Priya Sharma's is clean — no labels at all, and it names the specific thing she
> wrote about rather than the topic in general. **That's the whole test: would I
> be happy to have sent this under my own name?**

**1:41 — the five seconds**

> Approving hands it to the pacer, which picks a send time that doesn't look like
> a machine's. And there's five seconds to take it back — **not a confirm box**,
> because those get clicked through without reading.

**1:54 — all the way through**

> And here's this morning's, which went the whole way: found, written, flagged,
> read by a human, paced, and sent — **a real HTTP request built by the real
> transport**, logged with what it contained.

**2:07 — what isn't real yet**

> The honest part: that request went to a local stand-in for LinkedIn's API, not
> to linkedin.com. **Nothing in this system has ever run against a live LinkedIn
> session.** That's the top of next week's list, not a footnote.

---

## Notes for whoever presents this

- **Lead with the last caption, not the first.** Volunteering the boundary buys
  more credibility than the demo does, and it stops someone finding it for you
  three minutes in.
- **The names change between recordings.** The script reads the live queue and
  picks a genuinely flagged item to skip and a genuinely clean one to approve,
  then names them in the captions. It does that because the first take narrated
  "this one earns it" over an approval of a comment that was carrying a Generic
  phrase flag — the script had clicked whatever was on top. If you re-record, the
  captions follow the data.
- **The video is `.webm`.** The ffmpeg that ships with Playwright is a cut-down
  build with no mp4 muxer at all, so there's no mp4 unless a full ffmpeg gets
  installed on the machine. It plays in any browser and in VLC.
- **If you get asked "is this a mock?"** — the answer is no, and the receipt is
  `staging_run/voyager_requests.jsonl`: every LinkedIn call the run made, with
  the comment body that was posted, credentials redacted.
