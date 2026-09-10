# Attribution and sources

This project would not exist without other people's work, most of it volunteered.

## Required notice

> **This work uses trademarks and/or copyrights owned by Paizo Inc., used under
> Paizo's Community Use Policy ([paizo.com/communityuse](https://paizo.com/communityuse)).
> We are expressly prohibited from charging you to use or access this content.
> This work is not published, endorsed, or specifically approved by Paizo.
> For more information about Paizo Inc. and Paizo products, visit
> [paizo.com](https://paizo.com).**

Pathfinder and the Pathfinder logo are trademarks of Paizo Inc. Rules mechanics
are available under the [ORC License](https://paizo.com/licenses) and the Open
Game License v1.0a.

## Thanks

**[Archives of Nethys](https://2e.aonprd.com/)** — the entire rules corpus. A
free, complete, meticulously maintained reference that a volunteer team has kept
current through an edition remaster. Every answer this project gives is really
theirs; all it adds is a way to search them. Please
[support them](https://2e.aonprd.com/) and use the site directly.

**Pathfinder-Icons font** — the action symbols (one, two and three actions, free
action, reaction) are drawn with Paizo's icon font, © Paizo Inc. 2019, the same
file the Archives of Nethys serve. It is embedded in the web page so it renders
offline, under the Community Use Policy above.

**Erathian font** — the alphabet newly written text is shown in before it settles
is the Erathian script from the *Might and Magic* games, as the font by
[Tom Chen](https://github.com/might-and-magic/erathian-font), SIL Open Font License 1.1
(the remaining glyphs come from Alegreya, also OFL). The letter shapes themselves
belong to New World Computing, The 3DO Company and Ubisoft Entertainment; *Might and
Magic* is a registered trademark of Ubisoft Entertainment SA.

**[PathfinderWiki](https://pathfinderwiki.com/)** — 27,749 articles of Golarion
lore, written and curated by volunteers over more than a decade.

**[Paizo Inc.](https://paizo.com/)** — for the game, and for a Community Use
Policy generous enough that a project like this is allowed to exist at all.

**[RPG Stack Exchange](https://rpg.stackexchange.com/)** — the questions that
turned this from a demo into something measured. The realisation that a benchmark
written by its own author flatters itself came from comparing it against
questions real people asked there. Contributions are
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/); this repository
does not redistribute them, and `scripts/mine_wild_questions.py` records the
permalink of every question it uses.

**Open models** — [Qwen](https://github.com/QwenLM) (Alibaba) for Qwen3.5 and
Qwen3-Embedding under Apache 2.0, [Ollama](https://ollama.com/) for making local
serving unremarkable, and [llama.cpp](https://github.com/ggerganov/llama.cpp)
underneath it.

## How the corpus was collected

Stated plainly so anyone can judge it:

- **Archives of Nethys** — read from the anonymously-readable Elasticsearch index
  that backs the site's own search, once, 45,547 documents, paginated per
  category. There is no `robots.txt` on the site (404) and no published API
  terms. **This is the greyest thing here**: publicly reachable is not the same
  as authorised. It is a single non-commercial read of a public search index, but
  anyone building on this commercially, or at volume, should ask the Archives of
  Nethys team first.
- **PathfinderWiki** — the public MediaWiki API, rate-limited to four requests a
  second with an identifying User-Agent, 27,761 pages.
- **RPG Stack Exchange** — the public Stack Exchange API, well inside anonymous
  quota, 730 questions and 574 accepted answers.

Nothing was collected behind a login or a paywall, and no rate limit was evaded.

## What this project redistributes

- **The packaged index** ([release asset](https://github.com/DeastinY/pf2etune/releases))
  contains Archives of Nethys rules text — 41,743 entries, 48 MB. That is
  redistribution of Paizo Material under the Community Use Policy: non-commercial
  only, free to access, never behind a paywall, with the notice above. Every
  entry keeps its source URL.
- **Nothing else.** The corpus, the mined questions and the raw scrapes are all
  rebuilt from scripts and are not committed.
- **No model weights.** Three adapters were trained during this project and none
  shipped — see [`docs/LICENSING.md`](docs/LICENSING.md) for why publishing
  weights trained on Community Use content is a worse idea than it looks.
