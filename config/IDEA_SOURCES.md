# Weekly Idea Sources

When Dean asks for ideas this week, the agent should run:

```bash
python scripts/fetch_ideas.py --sources-only
```

This creates `pipeline/ideas/YYYY-MM-DD-source-report.md` so Dean can see what
was checked before any AI ranking happens.

## Live Sources

- NHL.com official news.
- Canucks official news.
- Sportsnet NHL.
- TSN NHL.
- ESPN NHL.
- Google News sweeps for Canucks, NHL trades, and NHL injuries.
- Reddit hot/new from `r/hockey`, `r/canucks`, and `r/nhl`.
- Official YouTube uploads from NHL, Sportsnet, TSN, ESPN, Canucks, and NHL on
  ESPN.
- Competitor uploads from The Hockey Guy, Graviteh, Eck, Canucks Conversation,
  Sekeres and Price, and Locked On Canucks.
- Public NHL API schedule context for Canadian-market teams.

## What The Agent Should Look For

- breaking injuries, controversial hits, suspensions, and fights,
- playoff series swings and officiating controversies,
- Canucks front-office moves, rumours, and local fan sentiment,
- trade rumours and draft rankings when people are actively searching,
- upcoming games that can be previewed before demand peaks,
- competitor uploads that prove a topic is already moving.

The goal is speed: catch the topic while people are starting to search, then
write Dean's angle before the market is saturated.
