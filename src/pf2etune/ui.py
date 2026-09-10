"""The single page served by ``pf2e serve``.

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

PAGE = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PF2e Rules</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Cpath d='M16 2 3 9.5v13L16 30l13-7.5v-13z' fill='%238a1b2e'/%3E%3Cpath d='M16 2v10.5L3 9.5M16 12.5 29 9.5M16 12.5 8 22.5h16L16 12.5M3 22.5l5 0M29 22.5l-5 0M8 22.5 16 30l8-7.5' fill='none' stroke='%23fff' stroke-width='1.3' stroke-linejoin='round'/%3E%3Ctext x='16' y='21.5' font-size='8' font-family='Georgia,serif' font-weight='700' text-anchor='middle' fill='%23fff'%3E20%3C/text%3E%3C/svg%3E">
<style>
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
.acts{display:inline-flex;gap:.1rem;align-items:center;vertical-align:-.08em}
.acts svg{width:.82em;height:.82em;fill:var(--ink)}
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
.body .clip{max-height:16rem;overflow:auto}
.deg{display:block;margin-top:.3rem}
.deg .field{color:var(--ok)}
.deg.f .field{color:var(--fail)}
.deg.cf .field{color:var(--crit-fail)}

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
.caret{display:inline-block;width:.45em;height:1em;vertical-align:text-bottom;
 background:var(--warn);animation:blink 1s steps(2,start) infinite}
@keyframes blink{to{visibility:hidden}}
@media(prefers-reduced-motion:reduce){.caret,.dot.pulse{animation:none}}

/* ---- a little more life ----
   The d20 in the header rolls while a question is in flight; the busy line
   speaks in the game's own terms. Neither touches the caution flag on the
   answer, which is the one bit of this page that must stay plain. */
.d20{width:1.35rem;height:1.35rem;flex:none;align-self:center;color:var(--accent)}
.d20 svg{width:100%;height:100%;display:block}
.d20.rolling svg{animation:roll 1.4s cubic-bezier(.4,.1,.3,1) infinite}
@keyframes roll{0%{transform:rotate(0)}70%{transform:rotate(360deg)}100%{transform:rotate(360deg)}}
@media(prefers-reduced-motion:reduce){.d20.rolling svg{animation:none}}
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
.ob .row{display:flex;gap:.5rem;align-items:center;flex-wrap:wrap;margin-top:.6rem}
.ob .row .note{margin:0;flex:1;grid-column:auto}
</style></head><body><div class="wrap">
<header><span class="d20" id="d20" aria-hidden="true"></span>
<h1>Pathfinder 2e rules <small>— Archives of Nethys, offline</small></h1>
<button id="hist" title="Questions you have asked" aria-expanded="false" aria-controls="history"></button>
<button id="gear" title="Settings" aria-expanded="false" aria-controls="settings"></button>
<button id="help" title="How this works" aria-expanded="false">?</button>
<button id="theme" title="Theme"></button></header>
<div id="status"><span class="dot pulse"></span><span id="statustext">starting…</span></div>
<form id="f"><input id="q" placeholder="ask what happens, name it, or describe it…" autofocus
 autocomplete="off" disabled><button class="primary" id="askbtn" disabled>Ask</button>
<button id="lookbtn" type="button" disabled>Look up</button></form>
<p class="hint"><kbd>Enter</kbd> asks and writes an answer from the rules — good for straight
lookups, unreliable for rule interactions; check the citation. <kbd>Shift</kbd>+<kbd>Enter</kbd>
just shows the entries. <kbd>↑</kbd> brings back an earlier question.</p>

<div id="history" hidden>
<div class="top"><p class="set-h">Asked before</p>
 <button type="button" id="h-clear">Forget all</button></div>
<p class="note" style="margin:0 0 .5rem">Answers are kept in this browser, so asking the same
thing again is instant — until you press <b>Ask again</b>.</p>
<ul class="recent" id="h-list"></ul>
</div>

<div id="onboard" hidden>
<div class="ob" role="dialog" aria-modal="true" aria-labelledby="ob-h">
<h2 id="ob-h"><span class="d20" aria-hidden="true"></span>Well met, adventurer.</h2>
<p class="lead">This is a Pathfinder 2e rules reference that runs on this machine, searches the
Archives of Nethys, and cites its sources. No account, no cloud, no dice tax.</p>
<ol>
 <li><b>Type a question and press Enter.</b> It finds the relevant entries and writes a short
  answer with links back to the Archives.</li>
 <li><b>Shift+Enter shows only the entries</b> — faster, and often all you need.</li>
 <li><b>Everything you ask is kept in this browser.</b> The history button brings it back
  instantly; the same question twice costs nothing.</li>
</ol>
<div class="trust">
 <span class="ok">Trust it</span><span>“What level is Battle Medicine?” · “How does Treat Wounds work?”</span>
 <span class="so">Mostly</span><span>“Is there a feat that makes falling less dangerous?”</span>
 <span class="no">Read the rule</span><span>“Does X interact with Y?” — it finds the rule fast; you settle the argument.</span>
</div>
<div class="row"><button class="primary" type="button" id="ob-go">Roll for initiative</button>
<p class="note">Press <kbd>?</kbd> any time to see this again.</p></div>
</div></div>

<div id="home" hidden>
<p class="tryh">Try one</p>
<div class="chips" id="examples"></div>
<div id="recent-wrap" hidden><p class="tryh">Asked before</p><ul class="recent" id="recent"></ul></div>
</div>

<div id="settings" hidden>
<p class="set-h">Preset</p>
<div class="presets">
 <button type="button" class="preset" id="p-better"><b>Better</b>
  <span>qwen3.5:9b · 100/109 on the holdout · ~6.6 GB</span></button>
 <button type="button" class="preset" id="p-faster"><b>Faster</b>
  <span>qwen3.5:4b · 93/109 on the holdout · ~3.4 GB</span></button>
</div>
<p class="note" id="p-note"></p>

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
<div class="grid" style="margin-top:.6rem">
 <label for="s-embed">Embedder</label>
 <select id="s-embed">
  <option value="server">This server's — verified against the index</option>
  <option value="backend">The backend above — checked before use</option>
 </select>
 <p class="note" id="s-embednote"></p>
</div>
<div class="pair" style="margin-top:.7rem"><button id="s-reset" type="button">Reset to
 defaults</button><span class="note" style="grid-column:auto;margin:0">Applies to the next
 question. Kept in this browser only.</span></div>

<p class="set-h">Use it from Claude Desktop or Claude Code</p>
<p class="tools">A stdio MCP server exposing <code>pf2e_ask</code> (the whole pipeline) and
<code>pf2e_search</code> (the excerpts, for the calling model to read itself — the better
choice when the caller is a strong model).</p>
<div class="pair" style="margin-top:.5rem"><b style="font-size:.8rem;color:var(--soft)">Claude
 Desktop</b><button id="c-desktop" type="button">Copy</button></div>
<pre class="snip" id="snip-desktop">{
  "mcpServers": {
    "pf2e": {
      "command": "pf2e",
      "args": ["mcp"]
    }
  }
}</pre>
<div class="pair" style="margin-top:.6rem"><b style="font-size:.8rem;color:var(--soft)">Claude
 Code</b><button id="c-code" type="button">Copy</button></div>
<pre class="snip" id="snip-code">claude mcp add pf2e -- pf2e mcp</pre>
<p class="tools">Not installed as a tool? Use the interpreter that runs this server:
<code>"command": "/path/to/.venv/bin/python", "args": ["-m", "pf2etune", "mcp"]</code>.
Both accept <code>--index</code> and <code>--ollama</code> before <code>mcp</code>. These
settings do not travel to it — the MCP server uses its own command-line flags.</p>
</div>

<div id="out"></div>
</div><script>
const out=document.getElementById('out'),q=document.getElementById('q'),
 st=document.getElementById('status'),stt=document.getElementById('statustext'),
 look=document.getElementById('lookbtn'),askBtn=document.getElementById('askbtn'),
 themeBtn=document.getElementById('theme'),d20=document.getElementById('d20');
const D20='<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M16 2 3 9.5v13L16 30l13-7.5v-13z" fill="currentColor" opacity=".18"/><path d="M16 2 3 9.5v13L16 30l13-7.5v-13zM16 2v10.5L3 9.5M16 12.5 29 9.5M16 12.5 8 22.5h16L16 12.5M3 22.5h5M29 22.5h-5M8 22.5 16 30l8-7.5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><text x="16" y="21" font-size="7.5" font-family="Georgia,serif" font-weight="700" text-anchor="middle" fill="currentColor">20</text></svg>';
d20.innerHTML=D20;document.querySelector('.ob .d20').innerHTML=D20;

/* ---------- theme: auto / light / dark, remembered per browser ---------- */
const ICON={
 auto:'<svg viewBox="0 0 16 16"><path d="M8 1a7 7 0 100 14A7 7 0 008 1zm0 1.6v10.8a5.4 5.4 0 010-10.8z"/></svg>',
 light:'<svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="3.2"/><path d="M8 .8v2.1M8 13.1v2.1M.8 8h2.1M13.1 8h2.1M2.9 2.9l1.5 1.5M11.6 11.6l1.5 1.5M13.1 2.9l-1.5 1.5M4.4 11.6l-1.5 1.5" stroke="currentColor" stroke-width="1.3" fill="none" stroke-linecap="round"/></svg>',
 dark:'<svg viewBox="0 0 16 16"><path d="M13.4 10.2A5.8 5.8 0 015.8 2.6a6 6 0 107.6 7.6z"/></svg>'};
const THEMES=['auto','light','dark'];
let theme=localStorage.getItem('pf2e-theme')||'auto';
function applyTheme(){
  if(theme==='auto')document.documentElement.removeAttribute('data-theme');
  else document.documentElement.setAttribute('data-theme',theme);
  themeBtn.innerHTML=ICON[theme]+'<span>'+theme[0].toUpperCase()+theme.slice(1)+'</span>';
  try{localStorage.setItem('pf2e-theme',theme)}catch(e){}
}
themeBtn.addEventListener('click',()=>{theme=THEMES[(THEMES.indexOf(theme)+1)%3];applyTheme()});
applyTheme();

function esc(s){return (s||'').replace(/[&<>"]/g,c=>(
 {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function enable(on){q.disabled=!on;look.disabled=!on;askBtn.disabled=!on;
 if(on&&!q.value)q.focus()}

/* ---------- action glyphs ----------
   Drawn here rather than loaded as Paizo's action font: the page has to render
   offline, and the shapes are simple. Single/two/three actions are pips; a
   reaction is the arrow that turns back on itself; a free action is hollow. */
const PIP='<svg viewBox="0 0 10 10" aria-hidden="true"><path d="M5 .6l4.4 4.4L5 9.4.6 5z"/></svg>';
const PIP_O='<svg viewBox="0 0 10 10" aria-hidden="true"><path d="M5 .6l4.4 4.4L5 9.4.6 5z" fill="none" stroke="currentColor" stroke-width="1.4"/></svg>';
const REACT='<svg viewBox="0 0 10 10" aria-hidden="true"><path d="M2 8.6V6.2a3.4 3.4 0 013.4-3.4h2.2" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/><path d="M5.6 1l2.6 1.8-2.6 1.8z"/></svg>';
const COST={'single action':PIP,'two actions':PIP+PIP,'three actions':PIP+PIP+PIP,
 'reaction':REACT,'free action':PIP_O};
function glyphs(label){
  const key=(label||'').toLowerCase().trim();
  if(COST[key])return '<span class="acts" title="'+esc(label)+'">'+COST[key]+'</span>';
  // ranges like "Single Action or Two Actions" -- show both, joined
  const parts=key.split(/\s+(?:or|to)\s+/).map(p=>COST[p]).filter(Boolean);
  if(parts.length>1)return '<span class="acts" title="'+esc(label)+'">'+
    parts.join('<span style="opacity:.5;padding:0 .1em">–</span>')+'</span>';
  return '';
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
  t=t.replace(/\*\*(.+?)\*\*/g,'<b>$1</b>')
     // require a non-space next to each marker, or the "*   *" between list
     // items becomes an italic run of spaces
     .replace(/(^|[^*])\*(?=\S)([^*\n]*[^*\s])\*/g,'$1<i>$2</i>');
  // Bare URLs are linked before anything else emits a tag -- run this pass over
  // HTML and it happily rewrites the href of a link made a line earlier.
  t=t.replace(/https?:\/\/[^\s<)\]]+/g,u=>{
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
  return t;
}
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
        (/^Failure/.test(f[1])?'deg f':'deg')):'';
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
    let t=head[1].replace(/\n/g,' ');
    // An action with no cost is written "[]" in the corpus; drop the empty brackets.
    t=t.replace(/\[\s*\]/,'');
    const c=t.match(/\[([^\]]+)\]/); if(c){cost=c[1];t=t.replace(c[0],'')}
    const k=t.match(/\(([^)]+)\)\s*$/); if(k){kind=k[1];t=t.replace(k[0],'')}
    title=t.trim()||h.name;
  }
  let traits=[];
  const tr=text.match(/^\*\*Traits\*\*\s*([^\n]+)\n?/m);
  if(tr){traits=tr[1].split(',').map(s=>s.trim()).filter(Boolean);
         text=text.replace(tr[0],'')}
  const rank=kind||(h.level!==null&&h.level!==undefined?'Level '+h.level:'');

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
function cards(hits){
  if(!hits||!hits.length)return '';
  return '<p class="sources-h">Entries · Archives of Nethys</p>'+hits.map(statblock).join('');
}
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
const EL=id=>document.getElementById(id);
const SDEF={backend:'ollama',base:'http://localhost:11434',model:'',key:'',
 k:8,rerank:true,ctx:1600,tokens:400,embed:'server'};
let SET=Object.assign({},SDEF),SEEDED=false,LOCAL_ONLY=true,EMBED_MODEL='';
let STORED=false;
try{const raw=localStorage.getItem('pf2e-settings');
    if(raw){SET=Object.assign({},SDEF,JSON.parse(raw));STORED=true}}catch(e){}
function saveSettings(){
  // Private windows throw on every access, not just on write.
  try{localStorage.setItem('pf2e-settings',JSON.stringify(SET))}catch(e){}
}

function settingsQuery(extra){
  const p=new URLSearchParams(extra||{});
  p.set('backend',SET.backend);
  if(SET.base)p.set('base',SET.base);
  if(SET.model)p.set('model',SET.model);
  p.set('k',SET.k);p.set('rerank',SET.rerank?'1':'0');
  p.set('ctx',SET.ctx);p.set('tokens',SET.tokens);
  p.set('embed',SET.embed);
  return p.toString();
}
function settingsHeaders(){
  // Only for the backend that has keys, and only when one was typed. A header
  // keeps it out of history, out of a Referer, and out of any future access log.
  return (SET.backend==='openai'&&SET.key)?{'X-PF2E-Key':SET.key}:{};
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
 better:'The shipped configuration — 100/109 on the hand-written holdout.',
 faster:'93/109 on the same holdout, against 100 for Better: seven items worse, and that '
  +'gap is the trade. Rerank is off because it removes a whole model call at no measurable '
  +'cost — the 4B scores the same with it and without it, once the same configuration is run '
  +'more than once. Half the weights should mean roughly twice the decode rate; that is '
  +'projected from model size, not a figure measured here.',
 custom:'Custom — the fields below match neither preset.'};
function currentPreset(){
  for(const name in PRESETS){
    const p=PRESETS[name];
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
  EL('s-embed').value=SET.embed;
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
  saveSettings();paintSettings();
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
    ? 'The backend above must serve '+(EMBED_MODEL||'the index’s encoder')
      +'. It is fingerprinted against the index before the first question and refused on a '
      +'mismatch — a wrong encoder returns plausible, unrelated entries rather than an error.'
    : 'Retrieval keeps the encoder this server verified against the index, so changing the '
      +'answering model cannot change what is retrieved. Leave it here unless this server has '
      +'no local models.';
}
function seedFromServer(health){
  // The panel shows what `pf2e serve` was actually launched with rather than a
  // second copy of the defaults, so --llm-model on the command line is visible.
  if(SEEDED||!health)return;
  SEEDED=true;LOCAL_ONLY=health.local_only!==false;
  const d=health.defaults||{};EMBED_MODEL=d.embed_model||'';
  if(d.backend)SDEF.backend=d.backend;
  if(d.base_url)SDEF.base=d.base_url;
  if(d.llm_model)SDEF.model=d.llm_model;
  if(d.k)SDEF.k=d.k;
  if(d.context_chars)SDEF.ctx=d.context_chars;
  if(d.answer_tokens)SDEF.tokens=d.answer_tokens;
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
const gear=EL('gear'),panel=EL('settings');
gear.innerHTML=GEAR+'<span>Settings</span>';
gear.addEventListener('click',()=>{
  const open=panel.hidden;panel.hidden=!open;gear.setAttribute('aria-expanded',String(open));
  // Fill the model list the first time it is opened, not on every page load:
  // it is one request to the backend and nobody who never opens this needs it.
  if(open&&!EL('s-models').children.length)probeModels(true);
});
for(const id of ['s-backend','s-base','s-model','s-key','s-k','s-rerank','s-ctx','s-tokens',
                 's-embed'])
  EL(id).addEventListener('change',readForm);
for(const name of ['better','faster'])
  // Writing the values into the fields rather than holding a hidden mode: the
  // point is that you can see what the preset did and then hand-tune from it.
  EL('p-'+name).addEventListener('click',()=>{
    Object.assign(SET,PRESETS[name]);saveSettings();writeForm();
  });
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
      return;
    }
    if(d.state==='error'){enable(false);return}
  }catch(e){stt.textContent='server not responding'}
  setTimeout(poll,700);
}
poll();

/* ---------- history ----------
   Kept in this browser: a table has one laptop, and what it asked last week is
   worth more than a login. Each record carries the answer, the entries and the
   timings, so replaying one draws exactly what was drawn the first time and
   costs no model call. Bounded, and trimmed further if the browser says no. */
const HKEY='pf2e-history',HMAX=80;
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
  if(!n){if(!empty){list.insertAdjacentHTML('afterend','<p class="empty">Nothing yet. The first question goes here.</p>')}}
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
  if(!HIST.length||confirm('Forget all '+HIST.length+' questions kept in this browser?')){
    HIST=[];saveHist();paintHist();}
});
const histBtn=EL('hist'),histPanel=EL('history');
histBtn.addEventListener('click',()=>{
  const open=histPanel.hidden;histPanel.hidden=!open;
  histBtn.setAttribute('aria-expanded',String(open));
  if(open){panel.hidden=true;gear.setAttribute('aria-expanded','false')}
});

/* ---------- empty state ---------- */
const EXAMPLES=[
 ['How does Treat Wounds work?','ask'],
 ['What level is Battle Medicine?','ask'],
 ['Is there a feat that makes falling less dangerous?','ask'],
 ['What can players do during exploration?','ask'],
 ['Was Magic Missile renamed?','ask'],
 ['grabbed','search']];
EL('examples').innerHTML=EXAMPLES.map(([t,m],i)=>
  '<button type="button" class="chip" data-i="'+i+'">'+esc(t)+
  (m==='search'?'<span class="m">look up</span>':'')+'</button>').join('');
EL('examples').addEventListener('click',e=>{
  const b=e.target.closest('.chip');if(!b)return;
  const [t,m]=EXAMPLES[+b.dataset.i];q.value=t;go(m);
});
function showHome(on){EL('home').hidden=!on}
paintHist();showHome(true);

/* ---------- onboarding ---------- */
const ob=EL('onboard');
function openHelp(){ob.hidden=false;EL('help').setAttribute('aria-expanded','true');
  EL('ob-go').focus()}
function closeHelp(){ob.hidden=true;EL('help').setAttribute('aria-expanded','false');
  try{localStorage.setItem('pf2e-onboarded','1')}catch(e){}
  if(ready)q.focus()}
EL('ob-go').addEventListener('click',closeHelp);
EL('help').addEventListener('click',()=>ob.hidden?openHelp():closeHelp());
ob.addEventListener('click',e=>{if(e.target===ob)closeHelp()});
let seen=false;try{seen=!!localStorage.getItem('pf2e-onboarded')}catch(e){}
if(!seen)openHelp();

/* ---------- asking ---------- */
const LINES={
 search:['Consulting the Archives','Thumbing through the index','Searching the stacks'],
 find:['Consulting the Archives','Rolling Recall Knowledge','Finding the right page',
       'Asking the librarian','Checking the errata'],
 write:['The scribe is writing','Putting it in plain words','Citing the sources']};
let timer=null;
function rolling(on){d20.classList.toggle('rolling',on)}
function busy(kind){
  const t0=Date.now(),pool=LINES[kind];
  const tick=()=>{const label=pool[Math.floor((Date.now()-t0)/2600)%pool.length];
    out.innerHTML='<p class="spin">'+label+'… '+((Date.now()-t0)/1000).toFixed(1)+'s</p>'};
  tick();clearInterval(timer);timer=setInterval(tick,100);rolling(true);
}
function stamp(t){
  // The per-stage split is the answer to "why is this slow on my laptop".
  const parts=[];
  for(const k of ['rewrite','retrieve','rerank','first_token','answer'])
    if(t[k]!==undefined)parts.push(k.replace('_',' ')+' '+t[k].toFixed(1)+'s');
  if(!parts.length)return '';
  return '<div class="timing">'+parts.join(' · ')+
    (t.total?' · total '+t.total.toFixed(1)+'s':'')+'</div>';
}
function setCites(hits){
  CITES=hits||[];AON_LABEL={};CITES.forEach(h=>{if(h.url)AON_LABEL[h.url]=h.name});
}
function answerCard(answer,timings,live){
  return '<div class="card answer"><div class="flag"><span>⚠</span>'+
    '<span>Generated from the entries below — verify against the citations, '+
    'especially for rule interactions.</span></div>'+
    '<div class="body">'+(answer?md(answer,true)+(live?'<span class="caret"></span>':'')
      :'<span class="spin" id="pend">'+LINES.write[0]+'…</span>')+'</div>'+
    stamp(timings||{})+'</div>';
}
function fromBanner(r){
  return '<div class="from"><span><span class="ok">✓</span> From your history — '+
    (r.mode==='ask'?'asked ':'looked up ')+ago(r.ts)+(r.model?' with '+esc(r.model):'')+
    ', no model call.</span><button type="button" id="again">'+
    (r.mode==='ask'?'Ask again':'Look up again')+'</button></div>';
}
function replay(r){
  showHome(false);setCites(r.hits);
  out.innerHTML=fromBanner(r)+(r.mode==='ask'?answerCard(r.answer,r.timings,false):'')+
    cards(r.hits);
  EL('again').addEventListener('click',()=>go(r.mode,true));
  histPanel.hidden=true;histBtn.setAttribute('aria-expanded','false');
  window.scrollTo({top:0,behavior:'smooth'});
}
async function search(text){
  busy('search');
  const d=await (await fetch('/api/search?'+settingsQuery({q:text}),
    {headers:settingsHeaders()})).json();
  clearInterval(timer);rolling(false);
  if(d.error){out.innerHTML='<p class="err">'+esc(d.error)+'</p>';return}
  setCites(d.hits);
  out.innerHTML=cards(d.hits)||'<p class="spin">Nothing matched.</p>';
  addHist({id:String(Date.now()),q:text,mode:'search',ts:Date.now(),
    model:SET.model||SDEF.model,hits:d.hits||[],timings:{}});
}
async function ask(text){
  busy('find');
  const res=await fetch('/api/ask?'+settingsQuery({q:text}),{headers:settingsHeaders()});
  if(!res.ok){
    // A refusal (still loading, or a rejected configuration) is plain JSON, not
    // an event stream, and reading it as one would spin forever.
    clearInterval(timer);rolling(false);
    let msg='';try{msg=(await res.json()).error}catch(e){}
    out.innerHTML='<p class="err">'+esc(msg||('server said '+res.status))+'</p>';return;
  }
  const reader=res.body.getReader(),dec=new TextDecoder();
  let buf='',answer='',timings={},hits=[],srcHtml='',started=false;
  const paint=()=>{out.innerHTML=answerCard(answer,timings,true)+srcHtml};
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
        setCites(hits);paint();pending();
      }else if(ev.event==='token'){
        if(!started){started=true;clearInterval(timer)}
        answer+=ev.text;paint();
      }else if(ev.event==='done'){clearInterval(timer);rolling(false);timings=ev.timings;
        answer=answer.trimEnd();out.innerHTML=answerCard(answer,timings,false)+srcHtml;
        addHist({id:String(Date.now()),q:text,mode:'ask',ts:Date.now(),
          model:SET.model||SDEF.model,answer,hits,timings});
      }else if(ev.event==='error'){clearInterval(timer);rolling(false);
        out.innerHTML='<p class="err">'+esc(ev.error)+'</p>';return}
    }
  }
  clearInterval(timer);rolling(false);
}
async function go(mode,force){
  const text=q.value.trim(); if(!text)return;
  const cached=!force&&findHist(text,mode);
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
  if(e.key==='Escape'){if(!ob.hidden)closeHelp();return}
  if(document.activeElement===q||e.metaKey||e.ctrlKey||e.altKey)return;
  if(e.key==='/'){e.preventDefault();q.focus();q.select()}
  else if(e.key==='?'){e.preventDefault();ob.hidden?openHelp():closeHelp()}
});
</script></body></html>"""
