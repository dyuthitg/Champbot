"""
Builds the 30-case golden set: real-shaped LinkedIn posts spanning the range
the bot will actually see, a hand-written "what a good human comment looks
like" target for each, and the structured fields (title/company/industry,
plus the automated scorer's hook words and tone-risk flag) needed to
actually run the real copywriter against every case and grade what comes
back -- see scripts/run_golden_set.py.

Every post/company/name below is invented for this exercise -- none are real
people or companies. That's deliberate: this file is meant to sit in the repo
and be scored against for as long as the copywriter exists, so it can't
depend on scraping anyone's actual posts (and we have no live LinkedIn access
to do that with anyway -- see docs/CONNECTING_AN_ACCOUNT.md).

Run: python scripts/build_golden_set.py
Writes: docs/golden_set/golden_set.csv
"""

import csv
import os

HERE = os.path.abspath(os.path.dirname(__file__))
OUT_DIR = os.path.join(HERE, "..", "docs", "golden_set")
OUT_CSV = os.path.join(OUT_DIR, "golden_set.csv")


# hooks: 1-2 distinctive words/phrases from THIS post that a comment has to
# reference to count as responding to the specific post rather than the
# general topic -- see run_golden_set.py's scorer and RUBRIC.md's "3" anchor.
# tone_risk: True marks a case where a normal congratulatory/excited register
# would be the wrong tone entirely (bridge round, sunset, relaunch, layoff).
# skip: True marks a case whose gold-standard action is no comment at all.
CASES = [
    # ---------------------------------------------------------------- funding
    dict(
        category="funding", full_name="Sana Patel", title="Founder & CEO", industry="SaaS",
        source_post=(
            "We closed our $4M seed round. This one's for the 11 people who joined "
            "when we were three people and a Figma file. More engineers, one "
            "designer, and finally a person whose whole job is talking to customers "
            "instead of me doing it at 11pm."
        ),
        ideal_comment=(
            "The part that'll actually matter in six months is someone owning customer "
            "conversations full-time instead of it being your 11pm job. What made you "
            "wait this long to hire for that?"
        ),
        notes="Standard good case. Specific detail (the 11pm line) is there to reward.",
        hooks=["11pm"], tone_risk=False, skip=False,
    ),
    dict(
        category="funding", full_name="Derek Osei", title="Co-founder", industry="Software",
        source_post=(
            "Announcing our Series A: $18M led by Northlight Ventures. We'll use it "
            "to expand from the UK into the US and double the eng team. Huge thanks "
            "to our early customers who let us build this in public with them."
        ),
        ideal_comment=(
            "UK to US is a different sales motion, not just more of the same one -- "
            "what's changing first, the pricing or the team you're hiring for it?"
        ),
        notes="Standard good case.",
        hooks=["uk to us", "sales motion"], tone_risk=False, skip=False,
    ),
    dict(
        category="funding", full_name="Marie Callaghan", title="CEO", industry="Healthtech",
        source_post=(
            "Proud to share our Series B, $32M, to keep building tools for "
            "independent clinics tracking patient outcomes. We started this because "
            "my mother's clinic was still doing this on paper in 2021."
        ),
        ideal_comment=(
            "Starting from your mother's clinic doing this on paper is a much better "
            "reason than most Series B posts give -- did the product change once you "
            "saw it used somewhere that wasn't a paper process to begin with?"
        ),
        notes="Standard good case; reward referencing the specific origin detail, not generic 'congrats'.",
        hooks=["mother", "paper"], tone_risk=False, skip=False,
    ),
    dict(
        category="funding", full_name="Tom Reyes", title="Founder", industry="SaaS",
        source_post=(
            "We're raising a bridge, not a victory-lap round. $2.5M to get to 18 "
            "months of runway while we fix retention. I'd rather say that plainly "
            "than dress it up as something else."
        ),
        ideal_comment=(
            "Saying 'bridge to fix retention' plainly instead of dressing it up is "
            "rarer than it should be. What's the retention number you're actually "
            "trying to move first?"
        ),
        notes=(
            "Reward the comment for matching the founder's own honest framing rather than congratulating a "
            "'win' that wasn't presented as one -- a generic 'congrats on the raise!' misreads the post's tone entirely."
        ),
        hooks=["bridge", "retention"], tone_risk=True, skip=False,
    ),
    dict(
        category="funding", full_name="Priya Nathan", title="Founder", industry="SaaS",
        source_post=(
            "We tried to raise for four months and couldn't close a round on terms "
            "we'd sign. So we're not raising. We cut costs, kept the team that "
            "matters, and we're profitable as of last month. Not the post I "
            "expected to write this year."
        ),
        ideal_comment=(
            "Getting to profitable after a raise falls through is a much harder "
            "story to tell than closing a round, and a much more useful one for "
            "anyone else reading this right now. What got cut first?"
        ),
        notes="A congratulatory or funding-cheerleading comment here is tone-deaf -- this is a story about "
              "resilience after failing to raise, not a funding win.",
        hooks=["profitable", "four months"], tone_risk=True, skip=False,
    ),
    # ---------------------------------------------------------------- hiring
    dict(
        category="hiring", full_name="Champions Ranch Careers", title="Careers", industry="SaaS",
        source_post=(
            "We're hiring 5 backend engineers and 2 product designers. Remote-first, "
            "async by default, no meetings before 11am. Link to the roles in the "
            "comments."
        ),
        ideal_comment=(
            "No meetings before 11am is doing a lot of the recruiting work in this "
            "post already -- is that a written policy or just how the team happens "
            "to work right now?"
        ),
        notes="Standard good case; the specific perk detail is the personalization hook, not the job link.",
        hooks=["11am"], tone_risk=False, skip=False,
    ),
    dict(
        category="hiring", full_name="Ade Okonkwo", title="VP of Growth", company="Brightline Analytics", industry="SaaS",
        source_post=(
            "I'm thrilled to share that I've joined Brightline Analytics as VP of "
            "Growth. After 6 years building the growth function at my last company, "
            "I'm excited for a new challenge with a team that's obsessed with "
            "activation the way I am."
        ),
        ideal_comment=(
            "Six years is long enough that whatever you built there has your "
            "fingerprints all over it -- what's the first thing you're rebuilding "
            "from scratch here versus carrying over?"
        ),
        notes="Standard good case.",
        hooks=["6 years", "fingerprints"], tone_risk=False, skip=False,
    ),
    dict(
        category="hiring", full_name="Lena Forsythe", title="Talent Partner", industry="Fintech",
        source_post=(
            "Urgent: we need a senior SRE who's dealt with a payments system at "
            "scale. This is a real fire, not a 'nice to have' req. DM me if that's "
            "you or you know someone."
        ),
        ideal_comment=(
            "'Real fire, not a nice-to-have' is an unusually honest way to post a "
            "req -- is this a growth problem or an incident that's still ongoing?"
        ),
        notes="Standard good case.",
        hooks=["fire"], tone_risk=False, skip=False,
    ),
    dict(
        category="hiring", full_name="Marcus Webb", title="Head of Sales", industry="SaaS",
        source_post=(
            "Promoting Jade Lin from SDR to Account Executive after 14 months of "
            "her being the most disciplined person on the team about updating the "
            "CRM. That discipline is exactly why she's getting her own book now."
        ),
        ideal_comment=(
            "Getting promoted because you kept the CRM clean is a funny and "
            "completely believable reason -- did that discipline come from somewhere "
            "before this job, or did the job teach her that?"
        ),
        notes="Standard good case; reward comments engaging with the specific 'why', not generic promotion congrats.",
        hooks=["crm"], tone_risk=False, skip=False,
    ),
    dict(
        category="hiring", full_name="Northfield Systems", title="Company page", industry="Software",
        source_post=(
            "We laid off 40 people in March. We're now hiring 6 engineers for a new "
            "team. We know how that looks. Several of the roles are open to anyone "
            "we let go in March who wants to come back."
        ),
        ideal_comment=(
            "Naming that it looks bad, in the post itself, is the only reason this "
            "doesn't read as tone-deaf -- are the open-to-rehire roles the same "
            "roles that were cut, or genuinely new ones?"
        ),
        notes="The tension (layoffs then hiring months later) is the point of this case -- a comment that ignores "
              "it and just says 'great, hiring!' misses what the post is actually about.",
        hooks=["march"], tone_risk=True, skip=False,
    ),
    # ------------------------------------------------------- thought leadership
    dict(
        category="thought_leadership", full_name="Jonah Iverson", title="VP Growth", industry="SaaS",
        source_post=(
            "Everyone measures activation on day 1 or day 7. We started measuring "
            "day 30 retention of people who activated versus people who didn't, and "
            "the day-1 number stopped meaning anything to us. Activation that "
            "doesn't survive a month isn't activation."
        ),
        ideal_comment=(
            "Watching the day-1 number stop mattering once you had a day-30 lens on "
            "it is the kind of thing that only shows up after you've already made "
            "the mistake once -- what did you do with the metric you dropped?"
        ),
        notes="Standard good case; the bot should engage with the specific claim, not restate it back generically.",
        hooks=["day 30", "day-1"], tone_risk=False, skip=False,
    ),
    dict(
        category="thought_leadership", full_name="Camille Beaumont", title="Head of Demand Gen", industry="SaaS",
        source_post=(
            "MQLs are a vanity metric dressed up as a pipeline metric. I'd rather "
            "report zero MQLs and 12 real conversations than 400 MQLs and 2 "
            "conversations, and I've started saying that in board meetings."
        ),
        ideal_comment=(
            "Saying that in a board meeting is the harder version of this opinion -- "
            "did the room agree with you, or did you have to fight for the "
            "12-conversations number to count as a real result?"
        ),
        notes="Contrarian/opinion post; reward a comment that pushes back or asks about the harder real-world "
              "consequence (the board reaction), not one that just agrees.",
        hooks=["board"], tone_risk=False, skip=False,
    ),
    dict(
        category="thought_leadership", full_name="Rafael Ochoa", title="Founder", industry="SaaS",
        source_post=(
            "Three years in, the biggest lesson is that most churn isn't a product "
            "problem, it's a week-two problem. Nobody builds a reason to come back "
            "on day nine, and then everyone is surprised at the day-ninety number."
        ),
        ideal_comment=(
            "Week-two and day-ninety are pretty far apart to connect like that -- "
            "what's the thing you actually built to give someone a reason to come "
            "back on day nine?"
        ),
        notes="Standard good case.",
        hooks=["day nine", "day-ninety"], tone_risk=False, skip=False,
    ),
    dict(
        category="thought_leadership", full_name="Dana Whitfield", title="Data Lead", industry="SaaS",
        source_post=(
            "We pulled 40,000 onboarding sessions and the single biggest predictor "
            "of week-4 retention wasn't feature usage, it was whether the user "
            "invited a teammate in the first 48 hours. Nothing else came close."
        ),
        ideal_comment=(
            "Nothing else coming close is a stronger claim than most 'we found a "
            "correlation' posts make -- did you test whether prompting the invite "
            "actually caused the retention, or just noticed the two moved together?"
        ),
        notes="Data-driven post; reward a comment that questions correlation vs. causation specifically, "
              "since that's the real gap in the claim as stated.",
        hooks=["48 hours"], tone_risk=False, skip=False,
    ),
    dict(
        category="thought_leadership", full_name="Idris Bello", title="Founder", industry="SaaS",
        source_post=(
            "Unpopular opinion: most 'customer obsessed' companies have never once "
            "changed a roadmap decision because of a customer call. They just "
            "relabeled the roadmap meeting. I include companies I've worked at in "
            "this."
        ),
        ideal_comment=(
            "Including your own past companies in the criticism is what keeps this "
            "from being a cheap shot at everyone else -- what's the roadmap decision "
            "you personally didn't change when you probably should have?"
        ),
        notes="Polarizing/contrarian post; reward engaging with the self-implicating detail specifically, "
              "since that's what makes the claim credible rather than generic griping.",
        hooks=["roadmap"], tone_risk=False, skip=False,
    ),
    # ---------------------------------------------------------- product launch
    dict(
        category="product_launch", full_name="Sophie Marchetti", title="Head of Product", industry="SaaS",
        source_post=(
            "Launching bulk actions in the review queue today. If you've ever had "
            "200 items sitting in a queue and clicked 'approve' 200 times, this is "
            "for you. Small feature, but it's the one we got asked for the most."
        ),
        ideal_comment=(
            "200 individual clicks is a very specific number to have watched someone "
            "actually do -- was there a real customer session where you saw that "
            "happen, or is that the support-ticket number?"
        ),
        notes="Standard good case; the specificity is the '200 clicks' detail.",
        hooks=["200"], tone_risk=False, skip=False,
    ),
    dict(
        category="product_launch", full_name="Elliot Vance", title="Founder", industry="SaaS",
        source_post=(
            "Public beta is open. No waitlist, no invite code, just a link. We spent "
            "8 months on this and the honest answer is it's still rough in a couple "
            "of places -- the export flow especially. Tell us where it breaks."
        ),
        ideal_comment=(
            "Naming the export flow as the rough spot before anyone else finds it is "
            "the right instinct -- is that a data-format problem or a "
            "how-long-it-takes problem?"
        ),
        notes="Standard good case; reward engaging with the named weak spot, not a generic 'exciting, congrats!'.",
        hooks=["export"], tone_risk=False, skip=False,
    ),
    dict(
        category="product_launch", full_name="Grace Odutayo", title="CEO", industry="SaaS",
        source_post=(
            "We rebuilt the whole onboarding flow and relaunched it this week under "
            "a new name after the last one quietly failed to land for a year. Not "
            "proud of year one. Proud of this."
        ),
        ideal_comment=(
            "'Not proud of year one, proud of this' is an unusually blunt way to "
            "frame a relaunch -- what told you the first version had actually "
            "failed, versus just being slow to take off?"
        ),
        notes="Relaunch-after-failure framing; reward a comment that acknowledges the honest framing "
              "rather than treating it as a normal, upbeat launch post.",
        hooks=["year one"], tone_risk=True, skip=False,
    ),
    dict(
        category="product_launch", full_name="Priya Sharma", title="Growth Lead", company="BrightMetrics", industry="SaaS",
        source_post=(
            "We cut our signup form from nine fields to two. Conversion went up 40% "
            "and, to my surprise, lead quality didn't move at all. The extra seven "
            "fields were buying us nothing but a slower funnel."
        ),
        ideal_comment=(
            "Lead quality not moving at all is the part most teams would be too "
            "nervous to test -- did you have to convince anyone internally that the "
            "extra fields weren't doing real qualification work?"
        ),
        notes="Standard good case (real product data point from the existing fixtures, reused for continuity).",
        hooks=["nine fields", "lead quality"], tone_risk=False, skip=False,
    ),
    dict(
        category="product_launch", full_name="Owen Castellano", title="Founder", industry="SaaS",
        source_post=(
            "We're sunsetting our original AI-summary feature next month. It was "
            "our first launch, it never got the adoption we hoped, and keeping it "
            "half-maintained was worse than admitting that and shutting it down."
        ),
        ideal_comment=(
            "Killing your own first launch is a harder post to write than shipping a "
            "new one -- was the low adoption visible early, or did it take a while "
            "to admit it wasn't going to turn around?"
        ),
        notes="Sunset/failure-admission post; reward engaging honestly with the shutdown, not congratulating "
              "it like a normal launch.",
        hooks=["adoption", "sunsetting"], tone_risk=True, skip=False,
    ),
    # ------------------------------------------------------- personal milestone
    dict(
        category="personal_milestone", full_name="Renata Silva", title="Senior Engineer", industry="Software",
        source_post=(
            "Five years at Fernbank today. I've shipped things I'm proud of and a "
            "couple I quietly hope nobody looks at too closely. Grateful for both "
            "kinds of years."
        ),
        ideal_comment=(
            "Admitting there are a couple you hope nobody looks at too closely is "
            "the honest version of a work-anniversary post -- is there one of those "
            "you'd actually go back and rebuild if you had the time now?"
        ),
        notes="Standard good case; the specific hook is the 'don't look too closely' admission.",
        hooks=["too closely"], tone_risk=False, skip=False,
    ),
    dict(
        category="personal_milestone", full_name="Jamal Osei", title="Director of Engineering", industry="Software",
        source_post=(
            "Promoted to Director of Engineering. Six months ago I wasn't sure I "
            "wanted to keep managing people at all. Glad I stuck with it, and glad "
            "the team told me when I was doing it badly."
        ),
        ideal_comment=(
            "Six months from unsure-you-wanted-this to Director is a fast turn -- "
            "what actually changed, the job or how you were doing it?"
        ),
        notes="Standard good case; reward the specific detail (team telling him when he was doing it badly), "
              "not a generic 'congrats on the promotion!'.",
        hooks=["six months"], tone_risk=False, skip=False,
    ),
    dict(
        category="personal_milestone", full_name="Fatima Al-Rashid", title="Data Scientist", industry="SaaS",
        source_post=(
            "Finished my part-time master's in data science last night, three years "
            "after starting it while working full-time. My kids stayed up to watch "
            "the ceremony on my laptop at 11pm their time."
        ),
        ideal_comment=(
            "Three years part-time while working full-time is the actual achievement "
            "here, the ceremony is just the last five minutes of it -- what almost "
            "made you quit partway through?"
        ),
        notes="Standard good case.",
        hooks=["three years", "kids"], tone_risk=False, skip=False,
    ),
    dict(
        category="personal_milestone", full_name="Nadia Kowalski", title="Product Manager", industry="SaaS",
        source_post=(
            "Back at work today after 7 months of parental leave. First meeting "
            "back, I forgot the name of a tool we use every day. Reintroducing "
            "myself to my own job, slowly."
        ),
        ideal_comment=(
            "Forgetting the tool name on day one is a much more honest re-entry "
            "story than 'excited to be back!' -- is it the tools that feel "
            "different, or the team itself?"
        ),
        notes="Standard good case; reward engaging with the specific, slightly vulnerable detail.",
        hooks=["forgot", "tool"], tone_risk=False, skip=False,
    ),
    dict(
        category="personal_milestone", full_name="Ben Okafor", title="Engineer", industry="Software",
        source_post=(
            "Ran my first marathon yesterday. 4:42, which is nowhere near fast, but "
            "a year ago I couldn't run for a bus. Posting this here because half "
            "the people who kept me accountable were people from work."
        ),
        ideal_comment=(
            "Work people being the accountability group is the actual reason this "
            "belongs on LinkedIn instead of feeling out of place here -- did anyone "
            "from work show up to watch?"
        ),
        notes="Standard good case; non-work milestone but explicitly tied back to work relationships in the post.",
        hooks=["bus", "accountable"], tone_risk=False, skip=False,
    ),
    # -------------------------------------------------------------------- layoffs
    dict(
        category="layoff", full_name="Victor Hammond", title="CEO", industry="SaaS",
        source_post=(
            "Today we let go of 30 people, about 18% of the company. This is on "
            "me: I hired ahead of revenue that didn't show up on the timeline I "
            "expected. If you're hiring for growth, marketing, or ops roles, the "
            "people affected are excellent and I'll gladly make an introduction."
        ),
        ideal_comment=(
            "Naming it as your own hiring-ahead-of-revenue call, not 'market "
            "conditions,' is the part worth responding to directly. Happy to keep an "
            "eye out on our side for the growth and ops folks."
        ),
        notes="Reward taking real ownership and offering something concrete (keeping an eye out), not a "
              "generic 'sorry to hear this' or, worse, a pitch. No question needed here -- an ask feels wrong.",
        hooks=["ahead of revenue", "introduction"], tone_risk=True, skip=False,
    ),
    dict(
        category="layoff", full_name="Isabel Tran", title="Product Marketer", industry="SaaS",
        source_post=(
            "I was laid off on Tuesday along with 40 other people. 6 years as a "
            "product marketer, most recently running launches end to end. Open to "
            "work, open to relocating, not open to pretending this doesn't sting."
        ),
        ideal_comment=(
            "6 years running launches end to end is a real, specific thing to be "
            "looking for next, not just a title -- if it's useful, happy to pass "
            "your name to a couple of people I know hiring for exactly that."
        ),
        notes="Reward a concrete, low-effort offer of help over a sympathetic-but-empty comment. Still no "
              "'what strategies are you using in your job search' question -- that reads as content-farming her situation.",
        hooks=["end to end", "6 years"], tone_risk=True, skip=False,
    ),
    dict(
        category="layoff", full_name="Northfield Systems", title="Company page", industry="Software",
        source_post=(
            "As part of our commitment to sustainable growth, we are optimizing our "
            "workforce to align with strategic priorities. We thank affected team "
            "members for their contributions to our journey."
        ),
        ideal_comment="",
        notes="SKIP -- gold-standard action is no comment. This is the hardest case in the set on purpose: "
              "generating anything here, even something well-written, is the wrong output. A rubric that gives "
              "this a high score for fluent, on-topic corporate-speak has a real blind spot.",
        hooks=[], tone_risk=True, skip=True,
    ),
    # ---------------------------------------------------------------- condolences
    dict(
        category="condolence", full_name="Priyanka Desai", title="Co-founder", industry="SaaS",
        source_post=(
            "Our co-founder Ravi passed away on Sunday after a short illness. He "
            "wrote the first line of code this company ever shipped. I don't have "
            "anything more polished to say than that we miss him."
        ),
        ideal_comment="",
        notes="SKIP -- gold-standard action is no comment. This is a genuine bereavement post; the account "
              "should not be commenting here at all, regardless of how well-written the comment is.",
        hooks=[], tone_risk=True, skip=True,
    ),
    dict(
        category="condolence", full_name="Marcus Webb", title="Head of Sales", industry="SaaS",
        source_post=(
            "Stepping back from work for a couple of weeks. My father passed away "
            "on Friday. I'll be slow to respond to messages. Thank you for "
            "understanding."
        ),
        ideal_comment="",
        notes="SKIP -- gold-standard action is no comment, and also no invitation/message of any kind while "
              "this person has explicitly said they're stepping back. This is the single clearest case in the "
              "set of 'the bot should recognize this and do nothing.'",
        hooks=[], tone_risk=True, skip=True,
    ),
]


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    rows = []
    for i, case in enumerate(CASES, start=1):
        rows.append(
            {
                "id": f"G{i:02d}",
                "category": case["category"],
                "full_name": case["full_name"],
                "title": case.get("title", ""),
                "company": case.get("company", ""),
                "industry": case.get("industry", ""),
                "source_post": case["source_post"],
                "ideal_comment": case["ideal_comment"],
                "notes": case["notes"],
                "hooks": "|".join(case.get("hooks", [])),
                "tone_risk": "1" if case.get("tone_risk") else "0",
                "skip": "1" if case.get("skip") else "0",
            }
        )

    fieldnames = [
        "id", "category", "full_name", "title", "company", "industry",
        "source_post", "ideal_comment", "notes", "hooks", "tone_risk", "skip",
    ]
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    by_category = {}
    for r in rows:
        by_category[r["category"]] = by_category.get(r["category"], 0) + 1

    print(f"Wrote {len(rows)} cases -> {OUT_CSV}")
    for cat, n in by_category.items():
        print(f"  {cat}: {n}")
    print(f"  skip cases: {sum(1 for r in rows if r['skip'] == '1')}")


if __name__ == "__main__":
    main()
