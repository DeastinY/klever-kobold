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
<style>
/* Light is the base palette; the two blocks after it redefine only the tokens,
   so an un-stamped document (the default "system" setting) still resolves. */
:root{color-scheme:light;
--bg:#f7f4f1;--card:#fffdfb;--ink:#1c1719;--soft:#4a4341;--muted:#7b716d;
--line:#e0d8d2;--rule:#cdc2ba;--accent:#8a1b2e;--accent-ink:#fff;
--warn:#8a5a12;--ok:#2f6b4f;--fail:#a3421f;--crit-fail:#9c1f1f;--chip:#efe9e4}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){color-scheme:dark;
--bg:#141113;--card:#1d191b;--ink:#ece7e5;--soft:#c6bebb;--muted:#988d89;
--line:#332c2e;--rule:#3f3639;--accent:#e0788a;--accent-ink:#1a1113;
--warn:#d8a557;--ok:#74b894;--fail:#dd8f6b;--crit-fail:#e0736f;--chip:#282124}}
:root[data-theme=dark]{color-scheme:dark;
--bg:#141113;--card:#1d191b;--ink:#ece7e5;--soft:#c6bebb;--muted:#988d89;
--line:#332c2e;--rule:#3f3639;--accent:#e0788a;--accent-ink:#1a1113;
--warn:#d8a557;--ok:#74b894;--fail:#dd8f6b;--crit-fail:#e0736f;--chip:#282124}

*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
 font:15px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:58rem;margin:0 auto;padding:1.25rem 1rem 4rem}
header{display:flex;align-items:baseline;gap:.6rem;margin-bottom:.75rem}
h1{font-size:1.05rem;margin:0;font-weight:600;
 font-family:ui-serif,Georgia,"Iowan Old Style",serif}
h1 small{color:var(--muted);font-weight:400;font-family:inherit}
#theme{margin-left:auto;padding:.35rem .65rem;font-size:.8rem;border:1px solid var(--line);
 background:var(--card);color:var(--soft);border-radius:6px;cursor:pointer;
 display:flex;align-items:center;gap:.35rem}
#theme svg{width:.85rem;height:.85rem;fill:currentColor}
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
.err{color:var(--accent)}
.timing{color:var(--muted);font-size:.72rem;margin-top:.7rem;
 font-variant-numeric:tabular-nums}
.caret{display:inline-block;width:.45em;height:1em;vertical-align:text-bottom;
 background:var(--warn);animation:blink 1s steps(2,start) infinite}
@keyframes blink{to{visibility:hidden}}
@media(prefers-reduced-motion:reduce){.caret,.dot.pulse{animation:none}}
</style></head><body><div class="wrap">
<header><h1>Pathfinder 2e rules <small>— Archives of Nethys, offline</small></h1>
<button id="theme" title="Theme"></button></header>
<div id="status"><span class="dot pulse"></span><span id="statustext">starting…</span></div>
<form id="f"><input id="q" placeholder="describe it, name it, or ask what happens…" autofocus
 autocomplete="off" disabled><button class="primary" id="lookbtn" disabled>Look up</button>
<button id="askbtn" type="button" disabled>Ask</button></form>
<p class="hint">Look up shows the rules entries themselves. <b>Ask</b> writes an answer from them —
good for straight lookups, unreliable for rule interactions. Check the citation.</p>
<div id="out"></div>
</div><script>
const out=document.getElementById('out'),q=document.getElementById('q'),
 st=document.getElementById('status'),stt=document.getElementById('statustext'),
 look=document.getElementById('lookbtn'),askBtn=document.getElementById('askbtn'),
 themeBtn=document.getElementById('theme');

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
let ready=false;
async function poll(){
  try{
    const d=await (await fetch('/api/health')).json();
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

let timer=null;
function busy(label){
  const t0=Date.now();
  const tick=()=>{out.innerHTML='<p class="spin">'+label+' — '+
    ((Date.now()-t0)/1000).toFixed(1)+'s</p>'};
  tick();clearInterval(timer);timer=setInterval(tick,100);
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
async function search(text){
  busy('searching');
  const d=await (await fetch('/api/search?q='+encodeURIComponent(text))).json();
  clearInterval(timer);
  out.innerHTML=d.error?'<p class="err">'+esc(d.error)+'</p>'
    :(cards(d.hits)||'<p class="spin">Nothing matched.</p>');
}
async function ask(text){
  busy('finding the relevant rules');
  const res=await fetch('/api/ask?q='+encodeURIComponent(text));
  const reader=res.body.getReader(),dec=new TextDecoder();
  let buf='',answer='',timings={},srcHtml='',started=false;
  const paint=()=>{
    out.innerHTML='<div class="card answer"><div class="flag"><span>⚠</span>'+
      '<span>Generated from the entries below — verify against the citations, '+
      'especially for rule interactions.</span></div>'+
      '<div class="body">'+(answer?md(answer,true)+'<span class="caret"></span>'
        :'<span class="spin" id="pend">writing the answer…</span>')+'</div>'+
      stamp(timings)+'</div>'+srcHtml;
  };
  const pending=()=>{const t0=Date.now();clearInterval(timer);
    timer=setInterval(()=>{const el=document.getElementById('pend');
      if(el)el.textContent='writing the answer — '+((Date.now()-t0)/1000).toFixed(1)+'s'},100)};
  for(;;){
    const {done,value}=await reader.read(); if(done)break;
    buf+=dec.decode(value,{stream:true});
    const parts=buf.split('\n\n'); buf=parts.pop();
    for(const line of parts){
      if(!line.startsWith('data: '))continue;
      const ev=JSON.parse(line.slice(6));
      if(ev.event==='sources'){
        clearInterval(timer);timings=ev.timings;srcHtml=cards(ev.hits);
        CITES=ev.hits||[];
        AON_LABEL={};CITES.forEach(h=>{if(h.url)AON_LABEL[h.url]=h.name});
        paint();pending();
      }else if(ev.event==='token'){
        if(!started){started=true;clearInterval(timer)}
        answer+=ev.text;paint();
      }else if(ev.event==='done'){clearInterval(timer);timings=ev.timings;
        answer=answer.trimEnd();paint();
        const c=document.querySelector('.caret');if(c)c.remove();
      }else if(ev.event==='error'){clearInterval(timer);
        out.innerHTML='<p class="err">'+esc(ev.error)+'</p>';return}
    }
  }
  clearInterval(timer);
}
async function go(mode){
  const text=q.value.trim(); if(!text||!ready)return;
  enable(false);
  try{ mode==='ask'?await ask(text):await search(text) }
  catch(e){clearInterval(timer);out.innerHTML='<p class="err">'+esc(String(e))+'</p>'}
  enable(true);
}
document.getElementById('f').addEventListener('submit',e=>{e.preventDefault();go('search')});
askBtn.addEventListener('click',()=>go('ask'));
document.addEventListener('keydown',e=>{if(e.key==='/'&&document.activeElement!==q){
  e.preventDefault();q.focus();q.select()}});
</script></body></html>"""
