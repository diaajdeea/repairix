# -*- coding: utf-8 -*-
"""حسابات + مظهر: ثيم فاتح/داكن، تسجيل بطلب موافقة عبر واتساب (رابط wa.me)، لوحة موافقة المالك."""
import datetime, hmac, os, secrets
from urllib.parse import quote


def register(ns):
    app, T, q, ex, uid = ns["app"], ns["T"], ns["q"], ns["ex"], ns["uid"]
    render_template, redirect, request, flash, session = ns["render_template"], ns["redirect"], ns["request"], ns["flash"], ns["session"]
    OWNER_EMAIL, today, is_owner, cur_user = ns["OWNER_EMAIL"], ns["today"], ns["is_owner"], ns["cur_user"]
    generate_password_hash, TRIAL_DAYS = ns["generate_password_hash"], ns["TRIAL_DAYS"]

    # ---------------- الثيم ----------------
    HEAD = ("<script>(function(){try{var h=document.documentElement;if(localStorage.getItem('rx-theme')==='dark')h.setAttribute('data-theme','dark');if(localStorage.getItem('rx-lang')==='en'){h.setAttribute('dir','ltr');h.setAttribute('lang','en')}}catch(e){}})();"
            "document.addEventListener('click',function(e){var b=e.target.closest&&e.target.closest('[data-lang]');if(!b)return;var c;try{c=localStorage.getItem('rx-lang')==='en'?'en':'ar'}catch(x){c='ar'}var n=b.dataset.lang==='toggle'?(c==='en'?'ar':'en'):b.dataset.lang;try{localStorage.setItem('rx-lang',n)}catch(x){}location.reload()});"
            "document.addEventListener('DOMContentLoaded',function(){var c;try{c=localStorage.getItem('rx-lang')==='en'?'en':'ar'}catch(x){c='ar'}document.querySelectorAll('[data-lang]').forEach(function(b){if(b.dataset.lang==='toggle')b.textContent=c==='en'?'عربي':'EN';else b.classList.toggle('on',b.dataset.lang===c)})});"
            "function rxTheme(t){try{localStorage.setItem('rx-theme',t)}catch(e){}if(t==='dark')document.documentElement.setAttribute('data-theme','dark');else document.documentElement.removeAttribute('data-theme');"
            "document.querySelectorAll('[data-th]').forEach(function(b){b.classList.toggle('on',b.dataset.th===t)})}"
            "document.addEventListener('DOMContentLoaded',function(){var t=document.documentElement.getAttribute('data-theme')==='dark'?'dark':'light';document.querySelectorAll('[data-th]').forEach(function(b){b.classList.toggle('on',b.dataset.th===t);b.addEventListener('click',function(){rxTheme(b.dataset.th)})})});</script>")
    D = "html[data-theme=dark] "
    def r(sels, css): return ",".join(D + s.strip() for s in sels.split("|")) + "{" + css + "}"
    CSS = "<style>" + "".join([
        "html[data-theme=dark]{color-scheme:dark;--paper:#0a0f24;--ink:#e6e9f7;--mut:#9aa5c8;--line:#27315a;--navy:#e6e9f7;--sh:0 1px 2px #0006,0 10px 28px -14px #000a}",
        D + "body{background:#0a0f24;background-image:radial-gradient(900px 500px at 105% -8%,#3b2fd033,transparent 60%),radial-gradient(700px 480px at -8% 108%,#0e749033,transparent 60%);color:var(--ink)}",
        r(".card|.tools|.st|.sc|.pc|.tb7|dialog.dlg|.cpill|.bm|.stp|.psr|.pm2|.fxm|.fxo div|.tpf>summary|.st-top|.st-cats|.st-card|.st-q|.tl-card|.bp .pr3>div|.ring b|.pkqs|#dlg-give .pkmain|#dlg-pick .pkw|#dlg-pick .pktb|#dlg-pick .pkchip|#dlg-give .pkbr|.form|.lgx|.tbl.im|.tbl .wb|.lgp.im|.vt button.on|.tbar .tbl.im", "background:#141b3a!important;color:var(--ink);border-color:var(--line)"),
        r("input|select|textarea|.search input|.ct-pan input:not([type=radio]):not([type=checkbox])|.ct-pan select|.ct-pan textarea|.pkqs input", "background:#0d1330!important;color:var(--ink);border-color:#2f3a68"),
        r("input::placeholder|textarea::placeholder", "color:#6f7aa3"),
        r("th|.th|.df|.pr3>div|.pf|.pkft|.bp|#dlg-give .pkbasket", "background:#18204a!important;color:var(--ink)"),
        r("tbody tr:nth-child(even) td|table tr:nth-child(even)>td|#dlg-pick .pkrow:nth-child(even)", "background:#10173a"),
        r("tbody tr:hover td|tr:hover>td|table tr:hover>td|.lw:hover|.st-cats a:hover|.pm2 a:hover|#dlg-pick .pkrow:hover|.psit:hover", "background:#1c2552!important"),
        r(".ghost|.ib|button.ib|.tcl|.tch|.fx>summary|.fxc|.fxm button.fxr|.qt|.qb|.cpill em|.st-cats a em|.st-q button|.pkqs button|.tl-meta span|.pfx .pt|.dist|.pgb|.bar .tr|.toast .x|.dtl .nv a|.vt|#dlg-give .pksum div|.search input:focus", "background:#1d2656!important;color:#cfd6f5!important;border-color:#2f3a68"),
        r(".pick|.pkr|.bm-add|.si.a|.chips label:has(input:checked)|.pay label:has(input:checked)|#dlg-pick .pkrow.sel", "background:#26307a!important;color:#e6e9f7"),
        r(".tag|.pill.s2|.pl-g|.si.c|.si.f|.okb|.st-in|.fxs", "background:#0f3a2e!important;color:#6ee7b7!important"),
        r(".tag.bad|.pill.s3|.pl-r|.si.d|.err|.pfx .rx|.fxs.x|.pkrm:hover", "background:#40152a!important;color:#fda4af!important"),
        r(".pill.s0|.pl-a|.new|.si.e|.tbd|.fxs.m|#dlg-pick .pkbd.low", "background:#40300f!important;color:#fcd34d!important"),
        r(".si.g", "background:#34195a!important;color:#e9d5ff!important"),
        r(".hb .btn", "color:#0c1233!important"),
        r(".toast", "background:#141b3af2!important;border-color:var(--line)!important"),
        r(".hb .btn.o", "background:#ffffff22!important;color:#fff!important;border-color:#ffffff55!important"),
        r("#dlg-pick .pkchip:not(.on)", "color:#cfd6f5!important"),
        r(".cb-tabs a.on|a.on.btn|.tabs a.on|.seg a.on", "color:#fff!important"),
        r(".tbar", "background:#0f1638;border-color:var(--line)"),
        r("h1|h2|h3|b|label|.ph h2", "color:var(--ink)"),
        r("small|.ph p", "color:var(--mut)"),
        r("a:not(.btn):not(.ib):not(.tbr)", "color:#a5b4fc"),
        r("aside a", "color:#b4bde6"),
        r(".cut span|.st-add[disabled]", "background:#141b3a!important;color:var(--mut)"),
        # شبكة أمان: أي عنصر خلفيته فاتحة بستايل مباشر (inline) أو لونه غامق بيتحوّل للداكن
        r('[style*="background:#fff"]|[style*="background: #fff"]|[style*="background:white"]|[style*="background:#eef1fb"]|[style*="background:#f6f8ff"]|[style*="background:#fafbff"]|[style*="background:#f1f4fb"]|[style*="background:#e7ecff"]|[style*="background:#dfe5fb"]', "background:#141b3a!important;color:var(--ink)!important;border-color:var(--line)!important"),
        r('[style*="color:#33407a"]|[style*="color:#16213f"]|[style*="color:#1c2760"]|[style*="color:#5a6499"]|[style*="color:#6a74a8"]|[style*="color:#7a84b4"]|[style*="color:#1e2a5a"]|[style*="color:#0c1233"]', "color:#b4bde6!important"),
        # صفحة الموظفين: بطاقات القائمة، الأيقونات، الأزرار وألوان inline الغامقة
        r(".ec", "background:#141b3a!important;box-shadow:var(--sh),0 0 0 1px var(--line)"),
        r(".ec3>div", "background:#0d1330!important;border-color:var(--line)"),
        r(".ecf", "color:#a5b4fc"),
        r(".si.b|.pill.s1", "background:#0c3a47!important;color:#67e8f9!important"),
        r(".paybtn", "color:#fff!important"),
        "".join(D + '[style*="color:%s"]{color:%s!important}' % kv for kv in (("#059669", "#34d399"), ("#047857", "#34d399"), ("#16a34a", "#4ade80"), ("#e11d48", "#fb7185"), ("#dc2626", "#f87171"), ("#b45309", "#fbbf24"), ("#d97706", "#fbbf24"), ("#0e7490", "#67e8f9"), ("#4338ca", "#a5b4fc"), ("#4f46e5", "#a5b4fc"))),
        "html[lang=en] .st-add{font-size:12.5px;padding-inline:10px;white-space:nowrap}html[lang=en] body,html[lang=en] body *{direction:ltr}html[lang=en] .lx-card,html[lang=en] .lx-form{text-align:left}",
        # مبدّل المظهر (إعدادات + دخول)
        ".thm{display:flex;gap:10px;flex-wrap:wrap;margin-top:6px}.thm button{display:flex;align-items:center;gap:8px;padding:11px 20px;border-radius:14px;border:2px solid var(--line);background:transparent;color:var(--ink);font-weight:700;font-size:14px;font-family:inherit;cursor:pointer}.thm button.on{border-color:var(--br);box-shadow:0 0 0 3px #4f46e533}.thm svg{width:18px;height:18px}",
        ".thm button{background:#fff!important;color:#1e2a5a!important;border:2px solid #cfd7f1!important;box-shadow:none!important;opacity:1!important}.thm button:hover{border-color:var(--br)!important}.thm button.on{background:#eef0ff!important;border-color:var(--br)!important;box-shadow:0 0 0 3px #4f46e533!important}.thm button svg{color:inherit;stroke:currentColor}",
        D + ".thm button{background:#141b3a!important;color:#e6e9f7!important;border-color:#27315a!important}",
        D + ".thm button.on{background:#26307a!important;color:#fff!important;border-color:#8ea2ff!important}",
        # 2) صفحة الدخول: بالعربي الكرت يمين (RTL) وبالإنجليزي يسار (LTR)
        "html .lx{direction:ltr}",
        "@media(max-width:760px){.lx .lx-form{padding-top:84px!important}}",
        ".thf{position:fixed;top:14px;left:14px;z-index:50;display:flex;gap:4px;padding:4px;border-radius:99px;background:#ffffffd9;border:1px solid #0001;box-shadow:0 8px 24px -10px #0006;-webkit-backdrop-filter:blur(10px);backdrop-filter:blur(10px)}.thf button{width:36px;height:36px;border-radius:50%;border:0;background:transparent;cursor:pointer;display:grid;place-items:center;color:#475569}.thf button.on{background:var(--br);color:#fff}.thf svg{width:18px;height:18px}.thf button[data-lang]{font-weight:800;font-size:12px;font-family:inherit}.thsep{width:1px;background:#0002;margin:6px 2px}",
        D + ".thf{background:#141b3ad9;border-color:#ffffff22}",
        D + ".thf button{color:#b4bde6}",
        D + ".thf button.on{background:var(--br);color:#fff}",
        D + ".pkr{border-color:#4a3fd0!important}",
        D + ".pkr b{color:#dfe3ff!important}",
        D + ".pkr label{color:#b4bde6}",
        # صفحة الدخول: العربي = الفورم يسار، الإنجليزي = الفورم يمين
        "html .lx{grid-template-columns:minmax(380px,.9fr) 1.1fr;grid-template-areas:'form art'}html .lx-form{grid-area:form}html .lx-art{grid-area:art}",
        "html[lang=en] .lx{grid-template-columns:1.1fr minmax(380px,.9fr);grid-template-areas:'art form'}",
        "@media(max-width:900px){html .lx,html[lang=en] .lx{grid-template-columns:1fr;grid-template-areas:'form' 'art'}}",
        "html[lang=en] .pw .lk{left:12px;right:auto}",
        ".lgm{position:fixed;top:14px;right:14px;left:auto;z-index:50;direction:ltr;font-family:system-ui,sans-serif}.lgm button{display:flex;align-items:center;gap:8px;margin:0;padding:8px 12px;border-radius:12px;border:1px solid #ffffff22;background:#141b3acc;-webkit-backdrop-filter:blur(10px);backdrop-filter:blur(10px);color:#b4bde6;font-size:13px;font-weight:700;letter-spacing:.04em;cursor:pointer}.lgm button svg{width:20px;height:20px}.lgm button:hover{color:#fff;border-color:#ffffff44}",
        ".lgm ul{position:absolute;top:calc(100% + 6px);right:0;margin:0;padding:6px;list-style:none;min-width:140px;background:#141b3af2;border:1px solid #ffffff22;border-radius:12px;box-shadow:0 18px 40px -14px #000a}.lgm li{padding:9px 12px;border-radius:8px;color:#e6e9f7;font-size:14px;cursor:pointer;text-align:left}.lgm li:hover{background:#ffffff14}.lgm li.on{background:var(--br);color:#fff}",
        D + ".lx-card{background:#121a3ae6;border-color:#ffffff1f;color:var(--ink);--wm:#e6e9f7}",
        D + ".lx-card label,.lx-card .sub,.lx-card h1{color:var(--ink)}",
        D + ".lx-card .sub,.lx-card .sw{color:var(--mut)}",
        D + ".lx-card .tbx{background:#1b2452;border-color:#ffffff24}",
        D + ".lx-card .tbx b{color:#fff}",
        D + ".lx-card .tbx small{color:#c7d2ff}",
        D + ".lx-card input{color:#fff;background:#0d1330;border-color:#2c3768}",
        D + ".lx-card .tbp{background:#4f46e533;color:#a5b4fc;border-color:#6d5efc55}",
        D + ".lx-card .lgbx{border-color:#ffffff24;background:#0d133066}",
        D + ".lx-card .lgi{border-color:#8a95bd}",
        D + ".lx-card input::placeholder{color:#8a95bd}",
        # وضع فاتح لصفحة الدخول (الخلفية الافتراضية داكنة، نفتّحها)
        "html:not([data-theme=dark]) .lx{background:#eef1fb}html:not([data-theme=dark]) .lx-bg{background:linear-gradient(125deg,#eef1ff,#dfe6ff,#e6f6ff,#f3eaff,#eef1ff);background-size:400% 400%}",
        "html:not([data-theme=dark]) .lx-bg:before{opacity:.35}html:not([data-theme=dark]) .lx-orb{opacity:.28}",
        "html:not([data-theme=dark]) .lx-art,html:not([data-theme=dark]) .lx-art p,html:not([data-theme=dark]) .lx-art .pts,html:not([data-theme=dark]) .lx-art .tg{color:#1e2a5a}",
        "html:not([data-theme=dark]) .lx-art h2{text-shadow:none;color:#0c1233}",
        "html:not([data-theme=dark]) .lx-chip{background:#ffffffb0;border-color:#0001;color:#0c1233}html:not([data-theme=dark]) .lx-chip small{color:#475569}",
    ]) + "</style>"
    SUN = '<svg viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2 stroke-linecap=round><circle cx=12 cy=12 r=4 /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>'
    MOON = '<svg viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2 stroke-linecap=round stroke-linejoin=round><path d="M21 12.8A9 9 0 1111.2 3a7 7 0 009.8 9.8z"/></svg>'
    FLOAT = f'<div class=thf role=group aria-label="المظهر"><button type=button data-th=light title="فاتح" aria-label="فاتح">{SUN}</button><button type=button data-th=dark title="داكن" aria-label="داكن">{MOON}</button><span class=thsep></span><button type=button data-lang=ar title="عربي">ع</button><button type=button data-lang=en title="English">EN</button></div>'
    CARD = (f'<div class=card style="margin-top:16px"><h3>المظهر</h3><small>اختر شكل البرنامج. الاختيار بيتحفظ على هذا الجهاز.</small>'
            f'<div class=thm><button type=button data-th=light>{SUN} فاتح</button><button type=button data-th=dark>{MOON} داكن</button></div>'
            f'<h3 style="margin-top:18px">اللغة</h3><div class=thm><button type=button data-lang=ar>عربي</button><button type=button data-lang=en>English</button></div></div>')

    b = T["base"]
    T["base"] = b.replace("<meta name=viewport", HEAD + "<meta name=viewport", 1).replace("<div id=tc", CSS + '<script src="/i18n.js?v=1" defer></script><div id=tc', 1)
    T["base"] = T["base"].replace('<a class="ib tgs', '<button type=button class=ib data-lang=toggle title="Language / اللغة" aria-label="Language" style="font-weight:800;font-size:12px;min-width:44px">EN</button><a class="ib tgs', 1)
    FLOAT_AUTH = FLOAT.replace(f'<button type=button data-th=light title="فاتح" aria-label="فاتح">{SUN}</button><button type=button data-th=dark title="داكن" aria-label="داكن">{MOON}</button><span class=thsep></span>', '')
    LANGMENU = ('<div class=lgm><button type=button id=lgb aria-haspopup=listbox aria-expanded=false title="Language / اللغة"><span id=lgc>AR</span><svg viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=1.8 stroke-linecap=round stroke-linejoin=round><path d="M4 5h8M8 3v2M5.5 5c.6 3 2.6 5.3 5.5 6.5M11 5c-.6 3-2.8 5.7-6.5 7.2"/><path d="M12 20l4-9 4 9M13.5 17h5"/></svg></button>'
                '<ul id=lgl role=listbox hidden><li role=option data-v=ar>العربية</li><li role=option data-v=en>English</li></ul></div>'
                "<script>(function(){var b=document.getElementById('lgb'),l=document.getElementById('lgl'),t=document.getElementById('lgc');if(!b)return;var c;try{c=localStorage.getItem('rx-lang')==='en'?'en':'ar'}catch(e){c='ar'}t.textContent=c.toUpperCase();[].forEach.call(l.children,function(i){if(i.dataset.v===c)i.className='on'});"
                "b.addEventListener('click',function(e){e.stopPropagation();l.hidden=!l.hidden;b.setAttribute('aria-expanded',String(!l.hidden))});document.addEventListener('click',function(){l.hidden=true});"
                "l.addEventListener('click',function(e){var v=e.target.dataset&&e.target.dataset.v;if(!v)return;try{localStorage.setItem('rx-lang',v)}catch(x){}location.reload()})})();</script>")
    T["auth"] = T["auth"].replace("<div class=lx>", LANGMENU + "<div class=lx>", 1)
    T["auth"] = T["auth"].replace("{% block c %}", "{% block c %}<script>document.documentElement.setAttribute('data-theme','dark')</script>", 1)
    s = T["settings"]
    T["settings"] = s.replace("<p><button>حفظ</button></p></form>", "<p><button>حفظ</button></p></form>", 1)
    T["settings"] = T["settings"].replace('<div class=card style="margin-top:16px"><h3>تغيير كلمة السر</h3>', CARD + '<div class=card style="margin-top:16px"><h3>تغيير كلمة السر</h3>', 1)

    # ---------------- واتساب ----------------
    def digits(p): return "".join(c for c in (p or "") if c.isdigit())
    def intl(p, cc="970"):
        d = digits(p)
        return d[2:] if d.startswith("00") else (cc + d[1:] if d.startswith("0") else d)
    def owner_wa():
        r_ = q("select v from meta where k='owner_whatsapp'")
        return intl((r_[0]["v"] if r_ else "") or os.environ.get("OWNER_WHATSAPP", ""))
    def wa_link(phone, text): return f"https://wa.me/{phone}?text={quote(text)}"
    ns["owner_wa"], ns["wa_link"], ns["intl_phone"] = owner_wa, wa_link, intl

    # ---------------- صفحة الانتظار ----------------
    T["pending"] = """<!doctype html><html lang=ar dir=rtl><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>بانتظار الموافقة</title><script src="/i18n.js?v=1" defer></script>
<script>(function(){try{var h=document.documentElement;if(localStorage.getItem('rx-theme')==='dark')h.setAttribute('data-theme','dark');if(localStorage.getItem('rx-lang')==='en'){h.setAttribute('dir','ltr');h.setAttribute('lang','en')}}catch(e){}})();document.addEventListener('click',function(e){var b=e.target.closest&&e.target.closest('[data-lang]');if(!b)return;try{localStorage.setItem('rx-lang',b.dataset.lang)}catch(x){}location.reload()});document.addEventListener('DOMContentLoaded',function(){var c;try{c=localStorage.getItem('rx-lang')==='en'?'en':'ar'}catch(x){c='ar'}document.querySelectorAll('[data-lang]').forEach(function(b){b.classList.toggle('on',b.dataset.lang===c)})});function rxTheme(t){try{localStorage.setItem('rx-theme',t)}catch(e){}if(t==='dark')document.documentElement.setAttribute('data-theme','dark');else document.documentElement.removeAttribute('data-theme');document.querySelectorAll('[data-th]').forEach(function(b){b.classList.toggle('on',b.dataset.th===t)})}
document.addEventListener('DOMContentLoaded',function(){var t=document.documentElement.getAttribute('data-theme')==='dark'?'dark':'light';document.querySelectorAll('[data-th]').forEach(function(b){b.classList.toggle('on',b.dataset.th===t);b.addEventListener('click',function(){rxTheme(b.dataset.th)})})});</script>
<style>:root{--br:#4f46e5;--ink:#0f172a;--mut:#64748b;--card:#fff;--bg:linear-gradient(140deg,#eef1ff,#dfe6ff 60%,#e6f6ff)}
html[data-theme=dark]{--ink:#e6e9f7;--mut:#9aa5c8;--card:#141b3a;--bg:linear-gradient(140deg,#0c1233,#1a2370 60%,#0b3b78);color-scheme:dark}
body{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--bg);font-family:system-ui,Tahoma,Arial,sans-serif;color:var(--ink)}
.bx{background:var(--card);border-radius:24px;padding:34px 30px;width:min(500px,92vw);box-shadow:0 40px 90px -30px #000a;text-align:center}
.ic{width:70px;height:70px;border-radius:50%;background:#eef0ff;color:var(--br);display:grid;place-items:center;margin:0 auto 12px}
h1{margin:0 0 6px;font-size:23px}p{color:var(--mut);line-height:1.8;margin:6px 0}
.sm{background:#f1f4fb;border-radius:14px;padding:10px 14px;text-align:right;font-size:13.5px;margin:14px 0}html[data-theme=dark] .sm{background:#0d1330}.sm b{color:var(--ink)}
.wa{display:flex;align-items:center;justify-content:center;gap:10px;padding:13px 20px;border-radius:14px;background:#16a34a;color:#fff;text-decoration:none;font-weight:700;margin:10px 0}
form{margin-top:16px;text-align:right}label{font-weight:700;font-size:13.5px}input{width:100%;box-sizing:border-box;margin-top:6px;padding:13px;border-radius:12px;border:1px solid #cdd5e8;font:700 22px monospace;letter-spacing:.4em;text-align:center;background:transparent;color:var(--ink)}
button.go{width:100%;margin-top:12px;padding:13px;border:0;border-radius:12px;background:linear-gradient(135deg,#4f46e5,#6d5efc);color:#fff;font-weight:700;font-size:16px;font-family:inherit;cursor:pointer}
.err{background:#fff1f3;color:#be123c;border-radius:12px;padding:10px;margin-top:12px;font-size:13.5px}.out{display:block;margin-top:16px;color:var(--mut);font-size:13.5px}
.thf{position:fixed;top:14px;left:14px;display:flex;gap:4px;padding:4px;border-radius:99px;background:#ffffffd9;border:1px solid #0001;box-shadow:0 8px 24px -10px #0006}.thf button{width:36px;height:36px;border-radius:50%;border:0;background:transparent;cursor:pointer;display:grid;place-items:center;color:#475569}.thf button.on{background:var(--br);color:#fff}.thf svg{width:18px;height:18px}.thf button[data-lang]{font-weight:800;font-size:12px;font-family:inherit}.thsep{width:1px;background:#0002;margin:6px 2px}
html[data-theme=dark] .thf{background:#141b3ad9}html[data-theme=dark] .thf button{color:#b4bde6}html[data-theme=dark] .thf button.on{color:#fff}html[data-theme=dark] .err{background:#40152a;color:#fda4af}html[data-theme=dark] .ic{background:#26307a}</style>
""" + FLOAT + """
<div class=bx><div class=ic><svg width=34 height=34 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2 stroke-linecap=round stroke-linejoin=round><circle cx=12 cy=12 r=9 /><path d="M12 7v5l3 2"/></svg></div>
<h1>طلبك قيد الموافقة</h1><p>أهلاً {{u.full_name or u.email}}، حسابك لسا ما اتفعّل. مالك البرنامج بيراجع الطلب وبيعطيك <b>كود تفعيل</b> من 6 أرقام.</p>
<div class=sm>الاسم: <b>{{u.full_name}}</b><br>الهاتف: <b dir=ltr>{{u.phone}}</b><br>الإيميل: <b dir=ltr>{{u.email}}</b></div>
{% if wa %}<a class=wa href="{{wa}}" target=_blank rel=noopener>إرسال طلب الموافقة للمالك عبر واتساب</a>{% else %}<p>تواصل مع المالك على <b dir=ltr>{{owner_email}}</b> لتفعيل حسابك.</p>{% endif %}
{% if err %}<div class=err role=alert>{{err}}</div>{% endif %}
<form method=post action=/activate><label for=cd>عندك الكود من المالك؟ اكتبه هنا</label><input id=cd name=code inputmode=numeric maxlength=6 autocomplete=one-time-code placeholder="••••••" dir=ltr required><button class=go>تفعيل حسابي وبدء التجربة ({{trial_days}} أيام)</button></form>
<a class=out href=/logout>تسجيل الخروج</a></div></html>"""

    def req_msg(u):
        return (f"مرحباً، بدي أفعّل حساب جديد على {ns['BRAND']}.\nالاسم: {u['full_name']}\nالهاتف: {u['phone']}\nالإيميل: {u['email']}\nرقم الطلب: {u['id']}\nالرجاء إرسال كود الموافقة.")

    def pending_page(err=None):
        u = cur_user(); w = owner_wa()
        return render_template("pending", u=u, wa=wa_link(w, req_msg(u)) if w else None, err=err, owner_email=OWNER_EMAIL, trial_days=TRIAL_DAYS)

    @app.route("/pending")
    def pending():
        u = cur_user()
        if (u.get("status") or "active") != "pending": return redirect("/")
        return pending_page()

    @app.post("/activate")
    def activate():
        u = cur_user()
        if (u.get("status") or "active") != "pending": return redirect("/")
        code = "".join(c for c in request.form.get("code", "") if c.isdigit())
        if (u.get("approval_tries") or 0) >= 5: return pending_page("تجاوزت عدد المحاولات. اطلب من المالك كود جديد.")
        if not u.get("approval_code"): return pending_page("المالك لسا ما أعطاك كود. أرسل الطلب عبر واتساب وانتظر.")
        if not hmac.compare_digest(code, u["approval_code"]):
            ex("update users set approval_tries=coalesce(approval_tries,0)+1 where id=?", (u["id"],)); return pending_page("الكود غلط")
        _activate(u["id"]); flash(f"تم تفعيل حسابك|بدأت تجربتك المجانية ({TRIAL_DAYS} أيام). بالتوفيق!", "ok"); return redirect("/")

    def _activate(i):
        ex("update users set status='active', approval_code=null, approval_tries=0, approved_at=? where id=?", (datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), i))
        ex("update settings set trial_start=? where user_id=?", (today(), i))

    # ---------------- لوحة المالك ----------------
    def pend_rows():
        out = []
        for x in q("select u.*, s.shop_name from users u left join settings s on s.user_id=u.id where u.status='pending' order by u.id desc"):
            x = dict(x); x["wa"] = None
            if x.get("approval_code") and x.get("phone"):
                x["wa"] = wa_link(intl(x["phone"]), f"مرحباً {x.get('full_name') or ''}، تمت الموافقة على حسابك في {ns['BRAND']}.\nكود التفعيل: {x['approval_code']}\nادخل الكود في صفحة الانتظار لتبدأ تجربتك المجانية.")
            out.append(x)
        return out
    ns["pend_rows"] = pend_rows

    T["owner"] = T["owner"].replace("<div class=tools>", """{% if pend is defined %}<div class=card style="margin-bottom:16px"><h3>طلبات الحسابات الجديدة{% if pend %} <span class="pill pl-a">{{pend|length}}</span>{% endif %}</h3>
<form method=post action=/owner/wa style="display:flex;gap:8px;flex-wrap:wrap;align-items:end;margin-bottom:12px"><label style="flex:1;min-width:220px;font-size:13px">رقم واتساب المالك (يستقبل طلبات الموافقة)<input name=wa value="{{owner_wa_raw}}" placeholder="مثال: 0599123456" dir=ltr></label><button>حفظ الرقم</button></form>
{% if not owner_wa_raw %}<div class=err>حط رقم واتساب لتوصلك طلبات الموافقة. بدونه الزبون بيشوف إيميلك بدل زر واتساب.</div>{% endif %}
{% if pend %}<div style="overflow:auto"><table><tr><th>الاسم<th>الهاتف<th>الإيميل<th>الشركة<th>التاريخ<th>إجراء</tr>
{% for p in pend %}<tr><td>{{p.full_name or '—'}}<td dir=ltr>{{p.phone or '—'}}<td dir=ltr>{{p.email}}<td>{{p.shop_name or '—'}}<td dir=ltr>{{p.approval_requested or ''}}
<td>{% if p.approval_code %}الكود: <b dir=ltr style="font-size:18px;letter-spacing:.15em">{{p.approval_code}}</b> {% if p.wa %}<a class="btn" target=_blank rel=noopener href="{{p.wa}}">أرسل الكود واتساب</a>{% endif %}{% endif %}
<form method=post action=/owner/approve style="display:inline"><input type=hidden name=sid value="{{p.id}}"><button>{{ 'كود جديد' if p.approval_code else 'موافقة وتوليد كود' }}</button></form>
<form method=post action=/owner/activate style="display:inline"><input type=hidden name=sid value="{{p.id}}"><button class=ghost>تفعيل مباشر</button></form>
<form method=post action=/owner/reject style="display:inline" onsubmit="return confirm('رفض الطلب وحذف الحساب؟')"><input type=hidden name=sid value="{{p.id}}"><button class=ghost>رفض</button></form></tr>{% endfor %}</table></div>{% else %}<small>لا توجد طلبات معلّقة.</small>{% endif %}</div>{% endif %}
<div class=tools>""", 1)

    def _pend_target():
        r_ = q("select * from users where id=? and status='pending' and lower(email)<>?", (request.form.get("sid"), OWNER_EMAIL))
        return dict(r_[0]) if r_ else None

    @app.post("/owner/wa")
    def owner_wa_save():
        v = "".join(c for c in request.form.get("wa", "") if c.isdigit() or c == "+").strip()
        ex("insert into meta(k,v) values('owner_whatsapp',?) on conflict(k) do update set v=excluded.v", (v,))
        flash("تم الحفظ|رقم واتساب المالك: " + (v or "غير محدد"), "ok"); return redirect("/owner")

    @app.post("/owner/approve")
    def owner_approve():
        u = _pend_target()
        if u:
            ex("update users set approval_code=?, approval_tries=0 where id=?", (f"{secrets.randbelow(900000) + 100000}", u["id"]))
            flash("تمت الموافقة|أرسل الكود للمستخدم عبر زر واتساب بجانب اسمه", "ok")
        return redirect("/owner")

    @app.post("/owner/activate")
    def owner_activate():
        u = _pend_target()
        if u: _activate(u["id"]); flash("تم تفعيل الحساب|" + u["email"], "ok")
        return redirect("/owner")

    @app.post("/owner/reject")
    def owner_reject():
        u = _pend_target()
        if u:
            lg = q("select logo from settings where user_id=?", (u["id"],))
            if lg and lg[0]["logo"]: ns["del_file"](lg[0]["logo"])
            ex("delete from settings where user_id=?", (u["id"],)); ex("delete from users where id=?", (u["id"],))
            flash("تم رفض الطلب|" + u["email"], "warn")
        return redirect("/owner")

    # ---------------- A4 بسيط ----------------
    T["a4css"] = """<!doctype html><html lang=ar dir=rtl><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>{{doc_title}} {{ref}}</title>
<style>
@page{size:A4;margin:14mm 14mm 16mm;@bottom-left{content:"صفحة " counter(page) " من " counter(pages);font:10px Tahoma,Arial,sans-serif;color:#000}}
*{box-sizing:border-box}
html,body{margin:0;background:#e5e5e5;color:#000}
body{font-family:Tahoma,"Segoe UI",Arial,sans-serif;font-size:13px;line-height:1.6}
.bar{background:#222;padding:10px;text-align:center;position:sticky;top:0;z-index:5}
.bar button{margin:3px 4px;padding:8px 18px;font:inherit;border:0;background:#fff;color:#000;border-radius:6px;cursor:pointer;font-weight:700}
.bar a.hint{color:#ddd;font-size:12px;margin-right:10px}
.sheet{width:210mm;margin:14px auto;background:#fff;padding:14mm;box-shadow:0 2px 12px rgba(0,0,0,.25)}
.hd{display:flex;flex-direction:column;align-items:center;gap:6px;text-align:center;padding-bottom:10px;border-bottom:1px solid #000}
.hd .who{display:flex;flex-direction:column;align-items:center;gap:6px}.hd img{max-height:28mm;max-width:70mm;object-fit:contain;display:block;margin:0 auto}
.hd .nm{font-size:19px;font-weight:700}.hd .adr{font-size:12.5px;color:#222}.hd .dt{font-size:12px}
h1.tt{margin:0 0 2px;font-size:22px;text-align:center;font-weight:700}
.hd3{display:grid;grid-template-columns:1fr auto 1fr;gap:12px;align-items:center;padding-bottom:10px;border-bottom:1px solid #000}.hd3 .hr{text-align:right}.hd3 h1.tt{margin:0 0 2px;font-size:20px;text-align:right}.hd3 .rf{text-align:right;margin:0}.hd3 .hc{display:flex;flex-direction:column;align-items:center;gap:6px;text-align:center}.hd3 .hc img{max-height:28mm;max-width:70mm;object-fit:contain;display:block}.hd3 .nm{font-size:19px;font-weight:700}.hd3 .adr{font-size:12.5px;color:#222}.hd3 .hl{text-align:left;font-size:12px}.rf{text-align:center;margin-bottom:10px}.hd{margin-top:6px}
.info{display:grid;grid-template-columns:1fr 1fr;gap:4px 24px;margin:10px 0 14px}.info div{padding:2px 0;border-bottom:1px dotted #777}.info span{color:#444}
table.items{width:100%;border-collapse:collapse;margin-top:6px}
.items th,.items td{border:1px solid #000;padding:5px 8px;text-align:right}.items th{font-weight:700}
.items tr{break-inside:avoid;page-break-inside:avoid}.items thead{display:table-header-group}
.n{width:34px;text-align:center}.num{white-space:nowrap;text-align:left}.dt2{display:block;font-size:10.5px;color:#444}
.sum{margin:12px 0 0 auto;width:260px;border-collapse:collapse}.sum td{padding:4px 8px;border-bottom:1px solid #999}.sum tr.net td{border-top:2px solid #000;border-bottom:2px solid #000;font-weight:700;font-size:15px}
.note{margin-top:14px;font-size:12px;color:#222;break-inside:avoid}
.sigs{display:grid;grid-template-columns:1fr 1fr;gap:40px;margin-top:34px;break-inside:avoid}.sigs div{border-top:1px solid #000;padding-top:4px;text-align:center;font-size:12px}
.h2{margin:18px 0 4px;font-size:14px;font-weight:700}
@media print{html,body{background:#fff}.bar{display:none}.sheet{width:auto;margin:0;padding:0;box-shadow:none}}
</style>"""
    T["a4doc"] = """{% include 'a4css' %}
<div class=bar><button type=button onclick="history.length>1?history.back():location.href='{{back}}'">← رجوع</button><button onclick="print()">طباعة / حفظ PDF</button><a href="{{th_url}}"><button type=button>نسخة حرارية</button></a>{% if can_stock %}<a href="?{{ '' if with_stock else 'stock=1' }}"><button type=button>{{ 'بدون قطع المخزون' if with_stock else 'مع قطع المخزون' }}</button></a>{% endif %}{% if not tb_logo %}<a class=hint href=/settings>أضف شعار شركتك من الإعدادات ليظهر هنا</a>{% endif %}</div>
<div class=sheet>
<div class=hd3><div class=hr><h1 class=tt>{{doc_title}}</h1><div class=rf dir=ltr>{% if ref %}{{ref}}{% endif %}</div></div><div class=hc>{% if tb_logo %}<img src="/shoplogo?v={{tb_logo}}" alt="">{% endif %}<div class=nm>{{st.shop_name}}</div>{% if st.address %}<div class=adr>{{st.address}}</div>{% endif %}</div><div class=hl dir=ltr>{{now}}</div></div>
<div class=info><div><span>المورد: </span><b>{{party or '—'}}</b></div><div><span>الهاتف: </span><b dir=ltr>{{phone or '—'}}</b></div><div><span>التاريخ: </span><b dir=ltr>{{now}}</b></div><div><span>البنود: </span><b>{{lines|length}} بند · {{qty}} قطعة</b></div></div>
{% if lines %}
<table class=items><thead><tr><th class=n>#<th>الصنف<th>الكمية<th class=num>سعر الوحدة<th class=num>المجموع</tr></thead><tbody>
{% for l in lines %}<tr><td class=n>{{l.n}}<td>{{l.name}}{% if l.kind=='مرتجع' %} (مرتجع){% endif %}{% if not ref %}<span class=dt2 dir=ltr>{{l.date}}</span>{% endif %}<td>{{l.qty}}<td class=num>{{ '%g'|format(l.cost) }} ₪<td class=num>{{ '%g'|format(l.signed) }} ₪</tr>{% endfor %}</tbody></table>
<table class=sum><tr><td>إجمالي المشتريات<td class=num dir=ltr>{{ '%g'|format(buy_total) }} ₪</tr>{% if ret_total %}<tr><td>المرتجعات<td class=num dir=ltr>-{{ '%g'|format(ret_total) }} ₪</tr>{% endif %}<tr class=net><td>الصافي المستحق<td class=num dir=ltr>{{ '%g'|format(net) }} ₪</tr></table>
<div class=note>يرجى مطابقة الكميات والأسعار عند الاستلام، وأي ملاحظة تُبلَّغ خلال 48 ساعة من تاريخ المستند.</div>
{% else %}<div class=note style="text-align:center">لا توجد مشتريات مسجّلة</div>{% endif %}
{% if stk %}<div class=h2>قطع المخزون من هذا المورد</div>
<table class=items><thead><tr><th class=n>#<th>الصنف<th>الكمية<th class=num>الجملة</tr></thead><tbody>{% for r in stk %}<tr><td class=n>{{loop.index}}<td>{{r.name}}{% if r.color %} · {{r.color}}{% endif %}<td>{{r.qty}}<td class=num>{{ '%g'|format(r.cost) }} ₪</tr>{% endfor %}</tbody></table>{% endif %}
</div>
<script>if(/[?&]auto=1/.test(location.search))window.addEventListener('load',function(){setTimeout(print,300)});</script></html>"""

    # ---------------- اللغة (عربي / English) ----------------
    import json as _json
    _D = {}
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "i18n_en.txt"), encoding="utf-8") as _f:
        for _l in _f:
            _l = _l.rstrip("\n")
            if "|" in _l: _a, _e = _l.split("|", 1); _D[" ".join(_a.split())] = _e
    _PAT = [[r"^(\d) أطراف$", "$1 parties"], [r"^اسم الطرف (\d)$", "Party $1 name"], [r"^المجموع ([\d.]+)% — لازم يكون 100%$", "Total $1% — must be 100%"], [r"^تجريبي · متبقي (\d+) أيام?$", "Trial · $1 days left"], [r"^(\d+) منتج$", "$1 products"], [r"^(\d+) صنف · (\d+) قطعة$", "$1 items · $2 pcs"], [r"^متوفر (\d+)$", "In stock $1"], [r"^نفد (\d+)$", "Out of stock $1"],
            [r"^منخفض (\d+)$", "Low $1"], [r"^المتوفر: (\d+)$", "In stock: $1"], [r"^(\d+) أيام?$", "$1 days"], [r"^متبقي (\d+) من (\d+) أيام · تنتهي بتاريخ (.+)$", "$1 of $2 days left · ends on $3"], [r"^متبقي (.+)$", "Remaining $1"],
            [r"^أهلاً بك في (.+)$", "Welcome to $1"], [r"^أهلاً (.+)، حسابك لسا ما اتفعّل.*$", "Hello $1, your account is not activated yet. The owner reviews your request and gives you a 6-digit activation code."],
            [r"^تفعيل حسابي وبدء التجربة \((\d+) أيام\)$", "Activate my account and start the trial ($1 days)"], [r"^طلب حساب جديد: (.+)$", "New account request: $1"],
            [r"^صيانات اليوم · (.+)$", "Today's repairs · $1"], [r"^(\d+) بند · (\d+) قطعة$", "$1 items · $2 pcs"], [r"^الكود: (\d+)$", "Code: $1"], [r"^جرّب REPAIRIX مجاناً لمدة (\d+) أيام$", "Try REPAIRIX free for $1 days"]]
    _JS = ("(function(){var D=" + _json.dumps(_D, ensure_ascii=False) + ",P=" + _json.dumps(_PAT, ensure_ascii=False) + ";var en;try{en=localStorage.getItem('rx-lang')==='en'}catch(e){}if(!en)return;"
           "var AR=/[\\u0600-\\u06FF]/;function T(t){var k=t.replace(/\\s+/g,' ').trim();if(!k||!AR.test(k))return t;var r=D[k];"
           "if(r===undefined){var m=k.match(/^(.*?)\\s*\\((\\d+)\\)$/);if(m&&D[m[1]]!==undefined)r=D[m[1]]+' ('+m[2]+')'}"
           "if(r===undefined){for(var i=0;i<P.length;i++){var x=new RegExp(P[i][0]).exec(k);if(x){r=P[i][1].replace(/\\$(\\d)/g,function(a,n){return x[n]});break}}}"
           "if(r===undefined)return t;var a=t.match(/^\\s*/)[0],b=t.match(/\\s*$/)[0];return a+r+b}"
           "var AT=['placeholder','title','aria-label','alt'];function el(e){if(e.nodeType!==1)return;AT.forEach(function(a){var v=e.getAttribute&&e.getAttribute(a);if(v&&AR.test(v)){var w=T(v);if(w!==v)e.setAttribute(a,w)}});"
           "if(e.tagName==='INPUT'&&(e.type==='submit'||e.type==='button')&&AR.test(e.value)){var u=T(e.value);if(u!==e.value)e.value=u}}"
           "function walk(n){if(n.nodeType===3){if(AR.test(n.nodeValue)){var p=n.parentNode&&n.parentNode.tagName;if(p!=='SCRIPT'&&p!=='STYLE'){var v=T(n.nodeValue);if(v!==n.nodeValue)n.nodeValue=v}}return}"
           "if(n.nodeType!==1)return;el(n);var c=n.firstChild;while(c){walk(c);c=c.nextSibling}}"
           "function go(){document.documentElement.setAttribute('dir','ltr');document.documentElement.setAttribute('lang','en');walk(document.body);if(AR.test(document.title))document.title=T(document.title);"
           "new MutationObserver(function(ms){ms.forEach(function(m){if(m.type==='characterData'){if(AR.test(m.target.nodeValue)){var v=T(m.target.nodeValue);if(v!==m.target.nodeValue)m.target.nodeValue=v}}else m.addedNodes.forEach(walk)})}).observe(document.body,{childList:true,subtree:true,characterData:true})}"
           "if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',go);else go()})();")

    @app.route("/i18n.js")
    def i18n_js():
        return app.response_class(_JS, mimetype="application/javascript", headers={"Cache-Control": "public, max-age=3600"})
