# -*- coding: utf-8 -*-
"""
store.py — إضافات REPAIRIX:
  1) تصنيفات المنتجات (/store): متجر إلكتروني بقائمة جانبية للتصنيفات + سلة مشتريات
  2) السلة (/store/cart): تعديل الكميات والأسعار، اختيار الشخص المشتري، طريقة الدفع (نقدي / دين)، ثم إنشاء فاتورة بيع
  3) فواتير البيع (/sales): عرض A4 وحراري، وإلغاء الفاتورة (بيرجّع المخزون ويحذف الدين المرتبط)
  4) أدوات الصيانة (/tools): جرد أدوات الورشة مع صور وبحث وتصنيف وسعر بيع (وبتنباع من المتجر)

بيتفعّل من آخر app.py بالسطر:  import store; store.register(globals())
المخزون بيُنقص تلقائياً من جدول parts، والدين بيتسجّل بحساب الشخص (صفحة الأشخاص / الديون).
"""
import datetime
from flask import request, redirect, session, abort, jsonify, flash, render_template

# ------------------------------------------------------------------ القوالب
STORE_CSS = r"""<style>
.st-top{display:flex;flex-wrap:wrap;align-items:center;gap:10px;background:#fff;border:1px solid var(--line);border-radius:20px;padding:12px 14px;box-shadow:var(--sh);margin-bottom:16px}
.st-top .search{flex:1 1 260px;max-width:none}
.st-top select{min-width:130px;margin:0}
.st-chk{display:inline-flex;align-items:center;gap:7px;font-size:13.5px;font-weight:600;color:var(--ink);cursor:pointer;margin:0 4px}
.st-chk input{margin:0;width:17px;height:17px;accent-color:var(--br)}
.st-cart{position:relative;margin-inline-start:auto}
.st-cart .bd{position:static;font-size:13px;padding:0 8px;line-height:22px;background:#fff;color:var(--br);border-radius:99px}
.st-wrap{display:grid;grid-template-columns:250px minmax(0,1fr);gap:18px;align-items:start}
.st-cats{position:sticky;top:84px;background:#fff;border:1px solid var(--line);border-radius:20px;padding:10px;box-shadow:var(--sh)}
.st-cats h4{margin:6px 10px 8px;font-size:12.5px;color:var(--mut);font-weight:700;letter-spacing:.02em}
.st-cats a{display:flex;align-items:center;gap:10px;padding:10px 12px;margin-bottom:3px;border-radius:13px;color:var(--ink);font-weight:600;font-size:14.5px;transition:.15s}
.st-cats a:hover{background:#f1f4fc;text-decoration:none}
.st-cats a .ci{width:32px;height:32px;border-radius:10px;display:grid;place-items:center;background:var(--c1);color:var(--c3);flex:none}
.st-cats a .ci svg{width:17px;height:17px}
.st-cats a em{margin-inline-start:auto;font-style:normal;background:#eef1fa;color:var(--mut);border-radius:99px;padding:0 9px;font-size:12px;line-height:22px}
.st-cats a.on{background:linear-gradient(90deg,#4f46e5,#6d5efc);color:#fff;box-shadow:0 12px 22px -12px #6d5efc}
.st-cats a.on .ci{background:#ffffff26;color:#fff}.st-cats a.on em{background:#ffffff30;color:#fff}
.st-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(225px,1fr));gap:16px}
.st-card{background:#fff;border:1px solid var(--line);border-radius:22px;overflow:hidden;box-shadow:var(--sh);display:flex;flex-direction:column;transition:.25s}
.st-card:hover{transform:translateY(-4px);box-shadow:0 24px 44px -24px #0f172a66}
.st-card.out{opacity:.72}
.st-card .pm{height:132px}
.st-b{padding:12px 14px 6px;flex:1}
.st-n{font-weight:700;font-size:15px;line-height:1.4;display:flex;align-items:center;gap:7px}
.st-n .dot{width:12px;height:12px;border-radius:50%;border:1px solid #0002;flex:none}
.st-m{color:var(--mut);font-size:12.5px;margin-top:2px}
.st-pr{display:flex;align-items:baseline;justify-content:space-between;margin-top:8px}
.st-pr b{font-size:20px;color:var(--br)}.st-pr small{font-size:12.5px}
.st-in{display:inline-block;margin-top:6px;background:#e7f8ef;color:#047857;font-weight:700;font-size:12px;border-radius:99px;padding:1px 10px}
.st-f{display:flex;gap:6px;padding:8px 12px 14px;align-items:center}
.st-f form{display:flex;gap:6px;align-items:center;width:100%;margin:0}
.st-q{display:inline-flex;align-items:center;border:1px solid #d3d9e8;border-radius:11px;overflow:hidden;background:#fff;flex:none}
.st-q button{margin:0;padding:0;width:30px;height:36px;border-radius:0;background:#f1f4fb;color:var(--ink)!important;box-shadow:none;justify-content:center;font-size:17px}
.st-q button:before{display:none}
.st-q input{width:42px;margin:0;border:0;border-radius:0;text-align:center;padding:7px 0;font-weight:700;-moz-appearance:textfield}
.st-q input::-webkit-outer-spin-button,.st-q input::-webkit-inner-spin-button{-webkit-appearance:none;margin:0}
.st-add{flex:1;margin:0;padding:9px 8px;justify-content:center;font-size:14px;white-space:nowrap}
.st-add[disabled]{background:#e4e8f1!important;color:#94a3b8!important;box-shadow:none;cursor:not-allowed;transform:none}
.st-sec{display:flex;align-items:center;gap:10px;margin:2px 2px 12px}.st-sec h3{margin:0}.st-sec span{color:var(--mut);font-size:13px}
@media(max-width:900px){.st-wrap{grid-template-columns:1fr}.st-cats{position:static;display:flex;gap:6px;overflow-x:auto;padding:8px}.st-cats h4{display:none}.st-cats a{flex:none;margin:0;white-space:nowrap}.st-cats a em{margin-inline-start:6px}}
/* السلة */
.ct-wrap{display:grid;grid-template-columns:minmax(0,1fr) 380px;gap:18px;align-items:start}
.ct-wrap .card{margin-bottom:0}
.ct-table td{vertical-align:middle}.ct-table input{margin:0}.ct-table .qi{width:74px;text-align:center}.ct-table .pi{width:96px;text-align:center}
.ct-pan{position:sticky;top:84px}
.ct-pan h3{display:flex;align-items:center;gap:8px}
.ct-pan label{display:block;font-size:13px;font-weight:600;color:var(--mut);margin-top:12px}
.ct-pan input:not([type=radio]):not([type=checkbox]),.ct-pan select,.ct-pan textarea{display:block;width:100%;margin:5px 0 0;font:inherit;padding:9px 12px;border:1px solid #d3d9e8;border-radius:10px;background:#fff}
.ct-sum{border:1px solid var(--line);border-radius:16px;overflow:hidden;margin-top:14px}
.ct-sum div{display:flex;justify-content:space-between;padding:9px 14px;border-top:1px solid var(--line);font-size:14px}.ct-sum div:first-child{border:0}
.ct-sum .net{background:linear-gradient(135deg,var(--navy),#2a3190);color:#fff;font-size:17px;font-weight:800}
.ct-sum .rm b{color:var(--red)}
.pay{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:6px}
.pay label{margin:0;border:1.5px solid var(--line);border-radius:12px;padding:10px;text-align:center;cursor:pointer;color:var(--ink);font-weight:700;transition:.15s}
.pay input{position:absolute;opacity:0;pointer-events:none}
.pay label:has(input:checked){border-color:var(--br);background:#eef0ff;color:var(--br)}
.ct-pan h3 svg,.ct-go svg,.st-add svg,.st-cart svg,.st-sec svg{width:19px;height:19px;flex:none}
.ct-go{width:100%;justify-content:center;margin:14px 0 0;padding:13px;font-size:16px}
.ct-empty{text-align:center;padding:50px 10px;color:var(--mut)}.ct-empty svg{width:64px;height:64px;opacity:.35}
@media(max-width:1000px){.ct-wrap{grid-template-columns:1fr}.ct-pan{position:static}}
</style>"""

T_STORE = r"""{% extends 'base' %}{% block c %}""" + STORE_CSS + r"""
<div class=st-top>
<label class=search>{{ic.sr}}<input id=stq placeholder="ابحث باسم المنتج أو اللون أو الجهاز..." autocomplete=off></label>
<select id=stb aria-label="الجهاز"><option value="">كل الأجهزة{% for b in brands %}<option>{{b}}{% endfor %}</select>
<select id=sts aria-label="الترتيب"><option value="">ترتيب: الافتراضي<option value="name">الاسم (أ ← ي)<option value="pa">السعر: الأقل<option value="pd">السعر: الأعلى<option value="sd">المتوفر: الأكثر</select>
<label class=st-chk><input type=checkbox id=sto> المتوفر فقط</label>
<a class="btn st-cart" href=/store/cart>{{ic.ct}} السلة <span class=bd id=cartn>{{cart_n}}</span><small id=cartt style="color:#fff;opacity:.85">{{ '%g'|format(cart_total) }} ₪</small></a>
</div>
<div class=st-wrap>
<nav class=st-cats aria-label="تصنيفات المنتجات"><h4>التصنيفات</h4>
<a href=/store class="{{'on' if not cat}}"><span class="ci k5"><svg viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2 stroke-linecap=round stroke-linejoin=round><path d="M3 3h7v7H3zM14 3h7v7h-7zM14 14h7v7h-7zM3 14h7v7H3z"/></svg></span>كل المنتجات<em>{{total}}</em></a>
{% for c in cats %}<a href="/store?cat={{c|urlencode}}" class="{{'on' if cat==c}}"><span class="ci k{{kc.get(c,5)}}">{{cic.get(c,cic['أخرى'])}}</span>{{cplural.get(c,c)}}<em>{{cnt[c]}}</em></a>{% endfor %}
<a href="/store?cat=tools" class="{{'on' if cat=='tools'}}"><span class="ci k3">{{cic['أدوات الصيانة']}}</span>أدوات الصيانة<em>{{tools_n}}</em></a>
<h4 style="margin-top:14px">روابط سريعة</h4>
<a href=/store/cart><span class="ci k1">{{ic.ct}}</span>سلة المشتريات<em id=cartn2>{{cart_n}}</em></a>
<a href=/sales><span class="ci k4"><svg viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2 stroke-linecap=round stroke-linejoin=round><path d="M6 2h9l5 5v15H6zM14 2v6h6M9 13h8M9 17h8"/></svg></span>فواتير البيع</a>
<a href=/parts?new=1><span class="ci k2"><svg viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2 stroke-linecap=round stroke-linejoin=round><path d="M12 5v14M5 12h14"/></svg></span>إضافة منتج جديد</a>
</nav>
<div>
<div class=st-sec><h3>{{ 'أدوات الصيانة' if cat=='tools' else (cplural.get(cat,cat) if cat else 'كل المنتجات') }}</h3><span id=stcount>{{rows|length}} منتج</span></div>
{% if not rows %}<div class="card em">ما في منتجات بهالتصنيف لسا. أضفها من <a href="{{ '/tools' if cat=='tools' else '/parts?new=1' }}">{{ 'أدوات الصيانة' if cat=='tools' else 'قطع الغيار' }}</a>.</div>{% endif %}
<div class=st-grid id=stg>
{% for p in rows %}{% set n = incart.get(p.key, 0) %}
<div class="st-card{{' out' if p.qty<=0}}" data-s="{{p.name}} {{p.maker or ''}} {{p.color or ''}} {{p.category}} {{p.brand}}" data-brand="{{p.brand}}" data-price="{{p.price}}" data-stock="{{p.qty}}" data-name="{{p.name}}" data-i="{{loop.index}}">
<div class="pm k{{kc.get(p.category,5)}}">{% if p.photo %}<img src="{{p.purl}}" alt="" loading=lazy>{% else %}{{cic.get(p.category,cic['أخرى'])}}{% endif %}<span class=cb>{{p.category}}</span><span class="pill ss {{'s3' if p.qty<=0 else 's0' if p.qty<=p.min_qty else 's2'}}">{{'نفد' if p.qty<=0 else 'منخفض' if p.qty<=p.min_qty else 'متوفر'}}</span></div>
<div class=st-b><div class=st-n>{% if p.hex %}<span class=dot style="background:{{p.hex}}"></span>{% endif %}<span>{{p.name}}{{ ' · '+p.color if p.color }}{% if p.maker %} <small style="background:#eef2ff;color:#4338ca;padding:1px 8px;border-radius:99px;font-weight:700">{{p.maker}}</small>{% endif %}</span></div>
<div class=st-m>{{ p.brand if p.brand != 'أخرى' else p.category }}</div>
<div class=st-pr><b>{{ '%g'|format(p.price) }} ₪</b><small>المتوفر: <b style="font-size:13px;color:inherit">{{p.qty}}</b></small></div>
<span class=st-in id="in{{p.key}}" {{'hidden' if not n}}>في السلة: <span>{{n}}</span></span></div>
<div class=st-f><form class=ad method=post action=/store/cart/add><input type=hidden name=pid value="{{p.key}}"><input type=hidden name=back value="{{request.full_path}}">
<div class=st-q><button type=button data-d=-1 aria-label="إنقاص">−</button><input name=qty type=number value=1 min=1 max="{{p.qty}}" {{'disabled' if p.qty<=0}} aria-label="الكمية"><button type=button data-d=1 aria-label="زيادة">+</button></div>
<button class=st-add {{'disabled' if p.qty<=0}}>{{ic.ct}} {{'نفد المخزون' if p.qty<=0 else 'أضف للسلة'}}</button></form></div></div>
{% endfor %}</div>
<div class="card em" id=stnores hidden>ما في نتائج مطابقة للبحث.</div>
</div></div>
<script>(function(){
function norm(x){return (x||'').toLowerCase().replace(/[ً-ٟ]/g,'').replace(/[أإآ]/g,'ا').replace(/ى/g,'ي').replace(/ة/g,'ه')}
var g=document.getElementById('stg'),q=document.getElementById('stq'),b=document.getElementById('stb'),s=document.getElementById('sts'),o=document.getElementById('sto'),cnt=document.getElementById('stcount'),nr=document.getElementById('stnores');
function run(){if(!g)return;var v=norm(q.value.trim()),cards=[].slice.call(g.children),n=0;
cards.forEach(function(c){var ok=(!v||norm(c.dataset.s).indexOf(v)>-1)&&(!b.value||c.dataset.brand===b.value)&&(!o.checked||+c.dataset.stock>0);c.style.display=ok?'':'none';if(ok)n++});
var k=s.value;cards.sort(function(x,y){var a=x.dataset,d=y.dataset;
if(k==='name')return a.name.localeCompare(d.name,'ar');if(k==='pa')return a.price-d.price;if(k==='pd')return d.price-a.price;if(k==='sd')return d.stock-a.stock;return a.i-d.i}).forEach(function(c){g.appendChild(c)});
if(cnt)cnt.textContent=n+' منتج';if(nr)nr.hidden=n>0||!cards.length}
[q,b,s,o].forEach(function(e){e.addEventListener('input',run);e.addEventListener('change',run)});
document.addEventListener('click',function(e){var d=e.target.closest('.st-q button');if(!d)return;var i=d.parentNode.querySelector('input');if(i.disabled)return;
var v=(parseInt(i.value)||1)+parseInt(d.dataset.d),mx=parseInt(i.max)||1;i.value=Math.max(1,Math.min(mx,v))});
function fmt(n){return (Math.round(n*100)/100).toString()}
function toast(t,m,k){var box=document.getElementById('tc');if(!box)return;var d=document.createElement('div');d.className='toast '+k;d.setAttribute('role','status');
d.innerHTML='<span class=ti><svg width=16 height=16 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2.4 stroke-linecap=round stroke-linejoin=round>'+(k==='ok'?'<path d="M5 12.5l4.5 4.5L19 7.5"/>':'<path d="M12 3l10 18H2zM12 10v5M12 18h.01"/>')+'</svg></span><div class=tb><b></b><span></span></div>';
d.querySelector('b').textContent=t;d.querySelector('span:last-child').textContent=m;box.appendChild(d);setTimeout(function(){d.remove()},4600)}
document.addEventListener('submit',function(e){var f=e.target.closest('form.ad');if(!f||!window.fetch)return;e.preventDefault();
fetch(f.action,{method:'POST',body:new FormData(f),headers:{'X-Requested-With':'fetch'},credentials:'same-origin'}).then(function(r){return r.json()}).then(function(j){
if(j.msg)toast(j.ok?'أُضيف للسلة':'تنبيه',j.msg,j.ok?'ok':'warn');
if(j.count!=null){['cartn','cartn2'].forEach(function(id){var x=document.getElementById(id);if(x)x.textContent=j.count});var t=document.getElementById('cartt');if(t)t.textContent=fmt(j.total)+' ₪'}
if(j.pid){var w=document.getElementById('in'+j.pid);if(w){w.hidden=!j.incart;w.querySelector('span').textContent=j.incart}}
}).catch(function(){f.submit()})});
})();</script>{% endblock %}"""

T_CART = r"""{% extends 'base' %}{% block c %}""" + STORE_CSS + r"""
{% if not items %}<div class="card ct-empty"><svg viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=1.6 stroke-linecap=round stroke-linejoin=round><path d="M9 21a1 1 0 100-2 1 1 0 000 2zM20 21a1 1 0 100-2 1 1 0 000 2zM1 1h4l2.7 13.4a2 2 0 001.6 1.6h9.7a2 2 0 002-1.6L23 6H6"/></svg>
<h3 style="margin-top:10px">السلة فاضية</h3><p>اختر منتجات من المتجر وأضفها للسلة، وبعدها بتختار الشخص وبتطلع الفاتورة.</p><a class=btn href=/store>الذهاب للمتجر</a></div>
{% else %}
<form method=post action=/store/cart/checkout id=cf autocomplete=off>
<div class=ct-wrap>
<div class=card style="padding:0"><div style="padding:16px 18px 0;display:flex;align-items:center;gap:10px"><h3 style="margin:0">المنتجات المختارة ({{items|length}})</h3><span style="flex:1"></span><a class="btn ghost" href=/store>+ إضافة منتجات</a></div>
<div style="overflow-x:auto;padding:8px 10px 14px"><table class=ct-table><tr><th><th>المنتج<th>سعر الوحدة (₪)<th>الكمية<th>المجموع<th></tr>
{% for it in items %}<tr><td>{% if it.photo %}<img class=th src="{{it.purl}}" alt="">{% else %}<span class=th style="display:grid;place-items:center;color:var(--mut)">{{cic.get(it.category,cic['أخرى'])}}</span>{% endif %}
<td><b>{{it.label}}</b><br><small>{{it.category}} · المتوفر {{it.stock}}</small>{% if it.qty>it.stock %}<br><span class="pill s3">الكمية أكبر من المتوفر</span>{% endif %}
<td><input class=pi type=number step=any min=0 name="p_{{it.key}}" value="{{ '%g'|format(it.price) }}" data-cost="{{it.cost}}" aria-label="السعر">
<td><input class=qi type=number min=1 max="{{it.stock}}" name="q_{{it.key}}" value="{{it.qty}}" aria-label="الكمية">
<td class=nw><b class=lt>0</b> ₪
<td><button class="ib dl" name=rm value="{{it.key}}" formaction=/store/cart/remove formnovalidate title="إزالة من السلة" aria-label="إزالة">{{ic.dl}}</button></tr>{% endfor %}</table></div>
<div style="padding:0 18px 16px;display:flex;gap:8px;flex-wrap:wrap"><button class=ghost formaction=/store/cart/update formnovalidate>تحديث الكميات</button><button class=ghost formaction=/store/cart/clear formnovalidate onclick="return confirm('تفريغ السلة؟')">تفريغ السلة</button></div></div>
<div class="card ct-pan"><h3>{{ic.ph}} إتمام البيع</h3>
<label>الشخص المشتري <span style="color:var(--red)">*</span>
<select name=person_id id=pp>{% if people %}<option value="">— اختر شخصاً —{% endif %}{% for r in people %}<option value={{r.id}} {{'selected' if sel==r.id}}>{{r.name}}{% if r.phone %} · {{r.phone}}{% endif %}{% if r.rem>0 %} (عليه {{ '%g'|format(r.rem) }} ₪){% endif %}{% endfor %}<option value="new" {{'selected' if not people}}>＋ شخص جديد...</select></label>
<div id=np {{'hidden' if people}}><label>اسم الشخص الجديد<input name=person_name placeholder="مثال: محل الأمين للاتصالات"></label><label>رقم الهاتف<input name=phone type=tel dir=ltr inputmode=tel></label></div>
<label style="margin-top:14px">طريقة الدفع</label><div class=pay><label><input type=radio name=method value="نقدي" checked>💵 نقدي</label><label><input type=radio name=method value="دين">📒 دين (آجل)</label></div>
<div id=pdw hidden><label>دفعة مقدّمة الآن (₪) — اختياري<input type=number step=any min=0 name=paid value=0 id=paid></label></div>
<label>خصم (₪)<input type=number step=any min=0 name=discount value=0 id=disc></label>
<label>ملاحظة على الفاتورة<input name=note placeholder="اختياري"></label>
<div class=ct-sum><div><span>عدد القطع</span><b id=sq>0</b></div><div><span>المجموع</span><b id=ss>0 ₪</b></div><div><span>الخصم</span><b id=sd>0 ₪</b></div><div class=net><span>الصافي</span><b id=st>0 ₪</b></div><div><span>المربح</span><b id=spf style="color:#059669">0 ₪</b></div><div class=rm id=rmw hidden><span>المتبقي دين</span><b id=sr>0 ₪</b></div></div>
<button class=ct-go>{{ic.sh}} تأكيد البيع وإنشاء الفاتورة</button></div></div></form>
<script>(function(){
var f=document.getElementById('cf');function $(i){return document.getElementById(i)}function fm(n){return (Math.round(n*100)/100).toLocaleString('en-US')}
function calc(){var sub=0,qt=0,cst=0;f.querySelectorAll('.ct-table tr').forEach(function(r){var p=r.querySelector('.pi'),q=r.querySelector('.qi');if(!p)return;var t=(parseFloat(p.value)||0)*(parseInt(q.value)||0);r.querySelector('.lt').textContent=fm(t);sub+=t;qt+=parseInt(q.value)||0;cst+=(parseFloat(p.dataset.cost)||0)*(parseInt(q.value)||0)});
var d=Math.min(Math.max(parseFloat($('disc').value)||0,0),sub),net=sub-d,debt=f.method.value==='دين',pd=debt?Math.min(Math.max(parseFloat($('paid').value)||0,0),net):net;
$('spf').textContent=fm(net-cst)+' ₪';$('spf').style.color=(net-cst)>=0?'#059669':'#e11d48';$('sq').textContent=qt;$('ss').textContent=fm(sub)+' ₪';$('sd').textContent=fm(d)+' ₪';$('st').textContent=fm(net)+' ₪';$('rmw').hidden=!debt;$('sr').textContent=fm(net-pd)+' ₪';$('pdw').hidden=!debt}
f.addEventListener('input',calc);f.addEventListener('change',calc);
$('pp').addEventListener('change',function(){$('np').hidden=this.value!=='new'});calc();
f.addEventListener('submit',function(e){var b=e.submitter;if(b&&b.getAttribute('formaction'))return;var v=$('pp').value;if(!v){e.preventDefault();alert('اختر الشخص اللي بدك تبيعه');$('pp').focus();return}
if(v==='new'&&!f.person_name.value.trim()){e.preventDefault();alert('اكتب اسم الشخص الجديد');f.person_name.focus()}})})();</script>
{% endif %}{% endblock %}"""

T_SALES = r"""{% extends 'base' %}{% block c %}
<div class=sg4>
<div class=sc><span class="si a">#</span><div><small>عدد الفواتير</small><b>{{S.n}}</b></div></div>
<div class=sc><span class="si c">₪</span><div><small>مبيعات اليوم</small><b>{{ '%g'|format(S.today) }} ₪</b></div></div>
<div class=sc><span class="si b">₪</span><div><small>مبيعات الشهر</small><b>{{ '%g'|format(S.month) }} ₪</b></div></div>
<div class=sc><span class="si e">₪</span><div><small>ربح اليوم</small><b>{{ '%g'|format(S.profit_today) }} ₪</b></div></div>
<div class=sc><span class="si e">₪</span><div><small>ربح الشهر</small><b>{{ '%g'|format(S.profit) }} ₪</b></div></div>
<div class=sc><span class="si d">₪</span><div><small>ديون الفواتير (متبقي)</small><b>{{ '%g'|format(S.rem) }} ₪</b></div></div></div>
<div class=tools><div class=r1><label class=search>{{ic.sr}}<input data-tsearch=stbl placeholder="ابحث برقم الفاتورة أو اسم الشخص..."></label><span style="flex:1"></span><a class=btn href=/store>{{ic.ct}} فاتورة جديدة (المتجر)</a></div></div>
<div class=card><table id=stbl><tr><th>رقم الفاتورة<th>التاريخ<th>الشخص<th>القطع<th>الصافي<th>المربح<th>المدفوع<th>المتبقي<th>الدفع<th></tr>
{% for r in rows %}<tr><td><a href=/sales/{{r.id}}><b dir=ltr>SALE-{{'%04d'|format(r.id)}}</b></a><td class=nw dir=ltr>{{r.created}}
<td>{% if r.person_id %}<a href=/people/{{r.person_id}}>{{r.person_name}}</a>{% else %}{{r.person_name}}{% endif %}{% if r.person_phone %}<br><small dir=ltr>{{r.person_phone}}</small>{% endif %}
<td>{{r.pcs}}<td class=nw><b>{{ '%g'|format(r.total) }} ₪</b><td class=nw><b style="color:{{ '#059669' if r.profit>=0 else '#e11d48' }}">{{ '%g'|format(r.profit) }} ₪</b><td class=nw>{{ '%g'|format(r.paid) }} ₪<td class=nw>{% if r.total-r.paid>0.004 %}<span class="pill s3">{{ '%g'|format(r.total-r.paid) }} ₪</span>{% else %}—{% endif %}
<td><span class="pill {{'s2' if r.method=='نقدي' else 's0'}}">{{r.method}}</span>
<td><div class=sa><a class=ib href=/sales/{{r.id}} title="عرض الفاتورة A4" aria-label="عرض">{{ic.eye}}</a><a class=ib target=_blank href=/sales/{{r.id}}/thermal title="طباعة حرارية" aria-label="طباعة حرارية">{{ic.pr}}</a>
<form method=post action=/sales/{{r.id}}/delete onsubmit="return confirm('إلغاء الفاتورة؟ بترجع القطع للمخزون وبينحذف الدين المرتبط فيها.')"><button class="ib dl" title="إلغاء الفاتورة" aria-label="إلغاء">{{ic.dl}}</button></form></div></tr>
{% else %}<tr><td colspan=10 class=em>ما في فواتير بيع لسا. افتح "تصنيفات المنتجات"، أضف قطع للسلة وأكمل البيع.</tr>{% endfor %}</table></div>{% endblock %}"""

# فاتورة A4: نفس تصميم a4doc (بنستعير الـ CSS منه) مع بيانات الزبون والخصم والمدفوع والمتبقي
T_SALE_A4 = r"""{% set doc_title = 'فاتورة بيع' %}{% include 'a4css' %}
<div class=bar><button type=button onclick="history.length>1?history.back():location.href='/sales'">← رجوع</button><button onclick="print()">طباعة / حفظ PDF</button><a href="/sales/{{s.id}}/thermal"><button type=button>نسخة حرارية</button></a><span style="margin-inline-start:12px;padding:6px 14px;border-radius:99px;background:{{ '#d1fae5' if profit>=0 else '#ffe4e6' }};color:{{ '#047857' if profit>=0 else '#be123c' }};font-weight:700;font-size:14px" title="ما بيظهر بالطباعة">مربح هالفاتورة: {{ '%g'|format(profit) }} ₪</span>{% if not tb_logo %}<a class=hint href=/settings>أضف شعار شركتك من الإعدادات ليظهر هنا</a>{% endif %}</div>
<div class=sheet>
<div class=hd3><div class=hr><h1 class=tt>فاتورة بيع</h1><div class=rf dir=ltr>{{ref}}</div></div><div class=hc>{% if tb_logo %}<img src="/shoplogo?v={{tb_logo}}" alt="">{% endif %}<div class=nm>{{st.shop_name}}</div>{% if st.address %}<div class=adr>{{st.address}}</div>{% endif %}</div><div class=hl dir=ltr>{{s.created}}</div></div>
<div class=info><div><span>المشتري: </span><b>{{s.person_name or '—'}}</b></div><div><span>الهاتف: </span><b dir=ltr>{{s.person_phone or '—'}}</b></div><div><span>التاريخ: </span><b dir=ltr>{{s.created}}</b></div><div><span>الدفع: </span><b>{{s.method}} · {{lines|length}} بند · {{pcs}} قطعة</b></div></div>
<table class=items><thead><tr><th class=n>#<th>الصنف<th>الكمية<th class=num>سعر الوحدة<th class=num>المجموع</tr></thead><tbody>
{% for l in lines %}<tr><td class=n>{{l.n}}<td>{{l.name}}<span class=dt2>{{l.category}}</span><td>{{l.qty}}<td class=num>{{ '%g'|format(l.price) }} ₪<td class=num>{{ '%g'|format(l.total) }} ₪</tr>{% endfor %}</tbody></table>
<table class=sum><tr><td>المجموع<td class=num dir=ltr>{{ '%g'|format(s.subtotal) }} ₪</tr>{% if s.discount %}<tr><td>الخصم<td class=num dir=ltr>-{{ '%g'|format(s.discount) }} ₪</tr>{% endif %}
<tr class=net><td>الصافي<td class=num dir=ltr>{{ '%g'|format(s.total) }} ₪</tr><tr><td>المدفوع<td class=num dir=ltr>{{ '%g'|format(s.paid) }} ₪</tr>{% if s.total-s.paid>0.004 %}<tr><td>المتبقي (دين)<td class=num dir=ltr>{{ '%g'|format(s.total-s.paid) }} ₪</tr>{% endif %}</table>
<div class=note>{{ s.note if s.note else 'يرجى فحص القطع عند الاستلام، وأي ملاحظة تُبلَّغ خلال 48 ساعة من تاريخ الفاتورة.' }}{% if bal is not none and bal>0.004 %}<br><b>إجمالي المتبقي على حساب {{s.person_name}} حالياً: {{ '%g'|format(bal) }} ₪</b>{% endif %}</div>
</div>
<script>if(/[?&]auto=1/.test(location.search))window.addEventListener('load',function(){setTimeout(print,300)});</script></html>"""

T_SALE_TH = r"""<!doctype html><html lang=ar dir=rtl><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>فاتورة بيع {{ref}}</title>
{% include 'thcss' %}
<div class=bar><button type=button onclick="history.length>1?history.back():location.href='/sales'">← رجوع</button><button onclick="print()">طباعة</button><button onclick="sw('w80')">ورق 80 مم</button><button onclick="sw('w58')">ورق 58 مم</button><a href="/sales/{{s.id}}"><button type=button>نسخة A4</button></a></div>
<div class=tk>
<span class=ttl>فاتورة بيع</span><div class=ref dir=ltr>{{ref}}</div>
<div class=head><span class=lg>{{thic.store}}</span><h1 class=shop>{{st.shop_name}}</h1></div>{% if st.address %}<div style="text-align:center;font-size:11px;margin:2px 0 4px">{{st.address}}</div>{% endif %}
<div class=inf>
<div class=f><span class=k>{{thic.user}}المشتري</span><span class=dl></span><span class=v>{{s.person_name or '—'}}</span></div>
{% if s.person_phone %}<div class=f><span class=k>{{thic.phone}}الهاتف</span><span class=dl></span><span class=v dir=ltr>{{s.person_phone}}</span></div>{% endif %}
<div class=f><span class=k>{{thic.cal}}التاريخ</span><span class=dl></span><span class=v dir=ltr>{{s.created}}</span></div></div>
<table><colgroup><col class=cn style="width:8%"><col style="width:38%"><col style="width:14%"><col style="width:18%"><col style="width:22%"></colgroup>
<tr><th class=cn>#<th>الصنف<th>الكمية<th>السعر<th>المجموع</tr>
{% for l in lines %}<tr><td class=cn>{{l.n}}<td class=nm>{{l.name}}<td>{{l.qty}}<td dir=ltr>{{ '%g'|format(l.price) }}<td dir=ltr>{{ '%g'|format(l.total) }}</tr>{% endfor %}</table>
<table class=sum><tr><td class=k>عدد القطع<td dir=ltr>{{pcs}}</tr>
{% if s.discount %}<tr><td class=k>المجموع<td dir=ltr>{{ '%g'|format(s.subtotal) }} ₪</tr><tr><td class=k>الخصم<td dir=ltr>-{{ '%g'|format(s.discount) }} ₪</tr>{% endif %}
<tr><td class=k>الدفع<td>{{s.method}}</tr><tr><td class=k>المدفوع<td dir=ltr>{{ '%g'|format(s.paid) }} ₪</tr>
{% if s.total-s.paid>0.004 %}<tr><td class=k>المتبقي دين<td dir=ltr>{{ '%g'|format(s.total-s.paid) }} ₪</tr>{% endif %}</table>
<div class=tot><span>الصافي</span><b>{{ '%g'|format(s.total) }} ₪</b></div>
{% if s.note %}<div class=nt>{{s.note}}</div>{% endif %}
<div class=ft>شكراً لتعاملكم معنا</div><div class=cut><span>✂</span></div></div></html>"""

T_TOOLS = r"""{% extends 'base' %}{% block c %}
<style>
.tl-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(235px,1fr));gap:18px}
.tl-card{background:#fff;border:1px solid var(--line);border-radius:22px;overflow:hidden;box-shadow:var(--sh);display:flex;flex-direction:column;transition:.25s}
.tl-card:hover{transform:translateY(-4px);box-shadow:0 24px 44px -24px #0f172a66}
.tl-img{height:170px;position:relative;display:grid;place-items:center;background:linear-gradient(135deg,#eef0ff,#dfe4ff);color:#4f46e5;cursor:zoom-in}
.tl-img img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}.tl-img>svg{width:56px;height:56px;opacity:.7}.tl-img.no{cursor:default}
.tl-img .cb{max-width:70%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tl-b{padding:13px 15px 6px;flex:1}.tl-b h4{margin:0;font-size:16px}.tl-b p{margin:5px 0 0;color:var(--mut);font-size:13px;line-height:1.5}
.tl-meta{display:flex;gap:6px;flex-wrap:wrap;margin-top:9px}.tl-meta span{background:#f1f4fb;border-radius:99px;padding:1px 10px;font-size:12.5px;font-weight:600;color:#475569}
.tl-f button svg{width:17px;height:17px}
.tl-f{display:flex;gap:4px;padding:8px 12px 14px;align-items:center}
#imgv{border:0;padding:0;background:transparent;max-width:94vw;max-height:94vh}#imgv::backdrop{background:#0c1233dd}#imgv img{max-width:92vw;max-height:88vh;border-radius:16px;display:block}
#imgv .cl{position:absolute;top:8px;left:8px;background:#000a!important}
.xlb{display:inline-flex;align-items:center;gap:7px;white-space:nowrap}
</style>
<div class=sg4>
<div class=sc><span class="si a"><svg width=24 height=24 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=1.9 stroke-linecap=round stroke-linejoin=round><path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z"/></svg></span><div><small>عدد الأدوات</small><b>{{rows|length}}</b></div></div>
<div class=sc><span class="si b">#</span><div><small>مجموع القطع</small><b>{{ST.qty}}</b></div></div>
<div class=sc><span class="si c">₪</span><div><small>قيمة الأدوات</small><b>{{ '%g'|format(ST.val) }} ₪</b></div></div>
<div class=sc><span class="si e"><svg width=24 height=24 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=1.9 stroke-linecap=round stroke-linejoin=round><path d="M3 5h18v14H3zM3 16l5-5 4 4 3-3 6 6"/></svg></span><div><small>أدوات بصور</small><b>{{ST.imgs}}</b></div></div></div>
<div class=tools><div class=r1><label class=search>{{ic.sr}}<input id=tq placeholder="ابحث باسم الأداة أو تصنيفها أو مكانها..." autocomplete=off></label><span style="flex:1"></span><a class="btn ghost xlb" href=/tools/import title="استيراد أدوات من ملف Excel" aria-label="استيراد من Excel"><svg width=20 height=20 viewBox="0 0 24 24" aria-hidden=true><rect x=2.5 y=2.5 width=19 height=19 rx=4 fill=#16a34a /><path d="M8.5 8.5l7 7M15.5 8.5l-7 7" stroke=#fff stroke-width=2 stroke-linecap=round fill=none /></svg> استيراد Excel</a><button type=button data-open=dlg-tool data-act=/tools>+ إضافة أداة</button></div>
{% if cats %}<div class=cats style="padding:6px 0 0"><button type=button class="cpill on" data-tc="">كل الأدوات <em>{{rows|length}}</em></button>{% for c,n in cats %}<button type=button class=cpill data-tc="{{c}}">{{c}} <em>{{n}}</em></button>{% endfor %}</div>{% endif %}</div>
{% if not rows %}<div class="card em">ما أضفت أي أداة لسا. اضغط "إضافة أداة" وارفع صورة لها.</div>{% endif %}
<div class=tl-grid id=tg>
{% for t in rows %}<div class=tl-card data-s="{{t.name}} {{t.category or ''}} {{t.location or ''}} {{t.notes or ''}} {{t.barcode or ''}}" data-c="{{t.category or ''}}">
<div class="tl-img{{'' if t.photo else ' no'}}" {% if t.photo %}data-zoom="/toolphoto/{{t.photo}}"{% endif %}>{% if t.photo %}<img src=/toolphoto/{{t.photo}} alt="{{t.name}}" loading=lazy>{% else %}<svg viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=1.6 stroke-linecap=round stroke-linejoin=round><path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z"/></svg>{% endif %}{% if t.category %}<span class=cb>{{t.category}}</span>{% endif %}</div>
<div class=tl-b><h4>{{t.name}}</h4>{% if t.barcode %}<div class=bcc><a href="/barcodes?ids=t{{t.id}}" title="طباعة ملصق باركود" style="text-decoration:none">▮▯ {{t.barcode}}</a></div>{% endif %}{% if t.notes %}<p>{{t.notes}}</p>{% endif %}
<div class=tl-meta><span>العدد: {{t.qty}}</span>{% if t.price %}<span>بيع: {{ '%g'|format(t.price) }} ₪</span>{% elif t.cost %}<span>{{ '%g'|format(t.cost) }} ₪</span>{% endif %}{% if t.location %}<span>📍 {{t.location}}</span>{% endif %}</div></div>
<div class=tl-f><button type=button class=ghost style="flex:1;justify-content:center;margin:0" data-open=dlg-tool data-act=/tools/{{t.id}}/edit data-fill='{{ {"_t":"تعديل أداة","name":t.name,"category":t.category or "","qty":t.qty,"cost":t.cost or 0,"price":t.price or 0,"location":t.location or "","notes":t.notes or ""}|tojson }}'>{{ic.ed}} تعديل</button>
<form method=post action=/tools/{{t.id}}/delete class=il onsubmit="return confirm('حذف الأداة؟')"><button class="ib dl" title="حذف" aria-label="حذف">{{ic.dl}}</button></form></div></div>{% endfor %}</div>
<div class="card em" id=tno hidden>ما في نتائج.</div>
<dialog class=dlg id=dlg-tool><form method=post action=/tools enctype=multipart/form-data>
<div class=dh><h3>إضافة أداة</h3><button type=button class=cl data-close aria-label="إغلاق">×</button></div>
<div class=db><div class=fg>
<label class=fa>اسم الأداة<input name=name required placeholder="مثال: مفك خماسي / محطة لحام هواء ساخن"></label>
<label>التصنيف<input name=category list=tcats placeholder="مثال: مفكات"><datalist id=tcats>{% for c in tcats %}<option value="{{c}}">{% endfor %}</datalist></label>
<label>العدد<input name=qty type=number min=0 value=1></label>
<label>سعر الشراء (اختياري)<input name=cost type=number step=any min=0 value=0></label><label>سعر البيع (لو بدك تبيعها من المتجر)<input name=price type=number step=any min=0 value=0></label>
<label>مكان الأداة<input name=location placeholder="مثال: الدرج الأول"></label>
<label class=fa>ملاحظات<input name=notes placeholder="مقاس، موديل، حالة..."></label>
<label class=fa>صورة الأداة (JPG / PNG / WEBP)<input name=photo type=file accept="image/*" capture=environment></label></div></div>
<div class=df><button>حفظ</button><button type=button class=ghost data-close>إلغاء</button></div></form></dialog>
<dialog id=imgv><button type=button class=cl data-close aria-label="إغلاق">×</button><img alt=""></dialog>
<script>(function(){
function norm(x){return (x||'').toLowerCase().replace(/[ً-ٟ]/g,'').replace(/[أإآ]/g,'ا').replace(/ى/g,'ي').replace(/ة/g,'ه')}
var cat='',q=document.getElementById('tq');
function run(){var v=norm(q.value.trim()),n=0,all=[].slice.call(document.querySelectorAll('#tg .tl-card'));all.forEach(function(c){var ok=(!v||norm(c.dataset.s).indexOf(v)>-1)&&(!cat||c.dataset.c===cat);c.style.display=ok?'':'none';if(ok)n++});var x=document.getElementById('tno');if(x)x.hidden=n>0||!all.length}
q.addEventListener('input',run);
document.addEventListener('click',function(e){var p=e.target.closest('[data-tc]');if(p){cat=p.dataset.tc;document.querySelectorAll('[data-tc]').forEach(function(x){x.classList.toggle('on',x===p)});run();return}
var o=e.target.closest('[data-open=dlg-tool]');if(o){document.querySelector('#dlg-tool form').action=o.dataset.act||'/tools';return}
var z=e.target.closest('[data-zoom]');if(z){var d=document.getElementById('imgv');d.querySelector('img').src=z.dataset.zoom;d.showModal();return}
if(e.target.id==='imgv')e.target.close()});
})();</script>{% endblock %}"""


# ------------------------------------------------------------------ المسارات
def register(ns):
    """ns = globals() الخاصة بـ app.py (بنستعمل نفس الدوال والمتغيرات)."""
    app, T, q, ex, db, uid, notify = ns["app"], ns["T"], ns["q"], ns["ex"], ns["db"], ns["uid"], ns["notify"]
    save_photo, send_from_directory, UP = ns["save_photo"], ns["send_from_directory"], ns["UP"]
    settings, today, now_s, _i, _f = ns["settings"], ns["today"], ns["now_s"], ns["_i"], ns["_f"]
    CATS, CAT_PLURAL, brand_of, BRAND_ORDER = ns["CATS"], ns["CAT_PLURAL"], ns["brand_of"], ns["BRAND_ORDER"]
    people_rows, person_by_name, person_figs, debtor_or_404 = ns["people_rows"], ns["person_by_name"], ns["person_figs"], ns["debtor_or_404"]
    plabel = ns["plabel"]
    ns["CIC"]["أدوات الصيانة"] = ns["_ic"]("M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z")
    ns["KC"]["أدوات الصيانة"] = 3

    T["store"], T["cart"], T["sales"], T["tools"] = T_STORE, T_CART, T_SALES, T_TOOLS
    T["saleinv"], T["salethermal"] = T_SALE_A4, T_SALE_TH

    def remove_file(name):
        """الصور بتتخزن بجدول files بـ Neon (مش بمجلد)."""
        if name: ns["del_file"](name)

    # ---------- السلة (بالجلسة: {معرّف القطعة: الكمية}) ----------
    def get_cart():
        c = session.get("cart")
        return c if isinstance(c, dict) else {}

    def set_cart(c):
        session["cart"] = c; session.modified = True

    def cart_items(cart=None):
        """مفتاح السلة: رقم القطعة، أو t<رقم> للأداة."""
        cart = get_cart() if cart is None else cart
        out = []
        for key, qty in cart.items():
            tool = str(key).startswith("t"); n = _i(str(key)[1:] if tool else key)
            r = q("select * from tools where id=? and user_id=?" if tool else "select * from parts where id=? and user_id=?", (n, uid()))
            if not r: continue
            p = dict(r[0])
            if tool:
                out.append(dict(key=str(key), kind="tool", id=n, label=p["name"], price=p["price"] or 0, cost=p["cost"] or 0, stock=p["qty"] or 0, photo=p["photo"],
                                purl="/toolphoto/%s" % p["photo"] if p["photo"] else "", category="أدوات الصيانة", min_qty=0, qty=max(1, _i(qty, 1))))
            else:
                out.append(dict(key=str(key), kind="part", id=n, label=plabel(p), price=p["price"] or 0, cost=p["cost"] or 0, stock=p["qty"] or 0, photo=p["photo"],
                                purl="/photo/%s" % p["photo"] if p["photo"] else "", category=p["category"], min_qty=p["min_qty"], qty=max(1, _i(qty, 1))))
        return out

    def cart_totals():
        its = cart_items()
        return sum(i["qty"] for i in its), round(sum(i["qty"] * i["price"] for i in its), 2)

    @app.route("/store")
    def store():
        cat = request.args.get("cat") or None
        if cat not in CATS and cat != "tools": cat = None
        allr = [dict(r, brand=brand_of(r["name"]), key=str(r["id"]), purl="/photo/%s" % r["photo"] if r["photo"] else "") for r in q("select * from parts where user_id=?", (uid(),))]
        trows = [dict(id=r["id"], key="t%d" % r["id"], name=r["name"], color=None, hex=None, category="أدوات الصيانة", brand="أدوات الصيانة", price=r["price"] or 0, cost=r["cost"] or 0,
                      qty=r["qty"] or 0, min_qty=0, photo=r["photo"], purl="/toolphoto/%s" % r["photo"] if r["photo"] else "") for r in q("select * from tools where user_id=? order by name", (uid(),))]
        rows = [r for r in allr if cat != "tools" and (not cat or r["category"] == cat)]
        rows.sort(key=lambda r: (CATS.index(r["category"]) if r["category"] in CATS else 99, BRAND_ORDER.get(r["brand"], 99), r["name"], r["color"] or ""))
        if cat in (None, "tools"): rows += trows
        n, t = cart_totals()
        return render_template("store", rows=rows, cat=cat, cats=CATS, cnt={c: sum(1 for r in allr if r["category"] == c) for c in CATS}, total=len(allr) + len(trows), tools_n=len(trows),
                               brands=sorted({r["brand"] for r in rows}, key=lambda b: BRAND_ORDER.get(b, 99)), cplural=CAT_PLURAL,
                               incart={str(k): v for k, v in get_cart().items()}, cart_n=n, cart_total=t,
                               ttl=("تصنيفات المنتجات", "تصفّح القطع حسب التصنيف، أضف للسلة، اختر الشخص واطلع الفاتورة"))

    @app.post("/store/cart/add")
    def cart_add():
        key = (request.form.get("pid") or "").strip(); qty = max(1, _i(request.form.get("qty"), 1))
        tool = key.startswith("t"); pid = _i(key[1:] if tool else key)
        p = q("select * from tools where id=? and user_id=?" if tool else "select * from parts where id=? and user_id=?", (pid, uid())); ajax = request.headers.get("X-Requested-With") == "fetch"
        cart = get_cart(); ok, msg = False, "المنتج غير موجود"; key = ("t%d" % pid) if tool else str(pid)
        if p:
            p = p[0]; have = _i(cart.get(key), 0); label = p["name"] if tool else plabel(p)
            if (p["qty"] or 0) <= 0: msg = f"{label}: نفد من المخزون"
            else:
                new = min(have + qty, p["qty"]); cart[key] = new; set_cart(cart); ok = True
                msg = f"{label} × {new}" + (f" (المتوفر {p['qty']} فقط)" if have + qty > p["qty"] else "")
        n, t = cart_totals()
        if ajax: return jsonify(ok=ok, msg=msg, count=n, total=t, pid=key, incart=_i(cart.get(key), 0))
        flash(("تمت الإضافة للسلة|" if ok else "تعذّرت الإضافة|") + msg, "ok" if ok else "warn")
        back = request.form.get("back") or "/store"
        return redirect(back if back.startswith("/") and not back.startswith("//") else "/store")

    def _apply_form_qty(cart):
        for k, v in request.form.items():
            if k.startswith("q_"):
                pid = k[2:]
                if pid in cart: cart[pid] = max(1, _i(v, 1))
        return cart

    @app.post("/store/cart/update")
    def cart_update():
        set_cart(_apply_form_qty(get_cart())); flash("تم التحديث|تم تحديث كميات السلة", "ok"); return redirect("/store/cart")

    @app.post("/store/cart/remove")
    def cart_remove():
        cart = _apply_form_qty(get_cart()); cart.pop((request.form.get("rm") or "").strip(), None); set_cart(cart)
        return redirect("/store/cart")

    @app.post("/store/cart/clear")
    def cart_clear():
        set_cart({}); return redirect("/store/cart")

    @app.route("/store/cart")
    def cart_page():
        cart = get_cart(); items = cart_items(cart)
        if len(items) != len(cart): set_cart({i["key"]: i["qty"] for i in items})   # قطع انحذفت من المخزن
        return render_template("cart", items=items, people=people_rows(), sel=_i(request.args.get("person")),
                               ttl=("سلة المشتريات", "راجع المنتجات، اختر الشخص المشتري وطريقة الدفع ثم أنشئ الفاتورة"))

    @app.post("/store/cart/checkout")
    def cart_checkout():
        f = request.form; cart = get_cart(); items = cart_items(cart)
        if not items:
            flash("السلة فاضية|أضف منتجات أول.", "warn"); return redirect("/store")
        lines, errs = [], []
        for it in items:
            qty, price = _i(f.get("q_" + it["key"]), it["qty"]), _f(f.get("p_" + it["key"]), it["price"])
            cart[it["key"]] = max(1, qty)
            if qty < 1: errs.append(f"{it['label']}: كمية غير صحيحة")
            elif qty > it["stock"]: errs.append(f"{it['label']}: المتوفر {it['stock']} فقط")
            elif price < 0: errs.append(f"{it['label']}: سعر غير صحيح")
            else: lines.append((it, qty, round(price, 2)))
        set_cart(cart)
        if errs:
            flash("ما تم البيع|" + " — ".join(errs), "warn"); return redirect("/store/cart")
        # الشخص المشتري (إلزامي)
        pv = f.get("person_id", "")
        if pv == "new":
            nm = (f.get("person_name") or "").strip()
            if not nm: flash("اختر الشخص|اكتب اسم الشخص الجديد.", "warn"); return redirect("/store/cart")
            pid = person_by_name(nm, f.get("phone", ""))
        else:
            pid = _i(pv)
        pr = q("select * from debtors where id=? and user_id=?", (pid, uid())) if pid else []
        if not pr:
            flash("اختر الشخص|لازم تختار الشخص اللي ببيعه قبل إتمام البيع.", "warn"); return redirect("/store/cart")
        pr = pr[0]
        sub = round(sum(qty * price for _, qty, price in lines), 2)
        disc = min(max(_f(f.get("discount")), 0), sub); total = round(sub - disc, 2)
        method = "دين" if f.get("method") == "دين" else "نقدي"
        paid = total if method == "نقدي" else min(max(_f(f.get("paid")), 0), total)
        c = db().execute("insert into sales(user_id,person_id,person_name,person_phone,created,subtotal,discount,total,paid,method,note) values(?,?,?,?,?,?,?,?,?,?,?)",
                         (uid(), pr["id"], pr["name"], pr["phone"] or "", now_s(), sub, disc, total, paid, method, (f.get("note") or "").strip()))
        sid = c.lastrowid
        for it, qty, price in lines:
            tl = it["kind"] == "tool"
            db().execute("insert into sale_items(user_id,sale_id,part_id,tool_id,name,category,qty,price,cost) values(?,?,?,?,?,?,?,?,?)",
                         (uid(), sid, None if tl else it["id"], it["id"] if tl else None, it["label"], it["category"], qty, price, it["cost"]))
            db().execute("update %s set qty=greatest(0,qty-?) where id=? and user_id=?" % ("tools" if tl else "parts"), (qty, it["id"], uid()))
        ref = "SALE-%04d" % sid; summary = "، ".join(f"{qty}×{it['label']}" for it, qty, _ in lines[:4]) + ("..." if len(lines) > 4 else "")
        profit = round(sum(qty * (price - (it["cost"] or 0)) for it, qty, price in lines) - disc, 2)
        if method == "دين":   # الدين بيتسجّل بحساب الشخص، والدفعة المقدّمة (إن وُجدت) بتنزل منه
            db().execute("insert into debt_entries(user_id,debtor_id,kind,amount,method,check_no,bank,due,status,note,created,item,sale_id) values(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (uid(), pr["id"], "دين", total, "", "", "", "", "", f"فاتورة {ref}", today(), summary, sid))
            if paid > 0:
                db().execute("insert into debt_entries(user_id,debtor_id,kind,amount,method,check_no,bank,due,status,note,created,item,sale_id) values(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                             (uid(), pr["id"], "دفعة", paid, "نقد", "", "", "", "", f"دفعة مقدّمة — فاتورة {ref}", today(), "", sid))
        db().commit()
        set_cart({})
        notify(f"{ref} · {pr['name']} · {total:g} ₪ · المربح {profit:g} ₪ · {'نقدي' if method == 'نقدي' else 'دين' + (f' (متبقي {total - paid:g} ₪)' if total - paid > 0 else '')}", "ok", "تم البيع وأُنشئت الفاتورة")
        for it, qty, _ in lines:
            left = it["stock"] - qty
            if it["kind"] == "part" and left <= (it["min_qty"] if it["min_qty"] is not None else 2): notify(f"{it['label']} — باقي {max(left, 0)} فقط", "warn", "تنبيه مخزون")
        return redirect(f"/sales/{sid}")

    # ---------- فواتير البيع ----------
    def sale_or_404(i):
        r = q("select * from sales where id=? and user_id=?", (i, uid()))
        if not r: abort(404)
        return dict(r[0])

    def sale_ctx(i):
        s = sale_or_404(i); its = [dict(r) for r in q("select * from sale_items where sale_id=? and user_id=? order by id", (i, uid()))]
        lines = [dict(r, n=n, total=round(r["qty"] * r["price"], 2)) for n, r in enumerate(its, 1)]
        bal = None
        if s["person_id"] and q("select 1 from debtors where id=? and user_id=?", (s["person_id"], uid())):
            ents = [dict(r) for r in q("select * from debt_entries where user_id=? and debtor_id=?", (uid(), s["person_id"]))]
            chs = [dict(r) for r in q("select * from cheques where user_id=? and person_id=?", (uid(), s["person_id"]))]
            bal = person_figs(ents, chs)["rem"]
        profit = round(sum(l["qty"] * (l["price"] - (l["cost"] or 0)) for l in lines) - (s["discount"] or 0), 2)
        return dict(s=s, lines=lines, pcs=sum(l["qty"] for l in lines), ref="SALE-%04d" % i, st=settings(), bal=bal, profit=profit)

    @app.route("/sales")
    def sales_list():
        rows = [dict(r) for r in q("select s.*, (select coalesce(sum(qty),0) from sale_items i where i.sale_id=s.id) pcs, (select coalesce(sum(i.qty*(i.price-i.cost)),0) from sale_items i where i.sale_id=s.id) - coalesce(s.discount,0) profit from sales s where s.user_id=? order by s.id desc", (uid(),))]
        for r in rows: r["profit"] = round(r["profit"] or 0, 2)
        m = today()[:7]
        prof = q("select coalesce(sum(i.qty*(i.price-i.cost)),0) p from sale_items i join sales s on s.id=i.sale_id where s.user_id=? and s.created like ?", (uid(), m + "%"))[0]["p"]
        disc = sum(r["discount"] for r in rows if (r["created"] or "").startswith(m))
        S = {"n": len(rows), "today": sum(r["total"] for r in rows if (r["created"] or "").startswith(today())),
             "month": sum(r["total"] for r in rows if (r["created"] or "").startswith(m)), "profit": round(prof - disc, 2),
             "profit_today": round(sum(r["profit"] for r in rows if (r["created"] or "").startswith(today())), 2),
             "rem": sum(max(r["total"] - r["paid"], 0) for r in rows)}
        return render_template("sales", rows=rows, S=S, ttl=("فواتير البيع", "كل فواتير المبيعات من المتجر، مع المدفوع والمتبقي"))

    @app.route("/sales/<int:i>")
    def sale_view(i): return render_template("saleinv", **sale_ctx(i))

    @app.route("/sales/<int:i>/thermal")
    def sale_thermal(i): return render_template("salethermal", **sale_ctx(i))

    @app.post("/sales/<int:i>/delete")
    def sale_delete(i):
        s = sale_or_404(i)
        for it in q("select * from sale_items where sale_id=? and user_id=?", (i, uid())):
            if it["tool_id"]: db().execute("update tools set qty=qty+? where id=? and user_id=?", (it["qty"], it["tool_id"], uid()))
            elif it["part_id"]: db().execute("update parts set qty=qty+? where id=? and user_id=?", (it["qty"], it["part_id"], uid()))
        db().execute("delete from debt_entries where sale_id=? and user_id=?", (i, uid()))
        db().execute("delete from sale_items where sale_id=? and user_id=?", (i, uid()))
        db().execute("delete from sales where id=? and user_id=?", (i, uid())); db().commit()
        notify(f"SALE-{i:04d} · {s['person_name']} — رجعت القطع للمخزون", "warn", "تم إلغاء الفاتورة")
        return redirect("/sales")

    @app.route("/healthz")
    def healthz(): return "ok"      # فحص صحة الخدمة لـ Render (بدون تسجيل دخول)

    # ---------- أدوات الصيانة ----------
    TOOL_CATS = ["مفكات", "لحام وقصدير", "ملاقط وأدوات فتح", "قياس وفحص", "تسخين وهواء ساخن", "تنظيف", "أدوات يدوية"]

    @app.route("/toolphoto/<name>")
    def toolphoto(name):
        if not q("select 1 from tools where photo=? and user_id=?", (name, uid())): abort(404)
        return send_from_directory(UP, name)

    @app.route("/tools")
    def tools_page():
        rows = [dict(r) for r in q("select * from tools where user_id=? order by lower(category), lower(name)", (uid(),))]
        cats = {}
        for r in rows:
            if r["category"]: cats[r["category"]] = cats.get(r["category"], 0) + 1
        ST = {"qty": sum(r["qty"] or 0 for r in rows), "val": sum((r["qty"] or 0) * (r["cost"] or 0) for r in rows), "imgs": sum(1 for r in rows if r["photo"])}
        return render_template("tools", rows=rows, ST=ST, cats=sorted(cats.items()), tcats=sorted(set(TOOL_CATS) | set(cats)),
                               ttl=("أدوات الصيانة", "جرد أدوات الورشة مع الصور والأعداد والأماكن"))

    def _tool_fields(f):
        return ((f.get("name") or "").strip(), (f.get("category") or "").strip(), max(0, _i(f.get("qty"), 1)), max(0.0, _f(f.get("cost"))),
                (f.get("location") or "").strip(), (f.get("notes") or "").strip(), max(0.0, _f(f.get("price"))))

    @app.post("/tools")
    def tool_add():
        nm, cat, qty, cost, loc, notes, price = _tool_fields(request.form)
        if not nm: notify("اكتب اسم الأداة", "warn", "البيانات ناقصة"); return redirect("/tools")
        f = request.files.get("photo"); ph = save_photo(f)
        if f and f.filename and not ph: notify("الصورة لازم تكون JPG أو PNG أو WEBP — انحفظت الأداة بدون صورة", "warn", "صيغة الصورة")
        ex("insert into tools(user_id,name,category,qty,cost,location,notes,photo,created,price) values(?,?,?,?,?,?,?,?,?,?)", (uid(), nm, cat, qty, cost, loc, notes, ph, today(), price))
        notify(nm, "ok", "تمت إضافة الأداة"); return redirect("/tools")

    @app.post("/tools/<int:i>/edit")
    def tool_edit(i):
        t = q("select * from tools where id=? and user_id=?", (i, uid()))
        if not t: abort(404)
        nm, cat, qty, cost, loc, notes, price = _tool_fields(request.form)
        if not nm: notify("اكتب اسم الأداة", "warn", "البيانات ناقصة"); return redirect("/tools")
        ph = save_photo(request.files.get("photo"))
        if ph: remove_file(t[0]["photo"])
        ex("update tools set name=?,category=?,qty=?,cost=?,location=?,notes=?,photo=?,price=? where id=? and user_id=?", (nm, cat, qty, cost, loc, notes, ph or t[0]["photo"], price, i, uid()))
        notify(nm, "ok", "تم حفظ التعديل"); return redirect("/tools")

    @app.post("/tools/<int:i>/delete")
    def tool_delete(i):
        t = q("select * from tools where id=? and user_id=?", (i, uid()))
        if t:
            ex("delete from tools where id=? and user_id=?", (i, uid())); remove_file(t[0]["photo"]); notify(t[0]["name"], "warn", "تم حذف الأداة")
        return redirect("/tools")
