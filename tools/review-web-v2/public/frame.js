'use strict';
let suppressScroll=false;
const send=(type,data={})=>parent.postMessage({reviewFrame:true,type,...data},'*');
document.addEventListener('click',e=>{const link=e.target.closest('a');if(link){const href=link.getAttribute('href');if(href?.startsWith('#'))return;e.preventDefault();send('navigate',{href});return;}const node=e.target.closest('[data-entry]');if(node){send('select',{index:Number(node.dataset.entry)});}});
document.addEventListener('keydown',e=>{if(e.key==='Enter'&&e.target.matches('[data-entry]'))send('select',{index:Number(e.target.dataset.entry)});});
window.addEventListener('message',e=>{if(e.source!==parent||!e.data?.reviewParent)return;const m=e.data;if(m.type==='highlight'){document.querySelectorAll('.selected').forEach(n=>n.classList.remove('selected'));document.querySelectorAll(`[data-entry="${Number(m.index)}"]`).forEach(n=>n.classList.add('selected'));if(m.scroll)document.querySelector(`[data-entry="${Number(m.index)}"]`)?.scrollIntoView({block:'center'});}if(m.type==='scroll'){suppressScroll=true;window.scrollTo(0,m.ratio*Math.max(0,document.documentElement.scrollHeight-innerHeight));setTimeout(()=>suppressScroll=false,150);}if(m.type==='find'){const node=document.getElementById(m.anchor);node?.scrollIntoView({block:'start'});}});
let ticking=false;window.addEventListener('scroll',()=>{if(suppressScroll||ticking)return;ticking=true;requestAnimationFrame(()=>{ticking=false;send('scroll',{ratio:scrollY/Math.max(1,document.documentElement.scrollHeight-innerHeight)});});},{passive:true});
send('ready');
