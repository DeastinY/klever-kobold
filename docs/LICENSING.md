# Licensing

Not legal advice. This is the working understanding this project operates under.
The required attribution and the full source acknowledgements are in
[`NOTICE.md`](../NOTICE.md).

## The two bodies of text are licensed differently

**Rules mechanics** (Archives of Nethys) are published under the **ORC License** — the
system-neutral open license Paizo moved to in 2023, stewarded by Azora Law rather than owned by
Paizo. Rules expressions are reusable with attribution. AoN itself additionally operates under
Paizo's Community Use Policy.

**Setting lore** (Golarion, PathfinderWiki) is **Paizo IP under the Community Use Policy**.
PathfinderWiki's own API reports its rights as "Paizo's Community Use Policy". The CUP permits
non-commercial, freely available use: online references and tools, wikis, guides. It does not
permit commercial use, and it does not permit charging for access.

## What that means here

- **Personal, local use of a fine-tuned model: fine.** Nothing in Paizo's license pages addresses
  AI training either way, and non-commercial personal research on CUP content is squarely what the
  CUP contemplates.
- **Publishing model weights trained on CUP lore: genuinely grey.** The weights are a derivative of
  Paizo IP that cannot carry the CUP's attribution requirements in any meaningful way, and the CUP
  bars commercial use of the result. Do not publish lore-trained weights without thinking harder
  than this document does.
- **Publishing weights trained only on ORC rules text** is a better position, but ORC carries its
  own attribution and downstream-licensing obligations that a weight file does not naturally
  satisfy.
- **The benchmark is the safe artifact.** Questions and structured answers derived from ORC rules
  expressions, with a source URL on every item, are the most publishable thing in this repository.

## Paizo's stated position on AI

Paizo [banned AI-generated art and text](https://paizo.com/blog/paizo-and-artificial-intelligence)
in its own products and on the Pathfinder/Starfinder Infinite marketplaces in 2023, citing
unresolved ethical and legal questions around how models are trained. That policy governs Paizo's
publications and marketplaces, not a personal fine-tune — but it does predict how the community
would receive published weights.

## The grey area, named

The Archives of Nethys corpus was read from the Elasticsearch index that backs
the site's own search, which answers anonymous queries. The site publishes no
`robots.txt` (404) and no API terms, so nothing forbids it — but nothing permits
it either, and a publicly reachable backend is not a public API. One
non-commercial read of 45,547 documents is a small thing; a commercial product or
a recurring high-volume crawl is not, and either should start with an email to
the Archives of Nethys team.

RPG Stack Exchange content is CC BY-SA 4.0. This repository does not redistribute
it — the mined questions are gitignored and rebuilt by script — but anything that
did would owe attribution and share-alike.

## Practical rules this repo follows

1. No corpus data is committed. Everything is rebuilt from source by script.
2. Every chunk keeps `url` and source-book metadata, so attribution stays possible downstream.
3. Scrapers identify themselves and rate-limit (PathfinderWiki is volunteer-run).
4. Non-commercial research only.

## Sources

- [Paizo licenses](https://paizo.com/licenses)
- [Paizo Community Use Policy](https://paizo.com/community/communityuse)
- [Paizo and Artificial Intelligence](https://paizo.com/blog/paizo-and-artificial-intelligence)
- [PathfinderWiki copyrights](https://pathfinderwiki.com/wiki/PathfinderWiki:Copyrights)
