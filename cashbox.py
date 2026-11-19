# -*- coding: utf-8 -*-
"""الصندوق المالي: كل حركات المال (صيانات، مبيعات، تحصيل ديون، شيكات) + مصاريف ودفعات موردين وجرد."""
import csv, io, datetime

KINDS_OUT = {"مصروف": "مصروف", "دفعة مورد": "دفعة مورد", "سحب": "سحب"}
KINDS_IN = {"إيداع": "إيداع", "دخل آخر": "دخل آخر"}
CATS = ["إيجار", "كهرباء وماء", "رواتب", "مواصلات", "إنترنت واتصالات", "أدوات ومعدات", "ضيافة", "صيانة الشركة", "أخرى"]

T_CB = r"""{% extends 'base' %}{% block c %}
<style>
.cb-top{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:14px;margin-bottom:16px}
.cb-k{background:#fff;border:1px solid var(--line);border-radius:20px;padding:16px;box-shadow:var(--sh)}.cb-k small{color:var(--mut);font-weight:700}.cb-k b{display:block;font-size:26px;margin-top:4px}.cb-k em{font-style:normal;font-size:12px;color:var(--mut)}
.cb-k.big{background:linear-gradient(135deg,#312e81,#4f46e5);color:#fff;border:0}.cb-k.big small,.cb-k.big em{color:#c7d2fe}
.cb-in{color:#059669}.cb-out{color:#e11d48}
.cb-f{display:flex;flex-wrap:wrap;gap:8px;align-items:end;margin-bottom:12px}.cb-f label{font-size:12px;font-weight:700;color:var(--mut)}.cb-f input,.cb-f select{margin:3px 0 0}
.cb-tabs{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px}.cb-tabs a{padding:7px 16px;border-radius:99px;border:1px solid var(--line);background:#fff;color:var(--ink);text-decoration:none;font-weight:700;font-size:13px}.cb-tabs a.on{background:var(--br);color:#fff;border-color:var(--br)}
.cb-grid{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(300px,1fr);gap:16px;margin-bottom:16px}
.cb-bars{display:flex;align-items:flex-end;gap:4px;height:150px;padding-top:10px}.cb-bars div{flex:1;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;height:100%;gap:2px;min-width:0}
.cb-bars i{display:block;width:100%;max-width:18px;border-radius:4px 4px 0 0;min-height:1px}.cb-bars .i{background:#10b981}.cb-bars .o{background:#f43f5e}.cb-bars span{font-size:9px;color:var(--mut);writing-mode:vertical-rl;height:26px;overflow:hidden}
.cb-src div{display:grid;grid-template-columns:110px 1fr auto;gap:10px;align-items:center;padding:5px 0;font-size:13px}.cb-src .t{height:8px;border-radius:9px;background:#eef1fa;overflow:hidden}.cb-src .t i{display:block;height:100%;border-radius:9px}
.cb-t{width:100%;border-collapse:collapse}.cb-t th{font-size:12px;color:var(--mut);text-align:start;padding:9px 8px;white-space:nowrap}.cb-t td{padding:9px 8px;border-top:1px solid var(--line);vertical-align:middle;font-size:13.5px}
.cb-t .n{white-space:nowrap;direction:ltr;text-align:end;font-variant-numeric:tabular-nums}.cb-t .ty{white-space:nowrap}.cb-t small{color:var(--mut)}
.cb-b{display:inline-block;padding:2px 10px;border-radius:99px;font-size:12px;font-weight:700;background:#eef1fa;color:#475569}.cb-b.in{background:#d1fae5;color:#047857}.cb-b.out{background:#ffe4e6;color:#be123c}.cb-b.bank{background:#e0e7ff;color:#3730a3}
.cb-x{border:0;background:transparent;color:#e11d48;cursor:pointer;padding:2px 8px;font-size:16px;box-shadow:none}
.cb-act{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px}
.cb-b2{display:flex;gap:8px;flex-wrap:wrap}
.cb-day{margin-bottom:18px}.cb-dh{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:12px}.cb-dh form{margin:0}.cb-dh input{margin:0}
.cb-dh .nv{padding:7px 14px;border-radius:99px;border:1px solid var(--line);background:#fff;color:var(--ink);text-decoration:none;font-weight:700;font-size:13px}
.cb-st{display:inline-block;padding:4px 14px;border-radius:99px;font-weight:800;font-size:12.5px}.cb-st.cl{background:#d1fae5;color:#047857}.cb-st.op{background:#fef3c7;color:#92400e}
.cb-cl{display:flex;flex-wrap:wrap;gap:16px;align-items:center;background:#f6f8ff;border:1px dashed #c7d0ee;border-radius:16px;padding:12px 16px;font-size:14px}.cb-cl b{font-size:15px}
.cb-day .cb-top{margin-bottom:12px}
html[data-theme=dark] .cb-dh .nv{background:#141b3a;color:var(--ink);border-color:var(--line)}html[data-theme=dark] .cb-cl{background:#0d1330;border-color:var(--line)}
@media(max-width:980px){.cb-grid{grid-template-columns:1fr}}
html[data-theme=dark] .cb-k,html[data-theme=dark] .cb-tabs a{background:#141b3a!important;color:var(--ink);border-color:var(--line)}html[data-theme=dark] .cb-k.big{background:linear-gradient(135deg,#312e81,#4f46e5)!important;color:#fff}
html[data-theme=dark] .cb-tabs a.on{background:var(--br)!important;color:#fff}html[data-theme=dark] .cb-src .t{background:#0d1330}html[data-theme=dark] .cb-b{background:#1d2656;color:#cfd6f5}
</style>
<div class=ph><h2>الصندوق المالي</h2><p>كل مصاري الشركة بمكان واحد: الوارد من الصيانات والمبيعات والديون والشيكات، والمصاريف ودفعات الموردين</p></div>

<div class="card cb-day">
<div class=cb-dh>
<a class=nv href="/cashbox?day={{prev}}">→ اليوم السابق</a>
<form method=get><input type=date name=day value="{{dayv}}" max="{{today}}" onchange="this.form.submit()" aria-label="اختر يوم"></form>
{% if nxt %}<a class=nv href="/cashbox?day={{nxt}}">اليوم التالي ←</a>{% endif %}{% if dayv!=today %}<a class=nv href="/cashbox">اليوم</a>{% endif %}
<b style="font-size:17px">{{dname}} {{dayv}}{{ ' · اليوم' if dayv==today }}</b>
{% if closing %}<span class="cb-st cl">مقفل ✓</span>{% else %}<span class="cb-st op">مفتوح</span>{% endif %}
</div>
<div class=cb-top>
<div class=cb-k><small>الدرج (نقد) بداية اليوم</small><b dir=ltr>{{ '%g'|format(df.cash_start) }} ₪</b><em>اللي كان بالصندوق قبل ما يبدأ اليوم</em></div>
<div class=cb-k><small>وارد اليوم</small><b class=cb-in dir=ltr>+{{ '%g'|format(df.inn) }} ₪</b><em>مبيعات وصيانات وتحصيل</em></div>
<div class=cb-k><small>مصاريف اليوم</small><b class=cb-out dir=ltr>-{{ '%g'|format(df.exp) }} ₪</b><em>مصاريف ودفعات موردين{% if df.wd %} · سحب {{ '%g'|format(df.wd) }} ₪{% endif %}</em></div>
<div class=cb-k><small>مربح اليوم</small><b class="{{ 'cb-in' if df.profit>=0 else 'cb-out' }}" dir=ltr>{{ '%g'|format(df.profit) }} ₪</b><em>مبيعات + صيانات (بعد خصم الجملة)</em></div>
<div class="cb-k big"><small>الدرج (نقد) نهاية اليوم</small><b dir=ltr>{{ '%g'|format(df.cash_end) }} ₪</b><em>{{ 'بعد الإقفال والسحب' if closing else 'المتوقع بالصندوق' }}</em></div>
</div>
{% if closing %}<div class=cb-cl><span>عُدّ: <b>{{ '%g'|format(closing.counted) }} ₪</b></span><span>مسحوب: <b>{{ '%g'|format(closing.withdrawn) }} ₪</b></span>
<span>الفرق: <b class="{{ 'cb-in' if closing.diff>=0 else 'cb-out' }}">{{ '%g'|format(closing.diff) }} ₪</b></span><span>مربح اليوم وقت الإقفال: <b>{{ '%g'|format(closing.profit) }} ₪</b></span>{% if closing.note %}<span>ملاحظة: {{closing.note}}</span>{% endif %}
<span style="flex:1"></span><form method=post action="/cashbox/close/{{closing.id}}/undo" onsubmit="return confirm('إلغاء إقفال هاليوم؟ بينحذف السحب المسجّل معه وبيرجع المبلغ للصندوق.')" style="margin:0"><button class=ghost>إلغاء الإقفال</button></form></div>
{% else %}<div class=cb-act style="margin:0"><button type=button onclick="document.getElementById('cb-close').showModal()">🔒 إقفال اليوم (جرد + سحب)</button><small style="align-self:center;color:var(--mut)">بعد الإقفال بيبدأ اليوم الجديد بصندوق صفر، وبتقدر ترجع لأي يوم من التاريخ فوق.</small></div>{% endif %}
</div>

<div class=cb-top>
<div class="cb-k big"><small>رصيد الصندوق الآن (نقد + بنك)</small><b dir=ltr>{{ '%g'|format(bal.total) }} ₪</b><em>نقد {{ '%g'|format(bal.cash) }} · بنك/شيكات {{ '%g'|format(bal.bank) }}</em></div>
<div class=cb-k><small>وارد الفترة</small><b class=cb-in dir=ltr>+{{ '%g'|format(per.inn) }} ₪</b><em>{{lbl}}</em></div>
<div class=cb-k><small>صادر الفترة</small><b class=cb-out dir=ltr>-{{ '%g'|format(per.out) }} ₪</b><em>مصاريف ودفعات وسحب</em></div>
<div class=cb-k><small>صافي الفترة</small><b dir=ltr class="{{ 'cb-in' if per.inn>=per.out else 'cb-out' }}">{{ '%g'|format(per.inn-per.out) }} ₪</b><em>وارد − صادر</em></div>
</div>

<div class=cb-act>
<button type=button onclick="cbOpen('مصروف')">− مصروف</button>
<button type=button onclick="cbOpen('دفعة مورد')">− دفعة لمورد</button>
<button type=button class=ghost onclick="cbOpen('إيداع')">+ إيداع</button>
<button type=button class=ghost onclick="cbOpen('سحب')">سحب</button>
<button type=button class=ghost onclick="cbOpen('دخل آخر')">+ دخل آخر</button>
<button type=button class=ghost onclick="document.getElementById('cb-count').showModal()">جرد الصندوق</button>
<button type=button class=ghost onclick="document.getElementById('cb-open').showModal()">الرصيد الافتتاحي</button>
<a class=btn href="/cashbox.csv?{{qs}}">تصدير Excel</a>
</div>

<div class=cb-tabs>{% for k,v in tabs %}<a href="/cashbox?range={{k}}&acct={{acct}}" class="{{ 'on' if rng==k }}">{{v}}</a>{% endfor %}</div>
<form class="card cb-f" method=get><input type=hidden name=range value="{{rng}}">
<label>من<input type=date name=d1 value="{{d1}}"></label><label>إلى<input type=date name=d2 value="{{d2}}"></label>
<label>الحساب<select name=acct><option value="">الكل<option value=نقد {{ 'selected' if acct=='نقد' }}>نقد<option value=بنك {{ 'selected' if acct=='بنك' }}>بنك / شيكات</select></label>
<label>النوع<select name=src><option value="">كل الأنواع{% for s in srcs %}<option {{ 'selected' if s==src }}>{{s}}{% endfor %}</select></label>
<label style="flex:1;min-width:180px">بحث<input name=q value="{{qq}}" placeholder="وصف، اسم، رقم..." style="width:100%"></label><button>تطبيق</button></form>

<div class=cb-grid>
<div class=card><h3>الحركة اليومية</h3>{% if days %}<div class=cb-bars>{% for d in days %}<div title="{{d.date}} · وارد {{ '%g'|format(d.inn) }} · صادر {{ '%g'|format(d.out) }}"><i class=i style="height:{{ (d.inn/mx*100)|round(1) }}%"></i><i class=o style="height:{{ (d.out/mx*100)|round(1) }}%"></i><span>{{d.date[5:]}}</span></div>{% endfor %}</div>
<small><span class=cb-in>■</span> وارد &nbsp; <span class=cb-out>■</span> صادر</small>{% else %}<div class=em>ما في حركة بهالفترة.</div>{% endif %}</div>
<div class=card><h3>من وين وإلى وين</h3><div class=cb-src>{% for s in bysrc %}<div><span>{{s.name}}</span><span class=t><i style="width:{{ (s.v/smx*100)|round }}%;background:{{ '#10b981' if s.dir=='in' else '#f43f5e' }}"></i></span><b class="{{ 'cb-in' if s.dir=='in' else 'cb-out' }}" dir=ltr>{{ '+' if s.dir=='in' else '-' }}{{ '%g'|format(s.v) }}</b></div>{% else %}<div class=em>لا يوجد.</div>{% endfor %}</div></div>
</div>

{% if pay %}<div class=card style="margin-bottom:16px"><h3>حسابات الموردين</h3><div style="overflow:auto"><table class=cb-t><tr><th>المورد<th>فواتير الشراء (صافي)<th>المدفوع<th>المتبقي<th></tr>
{% for s in pay %}<tr><td><b>{{s.name}}</b><td class=n>{{ '%g'|format(s.inv) }} ₪<td class=n>{{ '%g'|format(s.paid) }} ₪<td class=n><b class="{{ 'cb-out' if s.rem>0.004 else 'cb-in' }}">{{ '%g'|format(s.rem) }} ₪</b><td><button type=button class=ghost onclick="cbOpen('دفعة مورد',{{s.id}},{{ [s.rem,0]|max }})">دفع</button></tr>{% endfor %}</table></div></div>{% endif %}

<div class=card><h3>سجل الحركات <small style="font-weight:400">({{rows|length}}{{ ' من ' ~ total_rows if total_rows>rows|length }})</small></h3><div style="overflow:auto"><table class=cb-t>
<tr><th>التاريخ<th>النوع<th>التفاصيل<th>الحساب<th class=n>وارد<th class=n>صادر<th class=n>الرصيد<th></tr>
{% for r in rows %}<tr><td class=n style="text-align:start">{{r.date}}<small> {{r.time}}</small><td class=ty><span class="cb-b {{ r.dir }}">{{r.label}}</span>
<td>{% if r.link %}<a href="{{r.link}}">{{r.desc}}</a>{% else %}{{r.desc}}{% endif %}{% if r.note %}<br><small>{{r.note}}</small>{% endif %}
<td><span class="cb-b {{ 'bank' if r.acct=='بنك' }}">{{r.acct}}</span><td class="n cb-in">{{ '+'~('%g'|format(r.amt)) if r.dir=='in' }}<td class="n cb-out">{{ '-'~('%g'|format(r.amt)) if r.dir=='out' }}<td class=n>{{ '%g'|format(r.rb) }}
<td>{% if r.mid %}<form method=post action="/cashbox/{{r.mid}}/delete" onsubmit="return confirm('حذف هالحركة؟')" style="margin:0"><button class=cb-x title="حذف">✕</button></form>{% endif %}</tr>
{% else %}<tr><td colspan=8 class=em>ما في حركات مطابقة.</tr>{% endfor %}</table></div>
{% if total_rows>rows|length %}<small>معروضة آخر {{rows|length}} حركة، ضيّق الفترة أو صدّر Excel للكل.</small>{% endif %}</div>

{% if counts %}<div class=card style="margin-top:16px"><h3>آخر عمليات الجرد</h3><table class=cb-t><tr><th>التاريخ<th class=n>المتوقع<th class=n>الفعلي<th class=n>الفرق<th>ملاحظة</tr>
{% for c in counts %}<tr><td>{{c.created}}<td class=n>{{ '%g'|format(c.expected) }}<td class=n>{{ '%g'|format(c.counted) }}<td class="n {{ 'cb-in' if c.counted-c.expected>=0 else 'cb-out' }}">{{ '%g'|format((c.counted-c.expected)|round(2)) }}<td>{{c.note or ''}}</tr>{% endfor %}</table></div>{% endif %}

<dialog class=dlg id=cb-d><form method=post action=/cashbox/add enctype=multipart/form-data><div class=dh><h3 id=cb-t>حركة جديدة</h3><button type=button class=cl onclick="this.closest('dialog').close()" aria-label="إغلاق">×</button></div>
<div class=db><div class=fg><input type=hidden name=kind id=cb-kind>
<label>المبلغ (₪)<input name=amount id=cb-amt type=number step=any min=0.01 required></label><label>التاريخ<input type=date name=created value="{{today}}" max="{{today}}"></label>
<label>الحساب<select name=account><option>نقد<option value=بنك>بنك / تحويل</select></label>
<label id=cb-supl>المورد<select name=supplier_id id=cb-sup><option value="">— اختر المورد —{% for s in suppliers %}<option value={{s.id}}>{{s.name}}{% endfor %}</select></label>
<label id=cb-catl>التصنيف<select name=category>{% for c in cats %}<option>{{c}}{% endfor %}</select></label>
<label class=fa>وصل التحويل (إلزامي لدفعة المورد البنكية) — صورة أو PDF<input type=file name=receipt accept="image/*,application/pdf"></label>
<label class=fa>ملاحظة<input name=note placeholder="اختياري"></label></div></div>
<div class=df><button>حفظ</button></div></form></dialog>

{% if closings %}<div class=card style="margin-top:16px"><h3>سجل إقفال الأيام</h3><div style="overflow:auto"><table class=cb-t><tr><th>اليوم<th class=n>الدخل<th class=n>المصاريف<th class=n>المربح<th class=n>المعدود<th class=n>المسحوب<th class=n>الفرق<th>ملاحظة</tr>
{% for c in closings %}<tr><td><a href="/cashbox?day={{c.day}}"><b>{{c.day}}</b></a><td class=n>{{ '%g'|format(c.income) }}<td class=n>{{ '%g'|format(c.expenses) }}<td class="n {{ 'cb-in' if c.profit>=0 else 'cb-out' }}"><b>{{ '%g'|format(c.profit) }}</b><td class=n>{{ '%g'|format(c.counted) }}<td class=n>{{ '%g'|format(c.withdrawn) }}<td class="n {{ 'cb-in' if c.diff>=0 else 'cb-out' }}">{{ '%g'|format(c.diff) }}<td>{{c.note or ''}}</tr>{% endfor %}</table></div></div>{% endif %}

<dialog class=dlg id=cb-close><form method=post action=/cashbox/close><input type=hidden name=day value="{{dayv}}"><div class=dh><h3>إقفال يوم {{dayv}}</h3><button type=button class=cl onclick="this.closest('dialog').close()" aria-label="إغلاق">×</button></div>
<div class=db><div class=fg><label class=fa>المتوقع بالدرج (نقد)<input value="{{ '%g'|format(df.cash_end) }} ₪" readonly></label>
<label class=fa>عدّيت كم فعلياً؟ (₪)<input name=counted id=cc-c type=number step=any min=0 required value="{{ '%g'|format([df.cash_end,0]|max) }}"></label>
<label class=fa>كم سحبت من الصندوق؟ (₪)<input name=withdrawn id=cc-w type=number step=any min=0 value="{{ '%g'|format([df.cash_end,0]|max) }}"></label>
<label class=fa>ملاحظة<input name=note placeholder="اختياري"></label></div>
<small>بيتسجّل سحب بالمبلغ اللي سحبته، وإذا المعدود غير المتوقع بيتسجّل الفرق كتسوية جرد. اليوم الجديد بيبدأ بالباقي بالدرج (صفر إذا سحبت كل شي).</small></div>
<div class=df><button>إقفال اليوم</button></div></form></dialog>
<script>(function(){var c=document.getElementById('cc-c'),w=document.getElementById('cc-w');if(!c||!w)return;w.addEventListener('input',function(){w.dataset.t=1});c.addEventListener('input',function(){if(!w.dataset.t)w.value=c.value})})()</script>

<dialog class=dlg id=cb-count><form method=post action=/cashbox/count><div class=dh><h3>جرد الصندوق (النقد)</h3><button type=button class=cl onclick="this.closest('dialog').close()" aria-label="إغلاق">×</button></div>
<div class=db><div class=fg><label class=fa>المتوقع بالصندوق<input value="{{ '%g'|format(bal.cash) }} ₪" readonly><input type=hidden name=expected value="{{bal.cash}}"></label>
<label class=fa>عدّيت كم فعلياً؟ (₪)<input name=counted type=number step=any min=0 required></label><label class=fa>ملاحظة<input name=note placeholder="مثال: إقفال اليوم"></label></div></div><div class=df><button>حفظ الجرد</button></div></form></dialog>

<dialog class=dlg id=cb-open><form method=post action=/cashbox/open><div class=dh><h3>الرصيد الافتتاحي</h3><button type=button class=cl onclick="this.closest('dialog').close()" aria-label="إغلاق">×</button></div>
<div class=db><div class=fg><label>نقد بالصندوق قبل البدء (₪)<input name=cash_open type=number step=any value="{{op.cash}}"></label><label>رصيد البنك قبل البدء (₪)<input name=bank_open type=number step=any value="{{op.bank}}"></label></div><small>بيدخل بحساب الرصيد الحالي فقط، وما بيأثر على الوارد والصادر.</small></div><div class=df><button>حفظ</button></div></form></dialog>
<script>function cbOpen(k,sid,amt){var d=document.getElementById('cb-d');document.getElementById('cb-kind').value=k;document.getElementById('cb-t').textContent={'مصروف':'تسجيل مصروف','دفعة مورد':'دفعة لمورد','سحب':'سحب من الصندوق','إيداع':'إيداع بالصندوق','دخل آخر':'دخل آخر'}[k]||k;
var sup=k==='دفعة مورد';document.getElementById('cb-supl').hidden=!sup;document.getElementById('cb-sup').required=sup;document.getElementById('cb-catl').hidden=k!=='مصروف';
document.getElementById('cb-sup').value=sid||'';document.getElementById('cb-amt').value=amt&&amt>0?amt:'';d.showModal();setTimeout(function(){document.getElementById('cb-amt').focus()},50)}</script>
{% endblock %}"""


T_TODAY = r"""{% extends 'base' %}{% block c %}
<style>.td-n{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:14px}.td-n form{margin:0}.td-n input{margin:0}
.td-n .nv{padding:7px 14px;border-radius:99px;border:1px solid var(--line);background:#fff;color:var(--ink);text-decoration:none;font-weight:700;font-size:13px}
.td-t{width:100%;border-collapse:collapse}.td-t th{font-size:12px;color:var(--mut);text-align:start;padding:9px 8px;white-space:nowrap}.td-t td{padding:10px 8px;border-top:1px solid var(--line);font-size:13.5px;vertical-align:middle}
.td-t .n{white-space:nowrap;direction:ltr;text-align:end;font-variant-numeric:tabular-nums}.td-b{display:inline-block;padding:2px 12px;border-radius:99px;font-size:12px;font-weight:700}.td-b.s{background:#e0e7ff;color:#3730a3}.td-b.r{background:#d1fae5;color:#047857}
html[data-theme=dark] .td-n .nv{background:#141b3a;color:var(--ink);border-color:var(--line)}</style>
<div class=td-n><a class=nv href="/today?d={{prev}}">→ اليوم السابق</a><form method=get><input type=date name=d value="{{d}}" max="{{t}}" onchange="this.form.submit()" aria-label="اختر يوم"></form>{% if nxt %}<a class=nv href="/today?d={{nxt}}">اليوم التالي ←</a>{% endif %}{% if d!=t %}<a class=nv href="/today">اليوم</a>{% endif %}
<b style="font-size:17px">{{dname}} {{d}}{{ ' · اليوم' if d==t }}</b><span style="flex:1"></span><a class="btn ghost" href="/cashbox?day={{d}}">🔒 الصندوق المالي</a><a class=btn href=/pos>كاشير سريع</a></div>
<div class=sg4>
<div class=sc><span class="si c">₪</span><div><small>دخل اليوم (الكل)</small><b>{{ '%g'|format(S.income) }} ₪</b></div></div>
<div class=sc><span class="si e">₪</span><div><small>مربح اليوم</small><b style="color:{{ '#059669' if S.profit>=0 else '#e11d48' }}">{{ '%g'|format(S.profit) }} ₪</b></div></div>
<div class=sc><span class="si a">₪</span><div><small>مبيعات · صيانات</small><b>{{ '%g'|format(S.sales) }} · {{ '%g'|format(S.rep) }}</b></div></div>
<div class=sc><span class="si b">₪</span><div><small>مقبوض فعلياً</small><b>{{ '%g'|format(S.paid) }} ₪</b></div></div>
<div class=sc><span class="si d">₪</span><div><small>دين على الزبائن (اليوم)</small><b>{{ '%g'|format(S.debt) }} ₪</b></div></div></div>
{% if col>0 or pend>0 %}<div class="card" style="margin-bottom:14px;display:flex;gap:18px;flex-wrap:wrap;font-size:13.5px;color:var(--mut)">{% if col>0 %}<span>💵 تحصيل ديون قديمة اليوم: <b style="color:var(--ink)">{{ '%g'|format(col) }} ₪</b> (مش محسوبة بالدخل لأنها من مبيعات سابقة)</span>{% endif %}{% if pend>0 %}<span>🔧 {{pend}} صيانة سُجّلت اليوم وما انسلمت لسا — بتنحسب عند التسليم</span>{% endif %}</div>{% endif %}
<div class=card><h3>كل اللي انباع ({{S.n}})</h3><div style="overflow:auto"><table class=td-t><tr><th>الوقت<th>النوع<th>التفاصيل<th>الزبون<th class=n>المبلغ<th class=n>المدفوع<th class=n>المربح<th></tr>
{% for r in rows %}<tr><td class=nw>{{r.t or '—'}}<td><span class="td-b {{ 's' if r.kind=='بيع' else 'r' }}">{{r.kind}}</span><td>{{r.title}}<br><small style="color:var(--mut)" dir=ltr>{{r.ref}}</small><td>{{r.who}}<td class=n><b>{{ '%g'|format(r.total) }}</b><td class=n>{{ '%g'|format(r.paid) }}<td class=n><b style="color:{{ '#059669' if r.profit>=0 else '#e11d48' }}">{{ '%g'|format(r.profit) }}</b><td><a class=ib href="{{r.link}}" title="فتح" aria-label="فتح">{{ic.eye}}</a></tr>
{% else %}<tr><td colspan=8 class=em>ما في مبيعات لهاليوم لسا. أي بيع من الكاشير السريع أو المتجر أو تسليم صيانة بيظهر هون لحاله.</tr>{% endfor %}
{% if rows %}<tr style="font-weight:800"><td colspan=4>المجموع<td class=n>{{ '%g'|format(S.income) }}<td class=n>{{ '%g'|format(S.paid) }}<td class=n>{{ '%g'|format(S.profit) }}<td></tr>{% endif %}</table></div></div>{% endblock %}"""


def register(ns):
    app, T, q, ex, uid = ns["app"], ns["T"], ns["q"], ns["ex"], ns["uid"]
    render_template, redirect, request, flash, Response = ns["render_template"], ns["redirect"], ns["request"], ns["flash"], ns["Response"]
    notify, today, now_s, _f = ns["notify"], ns["today"], ns["now_s"], ns["_f"]
    CH_OK = ns["CH_OK"]; AR_DAYS = ns["AR_DAYS"]; db = ns["db"]

    def ins(sql, a):   # insert + commit وبيرجّع رقم الصف الجديد
        c = db().execute(sql, a); db().commit(); return c.lastrowid
    save_receipt, del_file = ns["save_receipt"], ns["del_file"]
    T["cashbox"] = T_CB; T["today"] = T_TODAY

    def opening():
        r = q("select cash_open, bank_open from settings where user_id=?", (uid(),))
        return {"cash": (r[0]["cash_open"] or 0) if r else 0, "bank": (r[0]["bank_open"] or 0) if r else 0}

    def ledger():
        """كل الحركات (من أول يوم) بترتيب زمني مع الرصيد الجاري لكل حساب."""
        u = uid(); rows = []
        def add(date, tm, label, dir_, amt, acct, desc, link="", note="", mid=None, src=None):
            if amt and amt > 0 and date: rows.append(dict(date=date[:10], time=tm, label=label, dir=dir_, amt=round(amt, 2), acct=acct, desc=desc, link=link, note=note, mid=mid, src=src or label))
        for r in q("select * from repairs where user_id=? and status='تم التسليم'", (u,)):
            add(r["done_date"] or r["created"], "", "صيانة", "in", r["price"] or 0, "نقد", f"{r['device'] or ''} · {r['customer'] or ''}", "/repairs")
        for r in q("select * from sales where user_id=?", (u,)):
            c = r["created"] or ""; add(c, c[11:16], "مبيعات", "in", r["paid"] or 0, "نقد", f"{'SALE-%04d' % r['id']} · {r['person_name'] or ''}", f"/sales/{r['id']}")
        for r in q("select e.*, d.name dname from debt_entries e left join debtors d on d.id=e.debtor_id where e.user_id=? and e.kind<>'دين' and e.sale_id is null", (u,)):
            add(r["created"], "", "تحصيل دين", "in", r["amount"] or 0, "نقد", f"{r['dname'] or ''}" + (f" · {r['note']}" if r["note"] else ""), f"/people/{r['debtor_id']}")
        for r in q("select c.*, d.name dname from cheques c left join debtors d on d.id=c.person_id where c.user_id=? and c.status=?", (u, CH_OK)):
            add(r["cashed_date"] or r["created"], "", "شيك مصروف", "in", r["amount"] or 0, "بنك", f"شيك {r['number'] or ''} · {r['bank'] or ''} · {r['drawer'] or r['dname'] or ''}", "/cheques")
        enm = {e["id"]: e["name"] for e in q("select id,name from employees where user_id=?", (u,))}
        for r in q("select * from emp_co_pay where user_id=?", (u,)):
            add((r["created"] or "")[:10], (r["created"] or "")[11:16], "دفعة موظف", "in", r["amount"] or 0, r["method"] or "نقد", f"دفعة موظف · {enm.get(r['emp_id'], '')}" + (" 🧾" if r["receipt"] else ""),
                ("/payreceipt/" + r["receipt"]) if r["receipt"] else f"/employees/{r['emp_id']}", r["note"] or "")
        sup = {s["id"]: s["name"] for s in q("select id,name from suppliers where user_id=?", (u,))}
        for r in q("select * from cash_entries where user_id=?", (u,)):
            d = r["direction"]; k = r["kind"]
            desc = k + (f" · {sup.get(r['supplier_id'], '')}" if r["kind"] == "دفعة مورد" else "") + (f" · {r['category']}" if r["category"] and k == "مصروف" else "")
            add(r["created"], (r["created_at"] or "")[11:16], k, d, r["amount"] or 0, r["account"] or "نقد", desc + (" 🧾" if r["receipt"] else ""), ("/payreceipt/" + r["receipt"]) if r["receipt"] else "", r["note"] or "", r["id"])
        rows.sort(key=lambda x: (x["date"], x["time"], x["mid"] or 0))
        o = opening(); rb = {"نقد": o["cash"], "بنك": o["bank"]}
        for x in rows:
            rb[x["acct"]] += x["amt"] if x["dir"] == "in" else -x["amt"]; x["rb"] = round(rb[x["acct"]], 2)
        bal = {"cash": round(rb["نقد"], 2), "bank": round(rb["بنك"], 2), "total": round(rb["نقد"] + rb["بنك"], 2)}
        return rows, bal

    def sel_day():
        try: dd = datetime.date.fromisoformat(request.args.get("day") or "")
        except ValueError: return today()
        return min(dd.isoformat(), today())

    def sales_profit(day):
        r = q("select coalesce(sum(i.qty*(i.price-i.cost)),0) p from sale_items i join sales s on s.id=i.sale_id where s.user_id=? and s.created like ?", (uid(), day + "%"))[0]["p"] or 0
        dsc = q("select coalesce(sum(discount),0) d from sales where user_id=? and created like ?", (uid(), day + "%"))[0]["d"] or 0
        return round(r - dsc, 2)

    def repairs_profit(day):
        return round(q("select coalesce(sum(price-cost),0) p from repairs where user_id=? and status='تم التسليم' and coalesce(done_date,created)=?", (uid(), day))[0]["p"] or 0, 2)

    def cash_at(rows, day):
        last = None
        for x in rows:
            if x["acct"] == "نقد" and x["date"] <= day: last = x["rb"]
        return opening()["cash"] if last is None else last

    def day_figs(rows, day):
        inn = exp = wd = 0.0
        for x in rows:
            if x["date"] != day or x["src"] == "تسوية جرد": continue
            if x["dir"] == "in": inn += x["amt"]
            elif x["src"] == "سحب": wd += x["amt"]
            else: exp += x["amt"]
        prev = (datetime.date.fromisoformat(day) - datetime.timedelta(days=1)).isoformat()
        return dict(inn=round(inn, 2), exp=round(exp, 2), wd=round(wd, 2), profit=round(sales_profit(day) + repairs_profit(day), 2),
                    cash_start=round(cash_at(rows, prev), 2), cash_end=round(cash_at(rows, day), 2))

    def period():
        a = request.args; t = today(); d = datetime.date.fromisoformat(t)
        d1, d2 = a.get("d1") or "", a.get("d2") or ""
        if not (d1 or d2) and not a.get("range") and a.get("day"):
            sd = sel_day(); return "day", sd, sd
        rng = a.get("range") or "today"   # اليوم الجديد بيبدأ بحقول صفر
        if not (d1 or d2):
            if rng == "today": d1 = d2 = t
            elif rng == "week": d1, d2 = (d - datetime.timedelta(days=6)).isoformat(), t
            elif rng == "month": d1, d2 = d.replace(day=1).isoformat(), t
            elif rng == "all": d1 = d2 = ""
            else: rng = "month"; d1, d2 = d.replace(day=1).isoformat(), t
        else: rng = "custom"
        return rng, d1, d2

    def filtered():
        rows, bal = ledger(); rng, d1, d2 = period(); a = request.args
        acct = a.get("acct") if a.get("acct") in ("نقد", "بنك") else ""; src = a.get("src") or ""; qq = (a.get("q") or "").strip().lower()
        out = [r for r in rows if (not d1 or r["date"] >= d1) and (not d2 or r["date"] <= d2) and (not acct or r["acct"] == acct) and (not src or r["src"] == src)
               and (not qq or qq in (r["desc"] + " " + (r["note"] or "") + " " + r["label"]).lower())]
        return rows, bal, out, rng, d1, d2, acct, src, qq

    @app.route("/cashbox")
    def cashbox_page():
        rows, bal, out, rng, d1, d2, acct, src, qq = filtered()
        inn = round(sum(r["amt"] for r in out if r["dir"] == "in"), 2); outv = round(sum(r["amt"] for r in out if r["dir"] == "out"), 2)
        days = {}
        for r in out:
            x = days.setdefault(r["date"], {"date": r["date"], "inn": 0, "out": 0}); x["inn" if r["dir"] == "in" else "out"] += r["amt"]
        days = sorted(days.values(), key=lambda x: x["date"])[-31:]
        mx = max([max(x["inn"], x["out"]) for x in days] + [1])
        by = {}
        for r in out:
            x = by.setdefault((r["src"], r["dir"]), 0); by[(r["src"], r["dir"])] = x + r["amt"]
        bysrc = sorted([dict(name=k[0], dir=k[1], v=round(v, 2)) for k, v in by.items()], key=lambda x: (x["dir"] != "in", -x["v"]))
        smx = max([s["v"] for s in bysrc] + [1])
        # حسابات الموردين
        inv = {r["supplier_id"]: r["t"] or 0 for r in q("select supplier_id, sum(total) t from invoices where user_id=? group by supplier_id", (uid(),))}
        paid = {r["supplier_id"]: r["t"] or 0 for r in q("select supplier_id, sum(amount) t from cash_entries where user_id=? and kind='دفعة مورد' group by supplier_id", (uid(),))}
        suppliers = [dict(r) for r in q("select id,name from suppliers where user_id=? order by name", (uid(),))]
        pay = [dict(id=s["id"], name=s["name"], inv=round(inv.get(s["id"], 0), 2), paid=round(paid.get(s["id"], 0), 2), rem=round(inv.get(s["id"], 0) - paid.get(s["id"], 0), 2)) for s in suppliers if s["id"] in inv or s["id"] in paid]
        counts = [dict(r) for r in q("select * from cash_counts where user_id=? order by id desc limit 5", (uid(),))]
        tabs = [("today", "اليوم"), ("week", "آخر 7 أيام"), ("month", "هذا الشهر"), ("all", "الكل")]
        lbl = {"today": "اليوم", "week": "آخر 7 أيام", "month": "هذا الشهر", "all": "كل الفترات", "day": d1}.get(rng, f"{d1 or '…'} → {d2 or '…'}")
        qs = "&".join(f"{k}={v}" for k, v in request.args.items() if k in ("range", "d1", "d2", "acct", "src", "q", "day") and v)
        disp = list(reversed(out))[:300]
        dayv = sel_day(); dd = datetime.date.fromisoformat(dayv); t = today()
        prev = (dd - datetime.timedelta(days=1)).isoformat(); nxt = (dd + datetime.timedelta(days=1)).isoformat() if dayv < t else None
        cl = q("select * from day_closings where user_id=? and day=? order by id desc limit 1", (uid(), dayv))
        closings = [dict(r) for r in q("select * from day_closings where user_id=? order by day desc, id desc limit 40", (uid(),))]
        return render_template("cashbox", dayv=dayv, prev=prev, nxt=nxt, dname=AR_DAYS[dd.weekday()], df=day_figs(rows, dayv), closing=dict(cl[0]) if cl else None, closings=closings, rows=disp, total_rows=len(out), bal=bal, per=dict(inn=inn, out=outv), days=days, mx=mx, bysrc=bysrc, smx=smx, pay=pay, counts=counts, tabs=tabs,
                               rng=rng, d1=d1, d2=d2, acct=acct, src=src, qq=qq, lbl=lbl, qs=qs, srcs=["صيانة", "مبيعات", "تحصيل دين", "شيك مصروف", "دفعة موظف", "مصروف", "دفعة مورد", "سحب", "إيداع", "دخل آخر", "تسوية جرد"],
                               suppliers=suppliers, cats=CATS, today=today(), op=opening())

    @app.route("/cashbox.csv")
    def cashbox_csv():
        _, _, out, *_ = filtered()
        o = io.StringIO(); w = csv.writer(o); w.writerow(["التاريخ", "الوقت", "النوع", "التفاصيل", "الحساب", "وارد", "صادر", "الرصيد", "ملاحظة"])
        for r in out: w.writerow([r["date"], r["time"], r["label"], r["desc"], r["acct"], r["amt"] if r["dir"] == "in" else "", r["amt"] if r["dir"] == "out" else "", r["rb"], r["note"]])
        return Response("﻿" + o.getvalue(), mimetype="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=cashbox.csv"})

    @app.post("/cashbox/add")
    def cashbox_add():
        f = request.form; kind = f.get("kind", ""); amt = round(_f(f.get("amount")), 2)
        if kind not in KINDS_OUT and kind not in KINDS_IN or amt <= 0:
            flash("تعذّر الحفظ|اكتب مبلغ صحيح.", "warn"); return redirect("/cashbox")
        sid = None
        if kind == "دفعة مورد":
            r = q("select id from suppliers where id=? and user_id=?", (f.get("supplier_id") or 0, uid()))
            if not r: flash("اختر المورد|لازم تحدد المورد للدفعة.", "warn"); return redirect("/cashbox")
            sid = r[0]["id"]
        d = f.get("created") or today()
        if d > today(): d = today()
        bank = f.get("account") == "بنك"; rcpt = save_receipt(request.files.get("receipt"))
        if kind == "دفعة مورد" and bank and not rcpt:
            flash("الوصل مطلوب|أرفق وصل التحويل (صورة أو PDF) للدفعة البنكية.", "warn"); return redirect("/cashbox")
        ex("insert into cash_entries(user_id,created,kind,direction,amount,account,category,supplier_id,note,created_at,receipt) values(?,?,?,?,?,?,?,?,?,?,?)",
           (uid(), d, kind, "out" if kind in KINDS_OUT else "in", amt, "بنك" if bank else "نقد", (f.get("category") or "") if kind == "مصروف" else "", sid, (f.get("note") or "").strip()[:200], now_s(), rcpt))
        notify(f"{kind} · {amt:g} ₪", "ok", "تم تسجيل الحركة"); return redirect("/cashbox")

    @app.post("/cashbox/<int:i>/delete")
    def cashbox_del(i):
        for _r in q("select receipt from cash_entries where id=? and user_id=?", (i, uid())): del_file(_r["receipt"])
        ex("delete from cash_entries where id=? and user_id=?", (i, uid())); notify("تم حذف الحركة", "ok"); return redirect(request.referrer or "/cashbox")

    @app.post("/cashbox/count")
    def cashbox_count():
        f = request.form
        ex("insert into cash_counts(user_id,created,expected,counted,note) values(?,?,?,?,?)", (uid(), now_s(), _f(f.get("expected")), _f(f.get("counted")), (f.get("note") or "").strip()[:200]))
        diff = round(_f(f.get("counted")) - _f(f.get("expected")), 2)
        notify(("مطابق ✓" if abs(diff) < 0.005 else f"الفرق {diff:+g} ₪"), "ok" if abs(diff) < 0.005 else "warn", "تم حفظ الجرد"); return redirect("/cashbox")

    @app.post("/cashbox/close")
    def cashbox_close():
        f = request.form; day = (f.get("day") or today())[:10]
        try: datetime.date.fromisoformat(day)
        except ValueError: day = today()
        if day > today(): day = today()
        if q("select 1 from day_closings where user_id=? and day=?", (uid(), day)):
            flash("اليوم مقفل|هاليوم مقفل من قبل. ألغِ الإقفال أول إذا بدك تعيد الجرد.", "warn"); return redirect(f"/cashbox?day={day}")
        rows, _ = ledger(); fg = day_figs(rows, day); expected = fg["cash_end"]
        counted = round(max(_f(f.get("counted"), expected), 0), 2)
        wd = round(min(max(_f(f.get("withdrawn"), counted), 0), counted), 2)
        diff = round(counted - expected, 2); note = (f.get("note") or "").strip()[:200]
        adj = None
        if abs(diff) >= 0.005:   # فرق الجرد بينسجّل كتسوية عشان رصيد الدرج يطابق المعدود
            adj = ins("insert into cash_entries(user_id,created,kind,direction,amount,account,category,supplier_id,note,created_at) values(?,?,?,?,?,?,?,?,?,?)",
                     (uid(), day, "تسوية جرد", "in" if diff > 0 else "out", abs(diff), "نقد", "", None, "فرق الجرد عند إقفال اليوم", now_s()))
        wid = None
        if wd > 0:
            wid = ins("insert into cash_entries(user_id,created,kind,direction,amount,account,category,supplier_id,note,created_at) values(?,?,?,?,?,?,?,?,?,?)",
                     (uid(), day, "سحب", "out", wd, "نقد", "", None, "سحب عند إقفال اليوم" + (f" — {note}" if note else ""), now_s()))
        ex("insert into cash_counts(user_id,created,expected,counted,note) values(?,?,?,?,?)", (uid(), now_s(), expected, counted, f"إقفال {day}" + (f" — {note}" if note else "")))
        ex("insert into day_closings(user_id,day,closed_at,expected,counted,withdrawn,diff,income,expenses,profit,note,withdraw_entry_id,adjust_entry_id) values(?,?,?,?,?,?,?,?,?,?,?,?,?)",
           (uid(), day, now_s(), expected, counted, wd, diff, fg["inn"], fg["exp"], fg["profit"], note, wid, adj))
        notify(f"{day} · دخل {fg['inn']:g} · مربح {fg['profit']:g} · سحبت {wd:g} ₪", "ok", "تم إقفال اليوم")
        return redirect(f"/cashbox?day={day}")

    @app.post("/cashbox/close/<int:i>/undo")
    def cashbox_close_undo(i):
        r = q("select * from day_closings where id=? and user_id=?", (i, uid()))
        if not r: return redirect("/cashbox")
        r = r[0]
        for k in ("withdraw_entry_id", "adjust_entry_id"):
            if r[k]: ex("delete from cash_entries where id=? and user_id=?", (r[k], uid()))
        ex("delete from day_closings where id=? and user_id=?", (i, uid()))
        notify(f"{r['day']} — رجع المبلغ المسحوب للصندوق", "warn", "تم إلغاء إقفال اليوم"); return redirect(f"/cashbox?day={r['day']}")

    # ---------- دخل اليوم: كل اللي انباع (مبيعات + صيانات مسلّمة) مع المربح
    @app.route("/today")
    def today_page():
        t = today()
        try: dd = datetime.date.fromisoformat(request.args.get("d") or t)
        except ValueError: dd = datetime.date.fromisoformat(t)
        d = min(dd.isoformat(), t); dd = datetime.date.fromisoformat(d)
        sales = [dict(r) for r in q("select * from sales where user_id=? and created like ? order by id desc", (uid(), d + "%"))]
        its = {}
        if sales:
            for r in q("select * from sale_items where user_id=? and sale_id in (%s) order by id" % ",".join("?" * len(sales)), (uid(),) + tuple(x["id"] for x in sales)): its.setdefault(r["sale_id"], []).append(r)
        rows = []
        for s_ in sales:
            L = its.get(s_["id"], [])
            pf = round(sum(x["qty"] * (x["price"] - (x["cost"] or 0)) for x in L) - (s_["discount"] or 0), 2)
            rows.append(dict(kind="بيع", t=(s_["created"] or "")[11:16], title="، ".join(f"{x['qty']}×{x['name']}" for x in L[:4]) + ("..." if len(L) > 4 else ""), who=s_["person_name"] or "",
                             total=s_["total"] or 0, paid=s_["paid"] or 0, profit=pf, link=f"/sales/{s_['id']}", ref="SALE-%04d" % s_["id"], sk=s_["id"]))
        for r in q("select * from repairs where user_id=? and status='تم التسليم' and coalesce(done_date,created)=? order by id desc", (uid(), d)):
            rows.append(dict(kind="صيانة", t="", title=f"{r['device'] or ''} — {r['issue'] or ''}".strip(" —"), who=r["customer"] or "", total=r["price"] or 0, paid=r["price"] or 0,
                             profit=round((r["price"] or 0) - (r["cost"] or 0), 2), link=f"/repairs?from={d}&to={d}", ref=f"#{r['id']}", sk=0))
        rows.sort(key=lambda x: (x["t"], x["sk"]), reverse=True)
        pend = q("select count(*) n from repairs where user_id=? and status<>'تم التسليم' and created=?", (uid(), d))[0]["n"]
        col = q("select coalesce(sum(amount),0) a from debt_entries where user_id=? and kind<>'دين' and sale_id is null and created=?", (uid(), d))[0]["a"] or 0
        S = dict(n=len(rows), income=round(sum(x["total"] for x in rows), 2), paid=round(sum(x["paid"] for x in rows), 2), profit=round(sum(x["profit"] for x in rows), 2),
                 sales=round(sum(x["total"] for x in rows if x["kind"] == "بيع"), 2), rep=round(sum(x["total"] for x in rows if x["kind"] == "صيانة"), 2))
        S["debt"] = round(S["income"] - S["paid"], 2)
        prev = (dd - datetime.timedelta(days=1)).isoformat(); nxt = (dd + datetime.timedelta(days=1)).isoformat() if d < t else None
        return render_template("today", rows=rows, S=S, d=d, t=t, prev=prev, nxt=nxt, dname=AR_DAYS[dd.weekday()], pend=pend, col=round(col, 2),
                               ttl=("دخل اليوم", "كل اللي بعته اليوم (مبيعات من الكاشير والمتجر + الصيانات المسلّمة) ومربحه"))

    @app.post("/cashbox/open")
    def cashbox_open():
        f = request.form
        ex("update settings set cash_open=?, bank_open=? where user_id=?", (_f(f.get("cash_open")), _f(f.get("bank_open")), uid())); return redirect("/cashbox")
