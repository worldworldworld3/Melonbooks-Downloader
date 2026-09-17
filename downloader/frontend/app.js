'use strict';
const $ = id => document.getElementById(id);
let books=[], state={}, revision=-1, selected=new Set(), downloaded=new Set(), tab='all', group='', filter='all', view='grid', detailId=null, lastAccount='', polling=false;
const el=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n};
const mb=n=>n?`${(n/1048576).toFixed(1)} MB`:'';
function toast(text){$('toast').textContent=text;$('toast').hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('toast').hidden=true,4200)}
async function call(method,...args){try{if(!window.pywebview?.api){toast('请运行 Melonbooks Downloader.exe。');return}const result=await window.pywebview.api[method](...args);if(result?.error)toast(result.error);await poll();return result}catch(e){toast('无法连接下载器，请重新启动。')}}
function filtered(){const q=$('search').value.trim().toLocaleLowerCase();return books.filter(b=> (!q||[b.title,b.circle,b.author,b.id].join(' ').toLocaleLowerCase().includes(q))&&(filter==='all'||filter==='general'&&!b.adult||filter==='adult'&&b.adult)&&(!group||b[tab]===group)).sort((a,b)=>$('sort').value==='title'?a.title.localeCompare(b.title,'ja'):$('sort').value==='size'?b.size-a.size:b.date.localeCompare(a.date))}
function placeholder(){const p=el('div','cover-placeholder');p.append(el('b','','▤'),el('small','','暂无封面'));return p}
function cover(b){if(!b.thumbnail)return placeholder();const image=el('img');image.src=b.thumbnail;image.alt=b.title+' 封面';image.loading='lazy';image.referrerPolicy='no-referrer';image.addEventListener('error',()=>image.replaceWith(placeholder()),{once:true});return image}
function toggleSelect(id){if(downloaded.has(id)){selected.delete(id);render();return}selected.has(id)?selected.delete(id):selected.add(id);render()}
function detail(id,show=true){const b=books.find(b=>b.id===id);if(!b)return;detailId=id;const wrap=el('div','detail-layout'),picture=el('div','detail-cover'),info=el('div','detail-info');picture.append(cover(b));info.append(el('span','eyebrow',b.format),el('h2','',b.title));const dl=el('dl');[['社团',b.circle||'未提供'],['作者',b.author||'未提供'],['购买日期',b.date||'未提供'],...(b.size>0?[['源文件大小',mb(b.size)]]:[]),['作品编号',b.id],['分级',b.adult?'成年':'一般']].forEach(([key,value])=>dl.append(el('dt','',key),el('dd','',value)));info.append(dl);wrap.append(picture,info);$('detailBody').replaceChildren(wrap);$('detailSelect').disabled=downloaded.has(id);$('detailSelect').textContent=downloaded.has(id)?'✓ 已下载':selected.has(id)?'取消选择':'选择此作品';if(show)$('detail').showModal()}
function renderGroups(){const container=$('groups');container.replaceChildren();if(tab==='all')return;const counts=new Map();books.forEach(b=>{if(b[tab])counts.set(b[tab],(counts.get(b[tab])||0)+1)});const all=el('button',!group?'active':'','全部');all.onclick=()=>{group='';renderGroups();render()};container.append(all);[...counts].sort((a,b)=>b[1]-a[1]).forEach(([name,count])=>{const b=el('button',group===name?'active':'',`${name} · ${count}`);b.onclick=()=>{group=name;renderGroups();render()};container.append(b)})}
function render(){selected=new Set([...selected].filter(id=>!downloaded.has(id)));const list=filtered();$('shelf').className='shelf'+(view==='list'?' list':'');const fragment=document.createDocumentFragment();list.forEach(b=>{const card=el('article','book'+(selected.has(b.id)?' selected':'')+(downloaded.has(b.id)?' is-downloaded':''));card.dataset.id=b.id;const pick=el('label','pick'),check=el('input');check.type='checkbox';check.checked=selected.has(b.id);check.disabled=downloaded.has(b.id);check.setAttribute('aria-label','选择 '+b.title);check.onchange=()=>toggleSelect(b.id);pick.append(check);const picture=el('button','cover-button');picture.setAttribute('aria-label','查看 '+b.title+' 详情');picture.append(cover(b));picture.onclick=()=>detail(b.id);const info=el('div','book-info'),title=el('button','book-title',b.title);title.title=b.title;title.onclick=()=>detail(b.id);info.append(title);[['社团',b.circle],['作者',b.author]].forEach(([label,value])=>{const m=el('p','meta');m.append(el('span','',label),document.createTextNode(value||'未提供'));m.title=value||'未提供';info.append(m)});const bottom=el('div','book-bottom');bottom.append(el('span','badge',b.format));if(b.size>0)bottom.append(el('span','file-size',mb(b.size)));if(downloaded.has(b.id))bottom.append(el('span','downloaded','✓ 已下载'));info.append(bottom);card.append(pick,picture,info);fragment.append(card)});$('shelf').replaceChildren(fragment);$('count').textContent=books.length;$('visibleCount').textContent=`${list.length} 本作品`;$('empty').hidden=list.length>0;$('emptyLogin').hidden=!!state.logged_in||books.length>0;$('emptyText').hidden=!!state.logged_in||books.length>0;$('emptyTitle').hidden=!state.logged_in&&!books.length;$('emptyTitle').textContent=books.length?'没有匹配作品':'暂无作品';const eligible=list.filter(b=>!downloaded.has(b.id));const num=eligible.filter(b=>selected.has(b.id)).length;$('selectAll').checked=!!eligible.length&&num===eligible.length;$('selectAll').indeterminate=num>0&&num<eligible.length;$('selectAll').disabled=!eligible.length;$('selectedCount').textContent=`已选择 ${selected.size} 本`;$('download').disabled=!!state.busy||!state.logged_in||!selected.size;$('clear').disabled=selected.size===0}
function applySnapshot(s){const change=Array.isArray(s.books);const account=s.account||'';if(account!==lastAccount){selected.clear();lastAccount=account}const downloadsChanged=JSON.stringify(state.downloaded)!==JSON.stringify(s.downloaded);state=s;downloaded=new Set(s.downloaded||[]);selected=new Set([...selected].filter(id=>!downloaded.has(id)));if(change){books=s.books;revision=s.revision;const ids=new Set(books.map(b=>b.id));selected=new Set([...selected].filter(id=>ids.has(id)));if(group&&!books.some(b=>b[tab]===group))group='';renderGroups()}$('account').textContent=s.logged_in?'已登录 · '+account:'尚未登录';$('login').textContent=s.logged_in?'切换账号':'登录账号';$('folder').textContent=s.folder||'';$('folder').title=(s.folder||'')+'（点击更改）';$('status').textContent=s.message||'';$('status').title=s.message||'';$('status').parentElement.classList.toggle('error',!!s.error);$('progress').style.width=(s.progress||0)+'%';$('progressText').textContent=s.progress_text||'';['login','emptyLogin','refresh','folder','convertLocal','clearCache'].forEach(id=>$(id).disabled=!!s.busy);$('refresh').disabled=!!s.busy||!s.logged_in;$('cancel').hidden=!['download','convert','login','check'].includes(s.operation);$('download').disabled=!!s.busy||!s.logged_in||!selected.size;if(change||downloadsChanged){render();if($('detail').open)detail(detailId,false)}applyLocal(s)}
async function poll(){if(polling||!window.pywebview?.api)return;polling=true;try{applySnapshot(await window.pywebview.api.snapshot(revision))}catch(e){$('status').textContent='下载器连接中断，请重新启动。'}finally{polling=false}}
$('login').onclick=$('emptyLogin').onclick=()=>call('login');$('refresh').onclick=()=>call('refresh');$('folder').onclick=()=>call('choose_folder');$('openFolder').onclick=()=>call('open_folder');$('cancel').onclick=()=>call('cancel');$('download').onclick=()=>call('download',[...selected]);$('search').oninput=render;$('sort').onchange=render;$('clear').onclick=()=>{selected.clear();render()};$('selectAll').onchange=()=>{const add=$('selectAll').checked;filtered().filter(b=>!downloaded.has(b.id)).forEach(b=>add?selected.add(b.id):selected.delete(b.id));render()};$('closeDetail').onclick=()=>$('detail').close();$('detailSelect').onclick=()=>{toggleSelect(detailId);detail(detailId,false)};
document.querySelectorAll('[data-filter]').forEach(b=>b.onclick=()=>{filter=b.dataset.filter;document.querySelectorAll('[data-filter]').forEach(n=>n.classList.toggle('active',n===b));render()});document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{tab=b.dataset.tab;group='';document.querySelectorAll('[data-tab]').forEach(n=>n.classList.toggle('active',n===b));$('heading').textContent={all:'全部作品',circle:'按社团浏览',author:'按作者浏览'}[tab];renderGroups();render()});function switchView(v){view=v;['grid','list'].forEach(n=>{$(n+'View').classList.toggle('active',n===v);$(n+'View').setAttribute('aria-pressed',n===v)});render()}$('gridView').onclick=()=>switchView('grid');$('listView').onclick=()=>switchView('list');window.addEventListener('pywebviewready',()=>{poll();setInterval(poll,500)});render();

$('convertLocal').onclick=()=>call('convert_local');

let localRenderKey='';
function applyLocal(s){
 const open=!!s.local_open, rows=s.local_files||[], ready=rows.filter(r=>r.status==='ready').length;
 $('convertLocal').disabled=!!s.busy||!s.logged_in;
 $('libraryPage').hidden=open;$('localPage').hidden=!open;document.querySelector('.tabs').hidden=open;
 $('download').hidden=open;$('selectedCount').hidden=open;$('startLocal').hidden=!open;
 $('startLocal').disabled=!!s.busy||!s.logged_in||!ready;
 $('startLocal').textContent=`转换可用文件${ready?' ('+ready+')':''}`;
 $('localAccount').textContent='当前账号 · '+(s.account||'尚未登录');
 ['addLocal','addCache','recheckLocal','clearLocal','backLibrary'].forEach(id=>$(id).disabled=!!s.busy);
 $('dropZone').setAttribute('aria-disabled',String(!!s.busy||!s.logged_in));
 const done=rows.filter(r=>r.status==='done').length;
 $('localSummary').textContent=`共 ${rows.length} 个 · 可转换 ${ready} 个 · 已完成 ${done} 个`;
 const key=JSON.stringify([rows,!!s.busy]);if(key===localRenderKey)return;localRenderKey=key;
 const fragment=document.createDocumentFragment();
 const labels={pending:'待校验',checking:'正在校验',ready:'可转换',blocked:'无法转换',converting:'正在转换',done:'已完成',failed:'转换失败'};
 rows.forEach(r=>{
  const tr=el('tr'),file=el('td'),size=el('td','',mb(r.size)),status=el('td'),actions=el('td');
  file.append(el('strong','file-name',r.name));if(r.title)file.append(el('span','file-title',r.title));
  status.append(el('span','local-status '+r.status,labels[r.status]||r.status),el('p','local-reason',r.detail));
  const remove=el('button','text-button','移除');remove.disabled=!!s.busy;remove.onclick=()=>call('remove_local_file',r.id);actions.append(remove);
  tr.append(file,size,status,actions);fragment.append(tr);
 });
 $('localRows').replaceChildren(fragment);
}
$('backLibrary').onclick=()=>call('close_local');
$('addLocal').onclick=()=>call('choose_local_files');
$('addCache').onclick=()=>call('add_cached_files');
$('recheckLocal').onclick=()=>call('check_local_files');
$('clearLocal').onclick=()=>call('remove_local_file');
$('startLocal').onclick=()=>call('start_local_conversion');
const dropZone=$('dropZone');
function pickLocal(){if(!state.busy&&state.logged_in)call('choose_local_files')}
dropZone.onclick=pickLocal;
dropZone.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();pickLocal()}};
['dragenter','dragover'].forEach(event=>dropZone.addEventListener(event,e=>{e.preventDefault();if(!state.busy&&state.logged_in)dropZone.classList.add('dragging')}));
['dragleave','drop'].forEach(event=>dropZone.addEventListener(event,e=>{e.preventDefault();dropZone.classList.remove('dragging')}));
window.addEventListener('dragover',e=>e.preventDefault());
window.addEventListener('drop',e=>e.preventDefault());

let cacheToken=null;
$('clearCache').onclick=async()=>{
 const result=await call('cache_preview');if(!result||result.error)return;
 cacheToken=result.token;
 $('cacheSummary').textContent=`本次将清除 ${result.count} 个文件，共 ${(result.bytes/1048576).toFixed(1)} MB。`;
 $('confirmClearCache').disabled=!result.count||!!state.busy;
 $('cacheDialog').showModal();
};
$('cancelClearCache').onclick=()=>{cacheToken=null;$('cacheDialog').close()};
$('confirmClearCache').onclick=async()=>{
 if(!cacheToken)return;
 const token=cacheToken;cacheToken=null;$('cacheDialog').close();
 await call('clear_cache',token);
};
