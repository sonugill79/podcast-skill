# Angle: product-research

**Use when** the listener is evaluating a product, tool, service or product category before buying, adopting,
integrating, or building a competitor to it.
**Listener goal:** know what it really does and costs, what real users love and hate, the alternatives (free/local
included), the trust and lock-in risks, and a clear verdict for their use case.

## Brief (ask only if missing)
- The product (or category), and the decision: buy / adopt at work / integrate into a project / build something similar.
- The use case and scale (e.g. "personal use", "a 50-engineer org", "a side project with ~1k users"). Pull from `listener.md` if obvious.

## Research areas (one agent each)
| # | Area | Focus |
|---|---|---|
| 1 | What it is & how it works | Features that exist today (docs, changelog) vs roadmap, architecture/how it works, **pricing tiers verbatim from the vendor page, dated**, usage limits, platforms, API/integrations |
| 2 | Real-world user experience | App store / G2 / Capterra / Trustpilot ratings **with counts and dates**, Reddit and HN threads, recurring complaints and praise (say sample size), support quality, status-page incident history |
| 3 | Alternatives & comparison | Direct competitors, **open-source and self-hosted equivalents**, preferred where genuinely comparable, a pricing comparison table at the listener's scale, migration paths between them |
| 4 | Trust, security & vendor health | Privacy policy and data retention/training use, security incidents and breaches, compliance certs (SOC 2, ISO 27001), licence terms for "open source" claims, vendor funding, layoffs, acquisition/shutdown risk |
| 5 | Fit for the listener | Integration with their stack, total cost at their scale, lock-in and exit cost, a decision rubric with 4–6 weighted criteria, what a two-week trial should test |

`quick` depth merges 1+3 and 4+5, and keeps 2 (3 agents).

## Segment outline (≈ share of runtime)
1. Cold open: the decision being made (4%)
2. What it is, in ninety seconds (10%)
3. Pricing and limits, verbatim and dated (12%)
4. What users love and what they hate (16%)
5. Alternatives, including free and local (16%)
6. Trust, security and vendor health (12%)
7. Fit for you: integration, cost at your scale, lock-in (14%)
8. Verdict: buy / try / skip, with the conditions that would flip it (11%)
9. Wrap: what to test in a trial, what couldn't be verified (5%)

## Must verify yourself
- Pricing and plan limits from the vendor's own page via `rawfetch.py --grep`, with the date.
- Feature claims against current docs (not marketing, not old reviews).
- Ratings with counts and dates.
- Security incidents (primary disclosure or reputable reporting) and certifications (the vendor's trust page).
- "Open source" claims: check the actual licence file.

## Don'ts
- Don't treat a competitor's comparison page as neutral. Label it.
- Don't recommend a paid tool when a local/free equivalent is genuinely comparable without saying why.
- Don't present roadmap features as available.
