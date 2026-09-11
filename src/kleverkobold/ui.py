"""The single page served by ``kobold serve``.

One string, no build step, no CDN. The runtime keeps its four dependencies and
the page has to work on a laptop with no network -- which is the whole point of
an offline rules reference -- so the markdown renderer, the action glyphs and
the stat-block styling are all done here rather than pulled from a library.

The visual language is Paizo's own stat block, because that is the shape the
corpus is already in: ``# Name [Two Actions] (Feat 1)``, a ``**Traits**`` line,
labelled fields, a rule, then the body with its four degrees of success. Parsing
that back into a stat block is mostly a matter of not throwing the structure
away, which the previous plain-text rendering did.
"""

from __future__ import annotations

import base64
import importlib.resources

# Paizo's action-icon font, the one the Archives of Nethys draws its action
# symbols with, embedded so the page needs no network for it. Used under the
# Community Use Policy; see NOTICE.md. Glyphs: U+E902 one action, U+E901 two,
# U+E900 three, U+E903 free action, U+E904 reaction.
_FONT = base64.b64encode(
    importlib.resources.files(__package__).joinpath("Pathfinder-Icons.ttf").read_bytes()
).decode()

# The Erathian alphabet from Might and Magic, as a font by Tom Chen (SIL OFL;
# see NOTICE.md). Latin letters typeset in it come out as Erathian glyphs, so
# freshly streamed text can be shown "untranslated" and then settle into the
# page's own face, one character at a time.
_ERATHIAN = base64.b64encode(
    importlib.resources.files(__package__).joinpath("Erathian-min.woff2").read_bytes()
).decode()

_PAGE = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>The Klever Kobold</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='7' fill='#8a1b2e'/%3E%3Cpolygon points='16,1.6 7.6,11.9 24.4,11.9' fill='#fff' opacity='0.42'/%3E%3Cpolygon points='3.4,8.8 16,1.6 7.6,11.9' fill='#fff' opacity='0.28'/%3E%3Cpolygon points='16,1.6 28.6,8.8 24.4,11.9' fill='#fff' opacity='0.34'/%3E%3Cpolygon points='3.4,8.8 7.6,11.9 3.4,23.2' fill='#fff' opacity='0.2'/%3E%3Cpolygon points='28.6,8.8 28.6,23.2 24.4,11.9' fill='#fff' opacity='0.26'/%3E%3Cpolygon points='3.4,23.2 7.6,11.9 16,26.4' fill='#fff' opacity='0.16'/%3E%3Cpolygon points='24.4,11.9 28.6,23.2 16,26.4' fill='#fff' opacity='0.22'/%3E%3Cpolygon points='3.4,23.2 16,26.4 16,30.4' fill='#fff' opacity='0.12'/%3E%3Cpolygon points='16,26.4 28.6,23.2 16,30.4' fill='#fff' opacity='0.18'/%3E%3Cpolygon points='7.6,11.9 24.4,11.9 16,26.4' fill='#fff' opacity='0.07'/%3E%3Cpolygon points='16,1.6 28.6,8.8 28.6,23.2 16,30.4 3.4,23.2 3.4,8.8' fill='none' stroke='#fff' stroke-width='1.5' stroke-linejoin='round'/%3E%3Cpath d='M16,1.6 L7.6,11.9 M16,1.6 L24.4,11.9 M7.6,11.9 L24.4,11.9 M7.6,11.9 L16,26.4 M24.4,11.9 L16,26.4 M3.4,8.8 L7.6,11.9 M28.6,8.8 L24.4,11.9 M3.4,23.2 L7.6,11.9 M28.6,23.2 L24.4,11.9 M3.4,23.2 L16,26.4 M28.6,23.2 L16,26.4 M16,30.4 L16,26.4' fill='none' stroke='#fff' stroke-width='1.1' stroke-linejoin='round' stroke-linecap='round'/%3E%3C/svg%3E">
<style>
@font-face{font-family:"Erathian";src:url(data:font/woff2;base64,__ERATHIAN__) format("woff2");font-display:block}
@font-face{font-family:"Pathfinder-Icons";src:url(data:font/ttf;base64,__ICON_FONT__) format("truetype");font-display:block}
/* Light is the base palette; the two blocks after it redefine only the tokens,
   so an un-stamped document (the default "system" setting) still resolves. */
:root{color-scheme:light;
--bg:#f7f4f1;--card:#fffdfb;--ink:#1c1719;--soft:#4a4341;--muted:#7b716d;
--line:#e0d8d2;--rule:#cdc2ba;--accent:#8a1b2e;--accent-ink:#fff;
--warn:#8a5a12;--ok:#2f6b4f;--fail:#a3421f;--crit-fail:#9c1f1f;--chip:#efe9e4;
--warn-bg:#fbf3e2;--warn-line:#e3cd9a;--code:#f3efeb}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){color-scheme:dark;
--bg:#141113;--card:#1d191b;--ink:#ece7e5;--soft:#c6bebb;--muted:#988d89;
--line:#332c2e;--rule:#3f3639;--accent:#e0788a;--accent-ink:#1a1113;
--warn:#d8a557;--ok:#74b894;--fail:#dd8f6b;--crit-fail:#e0736f;--chip:#282124;
--warn-bg:#2b2115;--warn-line:#54401f;--code:#221d1f}}
:root[data-theme=dark]{color-scheme:dark;
--bg:#141113;--card:#1d191b;--ink:#ece7e5;--soft:#c6bebb;--muted:#988d89;
--line:#332c2e;--rule:#3f3639;--accent:#e0788a;--accent-ink:#1a1113;
--warn:#d8a557;--ok:#74b894;--fail:#dd8f6b;--crit-fail:#e0736f;--chip:#282124;
--warn-bg:#2b2115;--warn-line:#54401f;--code:#221d1f}

*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
 font:15px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:58rem;margin:0 auto;padding:1.25rem 1rem 4rem}
header{display:flex;align-items:baseline;gap:.6rem;margin-bottom:.75rem}
#home-link{display:flex;align-items:baseline;gap:.6rem;color:inherit;text-decoration:none;
 border-radius:8px;padding:.15rem .4rem .15rem .2rem;margin-left:-.2rem}
#home-link:hover{background:var(--chip)}
#home-link:hover .d20{transform:rotate(-12deg)}
#home-link .d20{transition:transform .2s}
h1{font-size:1.05rem;margin:0;font-weight:600;
 font-family:ui-serif,Georgia,"Iowan Old Style",serif}
h1 small{color:var(--muted);font-weight:400;font-family:inherit}
#theme,#gear{padding:.35rem .65rem;font-size:.8rem;border:1px solid var(--line);
 background:var(--card);color:var(--soft);border-radius:6px;cursor:pointer;
 display:flex;align-items:center;gap:.35rem}
#gear{margin-left:auto}
#theme svg,#gear svg{width:.85rem;height:.85rem;fill:currentColor}
#gear[aria-expanded=true]{border-color:var(--accent);color:var(--accent)}
form{display:flex;gap:.5rem;position:sticky;top:0;background:var(--bg);
 padding:.5rem 0 .75rem;z-index:2}
input{flex:1;padding:.7rem .85rem;font-size:1rem;border:1px solid var(--line);
 background:var(--card);color:var(--ink);border-radius:6px}
input:focus{outline:2px solid var(--accent);outline-offset:1px}
button{padding:.7rem 1rem;font-size:.92rem;border:1px solid var(--line);background:var(--card);
 color:var(--ink);border-radius:6px;cursor:pointer}
button.primary{background:var(--accent);border-color:var(--accent);color:var(--accent-ink)}
button[disabled],input[disabled]{opacity:.55;cursor:progress}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.hint{color:var(--muted);font-size:.82rem;margin:0 0 .5rem}
#status{display:flex;align-items:center;gap:.5rem;font-size:.85rem;color:var(--muted);
 border:1px solid var(--line);background:var(--card);border-radius:8px;padding:.55rem .8rem;
 margin:0 0 .75rem}
#status.ready{color:var(--ok)}#status.bad{color:var(--accent)}
#status[hidden]{display:none}
.dot{width:.5rem;height:.5rem;border-radius:50%;background:currentColor;flex:none}
.dot.pulse{animation:p 1.1s ease-in-out infinite}
@keyframes p{0%,100%{opacity:.25}50%{opacity:1}}

/* ---- settings ----
   Closed by default and rendered below the search box, so opening it never
   moves the thing people came here to type in. */
#settings{background:var(--card);border:1px solid var(--line);border-radius:8px;
 padding:.85rem 1rem;margin:0 0 .9rem}
#settings[hidden]{display:none}
.set-h{font-size:.72rem;letter-spacing:.09em;text-transform:uppercase;color:var(--muted);
 margin:1.1rem 0 .5rem;border-top:1px solid var(--line);padding-top:.8rem}
.set-h:first-child{margin-top:0;border-top:0;padding-top:0}
.presets{display:flex;gap:.5rem;flex-wrap:wrap}
.preset{flex:1;min-width:16rem;display:flex;flex-direction:column;align-items:flex-start;
 gap:.1rem;padding:.55rem .7rem;text-align:left;line-height:1.35}
.preset b{font-family:ui-serif,Georgia,"Iowan Old Style",serif;font-size:.95rem;font-weight:600}
.preset span{font-size:.75rem;color:var(--muted);font-variant-numeric:tabular-nums}
.preset.on{border-color:var(--accent);background:var(--chip)}
.preset.on b{color:var(--accent)}
.grid{display:grid;grid-template-columns:auto 1fr;gap:.5rem .7rem;align-items:center}
.grid label{font-size:.82rem;color:var(--soft);white-space:nowrap}
#settings input,#settings select{padding:.4rem .5rem;font-size:.85rem;flex:none;width:100%;
 border:1px solid var(--line);background:var(--bg);color:var(--ink);border-radius:5px}
#settings input[type=checkbox]{width:auto}
#settings input[type=number]{width:6.5rem}
.pair{display:flex;gap:.5rem;align-items:center;flex-wrap:wrap}
#settings .pair input{flex:1;width:auto;min-width:9rem}
.pair button{padding:.4rem .7rem;font-size:.82rem;white-space:nowrap}
.nums{display:flex;gap:1.1rem;flex-wrap:wrap;align-items:center}
.nums span{display:flex;gap:.4rem;align-items:center;font-size:.82rem;color:var(--soft)}
.note{font-size:.78rem;color:var(--muted);margin:.45rem 0 0;grid-column:1/-1}
.warnbox{grid-column:1/-1;display:flex;gap:.45rem;font-size:.78rem;color:var(--warn);
 background:var(--warn-bg);border:1px solid var(--warn-line);border-radius:6px;
 padding:.45rem .6rem;margin:.5rem 0 0}
/* An author `display` beats the user agent's [hidden] rule, so say it again. */
.warnbox[hidden]{display:none}
#tstat{font-size:.8rem;margin:.55rem 0 0;white-space:pre-wrap}
#tstat.ok{color:var(--ok)}#tstat.bad{color:var(--accent)}#tstat.wait{color:var(--muted)}
.snip{background:var(--code);border:1px solid var(--line);border-radius:6px;
 padding:.6rem .7rem;margin:.4rem 0 0;overflow-x:auto;font-size:.76rem;
 font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;color:var(--soft)}
.tools{font-size:.78rem;color:var(--muted);margin:.5rem 0 0}
.tools code{background:var(--chip);border-radius:3px;padding:.05rem .3rem;color:var(--accent)}
footer.thanks{margin:3rem 0 0;padding-top:1rem;border-top:1px solid var(--line);font-size:.8rem;
 color:var(--muted);line-height:1.6}
footer.thanks a{color:var(--accent)}
footer.thanks .sep{margin:0 .4rem}

/* ---- stat block ---- */
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;
 padding:.85rem 1rem;margin:.6rem 0}
.head{display:flex;align-items:baseline;gap:.5rem;flex-wrap:wrap;
 border-bottom:2px solid var(--accent);padding-bottom:.35rem;margin-bottom:.5rem}
.name{font-family:ui-serif,Georgia,"Iowan Old Style",serif;font-size:1.06rem;
 font-weight:600;margin:0;letter-spacing:.01em}
.name a{color:var(--ink);text-decoration:none}
.name a:hover{text-decoration:underline;text-decoration-color:var(--accent)}
.rank{margin-left:auto;font-family:ui-serif,Georgia,serif;font-size:.9rem;
 color:var(--soft);white-space:nowrap;font-variant-numeric:tabular-nums}
.acts{display:inline-flex;align-items:center;font-family:"Pathfinder-Icons",serif;
 font-size:1.05em;line-height:1;color:var(--ink);white-space:nowrap;vertical-align:-.05em}
.acts .dash{font-family:inherit;opacity:.5;padding:0 .08em}
.acts.txt{font-family:inherit;font-size:.72rem;color:var(--muted)}
.traits{display:flex;flex-wrap:wrap;gap:.25rem;margin:0 0 .5rem}
.trait{font-size:.68rem;letter-spacing:.06em;text-transform:uppercase;font-weight:600;
 padding:.14rem .42rem;border-radius:2px;background:#5d0000;color:#fff;border:1px solid #3d0000}
.trait.uncommon{background:#c45500;border-color:#8c3c00}
.trait.rare{background:#0c1466;border-color:#080d40}
.trait.unique{background:#800080;border-color:#560056}
.trait.size,.trait.align{background:#3b7a57;border-color:#2a5a3f}
.field{font-weight:700;color:var(--ink)}
.body{font-size:.9rem;color:var(--soft)}
.body p{margin:.4rem 0}
.body hr{border:0;border-top:1px solid var(--rule);margin:.6rem 0}
.body ul{margin:.35rem 0;padding-left:1.1rem}
.body li.sub{margin-left:1.1rem;list-style:circle}
.body li.sub{margin-left:1.1rem;list-style:circle;color:var(--muted)}
.body a{color:var(--accent)}
/* The Archives underline their cross-references; keep that habit so a linked
   term reads as one. */
:root{--link:#1a3f8f}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){--link:#8fb0ff}}
:root[data-theme=dark]{--link:#8fb0ff}
.body a.lnk{color:var(--link);text-decoration:underline;text-decoration-thickness:1px;
 text-underline-offset:.12em}
.body a.lnk:hover{color:var(--accent)}
.answer .body a.ent{color:var(--accent);text-decoration-color:color-mix(in srgb,var(--accent) 45%,transparent);
 font-weight:600}
.star{background:none;border:0;padding:0 .1rem;cursor:pointer;font-size:1.05rem;line-height:1;
 color:var(--muted);flex:none;align-self:center}
.star:hover,.star.on{color:#d19a1a}
.tile .star{position:absolute;top:.35rem;right:.5rem}
.pop .star{position:absolute;top:.75rem;right:3rem;font-size:1.25rem}
#favs[hidden]{display:none}
.body .clip{max-height:16rem;overflow:auto}
.tw{overflow-x:auto;margin:.45rem 0}
.body table{border-collapse:collapse;font-size:.85rem;min-width:50%}
.body th,.body td{border:1px solid var(--line);padding:.25rem .55rem;text-align:left;
 white-space:nowrap;font-variant-numeric:tabular-nums}
.body th{background:var(--chip);font-weight:600}
.body tr:nth-child(even) td{background:color-mix(in srgb,var(--chip) 45%,transparent)}
.body .src{font-size:.8rem;color:var(--muted);margin:.25rem 0 .45rem}
.body .src .field{font-size:.68rem;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.body .src .pg{margin-left:.2rem}
.body .src .ed{margin-left:.45rem;font-size:.66rem;border:1px solid var(--line);border-radius:3px;
 padding:0 .3rem;vertical-align:.1em}
.dc{font-weight:700;color:var(--accent);white-space:nowrap}
.dice{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:.92em;
 background:var(--chip);border-radius:3px;padding:0 .3em 0 .2em;white-space:nowrap;
 display:inline-flex;align-items:center;gap:.18em}
.dice .die{width:.95em;height:.95em;color:var(--accent);flex:none}
.deg{display:block;margin-top:.3rem}
.deg .field{color:var(--ok)}
.deg.f .field{color:var(--fail)}
.deg.cf .field{color:var(--crit-fail)}

/* ---- tiles ----
   Colour says what a thing *is* before the name is read: the stripe and badge
   follow the entry's kind, the border follows its rarity in the Archives'
   own colours (uncommon orange, rare blue, unique purple). */
:root{--k-spell:#5b3fa6;--k-feat:#2f6b4f;--k-action:#8a1b2e;--k-skill:#0e6e75;
 --k-rules:#5a4d44;--k-item:#9a6a12;--k-creature:#3d5a1e;--k-condition:#b3541e;
 --k-class:#2c4a8a;--k-other:#6b6560;--k-lore:#8f4a6b}
:root[data-theme=dark],:root:not([data-theme=light]){}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){--k-spell:#a68cf0;--k-feat:#74b894;
 --k-action:#e0788a;--k-skill:#5fc3cb;--k-rules:#b8a99c;--k-item:#e0b45a;--k-creature:#9ccf6a;
 --k-condition:#f0965a;--k-class:#86a5ec;--k-other:#a39c96;--k-lore:#d98cb0}}
:root[data-theme=dark]{--k-spell:#a68cf0;--k-feat:#74b894;--k-action:#e0788a;--k-skill:#5fc3cb;
 --k-rules:#b8a99c;--k-item:#e0b45a;--k-creature:#9ccf6a;--k-condition:#f0965a;--k-class:#86a5ec;
 --k-other:#a39c96;--k-lore:#d98cb0}
.tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(15.5rem,1fr));gap:.6rem;
 margin:.4rem 0}
.tile{--k:var(--k-other);position:relative;background:var(--card);border:1px solid var(--line);
 border-top:3px solid var(--k);border-radius:8px;padding:.6rem .75rem .65rem;cursor:pointer;
 transition:transform .12s,box-shadow .12s,border-color .12s;display:flex;flex-direction:column}
.tile:hover{transform:translateY(-1px);box-shadow:0 6px 18px rgba(0,0,0,.10);border-color:var(--k)}
.tile:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.tile.uncommon{border-color:#c45500;border-top-color:var(--k)}
.tile.rare{border-color:#0c1466;border-top-color:var(--k)}
.tile.unique{border-color:#800080;border-top-color:var(--k)}
.tile .kind{display:flex;align-items:center;gap:.3rem;font-size:.66rem;letter-spacing:.07em;
 text-transform:uppercase;font-weight:700;color:var(--k);margin-bottom:.25rem;padding-right:1.6rem}
.tile .kind svg{width:.9rem;height:.9rem;fill:currentColor}
.tile .kind .lvl{margin-left:auto;font-weight:600;letter-spacing:0;text-transform:none;
 color:var(--muted);font-size:.72rem;font-variant-numeric:tabular-nums}
.tile .thead{display:flex;gap:.45rem;align-items:baseline}
.tile .tname{font-family:ui-serif,Georgia,"Iowan Old Style",serif;font-weight:600;
 font-size:.98rem;flex:1;min-width:0}
.tile .acts{font-size:1.15em;margin-left:auto}
.tile .traits{margin:.3rem 0 .1rem}
.tile .trait{font-size:.6rem;padding:.1rem .35rem}
.was{margin:.05rem 0 0;font-size:.76rem;color:var(--muted);font-style:italic}
.pop .was{margin:-.3rem 0 .5rem}
.snip-t{margin:.3rem 0 0;font-size:.82rem;color:var(--soft);line-height:1.4}
.secs{margin:.25rem 0 0;font-size:.76rem;color:var(--muted)}
.secs a{color:var(--muted);text-decoration:underline dotted}
.secs a:hover{color:var(--accent)}
.tile .more{position:absolute;right:.6rem;bottom:.45rem;font-size:.7rem;color:var(--muted);
 opacity:0;transition:opacity .12s}
.tile:hover .more{opacity:1}

/* ---- popouts: entries, settings, history ---- */
.ov,#sheet{position:fixed;inset:0;background:rgba(20,17,19,.5);display:flex;align-items:flex-start;
 justify-content:center;padding:3vh 1rem;z-index:15;overflow:auto}
#sheet[hidden],.ov[hidden]{display:none}
.pop.wide{max-width:50rem}
.ov #settings,.ov #history{border:0;background:none;padding:0;margin:0}
.ov .set-h:first-child{padding-right:2.4rem}
.ov #history .top{padding-right:2.4rem}
.pop{--k:var(--k-other);position:relative;background:var(--card);color:var(--ink);
 border:1px solid var(--line);border-top:4px solid var(--k);border-radius:12px;
 max-width:44rem;width:100%;padding:1.1rem 1.3rem 1.2rem;
 box-shadow:0 24px 70px rgba(0,0,0,.35);animation:pop .16s ease-out}
@keyframes pop{from{transform:translateY(8px) scale(.985);opacity:0}to{transform:none;opacity:1}}
@media(prefers-reduced-motion:reduce){.pop{animation:none}}
.pop .card{border:0;margin:0;padding:0;background:none}
.pop .body.clip{max-height:none}
.pop .kind{padding-right:5rem;display:inline-flex;align-items:center;gap:.3rem;font-size:.68rem;letter-spacing:.07em;
 text-transform:uppercase;font-weight:700;color:var(--k);margin-bottom:.2rem}
.pop .kind svg{width:.95rem;height:.95rem;fill:currentColor}
.pop .name{padding-right:2.4rem}
.pop .rank{display:none}  /* the kind badge above already carries the level */
.pop .acts{font-size:1.25em}
.pop .x{position:absolute;top:.6rem;right:.6rem;width:2rem;height:2rem;border-radius:50%;
 border:1px solid var(--line);background:var(--card);color:var(--soft);font-size:1.1rem;
 line-height:1;display:flex;align-items:center;justify-content:center;cursor:pointer;padding:0}
.pop .x:hover{border-color:var(--accent);color:var(--accent)}
.pop .nav{display:flex;gap:.5rem;justify-content:space-between;margin-top:.9rem;
 border-top:1px solid var(--line);padding-top:.7rem}
.pop .nav button{padding:.35rem .7rem;font-size:.8rem}
.pop .nav .aon{margin-left:auto;margin-right:auto}

/* ---- generated answer ---- */
.answer{border-left:3px solid var(--warn)}
.answer .flag{color:var(--warn);font-size:.78rem;margin-bottom:.45rem;
 display:flex;gap:.4rem;align-items:flex-start}
.answer .body{color:var(--ink);font-size:.95rem}
.cite{display:inline-flex;align-items:center;gap:.2rem;font-size:.8rem;
 background:var(--chip);border:1px solid var(--line);border-radius:999px;
 padding:.05rem .5rem;color:var(--accent);text-decoration:none;white-space:nowrap}
.cite:hover{border-color:var(--accent)}
.sources-h{font-size:.75rem;letter-spacing:.09em;text-transform:uppercase;color:var(--muted);
 margin:1.4rem 0 .1rem}
.spin{color:var(--muted);font-size:.85rem;padding:.5rem 0}
/* The embedder-mismatch message is three lines and each one carries a fact. */
.err{color:var(--accent);white-space:pre-wrap}
.timing{color:var(--muted);font-size:.72rem;margin-top:.7rem;
 font-variant-numeric:tabular-nums}
.er{font-family:"Erathian",serif;color:var(--accent);letter-spacing:.03em}
.st{color:var(--ink)}
.caret{display:inline-block;width:.45em;height:1em;vertical-align:text-bottom;
 background:var(--warn);animation:blink 1s steps(2,start) infinite}
@keyframes blink{to{visibility:hidden}}
@media(prefers-reduced-motion:reduce){.caret,.dot.pulse{animation:none}}

/* ---- a little more life ----
   The d20 in the header rolls while a question is in flight; the busy line
   speaks in the game's own terms. Neither touches the caution flag on the
   answer, which is the one bit of this page that must stay plain. */
.d20{width:1.6rem;height:1.6rem;flex:none;align-self:center;color:var(--accent)}
.d20 svg{width:100%;height:100%;display:block}
.d20{transform-origin:50% 52%;will-change:transform;backface-visibility:hidden;
 contain:layout paint}
/* The container is a compositor layer: rotating it costs no repaint. Animating
   the SVG's parts did -- ten facets re-rasterised per frame, which stuttered
   on a laptop already busy running the model. */
/* The cheapest motion there is: one composited layer, rotation only, no scale
   and no opacity, so the die is rasterised once and each frame is a single
   transform on the compositor. Slow, so a frame the busy GPU drops is a few
   degrees rather than a jump. */
.d20.rolling{animation:spin 4s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}

@media(prefers-reduced-motion:reduce){.d20.rolling{animation:none}}
#help,#hist{padding:.35rem .65rem;font-size:.8rem;border:1px solid var(--line);
 background:var(--card);color:var(--soft);border-radius:6px;cursor:pointer;
 display:flex;align-items:center;gap:.35rem}
#help{width:2rem;justify-content:center;font-family:ui-serif,Georgia,serif;font-weight:700}
#hist[aria-expanded=true],#help[aria-expanded=true]{border-color:var(--accent);color:var(--accent)}
#hist b{font-weight:600;background:var(--chip);border-radius:999px;padding:0 .4rem;
 font-size:.72rem;color:var(--accent)}
kbd{font:inherit;font-size:.75rem;background:var(--chip);border:1px solid var(--line);
 border-bottom-width:2px;border-radius:4px;padding:0 .35rem;color:var(--soft)}
.hint kbd{font-size:.72rem}

/* ---- empty state: example questions + the last few asked ---- */
#home{margin:.4rem 0 1rem}
#home[hidden]{display:none}
.tryh{font-size:.75rem;letter-spacing:.09em;text-transform:uppercase;color:var(--muted);
 margin:.9rem 0 .35rem}
.chips{display:flex;flex-wrap:wrap;gap:.4rem}
.chip{font-size:.83rem;padding:.35rem .7rem;border:1px solid var(--line);background:var(--card);
 color:var(--ink);border-radius:999px;cursor:pointer;text-align:left;line-height:1.3}
.chip:hover{border-color:var(--accent);color:var(--accent)}
.chip .m{color:var(--muted);font-size:.72rem;margin-left:.35rem}
.chip.again{color:var(--muted);padding:.35rem .6rem}
.recent{list-style:none;margin:0;padding:0}
.recent li{display:flex;gap:.5rem;align-items:baseline}
.recent li button.qq{flex:1;text-align:left;background:none;border:0;padding:.28rem 0;
 color:var(--ink);font-size:.9rem;cursor:pointer;border-radius:4px}
.recent li button.qq:hover{color:var(--accent)}
.recent .m{color:var(--muted);font-size:.72rem;white-space:nowrap;font-variant-numeric:tabular-nums}
.recent .x{background:none;border:0;color:var(--muted);cursor:pointer;padding:0 .3rem;
 font-size:.9rem;border-radius:4px}
.recent .x:hover{color:var(--accent)}

/* ---- history panel ---- */
#history{background:var(--card);border:1px solid var(--line);border-radius:8px;
 padding:.85rem 1rem;margin:0 0 .9rem}
#history[hidden]{display:none}
#history .top{display:flex;align-items:baseline;gap:.6rem;margin-bottom:.4rem}
#history .top .set-h{margin:0;border:0;padding:0;flex:1}
#history .top button{padding:.3rem .6rem;font-size:.78rem}
#history .empty{color:var(--muted);font-size:.85rem;margin:.3rem 0}
.from{display:flex;gap:.6rem;align-items:center;flex-wrap:wrap;font-size:.8rem;
 color:var(--muted);border:1px dashed var(--line);border-radius:8px;padding:.45rem .8rem;
 margin:.2rem 0 .6rem}
.from button{padding:.25rem .6rem;font-size:.78rem}
.answer .foot{display:flex;align-items:center;gap:.6rem;margin-top:.7rem}
.answer .foot .timing{margin:0}
.answer .foot .fun{font-style:italic}
.answer .foot .report{margin-left:auto;padding:.2rem .55rem;font-size:.74rem;white-space:nowrap;
 border-color:var(--line);background:var(--card);color:var(--muted)}
.answer .foot .report:hover{border-color:var(--warn);color:var(--warn)}
.r-label{font-size:.72rem;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:.7rem 0 .2rem}
.r-quote{margin:0;font-size:.88rem;color:var(--soft);background:var(--code);border:1px solid var(--line);
 border-radius:6px;padding:.45rem .6rem;white-space:pre-wrap}
.r-quote.clipq{max-height:9rem;overflow:auto}
#report-wrap textarea,#report-wrap input{width:100%;padding:.5rem .6rem;font:inherit;font-size:.9rem;
 border:1px solid var(--line);background:var(--bg);color:var(--ink);border-radius:6px}
#r-stat.ok{color:var(--ok)}#r-stat.bad{color:var(--accent)}#r-stat.wait{color:var(--muted)}
.from .ok{color:var(--ok)}

/* ---- onboarding ---- */
#onboard{position:fixed;inset:0;background:rgba(20,17,19,.55);display:flex;
 align-items:center;justify-content:center;padding:1rem;z-index:20}
#onboard[hidden]{display:none}
.ob{background:var(--card);color:var(--ink);border:1px solid var(--line);border-radius:12px;
 max-width:32rem;width:100%;padding:1.4rem 1.5rem 1.2rem;box-shadow:0 20px 60px rgba(0,0,0,.35);
 max-height:92vh;overflow:auto}
.ob h2{font-family:ui-serif,Georgia,"Iowan Old Style",serif;font-size:1.35rem;margin:0 0 .2rem;
 display:flex;align-items:center;gap:.6rem}
.ob .lead{color:var(--soft);margin:.2rem 0 .9rem}
.ob ol{margin:0 0 .9rem;padding-left:1.25rem}
.ob li{margin:.45rem 0;color:var(--soft)}
.ob li b{color:var(--ink)}
.ob .trust{display:grid;grid-template-columns:auto 1fr;gap:.25rem .7rem;font-size:.86rem;
 margin:.4rem 0 1rem;align-items:baseline}
.ob .trust .ok{color:var(--ok);font-weight:600}.ob .trust .no{color:var(--crit-fail);font-weight:600}
.ob .trust .so{color:var(--warn);font-weight:600}
.ob .trust .ext{color:var(--accent);font-weight:600}
.ob .models{margin-top:.2rem}
.ob code{background:var(--chip);border-radius:3px;padding:.05rem .3rem;font-size:.82em}
button.link{background:none;border:0;padding:0;font:inherit;color:var(--accent);
 text-decoration:underline;cursor:pointer}
.ob .row{display:flex;gap:.5rem;align-items:center;flex-wrap:wrap;margin-top:.6rem}
.choices{display:flex;gap:.5rem;flex-wrap:wrap}
.choice{flex:1;min-width:13rem;display:flex;flex-direction:column;align-items:flex-start;gap:.15rem;
 padding:.6rem .75rem;text-align:left;line-height:1.35;border:2px solid var(--line);
 background:var(--card);color:var(--ink);border-radius:8px;cursor:pointer;position:relative}
.choice b{font-family:ui-serif,Georgia,"Iowan Old Style",serif;font-size:1rem}
.choice em{position:absolute;top:.55rem;right:.7rem;font-style:normal;font-size:.68rem;
 letter-spacing:.06em;text-transform:uppercase;color:var(--ok);font-weight:700}
.choice span{font-size:.8rem;color:var(--soft)}
.choice.on{border-color:var(--accent);background:var(--chip)}
.choice.on b{color:var(--accent)}
.tog{display:flex;align-items:center;gap:.4rem;font-size:.88rem;color:var(--ink);cursor:pointer}
.tog input{width:auto;margin:0}
.ob .row .note{margin:0;flex:1;grid-column:auto}
</style></head><body><div class="wrap">
<header><a href="/" id="home-link" title="Start over"><span class="d20" id="d20" aria-hidden="true"></span>
<h1>The Klever Kobold <small>— Pathfinder 2e rules, offline</small></h1></a>
<button id="hist" title="Questions you have asked" aria-expanded="false" aria-controls="history"></button>
<button id="gear" title="Settings" aria-expanded="false" aria-controls="settings"></button>
<button id="help" title="How this works" aria-expanded="false">?</button>
<button id="theme" title="Theme"></button></header>
<div id="status"><span class="dot pulse"></span><span id="statustext">starting…</span></div>
<form id="f"><input id="q" placeholder="ask the kobold what happens, name a thing, or describe it…" autofocus
 autocomplete="off" disabled><button class="primary" id="askbtn" disabled>Ask</button>
<button id="lookbtn" type="button" disabled>Look up</button></form>
<p class="hint"><kbd>Enter</kbd> asks · <kbd>Shift</kbd>+<kbd>Enter</kbd> shows only the entries
· <kbd>↑</kbd> earlier questions</p>
<p class="hint" id="thread" hidden></p>

<div id="history-wrap" class="ov" hidden><div class="pop" role="dialog" aria-modal="true" aria-label="Asked before">
<button type="button" class="x" data-close="history-wrap" title="Close (Esc)" aria-label="Close">×</button>
<div id="history">
<div class="top"><p class="set-h">Things you asked the kobold</p>
 <button type="button" id="h-clear">Make the kobold forget</button></div>
<p class="note" style="margin:0 0 .5rem">Answers are kept in this browser, so asking the same
thing again is instant — until you press <b>Ask again</b>.</p>
<ul class="recent" id="h-list"></ul>
</div></div></div>

<div id="onboard" hidden>
<div class="ob" role="dialog" aria-modal="true" aria-labelledby="ob-h">
<h2 id="ob-h"><span class="d20" aria-hidden="true"></span>Well met, adventurer.</h2>
<p class="lead">The Klever Kobold is a Pathfinder 2e rules reference that runs entirely on this
machine. It carries its own copy of <span id="ob-corpus">the Archives of Nethys — 41,743
entries —</span> so nothing you type leaves your computer, and it works without a connection.
Each entry links to its page on the live site, should you want to check. No account, no
cloud, no dice tax.</p>
<p class="lead">It is a kobold: quick, keen, and wrong more often than it would like to admit —
which is why every answer shows the entries it was read from.</p>
<p class="lead">Everything it knows, it dug out of the
<a href="https://2e.aonprd.com/" target="_blank" rel="noreferrer">Archives of Nethys</a>, which a small
team keeps free. If the kobold earns its keep at your table, please
<a href="https://www.patreon.com/nethys" target="_blank" rel="noreferrer">support the Archives</a>.</p>
<ol>
 <li><b>Type a question and press Enter.</b> It finds the relevant entries in the local copy
  and a local model writes a short answer that cites them.</li>
 <li><b>Shift+Enter shows only the entries</b> — faster, and often all you need. Click an
  entry to read the whole thing.</li>
 <li><b>Everything you ask is kept in this browser.</b> The history button brings it back
  instantly; the same question twice costs nothing.</li>
</ol>
<div class="trust">
 <span class="ok">Trust it</span><span>“What level is Battle Medicine?” · “How does Treat Wounds work?”</span>
 <span class="so">Mostly</span><span>“Is there a feat that makes falling less dangerous?”</span>
 <span class="no">Read the rule</span><span>“Does X interact with Y?” — it finds the rule fast; you settle the argument.</span>
 <span class="so" id="trust-lore-h" hidden>Lore, mostly</span><span id="trust-lore" hidden>“Who rules Cheliax?” — from PathfinderWiki, which is thorough on the old
  books and thin on the newest. A rules question never gets a lore answer.</span>
</div>
<p class="tryh" style="margin-top:.2rem">Pick who answers</p>
<div class="choices" id="ob-choices">
 <button type="button" class="choice on" data-choice="faster"><b>Faster</b><em>recommended</em>
  <span>Quick answers, light on memory. Right 93 times out of 109 on our test.</span></button>
 <button type="button" class="choice" data-choice="better"><b>Better</b>
  <span>Right 100 times out of 109, at half the speed and about 7 GB of memory.
  Downloaded once, the first time you pick it.</span></button>
</div>
<p class="note" style="margin:.4rem 0 0">Change it any time in Settings. Your own model server, or
the MCP setup for Claude Desktop and Claude Code: Settings →
<button type="button" class="link" id="ob-settings">Expert mode</button>.</p>
<div class="row"><button class="primary" type="button" id="ob-go">Roll for initiative</button>
<p class="note">Press <kbd>?</kbd> any time to see this again.</p></div>
</div></div>

<div id="report-wrap" class="ov" hidden><div class="pop" role="dialog" aria-modal="true" aria-label="Report a wrong answer">
<button type="button" class="x" data-close="report-wrap" title="Close (Esc)" aria-label="Close">×</button>
<p class="set-h">Tell the kobold it was wrong</p>
<p class="note" id="r-where" style="margin:.2rem 0 .7rem"></p>
<p class="r-label">Question</p><p class="r-quote" id="r-q"></p>
<p class="r-label">Answer given</p><p class="r-quote clipq" id="r-a"></p>
<p class="r-label"><label for="r-fix">What is wrong, and what is right</label></p>
<textarea id="r-fix" rows="5" placeholder="e.g. Sneak Attack applies to the rogue's own Strikes, not to an ally's Reactive Strike."></textarea>
<p class="r-label"><label for="r-src">Where it says so (optional)</label></p>
<input id="r-src" placeholder="https://2e.aonprd.com/… or a page number">
<div class="row" style="margin-top:.8rem">
 <button type="button" class="primary" id="r-send">Send</button>
 <button type="button" class="primary" id="r-issue">Open as GitHub issue</button>
 <button type="button" id="r-copy">Copy as text</button>
 <span id="r-stat" class="note" style="margin:0"></span></div>
</div></div>

<div id="favs" hidden><p class="tryh">★ The hoard</p><div class="tiles" id="fav-tiles"></div></div>
<div id="home" hidden>
<p class="tryh">Ask the kobold</p>
<div class="chips" id="examples"></div>
<div id="recent-wrap" hidden><p class="tryh">You asked earlier</p><ul class="recent" id="recent"></ul></div>
</div>

<div id="settings-wrap" class="ov" hidden><div class="pop wide" role="dialog" aria-modal="true" aria-label="Settings">
<button type="button" class="x" data-close="settings-wrap" title="Close (Esc)" aria-label="Close">×</button>
<div id="settings">
<p class="set-h">Who answers</p>
<div class="presets">
 <button type="button" class="preset" id="p-faster"><b>Faster</b>
  <span>recommended · quick and light · 93 of 109</span></button>
 <button type="button" class="preset" id="p-better"><b>Better</b>
  <span>100 of 109 · half the speed · ~7 GB</span></button>
</div>
<p class="note" id="p-note"></p>
<div id="scope-wrap" hidden>
<p class="set-h" style="margin-top:.9rem">What it digs through</p>
<div class="grid">
 <label for="s-scope">Sources</label>
 <select id="s-scope">
  <option value="auto">Rules, and Golarion lore when the question is about the world</option>
  <option value="rules">Rules only — the Archives of Nethys</option>
  <option value="lore">Rules and lore together, every time</option>
 </select>
 <p class="note" id="s-scopenote"></p>
</div>
</div>
<div class="pair" style="margin-top:.9rem"><label class="tog"><input type="checkbox" id="s-expert">
 Expert mode</label><span class="note" style="margin:0">model servers, retrieval knobs, MCP</span></div>

<div id="expert" hidden>
<p class="set-h">Answering model</p>
<div class="grid">
 <label for="s-backend">Backend</label>
 <select id="s-backend">
  <option value="ollama">Ollama</option>
  <option value="openai">OpenAI-compatible</option>
 </select>
 <label for="s-base">Base URL</label>
 <input id="s-base" autocomplete="off" spellcheck="false"
  placeholder="http://localhost:11434">
 <label for="s-model">Model</label>
 <div class="pair"><input id="s-model" list="s-models" autocomplete="off" spellcheck="false"
  placeholder="qwen3.5:9b"><datalist id="s-models"></datalist>
  <button id="s-test" type="button">Test connection</button></div>
 <label for="s-key" id="s-keylabel">API key</label>
 <input id="s-key" type="password" autocomplete="off" spellcheck="false"
  placeholder="left blank for a local server">
 <p class="note" id="s-keywarn"></p>
</div>
<p id="tstat"></p>

<p class="set-h">Retrieval</p>
<div class="nums">
 <span><label for="s-k">Excerpts</label><input id="s-k" type="number" min="1" max="24"></span>
 <span><label for="s-rerank">Rerank</label><input id="s-rerank" type="checkbox"></span>
 <span><label for="s-ctx">Context chars</label><input id="s-ctx" type="number" min="200"
  max="8000" step="100"></span>
 <span><label for="s-tokens">Answer tokens</label><input id="s-tokens" type="number" min="32"
  max="4000" step="50"></span>
</div>
<p class="set-h">Conversation</p>
<div class="pair"><label class="tog"><input type="checkbox" id="s-followup">
 Follow-up questions</label><span class="note" style="margin:0">off by default</span></div>
<p class="note" id="s-follownote" style="margin:.35rem 0 0">Each question is answered on its own.
Turned on, the kobold reads your last question and its answer, rewrites a follow-up like “what if
she’s prone?” into a question that can be looked up, and searches the Archives again for it. One
extra model call; only the last turn travels, never the one before it.</p>

<div class="grid" style="margin-top:.6rem">
 <label for="s-embed">Embedder</label>
 <select id="s-embed">
  <option value="server">This server's</option>
  <option value="backend">The backend above</option>
 </select>
 <p class="note" id="s-embednote"></p>
</div>
<div class="pair" style="margin-top:.7rem"><button id="s-reset" type="button">Reset to
 defaults</button></div>

<p class="set-h">Use it from Claude Desktop or Claude Code</p>
<p class="tools">Exposes <code>kobold_ask</code> and <code>kobold_search</code> to Claude over stdio.</p>
<div class="pair" style="margin-top:.5rem"><b style="font-size:.8rem;color:var(--soft)">Claude
 Desktop</b><button id="c-desktop" type="button">Copy</button></div>
<pre class="snip" id="snip-desktop">{
  "mcpServers": {
    "pf2e": {
      "command": "kobold",
      "args": ["mcp"]
    }
  }
}</pre>
<div class="pair" style="margin-top:.6rem"><b style="font-size:.8rem;color:var(--soft)">Claude
 Code</b><button id="c-code" type="button">Copy</button></div>
<pre class="snip" id="snip-code">claude mcp add kobold -- kobold mcp</pre>
<p class="tools">Without the <code>kobold</code> command: <code>"command": "/path/to/.venv/bin/python",
"args": ["-m", "kleverkobold", "mcp"]</code>. These settings do not travel to it.</p>
</div>
</div></div></div>

<div id="out"></div>
<footer class="thanks">The kobold digs in the <a href="https://2e.aonprd.com/" target="_blank" rel="noreferrer">Archives of Nethys</a>,
which a small team keeps free for everyone. If it helps you, <a href="https://www.patreon.com/nethys" target="_blank" rel="noreferrer">support them</a>
<span class="sep">·</span> Lore comes from <a href="https://pathfinderwiki.com/" target="_blank" rel="noreferrer">PathfinderWiki</a>, written by volunteers —
<a href="https://pathfinderwiki.com/wiki/Help:Contents" target="_blank" rel="noreferrer">help write it</a>.</footer>
</div><script>
const EL=id=>document.getElementById(id);
// Settings, history and favourites saved under the old name carry over once.
try{for(const k of ['theme','settings','onboarded','history','favs','expert']){
  const o=localStorage.getItem('pf2e-'+k);
  if(o!==null&&localStorage.getItem('kobold-'+k)===null){localStorage.setItem('kobold-'+k,o);localStorage.removeItem('pf2e-'+k)}}}catch(e){}
const out=document.getElementById('out'),q=document.getElementById('q'),
 st=document.getElementById('status'),stt=document.getElementById('statustext'),
 look=document.getElementById('lookbtn'),askBtn=document.getElementById('askbtn'),
 themeBtn=document.getElementById('theme'),d20=document.getElementById('d20');
const D20='<svg viewBox="0 0 32 32" aria-hidden="true"><polygon points="16,1.6 7.6,11.9 24.4,11.9" fill="currentColor" opacity="0.42"/><polygon points="3.4,8.8 16,1.6 7.6,11.9" fill="currentColor" opacity="0.28"/><polygon points="16,1.6 28.6,8.8 24.4,11.9" fill="currentColor" opacity="0.34"/><polygon points="3.4,8.8 7.6,11.9 3.4,23.2" fill="currentColor" opacity="0.2"/><polygon points="28.6,8.8 28.6,23.2 24.4,11.9" fill="currentColor" opacity="0.26"/><polygon points="3.4,23.2 7.6,11.9 16,26.4" fill="currentColor" opacity="0.16"/><polygon points="24.4,11.9 28.6,23.2 16,26.4" fill="currentColor" opacity="0.22"/><polygon points="3.4,23.2 16,26.4 16,30.4" fill="currentColor" opacity="0.12"/><polygon points="16,26.4 28.6,23.2 16,30.4" fill="currentColor" opacity="0.18"/><polygon points="7.6,11.9 24.4,11.9 16,26.4" fill="currentColor" opacity="0.07"/><polygon points="16,1.6 28.6,8.8 28.6,23.2 16,30.4 3.4,23.2 3.4,8.8" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><path d="M16,1.6 L7.6,11.9 M16,1.6 L24.4,11.9 M7.6,11.9 L24.4,11.9 M7.6,11.9 L16,26.4 M24.4,11.9 L16,26.4 M3.4,8.8 L7.6,11.9 M28.6,8.8 L24.4,11.9 M3.4,23.2 L7.6,11.9 M28.6,23.2 L24.4,11.9 M3.4,23.2 L16,26.4 M28.6,23.2 L16,26.4 M16,30.4 L16,26.4" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linejoin="round" stroke-linecap="round"/></svg>';
d20.innerHTML=D20;document.querySelector('.ob .d20').innerHTML=D20;

/* ---------- theme: auto / light / dark, remembered per browser ---------- */
const ICON={
 auto:'<svg viewBox="0 0 16 16"><path d="M8 1a7 7 0 100 14A7 7 0 008 1zm0 1.6v10.8a5.4 5.4 0 010-10.8z"/></svg>',
 light:'<svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="3.2"/><path d="M8 .8v2.1M8 13.1v2.1M.8 8h2.1M13.1 8h2.1M2.9 2.9l1.5 1.5M11.6 11.6l1.5 1.5M13.1 2.9l-1.5 1.5M4.4 11.6l-1.5 1.5" stroke="currentColor" stroke-width="1.3" fill="none" stroke-linecap="round"/></svg>',
 dark:'<svg viewBox="0 0 16 16"><path d="M13.4 10.2A5.8 5.8 0 015.8 2.6a6 6 0 107.6 7.6z"/></svg>'};
const THEMES=['auto','light','dark'];
let theme=localStorage.getItem('kobold-theme')||'auto';
function applyTheme(){
  if(theme==='auto')document.documentElement.removeAttribute('data-theme');
  else document.documentElement.setAttribute('data-theme',theme);
  themeBtn.innerHTML=ICON[theme]+'<span>'+theme[0].toUpperCase()+theme.slice(1)+'</span>';
  try{localStorage.setItem('kobold-theme',theme)}catch(e){}
}
themeBtn.addEventListener('click',()=>{theme=THEMES[(THEMES.indexOf(theme)+1)%3];applyTheme()});
applyTheme();

function esc(s){return (s||'').replace(/[&<>"]/g,c=>(
 {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function enable(on){q.disabled=!on;look.disabled=!on;askBtn.disabled=!on;
 if(on&&!q.value)q.focus()}

/* ---------- action glyphs ----------
   The same symbols the Archives use, from Paizo's icon font embedded above:
   one/two/three actions, the hollow diamond for a free action, the turned
   arrow for a reaction. "Single Action or Two Actions" shows both, joined. */
const COST={'single action':'\ue902','one action':'\ue902','two actions':'\ue901',
 'three actions':'\ue900','reaction':'\ue904','free action':'\ue903'};
function glyphs(label){
  const key=(label||'').toLowerCase().trim();
  if(!key)return '';
  if(COST[key])return '<span class="acts" title="'+esc(label)+'" aria-label="'+esc(label)+'">'+COST[key]+'</span>';
  const parts=key.split(/\s+(?:or|to)\s+/).map(p=>COST[p]).filter(Boolean);
  if(parts.length>1)return '<span class="acts" title="'+esc(label)+'" aria-label="'+esc(label)+'">'+
    parts.join('<span class="dash">–</span>')+'</span>';
  return '<span class="acts txt" title="'+esc(label)+'">'+esc(label)+'</span>';
}

/* ---------- markdown ----------
   Input is model output and corpus text, so everything is escaped first and the
   transforms run over escaped text. Nothing here can introduce a tag the source
   did not already have escaped away. */
const DEGREES=/^(Critical Success|Success|Failure|Critical Failure)\b/;
function chip(url,label){
  return '<a class="cite" href="'+esc(url)+'" target="_blank" rel="noreferrer">'+
    esc(label)+'</a>';
}
function inline(t,cites){
  // The corpus keeps the Archives' own links ("[grabbed](https://2e.aonprd.com/…)").
  // They are rendered first, and the bare-URL pass below is told to leave an
  // href alone, so a link is never linked twice.
  t=t.replace(/\[([^\]\n]+)\]\((https?:\/\/[^)\s]+)\)/g,(m,label,url)=>
     '<a class="lnk" href="'+url+'" target="_blank" rel="noreferrer">'+label+'</a>');
  t=t.replace(/\*\*(.+?)\*\*/g,'<b>$1</b>')
     // require a non-space next to each marker, or the "*   *" between list
     // items becomes an italic run of spaces
     .replace(/(^|[^*])\*(?=\S)([^*\n]*[^*\s])\*/g,'$1<i>$2</i>')
     // _Player Core_ -- underscores only when they wrap a word, not inside one
     .replace(/(^|[^\w])_(?=\S)([^_\n]*[^_\s])_(?!\w)/g,'$1<i>$2</i>');
  // "[Reaction]", "[Two Actions]" in the body are AoN's action markers.
  t=t.replace(/\[((?:Single|One|Two|Three|Free) Actions?|Reaction)((?: (?:or|to) (?:Single|One|Two|Three|Free) Actions?)?)\]/g,
     (m,a,b)=>glyphs(a+b)||m);
  t=t.replace(/(?<!href=")https?:\/\/[^\s<)\]"]+/g,u=>{
    const clean=u.replace(/[.,;:]$/,''),tail=u.slice(clean.length);
    return chip(clean,AON_LABEL[clean]||clean.replace(/^https?:\/\/(www\.)?/,''))+tail;
  });
  if(cites&&CITES.length){
    // The answer cites excerpts by the number they carried in the prompt. Turn
    // each into the Archives of Nethys entry it refers to, and swallow the name
    // after it when the model repeated it.
    t=t.replace(/\[(\d+)\](\s*:?\s*)([A-Z][\w'\u2019\- ]{0,40})?/g,(m,n,gap,name)=>{
      const h=CITES[+n-1]; if(!h)return m;
      const same=name&&name.toLowerCase().startsWith(h.name.toLowerCase());
      return chip(h.url,h.name)+(same?name.slice(h.name.length):(gap+(name||'')));
    });
  }
  // DCs and dice stand out, the way a reader's eye already looks for them.
  // Only in text nodes: a URL or an attribute must not be rewritten.
  t=t.split(/(<[^>]+>)/).map(seg=>seg.startsWith('<')?seg:seg
     .replace(/\bDC\s?(\d{1,2})\b/g,'<span class="dc">DC $1</span>')
     .replace(/\b(\d{1,3}d\d{1,3}(?:\s?[+\u2212\-]\s?\d{1,3})?)\b/g,'<span class="dice">'+DIE+'$1</span>')
  ).join('');
  return t;
}
const DIE='<svg class="die" viewBox="0 0 16 16" aria-hidden="true"><path d="M8 1 1.8 4.6v6.8L8 15l6.2-3.6V4.6z" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M8 1v5.3L1.8 4.6M8 6.3l6.2-1.7M8 6.3 4.3 11.6h7.4z" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linejoin="round"/></svg>';
let AON_LABEL={};   // url -> entry name, so a cited link reads as the thing it cites
let CITES=[];       // the excerpts as numbered for the model, so "[3]" can link
function md(src,cites){
  const lines=esc(src||'').split('\n');
  let html='',para=[],list=null;
  const flush=()=>{if(para.length){html+='<p>'+inline(para.join(' '),cites)+'</p>';para=[]}};
  const closeList=()=>{if(list){flush();html+='<ul>'+list.join('')+'</ul>';list=null}};
  for(let i=0;i<lines.length;i++){
    const line=lines[i].trim();
    if(!line){closeList();flush();continue}
    if(/^(---|\*\*\*|___)$/.test(line)){closeList();flush();html+='<hr>';continue}
    if(/^#{1,6}\s/.test(line)){closeList();flush();
      html+='<p><b>'+inline(line.replace(/^#{1,6}\s*/,''),cites)+'</b></p>';continue}
    // "**Proficiency** | **DC** | …" then one row per line: a table the corpus
    // flattened to pipes. Consecutive piped lines become one <table>; a row of
    // bold cells is the header.
    if(line.includes(' | ')){
      closeList();flush();
      const rows=[];
      while(i<lines.length&&lines[i].trim().includes(' | ')){rows.push(lines[i].trim());i++}
      i--;
      html+='<div class="tw"><table>'+rows.map((r,n)=>{
        const cells=r.split(/\s*\|\s*/);
        const head=n===0&&cells.every(c=>/^\*\*.+\*\*$/.test(c));
        const tag=head?'th':'td';
        return '<tr>'+cells.map(c=>'<'+tag+'>'+inline(c,cites)+'</'+tag+'>').join('')+'</tr>';
      }).join('')+'</table></div>';
      continue;
    }
    const li=lines[i].match(/^(\s*)[-*•]\s+(.*)$/);
    if(li){
      flush();
      const deep=li[1].length>=2;   // the model indents sub-points by 2+ spaces
      (list=list||[]).push((deep?'<li class="sub">':'<li>')+inline(li[2],cites)+'</li>');
      continue;
    }
    closeList();
    // "**Critical Success** ..." and "**Range** ..." are stat-block fields, not
    // prose: each starts its own line and the label carries the emphasis.
    const f=line.match(/^\*\*([^*]+)\*\*\s*(.*)$/);
    if(f){
      flush();
      // Several fields put their value on the following line ("**Traditions**\n
      // Arcane, Primal"). Rendering that literally leaves an empty label and an
      // orphan paragraph, so pull the value up onto the label's line.
      let val=f[2];
      if(!val.trim()){
        while(i+1<lines.length&&lines[i+1].trim()&&
              !/^(\*\*|#|---|[-*•]\s)/.test(lines[i+1].trim())){
          val+=(val?' ':'')+lines[++i].trim();
        }
      }
      const deg=DEGREES.test(f[1]);
      const cls=deg?(/Critical Failure/.test(f[1])?'deg cf':
        (/^Failure/.test(f[1])?'deg f':'deg')):(/^Source$/i.test(f[1])?'src':'');
      if(cls==='src'){
        // "Player Core pg. 332" -> book in italics, page number muted, edition tag
        val=val.replace(/^((?:\[[^\]]+\]\([^)]+\))|[^,;]+?)(\s+pg\.?\s*\d+[\d\u2013\-]*)?(\s+\d\.\d)?\s*$/,
          (m,book,pg,ed)=>'<i>'+book+'</i>'+(pg?'<span class="pg">'+pg+'</span>':'')+
                          (ed?'<span class="ed">'+ed.trim()+'</span>':''));
      }
      html+='<p'+(cls?' class="'+cls+'"':'')+'><span class="field">'+inline(f[1],cites)+
        '</span> '+inline(val,cites)+'</p>';
      continue;
    }
    para.push(line);
  }
  closeList();flush();
  return html;
}

/* ---------- stat block ----------
   Splits "# Name [Two Actions] (Feat 1)" and the Traits line back out of the
   body so they can be laid out as a header rather than read as prose. */
const RARITY=['common','uncommon','rare','unique'];
const SIZES=['tiny','small','medium','large','huge','gargantuan'];
function statblock(h){
  let text=(h.text||'').replace(/\r/g,'');
  let title=h.name,cost='',kind='';
  // The heading may wrap onto a second line (spells do this).
  const head=text.match(/^#\s*([^\n]*(?:\n\[[^\]]*\][^\n]*)?)/);
  if(head){
    text=text.slice(head[0].length).replace(/^\n+/,'');
    let t=head[1].replace(/\n/g,' ').replace(/\[([^\]]+)\]\(https?:[^)]+\)/g,'$1');
    // An action with no cost is written "[]" in the corpus; drop the empty brackets.
    t=t.replace(/\[\s*\]/,'');
    const c=t.match(/\[([^\]]+)\]/); if(c){cost=c[1];t=t.replace(c[0],'')}
    const k=t.match(/\(([^)]+)\)\s*$/); if(k){kind=k[1];t=t.replace(k[0],'')}
    title=t.trim()||h.name;
  }
  let traits=[];
  // [ \t]* not \s*: an empty Traits line (archetypes) must not swallow the Source line after it.
  const tr=text.match(/^\*\*Traits\*\*[ \t]*([^\n]*)\n?/m);
  if(tr){traits=tr[1].split(',').map(s=>s.trim()).filter(Boolean);
         text=text.replace(tr[0],'')}
  // The kind badge above already says "Action" or "Spell"; the corner is for
  // the level, which the heading carries as "Feat 2" or the record as a number.
  const lvl=(kind||'').match(/\d+$/);
  const rank=lvl?'Level '+lvl[0]:(h.level!==null&&h.level!==undefined?'Level '+h.level:'');

  const pills=traits.map(t=>{
    const l=t.toLowerCase();
    const cls=RARITY.includes(l)?l:(SIZES.includes(l)?'size':'');
    return '<span class="trait'+(cls?' '+cls:'')+'">'+esc(t)+'</span>';
  }).join('');

  return '<div class="card"><div class="head">'+
    '<h2 class="name"><a href="'+esc(h.url)+'" target="_blank" rel="noreferrer">'+
      esc(title)+'</a></h2>'+glyphs(cost)+
    (rank?'<span class="rank">'+esc(rank)+'</span>':'')+'</div>'+
    (pills?'<div class="traits">'+pills+'</div>':'')+
    '<div class="body clip">'+md(text)+'</div></div>';
}
/* ---------- tiles and the popout ----------
   Eight full stat blocks are a wall; eight tiles are a glance. A tile shows the
   kind (coloured), the name with its action cost, up to four traits and the
   first line. Clicking opens the whole entry in a popout with an × in the
   corner; ← → step through the eight without closing it. */
let SHOWN=[],OPEN=-1,OPEN_SRC='res';
const KIND_ICON={
 spell:'<svg viewBox="0 0 16 16"><path d="M8 0l1.6 4.9L14.5 5l-3.9 3 1.5 4.9L8 10l-4.1 2.9L5.4 8 1.5 5l4.9-.1z"/></svg>',
 feat:'<svg viewBox="0 0 16 16"><path d="M8 1l6 2.2v4.1c0 3.6-2.5 6.3-6 7.7-3.5-1.4-6-4.1-6-7.7V3.2zM6.9 10.4l4.2-4.2-1.1-1.1-3.1 3.1-1.4-1.4-1.1 1.1z"/></svg>',
 action:'<svg viewBox="0 0 16 16"><path d="M8 1l7 7-7 7-7-7z"/></svg>',
 skill:'<svg viewBox="0 0 16 16"><path d="M2 2h5.2c.7 0 1.3.3 1.8.8.5-.5 1.1-.8 1.8-.8H14v10h-4.4c-.6 0-1.1.3-1.6.8-.5-.5-1-.8-1.6-.8H2zm1.4 1.4v7.2H6c.6 0 1.1.1 1.3.4V4.4c-.3-.6-.8-1-1.3-1zm5.3 1v6.6c.2-.3.7-.4 1.3-.4h2.6V3.4H10c-.5 0-1 .4-1.3 1z"/></svg>',
 rules:'<svg viewBox="0 0 16 16"><path d="M3 1h8.5A1.5 1.5 0 0113 2.5V13H4.3a1 1 0 000 2H13v-1H4.3a2.3 2.3 0 010-4.6H11.5V2.4H3.5c-.3 0-.5.2-.5.5V11h-1V2.9A1.9 1.9 0 013 1z"/></svg>',
 item:'<svg viewBox="0 0 16 16"><path d="M13.6 1.2 14.8 2.4 7.9 9.3l-1.2-1.2z"/><path d="M5.4 9.4l1.2 1.2-1 1-.9.1-.3-.3.1-.9z"/><path d="M4.2 8.6l3.2 3.2-1.1 1.1-3.2-3.2z" opacity=".55"/><path d="M3.3 11.6l1.1 1.1-1.6 1.6a.8.8 0 01-1.1-1.1z"/></svg>',
 creature:'<svg viewBox="0 0 16 16"><circle cx="4" cy="5" r="1.7"/><circle cx="12" cy="5" r="1.7"/><circle cx="7" cy="2.6" r="1.5"/><circle cx="9.6" cy="2.6" r="1.5"/><path d="M8 7c2.6 0 4.5 2.1 4.5 4.2 0 1.7-1.4 2.6-2.6 2.1-.9-.4-2.9-.4-3.8 0-1.2.5-2.6-.4-2.6-2.1C3.5 9.1 5.4 7 8 7z"/></svg>',
 condition:'<svg viewBox="0 0 16 16"><path d="M8 14.5S1.5 10.2 1.5 5.6A3.4 3.4 0 018 3.7a3.4 3.4 0 016.5 1.9c0 4.6-6.5 8.9-6.5 8.9z"/></svg>',
 class:'<svg viewBox="0 0 16 16"><path d="M8 1.2l2 4.1 4.5.6-3.3 3.2.8 4.5L8 11.5l-4 2.1.8-4.5L1.5 5.9 6 5.3z" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>',
 other:'<svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="3.2"/></svg>',
 lore:'<svg viewBox="0 0 16 16"><path d="M8 1a7 7 0 100 14A7 7 0 008 1zm4.9 6.3h-2.2a11 11 0 00-.9-3.6 5.7 5.7 0 013.1 3.6zM8 2.4c.7.9 1.3 2.4 1.5 4.9h-3C6.7 4.8 7.3 3.3 8 2.4zM3.1 8.7h2.2c.1 1.4.4 2.6.9 3.6a5.7 5.7 0 01-3.1-3.6zm2.2-1.4H3.1a5.7 5.7 0 013.1-3.6c-.5 1-.8 2.2-.9 3.6zM8 13.6c-.7-.9-1.3-2.4-1.5-4.9h3c-.2 2.5-.8 4-1.5 4.9zm1.8-1.3c.5-1 .8-2.2.9-3.6h2.2a5.7 5.7 0 01-3.1 3.6z"/></svg>'};
const KIND_OF={spell:'spell',ritual:'spell',feat:'feat',action:'action',
 'skill general action':'action',skill:'skill',rules:'rules',sidebar:'rules',
 'category page':'rules',equipment:'item',weapon:'item',armor:'item',shield:'item',
 creature:'creature',hazard:'creature','creature family':'creature',condition:'condition',
 trait:'condition','class feature':'class',class:'class',archetype:'class',
 background:'class',heritage:'class',ancestry:'class',deity:'other'};
// A lore entry is its own kind whatever its wiki template says: the stripe
// colour is the first thing that tells a nation page from a deity stat block.
function kindOf(cat,h){if(h&&h.corpus==='pathfinderwiki')return 'lore';return KIND_OF[(cat||'').toLowerCase()]||'other'}
const isLore=h=>!!h&&h.corpus==='pathfinderwiki';
function parseHead(h){
  let text=(h.text||'').replace(/\r/g,'');
  const head=text.match(/^#\s*([^\n]*(?:\n\[[^\]]*\][^\n]*)?)/);
  let title=h.name,cost='',kind='';
  if(head){let t=head[1].replace(/\n/g,' ').replace(/\[([^\]]+)\]\(https?:[^)]+\)/g,'$1')
      .replace(/\[\s*\]/,'');
    const c=t.match(/\[([^\]]+)\]/);if(c){cost=c[1];t=t.replace(c[0],'')}
    const k=t.match(/\(([^)]+)\)\s*$/);if(k){kind=k[1];t=t.replace(k[0],'')}
    title=t.trim()||h.name}
  const tr=text.match(/^\*\*Traits\*\*[ \t]*([^\n]*)/m);
  const traits=tr?tr[1].split(',').map(x=>x.trim()).filter(Boolean):[];
  const rarity=traits.map(t=>t.toLowerCase()).find(t=>RARITY.includes(t)&&t!=='common')||'';
  return {title,cost,kind,traits,rarity,text};
}
function kindBadge(h,p){
  const k=kindOf(h.category,h);
  const label=isLore(h)?(h.category||'article')+' · lore':(p.kind?p.kind.replace(/\s+\d+$/,''):(h.category||'entry'));
  const lvl=(p.kind||'').match(/\d+$/);
  return '<span class="kind">'+KIND_ICON[k]+esc(label)+
    (lvl?'<span class="lvl">Level '+lvl[0]+'</span>':
     (h.level!==null&&h.level!==undefined?'<span class="lvl">Level '+h.level+'</span>':''))+
    '</span>';
}
function firstLine(text){
  let t=(text||'').split('\n').map(l=>l.trim())
    .filter(l=>l&&!/^(#|\*\*[^*]+\*\*\s*$|---|\*\*(Traits|Source|Requirements|Trigger|Frequency|Prerequisites|Access|Cast|Range|Area|Targets|Duration|Saving Throw|Price|Bulk|Usage|Hands)\*\*)/.test(l)
      &&!l.includes(' | '));
  t=(t[0]||'').replace(/\*\*?/g,'');
  return t.length>150?t.slice(0,150).replace(/\s+\S*$/,'')+'…':t;
}
/* ---------- favourites ----------
   A star on any entry keeps it on the front page. The whole entry is stored,
   so a favourite opens instantly and offline like anything else here. */
const FKEY='kobold-favs';
let FAVS=[];
try{FAVS=JSON.parse(localStorage.getItem(FKEY)||'[]');if(!Array.isArray(FAVS))FAVS=[]}catch(e){FAVS=[]}
const favKey=h=>h.url||h.name;
const isFav=h=>FAVS.some(f=>favKey(f)===favKey(h));
function toggleFav(h){
  if(isFav(h))FAVS=FAVS.filter(f=>favKey(f)!==favKey(h));
  else FAVS.unshift({name:h.name,category:h.category,level:h.level,url:h.url,text:h.text,
                     summary:h.summary||'',legacy_name:h.legacy_name||[],corpus:h.corpus||'aon'});
  try{localStorage.setItem(FKEY,JSON.stringify(FAVS))}catch(e){}
  paintFavs();
  for(const b of document.querySelectorAll('.star[data-key]'))
    b.classList.toggle('on',FAVS.some(f=>favKey(f)===b.dataset.key)),
    b.textContent=b.classList.contains('on')?'★':'☆';
}
function starBtn(h){
  const on=isFav(h);
  return '<button type="button" class="star'+(on?' on':'')+'" data-key="'+esc(favKey(h))+
    '" title="'+(on?'Take it out of the hoard':'Add it to the hoard')+'" aria-label="Hoard">'+
    (on?'★':'☆')+'</button>';
}
function paintFavs(){
  const w=EL('favs');w.hidden=!FAVS.length;
  EL('fav-tiles').innerHTML=FAVS.map((h,i)=>tile(h,i,'fav')).join('');
}
let EXTRA=[];   // entries the answer mentions that were not among the eight shown
const LISTS={res:()=>SHOWN,fav:()=>FAVS,ext:()=>EXTRA};
/* ---------- names in the answer ----------
   "You can Grab an Edge as a reaction" -- the name becomes a link that opens
   the entry. Longest names first so "Treat Wounds" wins over "Wounds"; text
   nodes only, so nothing inside an existing link or tag is touched. */
function linkNames(html){
  const pool=[];
  for(const [src,list] of [['res',SHOWN],['ext',EXTRA]])
    list.forEach((h,i)=>{if(h.name&&h.name.length>=4)pool.push({name:h.name,url:h.url,src,i})});
  if(!pool.length)return html;
  pool.sort((a,b)=>b.name.length-a.name.length);
  // One pass with every name in one alternation, longest first: a replacement
  // never sees the markup another replacement just inserted, which is how
  // "Feats" once matched inside a freshly made href.
  const byKey={};for(const p of pool)byKey[p.name.toLowerCase()]=byKey[p.name.toLowerCase()]||p;
  const alt=Object.values(byKey).map(p=>p.name.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).join('|');
  const re=new RegExp('(^|[^\\w])('+alt+')(?![\\w])','gi');
  const seen=new Set();
  return html.split(/(<[^>]+>)/).map(seg=>{
    if(seg.startsWith('<'))return seg;
    return seg.replace(re,(m,pre,txt)=>{
      const key=txt.toLowerCase(),p=byKey[key];
      // one link per name: two "Falling" pages must not each claim an occurrence
      if(!p||seen.has(key))return m;seen.add(key);
      return pre+'<a class="lnk ent" href="'+esc(p.url)+'" data-src="'+p.src+'" data-i="'+p.i+
        '" target="_blank" rel="noreferrer">'+txt+'</a>'});
  }).join('');
}
/* The Remaster renamed things; the old name is what a table still says. */
function formerly(h){
  const names=[].concat(h.legacy_name||[]).filter(Boolean);
  return names.length?'<p class="was">formerly '+esc(names.join(', '))+'</p>':'';
}
/* A wiki page is split into sections for retrieval ("Coffee › In Casmaron");
   the page is the entity a reader recognises. */
const pageOf=h=>isLore(h)?(h.url||h.name||'').split('#')[0]:'';
const pageName=h=>isLore(h)?(h.name||'').split(' › ')[0]:(h.name||'');
const sectionName=h=>(h.name||'').split(' › ').slice(1).join(' › ');
function tile(h,i,src,sections){
  src=src||'res';
  const p=parseHead(h),k=kindOf(h.category,h);
  const snippet=h.summary||firstLine(p.text);
  const title=sections?pageName(h):p.title;
  // Other sections of the same page that were retrieved: named, and openable
  // in place, but not tiles of their own.
  const secs=sections&&sections.length?'<p class="secs">also '+sections.map(j=>
    '<a class="lnk ent" href="'+esc(SHOWN[j].url)+'" data-src="'+src+'" data-i="'+j+'">'+
    esc(sectionName(SHOWN[j])||'the page')+'</a>').join(' · ')+'</p>':'';
  return '<div class="tile'+(p.rarity?' '+p.rarity:'')+'" style="--k:var(--k-'+k+')" data-i="'+i+
    '" data-src="'+src+'" role="button" tabindex="0" title="Open">'+kindBadge(h,p)+starBtn(h)+
    '<div class="thead"><span class="tname">'+esc(title)+'</span>'+glyphs(p.cost)+'</div>'+
    formerly(h)+
    (p.traits.length?'<div class="traits">'+p.traits.slice(0,4).map(t=>{
      const l=t.toLowerCase(),cls=RARITY.includes(l)?l:(SIZES.includes(l)?'size':'');
      return '<span class="trait'+(cls?' '+cls:'')+'">'+esc(t)+'</span>'}).join('')+'</div>':'')+
    '<p class="snip-t">'+esc(snippet)+'</p>'+secs+'<span class="more">open ↗</span></div>';
}
function cards(hits,question){
  if(!hits||!hits.length)return '';
  SHOWN=hits;
  const lore=hits.some(isLore),rules=hits.some(h=>!isLore(h));
  const where=lore&&rules?'the Archives of Nethys and PathfinderWiki':lore?'PathfinderWiki':'the Archives of Nethys';
  // The prompt puts the entry the question names last, where a small model
  // reads best; a person wants it first. Display order only -- data-i keeps
  // the real index, so citations and the popout still line up.
  const ql=(question||q.value||'').toLowerCase();
  const named=h=>h.name&&h.name.length>=4&&ql.includes(h.name.toLowerCase())?0:1;
  const order=hits.map((h,i)=>i).sort((a,b)=>named(hits[a])-named(hits[b])||a-b);
  // One tile per wiki page: "is there coffee?" retrieves the Coffee page's
  // lead and four of its sections, which are one thing to a reader. The lead
  // fronts the tile when it was retrieved, else the best-ranked section; the
  // rest are listed on the tile. The model still reads every section.
  const groups=new Map();
  for(const i of order){
    const key=pageOf(hits[i]);
    if(!key){groups.set('#'+i,{rep:i,rest:[]});continue}
    const g=groups.get(key);
    if(!g)groups.set(key,{rep:i,rest:[]});
    else if(!sectionName(hits[i])&&sectionName(hits[g.rep])){g.rest.unshift(g.rep);g.rep=i}
    else g.rest.push(i);
  }
  return '<p class="sources-h">Found proof · dug out of '+where+' — '+
    'poke one to read it</p><div class="tiles">'+
    [...groups.values()].map(g=>tile(hits[g.rep],g.rep,'res',pageOf(hits[g.rep])?g.rest:null)).join('')+'</div>';
}
const sheet=document.createElement('div');sheet.id='sheet';sheet.hidden=true;
document.body.appendChild(sheet);
function openEntry(i,src){
  src=src||'res';const list=LISTS[src]();
  const h=list[i];if(!h)return;
  const p=parseHead(h),k=kindOf(h.category,h);OPEN=i;OPEN_SRC=src;
  sheet.innerHTML='<div class="pop'+(p.rarity?' '+p.rarity:'')+'" style="--k:var(--k-'+k+')" '+
    'role="dialog" aria-modal="true" aria-label="'+esc(p.title)+'">'+
    '<button type="button" class="x" id="sheet-x" title="Close (Esc)" aria-label="Close">×</button>'+
    starBtn(h)+kindBadge(h,p)+statblock(h).replace('</div><div class="body',formerly(h)+'</div><div class="body')+
    '<div class="nav"><button type="button" id="sheet-prev"'+(i?'':' disabled')+'>← previous</button>'+
    '<a class="cite aon" href="'+esc(h.url)+'" target="_blank" rel="noreferrer">'+
      (isLore(h)?'See it on PathfinderWiki ↗':'See it in the Archives ↗')+'</a>'+
    '<button type="button" id="sheet-next"'+(i<list.length-1?'':' disabled')+'>next →</button></div></div>';
  sheet.hidden=false;lockScroll();
  EL('sheet-x').addEventListener('click',closeEntry);
  EL('sheet-prev').addEventListener('click',()=>openEntry(i-1,src));
  EL('sheet-next').addEventListener('click',()=>openEntry(i+1,src));
  sheet.querySelector('.star').addEventListener('click',e=>{e.stopPropagation();toggleFav(h)});
  EL('sheet-x').focus();
}
/* A cross-reference to an entry that is already on the page opens in place;
   anything else goes to the Archives in a new tab, as the link says. */
function followLink(e){
  const a=e.target.closest('a.lnk');if(!a)return;
  if(a.dataset.src){e.preventDefault();openEntry(+a.dataset.i,a.dataset.src);return}
  const url=a.getAttribute('href');
  for(const src of ['res','fav']){
    const i=LISTS[src]().findIndex(h=>h.url===url);
    if(i>=0){e.preventDefault();openEntry(i,src);return}
  }
}
sheet.addEventListener('click',followLink);
function closeEntry(){
  if(sheet.hidden)return;
  sheet.hidden=true;lockScroll();
  const t=document.querySelector('.tile[data-i="'+OPEN+'"][data-src="'+OPEN_SRC+'"]');
  if(t)t.focus();OPEN=-1;
}
sheet.addEventListener('click',e=>{if(e.target===sheet)closeEntry()});
function tileClick(e){
  const star=e.target.closest('.star');
  if(star){e.stopPropagation();const t=star.closest('.tile');
    toggleFav(LISTS[t.dataset.src]()[+t.dataset.i]);return}
  if(e.target.closest('a')){followLink(e);return}
  const t=e.target.closest('.tile');if(t)openEntry(+t.dataset.i,t.dataset.src);
}
function tileKey(e){
  if((e.key==='Enter'||e.key===' ')&&e.target.classList.contains('tile')){
    e.preventDefault();openEntry(+e.target.dataset.i,e.target.dataset.src)}
}
out.addEventListener('click',tileClick);out.addEventListener('keydown',tileKey);
EL('favs').addEventListener('click',tileClick);EL('favs').addEventListener('keydown',tileKey);
paintFavs();
document.addEventListener('keydown',e=>{
  if(sheet.hidden)return;
  if(e.key==='Escape'){e.preventDefault();closeEntry()}
  else if(e.key==='ArrowRight'&&OPEN<LISTS[OPEN_SRC]().length-1)openEntry(OPEN+1,OPEN_SRC);
  else if(e.key==='ArrowLeft'&&OPEN>0)openEntry(OPEN-1,OPEN_SRC);
},true);
</script>
<script>
/* ---------- settings ----------
   The point is to put this retrieval in front of a model you already have, so
   the answering client is per-request: the server keeps one loaded index and
   swaps only the HTTP client. Nothing here is stored server-side, and the API
   key travels in a header rather than the query string so it stays out of the
   URL — see the warning the panel shows, because this page has no auth.

   The embedder is deliberately not the same choice. Querying the index with a
   different encoder does not fail, it returns plausible and unrelated entries,
   so "this server's own" is the default and the alternative is fingerprinted
   against the index before the first question. */
const SDEF={backend:'ollama',base:'http://localhost:11434',model:'',key:'',
 k:8,rerank:true,ctx:1600,tokens:400,embed:'server',scope:'auto',followup:false};
let SET=Object.assign({},SDEF),SEEDED=false,LOCAL_ONLY=true,EMBED_MODEL='',AUTO_MODEL=false;
// Whether the index this server loaded carries PathfinderWiki. Without it the
// scope control, the lore examples and the trust line stay hidden: nothing to
// choose, and nothing to promise.
let LORE=false;
let STORED=false;
try{const raw=localStorage.getItem('kobold-settings');
    if(raw){SET=Object.assign({},SDEF,JSON.parse(raw));STORED=true}}catch(e){}
function saveSettings(){
  // Private windows throw on every access, not just on write.
  try{localStorage.setItem('kobold-settings',JSON.stringify(SET))}catch(e){}
}

function settingsQuery(extra){
  const p=new URLSearchParams(extra||{});
  p.set('backend',SET.backend);
  if(SET.base)p.set('base',SET.base);
  if(SET.model)p.set('model',SET.model);
  p.set('k',SET.k);p.set('rerank',SET.rerank?'1':'0');
  p.set('ctx',SET.ctx);p.set('tokens',SET.tokens);
  p.set('embed',SET.embed);
  if(LORE)p.set('scope',SET.scope||'auto');
  return p.toString();
}
function settingsHeaders(){
  // Only for the backend that has keys, and only when one was typed. A header
  // keeps it out of history, out of a Referer, and out of any future access log.
  return (SET.backend==='openai'&&SET.key)?{'X-Kobold-Key':SET.key}:{};
}

/* Measured on eval/holdout.jsonl, the 109 hand-written questions:
     9b + rerank    100/109   (on index-v2)
     4b + rerank     93/109   (on index-v2)
     4b, no rerank   95, 93, 92/109 over three identical runs on index-v1

   That last row is the important one. The pipeline is not deterministic across
   processes even at temperature 0, and one configuration re-run three times
   spans three items -- so a single-run difference of three is not a result. The
   4B scores the same with the reranker and without it, within that spread.

   Faster still drops the rerank, on the grounds that survive the noise: it
   removes a whole model call for no measurable quality cost. The claim that
   removing it *improves* the 4B did not survive repetition and is not made here.

   Better against Faster is about six items, which is larger than the spread and
   is probably real -- but it is a trade, not an upgrade, and not a precise one.
   The preset touches only the answering model and the retrieval knobs; backend,
   base URL and key are left where they are. */
const PRESETS={
 better:{model:'qwen3.5:9b',rerank:true,k:8,ctx:1600,tokens:400},
 faster:{model:'qwen3.5:4b',rerank:false,k:8,ctx:1600,tokens:400}};
const PRESET_NOTE={
 faster:'Recommended. Applies to the next question.',
 better:'A little more accurate, twice the wait. Downloaded once when first chosen.',
 custom:'Custom settings — see Expert mode.'};
function currentPreset(){
  for(const name in PRESETS){
    const p=PRESETS[name];
    // followup is deliberately not part of this: it is a mode, not a quality
    // knob, and turning it on must not make the preset read as "custom".
    if(SET.model===p.model&&!!SET.rerank===p.rerank&&+SET.k===p.k&&+SET.ctx===p.ctx&&
       +SET.tokens===p.tokens)return name;
  }
  return 'custom';
}

function writeForm(){
  EL('s-backend').value=SET.backend;EL('s-base').value=SET.base;
  EL('s-model').value=SET.model;EL('s-key').value=SET.key;
  EL('s-k').value=SET.k;EL('s-rerank').checked=!!SET.rerank;
  EL('s-ctx').value=SET.ctx;EL('s-tokens').value=SET.tokens;
  EL('s-embed').value=SET.embed;EL('s-followup').checked=!!SET.followup;
  EL('s-scope').value=SET.scope||'auto';
  paintSettings();
}
function readForm(){
  SET.backend=EL('s-backend').value;
  SET.base=EL('s-base').value.trim();
  SET.model=EL('s-model').value.trim();
  SET.key=EL('s-key').value;
  SET.k=+EL('s-k').value||SDEF.k;
  SET.rerank=EL('s-rerank').checked;
  SET.ctx=+EL('s-ctx').value||SDEF.ctx;
  SET.tokens=+EL('s-tokens').value||SDEF.tokens;
  SET.embed=EL('s-embed').value;
  SET.scope=EL('s-scope').value||'auto';
  SET.followup=EL('s-followup').checked;
  if(!SET.followup)endThread();
  saveSettings();paintSettings();paintThread();
}
function paintSettings(){
  // Presets are a view of the fields, not a stored mode: hand-edit one field and
  // the control has to stop claiming a preset is in effect.
  const now=currentPreset();
  EL('p-better').classList.toggle('on',now==='better');
  EL('p-faster').classList.toggle('on',now==='faster');
  EL('p-note').textContent=PRESET_NOTE[now];
  const openai=SET.backend==='openai';
  EL('s-keylabel').hidden=!openai;EL('s-key').hidden=!openai;
  const warn=EL('s-keywarn');warn.hidden=!openai;warn.className='note warnbox';
  warn.textContent=LOCAL_ONLY
    ? 'This page has no authentication. The key is kept in this browser and sent with each '
      +'request; the server forwards it and never writes it to disk or logs it. Only enter one '
      +'while serving on localhost.'
    : 'This server is NOT bound to localhost, and the page has no authentication — anyone who '
      +'can reach it can use your key. Do not enter one here.';
  EL('s-embednote').textContent=SET.embed==='backend'
    ? 'Must serve '+(EMBED_MODEL||'the index’s encoder')+'; checked against the index first.'
    : 'Leave it here unless this server has no local models.';
  EL('scope-wrap').hidden=!LORE;
  EL('s-scopenote').textContent={
    auto:'The kobold reads each question and decides. When it is not sure, it sticks to the rules.',
    rules:'What every number in the docs was measured on. Lore questions will come back thin.',
    lore:'Every question sees the wiki too. A rules question may pick up a lore paragraph.'}[SET.scope||'auto'];
}
function seedFromServer(health){
  // The panel shows what `kobold serve` was actually launched with rather than a
  // second copy of the defaults, so --llm-model on the command line is visible.
  if(SEEDED||!health)return;
  SEEDED=true;LOCAL_ONLY=health.local_only!==false;
  const d=health.defaults||{};EMBED_MODEL=d.embed_model||'';
  if(d.backend)SDEF.backend=d.backend;
  if(d.base_url)SDEF.base=d.base_url;
  if(d.llm_model)SDEF.model=d.llm_model;
  if(d.k)SDEF.k=d.k;
  if(d.rerank!==undefined)SDEF.rerank=!!d.rerank;
  REPORT_URL=d.report_url||'';INDEX_TAG=d.index_tag||'';
  AUTO_MODEL=!!d.auto_model;
  if(d.context_chars)SDEF.ctx=d.context_chars;
  if(d.answer_tokens)SDEF.tokens=d.answer_tokens;
  LORE=!!d.lore;if(d.scope)SDEF.scope=d.scope;
  if(LORE){
    const c=d.corpus||{};
    if(c.aon&&c.pathfinderwiki)EL('ob-corpus').textContent='the Archives of Nethys and PathfinderWiki — '+
      c.aon.toLocaleString()+' rules entries and '+c.pathfinderwiki.toLocaleString()+' entries of Golarion lore —';
    EL('trust-lore-h').hidden=false;EL('trust-lore').hidden=false;
  }
  if(!STORED)SET=Object.assign({},SDEF);
  else for(const key in SDEF)if(SET[key]===''||SET[key]==null)SET[key]=SDEF[key];
  writeForm();
}

function fillModels(names){
  const dl=EL('s-models');dl.textContent='';
  for(const name of names||[]){const o=document.createElement('option');o.value=name;
    dl.appendChild(o)}
}
async function probeModels(quiet){
  const t=EL('tstat');
  if(!quiet){t.className='wait';t.textContent='testing…'}
  let d;
  try{
    d=await (await fetch('/api/test?'+settingsQuery(),{headers:settingsHeaders()})).json();
  }catch(e){
    if(!quiet){t.className='bad';t.textContent=String(e)}
    return;
  }
  fillModels(d.models);
  if(quiet)return;
  if(!d.ok){t.className='bad';t.textContent=d.error||'could not reach it';return}
  const n=(d.models||[]).length;
  const lines=[n+' model'+(n===1?'':'s')+' at '+d.base_url];
  lines.push((d.llm_ok?'✓ ':'✗ ')+d.llm_model+
    (d.llm_ok?' is available':' is not served here'));
  lines.push(d.remote_embedder
    ? (d.embed_ok?'✓ ':'✗ ')+d.embed_model+' (embedder)'+
      (d.embed_ok?' is available':' is not served here — retrieval would be refused')
    : '✓ embedder unchanged: this server’s own '+d.embed_model);
  const bad=!d.llm_ok||(d.remote_embedder&&!d.embed_ok);
  // textContent throughout: every string above the join comes from the backend.
  t.className=bad?'bad':'ok';t.textContent=lines.join('\n');
}

async function copySnip(id,btn){
  const text=EL(id).textContent,was=btn.textContent;
  let ok=false;
  try{await navigator.clipboard.writeText(text);ok=true}
  catch(e){
    // clipboard is unavailable over plain http to a LAN address, which is
    // exactly the --host 0.0.0.0 case this snippet is most wanted in.
    const ta=document.createElement('textarea');ta.value=text;
    ta.style.position='fixed';ta.style.opacity='0';document.body.appendChild(ta);
    ta.select();try{ok=document.execCommand('copy')}catch(e2){}
    ta.remove();
  }
  btn.textContent=ok?'Copied':'Select it manually';
  setTimeout(()=>{btn.textContent=was},1600);
}

const GEAR='<svg viewBox="0 0 16 16"><path d="M8 5.2A2.8 2.8 0 108 10.8 2.8 2.8 0 008 5.2zm0 1.5a1.3 1.3 0 110 2.6 1.3 1.3 0 010-2.6z"/><path d="M6.9.8h2.2l.3 1.7 1.2.5 1.4-1 1.5 1.5-1 1.4.5 1.2 1.7.3v2.2l-1.7.3-.5 1.2 1 1.4-1.5 1.5-1.4-1-1.2.5-.3 1.7H6.9l-.3-1.7-1.2-.5-1.4 1-1.5-1.5 1-1.4-.5-1.2L.8 9.1V6.9l1.7-.3.5-1.2-1-1.4L3.5 2.5l1.4 1 1.2-.5z" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/></svg>';
const gear=EL('gear'),panel=EL('settings-wrap');
gear.innerHTML=GEAR+'<span>Settings</span>';
function lockScroll(){document.body.style.overflow=
  [...document.querySelectorAll('.ov,#sheet,#onboard')].some(el=>!el.hidden)?'hidden':''}
gear.addEventListener('click',()=>{
  const open=panel.hidden;panel.hidden=!open;gear.setAttribute('aria-expanded',String(open));
  if(open){EL('history-wrap').hidden=true;EL('hist').setAttribute('aria-expanded','false')}
  lockScroll();
  // Fill the model list the first time it is opened, not on every page load:
  // it is one request to the backend and nobody who never opens this needs it.
  if(open&&!EL('s-models').children.length)probeModels(true);
});
for(const id of ['s-backend','s-base','s-model','s-key','s-k','s-rerank','s-ctx','s-tokens',
                 's-embed','s-scope','s-followup'])
  EL(id).addEventListener('change',readForm);
for(const name of ['better','faster'])
  // Writing the values into the fields rather than holding a hidden mode: the
  // point is that you can see what the preset did and then hand-tune from it.
  EL('p-'+name).addEventListener('click',()=>{
    Object.assign(SET,PRESETS[name]);saveSettings();writeForm();ensureModel(SET.model);
  });
/* ---------- expert mode ---------- */
let EXPERT=false;try{EXPERT=localStorage.getItem('kobold-expert')==='1'}catch(e){}
function paintExpert(){EL('expert').hidden=!EXPERT;EL('s-expert').checked=EXPERT}
EL('s-expert').addEventListener('change',()=>{EXPERT=EL('s-expert').checked;
  try{localStorage.setItem('kobold-expert',EXPERT?'1':'0')}catch(e){};paintExpert();
  const tm=document.querySelector('.answer .foot .timing:not(.fun)');
  if(tm&&CURRENT&&CURRENT.timings)tm.outerHTML=stamp(CURRENT.timings,false)});
paintExpert();
/* ---------- fetching a model the first time it is chosen ----------
   Ollama pulls on request, not on use: picking Better on a machine that only
   has the 4B would otherwise fail on the first question. The pull is asked of
   the server (which only knows the two shipped models) and its progress goes
   in the status line. */
let PULLING=false;
async function ensureModel(model){
  if(PULLING||SET.backend!=='ollama'||!model)return;
  let d;
  try{d=await (await fetch('/api/test?'+settingsQuery(),{headers:settingsHeaders()})).json()}
  catch(e){return}
  if(!d.ok||d.llm_ok)return;
  PULLING=true;st.hidden=false;st.className='';st.querySelector('.dot').classList.add('pulse');
  stt.textContent='downloading '+model+'…';enable(false);
  try{
    const res=await fetch('/api/pull?model='+encodeURIComponent(model));
    const reader=res.body.getReader(),dec=new TextDecoder();let buf='';
    for(;;){
      const {done,value}=await reader.read();if(done)break;
      buf+=dec.decode(value,{stream:true});
      const parts=buf.split('\n\n');buf=parts.pop();
      for(const line of parts){
        if(!line.startsWith('data: '))continue;
        const ev=JSON.parse(line.slice(6));
        if(ev.event==='progress'){
          const pct=ev.total?Math.round(100*ev.completed/ev.total):null;
          stt.textContent='downloading '+model+(pct!==null?' — '+pct+'%':' — '+ev.status);
        }else if(ev.event==='done'){st.className='ready';stt.textContent=model+' is ready';
          st.querySelector('.dot').classList.remove('pulse');setTimeout(()=>{st.hidden=true},2500);
        }else if(ev.event==='error'){st.className='bad';stt.textContent='could not download '+model+': '+ev.error;
          st.querySelector('.dot').classList.remove('pulse')}
      }
    }
  }catch(e){st.className='bad';stt.textContent='could not download '+model+': '+e}
  PULLING=false;if(ready)enable(true);
}
EL('s-test').addEventListener('click',()=>{readForm();probeModels(false)});
EL('s-reset').addEventListener('click',()=>{
  SET=Object.assign({},SDEF);saveSettings();writeForm();
  EL('tstat').textContent='';EL('tstat').className='';
});
EL('c-desktop').addEventListener('click',e=>copySnip('snip-desktop',e.currentTarget));
EL('c-code').addEventListener('click',e=>copySnip('snip-code',e.currentTarget));
writeForm();
</script>
<script>
let ready=false;
async function poll(){
  try{
    const d=await (await fetch('/api/health')).json();
    seedFromServer(d);
    stt.textContent=d.detail||d.state;
    st.className=d.state==='ready'?'ready':(d.state==='error'?'bad':'');
    st.querySelector('.dot').classList.toggle('pulse',d.state!=='ready'&&d.state!=='error');
    if(d.state==='ready'&&!ready){
      ready=true;enable(true);
      setTimeout(()=>{st.hidden=true},2500);
      if(LINKED_Q){q.value=LINKED_Q;go('ask').then(()=>{
        const n=parseInt(PARAMS.get('open')||'',10);
        if(!isNaN(n)&&SHOWN[n])openEntry(n,'res')})}
      return;
    }
    if(d.state==='error'){enable(false);return}
  }catch(e){stt.textContent='server not responding'}
  setTimeout(poll,700);
}
poll();

/* ---------- the thread ----------
   One turn, held in the page and sent with the next question. The server keeps
   nothing: it is handed the previous question, the previous answer and the
   standalone form the last condense produced, and that is the whole
   conversation as far as it is concerned.

   Only the last turn. Sending two would double the prompt for a gain nobody
   here has measured, and the standalone form already carries the subject
   forward — turn three condenses against a turn-two question that names what
   it is about. See notes/followup-design.md. */
let LAST=null;   // {q, answer, standalone} of the turn a follow-up follows
function endThread(){LAST=null;paintThread()}
function paintThread(){
  const el=EL('thread'),on=SET.followup&&LAST;
  el.hidden=!on;
  if(!on)return;
  el.innerHTML='Following on from “'+esc((LAST.standalone||LAST.q).slice(0,90))+
    '” · <button type="button" class="link" id="thread-end">start fresh</button>';
  EL('thread-end').addEventListener('click',endThread);
}
function threadParams(){
  // Nothing is sent unless the switch is on and there is a turn to send.
  if(!SET.followup||!LAST)return {};
  // 900 is HISTORY_CHARS in app.py. The server truncates to it anyway; doing it
  // here too keeps a long answer out of the query string rather than sending
  // three kilobytes for the server to throw away.
  return {followup:'1',prev_q:LAST.q,prev_a:(LAST.answer||'').slice(0,900),
          prev_std:LAST.standalone||''};
}

/* ---------- history ----------
   Kept in this browser: a table has one laptop, and what it asked last week is
   worth more than a login. Each record carries the answer, the entries and the
   timings, so replaying one draws exactly what was drawn the first time and
   costs no model call. Bounded, and trimmed further if the browser says no. */
const HKEY='kobold-history',HMAX=80;
let HIST=[];
try{HIST=JSON.parse(localStorage.getItem(HKEY)||'[]');if(!Array.isArray(HIST))HIST=[]}catch(e){HIST=[]}
function saveHist(){
  for(let tries=0;tries<6;tries++){
    try{localStorage.setItem(HKEY,JSON.stringify(HIST));return}
    catch(e){HIST=HIST.slice(0,Math.max(0,Math.floor(HIST.length/2)))}
  }
}
const norm=t=>t.trim().toLowerCase().replace(/\s+/g,' ');
function findHist(text,mode){
  const key=norm(text),model=SET.model||SDEF.model;
  return HIST.find(r=>r.mode===mode&&norm(r.q)===key&&r.model===model);
}
function addHist(rec){
  HIST=HIST.filter(r=>!(r.mode===rec.mode&&norm(r.q)===norm(rec.q)&&r.model===rec.model));
  HIST.unshift(rec);
  if(HIST.length>HMAX)HIST.length=HMAX;
  saveHist();paintHist();
}
function ago(ts){
  const s=Math.max(0,(Date.now()-ts)/1000);
  if(s<60)return 'just now';
  if(s<3600)return Math.round(s/60)+' min ago';
  if(s<86400)return Math.round(s/3600)+' h ago';
  const d=Math.round(s/86400);return d===1?'yesterday':d+' days ago';
}
function histRow(r){
  return '<li><button type="button" class="qq" data-id="'+r.id+'">'+esc(r.q)+'</button>'+
    '<span class="m">'+(r.mode==='ask'?'asked':'looked up')+' · '+ago(r.ts)+'</span>'+
    '<button type="button" class="x" data-del="'+r.id+'" title="Forget this one">×</button></li>';
}
function paintHist(){
  const list=EL('h-list'),n=HIST.length;
  EL('hist').innerHTML='<span>History</span>'+(n?'<b>'+n+'</b>':'');
  list.innerHTML=n?HIST.map(histRow).join(''):'';
  list.insertAdjacentHTML('beforebegin','');
  let empty=document.querySelector('#history .empty');
  if(!n){if(!empty){list.insertAdjacentHTML('afterend','<p class="empty">Nothing yet. The kobold is waiting.</p>')}}
  else if(empty)empty.remove();
  const rw=EL('recent-wrap');rw.hidden=!n;
  EL('recent').innerHTML=HIST.slice(0,5).map(histRow).join('');
}
for(const id of ['h-list','recent'])EL(id).addEventListener('click',e=>{
  const b=e.target.closest('button');if(!b)return;
  if(b.dataset.del){HIST=HIST.filter(r=>r.id!==b.dataset.del);saveHist();paintHist();return}
  const r=HIST.find(x=>x.id===b.dataset.id);if(!r)return;
  q.value=r.q;replay(r);
});
EL('h-clear').addEventListener('click',()=>{
  if(!HIST.length||confirm('Make the kobold forget all '+HIST.length+' questions kept in this browser?')){
    HIST=[];saveHist();paintHist();}
});
const histBtn=EL('hist'),histPanel=EL('history-wrap');
histBtn.addEventListener('click',()=>{
  const open=histPanel.hidden;histPanel.hidden=!open;
  histBtn.setAttribute('aria-expanded',String(open));
  if(open){panel.hidden=true;gear.setAttribute('aria-expanded','false')}
  lockScroll();
});
function closeOverlays(){
  for(const el of document.querySelectorAll('.ov'))el.hidden=true;
  gear.setAttribute('aria-expanded','false');histBtn.setAttribute('aria-expanded','false');
  lockScroll();
}
document.addEventListener('click',e=>{
  const x=e.target.closest('[data-close]');
  if(x){closeOverlays();return}
  if(e.target.classList&&e.target.classList.contains('ov'))closeOverlays();
});

/* ---------- empty state ---------- */
/* A different handful each visit: some from a hand-written pool that covers
   the shapes the evaluation cares about, some made from entries drawn at
   random from the index, so the corpus itself suggests what to ask. */
const POOL=[
 'How does Treat Wounds work?','What level is Battle Medicine?',
 'Is there a feat that makes falling less dangerous?','What can players do during exploration?',
 'Was Magic Missile renamed?','What does the off-guard condition do?',
 'How much damage does Fireball do at 5th rank?','An ogre has grabbed my monk. What can she do?',
 'Can I Raise a Shield as a free action?','What happens on a critical failure to Recall Knowledge?',
 'How does flanking work?','How long does Sudden Charge take?',
 'What is the DC to Escape a grab?','Can a rogue sneak attack with a ranged weapon?',
 'How does the frightened condition go away?','What does Quick Repair do?',
 'How far can I Stride with a speed of 25?','Is there an archetype for being a pirate?',
 'How does concealment affect attacks?','How do I Treat Poison?',
 'What does the Reactive Strike reaction do?','How does heroic recovery work?',
 'What is the range of a longbow?','How does Demoralize work?',
 'How much does a healing potion heal?','What does the manipulate trait mean?',
 'How do persistent damage checks work?','What does a critical hit do with a deadly weapon?',
 'How does Hustle work in exploration?','What does the invisible condition do?',
 'How many actions does it take to draw a weapon?','Can I Aid an ally from across the room?',
 'What does Cat Fall do?','How does Sneak differ from Hide?',
 'What are the rules for falling damage?','How does Wounded interact with Dying?'];
const LOOKUPS=['grabbed','flat-footed','Force Barrage','off-guard','Sudden Charge','Lay on Hands'];
// Offered only when the index carries PathfinderWiki.
const LORE_POOL=['Who rules Cheliax?','What happened when Aroden died?','Where is Sandpoint?',
 'Who is the Whispering Tyrant?','What is the Pathfinder Society?','What is the Worldwound?',
 'Which gods passed the Test of the Starstone?','What is Absalom known for?',
 'Who are the Hellknights?','What is Numeria famous for?','Who is Baba Yaga to Irrisen?',
 'What is the Starstone?','Which god judges the dead?','What was Thassilon?'];
const MADE={
 feat:n=>['What level is '+n+'?','What does the '+n+' feat do?'],
 spell:n=>['How does the spell '+n+' work?','What rank is '+n+'?'],
 action:n=>['How does '+n+' work?','What does '+n+' do?'],
 condition:n=>['What does the '+n+' condition do?'],
 equipment:n=>['What does '+n+' cost?','What does '+n+' do?'],
 weapon:n=>['What are the traits of '+n+'?','How much damage does '+n+' deal?'],
 creature:n=>['How dangerous is '+n+'?','What level is '+n+'?'],
 'class feature':n=>['Which class gets '+n+'?']};
const pick=(arr,n)=>{const a=arr.slice();for(let i=a.length-1;i>0;i--){const j=Math.random()*(i+1)|0;
  [a[i],a[j]]=[a[j],a[i]]}return a.slice(0,n)};
let EXAMPLES=[];
async function drawExamples(){
  let made=[];
  try{
    const d=await (await fetch('/api/examples')).json();
    for(const e of d.entries||[]){
      const f=MADE[(e.category||'').replace('-',' ')];if(!f)continue;
      made.push(pick(f(e.name),1)[0]);
    }
  }catch(e){}
  EXAMPLES=(LORE?pick(pick(POOL,3).concat(pick(made,2)).concat(pick(LORE_POOL,2)),6)
               :pick(pick(POOL,4).concat(pick(made,3)),6)).map(t=>[t,'ask']);
  EXAMPLES.push([pick(LOOKUPS,1)[0],'search']);
  EL('examples').innerHTML=EXAMPLES.map(([t,m],i)=>
    '<button type="button" class="chip" data-i="'+i+'">'+esc(t)+
    (m==='search'?'<span class="m">look up</span>':'')+'</button>').join('')+
    '<button type="button" class="chip again" id="reroll" title="Other ideas">↻</button>';
}
EL('examples').addEventListener('click',e=>{
  if(e.target.closest('#reroll')){drawExamples();return}
  const b=e.target.closest('.chip');if(!b)return;
  const [t,m]=EXAMPLES[+b.dataset.i];q.value=t;go(m);
});
drawExamples();
function showHome(on){EL('home').hidden=!on}
/* The die and the title are the way back to a blank page: nothing on screen
   but the box, the suggestions and what you have asked before. */
function goHome(){
  closeOverlays();closeEntry();clearInterval(timer);rolling(false);
  out.innerHTML='';q.value='';hpos=-1;CURRENT=null;endThread();showHome(true);
  window.scrollTo({top:0});if(ready)q.focus();
}
EL('home-link').addEventListener('click',e=>{e.preventDefault();goHome()});
paintHist();showHome(true);

/* ---------- onboarding ---------- */
const ob=EL('onboard');
function openHelp(){closeOverlays();ob.hidden=false;lockScroll();
  const now=currentPreset();if(now!=='custom'){OB_CHOICE=now;
    for(const c of EL('ob-choices').querySelectorAll('.choice'))c.classList.toggle('on',c.dataset.choice===now)}EL('help').setAttribute('aria-expanded','true');
  EL('ob-go').focus()}
function closeHelp(){ob.hidden=true;lockScroll();EL('help').setAttribute('aria-expanded','false');
  try{localStorage.setItem('kobold-onboarded','1')}catch(e){}
  if(ready)q.focus()}
let OB_CHOICE='faster',OB_TOUCHED=false;
EL('ob-choices').addEventListener('click',e=>{
  const b=e.target.closest('.choice');if(!b)return;
  OB_CHOICE=b.dataset.choice;OB_TOUCHED=true;
  for(const c of EL('ob-choices').querySelectorAll('.choice'))c.classList.toggle('on',c===b);
});
EL('ob-go').addEventListener('click',()=>{
  // First visit, or a choice made on this visit: apply it. Reopening the card
  // with ? and closing it again must not undo a hand-tuned setting.
  if(!seen||OB_TOUCHED){Object.assign(SET,PRESETS[OB_CHOICE]);saveSettings();writeForm();
    ensureModel(SET.model)}
  seen=true;OB_TOUCHED=false;closeHelp();
});
EL('ob-settings').addEventListener('click',()=>{closeHelp();
  EXPERT=true;try{localStorage.setItem('kobold-expert','1')}catch(e){};paintExpert();
  if(panel.hidden)gear.click()});
EL('help').addEventListener('click',()=>ob.hidden?openHelp():closeHelp());
ob.addEventListener('click',e=>{if(e.target===ob)closeHelp()});
let seen=false;try{seen=!!localStorage.getItem('kobold-onboarded')}catch(e){}
/* ---------- a link can carry a question ----------
   /?q=How%20does%20Treat%20Wounds%20work asks it once the models are up, so
   an answer can be shared as a link and the screenshots can be made by hand.
   theme=dark|light sets the theme; open=N opens entry N when the answer is done. */
const PARAMS=new URLSearchParams(location.search);
const LINKED_Q=(PARAMS.get('q')||'').trim();
if(PARAMS.get('theme')&&THEMES.includes(PARAMS.get('theme'))){theme=PARAMS.get('theme');applyTheme()}
if(!seen&&!LINKED_Q)openHelp();

/* ---------- asking ---------- */
const LINES={
 search:['Digging through the Archives','Sniffing along the shelves','Thumbing through the index'],
 find:['The kobold scurries off','Digging through the Archives','Rolling Recall Knowledge','Finding the right page',
       'Asking the librarian','Checking the errata','Pondering the orb','Waking the archivist'],
 write:['The kobold is writing','Pondering the orb','Questioning the dead','Consulting the oracle',
        'Leafing through the Player Core','Arguing with the GM','Sharpening the quill',
        'Casting Read Aura','Counting the action icons','Rolling a secret check'],
 fun:['The kobold is thinking','Pondering the orb','Questioning the dead','Consulting the oracle','Arguing with the GM',
      'Leafing through the Player Core','Sharpening the quill','Casting Read Aura',
      'Rolling a secret check','Bribing the librarian','Checking the errata',
      'Asking Nethys nicely','Reading the fine print']};
/* ---------- the text arrives in Erathian ----------
   Streamed text is shown the moment it lands, typeset in the Erathian
   alphabet and nearly transparent. Over the next 2.4 s each character fades
   in and, at its own moment, changes into the page's own face -- so the
   newest line reads as a foreign script clearing into words, and nothing
   ever pops into place. Text older than the window is rendered as markdown
   as before, so what has settled never flickers. Cuts fall on spaces so a
   markdown marker is never split. */
const SETTLE_MS=2400,FADE_MS=2400;
const REDUCED=matchMedia('(prefers-reduced-motion: reduce)').matches;
let ARRIVALS=[];   // [time, answer length at that time]
function noteArrival(len){ARRIVALS.push([Date.now(),len]);if(ARRIVALS.length>400)ARRIVALS.splice(0,200)}
function stableLength(answer,age){
  const cutoff=Date.now()-age;let n=0;
  for(const [t,len] of ARRIVALS){if(t<=cutoff)n=len;else break}
  return n;
}
// A small integer mix (xorshift-style): stable per position, no visible period.
const hash=i=>{let x=(i+0x9e3779b9)>>>0;x^=x>>>16;x=Math.imul(x,0x85ebca6b)>>>0;x^=x>>>13;
  x=Math.imul(x,0xc2b2ae35)>>>0;x^=x>>>16;return (x>>>0)/4294967296};
function charTimes(){
  const t=[];let from=0;
  for(const [time,len] of ARRIVALS){for(let i=from;i<len;i++)t[i]=time;from=Math.max(from,len)}
  return t;
}
function streamed(answer){
  // The Source line and anything after it is citation, not prose. It is not
  // written out character by character: it stays hidden while the answer
  // streams and is added whole by the final paint, as the chips it becomes.
  const srcMatch=answer.match(/(^|\n)\s*Source:/i);
  const srcAt=srcMatch?srcMatch.index:Infinity;
  const cut=Math.min(answer.length,srcAt);
  const prose=answer.slice(0,cut);
  if(REDUCED||!ARRIVALS.length)return md(prose,true);
  const times=charTimes(),now=Date.now();
  let old=Math.min(stableLength(answer,SETTLE_MS),cut);
  while(old>0&&old<cut&&!/\s/.test(answer[old]))old--;
  if(old>=cut)return md(prose,true);
  const settled=md(answer.slice(0,old),true);
  // Runs of characters that share a look become one span: the look is the
  // face (Erathian or settled) and the opacity in twentieths.
  let tail='',key=null;
  for(let i=old;i<cut;i++){
    const ch=answer[i],age=now-(times[i]||now);
    const op=Math.min(20,Math.round(20*age/FADE_MS)),f=Math.min(1,age/SETTLE_MS);
    const er=!/\s/.test(ch)&&f<.25+.75*hash(i);
    const k=(er?'e':'s')+op;
    if(k!==key){if(key!==null)tail+='</span>';
      tail+='<span class="'+(er?'er':'st')+'" style="opacity:'+(op/20).toFixed(2)+'">';key=k}
    tail+=esc(ch);
  }
  if(key!==null)tail+='</span>';
  const m=settled.match(/((?:<\/(?:p|li|ul|b|i)>\s*)+)$/);
  return m?settled.slice(0,m.index)+tail+m[1]:settled+tail;
}
let funTimer=null;
function funStart(){
  const t0=Date.now(),pool=LINES.fun.slice().sort(()=>Math.random()-.5);
  // The footer line starts with the first token; before that the body's own
  // waiting line is the only one, so nothing is said twice.
  const foot=document.querySelector('.answer .foot');
  if(foot&&!document.getElementById('fun'))foot.innerHTML=stamp({},true);
  clearInterval(funTimer);
  funTimer=setInterval(()=>{const el=document.getElementById('fun');
    if(el)el.textContent=pool[Math.floor((Date.now()-t0)/2600)%pool.length]+'…';
    if(typeof settle==='function')settle()},160);
}
let settle=null;   // set by the running ask: repaints so the runes keep settling
function funStop(){clearInterval(funTimer);funTimer=null}
let timer=null;
function rolling(on){d20.classList.toggle('rolling',on)}
function busy(kind){
  const t0=Date.now(),pool=LINES[kind];
  out.innerHTML='<p class="spin" id="busy"></p>';
  const el=EL('busy');
  const tick=()=>{const label=pool[Math.floor((Date.now()-t0)/2600)%pool.length];
    el.textContent=label+'… '+((Date.now()-t0)/1000).toFixed(1)+'s'};
  tick();clearInterval(timer);timer=setInterval(tick,100);rolling(true);
}
function stamp(t,live){
  // While writing: something to read. Done: the total. Expert mode: the
  // per-stage split, which is the answer to "why is this slow on my laptop".
  if(live)return '<span class="timing fun" id="fun">'+LINES.fun[0]+'…</span>';
  if(!t||t.total===undefined)return '<span class="timing"></span>';
  if(!EXPERT)return '<span class="timing">'+t.total.toFixed(1)+' s</span>';
  const parts=[];
  for(const k of ['rewrite','retrieve','rerank','first_token','answer'])
    if(t[k]!==undefined)parts.push(k.replace('_',' ')+' '+t[k].toFixed(1)+'s');
  return '<span class="timing">'+parts.join(' · ')+' · total '+t.total.toFixed(1)+'s</span>';
}
function setCites(hits){
  CITES=hits||[];AON_LABEL={};CITES.forEach(h=>{if(h.url)AON_LABEL[h.url]=h.name});
}
function answerCard(answer,timings,live){
  return '<div class="card answer">'+
    '<div class="body">'+(answer?md(answer,true)+(live?'<span class="caret"></span>':'')
      :'<span class="spin" id="pend">'+LINES.write[0]+'…</span>')+'</div>'+
    '<div class="foot">'+(answer||!live?stamp(timings||{},live):'')+
    (live?'':'<button type="button" class="report" id="report-btn">Wrong? Tell the kobold</button>')+
    '</div></div>';
}
/* ---------- reporting a wrong answer ----------
   The one place this page sends anything anywhere: a form, filled in by hand,
   posted on Send to the report URL the server was started with. Without a
   report URL it opens a pre-filled GitHub issue or copies the report. What is
   sent is exactly what the form shows. */
let REPORT_URL='',INDEX_TAG='';
let CURRENT=null;   // {q, answer, sources, model} of the answer on screen
function reportBody(correction,source){
  return {question:CURRENT.q,answer:CURRENT.answer,correction,source_url:source||'',
    sources:(CURRENT.sources||[]).map(h=>({name:h.name,url:h.url})),
    model:CURRENT.model||'',index_tag:INDEX_TAG,app:'The Klever Kobold'};
}
function reportMarkdown(b){
  return '**Question:** '+b.question+'\n\n**Answer given** ('+b.model+', '+b.index_tag+'):\n\n'+
    b.answer+'\n\n**Correction:**\n\n'+b.correction+'\n\n'+(b.source_url?'Source: '+b.source_url+'\n\n':'')+
    'Retrieved: '+b.sources.map(s=>s.name).join(', ')+'\n';
}
function openReport(){
  if(!CURRENT)return;
  const wrap=EL('report-wrap');wrap.hidden=false;lockScroll();
  EL('r-q').textContent=CURRENT.q;EL('r-a').textContent=CURRENT.answer;
  EL('r-fix').value='';EL('r-src').value='';EL('r-stat').textContent='';
  EL('r-send').hidden=!REPORT_URL;EL('r-issue').hidden=!!REPORT_URL;
  EL('r-where').textContent=REPORT_URL
    ?'Sent to '+REPORT_URL.replace(/^https?:\/\//,'')+' — the question, the answer, your correction and the names of the entries used. Nothing else.'
    :'No report server is configured, so this opens a GitHub issue with the report filled in, or copies it.';
  EL('r-fix').focus();
}
async function sendReport(){
  const fix=EL('r-fix').value.trim();if(!fix){EL('r-fix').focus();return}
  const b=reportBody(fix,EL('r-src').value.trim()),st=EL('r-stat');
  st.className='wait';st.textContent='sending…';
  try{
    const res=await fetch(REPORT_URL+'/report',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(b)});
    const d=await res.json();
    if(!res.ok||!d.ok){st.className='bad';st.textContent=d.error||('server said '+res.status);return}
    st.className='ok';st.textContent='The kobold has it. Thank you — report #'+d.id+'.';
    setTimeout(closeOverlays,1400);
  }catch(e){st.className='bad';st.textContent='could not send: '+e}
}
function issueReport(){
  const fix=EL('r-fix').value.trim();if(!fix){EL('r-fix').focus();return}
  const b=reportBody(fix,EL('r-src').value.trim());
  const u='https://github.com/DeastinY/klever-kobold/issues/new?title='+
    encodeURIComponent('Wrong answer: '+b.question.slice(0,80))+'&body='+encodeURIComponent(reportMarkdown(b));
  window.open(u,'_blank','noreferrer');
}
async function copyReport(){
  const fix=EL('r-fix').value.trim();if(!fix){EL('r-fix').focus();return}
  const text=reportMarkdown(reportBody(fix,EL('r-src').value.trim())),st=EL('r-stat');
  try{await navigator.clipboard.writeText(text);st.className='ok';st.textContent='Copied.'}
  catch(e){st.className='bad';st.textContent='Clipboard unavailable — select the text above.'}
}
out.addEventListener('click',e=>{if(e.target.closest('#report-btn'))openReport()});
EL('r-send').addEventListener('click',sendReport);
EL('r-issue').addEventListener('click',issueReport);
EL('r-copy').addEventListener('click',copyReport);
function fromBanner(r){
  return '<div class="from"><span><span class="ok">✓</span> The kobold remembers this one — '+
    (r.mode==='ask'?'asked ':'looked up ')+ago(r.ts)+(r.model?' with '+esc(r.model):'')+
    ', no model call.</span><button type="button" id="again">'+
    (r.mode==='ask'?'Ask again':'Look up again')+'</button></div>';
}
function replay(r){
  // Picking a question out of the history is starting somewhere else, not
  // continuing from here.
  endThread();
  showHome(false);setCites(r.hits);EXTRA=r.mentions||[];
  CURRENT=r.mode==='ask'?{q:r.q,answer:r.answer,sources:r.hits,model:r.model,timings:r.timings}:null;
  out.innerHTML=fromBanner(r)+(r.mode==='ask'?answerCard(r.answer,r.timings,false):'')+
    cards(r.hits,r.q);
  const b=out.querySelector('.answer .body');if(b)b.innerHTML=linkNames(b.innerHTML);
  EL('again').addEventListener('click',()=>go(r.mode,true));
  closeOverlays();
  window.scrollTo({top:0,behavior:'smooth'});
}
async function search(text){
  busy('search');
  const d=await (await fetch('/api/search?'+settingsQuery(Object.assign({q:text},threadParams())),
    {headers:settingsHeaders()})).json();
  clearInterval(timer);rolling(false);
  if(d.error){out.innerHTML='<p class="err">'+esc(d.error)+'</p>';return}
  setCites(d.hits);
  out.innerHTML=(d.standalone?asked(d.standalone):'')+
    (cards(d.hits)||'<p class="spin">Nothing matched.</p>');
  // A look-up has no answer to carry, but it is still a turn: the next
  // follow-up should be read against what was just looked up.
  if(SET.followup){LAST={q:text,answer:'',standalone:d.standalone||''};paintThread()}
  addHist({id:String(Date.now()),q:text,mode:'search',ts:Date.now(),
    model:SET.model||SDEF.model,hits:d.hits||[],timings:{}});
}
/* What the kobold decided it was being asked. Shown whenever it differs from
   what was typed, because when a follow-up goes wrong this is almost always
   where it went wrong, and the fix is to see it and rephrase. */
function asked(std){
  return '<p class="from"><span>Read as “'+esc(std)+'”</span></p>';
}
async function ask(text){
  busy('find');
  const res=await fetch('/api/ask?'+settingsQuery(Object.assign({q:text},threadParams())),
    {headers:settingsHeaders()});
  if(!res.ok){
    // A refusal (still loading, or a rejected configuration) is plain JSON, not
    // an event stream, and reading it as one would spin forever.
    clearInterval(timer);rolling(false);
    let msg='';try{msg=(await res.json()).error}catch(e){}
    out.innerHTML='<p class="err">'+esc(msg||('server said '+res.status))+'</p>';return;
  }
  const reader=res.body.getReader(),dec=new TextDecoder();
  let buf='',answer='',timings={},hits=[],srcHtml='',started=false,queued=false,standalone='';
  ARRIVALS=[];settle=()=>{if(!queued&&started){queued=true;setTimeout(()=>{queued=false;paint()},0)}};
  // Two containers: the entries are drawn once, and each token repaints only
  // the answer's body. Replacing the whole output per token tore the tiles out
  // from under a click.
  // The containers are made when the sources arrive: until then the busy
  // ticker owns the output and would overwrite them.
  const frame=()=>{if(!EL('ans'))out.innerHTML='<div id="std"></div><div id="ans"></div>'+
    '<div id="src"></div>'};
  const paint=(live=true,caret=true)=>{
    frame();const ans=EL('ans');
    if(!ans.firstChild){ans.innerHTML=answerCard(answer,timings,live);
      if(live&&answer)ans.querySelector('.body').innerHTML=streamed(answer)+'<span class="caret"></span>';return}
    const body=ans.querySelector('.body');
    body.innerHTML=answer?(live?streamed(answer)+(caret?'<span class="caret"></span>':''):linkNames(md(answer,true)))
      :'<span class="spin" id="pend">'+LINES.write[0]+'…</span>';
    // The footer's line begins in the same paint that removes the body's.
    if(live&&answer&&!document.getElementById('fun'))funStart();
    if(!live){
      ans.querySelector('.foot').innerHTML=stamp(timings||{},false)+
        '<button type="button" class="report" id="report-btn">Wrong? Tell the kobold</button>';
    }
  };
  const pending=()=>{const t0=Date.now();clearInterval(timer);
    timer=setInterval(()=>{const el=document.getElementById('pend');
      if(el){const l=LINES.write[Math.floor((Date.now()-t0)/2600)%LINES.write.length];
        el.textContent=l+'… '+((Date.now()-t0)/1000).toFixed(1)+'s'}},100)};
  for(;;){
    const {done,value}=await reader.read(); if(done)break;
    buf+=dec.decode(value,{stream:true});
    const parts=buf.split('\n\n'); buf=parts.pop();
    for(const line of parts){
      if(!line.startsWith('data: '))continue;
      const ev=JSON.parse(line.slice(6));
      if(ev.event==='sources'){
        clearInterval(timer);timings=ev.timings;hits=ev.hits||[];srcHtml=cards(hits);
        standalone=ev.standalone||'';
        setCites(hits);frame();EL('src').innerHTML=srcHtml;
        if(standalone)EL('std').innerHTML=asked(standalone);
        paint();pending();
      }else if(ev.event==='token'){
        if(!started){started=true;clearInterval(timer)}
        answer+=ev.text;noteArrival(answer.length);
        // One repaint per frame, however many chunks arrived: markdown over the
        // whole answer per token is what made the page stutter while writing.
        if(!queued){queued=true;const run=()=>{queued=false;paint()};
          // A hidden tab gets no animation frames; a timer keeps it current.
          if(document.hidden)setTimeout(run,150);else requestAnimationFrame(run)}
      }else if(ev.event==='done'){clearInterval(timer);funStop();settle=null;rolling(false);timings=ev.timings;
        EXTRA=ev.mentions||[];answer=answer.trimEnd();
        CURRENT={q:text,answer,sources:hits,model:SET.model||SDEF.model,timings};
        if(SET.followup){LAST={q:text,answer,standalone};paintThread()}
        // Let the last characters finish fading before the final render, or
        // the end of every answer snaps from half-faded to solid.
        await new Promise(res=>{const tick=setInterval(()=>{
          if(stableLength(answer,SETTLE_MS)>=answer.length||REDUCED){clearInterval(tick);res();return}
          paint(true,false)},100)});
        paint(false);
        addHist({id:String(Date.now()),q:text,mode:'ask',ts:Date.now(),
          model:SET.model||SDEF.model,answer,hits,timings,mentions:EXTRA});
      }else if(ev.event==='error'){clearInterval(timer);funStop();settle=null;rolling(false);
        out.innerHTML='<p class="err">'+esc(ev.error)+'</p>';return}
    }
  }
  clearInterval(timer);funStop();settle=null;rolling(false);
}
async function go(mode,force){
  const text=q.value.trim(); if(!text)return;
  // Replaying a stored answer is only free because the same words mean the
  // same thing. Inside a thread they do not -- "and untrained?" is a different
  // question after Treat Wounds than after Battle Medicine -- so a follow-up
  // always goes to the model.
  const cached=!force&&!(SET.followup&&LAST)&&findHist(text,mode);
  if(cached){replay(cached);return}
  if(!ready)return;
  showHome(false);enable(false);
  try{ mode==='ask'?await ask(text):await search(text) }
  catch(e){clearInterval(timer);rolling(false);
    out.innerHTML='<p class="err">'+esc(String(e))+'</p>'}
  enable(true);
}
document.getElementById('f').addEventListener('submit',e=>{e.preventDefault();go('ask')});
look.addEventListener('click',()=>go('search'));
let hpos=-1;   // where ↑/↓ are in the history, from the input
q.addEventListener('keydown',e=>{
  if(e.key==='Enter'&&e.shiftKey){e.preventDefault();go('search');return}
  if(e.key==='ArrowUp'&&HIST.length){e.preventDefault();
    hpos=Math.min(hpos+1,HIST.length-1);q.value=HIST[hpos].q;
    q.setSelectionRange(q.value.length,q.value.length);return}
  if(e.key==='ArrowDown'&&hpos>=0){e.preventDefault();
    hpos-=1;q.value=hpos<0?'':HIST[hpos].q;return}
  if(e.key.length===1)hpos=-1;
});
document.addEventListener('keydown',e=>{
  if(e.key==='Escape'){if(!ob.hidden)closeHelp();else closeOverlays();return}
  if(!sheet.hidden)return;
  if(document.activeElement===q||e.metaKey||e.ctrlKey||e.altKey)return;
  if(e.key==='/'){e.preventDefault();q.focus();q.select()}
  else if(e.key==='?'){e.preventDefault();ob.hidden?openHelp():closeHelp()}
});
</script></body></html>"""

PAGE = _PAGE.replace("__ICON_FONT__", _FONT).replace("__ERATHIAN__", _ERATHIAN)
