# -*- coding: utf-8 -*-
"""باركود للقطع + كاشير سريع + ملصقات باركود + عنوان الشركة على الفواتير."""
import json, html
from urllib.parse import quote

PAT = ['212222', '222122', '222221', '121223', '121322', '131222', '122213', '122312', '132212', '221213', '221312', '231212', '112232', '122132', '122231', '113222', '123122', '123221', '223211', '221132', '221231', '213212', '223112', '312131', '311222', '321122', '321221', '312212', '322112', '322211', '212123', '212321', '232121', '111323', '131123', '131321', '112313', '132113', '132311', '211313', '231113', '231311', '112133', '112331', '132131', '113123', '113321', '133121', '313121', '211331', '231131', '213113', '213311', '213131', '311123', '311321', '331121', '312113', '312311', '332111', '314111', '221411', '431111', '111224', '111422', '121124', '121421', '141122', '141221', '112214', '112412', '122114', '122411', '142112', '142211', '241211', '221114', '413111', '241112', '134111', '111242', '121142', '121241', '114212', '124112', '124211', '411212', '421112', '421211', '212141', '214121', '412121', '111143', '111341', '131141', '114113', '114311', '411113', '411311', '113141', '114131', '311141', '411131', '211412', '211214', '211232', '2331112']


def code128_svg(text, h=60, quiet=10):
    """Code128-B كـ SVG (بدون مكتبات خارجية)."""
    text = "".join(ch for ch in str(text) if 32 <= ord(ch) < 127) or "0"
    vals = [104] + [ord(ch) - 32 for ch in text]
    vals.append((104 + sum(i * v for i, v in enumerate(vals[1:], 1))) % 103)
    vals.append(106)
    x = quiet; bars = []
    for v in vals:
        for n, w in enumerate(PAT[v]):
            w = int(w)
            if n % 2 == 0: bars.append(f"M{x} 0h{w}v{h}h-{w}z")
            x += w
    W = x + quiet
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {h}" preserveAspectRatio="none" shape-rendering="crispEdges" role="img" aria-label="{html.escape(text)}">'
            f'<rect width="{W}" height="{h}" fill="#fff"/><path d="{"".join(bars)}" fill="#000"/></svg>')


def ean13(body12):
    s = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(body12))
    return body12 + str((10 - s % 10) % 10)


CAT_ROUTE = {"بطارية": "/batteries", "آيسي": "/ics", "شاشة": "/screens", "قاعدة شحن": "/chargers", "سماعات": "/headphones", "كونكتر": "/connectors", "ظهر": "/backs"}

CSS = """<style>
.px{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(320px,1fr);gap:18px;align-items:start}
.px-card{background:#fff;border:1px solid var(--line);border-radius:20px;box-shadow:var(--sh);padding:16px}
.px-scan{display:flex;gap:10px;align-items:center;position:relative}
.px-scan label{flex:1;display:flex;align-items:center;gap:10px;border:2px solid var(--br);border-radius:16px;padding:6px 14px;background:#fff}
.px-scan svg{width:26px;height:26px;color:var(--br);flex:none}
.px-scan input{flex:1;border:0!important;outline:0;font-size:20px;padding:10px 0;background:transparent!important;box-shadow:none!important;margin:0!important;min-width:0}
.px-res{position:absolute;top:100%;inset-inline:0;z-index:20;background:#fff;border:1px solid var(--line);border-radius:14px;box-shadow:var(--sh);margin-top:6px;max-height:340px;overflow:auto}
.px-res button{display:flex;width:100%;gap:10px;align-items:center;padding:10px 14px;border:0;background:transparent;text-align:start;cursor:pointer;font:inherit;border-radius:0;color:var(--ink);box-shadow:none}
.px-res button:hover,.px-res button.on{background:#eef0ff}.px-res b{flex:1}.px-res small{color:var(--mut)}
.px-msg{min-height:22px;margin:8px 4px 0;font-size:13.5px;font-weight:700}.px-msg.ok{color:#059669}.px-msg.err{color:#e11d48}
.px-tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;margin-top:12px}
.px-tile{border:1px solid var(--line);background:#fff;border-radius:14px;padding:10px;text-align:start;cursor:pointer;display:flex;flex-direction:column;gap:4px;font:inherit;color:var(--ink);box-shadow:none;transition:.12s}
.px-tile:hover{border-color:var(--br);transform:translateY(-1px)}.px-tile b{font-size:13.5px;line-height:1.35}.px-tile span{color:var(--br);font-weight:800}.px-tile small{color:var(--mut)}
.px-h{margin:14px 4px 0;font-size:13px;color:var(--mut);font-weight:700}
.px-cart table{width:100%;border-collapse:collapse}.px-cart th{font-size:12px;color:var(--mut);text-align:start;padding:8px 6px}.px-cart td{padding:6px;border-top:1px solid var(--line);vertical-align:middle}
.px-cart td b{font-size:14px}.px-q{display:inline-flex;align-items:center;border:1px solid var(--line);border-radius:10px;overflow:hidden}
.px-q button{width:30px;height:32px;border:0;background:#f1f4fb;cursor:pointer;font-size:16px;border-radius:0;padding:0;color:var(--ink);box-shadow:none}.px-q input{width:44px;text-align:center;border:0!important;margin:0!important;padding:4px 0;box-shadow:none!important;background:transparent!important}
.px-p{width:78px;padding:6px 8px;margin:0}.px-x{border:0;background:transparent;color:#e11d48;cursor:pointer;font-size:18px;padding:4px 8px;box-shadow:none}
.px-empty{text-align:center;color:var(--mut);padding:30px 0}
.px-sum div{display:flex;justify-content:space-between;padding:6px 0;font-size:14.5px}.px-sum .tt{font-size:26px;font-weight:800;border-top:2px solid var(--ink);margin-top:6px;padding-top:12px}
.px-pay{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:10px 0}
.px-pay button{padding:12px;border-radius:14px;border:2px solid var(--line);background:#fff;font:inherit;font-weight:800;cursor:pointer;color:var(--ink);box-shadow:none}.px-pay button.on{border-color:var(--br);background:#eef0ff;color:var(--br)}
.px-f label{display:block;font-size:12.5px;font-weight:700;margin-top:8px}.px-f input,.px-f select{width:100%;margin:4px 0 0;box-sizing:border-box}
.px-chg{background:#ecfdf5;color:#047857;border-radius:12px;padding:10px 14px;font-weight:800;display:flex;justify-content:space-between;margin-top:8px}
.px-go{width:100%;margin-top:12px;padding:16px;font-size:18px;font-weight:800;border-radius:16px;border:0;cursor:pointer;color:#fff;background:linear-gradient(135deg,#059669,#10b981);box-shadow:0 10px 24px -10px #059669}.px-go:disabled{opacity:.45;cursor:not-allowed}
.px-clr{background:transparent;border:0;color:var(--mut);cursor:pointer;font:inherit;text-decoration:underline;box-shadow:none;padding:6px}
.px-ov{position:fixed;inset:0;background:#0009;z-index:90;display:none;place-items:center}.px-ov.on{display:grid}
.px-ok{background:#fff;border-radius:24px;padding:28px;width:min(420px,92vw);max-height:92vh;max-height:92dvh;overflow-y:auto;overscroll-behavior:contain;text-align:center}.px-ok h2{margin:0 0 6px;color:#059669}.px-ok .big{font-size:34px;font-weight:800;margin:6px 0}
.px-ok .row{display:flex;gap:8px;justify-content:center;flex-wrap:wrap;margin-top:14px}
.px-kbd{font-size:12px;color:var(--mut);margin-top:10px}
@media(max-width:980px){.px{grid-template-columns:1fr}}
.px button.px-tile,.px-res button{background:#fff!important;color:var(--ink)!important}.px-res button:hover,.px-res button.on{background:#eef0ff!important}
.px-pay button{background:#fff!important;color:var(--ink)!important}.px-pay button.on{background:#eef0ff!important;color:var(--br)!important}
.px-q button{background:#f1f4fb!important;color:var(--ink)!important;min-width:30px}.px-x{background:transparent!important;color:#e11d48!important}.px-clr{background:transparent!important;color:var(--mut)!important}
html[data-theme=dark] .px button.px-tile,html[data-theme=dark] .px-res button,html[data-theme=dark] .px-pay button{background:#141b3a!important;color:var(--ink)!important}
html[data-theme=dark] .px-pay button.on,html[data-theme=dark] .px-res button.on{background:#26307a!important;color:#fff!important}html[data-theme=dark] .px-q button{background:#1d2656!important}
html[data-theme=dark] .px-card,html[data-theme=dark] .px-scan label,html[data-theme=dark] .px-res,html[data-theme=dark] .px-tile,html[data-theme=dark] .px-ok,html[data-theme=dark] .px-pay button{background:#141b3a!important;color:var(--ink);border-color:var(--line)}
html[data-theme=dark] .px-res button:hover,html[data-theme=dark] .px-res button.on,html[data-theme=dark] .px-pay button.on{background:#26307a!important;color:#fff}
html[data-theme=dark] .px-q button{background:#1d2656;color:var(--ink)}html[data-theme=dark] .px-chg{background:#0f3a2e;color:#6ee7b7}
</style>"""

T_POS = r"""{% extends 'base' %}{% block c %}
""" + CSS + r"""
<div class=ph><h2>كاشير سريع</h2><p>امسح الباركود أو اكتب اسم القطعة، وخلّص الفاتورة بثواني</p></div>
<div class=px>
<div>
<div class="px-card"><div class=px-scan><label><svg viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2 stroke-linecap=round><path d="M3 5v14M7 5v14M11 5v14M14 5v14M18 5v14M21 5v14"/></svg><input id=pxq placeholder="امسح الباركود أو ابحث باسم القطعة..." autocomplete=off autofocus inputmode=search></label><div class=px-res id=pxr hidden></div></div>
<div class=px-msg id=pxm></div>
<div class=px-h id=pxth>الأكثر مبيعاً</div><div class=px-tiles id=pxt></div></div>
<div class="px-card px-cart" style="margin-top:16px"><table><thead><tr><th>الصنف<th>السعر<th>الكمية<th>المجموع<th></tr></thead><tbody id=pxb></tbody></table><div class=px-empty id=pxe>السلة فاضية. امسح أول قطعة 👆</div></div>
</div>
<div class=px-card style="position:sticky;top:90px"><div class=px-sum><div><span>عدد القطع</span><b id=pxn>0</b></div><div><span>المجموع</span><b id=pxs>0 ₪</b></div><div><span>خصم (₪)</span><input id=pxd type=number min=0 step=any value=0 style="width:100px;margin:0"></div><div class=tt><span>الصافي</span><b id=pxt2>0 ₪</b></div><div><span>المربح</span><b id=pxpf style="color:#059669">0 ₪</b></div></div>
<div class=px-pay><button type=button data-m=نقدي class=on>💵 نقد</button><button type=button data-m=دين>📒 دين</button></div>
<div class=px-f>
<div id=pxcash><label>المدفوع من الزبون (₪)<input id=pxrc type=number min=0 step=any placeholder="اتركه فاضي = المبلغ بالضبط"></label><div class=px-chg id=pxch hidden><span>الباقي للزبون</span><b id=pxcv>0</b></div></div>
<div id=pxdebt hidden><label>دفعة الآن (₪)<input id=pxpd type=number min=0 step=any value=0></label></div>
<label id=pxpl>الشخص <span id=pxreq style="color:#e11d48" hidden>*</span><select id=pxp><option value="">زبون نقدي (بدون حساب)</option>{% for d in people %}<option value={{d.id}}>{{d.name}}</option>{% endfor %}<option value=new>+ شخص جديد...</option></select></label>
<input id=pxpn placeholder="اسم الشخص الجديد" hidden><input id=pxph placeholder="الهاتف (اختياري)" hidden dir=ltr>
</div>
<label class=px-f style="display:flex;gap:8px;align-items:center;font-weight:600;margin-top:10px"><input type=checkbox id=pxprint style="width:auto;margin:0" checked> طباعة الإيصال تلقائياً بعد البيع</label>
<button class=px-go id=pxgo disabled>إتمام البيع (F9)</button><div style="display:flex;justify-content:space-between"><button class=px-clr id=pxclr type=button>إفراغ السلة</button><span class=px-kbd>F2 للمسح · F9 للدفع</span></div></div>
</div>
<div class=px-ov id=pxov><div class=px-ok><h2>تم البيع ✓</h2><div class=big id=pxok1></div><div id=pxok2 style="color:var(--mut)"></div><div class=row><a class=btn id=pxa4 target=_blank>فاتورة A4</a><a class=btn id=pxth2 target=_blank>إيصال حراري</a><button id=pxnew type=button>بيع جديد (Enter)</button></div></div></div>
<iframe id=pxfr style="position:absolute;width:0;height:0;border:0" title="print"></iframe>
<script>(function(){
var P={{prods|tojson}},TOP={{top|tojson}},cart=[],M='نقدي',busy=false;
var $=function(i){return document.getElementById(i)},q=$('pxq'),R=$('pxr');
function fmt(n){n=Math.round(n*100)/100;return (n%1?n.toFixed(2):String(n))+' ₪'}
var AC;function beep(ok){try{AC=AC||new (window.AudioContext||window.webkitAudioContext)();var o=AC.createOscillator(),g=AC.createGain();o.connect(g);g.connect(AC.destination);o.frequency.value=ok?1100:220;g.gain.value=.08;o.start();o.stop(AC.currentTime+(ok?.07:.25))}catch(e){}}
function msg(t,k){var m=$('pxm');m.textContent=t||'';m.className='px-msg '+(k||'')}
function byBar(c){for(var i=0;i<P.length;i++)if(P[i].b&&P[i].b===c)return P[i];return null}
function byKey(k){for(var i=0;i<P.length;i++)if(P[i].k===k)return P[i];return null}
function add(p,n){if(!p)return;n=n||1;var l=cart.find(function(x){return x.k===p.k});var cur=l?l.q:0;if(cur+n>p.s){msg('المتوفر من «'+p.n+'» '+p.s+' فقط','err');beep(false);return}
if(l)l.q+=n;else cart.push({k:p.k,n:p.n,p:p.p,q:n,s:p.s,c:p.c0||0});msg('+ '+p.n,'ok');beep(true);draw()}
function total(){var s=0,n=0,c=0;cart.forEach(function(l){s+=l.p*l.q;n+=l.q;c+=(l.c||0)*l.q});var d=Math.min(Math.max(+$('pxd').value||0,0),s);var t=Math.round((s-d)*100)/100;return{n:n,s:s,d:d,t:t,pf:Math.round((t-c)*100)/100}}
function draw(){var b=$('pxb');b.innerHTML='';cart.forEach(function(l,i){var tr=document.createElement('tr');
tr.innerHTML='<td><b></b></td><td><input class=px-p type=number min=0 step=any></td><td><span class=px-q><button type=button data-a=m>−</button><input type=number min=1></span></td><td class=lt></td><td><button class=px-x type=button title=حذف>✕</button></td>';
tr.querySelector('b').textContent=l.n;var pi=tr.querySelector('.px-p');pi.value=l.p;pi.oninput=function(){l.p=+pi.value||0;sum();tr.querySelector('.lt').textContent=fmt(l.p*l.q)};
var qi=tr.querySelector('.px-q input');qi.value=l.q;qi.onchange=function(){var v=Math.max(1,parseInt(qi.value)||1);if(v>l.s){v=l.s;msg('المتوفر '+l.s+' فقط','err')}l.q=v;draw()};
var qb=tr.querySelector('.px-q button');qb.onclick=function(){if(l.q>1){l.q--;draw()}};var pl=document.createElement('button');pl.type='button';pl.textContent='+';pl.onclick=function(){if(l.q<l.s){l.q++;draw()}else{msg('المتوفر '+l.s+' فقط','err');beep(false)}};qi.after(pl);
tr.querySelector('.lt').textContent=fmt(l.p*l.q);tr.querySelector('.px-x').onclick=function(){cart.splice(i,1);draw()};b.appendChild(tr)});
$('pxe').hidden=cart.length>0;sum()}
function sum(){var t=total();$('pxn').textContent=t.n;$('pxs').textContent=fmt(t.s);$('pxt2').textContent=fmt(t.t);$('pxpf').textContent=fmt(t.pf);$('pxpf').style.color=t.pf>=0?'#059669':'#e11d48';$('pxgo').disabled=!cart.length||busy;chg()}
function chg(){var t=total(),r=$('pxrc').value;var show=M==='نقدي'&&r!==''&&(+r)>=t.t&&t.t>0;$('pxch').hidden=!show;if(show)$('pxcv').textContent=fmt(+r-t.t)}
$('pxd').oninput=sum;$('pxrc').oninput=chg;
document.querySelectorAll('.px-pay button').forEach(function(b){b.onclick=function(){M=b.dataset.m;document.querySelectorAll('.px-pay button').forEach(function(x){x.classList.toggle('on',x===b)});$('pxcash').hidden=M!=='نقدي';$('pxdebt').hidden=M==='نقدي';$('pxreq').hidden=M==='نقدي';chg()}});
$('pxp').onchange=function(){var n=this.value==='new';$('pxpn').hidden=!n;$('pxph').hidden=!n;if(n)$('pxpn').focus()};
function tiles(){var h='';TOP.forEach(function(k){var p=byKey(k);if(p)h+='<button class=px-tile type=button data-k="'+p.k+'"><b></b><span>'+fmt(p.p)+'</span><small>متوفر '+p.s+'</small></button>'});$('pxt').innerHTML=h;
var bs=$('pxt').querySelectorAll('.px-tile');TOP.filter(function(k){return byKey(k)}).forEach(function(k,i){bs[i].querySelector('b').textContent=byKey(k).n;bs[i].onclick=function(){add(byKey(k));q.focus()}})}
var sel=-1,list=[];
function search(){var v=q.value.trim().toLowerCase();if(!v){R.hidden=true;list=[];return}var ws=v.split(/\s+/);list=P.filter(function(p){var s=(p.n+' '+(p.b||'')+' '+(p.c||'')).toLowerCase();return ws.every(function(w){return s.indexOf(w)>-1})}).slice(0,30);sel=list.length?0:-1;
R.innerHTML='';list.forEach(function(p,i){var b=document.createElement('button');b.type='button';b.className=i===0?'on':'';b.innerHTML='<b></b><small></small><span></span>';b.querySelector('b').textContent=p.n;b.querySelector('small').textContent=(p.c||'')+' · متوفر '+p.s;b.querySelector('span').textContent=fmt(p.p);b.onclick=function(){add(p);q.value='';search();q.focus()};R.appendChild(b)});R.hidden=!list.length}
q.oninput=search;
q.onkeydown=function(e){if(e.key==='ArrowDown'||e.key==='ArrowUp'){if(!list.length)return;e.preventDefault();sel=(sel+(e.key==='ArrowDown'?1:-1)+list.length)%list.length;[].forEach.call(R.children,function(c,i){c.classList.toggle('on',i===sel)});R.children[sel].scrollIntoView({block:'nearest'})}
else if(e.key==='Enter'){e.preventDefault();var v=q.value.trim();if(!v)return;var p=byBar(v);if(!p&&list.length)p=list[Math.max(sel,0)];if(p){add(p);q.value='';search()}else{msg('ما لقيت «'+v+'»','err');beep(false)}}
else if(e.key==='Escape'){q.value='';search()}};
document.addEventListener('click',function(e){if(!e.target.closest('.px-scan'))R.hidden=true});
window.rxScanHook=function(code){var p=byBar(code);if(p)add(p);else{msg('باركود غير معروف: '+code,'err');beep(false)}};
$('pxclr').onclick=function(){if(cart.length&&confirm('إفراغ السلة؟')){cart=[];draw()}};
function reset(){cart=[];$('pxd').value=0;$('pxrc').value='';$('pxpd').value=0;$('pxp').value='';$('pxpn').hidden=$('pxph').hidden=true;$('pxpn').value='';$('pxph').value='';draw();msg('');q.value='';q.focus()}
function pay(){if(busy||!cart.length)return;var t=total();var pid=$('pxp').value;
if(M==='دين'&&!pid){msg('اختر الشخص للدين','err');beep(false);$('pxp').focus();return}
if(pid==='new'&&!$('pxpn').value.trim()){msg('اكتب اسم الشخص الجديد','err');$('pxpn').focus();return}
busy=true;$('pxgo').disabled=true;
var body={items:cart.map(function(l){return{k:l.k,q:l.q,p:l.p}}),discount:t.d,method:M,person_id:pid,person_name:$('pxpn').value,phone:$('pxph').value,paid:M==='دين'?(+$('pxpd').value||0):t.t};
fetch('/pos/checkout',{method:'POST',headers:{'Content-Type':'application/json','X-Requested-With':'fetch'},body:JSON.stringify(body)}).then(function(r){return r.json()}).then(function(j){busy=false;
if(!j.ok){msg(j.error||'تعذّر البيع','err');beep(false);sum();return}
cart.forEach(function(l){var p=byKey(l.k);if(p)p.s-=l.q});var rc=+$('pxrc').value;
$('pxok1').textContent=fmt(j.total);$('pxok2').textContent=j.ref+(M==='نقدي'&&rc>j.total?' · الباقي للزبون '+fmt(rc-j.total):'')+(j.due>0?' · متبقي دين '+fmt(j.due):'')+' · المربح '+fmt(j.profit);
$('pxa4').href='/sales/'+j.id;$('pxth2').href='/sales/'+j.id+'/thermal';$('pxov').classList.add('on');beep(true);
if($('pxprint').checked)$('pxfr').src='/sales/'+j.id+'/thermal?auto=1';
}).catch(function(){busy=false;msg('خطأ بالاتصال','err');sum()})}
$('pxgo').onclick=pay;
function done(){$('pxov').classList.remove('on');$('pxfr').src='about:blank';P=P.filter(function(p){return p.s>0});tiles();reset()}
$('pxnew').onclick=done;
document.addEventListener('keydown',function(e){if(e.key==='F9'){e.preventDefault();if($('pxov').classList.contains('on'))return;pay()}else if(e.key==='F2'){e.preventDefault();q.focus();q.select()}else if(e.key==='Enter'&&$('pxov').classList.contains('on')){e.preventDefault();done()}});
tiles();draw();
var a=new URLSearchParams(location.search).get('add');if(a){var p=byBar(a);if(p)add(p)}
})();</script>{% endblock %}"""

T_BC = r"""{% extends 'base' %}{% block c %}
<style>.bl-t{width:100%;border-collapse:collapse}.bl-t td,.bl-t th{padding:8px;border-bottom:1px solid var(--line);text-align:start}.bl-t svg{height:34px;width:130px;display:block}.bl-c{font-family:ui-monospace,Consolas,monospace;direction:ltr;display:inline-block}
.bl-b{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:12px}.bl-b input,.bl-b select{margin:0}</style>
<div class=ph><h2>ملصقات الباركود</h2><p>اختر القطع واطبع ملصقات باركود لزقها على القطع، وبعدها امسحها بالكاشير أو بأي صفحة</p></div>
<form method=get action=/barcodes/print target=_blank class=card id=bf><div class=bl-b>
<label class=search style="flex:1;min-width:220px">{{ic.sr}}<input id=bq placeholder="ابحث بالاسم أو الباركود..." autocomplete=off></label>
<label>عدد النسخ لكل قطعة <input type=number name=copies value=1 min=1 max=100 style="width:80px"></label>
<label>الحجم <select name=size><option value=a4>A4 (شبكة ملصقات)<option value=50x30>رول 50×30 مم<option value=40x25>رول 40×25 مم</select></label>
<button>طباعة المحدد</button><button type=button class=ghost id=ball>تحديد الكل</button></div>
<table class=bl-t id=bt><tr><th><th>القطعة<th>النوع<th>الباركود<th>الكمية<th>السعر</tr>
{% for p in items %}<tr data-s="{{p.label}} {{p.category}} {{p.barcode}}"><td><input type=checkbox name=ids value="{{p.key}}" style="margin:0"><td>{{p.label}}<td>{{p.category}}<td><span class=bl-c>{{p.barcode}}</span><td>{{p.qty}}<td>{{ '%g'|format(p.price) }} ₪</tr>
{% else %}<tr><td colspan=6 class=em>ما في قطع بعد.</tr>{% endfor %}</table></form>
<script>(function(){var q=document.getElementById('bq'),rows=[].slice.call(document.querySelectorAll('#bt tr[data-s]'));q.oninput=function(){var v=q.value.trim().toLowerCase();rows.forEach(function(r){r.hidden=v&&r.dataset.s.toLowerCase().indexOf(v)<0})};
document.getElementById('ball').onclick=function(){var vis=rows.filter(function(r){return !r.hidden});var all=vis.every(function(r){return r.querySelector('input').checked});vis.forEach(function(r){r.querySelector('input').checked=!all})};
{% if sel %}rows.forEach(function(r){var i=r.querySelector('input');if({{sel|tojson}}.indexOf(i.value)>-1)i.checked=true});{% endif %}})();</script>{% endblock %}"""

T_BCP = r"""<!doctype html><html lang=ar dir=rtl><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>ملصقات باركود</title>
<style>*{box-sizing:border-box}body{margin:0;background:#e5e5e5;font-family:Tahoma,Arial,sans-serif;color:#000}.bar{background:#222;padding:10px;text-align:center}.bar button{padding:8px 18px;border:0;border-radius:6px;background:#fff;font:inherit;font-weight:700;cursor:pointer}
.sheet{margin:14px auto;background:#fff;padding:8mm;display:flex;flex-wrap:wrap;gap:0;align-content:flex-start}
.lb{border:1px dashed #bbb;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:1.5mm;overflow:hidden;break-inside:avoid;page-break-inside:avoid}
.lb .sn{font-size:7px;color:#333;line-height:1}.lb .pn{font-size:9.5px;font-weight:700;line-height:1.15;max-height:2.4em;overflow:hidden;margin:.4mm 0}.lb svg{width:92%;flex:1;min-height:0;display:block}.lb .cd{font:9px ui-monospace,Consolas,monospace;letter-spacing:.06em;direction:ltr;line-height:1.1}.lb .pr{font-size:10.5px;font-weight:800}
.a4 .sheet{width:210mm;min-height:297mm}.a4 .lb{width:63mm;height:34mm}
.s50x30 .sheet{width:50mm;padding:0;margin:14px auto}.s50x30 .lb{width:50mm;height:30mm;border:0}.s40x25 .sheet{width:40mm;padding:0;margin:14px auto}.s40x25 .lb{width:40mm;height:25mm;border:0}
.s40x25 .pn{font-size:8px}.s40x25 .pr{font-size:9px}
@media print{body{background:#fff}.bar{display:none}.sheet{margin:0;box-shadow:none}.lb{border-color:transparent}.a4 .sheet{padding:6mm 6mm}}
{{ '@page{size:A4;margin:0}' if size=='a4' else '@page{size:'+size.replace('x','mm ')+'mm;margin:0}' }}</style>
<body class="{{ 'a4' if size=='a4' else 's'+size }}"><div class=bar><button onclick="print()">طباعة</button> <button onclick="{{ 'location.href=\'' + back + '\'' if back else 'history.length>1?history.back():close()' }}" style="margin-inline-start:6px">رجوع</button></div>
<div class=sheet>{% for l in labels %}<div class=lb><span class=sn>{{st.shop_name}}</span><div class=pn>{{l.label}}</div>{{l.svg|safe}}<div class=cd>{{l.barcode}}</div><div class=pr>{{ '%g'|format(l.price) }} ₪</div></div>{% endfor %}</div>{% if auto %}<script>window.addEventListener('load',function(){setTimeout(print,350)});window.onafterprint=function(){ {% if back %}location.href='{{back}}'{% endif %} }</script>{% endif %}</body></html>"""

BCC = "<style>"+r""".bcc{display:flex;align-items:center;gap:6px;margin-top:4px;font-size:11.5px;color:var(--mut)}.bcc a{color:inherit;display:inline-flex;align-items:center;gap:4px;text-decoration:none;direction:ltr;font-family:ui-monospace,Menlo,Consolas,monospace;letter-spacing:.02em}
.bcc a:hover{color:var(--br)}.bcc svg{width:14px;height:14px}
"""+"</style>"

JS = r"""<script>(function(){
window.rxBc=function(id,cur){var v=prompt('الباركود للقطعة (اتركه فاضي ليتولّد تلقائياً):',cur||'');if(v===null)return;var f=document.createElement('form');f.method='post';f.action='/parts/'+id+'/barcode';var i=document.createElement('input');i.type='hidden';i.name='barcode';i.value=v;f.appendChild(i);var b=document.createElement('input');b.type='hidden';b.name='back';b.value=location.pathname+location.search;f.appendChild(b);document.body.appendChild(f);f.submit()};
var buf='',last=0,fast=0;
document.addEventListener('keydown',function(e){var t=e.target,tag=t&&t.tagName;if(tag==='INPUT'||tag==='TEXTAREA'||tag==='SELECT'||(t&&t.isContentEditable))return;if(e.ctrlKey||e.altKey||e.metaKey)return;var now=Date.now();
if(e.key==='Enter'){if(buf.length>=4&&fast>=3){e.preventDefault();var c=buf;buf='';fast=0;if(window.rxScanHook)window.rxScanHook(c);else location.href='/scan/'+encodeURIComponent(c)}else{buf='';fast=0}return}
if(e.key.length!==1)return;if(now-last>80){buf='';fast=0}else fast++;buf+=e.key;last=now});
document.addEventListener('DOMContentLoaded',function(){var f=new URLSearchParams(location.search).get('find');if(!f)return;var i=document.querySelector('input[data-role=search],#stq,#bsearch');if(i){i.value=f;i.dispatchEvent(new Event('input',{bubbles:true}));i.dispatchEvent(new Event('keyup',{bubbles:true}));try{i.scrollIntoView({block:'center'})}catch(e){}}})})();</script>"""


def register(ns):
    app, T, q, ex, db, uid = ns["app"], ns["T"], ns["q"], ns["ex"], ns["db"], ns["uid"]
    render_template, redirect, request, flash, session = ns["render_template"], ns["redirect"], ns["request"], ns["flash"], ns["session"]
    notify, settings, today, now_s, _i, _f, plabel = ns["notify"], ns["settings"], ns["today"], ns["now_s"], ns["_i"], ns["_f"], ns["plabel"]
    person_by_name, jsonify, abort = ns["person_by_name"], ns["jsonify"], ns["abort"]
    app_ = app

    T["pos"], T["barcodes"], T["barcodeprint"] = T_POS, T_BC, T_BCP
    T["base"] = T["base"].replace("<div id=tc", BCC + JS + "<div id=tc", 1)

    # ---------- توليد الباركود الداخلي ----------
    import secrets as _sec

    def new_barcode():
        """كود عشوائي EAN-13 (بيبدأ بـ 2 = نطاق الاستعمال الداخلي)، مضمون غير مكرر."""
        for _ in range(50):
            code = ean13("2" + "".join(str(_sec.randbelow(10)) for _ in range(11)))
            if not taken(code): return code
        return ean13("2" + str(_sec.randbelow(10 ** 11)).zfill(11))
    ns["new_barcode"] = new_barcode

    def ensure_barcodes():
        u = uid()
        if not u: return
        for tbl in ("parts", "tools"):
            for r in q(f"select id from {tbl} where user_id=? and (barcode is null or barcode='')", (u,)):
                ex(f"update {tbl} set barcode=? where id=? and user_id=?", (new_barcode(), r["id"], u))
    ns["ensure_barcodes"] = ensure_barcodes

    @app.before_request
    def _bc_fill():
        if request.method == "GET" and session.get("uid") and request.endpoint in ("parts", "backs", "store", "tools_page", "pos_page", "barcodes_page", "barcode_print", "cart_page") :
            ensure_barcodes()

    def taken(code, skip_part=None):
        if q("select 1 from parts where user_id=? and barcode=? and id<>?", (uid(), code, skip_part or 0)): return True
        return bool(q("select 1 from tools where user_id=? and barcode=?", (uid(), code)))
    ns["barcode_taken"] = taken

    @app.route("/barcode/<code>.svg")
    def barcode_svg(code):
        return app.response_class(code128_svg(code), mimetype="image/svg+xml", headers={"Cache-Control": "public, max-age=86400"})

    @app.post("/parts/<int:i>/barcode")
    def part_barcode(i):
        p = q("select id,name from parts where id=? and user_id=?", (i, uid()))
        back = request.form.get("back") or request.referrer or "/parts"
        if not back.startswith("/"): back = "/parts"
        if not p: return redirect(back)
        v = "".join(ch for ch in (request.form.get("barcode") or "").strip() if 32 < ord(ch) < 127)[:40]
        if not v: v = new_barcode()
        if taken(v, i):
            notify(f"الباركود {v} مستعمل لقطعة ثانية", "warn", "الباركود مكرر")
        else:
            ex("update parts set barcode=? where id=? and user_id=?", (v, i, uid())); notify(f"{p[0]['name']} · {v}", "ok", "تم حفظ الباركود")
        return redirect(back)

    # ---------- المسح من أي صفحة ----------
    @app.route("/scan/<path:code>")
    def scan(code):
        code = code.strip()
        p = q("select * from parts where user_id=? and barcode=?", (uid(), code))
        if p:
            p = p[0]; base = CAT_ROUTE.get(p["category"], "/parts")
            find = p["name"] if p["category"] == "ظهر" else code
            return redirect(f"{base}?find={quote(find)}")
        t = q("select * from tools where user_id=? and barcode=?", (uid(), code))
        if t: return redirect(f"/tools?find={quote(code)}")
        notify(f"ما في قطعة بالباركود {code}", "warn", "باركود غير معروف")
        return redirect(request.referrer or "/")

    # ---------- ملصقات ----------
    def all_items():
        out = []
        for r in q("select * from parts where user_id=? order by category, name, color", (uid(),)):
            out.append(dict(key=str(r["id"]), label=plabel(r), category=r["category"], barcode=r["barcode"], qty=r["qty"], price=r["price"] or 0))
        for r in q("select * from tools where user_id=? order by name", (uid(),)):
            out.append(dict(key="t%d" % r["id"], label=r["name"], category="أدوات الصيانة", barcode=r["barcode"], qty=r["qty"], price=r["price"] or 0))
        return out

    @app.route("/barcodes")
    def barcodes_page():
        sel = [x for x in (request.args.get("ids") or "").split(",") if x]
        return render_template("barcodes", items=all_items(), sel=sel)

    @app.route("/barcodes/print")
    def barcode_print():
        ids = request.args.getlist("ids") or [x for x in (request.args.get("ids") or "").split(",") if x]
        ids = [x for s in ids for x in s.split(",") if x]
        copies = min(max(_i(request.args.get("copies"), 1), 1), 100)
        size = request.args.get("size") if request.args.get("size") in ("a4", "50x30", "40x25") else "a4"
        by = {i["key"]: i for i in all_items()}
        labels = []
        for k in ids:
            it = by.get(k)
            if it and it["barcode"]:
                for _ in range(copies): labels.append(dict(it, svg=code128_svg(it["barcode"], 60)))
        if not labels:
            flash("اختر قطعة|حدّد قطعة وحدة على الأقل للطباعة.", "warn"); return redirect("/barcodes")
        back = request.args.get("back") or ""
        return render_template("barcodeprint", labels=labels, size=size, st=settings(), auto=request.args.get("auto") == "1", back=back if back.startswith("/") else "")

    # ---------- الكاشير ----------
    @app.route("/pos")
    def pos_page():
        prods = []
        for r in q("select * from parts where user_id=? and qty>0 order by category,name", (uid(),)):
            prods.append(dict(k=str(r["id"]), n=plabel(r), p=r["price"] or 0, s=r["qty"], b=r["barcode"], c=r["category"], c0=r["cost"] or 0))
        for r in q("select * from tools where user_id=? and qty>0 order by name", (uid(),)):
            prods.append(dict(k="t%d" % r["id"], n=r["name"], p=r["price"] or 0, s=r["qty"], b=r["barcode"], c="أدوات الصيانة", c0=r["cost"] or 0))
        have = {p["k"] for p in prods}; top = []
        for r in q("select part_id, tool_id, sum(qty) n from sale_items where user_id=? group by part_id, tool_id order by n desc limit 18", (uid(),)):
            k = ("t%d" % r["tool_id"]) if r["tool_id"] else str(r["part_id"])
            if k in have: top.append(k)
        for p in prods:
            if len(top) >= 18: break
            if p["k"] not in top: top.append(p["k"])
        return render_template("pos", prods=prods, top=top, people=q("select id,name from debtors where user_id=? order by name", (uid(),)))

    @app.post("/pos/checkout")
    def pos_checkout():
        d = request.get_json(silent=True) or {}
        lines = []
        for it in d.get("items") or []:
            k = str(it.get("k", "")); tool = k.startswith("t"); n = _i(k[1:] if tool else k)
            r = q("select * from tools where id=? and user_id=?" if tool else "select * from parts where id=? and user_id=?", (n, uid()))
            if not r: return jsonify(ok=False, error="قطعة غير موجودة")
            r = dict(r[0]); qty = _i(it.get("q")); price = round(max(_f(it.get("p")), 0), 2); label = r["name"] if tool else plabel(r)
            if qty < 1: return jsonify(ok=False, error=f"{label}: كمية غير صحيحة")
            if qty > (r["qty"] or 0): return jsonify(ok=False, error=f"{label}: المتوفر {r['qty'] or 0} فقط")
            lines.append(dict(tool=tool, id=n, label=label, qty=qty, price=price, cost=r["cost"] or 0, cat="أدوات الصيانة" if tool else r["category"], min_qty=None if tool else r["min_qty"], stock=r["qty"] or 0))
        if not lines: return jsonify(ok=False, error="السلة فاضية")
        method = "دين" if d.get("method") == "دين" else "نقدي"
        pv = str(d.get("person_id") or ""); pr = None
        if pv == "new":
            nm = (d.get("person_name") or "").strip()
            if not nm: return jsonify(ok=False, error="اكتب اسم الشخص الجديد")
            pv = str(person_by_name(nm, d.get("phone") or ""))
        if pv:
            r = q("select * from debtors where id=? and user_id=?", (_i(pv), uid())); pr = dict(r[0]) if r else None
        if method == "دين" and not pr: return jsonify(ok=False, error="اختر الشخص للدين")
        sub = round(sum(l["qty"] * l["price"] for l in lines), 2); disc = round(min(max(_f(d.get("discount")), 0), sub), 2); total = round(sub - disc, 2)
        paid = total if method == "نقدي" else round(min(max(_f(d.get("paid")), 0), total), 2)
        c = db().execute("insert into sales(user_id,person_id,person_name,person_phone,created,subtotal,discount,total,paid,method,note) values(?,?,?,?,?,?,?,?,?,?,?)",
                         (uid(), pr["id"] if pr else None, pr["name"] if pr else "زبون نقدي", (pr["phone"] if pr else "") or "", now_s(), sub, disc, total, paid, method, "كاشير سريع"))
        sid = c.lastrowid
        for l in lines:
            db().execute("insert into sale_items(user_id,sale_id,part_id,tool_id,name,category,qty,price,cost) values(?,?,?,?,?,?,?,?,?)",
                         (uid(), sid, None if l["tool"] else l["id"], l["id"] if l["tool"] else None, l["label"], l["cat"], l["qty"], l["price"], l["cost"]))
            db().execute("update %s set qty=greatest(0,qty-?) where id=? and user_id=?" % ("tools" if l["tool"] else "parts"), (l["qty"], l["id"], uid()))
        ref = "SALE-%04d" % sid; summary = "، ".join(f"{l['qty']}×{l['label']}" for l in lines[:4]) + ("..." if len(lines) > 4 else "")
        profit = round(sum(l["qty"] * (l["price"] - l["cost"]) for l in lines) - disc, 2)
        if method == "دين":
            db().execute("insert into debt_entries(user_id,debtor_id,kind,amount,method,check_no,bank,due,status,note,created,item,sale_id) values(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (uid(), pr["id"], "دين", total, "", "", "", "", "", f"فاتورة {ref}", today(), summary, sid))
            if paid > 0:
                db().execute("insert into debt_entries(user_id,debtor_id,kind,amount,method,check_no,bank,due,status,note,created,item,sale_id) values(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                             (uid(), pr["id"], "دفعة", paid, "نقد", "", "", "", "", f"دفعة مقدّمة — فاتورة {ref}", today(), "", sid))
        db().commit()
        for l in lines:
            left = l["stock"] - l["qty"]
            if not l["tool"] and left <= (l["min_qty"] if l["min_qty"] is not None else 2): notify(f"{l['label']} — باقي {max(left, 0)} فقط", "warn", "تنبيه مخزون")
        return jsonify(ok=True, id=sid, ref=ref, total=total, due=round(total - paid, 2), profit=profit)
