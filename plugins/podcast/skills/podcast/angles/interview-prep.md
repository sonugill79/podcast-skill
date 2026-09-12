# Angle: interview-prep

**Use when** the listener is interviewing with a company (or about to start the process) for a specific role.
**Listener goal:** walk into the next conversation fluent in the company, the role, and the questions worth asking, and
clear about whether the role fits their criteria.

## Brief (ask only if missing)
- Company, and the role title if known. The posting URL is ideal.
- Stage (not yet applied / recruiter screen done / loop scheduled) and the date of the next conversation.
- `--personal`? If the listener opts in, the inbox and calendar can supply the role, recruiter, dates and title
  discrepancies. Otherwise ask.

## Research areas (one agent each)
| # | Area | Focus |
|---|---|---|
| 1 | Business & financials | Origin, mission, public/private status, latest quarter and full year (growth, profitability, **one-time items**), guidance, strategy pillars, leadership quotes on tech/AI with context |
| 2 | Product & customers | Product lines today, pricing, app-store/Trustpilot ratings **with counts and dates**, complaint themes (say sample size), launches in the last 12 months, fraud/trust issues |
| 3 | People, culture & interview process | Current leadership with dates, **values verbatim**, eng org and hubs, work policy, layoffs, Glassdoor/Blind (snippets, labelled), interview loop for this level, comp (posting band + levels.fyi) |
| 4 | Market, competition & regulation | Market size, competitors table, M&A, regulation and policy that becomes engineering/ops work, macro risks |
| 5 | The role itself | **Posting verbatim via `bin/rawfetch.py`**, the team's public stack/tooling, reporting line, industry context for the function, likely questions, strengths/gaps vs the listener |

`quick` depth merges 1+4 and folds 2 into 1, keeping 3 and 5 (3 agents).

## Segment outline (≈ share of runtime)
1. Cold open, who it's for and what they'll get (4%)
2. Where you are in the process: role, recruiter, title/level discrepancies (5%)
3. The company in three minutes, with the misleading number called out (9%)
4. Leadership and operating model, and why the leader's background matters to the listener (11%)
5. Product and customers (10%)
6. Market and regulation (7%)
7. The job itself: posting quotes, public stack, evidence for the function's hard problems (25%)
8. Your story in their language: values mapping, likely questions, a "why us, why now" sketch (15%)
9. Questions to ask, and things to weigh against the listener's criteria (location, comp, stability) (9%)
10. Wrap: three things to remember, what couldn't be verified, what to re-check before the next round (5%)

## Must verify yourself (never air from agent notes alone)
- Every quoted line of the posting, plus its salary band and work policy, via `rawfetch.py --grep`. Take the band from
  the **description text**: structured `baseSalary` fields are often ATS placeholders (one real posting's read "1-1,000,000").
- Leadership names, titles and **dates**; departures (8-K or equivalent).
- Headline financials and any one-time item inflating them; a recruiter's pitch numbers against the filing.
- Every executive quote **and what it was about** (a "massive opportunity" line may not refer to what the notes say).
- Values wording (small wording drift is common in agent notes).

## Don'ts
- Don't voice single anonymous posts (Blind/Glassdoor) as facts. Voice them as "one post claims… ask about it".
- Don't guess the internal tech stack. Say "not public" and turn it into a question.
- Don't say the listener's comp number out loud; say "your floor".
