import urllib.parse, datetime, os, io, csv, uuid, re, secrets, hashlib, smtplib, json, time, threading
import urllib.request
from email.message import EmailMessage
from urllib.parse import quote
from flask import Flask, request, redirect, render_template, g, session, Response, flash, send_from_directory as _sfd, abort, jsonify
from markupsafe import Markup
from werkzeug.security import generate_password_hash, check_password_hash
from jinja2 import DictLoader
import pgdb

app = Flask(__name__)
HERE = os.path.dirname(os.path.abspath(__file__))

def _secret_key():
    """المفتاح السري: من SECRET_KEY، وإلا من ملف .secret_key (بيتولّد مرة وحدة). ما في مفتاح ثابت بالكود."""
    k = os.environ.get("SECRET_KEY")
    if k: return k
    kf = os.path.join(HERE, ".secret_key")
    try:
        if not os.path.exists(kf):
            with open(kf, "w") as fh: fh.write(secrets.token_hex(32))
        return open(kf).read().strip()
    except OSError:
        return secrets.token_hex(32)   # ملف للقراءة فقط: مفتاح مؤقت (الجلسات بتنتهي عند إعادة التشغيل) — عيّن SECRET_KEY بالسيرفر
app.secret_key = _secret_key()
app.config["MAX_CONTENT_LENGTH"] = 6 * 1024 * 1024
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_SECURE=os.environ.get("APP_URL", "").startswith("https"))
if os.environ.get("K_SERVICE") or os.environ.get("BEHIND_PROXY"):   # Cloud Run / خلف بروكسي: بنثق بترويسات https والعنوان
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
# الصور (قطع/شيكات/مرتجعات/شعار) بتتخزن بجدول files بقاعدة Neon (مش بمجلد)، فبتضل موجودة على أي سيرفر.
_MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".pdf": "application/pdf"}

def put_file(name, data):
    ex("insert into files(name,mime,data,created) values(?,?,?,?)", (name, _MIME.get(os.path.splitext(name)[1].lower(), "application/octet-stream"), data, datetime.date.today().isoformat()))

def del_file(name):
    if name: ex("delete from files where name=?", (name,))

def send_from_directory(d, name, **kw):
    r = q("select mime,data from files where name=?", (name,))
    if not r: abort(404)
    resp = Response(bytes(r[0]["data"]), mimetype=r[0]["mime"] or "application/octet-stream")
    resp.headers["Cache-Control"] = "private, max-age=86400"   # أسماء الملفات UUID ما بتتغير
    return resp
UP = None   # (قديم) ما عاد في مجلد uploads
CATS = ["بطارية", "شاشة", "قاعدة شحن", "آيسي", "كونكتر", "سماعات", "ظهر", "أخرى"]
KC = {"بطارية": 0, "شاشة": 1, "قاعدة شحن": 2, "آيسي": 3, "كونكتر": 2, "سماعات": 4, "أخرى": 5, "ظهر": 3}
TRIAL_DAYS = 7
ST = ["قيد الصيانة", "جاهز", "تم التسليم"]
BRAND = "REPAIRIX"
RESET_MIN = 60  # صلاحية رابط استعادة كلمة السر بالدقائق
# حساب مالك البرنامج (لوحة المالك). كلمة السر محفوظة كهاش فقط. غيّرها من لوحة المالك > أو عبر "نسيت كلمة السر".
pgdb._load_dotenv()   # يقرأ .env (لو موجود) قبل ما نقرأ OWNER_PASSWORD
OWNER_EMAIL = os.environ.get("OWNER_EMAIL", "diaajdeea@gmail.com").strip().lower()
OWNER_PASSWORD = os.environ.get("OWNER_PASSWORD")   # كلمة سر المالك الأولية (متغير بيئة). إذا ما انحطت بتتولّد عشوائية وبتنطبع مرة وحدة بالكونسول
ONLINE_MIN = 5  # المستخدم يعتبر متصل إذا نشاطه خلال هالمدة (دقائق)

# تصنيف القطع حسب نوع/ماركة الجهاز (بيتحدد تلقائياً من اسم القطعة)
BRANDS = [("iPhone", r"iphone|ايفون|آيفون|airpods|ايربودز|apple|ابل|أبل"),
          ("Xiaomi", r"xiaomi|redmi|poco|شاومي|ريدمي|بوكو"),
          ("Huawei", r"huawei|honor|هواوي|هونر"),
          ("Oppo", r"oppo|realme|oneplus|اوبو|أوبو|ريلمي|ون بلس"),
          ("Vivo", r"vivo|فيفو"),
          ("Infinix / Tecno", r"infinix|tecno|itel|انفينكس|تكنو"),
          ("Samsung", r"samsung|galaxy|سامسونج|سامسونغ|جالكسي|\b[as]\d{2}\b")]
BRAND_ORDER = {b: i for i, (b, _) in enumerate(BRANDS)}; BRAND_ORDER["أخرى"] = 99
CAT_PLURAL = {"بطارية": "البطاريات", "شاشة": "الشاشات", "قاعدة شحن": "قواعد الشحن", "آيسي": "الآيسيات", "كونكتر": "الكونكترات", "سماعات": "السماعات", "ظهر": "الظهور", "أخرى": "أخرى"}

def brand_of(name):
    n = (name or "").lower()
    for b, pat in BRANDS:
        if re.search(pat, n): return b
    return "أخرى"

def phone_kind(name):
    b = brand_of(name)
    return "ip" if b == "iPhone" else "sm" if b == "Samsung" else "an"
LOCKUP = ('<div class=lk><svg viewBox="0 0 40 40" width=40 height=40 aria-hidden=true><defs><linearGradient id=lgg x1=0 y1=0 x2=1 y2=1><stop offset=0 stop-color="#6d5efc" /><stop offset=1 stop-color="#22d3ee" /></linearGradient></defs><rect x=6 y=6 width=28 height=28 rx=7 fill="url(#lgg)" />'
  '<path d="M15 28V12h6.5a4.5 4.5 0 010 9H15m6 0l5 7" fill=none stroke="#ffffff" stroke-width=3 stroke-linecap=round stroke-linejoin=round />'
  '<path d="M13 3v3M20 3v3M27 3v3M13 34v3M20 34v3M27 34v3M3 13h3M3 20h3M3 27h3M34 13h3M34 20h3M34 27h3" stroke="#8d9be0" stroke-width=2 stroke-linecap=round /></svg>'
  '<div><div class=wm>REPAIRIX</div><div class=tg>REPAIR &amp; INVENTORY MANAGEMENT</div></div></div>')

def _ic(p): return Markup('<svg viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2 stroke-linecap=round stroke-linejoin=round aria-hidden=true><path d="%s"/></svg>' % p)
ICONS = {"pr": _ic("M6 9V2h12v7M6 18H4a2 2 0 01-2-2v-5a2 2 0 012-2h16a2 2 0 012 2v5a2 2 0 01-2 2h-2M6 14h12v8H6z"),
         "ed": _ic("M12 20h9M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4z"),
         "dl": _ic("M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6M10 11v6M14 11v6"),
         "im": _ic("M3 5h18v14H3zM3 16l5-5 4 4 3-3 6 6M8.5 9.5h.01"),
         "sr": _ic("M21 21l-4.35-4.35M11 18a7 7 0 100-14 7 7 0 000 14z"),
         "ph": _ic("M7 2h10a2 2 0 012 2v16a2 2 0 01-2 2H7a2 2 0 01-2-2V4a2 2 0 012-2zM12 18h.01"),
         "ct": _ic("M9 21a1 1 0 100-2 1 1 0 000 2zM20 21a1 1 0 100-2 1 1 0 000 2zM1 1h4l2.7 13.4a2 2 0 002 1.6h9.7a2 2 0 002-1.6L23 6H6"),
         "cp": _ic("M3 4h18v18H3zM16 2v4M8 2v4M3 10h18M12 14v4M10 16h4"),
         "cd": _ic("M3 4h18v18H3zM16 2v4M8 2v4M3 10h18"),
         "lk": _ic("M5 11h14v10H5zM8 11V7a4 4 0 018 0v4"),
         "ul": _ic("M5 11h14v10H5zM8 11V7a4 4 0 017.5-2"),
         "sh": _ic("M12 2l8 4v6c0 5-3.5 8.5-8 10-4.5-1.5-8-5-8-10V6zM9 12l2 2 4-4")}
CIC = {"بطارية": _ic("M3 8h14a2 2 0 012 2v4a2 2 0 01-2 2H3a2 2 0 01-2-2v-4a2 2 0 012-2zM23 11v2"),
       "شاشة": _ic("M7 2h10a2 2 0 012 2v16a2 2 0 01-2 2H7a2 2 0 01-2-2V4a2 2 0 012-2zM12 18h.01"),
       "قاعدة شحن": _ic("M13 2L3 14h9l-1 8 10-12h-9z"),
       "آيسي": _ic("M6 6h12v12H6zM9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4"),
       "كونكتر": _ic("M9 2v6M15 2v6M7 8h10v5a5 5 0 01-10 0zM12 18v4"),
       "سماعات": _ic("M3 18v-6a9 9 0 0118 0v6M21 19a2 2 0 01-2 2h-1a2 2 0 01-2-2v-3a2 2 0 012-2h3zM3 19a2 2 0 002 2h1a2 2 0 002-2v-3a2 2 0 00-2-2H3z"),
       "ظهر": _ic("M6 2h12a2 2 0 012 2v16a2 2 0 01-2 2H6a2 2 0 01-2-2V4a2 2 0 012-2zM8 6h5v5H8z"),
       "أخرى": _ic("M21 8l-9-5-9 5v8l9 5 9-5zM3 8l9 5 9-5M12 13v8")}

def db():
    if "db" not in g:
        g.db = pgdb.connect()
    return g.db

@app.teardown_appcontext
def close(_):
    d = g.pop("db", None)
    if d: d.close()

def q(sql, a=()): return db().execute(sql, a).fetchall()
def ex(sql, a=()):
    db().execute(sql, a); db().commit()

def init():
    """بينشئ الجداول بـ Neon إذا مش موجودة (schema.sql)."""
    pgdb.init_schema()

DEFAULT_OWNER_PASSWORD = "Repairix@2026"   # كلمة سر المالك الافتراضية (غيّرها من إعدادات البرنامج بعد أول دخول)

def ensure_owner():
    """بينشئ حساب المالك إذا مش موجود. كلمة السر: OWNER_PASSWORD (بتنفرض عند كل تشغيل) وإلا الافتراضية."""
    with pgdb.connect() as c:
        row = c.execute("select pw, last_login from users where lower(email)=?", (OWNER_EMAIL,)).fetchone()
        if not row:
            c.execute("insert into users(email,pw,created,blocked) values(?,?,?,0)", (OWNER_EMAIL, generate_password_hash(OWNER_PASSWORD or DEFAULT_OWNER_PASSWORD), datetime.date.today().isoformat()))
        elif OWNER_PASSWORD:
            if not check_password_hash(row["pw"], OWNER_PASSWORD):
                c.execute("update users set pw=?, blocked=0 where lower(email)=?", (generate_password_hash(OWNER_PASSWORD), OWNER_EMAIL))
        elif not row["last_login"] and not check_password_hash(row["pw"], DEFAULT_OWNER_PASSWORD):
            # حساب مالك أنشئ سابقاً بكلمة عشوائية ولا أحد دخل فيه: منرجعه للافتراضية
            c.execute("update users set pw=? where lower(email)=?", (generate_password_hash(DEFAULT_OWNER_PASSWORD), OWNER_EMAIL))

def start():
    """تجهيز كامل: الجداول بـ Neon + حساب المالك."""
    init()
    ensure_owner()

T = {"base": """<!doctype html><html lang=ar dir=rtl><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>REPAIRIX | Repair &amp; Inventory Management</title>
<link rel=preconnect href="https://fonts.googleapis.com"><link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&display=swap" rel=stylesheet>
<style>:root{--navy:#0c1233;--navy2:#151d4d;--br:#4f46e5;--br2:#6d5efc;--cy:#22d3ee;--paper:#f3f5fb;--ink:#0f172a;--mut:#64748b;--line:#e4e8f1;--red:#e11d48;--ok:#059669;--sh:0 1px 2px #0f172a0a,0 10px 28px -14px #0f172a30}
*{box-sizing:border-box}body{margin:0;font-family:system-ui,-apple-system,"Segoe UI",Tahoma,Arial,sans-serif;background:var(--paper);color:var(--ink);line-height:1.6;-webkit-font-smoothing:antialiased}
h1,h2,h3{margin:0;font-weight:700}h3{font-size:17px;margin-bottom:14px}a{color:var(--br);text-decoration:none}a:hover{text-decoration:underline}
.lk{display:flex;align-items:center;gap:11px;direction:ltr}.wm{font:800 21px/1.1 system-ui,sans-serif;letter-spacing:.06em;color:var(--wm,#fff)}
.tg{font:600 7.4px/1.4 system-ui,sans-serif;letter-spacing:.1em;white-space:nowrap;color:var(--tgc,#8d9be0);margin-top:3px}
.app{display:flex;min-height:100vh}aside{width:262px;background:linear-gradient(180deg,var(--navy),#111a46);padding:22px 14px;position:sticky;top:0;height:100vh;overflow-y:auto;flex-shrink:0}
aside .lk{padding:0 8px 22px;margin-bottom:12px;border-bottom:1px solid #ffffff1a}
aside a{display:flex;align-items:center;gap:12px;color:#aab4e0;padding:10px 13px;margin-bottom:3px;border-radius:11px;font-size:14.5px;transition:.15s}
aside a:hover{background:#ffffff12;color:#fff;text-decoration:none}aside a.on{background:linear-gradient(90deg,#4f46e5,#6d5efc);color:#fff;box-shadow:0 10px 20px -10px #6d5efc}
aside .out{margin-top:18px;color:#8e9ad0;border-top:1px solid #ffffff1a;border-radius:0;padding-top:16px}
main{flex:1;padding:30px 34px;max-width:1260px;min-width:0}.bare main{max-width:none;padding:0}
.ph{margin-bottom:20px}.ph h2{font-size:26px}.ph p{margin:3px 0 0;color:var(--mut)}
.card{background:#fff;border:1px solid var(--line);border-radius:16px;padding:20px;margin-bottom:18px;overflow-x:auto;box-shadow:var(--sh)}
table{width:100%;border-collapse:collapse}th{font-weight:600;color:var(--mut);font-size:12.5px;background:#f6f8fd;white-space:nowrap}td,th{padding:12px 10px;border-bottom:1px solid var(--line);text-align:right}
th:first-child{border-radius:0 10px 10px 0}th:last-child{border-radius:10px 0 0 10px}tbody tr:hover td,tr:hover>td{background:#fafbff}tr:last-child td{border:0}td a{font-weight:600;margin-left:10px}small{color:var(--mut)}
input,select{font:inherit;padding:9px 12px;margin:3px;border:1px solid #d3d9e8;border-radius:10px;background:#fff;color:var(--ink);transition:.15s}
button,.btn{font:inherit;font-weight:600;padding:10px 20px;margin:3px;border:0;border-radius:10px;background:linear-gradient(135deg,var(--br),var(--br2));color:#fff!important;cursor:pointer;text-decoration:none!important;display:inline-flex;align-items:center;gap:8px;box-shadow:0 10px 20px -12px var(--br);transition:.15s}
button:hover,.btn:hover{transform:translateY(-1px);filter:brightness(1.08)}.ghost{background:#eef1fa!important;color:var(--ink)!important;box-shadow:none}
input:focus,select:focus{outline:0;border-color:var(--br);box-shadow:0 0 0 3px #4f46e522}button:focus-visible,a:focus-visible{outline:2px solid var(--br);outline-offset:2px}
.fg{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:14px}.fg label{font-size:13px;font-weight:600;color:var(--mut)}.fg input,.fg select{display:block;width:100%;margin:5px 0 0;color:var(--ink);font-weight:400}.fa{grid-column:1/-1}
.th{width:46px;height:46px;border-radius:11px;object-fit:cover;background:#e9edf6;display:block}.il{display:inline-flex;align-items:center;margin:0}.nw{white-space:nowrap}.ac{display:flex;align-items:center;gap:10px;white-space:nowrap}.ac button{padding:7px 12px;font-size:13px;margin:0 4px}.ac a{margin:0}.sm{width:62px;padding:7px 8px}.up{cursor:pointer;color:var(--br);font-weight:600;margin-left:8px}
.tag{display:inline-block;padding:1px 12px;border-radius:99px;background:#e7f8ef;color:var(--ok);font-size:13px;font-weight:700}.tag.bad{background:#fff1f3;color:var(--red)}
.pill{display:inline-block;padding:2px 12px;border-radius:99px;font-size:12.5px;font-weight:700}.pill.s0{background:#fff4dc;color:#b45309}.pill.s1{background:#e0f7fb;color:#0e7490}.pill.s2{background:#e7f8ef;color:#047857}
.low{color:var(--red);font-weight:600}.big{font-size:30px;color:var(--ok);font-weight:800}.new{background:#fff8e6}.bd{background:var(--red);color:#fff;border-radius:10px;padding:0 7px;font-size:12px}
.tools{display:flex;flex-direction:column;gap:10px;background:#fff;border:1px solid var(--line);border-radius:16px;padding:12px;box-shadow:var(--sh);margin-bottom:18px}
.tools .r1,.tools .r2{display:flex;gap:10px;align-items:center}.tools .r2{flex-wrap:wrap}.tools .sp{flex:1}.tools form{display:flex;gap:8px;align-items:center;margin:0}
.tools input,.tools select,.tools button,.tools .btn{margin:0}.tools input[data-role=search],#bsearch{flex:1;min-width:0}.tools select{min-width:150px}.tools input[type=date]{width:155px}
.tools>.r1>button,.tools .btn{white-space:nowrap}.dr{display:inline-flex;align-items:center;gap:8px}.tools .lb{font-size:13px;color:var(--mut)}.tools .vt{margin:0}
.hero3{display:grid;gap:14px;margin-bottom:18px;grid-template-columns:repeat(3,1fr)}.st{background:#fff;border:1px solid var(--line);border-radius:16px;padding:16px 18px;color:var(--mut);box-shadow:var(--sh)}.st b{display:block;font-size:27px;line-height:1.3;color:var(--ink)}
.hb{background:linear-gradient(120deg,#0c1233 0%,#262d8a 55%,#4f46e5 100%);color:#fff;border-radius:22px;padding:30px;display:flex;justify-content:space-between;align-items:center;gap:22px;flex-wrap:wrap;position:relative;overflow:hidden;margin-bottom:18px;box-shadow:0 24px 40px -24px #4f46e5}
.hb:before{content:'';position:absolute;inset:0;background:radial-gradient(circle at 12% 130%,#22d3ee66,transparent 45%),radial-gradient(circle at 92% -30%,#a78bfa77,transparent 42%)}.hb>*{position:relative}
.hb h2{font-size:27px}.hb p{margin:4px 0 0;color:#c4cbf3}.hb .bt{display:flex;gap:10px;margin-top:18px;flex-wrap:wrap}.hb .btn{background:#fff;color:var(--navy)!important;box-shadow:none;margin:0}.hb .btn.o{background:#ffffff1f;color:#fff!important;border:1px solid #ffffff4d}
.mos{display:flex;gap:14px}.mo{background:#ffffff17;border:1px solid #ffffff2b;border-radius:16px;padding:14px 22px;min-width:150px;backdrop-filter:blur(4px)}.mo small{color:#c4cbf3;display:block}.mo b{font-size:30px;line-height:1.3;display:block;font-weight:800}.mo b.cy{color:#67e8f9}
.sg4{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:14px;margin-bottom:18px}.sc{background:#fff;border:1px solid var(--line);border-radius:16px;padding:16px;display:flex;gap:14px;align-items:center;box-shadow:var(--sh)}
.si{width:44px;height:44px;border-radius:14px;display:grid;place-items:center;flex-shrink:0}.si.a{background:#eef0ff;color:var(--br)}.si.b{background:#e0f7fb;color:#0891b2}.si.c{background:#e7f8ef;color:var(--ok)}.si.d{background:#fff1f3;color:var(--red)}.si.e{background:#fff6e0;color:#d97706}
.sc small{display:block;line-height:1.4}.sc>div{min-width:0}.sc b{font-size:clamp(19px,2vw,26px);line-height:1.2;display:block;white-space:nowrap}
.sg3{grid-template-columns:repeat(3,1fr)}.ib{display:inline-grid;place-items:center;width:34px;height:34px;border-radius:10px;background:#f1f4fb;color:#55607f;margin:0 3px;transition:.15s}.ib:hover{background:var(--br);color:#fff;text-decoration:none}.ib.dl:hover{background:var(--red)}.ib svg{width:17px;height:17px}
th.sb{cursor:pointer;user-select:none}th.sb:hover{color:var(--ink)}th.sb:after{content:'↕';opacity:.35;margin-right:6px;font-size:11px}th[data-d=a]:after{content:'▲';opacity:1;color:var(--br)}th[data-d=d]:after{content:'▼';opacity:1;color:var(--br)}
.tools select{min-width:130px}.tools input[type=date]{min-width:0}.tools .lb{font-size:13px;color:var(--mut)}.si.f{background:#ecfdf5;color:#059669}.si.g{background:#f3e8ff;color:#9333ea}
.sg2{grid-template-columns:repeat(2,1fr)}
.k0{--c1:#e0f7fb;--c2:#bff3fb;--c3:#0891b2}.k1{--c1:#eef0ff;--c2:#dfe4ff;--c3:#4f46e5}.k2{--c1:#fff6e0;--c2:#fde9a8;--c3:#d97706}.k3{--c1:#f6ecff;--c2:#e9d5ff;--c3:#9333ea}.k4{--c1:#ecfdf5;--c2:#bbf7d0;--c3:#059669}.k5{--c1:#fff1f3;--c2:#fecdd3;--c3:#e11d48}
.pg{display:grid;grid-template-columns:repeat(auto-fill,minmax(255px,1fr));gap:18px;margin-bottom:18px}
.pc{background:#fff;border:1px solid var(--line);border-radius:20px;overflow:hidden;box-shadow:var(--sh);display:flex;flex-direction:column;transition:.2s}.pc:hover{transform:translateY(-3px);box-shadow:0 24px 44px -24px #0f172a66}
.pm{height:140px;position:relative;display:grid;place-items:center;background:linear-gradient(135deg,var(--c1),var(--c2));color:var(--c3)}.pm img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}.pm>svg{width:52px;height:52px;opacity:.8}
.cb{position:absolute;top:12px;right:12px;background:#ffffffe0;backdrop-filter:blur(6px);padding:2px 12px;border-radius:99px;font-size:12px;font-weight:700}.ss{position:absolute;top:12px;left:12px}.pill.s3{background:#ffe4e8;color:#be123c}
.pb{padding:16px;display:flex;flex-direction:column;gap:13px;flex:1}.pn{font-weight:700;font-size:16px;line-height:1.4;display:flex;align-items:center;gap:8px}.ps{font-size:12.5px;color:var(--mut);margin-top:-8px}
.dot{width:13px;height:13px;border-radius:50%;display:inline-block;border:1px solid #0003;flex-shrink:0}
.pr3{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.pr3>div{background:#f6f8fd;border-radius:12px;padding:8px 4px;text-align:center}.pr3 small{display:block;font-size:11px}.pr3 b{font-size:14px;white-space:nowrap}.pr3 .g b{color:var(--ok)}
.qb{display:flex;justify-content:space-between;font-size:13px;margin-bottom:6px}.qt{height:8px;background:#eef1fa;border-radius:99px;overflow:hidden}.qt i{display:block;height:100%;border-radius:99px;background:linear-gradient(90deg,#34d399,#059669)}.qt i.w{background:linear-gradient(90deg,#fbbf24,#f59e0b)}.qt i.r{background:linear-gradient(90deg,#fb7185,#e11d48)}
.pf{display:flex;align-items:center;gap:4px;padding:12px 14px;border-top:1px solid var(--line);background:#fafbff}.pf form{margin:0;display:flex;align-items:center;gap:6px;flex:1}.pf .sm{width:60px;margin:0}.pf button{padding:8px 14px;font-size:13px;margin:0}
.vt{display:inline-flex;background:#e9edf7;border-radius:12px;padding:3px}.vt button{background:none;color:var(--mut)!important;box-shadow:none;margin:0;padding:7px 11px}.vt button.on{background:#fff;color:var(--br)!important;box-shadow:0 2px 8px #0f172a22}.vt svg{width:18px;height:18px}
#pwrap[data-v=g] .tv{display:none}#pwrap[data-v=t] .gv{display:none}
.bg{display:grid;grid-template-columns:repeat(auto-fill,minmax(430px,1fr));gap:20px;margin-bottom:18px}
.mc{--bk:#888;background:radial-gradient(120% 90% at 15% 0%,color-mix(in srgb,var(--bk) 30%,#fff),#fff 62%);border:1px solid var(--line);border-radius:26px;padding:22px;display:grid;grid-template-columns:140px 1fr;gap:20px;box-shadow:var(--sh)}
.mp{display:grid;place-items:center}.mp svg{width:124px;height:auto;filter:drop-shadow(0 20px 18px #0c123340)}.bd2{fill:var(--bk);transition:fill .3s}
.mh{display:flex;justify-content:space-between;align-items:flex-start;gap:8px}.mh h3{margin:0;font-size:19px}.mh small{display:block}
.sws{display:flex;gap:12px;margin:16px 0 14px;flex-wrap:wrap}.swb{position:relative;width:40px;height:40px;padding:0;margin:0;border-radius:50%;border:3px solid #fff;background:var(--h);box-shadow:0 0 0 1px #c3cbe0,0 8px 12px -8px #0008;cursor:pointer}.swb.on{box-shadow:0 0 0 3px var(--br),0 10px 14px -8px #0009;transform:scale(1.1)}
.swb em{position:absolute;top:-8px;left:-8px;min-width:20px;height:20px;border-radius:99px;background:var(--ink);color:#fff;font:700 11px/20px system-ui;text-align:center;font-style:normal;padding:0 5px}.swb em.z{background:var(--red)}
.cp{background:#ffffffc4;border:1px solid var(--line);border-radius:16px;padding:12px 14px;backdrop-filter:blur(6px)}.cp .top{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;font-weight:700}
.cp .pf{background:none;border:0;padding:10px 0 0}
.cr{display:grid;grid-template-columns:52px 1fr 100px;gap:8px;align-items:center;margin-top:8px}.cr input{margin:0;width:100%}.cr input[type=color]{height:42px;padding:2px;border-radius:10px;cursor:pointer}
.tb7{display:flex;align-items:center;gap:18px;background:#fff;border:1px solid var(--line);border-right:5px solid #f59e0b;border-radius:18px;padding:16px 20px;margin-bottom:18px;box-shadow:var(--sh);flex-wrap:wrap}.tb7.end{border-right-color:var(--red)}.tb7 h3{margin:0;font-size:16px}.tb7 p{margin:2px 0 0;color:var(--mut);font-size:13.5px}.tb7 .sp{flex:1}.tb7 form{margin:0}
.ring{--p:0;width:62px;height:62px;border-radius:50%;background:conic-gradient(#f59e0b calc(var(--p)*1%),#eef1fa 0);display:grid;place-items:center;flex-shrink:0}.ring b{width:48px;height:48px;border-radius:50%;background:#fff;display:grid;place-items:center;font-size:19px}
.tbd{display:inline-block;background:#fff4dc;color:#b45309;border-radius:99px;font-size:12px;font-weight:700;padding:2px 10px;margin-right:6px}.trs{margin:14px 4px 0;padding:10px 12px;border-radius:12px;background:#ffffff12;border:1px dashed #ffffff44;color:#fde68a;font-size:13px;text-align:center}
.g2{display:grid;grid-template-columns:1.6fr 1fr;gap:18px;margin-bottom:18px}.g2>.card{margin:0}.ch{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}.ch h3{margin:0}
.bar{display:flex;align-items:center;gap:12px;margin:10px 0}.bar span{width:84px;color:var(--mut);font-size:13px;flex-shrink:0}.bar .tr{flex:1;background:#eef1fa;border-radius:99px;height:12px}.bar i{display:block;height:12px;background:linear-gradient(90deg,var(--br),var(--cy));border-radius:99px}.bar b{width:84px;text-align:left;font-size:13px}
.lw{display:flex;justify-content:space-between;align-items:center;padding:11px 0;border-bottom:1px solid var(--line)}.lw:last-child{border:0}.em{color:var(--mut);padding:18px 0;text-align:center}
.more{margin-top:14px;border:1px dashed #cdd5e8;border-radius:12px;padding:10px 14px}.more summary{cursor:pointer;font-weight:600;color:var(--br)}.more .fg{margin-top:12px}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px}.chips label{display:flex;align-items:center;gap:6px;border:1px solid #d3d9e8;border-radius:99px;padding:5px 13px;cursor:pointer;font-size:13.5px;color:var(--ink);font-weight:400}.chips label:has(input:checked){background:#eef0ff;border-color:var(--br);color:var(--br)}.chips input{margin:0}
dialog.dlg{border:0;padding:0;border-radius:22px;width:min(600px,94vw);max-height:92vh;box-shadow:0 40px 90px -24px #0c1233aa;color:var(--ink);overflow:hidden;background:#fff}
dialog.dlg[open]{animation:pop .24s cubic-bezier(.2,.9,.3,1.2)}dialog.dlg::backdrop{background:#0c123399;backdrop-filter:blur(3px)}
dialog.dlg form{margin:0;display:flex;flex-direction:column;max-height:92vh}.dh{display:flex;align-items:center;justify-content:space-between;padding:18px 22px;background:linear-gradient(135deg,var(--navy),#2a3190);color:#fff}.dh h3{margin:0;font-size:18px}
.cl{background:#ffffff22!important;box-shadow:none;width:34px;height:34px;padding:0;justify-content:center;font-size:20px;line-height:1;border-radius:50%;margin:0}.db{padding:22px;overflow-y:auto}.df{display:flex;gap:8px;padding:14px 22px;background:#f6f8fd;border-top:1px solid var(--line)}
@keyframes pop{from{opacity:0;transform:translateY(16px) scale(.97)}}
#tc{position:fixed;top:14px;left:50%;transform:translateX(-50%);z-index:999;display:grid;gap:12px;justify-items:center;width:min(330px,90vw);pointer-events:none}
.toast{pointer-events:auto;display:flex;align-items:center;gap:10px;width:100%;background:#ffffffef;backdrop-filter:blur(16px);border:1px solid #e4e8f1;border-radius:14px;padding:9px 11px;box-shadow:0 18px 40px -16px #0c123360,0 3px 10px -5px #0c123322;position:relative;overflow:hidden;animation:tin .5s cubic-bezier(.2,.9,.3,1.25),tout .4s 4.6s forwards}
.toast:after{content:'';position:absolute;bottom:0;right:0;height:3px;width:100%;background:linear-gradient(90deg,#34d399,#059669);transform-origin:right;animation:tbar 4.6s linear forwards}
.ti{width:32px;height:32px;border-radius:10px;display:grid;place-items:center;background:linear-gradient(135deg,#34d399,#059669);color:#fff;flex-shrink:0;box-shadow:0 10px 18px -8px #059669}
.tb{flex:1;min-width:0}.tb b{display:block;font-size:13.5px;line-height:1.35}.tb span{color:var(--mut);font-size:12px;line-height:1.35}
.toast.warn .ti{background:linear-gradient(135deg,#fb7185,#e11d48);box-shadow:0 10px 18px -8px #e11d48}.toast.warn:after{background:linear-gradient(90deg,#fb7185,#e11d48)}
.toast.info .ti{background:linear-gradient(135deg,#818cf8,#4f46e5);box-shadow:0 10px 18px -8px #4f46e5}.toast.info:after{background:linear-gradient(90deg,#818cf8,#4f46e5)}
.toast .x{background:#eef1fa;color:var(--mut)!important;font-size:16px;width:24px;height:24px;padding:0;margin:0;line-height:1;box-shadow:none;border-radius:50%;justify-content:center}
@keyframes tin{from{opacity:0;transform:translateY(-26px) scale(.94)}to{opacity:1;transform:none}}@keyframes tout{to{opacity:0;visibility:hidden;transform:translateY(-14px) scale(.97)}}@keyframes tbar{to{transform:scaleX(0)}}
@media(prefers-reduced-motion:reduce){.toast,.toast:after,dialog.dlg[open]{animation:tout .01s 5s forwards}dialog.dlg[open]{animation:none}}
.auth{display:flex;min-height:100vh}.form{flex:1;display:flex;align-items:center;justify-content:center;padding:24px;background:#fff;--wm:var(--navy);--tgc:#6b7799}.fw{width:100%;max-width:350px}
.fw h1{margin:28px 0 4px;font-size:25px}.sub{color:var(--mut);margin:0 0 8px}.fw label{display:block;font-weight:600;margin-top:14px}.fw input{display:block;width:100%;margin:6px 0 0;padding:12px}
.wide{width:100%;margin:22px 0 0;padding:13px;justify-content:center}.sw{margin-top:18px;color:var(--mut)}.sw a{font-weight:700}.err{background:#fff1f3;color:var(--red);padding:9px 12px;border-radius:10px;margin:10px 0}
.art{flex:1.1;background:linear-gradient(140deg,#0c1233,#262d8a 60%,#4f46e5);color:#fff;position:relative;display:flex;align-items:flex-end;padding:48px;overflow:hidden}.art svg{position:absolute;inset:0;width:100%;height:100%}
.tx{position:relative;max-width:480px}.tx h2{font-size:32px;line-height:1.35;margin:0 0 10px}.tx p{color:#c4cbf3;margin:0}
@media(max-width:860px){.tools .r1{flex-wrap:wrap}.tools .r1 input[data-role=search],#bsearch{flex:1 1 100%}.tools input[type=date]{width:140px}.app{display:block}aside{width:auto;height:auto;position:static;display:flex;overflow-x:auto;padding:8px}aside .lk{display:none}aside a{white-space:nowrap}aside .out{margin:0;border:0;padding:10px 13px}
main{padding:14px}.sg4{grid-template-columns:1fr 1fr}.sg2{grid-template-columns:1fr}.mc{grid-template-columns:1fr}.bg{grid-template-columns:1fr}.sg3{grid-template-columns:1fr}.g2{grid-template-columns:1fr}.hero3{grid-template-columns:1fr}.mos{width:100%}.mo{flex:1;min-width:0}.auth{flex-direction:column-reverse}.art{padding:28px;min-height:190px}.tx h2{font-size:24px}.tools input{min-width:0;flex:1}}
/* ===== v2: toolbar + forms polish ===== */
[hidden]{display:none!important}
select{appearance:none;-webkit-appearance:none;background:#fff url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8'%3E%3Cpath d='M1 1.5l5 5 5-5' fill='none' stroke='%2364748b' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E") no-repeat left 13px center/12px 8px;padding:9px 14px 9px 36px;cursor:pointer}
.tools{flex-direction:column;align-items:stretch;gap:10px;padding:14px 16px;border-radius:18px}
.tools .r1,.tools .r2{display:flex;align-items:center;gap:10px}.tools .r2{flex-wrap:wrap}.tools .r1{flex-wrap:wrap}.tools .r1 .search{margin-inline-end:auto}
.tools input,.tools select,.tools button,.tools .btn{height:42px;margin:0}
.tools button,.tools .btn{padding:0 20px}
.tools select{width:auto;min-width:0;max-width:200px;padding-top:0;padding-bottom:0}
.tools .sp{flex:1 1 0;min-width:0}
.search{position:relative;flex:1 1 240px;max-width:340px;min-width:190px;display:block;margin:0}
.search svg{position:absolute;inset-inline-start:14px;top:50%;margin-top:-9px;width:18px;height:18px;color:#8a95b3;pointer-events:none}
.search input{display:block;width:100%;margin:0;padding:0 42px 0 14px;background:#f8f9fd;border-color:#e1e6f2}.search input:focus{background:#fff}
.vt{height:42px;align-items:center}.vt button{height:36px;padding:0 11px}
.cats{display:flex;flex-wrap:wrap;gap:8px;padding:2px 0 14px}
.cpill{background:#fff;color:var(--ink)!important;border:1px solid var(--line);box-shadow:none;margin:0;padding:7px 12px;border-radius:99px;font-weight:600;font-size:13.5px;white-space:nowrap;gap:7px}
.cpill:hover{transform:none;filter:none;border-color:var(--br)}.cpill svg{width:16px;height:16px}
.cpill em{font-style:normal;background:#eef1fa;color:var(--mut);border-radius:99px;padding:0 8px;font-size:12px;line-height:20px}
.cpill.on{background:var(--navy);color:#fff!important;border-color:var(--navy)}.cpill.on em{background:#ffffff26;color:#fff}
.grp{margin-bottom:28px}.gh{display:flex;align-items:center;gap:12px;margin:2px 2px 14px}.gh h3{margin:0;font-size:18px}.gh:after{content:'';flex:1;height:1px;background:var(--line)}
.gi{width:38px;height:38px;border-radius:12px;display:grid;place-items:center;background:var(--c1);color:var(--c3)}.gi svg{width:20px;height:20px}.gc{color:var(--mut);font-size:13px}.grp .pg{margin-bottom:0}
.cg{margin-top:12px}.cgl{font-weight:700;display:block}
/* auth */
.lrow{display:flex;justify-content:space-between;align-items:center;margin-top:14px}.lrow label{margin:0!important}.fgt{font-size:13px;font-weight:600}
.pw{position:relative;margin-top:6px}.pw input{margin:0!important;padding-right:46px!important}
.eye{position:absolute;right:5px;left:auto;top:50%;margin:-17px 0 0!important;width:34px;height:34px;padding:0;background:none!important;box-shadow:none!important;color:var(--mut)!important;justify-content:center}.eye svg{width:19px;height:19px}
.tbx{display:flex;gap:14px;align-items:center;background:linear-gradient(135deg,#eef0ff,#e6f9fd);border:1px solid #d9defa;border-radius:16px;padding:14px 16px;margin:22px 0 2px}
.tbx .n{width:54px;height:54px;border-radius:16px;background:linear-gradient(135deg,var(--br),var(--br2));color:#fff;display:grid;place-items:center;font:800 26px/1 system-ui;flex-shrink:0;box-shadow:0 12px 22px -12px var(--br)}
.tbx b{display:block;font-size:16px}.tbx small{display:block;line-height:1.5}
.chk{list-style:none;margin:12px 2px 0;padding:0;display:grid;gap:7px;font-size:13.5px;color:var(--mut)}.chk li{display:flex;align-items:center;gap:8px}.chk svg{width:16px;height:16px;color:var(--ok);flex-shrink:0}
.okb{background:#ecfdf5;border:1px solid #a7f3d0;color:#065f46;padding:12px 14px;border-radius:12px;margin:14px 0;line-height:1.8}
.bk{display:inline-block;margin-top:18px;font-weight:700}
.art:after{content:'';position:absolute;inset:auto 0 0 0;height:62%;background:linear-gradient(0deg,#0c1233f0 15%,#0c123300)}.art .tx{z-index:1}
.art .pts{list-style:none;margin:18px 0 0;padding:0;display:grid;gap:10px;color:#dfe4ff}.art .pts li{display:flex;gap:10px;align-items:center}.art .pts svg{position:static;width:18px;height:18px;flex-shrink:0;stroke:#67e8f9;opacity:1}
/* backs page */
.bg{grid-template-columns:repeat(auto-fill,minmax(480px,1fr));gap:22px}
.mc{grid-template-columns:190px 1fr;gap:22px;padding:24px;border-radius:28px;position:relative}
.mp{position:relative;padding-bottom:16px;align-content:start}.mp svg{width:178px;filter:drop-shadow(0 30px 22px #0c123345) drop-shadow(0 3px 5px #0c123333)}
.mp:after{content:'';position:absolute;bottom:0;left:50%;width:130px;height:16px;margin-left:-65px;background:radial-gradient(#0c123338,transparent 70%)}
.fr{fill:color-mix(in srgb,var(--bk) 55%,#a1a7b5);transition:fill .3s}.bd2{fill:var(--bk);transition:fill .3s}.pl{fill:color-mix(in srgb,var(--bk) 88%,#fff);transition:fill .3s}
.bb{display:inline-flex;align-items:center;gap:6px;background:#ffffffb8;border:1px solid var(--line);border-radius:99px;padding:1px 11px;font-size:12px;font-weight:700;color:var(--mut);margin-top:6px}
.sws{margin:18px 0 16px}.swb{width:42px;height:42px}
@media(max-width:860px){.search{flex:1 1 100%;max-width:none}.tools select{flex:1 1 44%;max-width:none}.tools .sp{display:none}.bg{grid-template-columns:1fr}.mc{grid-template-columns:1fr;justify-items:stretch}.mp svg{width:150px}}

/* ===== v3: icon buttons (search / export) ===== */
.tools .ib2{width:42px;min-width:42px;padding:0;justify-content:center;border-radius:12px}.tools .ib2 svg{width:19px;height:19px}
.tools .ib2.xl{background:linear-gradient(135deg,#059669,#10b981);box-shadow:0 10px 20px -12px #059669}
.dr .sep{width:1px;height:26px;background:var(--line);margin:0 4px}
/* ===== v3: backs page ===== */
.bs{display:grid;grid-template-columns:repeat(4,minmax(0,1fr)) 1.6fr;background:linear-gradient(120deg,#0c1233,#1f2788 60%,#4f46e5);border-radius:22px;color:#fff;margin-bottom:18px;position:relative;overflow:hidden;box-shadow:0 24px 40px -26px #4f46e5}
.bs:before{content:'';position:absolute;inset:0;background:radial-gradient(circle at 8% 140%,#22d3ee55,transparent 45%),radial-gradient(circle at 95% -40%,#a78bfa66,transparent 45%)}
.bs>*{position:relative;padding:20px 22px;min-width:0}.bs-i+.bs-i,.bs-h{border-inline-start:1px solid #ffffff1f}
.bs small{color:#b9c2f0;display:block}.bs b{display:block;font-size:clamp(20px,2.2vw,28px);font-weight:800;line-height:1.35;white-space:nowrap}.bs b.cy{color:#67e8f9}
.hbar{display:flex;height:10px;border-radius:99px;overflow:hidden;background:#ffffff26;margin:12px 0 10px;gap:2px}.hbar i{display:block;height:100%;min-width:0}.hbar .a{background:#34d399}.hbar .b{background:#fbbf24}.hbar .c{background:#fb7185}
.hl{display:flex;gap:16px;font-size:12.5px;flex-wrap:wrap}.hl em{font-style:normal;display:inline-flex;align-items:center;gap:6px;color:#d5dbff!important}.hl em:before{content:'';width:8px;height:8px;border-radius:50%;background:currentColor}
.bgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(500px,1fr));gap:22px;margin-bottom:18px}
.bm{--bk:#888;display:grid;grid-template-columns:190px minmax(0,1fr);background:#fff;border:1px solid var(--line);border-radius:26px;overflow:hidden;box-shadow:var(--sh);transition:box-shadow .25s,transform .25s}
.bm:hover{transform:translateY(-3px);box-shadow:0 30px 50px -28px #0f172a66}
.bm-s{position:relative;display:grid;place-items:center;padding:28px 8px 38px;background:radial-gradient(90% 70% at 50% 28%,color-mix(in srgb,var(--bk) 36%,#fff),color-mix(in srgb,var(--bk) 10%,#f4f6fc) 78%);transition:background .35s}
.bm-s:after{content:'';position:absolute;bottom:16px;left:50%;width:110px;height:14px;margin-left:-55px;background:radial-gradient(#0c123338,transparent 70%)}
.bm-s svg{width:140px;height:auto;filter:drop-shadow(0 26px 20px #0c123345) drop-shadow(0 3px 5px #0c123333)}
.bm-b{padding:22px 24px;display:flex;flex-direction:column;gap:14px;min-width:0}
.bm-h{display:flex;justify-content:space-between;align-items:flex-start;gap:10px}.bm-h h3{margin:0 0 6px;font-size:19px;line-height:1.3}.bm-m{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.bm-add{margin:0;background:#eef0ff!important;color:var(--br)!important;flex-shrink:0;box-shadow:none;width:36px;height:36px;padding:0;border-radius:11px;justify-content:center}.bm-add svg{width:18px;height:18px}.bm-add:hover{background:var(--br)!important;color:#fff!important}
.dist{display:flex;height:8px;border-radius:99px;overflow:hidden;gap:2px;background:#eef1fa}.dist i{display:block;height:100%;box-shadow:inset 0 0 0 1px #0000001a}
.bsws{display:flex;gap:12px;flex-wrap:wrap;padding:4px 0}
.bsw{position:relative;width:46px;height:46px;padding:0;margin:0;border-radius:50%;border:3px solid #fff;background:var(--h);box-shadow:0 0 0 1px #c3cbe0,0 8px 12px -8px #0008;cursor:pointer;transition:.18s}
.bsw:hover{transform:scale(1.08)}.bsw.on{box-shadow:0 0 0 3px var(--br),0 10px 14px -8px #0009;transform:scale(1.12)}
.bsw em{position:absolute;inset:0;display:grid;place-items:center;background:none;color:#fff;font:800 16px/1 system-ui;text-shadow:0 1px 3px #000a;font-style:normal;pointer-events:none}.bsw.lt em{color:#111827;text-shadow:0 1px 0 #fff6}.bsw em.z{color:#fff;background:#e11d48;inset:11px;border-radius:50%;font-size:13px;text-shadow:none}
.bp{background:#f8f9fd;border:1px solid var(--line);border-radius:18px;padding:14px}.bp-t{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:12px;font-weight:700}.bp-n{display:inline-flex;align-items:center;gap:8px}
.bp .pr3>div{background:#fff;border:1px solid var(--line)}
.bp-f{display:flex;align-items:center;gap:10px;margin-top:12px;flex-wrap:wrap}.bp-f form{margin:0;display:flex;align-items:center;gap:6px}.bp-f .dl{margin:0 auto 0 0}
.stp{direction:ltr;background:#fff;border:1px solid var(--line);border-radius:12px;padding:3px}.stp .stb{width:32px;height:32px;padding:0;margin:0;justify-content:center;font-size:19px;line-height:1;border-radius:9px;box-shadow:none}
.stp .sq{min-width:38px;text-align:center;font-weight:800;font-size:16px}
.stp2 input{width:64px;margin:0;padding:7px 8px;text-align:center}.stp2 button{padding:8px 14px;font-size:13px;margin:0}
.bempty{display:flex;flex-direction:column;align-items:center;gap:6px;text-align:center;padding:46px 20px;color:var(--mut)}.bempty svg{color:var(--br);opacity:.8;margin-bottom:6px}.bempty b{color:var(--ink);font-size:18px}.bempty button{margin-top:10px}
@media(max-width:860px){.bs{grid-template-columns:1fr 1fr}.bs-i+.bs-i{border-inline-start:0}.bs-h{grid-column:1/-1;border-inline-start:0;border-top:1px solid #ffffff1f}.bgrid{grid-template-columns:1fr}.bm{grid-template-columns:1fr}.bm-s{padding:22px 8px 34px}.bm-s svg{width:128px}}

/* ===== v4: parts search picker ===== */
.psb{margin-top:16px}.pslb{font-weight:700;font-size:14px;margin-bottom:8px}
.psi{max-width:none!important;flex:none!important;display:block}.psi input{height:44px;width:100%}
.psr{margin-top:8px;border:1px solid var(--line);border-radius:14px;background:#fff;max-height:230px;overflow-y:auto;box-shadow:var(--sh)}
.psit{display:flex;justify-content:space-between;align-items:center;gap:10px;width:100%;margin:0;padding:10px 14px;border-radius:0;background:none!important;color:var(--ink)!important;box-shadow:none;font-weight:600;border-bottom:1px solid var(--line);text-align:right}
.psit:last-child{border:0}.psit:hover{background:#eef0ff!important;transform:none;filter:none}.psit em{font-style:normal;font-weight:400;font-size:12.5px;color:var(--mut);white-space:nowrap}
.psn{padding:12px 14px;color:var(--mut);text-align:center}
.pssel{display:flex;flex-direction:column;gap:8px;margin-top:10px}.pkr{display:grid;grid-template-columns:minmax(0,1fr) 84px 84px 26px;gap:8px;align-items:end;background:#eef0ff;border:1px solid var(--br);border-radius:14px;padding:8px 12px}.pkr b{color:var(--br);font-size:13.5px;align-self:center}.pkr label{font-size:12px;margin:0}.pkr input{padding:6px 8px;margin-top:2px;width:100%;min-width:0;box-sizing:border-box}.pkr .prm{position:static;margin:0 0 6px;flex:none}@media(max-width:600px){.pkr{grid-template-columns:minmax(0,1fr) minmax(0,1fr) 26px}.pkr b{grid-column:1/-1}}
.pick{display:inline-flex;align-items:center;gap:6px;background:#eef0ff;border:1px solid var(--br);color:var(--br);border-radius:99px;padding:4px 6px 4px 12px;font-size:13.5px;font-weight:600}
.prm{width:22px;height:22px;padding:0;margin:0;justify-content:center;border-radius:50%;background:var(--br)!important;box-shadow:none;font-size:15px;line-height:1}
/* ===== v5: supplier actions + owner panel + backs qty ===== */
button.ib{border:0;cursor:pointer;position:relative;padding:0;margin:0 3px;background:#f1f4fb;color:#55607f!important;box-shadow:none;width:34px;height:34px;justify-content:center}
button.ib:hover{background:var(--br);color:#fff!important;transform:none}button.ib.dl:hover{background:var(--red)}
.ib.ct:hover{background:#0891b2}.ib.pr:hover{background:#059669}.ib.ed:hover{background:#d97706}
.sa{display:flex;align-items:center;gap:2px;white-space:nowrap}.sa form{margin:0;display:inline-flex}.sa .ib{width:36px;height:36px}
button.ib,button.bsw{overflow:visible!important}.ib .cn{position:absolute;top:-7px;left:-7px;z-index:2;box-shadow:0 0 0 2px #fff;min-width:18px;height:18px;line-height:18px;border-radius:99px;background:var(--red);color:#fff;font:700 11px/18px system-ui;text-align:center;padding:0 5px}
.ipx{position:relative;width:148px;aspect-ratio:286/540;isolation:isolate;filter:drop-shadow(0 26px 20px #0c123345) drop-shadow(0 3px 5px #0c123333)}
.ipx .ic{position:absolute;inset:0;background:url(/phone-img/ip_body.png) center/100% 100% no-repeat,var(--bk);background-blend-mode:multiply;-webkit-mask:url(/phone-img/ip_body.png) center/100% 100% no-repeat;mask:url(/phone-img/ip_body.png) center/100% 100% no-repeat;transition:background .3s}
.ipx .ic:after{content:'';position:absolute;inset:0;background:linear-gradient(135deg,#fff6 0,#fff0 38%,#0000 62%,#0003 100%)}
.ipx img{position:absolute;inset:0;width:100%;height:100%;display:block;user-select:none;pointer-events:none}
.ipx.sx{width:128px;aspect-ratio:326/681}.ipx.sx .ic{background:url(/phone-img/sm_body.png) center/100% 100% no-repeat,var(--bk);background-blend-mode:multiply;-webkit-mask:url(/phone-img/sm_body.png) center/100% 100% no-repeat;mask:url(/phone-img/sm_body.png) center/100% 100% no-repeat}
.pq{position:absolute;left:50%;top:60%;transform:translate(-50%,-50%);display:flex;flex-direction:column;align-items:center;min-width:54px;padding:5px 12px 6px;border-radius:16px;background:#0c1233b3;color:#fff;backdrop-filter:blur(4px);box-shadow:0 8px 16px -8px #000a;line-height:1.1}
.pq small{font-size:10.5px;font-weight:600;opacity:.85}.pq b{font-size:26px;font-weight:800}.pq.z{background:#be123cd9}
@media(max-width:860px){.ipx{width:132px}}
dialog.dlg.wd{width:min(880px,95vw)}dialog.dlg.wd[open]{display:flex;flex-direction:column}dialog.dlg.wd>.dh,dialog.dlg.wd>.df{flex:none}dialog.dlg.wd>.db{flex:1 1 auto;min-height:0;overflow-y:auto;overscroll-behavior:contain}.mini{width:100%}.mini td,.mini th{padding:8px 9px;font-size:13.5px}
.dsec{font-weight:700;margin:18px 0 8px;font-size:14.5px}.hero3.h2{grid-template-columns:repeat(3,1fr);margin-bottom:6px}.hero3.h2 .st b{font-size:21px}
.pl-r{background:#fff1f3;color:var(--red)}.pl-g{background:#e7f8ef;color:#047857}.pl-a{background:#fff4dc;color:#b45309}.pl-b{background:#e0f7fb;color:#0e7490}
.sg4.o6{grid-template-columns:repeat(6,minmax(0,1fr))}.sg4.o6 .sc{padding:12px;gap:10px}.sg4.o6 .si{width:40px;height:40px;font-size:16px}@media(max-width:1150px){.sg4.o6{grid-template-columns:repeat(3,1fr)}}@media(max-width:600px){.sg4.o6{grid-template-columns:repeat(2,1fr)}}
.uc{display:flex;align-items:center;gap:8px;white-space:nowrap}.uc b{font-size:14.5px}
.dot-on{flex-shrink:0;display:inline-block;width:9px;height:9px;border-radius:50%;background:#10b981;box-shadow:0 0 0 3px #10b98133;margin-inline-end:6px}
.chp{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}.chp button{padding:6px 12px;font-size:13px;margin:0}
.pfx{display:block}.pfx .prow{display:grid;grid-template-columns:1fr 72px 100px 100px 30px;gap:6px;align-items:center;margin-bottom:6px}.pfx .phd{font-size:12px;font-weight:600;color:var(--mut)}
.pfx .prow input{margin:0;width:100%;min-width:0}.pfx .pt{background:#f1f4fb}.pfx .rx{background:#fff1f3!important;color:var(--red)!important;box-shadow:none;width:30px;height:30px;padding:0;justify-content:center;margin:0}
.pfx button svg{width:16px;height:16px;flex-shrink:0}.pfx .gt{display:flex;justify-content:space-between;font-weight:800;font-size:16px;border-top:2px solid var(--line);padding-top:10px;margin-top:8px}
@media(max-width:640px){.pfx .prow{grid-template-columns:1fr 60px 80px 80px 28px}}
.cr{grid-template-columns:52px 1fr 130px}.crh{margin-top:12px;font-size:12.5px;font-weight:600;color:var(--mut);display:grid;grid-template-columns:52px 1fr 130px;gap:8px}
/* ===== REPAIRIX theme v2 ===== */
:root{--navy:#080d2b;--navy2:#111a52;--br:#5b4ef0;--br2:#7c6bff;--cy:#22d3ee;--pk:#e879f9;--paper:#eef1fb;--line:#e6eaf5;--sh:0 1px 2px #0f172a08,0 14px 34px -18px #1e2a6b40;--shh:0 2px 4px #0f172a0a,0 30px 50px -26px #3b2fd066;--r:20px}
html{scroll-behavior:smooth}
body{font-family:"Cairo","Tajawal",system-ui,-apple-system,"Segoe UI",Tahoma,Arial,sans-serif;background:var(--paper);background-image:radial-gradient(900px 500px at 105% -8%,#c7d2fe80,transparent 60%),radial-gradient(700px 480px at -8% 108%,#a5f3fc66,transparent 60%),radial-gradient(#5b4ef014 1px,transparent 1px);background-size:auto,auto,26px 26px;background-attachment:fixed}
::selection{background:#5b4ef033}
*::-webkit-scrollbar{width:10px;height:10px}*::-webkit-scrollbar-thumb{background:#b9c2e6;border-radius:99px;border:2px solid transparent;background-clip:padding-box}*::-webkit-scrollbar-thumb:hover{background:#8f9bd4;background-clip:padding-box;border:2px solid transparent}
/* sidebar */
aside{width:278px;background:radial-gradient(380px 260px at 0% 0%,#5b4ef055,transparent 70%),radial-gradient(320px 300px at 100% 100%,#22d3ee33,transparent 70%),linear-gradient(185deg,#0a1034,#0c1340 55%,#101a55);padding:22px 16px;box-shadow:-20px 0 60px -30px #0c1233;border-left:1px solid #ffffff10}
aside .lk{padding:4px 8px 22px;margin-bottom:14px;border-bottom:1px solid #ffffff18}
aside .lk svg{filter:drop-shadow(0 6px 14px #5b4ef0aa)}
aside a{position:relative;gap:12px;padding:7px 10px;margin-bottom:4px;border-radius:14px;color:#b4bde6;font-weight:600;font-size:14.5px;transition:background .2s,color .2s,transform .2s}
aside a svg{width:34px;height:34px;padding:8px;border-radius:11px;background:#ffffff10;flex-shrink:0;transition:.2s}
aside a:hover{background:#ffffff0f;color:#fff;transform:translateX(-3px)}aside a:hover svg{background:#ffffff1c}
aside a.on{background:linear-gradient(90deg,#5b4ef0e6,#7c6bffcc);color:#fff;box-shadow:0 14px 26px -14px #7c6bff,0 0 0 1px #ffffff22 inset}
aside a.on svg{background:#ffffff26;color:#fff}
aside a.on:before{content:'';position:absolute;right:-16px;top:22%;bottom:22%;width:4px;border-radius:4px 0 0 4px;background:linear-gradient(180deg,#67e8f9,#a78bfa);box-shadow:0 0 14px #67e8f9}
aside .out{margin-top:16px;border-top:1px solid #ffffff18;border-radius:14px;padding:7px 10px;color:#fda4af}aside .out:hover{background:#e11d4826;color:#fecdd3}
aside .nvh{font-size:11.5px;font-weight:800;letter-spacing:.03em;color:#7f8ac4;padding:16px 12px 6px;margin-top:2px;border-top:1px solid #ffffff12}
.trs{background:linear-gradient(135deg,#fbbf2422,#f9731622);border:1px solid #fbbf2455;color:#fde68a;font-weight:700;border-radius:14px}
.bd{box-shadow:0 0 0 3px #e11d4833;animation:bdp 2.2s ease-in-out infinite}@keyframes bdp{50%{box-shadow:0 0 0 6px #e11d4800}}
/* main + header */
main{padding:32px 38px 48px;max-width:1320px}
.ph{display:flex;flex-direction:column;margin-bottom:24px;padding-inline-start:18px;position:relative;animation:up .5s both}
.ph:before{content:'';position:absolute;inset-inline-start:0;top:6px;bottom:6px;width:6px;border-radius:99px;background:linear-gradient(180deg,var(--br),var(--cy))}
.ph h2{font-size:30px;font-weight:800;letter-spacing:-.2px;background:linear-gradient(90deg,#0c1233,#3b2fd0);-webkit-background-clip:text;background-clip:text;color:transparent}
.ph p{font-size:15px}
@keyframes up{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}
main>*{animation:up .55s cubic-bezier(.2,.8,.2,1) both}main>*:nth-child(2){animation-delay:.04s}main>*:nth-child(3){animation-delay:.08s}main>*:nth-child(4){animation-delay:.12s}main>*:nth-child(5){animation-delay:.16s}main>*:nth-child(n+6){animation-delay:.2s}
/* cards */
.card,.tools,.st,.sc,.tb7{border:1px solid #ffffffcc;border-radius:var(--r);background:#ffffffd9;-webkit-backdrop-filter:blur(10px);backdrop-filter:blur(10px);box-shadow:var(--sh),0 0 0 1px var(--line)}
.card{padding:24px;position:relative}.card>h3:first-child{position:relative;padding-inline-start:14px}.card>h3:first-child:before{content:'';position:absolute;inset-inline-start:0;top:4px;bottom:4px;width:4px;border-radius:9px;background:linear-gradient(180deg,var(--br),var(--cy))}
.sc{transition:transform .25s,box-shadow .25s;overflow:hidden;position:relative}.sc:hover{transform:translateY(-4px);box-shadow:var(--shh),0 0 0 1px #c7cffa}
.sc:after{display:none}
.si{width:50px;height:50px;border-radius:16px;box-shadow:0 12px 20px -12px currentColor}
.si.a{background:linear-gradient(135deg,#e0e4ff,#c9d0ff)}.si.b{background:linear-gradient(135deg,#d3f6fc,#a5eefa)}.si.c{background:linear-gradient(135deg,#d6f7e6,#a7efc9)}.si.d{background:linear-gradient(135deg,#ffe4e8,#ffc2cb)}.si.e{background:linear-gradient(135deg,#fff0cc,#ffdf8f)}.si.f{background:linear-gradient(135deg,#d6f7e6,#a7efc9)}.si.g{background:linear-gradient(135deg,#f1e0ff,#ddb8ff)}
.sc b{font-weight:800;letter-spacing:-.3px}.sc small{font-weight:600}
/* hero */
.hb{border-radius:28px;padding:36px 38px;background:radial-gradient(500px 300px at 10% 120%,#22d3ee55,transparent 60%),radial-gradient(520px 320px at 95% -20%,#e879f988,transparent 60%),linear-gradient(120deg,#080d2b 0%,#2a2ba0 55%,#5b4ef0 100%);box-shadow:0 34px 60px -30px #4338ca}
.hb:before{background:none}
.hb:after{content:'';position:absolute;inset:-40% -10%;background:conic-gradient(from 0deg,transparent,#ffffff14,transparent 25%);animation:spin 18s linear infinite;pointer-events:none}@keyframes spin{to{transform:rotate(360deg)}}
.hb h2{font-size:31px;font-weight:800;text-shadow:0 6px 30px #0006}
.hb .btn{border-radius:14px;padding:12px 22px;font-weight:800}.hb .btn:hover{transform:translateY(-3px);box-shadow:0 14px 26px -10px #0008}
.mo{background:#ffffff1c;border:1px solid #ffffff3d;border-radius:20px;box-shadow:0 20px 34px -20px #000a,0 0 0 1px #ffffff12 inset;transition:transform .25s}.mo:hover{transform:translateY(-4px)}
.mo b{text-shadow:0 4px 20px #0005}
.tb7{border-right-width:6px}
/* buttons & fields */
button,.btn{white-space:nowrap;border-radius:12px;padding:10px 20px;font-weight:700;background:linear-gradient(135deg,var(--br) 0%,var(--br2) 100%);box-shadow:0 14px 24px -14px var(--br),0 1px 0 #ffffff55 inset;position:relative;overflow:hidden;transition:transform .15s,box-shadow .2s,filter .2s}
button:before,.btn:before{content:'';position:absolute;inset:0;background:linear-gradient(110deg,transparent 30%,#ffffff40 50%,transparent 70%);transform:translateX(120%);transition:transform .6s}
button:hover:before,.btn:hover:before{transform:translateX(-120%)}
button:hover,.btn:hover{transform:translateY(-2px);box-shadow:0 20px 30px -14px var(--br);filter:none}button:active,.btn:active{transform:translateY(0) scale(.98)}
.ghost{background:#eef1fb!important;color:#33407a!important;box-shadow:0 0 0 1px #dbe1f5 inset!important}.ghost:hover{background:#e3e8fb!important}
.vt button:before,.ib:before,.cl:before,.eye:before,.swb:before,.toast .x:before{display:none}
input,select,textarea{border-radius:12px;border:1.5px solid #dbe1f2;background-color:#fbfcff;padding:10px 14px;transition:border-color .2s,box-shadow .2s,background .2s}
input:hover,select:hover{border-color:#b9c4ec}input:focus,select:focus,textarea:focus{background-color:#fff;border-color:var(--br);box-shadow:0 0 0 4px #5b4ef01f}
input[type=checkbox],input[type=radio]{accent-color:var(--br)}
select{padding-left:34px!important}
.ib{width:36px;height:36px;border-radius:12px;background:#eef1fb;color:#4a5688;box-shadow:0 0 0 1px #e1e6f6 inset}.ib:hover{background:linear-gradient(135deg,var(--br),var(--br2));color:#fff;transform:translateY(-2px);box-shadow:0 12px 18px -10px var(--br)}.ib.dl:hover{background:linear-gradient(135deg,#fb7185,#e11d48);box-shadow:0 12px 18px -10px #e11d48}
.tools{padding:14px;border-radius:22px}
.vt{background:#e6eaf8;border-radius:14px}.vt button.on{border-radius:11px}
/* tables */
table{border-collapse:separate;border-spacing:0}
th{background:linear-gradient(180deg,#f4f6fe,#edf0fb);color:#56608b;font-weight:700;font-size:12.5px;letter-spacing:.2px;border-bottom:1px solid var(--line)}
td{border-bottom:1px solid #eef1f9;transition:background .15s}tr:last-child td{border-bottom:0}
tbody tr:nth-child(even) td,table tr:nth-child(even)>td{background:#fafbff}tbody tr:hover td,table tr:hover>td{background:#f1f3ff}
td b{font-weight:700}
/* pills tags */
.pill,.tag{display:inline-flex;align-items:center;gap:6px;padding:3px 13px;font-weight:700}
.pill:before,.tag:before{content:'';width:7px;height:7px;border-radius:50%;background:currentColor;box-shadow:0 0 0 3px color-mix(in srgb,currentColor 20%,transparent)}
.pill.s0{background:#fff3d6;color:#b45309}.pill.s1{background:#dcf6fb;color:#0e7490}.pill.s2{background:#dcf7ea;color:#047857}
/* product cards */
.pc{border-radius:24px;border:1px solid #ffffffcc;box-shadow:var(--sh),0 0 0 1px var(--line);transition:transform .3s cubic-bezier(.2,.8,.2,1),box-shadow .3s}.pc:hover{transform:translateY(-6px);box-shadow:var(--shh),0 0 0 1px #c7cffa}
.pm{height:150px;background:radial-gradient(120px 90px at 80% 20%,#ffffffaa,transparent),linear-gradient(135deg,var(--c1),var(--c2))}.pm>svg{width:58px;height:58px;filter:drop-shadow(0 12px 14px color-mix(in srgb,var(--c3) 45%,transparent));transition:transform .4s}.pc:hover .pm>svg{transform:scale(1.12) rotate(-6deg)}
.pr3>div{background:linear-gradient(180deg,#f7f9ff,#eff2fc);border:1px solid #e8ecf8;border-radius:14px}
.qt{height:9px;background:#e8ecf8}.qt i{box-shadow:0 0 12px -2px currentColor}
.pf{background:linear-gradient(180deg,#fbfcff,#f4f6fd)}
.mc{border-radius:30px;box-shadow:var(--sh),0 0 0 1px var(--line);transition:transform .3s,box-shadow .3s}.mc:hover{transform:translateY(-5px);box-shadow:var(--shh)}
.swb{transition:transform .2s,box-shadow .2s}.swb:hover{transform:scale(1.15)}
.cp{border-radius:18px}
/* bars */
.bar .tr{height:12px;background:#e9edfa}.bar i{background:linear-gradient(90deg,var(--br),var(--cy));box-shadow:0 6px 14px -6px var(--br);animation:grow 1s cubic-bezier(.2,.8,.2,1) both;transform-origin:right}@keyframes grow{from{transform:scaleX(0)}}
.lw{transition:background .15s,padding .15s;border-radius:12px}.lw:hover{background:#f3f5ff;padding-inline:10px}
.ring{box-shadow:0 12px 24px -14px #f59e0b}
/* dialogs */
dialog.dlg{border-radius:26px;box-shadow:0 50px 100px -30px #0c1233cc,0 0 0 1px #ffffff40}
.dh{background:radial-gradient(260px 120px at 100% 0%,#22d3ee55,transparent 70%),linear-gradient(135deg,#080d2b,#2b2fa0)}
.df{background:#f5f7fe}
/* === scroll fix: header/footer stay pinned, any dialog body scrolls (v9.1) === */
dialog.dlg{max-height:92vh;max-height:92dvh}
dialog.dlg[open]{display:flex;flex-direction:column}
dialog.dlg>form{flex:1 1 auto;min-height:0;max-height:none}
dialog.dlg .dh,dialog.dlg .df{flex:none}
dialog.dlg form>:not(.dh):not(.df):not([type=hidden]){flex:1 1 auto;min-height:0;overflow-y:auto;overscroll-behavior:contain;-webkit-overflow-scrolling:touch;touch-action:pan-y}
#dlg-pick .pkw{max-height:none;flex:1 1 auto;min-height:0}
#dlg-pick .pklist{overscroll-behavior:contain;-webkit-overflow-scrolling:touch}
#imgv img{max-width:100%;max-height:85vh;object-fit:contain}
/* toasts */
.toast{border-radius:16px}
/* chips */
.chips label{transition:.15s}.chips label:hover{border-color:var(--br)}
@media(max-width:860px){aside .nvh{display:none}aside{width:auto;padding:8px 10px}aside a svg{width:30px;height:30px;padding:7px}aside a.on:before{display:none}aside a:hover{transform:none}main{padding:16px 14px 36px}.ph h2{font-size:24px}.hb{padding:24px 20px}}
@media(prefers-reduced-motion:reduce){main>*,.ph,.hb:after,.bar i,.bd{animation:none!important}}
/* ===== employees / debts / returns ===== */
.eg{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:18px;margin-bottom:18px}
.ec{display:block;position:relative;overflow:hidden;background:#ffffffd9;border-radius:24px;padding:22px 20px 16px;box-shadow:var(--sh),0 0 0 1px var(--line);color:var(--ink)!important;text-decoration:none!important;transition:transform .3s cubic-bezier(.2,.8,.2,1),box-shadow .3s}
.ec:before{content:'';position:absolute;inset:0 0 auto 0;height:6px;background:linear-gradient(90deg,hsl(var(--h) 80% 60%),hsl(calc(var(--h) + 50) 85% 62%))}
.ec:hover{transform:translateY(-6px);box-shadow:var(--shh),0 0 0 1px #c7cffa}.ech{display:flex;gap:14px;align-items:center;margin-bottom:16px}
.av{width:56px;height:56px;border-radius:18px;display:grid;place-items:center;font-size:23px;font-weight:800;color:#fff;background:linear-gradient(135deg,hsl(var(--h) 70% 32%),hsl(calc(var(--h) + 45) 70% 38%));box-shadow:0 14px 22px -12px hsl(var(--h) 75% 45%);flex-shrink:0}
.en{min-width:0}.en b{display:block;font-size:17px;line-height:1.35}.en small{display:block;line-height:1.5}
.ec3{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.ec3>div{background:linear-gradient(180deg,#f7f9ff,#eff2fc);border:1px solid #e8ecf8;border-radius:14px;padding:9px 4px;text-align:center}.ec3 small{display:block;font-size:11px}.ec3 b{font-size:14.5px;white-space:nowrap}
.ecf{display:flex;align-items:center;justify-content:center;gap:8px;margin-top:14px;color:var(--br);font-weight:700;font-size:13.5px}.ecf svg{width:16px;height:16px}
.ehd{display:flex;align-items:center;gap:14px;flex-wrap:wrap;overflow:visible}.ehd .sp{flex:1}.ehd .il{display:inline-flex}.hint{color:var(--mut);font-size:13px;margin:12px 0 0}
.pgb{height:10px;border-radius:99px;background:#e8ecf8;overflow:hidden}.pgb i{display:block;height:100%;border-radius:99px}
.amt{font-weight:800}.amt.up{color:var(--red)}.amt.dn{color:var(--ok)}
.rem{display:flex;align-items:center;gap:24px;flex-wrap:wrap}.rem b{display:block;font-size:30px;line-height:1.3;font-weight:800}.rem b.up{color:var(--red)}.rem b.dn{color:var(--ok)}
.pill.s3{background:#ffe4e8;color:#be123c}
.il button.ib{margin:0}
/* ===== top bar ===== */
.mw{flex:1;min-width:0;display:flex;flex-direction:column}.mw>main{flex:1 1 auto;width:100%}
.tbar{position:sticky;top:0;z-index:40;display:flex;align-items:center;gap:12px;padding:12px 38px;background:linear-gradient(180deg,#fffffff2,#ffffffd6);-webkit-backdrop-filter:blur(14px) saturate(1.5);backdrop-filter:blur(14px) saturate(1.5);border-bottom:1px solid var(--line);box-shadow:0 14px 30px -26px #1e2a6b88}
.tbar:after{content:'';position:absolute;inset:auto 0 -1px 0;height:2px;background:linear-gradient(90deg,transparent,var(--br2),var(--cy),transparent);opacity:.55;pointer-events:none}
.tbr{display:flex;align-items:center;gap:12px;color:var(--ink)!important;text-decoration:none!important;min-width:0;flex:0 1 auto}.tbr .tbn{min-width:0}
.tbl{position:relative;width:46px;height:46px;border-radius:15px;flex-shrink:0;display:grid;place-items:center;color:#fff;font:800 24px/1 Cairo,system-ui,sans-serif;background:radial-gradient(34px 26px at 20% 0%,#ffffff55,transparent 70%),linear-gradient(135deg,#4338ca,#7c6bff 55%,#22d3ee);box-shadow:0 14px 22px -12px #5b4ef0,0 0 0 1px #ffffff55 inset;transition:transform .25s}
.tbr:hover .tbl{transform:rotate(-6deg) scale(1.06)}
.tbl .wb{position:absolute;bottom:-6px;left:-6px;width:21px;height:21px;padding:4px;border-radius:50%;background:#fff;color:var(--br);box-shadow:0 4px 10px -3px #1e2a6b66}
.tbl.im{background:#fff;box-shadow:0 0 0 1px var(--line),0 10px 18px -12px #1e2a6b66;overflow:hidden}.tbl.im img{width:100%;height:100%;object-fit:contain;display:block}
.tbn{display:flex;flex-direction:column;min-width:0;line-height:1.25}.tbn b{font-size:18px;font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:300px}.tbn small{font-size:12px;font-weight:600;white-space:nowrap}
.tsp{flex:1}
.tcl,.tch{display:flex;align-items:center;gap:10px;padding:6px 16px 6px 14px;border-radius:16px;background:#f4f6fe;box-shadow:0 0 0 1px #e4e8f6 inset;flex-shrink:0}
.tcl svg,.tch svg{width:34px;height:34px;padding:8px;border-radius:11px;flex-shrink:0}
.tcl>span,.tch>span{display:flex;flex-direction:column;line-height:1.25}.tcl small,.tch small{font-size:11.5px;font-weight:600;color:var(--mut)}.tcl b,.tch b{font-size:15px;font-weight:800;white-space:nowrap}
.tcl svg{background:linear-gradient(135deg,#e0e4ff,#c9d0ff);color:var(--br)}
.tch.c1 svg{background:linear-gradient(135deg,#d6f7e6,#a7efc9);color:#047857}.tch.c1 b{color:#047857}
.tch.c2 svg{background:linear-gradient(135deg,#d3f6fc,#a5eefa);color:#0e7490}
.tbar .ib{margin:0;position:relative;color:#4a5688!important;text-decoration:none!important;flex-shrink:0;width:42px;height:42px;border-radius:14px}.tbar .ib:hover{color:#fff!important}
.tbar .ib .bd{position:absolute;top:-6px;left:-6px;min-width:18px;height:18px;line-height:18px;padding:0 5px;text-align:center;font-size:11px;font-weight:800;border-radius:99px}
.tpf{position:relative;flex-shrink:0}.tpf>summary{list-style:none;display:flex;align-items:center;gap:10px;cursor:pointer;padding:5px 6px 5px 12px;border-radius:16px;background:#fff;box-shadow:0 0 0 1px var(--line);transition:.2s}
.tpf>summary::-webkit-details-marker{display:none}.tpf>summary:hover,.tpf[open]>summary{box-shadow:0 0 0 2px var(--br2),0 12px 22px -14px var(--br)}
.av2{width:38px;height:38px;border-radius:13px;display:grid;place-items:center;color:#fff;font-weight:800;font-size:17px;background:linear-gradient(135deg,#4338ca,#22d3ee);flex-shrink:0}
.pn{display:flex;flex-direction:column;line-height:1.25;max-width:150px}.pn b{font-size:14px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.pn small{font-size:11.5px;font-weight:700;color:var(--br)}
.tpf>summary>svg{width:16px;height:16px;color:var(--mut);transition:transform .2s;flex-shrink:0}.tpf[open]>summary>svg{transform:rotate(180deg)}
.pm2{position:absolute;top:calc(100% + 10px);left:0;min-width:210px;background:#fff;border-radius:18px;padding:8px;box-shadow:0 30px 60px -24px #0c1233aa,0 0 0 1px var(--line);animation:up .2s both;z-index:50}
.pm2 a{display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:12px;color:var(--ink);font-weight:600;text-decoration:none!important}.pm2 a svg{width:18px;height:18px;color:var(--br)}.pm2 a:hover{background:#f1f3ff}
.pm2 a.lo{color:#be123c}.pm2 a.lo svg{color:#e11d48}.pm2 a.lo:hover{background:#fff1f3}
/* --- أسعار الصرف بالقائمة العلوية --- */
.fx{position:relative;flex-shrink:0}
.fx>summary{list-style:none;display:flex;align-items:center;gap:4px;cursor:pointer;padding:5px 6px 5px 10px;border-radius:16px;background:#f4f6fe;box-shadow:0 0 0 1px #e4e8f6 inset;transition:.2s;user-select:none}
.fx>summary::-webkit-details-marker{display:none}
.fx>summary:hover,.fx[open]>summary{background:#fff;box-shadow:0 0 0 2px var(--br2),0 12px 22px -14px var(--br)}
.fx>summary>svg{width:16px;height:16px;color:var(--mut);transition:transform .2s;flex-shrink:0}.fx[open]>summary>svg{transform:rotate(180deg)}
.fxi{display:flex;align-items:center;gap:9px;padding:1px 4px 1px 10px}
.fxi+.fxi{border-right:1px solid #dde2f4;padding-right:12px}
.fxi i{font-style:normal;width:34px;height:34px;border-radius:11px;display:grid;place-items:center;font:800 14px/1 Cairo,system-ui,sans-serif;flex-shrink:0}
.fxi .fu{background:linear-gradient(135deg,#d6f7e6,#a7efc9);color:#047857}.fxi .fj{background:linear-gradient(135deg,#ffe9c7,#ffd08a);color:#b45309}
.fxi>span{display:flex;flex-direction:column;line-height:1.25}.fxi small{font-size:11.5px;font-weight:600;color:var(--mut)}
.fxi b{font-size:15px;font-weight:800;white-space:nowrap;font-variant-numeric:tabular-nums;display:flex;align-items:center;gap:4px}
.fxi b u{text-decoration:none;font-size:12px;color:var(--mut);font-weight:700}
.fxi em{font-style:normal;font-size:9.5px;font-weight:800}.fxi em.up{color:var(--ok)}.fxi em.dn{color:var(--red)}
.fx.ld .fxi b,.fx.ld .fxt td:last-child{color:transparent!important;background:linear-gradient(90deg,#e6eaf8,#f6f8fe,#e6eaf8);background-size:200% 100%;animation:fxs 1.2s linear infinite;border-radius:6px}
@keyframes fxs{to{background-position:-200% 0}}
.fxm{position:absolute;top:calc(100% + 10px);left:0;width:330px;background:#fff;border-radius:20px;padding:16px;box-shadow:0 30px 60px -24px #0c1233aa,0 0 0 1px var(--line);animation:up .2s both;z-index:50}
.fxh{display:flex;align-items:center;gap:8px;margin-bottom:8px}.fxh b{font-size:15.5px;flex:1}
.fxs{font-size:11px;font-weight:800;padding:3px 9px;border-radius:99px;background:#e7f8ef;color:#047857}.fxs.m{background:#fff4dc;color:#b45309}.fxs.x{background:#fff1f3;color:var(--red)}
.fxm button.fxr{width:32px;height:32px;margin:0;padding:0;justify-content:center;border-radius:10px;background:#f1f4fb;color:#55607f!important;box-shadow:none}.fxm button.fxr:hover{background:var(--br);color:#fff!important;transform:none}.fxm button.fxr svg{width:16px;height:16px}.fxm button.fxr.sp svg{animation:fxsp .8s linear infinite}
@keyframes fxsp{to{transform:rotate(360deg)}}
.fxt{width:100%;border-collapse:collapse;margin-bottom:12px}.fxt td{padding:9px 4px;border-bottom:1px dashed var(--line);font-size:14px}.fxt tr:last-child td{border-bottom:0}.fxt td:last-child{text-align:left;font-weight:800;font-variant-numeric:tabular-nums}
.fxc{background:#f4f6fe;border-radius:14px;padding:10px}.fxc>small{display:block;font-weight:700;color:var(--mut);margin:0 4px 2px}
.fxrow{display:flex}.fxrow input{flex:1;min-width:0;margin:3px;text-align:left;direction:ltr}.fxrow select{width:122px;margin:3px}
.fxo{display:flex;gap:8px;margin-top:4px}.fxo div{flex:1;background:#fff;border-radius:11px;padding:7px 10px;box-shadow:0 0 0 1px var(--line)}.fxo small{display:block;color:var(--mut);font-size:11px;font-weight:600}.fxo b{font-size:15px;font-variant-numeric:tabular-nums}
.fxn{display:block;margin-top:10px;color:var(--mut);font-size:11.5px;text-align:center}
/* --- تصميم القائمة العلوية الجديد (داكن) --- */
.tbar{padding:12px 34px;gap:12px;background:radial-gradient(520px 120px at 8% 0%,#6d5efc40,transparent 70%),radial-gradient(420px 120px at 92% 100%,#22d3ee26,transparent 70%),linear-gradient(100deg,#0c1233,#151d4d 55%,#1a2565);-webkit-backdrop-filter:none;backdrop-filter:none;border-bottom:1px solid #ffffff14;box-shadow:0 18px 38px -22px #0c1233}
.tbar:after{height:2px;opacity:.9;background:linear-gradient(90deg,transparent,#6d5efc,#22d3ee,transparent)}
.tbar .tbr{color:#fff!important}.tbar .tbn b{color:#fff;font-size:18.5px;letter-spacing:.2px}.tbar .tbn small{color:#9fb0ee}
.tbar .tbl{width:48px;height:48px;border-radius:16px}.tbar .tbl.im{background:#fff;box-shadow:0 0 0 2px #ffffff30,0 12px 22px -12px #000}
.tbar .tbl .wb{box-shadow:0 0 0 2px #0c1233}
.tbar .tcl,.tbar .tch,.tbar .fx>summary{background:#ffffff10;box-shadow:0 0 0 1px #ffffff1f inset;-webkit-backdrop-filter:blur(6px);backdrop-filter:blur(6px)}
.tbar .tcl small,.tbar .tch small,.tbar .fxi small{color:#9fb0ee}
.tbar .tcl b,.tbar .tch b,.tbar .fxi b{color:#fff}
.tbar .tch.c1 b{color:#6ee7b7}
.tbar .tcl svg{background:linear-gradient(135deg,#6d5efc55,#6d5efc22);color:#c7ceff}
.tbar .tch.c1 svg{background:linear-gradient(135deg,#10b98155,#10b98122);color:#6ee7b7}
.tbar .tch.c2 svg{background:linear-gradient(135deg,#22d3ee55,#22d3ee22);color:#67e8f9}
.tbar .fx>summary:hover,.tbar .fx[open]>summary{background:#ffffff1c;box-shadow:0 0 0 2px #6d5efc,0 14px 26px -14px #6d5efc}
.tbar .fx>summary>svg,.tbar .fxi b u{color:#9fb0ee}
.tbar .fxi+.fxi{border-right-color:#ffffff22}
.tbar .fxi .fu{background:linear-gradient(135deg,#10b98155,#10b98122);color:#6ee7b7}.tbar .fxi .fj{background:linear-gradient(135deg,#f59e0b55,#f59e0b22);color:#fcd34d}
.tbar .fxi em.up{color:#6ee7b7}.tbar .fxi em.dn{color:#fda4af}
.tbar .fx.ld .fxi b{background:linear-gradient(90deg,#ffffff10,#ffffff26,#ffffff10);background-size:200% 100%}
.fxm{color:var(--ink)}
.tbar .ib{width:46px;height:46px;border-radius:15px;background:#ffffff12;box-shadow:0 0 0 1px #ffffff1f inset;color:#dfe4ff!important;transition:.2s}
.tbar .ib svg{width:21px;height:21px}
.tbar .ib:hover{background:linear-gradient(135deg,#4f46e5,#6d5efc);color:#fff!important;transform:translateY(-2px);box-shadow:0 14px 24px -12px #6d5efc}
.tbar .ib.on{background:linear-gradient(135deg,#4f46e5,#6d5efc);color:#fff!important;box-shadow:0 12px 22px -12px #6d5efc}
.tbar .ib.tgs:hover svg{animation:tgr .9s ease}
@keyframes tgr{to{transform:rotate(180deg)}}
.tbar .ib .bd{top:-6px;left:-6px;background:linear-gradient(135deg,#f43f5e,#e11d48);color:#fff;box-shadow:0 0 0 2px #0c1233}
@media(max-width:1500px){.tcl{display:none}}
@media(max-width:1380px){.tch.c2{display:none}}
@media(max-width:1200px){.fxi small{display:none}.tch.c1 small{display:none}}
@media(max-width:860px){.tbar{padding:10px 14px;gap:8px}.tbn small,.tch{display:none}.tbn b{max-width:150px;font-size:16px}.fxi+.fxi{display:none}.fxi small{display:none}.fxm{position:fixed;top:68px;left:10px;right:10px;width:auto}}
@media print{.tbar{display:none}}
</style>
<div id=tc aria-live=polite>{% with m = get_flashed_messages(with_categories=true) %}{% for k,t in m %}{% set p = t.split('|',1) %}<div class="toast {{k}}" role=status>
<span class=ti><svg width=16 height=16 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2.4 stroke-linecap=round stroke-linejoin=round>{% if k == 'ok' %}<path d="M5 12.5l4.5 4.5L19 7.5"/>{% elif k == 'warn' %}<path d="M12 3l10 18H2zM12 10v5M12 18h.01"/>{% else %}<circle cx=12 cy=12 r=9 /><path d="M12 11v6M12 7.5h.01"/>{% endif %}</svg></span>
<div class=tb><b>{{p[0]}}</b><span>{{p[1]}}</span></div><button class=x aria-label="إغلاق" onclick="this.parentElement.remove()">×</button></div>{% endfor %}{% endwith %}</div>
{% set PT = {'/repairs':('الصيانة','سجّل الأجهزة وتابع حالتها وتواصل مع الزبون'),'/suppliers':('الموردين','بيانات الموردين وطرق التواصل'),'/report':('التقرير الشهري','الإيرادات والتكلفة والربح'),'/notifications':('الإشعارات','سجل كل العمليات والتنبيهات'),'/settings':('الإعدادات','اسم الشركة والشعار وأسعار الصرف ومفتاح الدولة'),'/requirements':('متطلبات الصيانة والمرتجعات','النواقص المطلوب شراؤها والمرتجعات، مع فاتورة لكل مورد')} %}
{% set NAV = [('',[('/','الرئيسية','M3 11l9-8 9 8v10h-6v-6H9v6H3z'),('/pos','كاشير سريع','M4 7h16v10H4zM8 21h8M12 17v4M7 11h4'),('/today','دخل اليوم','M12 1v22M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6')]),('الورشة',[('/repairs','الصيانة','M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z'),('/requirements','متطلبات الصيانة','M9 3h6v3H9zM6 5H5v16h14V5h-1M9 11h6M9 15h6'),('/tools','أدوات الصيانة','M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76zM3 21l3-3')]),('المخزون وقطع الغيار',[('/parts','قطع الغيار','M21 8l-9-5-9 5v8l9 5 9-5zM3 8l9 5 9-5M12 13v8'),('/screens','شاشات','M7 2h10a2 2 0 012 2v16a2 2 0 01-2 2H7a2 2 0 01-2-2V4a2 2 0 012-2zM12 18h.01'),('/batteries','البطاريات','M3 8h14a2 2 0 012 2v4a2 2 0 01-2 2H3a2 2 0 01-2-2v-4a2 2 0 012-2zM23 11v2'),('/ics','الآيسيات','M6 6h12v12H6zM9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4'),('/chargers','قواعد شحن','M13 2L3 14h9l-1 8 10-12h-9z'),('/connectors','الكونكترات','M7 3v5M17 3v5M5 8h14v4a7 7 0 01-14 0zM12 19v2'),('/headphones','سماعات','M3 18v-6a9 9 0 0118 0v6M21 19a2 2 0 01-2 2h-1a2 2 0 01-2-2v-3a2 2 0 012-2h3zM3 19a2 2 0 002 2h1a2 2 0 002-2v-3a2 2 0 00-2-2H3z'),('/backs','ظهور','M6 2h12a2 2 0 012 2v16a2 2 0 01-2 2H6a2 2 0 01-2-2V4a2 2 0 012-2zM8 6h5v5H8z'),('/barcodes','ملصقات الباركود','M3 5v14M7 5v14M11 5v14M14 5v14M18 5v14M21 5v14'),('/suppliers','الموردين','M1 6h13v10H1zM14 10h4l3 3v3h-7zM6 19a2 2 0 100-4 2 2 0 000 4zM17 19a2 2 0 100-4 2 2 0 000 4z')]),('المبيعات والمتجر',[('/store','تصنيفات المنتجات','M9 21a1 1 0 100-2 1 1 0 000 2zM20 21a1 1 0 100-2 1 1 0 000 2zM1 1h4l2.7 13.4a2 2 0 001.6 1.6h9.7a2 2 0 002-1.6L23 6H6'),('/sales','فواتير البيع','M6 2h9l5 5v15H6zM14 2v6h6M9 13h8M9 17h8'),('/returns','المرتجعات','M3 7h12a6 6 0 010 12H7M3 7l4-4M3 7l4 4')]),('المالية',[('/cashbox','الصندوق المالي','M3 7h18v12H3zM3 7l3-3h12l3 3M16 13h2'),('/debts','الديون','M12 1v22M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6'),('/cheques','الشيكات','M3 6h18v12H3zM3 10h18M7 15h5'),('/report','التقرير','M4 20V10M10 20V4M16 20v-8M22 20H2')]),('الفريق والحسابات',[('/employees','الموظفين','M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2M9 11a4 4 0 100-8 4 4 0 000 8zM23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75'),('/people','الأشخاص','M16 21v-2a4 4 0 00-4-4H6a4 4 0 00-4 4v2M9 11a4 4 0 100-8 4 4 0 000 8zM22 21v-2a4 4 0 00-3-3M16 3.1a4 4 0 010 7.8')]),('النظام',[('/notifications','الإشعارات','M18 8a6 6 0 10-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 01-3.4 0'),('/settings','الإعدادات','M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6')])] %}
<div class="{{'app' if session.uid else 'bare'}}">{% if session.uid %}<aside>{{logo}}
{% for gt,gi in NAV %}{% if gt %}<div class=nvh>{{gt}}</div>{% endif %}{% for u,n,ic in gi %}
{% set on = (request.path == '/') if u == '/' else request.path.startswith(u) %}<a href={{u}} class="{{'on' if on}}"><svg width=18 height=18 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=1.8 stroke-linecap=round stroke-linejoin=round><path d="{{ic}}"/></svg>{{n}}{% if u == '/notifications' and unread %} <span class=bd>{{unread}}</span>{% endif %}</a>{% endfor %}{% endfor %}
{% if is_owner %}<a href=/owner class="{{'on' if request.path.startswith('/owner')}}"><svg width=18 height=18 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=1.8 stroke-linecap=round stroke-linejoin=round><path d="M12 2l8 4v6c0 5-3.5 8.5-8 10-4.5-1.5-8-5-8-10V6zM9 12l2 2 4-4"/></svg>لوحة المالك</a>{% endif %}
{% if trial and trial.state=='active' %}<div class=trs>تجريبي · متبقي {{trial.left}} أيام</div>{% elif trial and trial.state=='paid' %}<div class=trs>اشتراك · متبقي {{trial.left}} يوم</div>{% endif %}<a class=out href=/logout>تسجيل الخروج</a></aside>{% endif %}{% if session.uid %}<div class=mw>
<header class=tbar>
<a class=tbr href=/ title="{{tb_shop}}">{% if tb_logo %}<span class="tbl im"><img src="/shoplogo?v={{tb_logo}}" alt=""></span>{% else %}<span class=tbl aria-hidden=true>{{ (tb_shop|trim|first)|upper }}<svg class=wb viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2.4 stroke-linecap=round stroke-linejoin=round><path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z"/></svg></span>{% endif %}<span class=tbn><b>{{tb_shop}}</b><small>إدارة الصيانة والمخزون</small></span></a>
<span class=tsp></span>
<div class=tcl><svg width=18 height=18 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2 stroke-linecap=round stroke-linejoin=round aria-hidden=true><path d="M12 22a10 10 0 100-20 10 10 0 000 20zM12 6v6l4 2"/></svg><span><b id=tclk>--:--</b><small id=tdt>{{dt if dt is defined else ''}}</small></span></div>
<details class="fx ld" id=fx><summary title="أسعار الصرف · اضغط لفتح المحوّل"><span class=fxi><i class=fu>$</i><span><small>الدولار</small><b><span id=fx-usd>0.00</span><u>₪</u><em id=fx-usd-c></em></b></span></span><span class=fxi><i class=fj>JD</i><span><small>الدينار</small><b><span id=fx-jod>0.00</span><u>₪</u><em id=fx-jod-c></em></b></span></span><svg viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2 stroke-linecap=round stroke-linejoin=round aria-hidden=true><path d="M6 9l6 6 6-6"/></svg></summary><div class=fxm><div class=fxh><b>أسعار الصرف</b><span class=fxs id=fx-src>...</span><button type=button class=fxr id=fx-rf title="تحديث الآن" aria-label="تحديث الأسعار"><svg viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2 stroke-linecap=round stroke-linejoin=round><path d="M21 12a9 9 0 11-3-6.7M21 4v5h-5"/></svg></button></div><table class=fxt><tr><td>1 دولار ($)</td><td><span id=t-usd>0.00</span> ₪</td></tr><tr><td>1 دينار (JD)</td><td><span id=t-jod>0.00</span> ₪</td></tr><tr><td>1 دولار ($)</td><td><span id=t-ujd>0.000</span> JD</td></tr></table><div class=fxc><small>محوّل سريع</small><div class=fxrow><input id=fxa type=number step=any min=0 value=100 inputmode=decimal aria-label="المبلغ"><select id=fxf aria-label="العملة"><option value=ILS>₪ شيكل</option><option value=USD>$ دولار</option><option value=JOD>JD دينار</option></select></div><div class=fxo><div><small id=fx-l1></small><b id=fx-o1>—</b></div><div><small id=fx-l2></small><b id=fx-o2>—</b></div></div></div><small class=fxn id=fx-time>جاري التحميل…</small></div></details>
<a class="tch c1" href=/today style="text-decoration:none;color:inherit" title="دخل اليوم: كل اللي بعته اليوم (مبيعات + صيانات مسلّمة) — اضغط للتفاصيل والمربح"><svg width=18 height=18 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2 stroke-linecap=round stroke-linejoin=round aria-hidden=true><path d="M12 1v22M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6"/></svg><span><small>دخل اليوم</small><b>{{'%g'|format(tb_inc)}} ₪</b></span></a>
<div class="tch c2" title="الأجهزة اللي لسا قيد الصيانة"><svg width=18 height=18 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2 stroke-linecap=round stroke-linejoin=round aria-hidden=true><path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z"/></svg><span><small>قيد الصيانة</small><b>{{tb_open}}</b></span></div>
<a class="ib nt{{' on' if request.path.startswith('/notifications')}}" href=/notifications title="الإشعارات" aria-label="الإشعارات"><svg width=18 height=18 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2 stroke-linecap=round stroke-linejoin=round aria-hidden=true><path d="M18 8a6 6 0 10-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 01-3.4 0"/></svg>{% if unread %}<span class=bd>{{unread}}</span>{% endif %}</a>
<a class="ib tgs{{' on' if request.path.startswith('/settings')}}" href=/settings title="الإعدادات" aria-label="الإعدادات"><svg width=20 height=20 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2 stroke-linecap=round stroke-linejoin=round aria-hidden=true><path d="M12 15a3 3 0 100-6 3 3 0 000 6z"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 11-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 11-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 11-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 110-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 112.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 114 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 112.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 110 4h-.09a1.65 1.65 0 00-1.51 1z"/></svg></a>
</header>
{% endif %}<main>
{% set hd = ttl or PT.get(request.path) %}{% if hd and session.uid %}<div class=ph><h2>{{hd[0]}}</h2><p>{{hd[1]}}</p></div>{% endif %}{% block c %}{% endblock %}</main>{% if session.uid %}</div>{% endif %}</div>{% if session.uid %}<script>(function(){var last=null,box=document.getElementById('tc'),bell=document.querySelector('a.nt');
function ding(){try{var a=new (window.AudioContext||window.webkitAudioContext)(),o=a.createOscillator(),g=a.createGain();o.connect(g);g.connect(a.destination);o.frequency.value=880;g.gain.value=.05;o.start();o.stop(a.currentTime+.15)}catch(e){}}
function toast(m){if(!box)return;var d=document.createElement('div');d.className='toast '+(m.kind||'info');d.setAttribute('role','status');var t=document.createElement('div');t.className='tb';var b=document.createElement('b');b.textContent='🔔 إشعار جديد';var sp=document.createElement('span');sp.textContent=m.msg;t.appendChild(b);t.appendChild(sp);var x=document.createElement('button');x.className='x';x.textContent='×';x.onclick=function(){d.remove()};d.appendChild(t);d.appendChild(x);box.appendChild(d);setTimeout(function(){d.remove()},9000);
try{if('Notification' in window&&Notification.permission==='granted')new Notification('REPAIRIX',{body:m.msg})}catch(e){}}
function badge(n){if(!bell)return;var b=bell.querySelector('.bd');if(n>0){if(!b){b=document.createElement('span');b.className='bd';bell.appendChild(b)}b.textContent=n}else if(b)b.remove()}
function poll(){fetch('/notifications/poll?after='+(last===null?0:last),{credentials:'same-origin'}).then(function(r){return r.ok?r.json():null}).then(function(j){if(!j)return;
if(last!==null)j.new.slice().reverse().forEach(function(m){toast(m);ding()});last=j.max;badge(j.unread)}).catch(function(){})}
try{if('Notification' in window&&Notification.permission==='default')document.addEventListener('click',function f(){Notification.requestPermission();document.removeEventListener('click',f)})}catch(e){}
poll();setInterval(poll,12000)})();</script>{% endif %}<script>(function(){function norm(x){return (x||'').toLowerCase().replace(/[\u064B-\u065F]/g,'').replace(/[أإآ]/g,'ا').replace(/ى/g,'ي').replace(/ة/g,'ه')}
document.querySelectorAll('input[data-tsearch]').forEach(function(i){var t=document.getElementById(i.dataset.tsearch),c=document.querySelector('[data-tcount='+i.dataset.tsearch+']');if(!t)return;
i.addEventListener('input',function(){var v=norm(i.value.trim()),n=0,tot=0;t.querySelectorAll('tr').forEach(function(r){if(r.querySelector('th'))return;if(r.querySelector('td.em'))return;tot++;var ok=!v||norm(r.textContent).indexOf(v)>-1;r.style.display=ok?'':'none';if(ok)n++});
if(c)c.textContent=v?(n?n+' من '+tot+' قطعة':'ما في نتائج للبحث'):''})})})();</script><script>(function(){var c=document.getElementById('tclk'),d=document.getElementById('tdt');function t(){var n=new Date();if(c)c.textContent=n.toLocaleTimeString('ar-u-nu-latn',{hour:'2-digit',minute:'2-digit'});if(d)d.textContent=n.toLocaleDateString('ar-u-nu-latn',{weekday:'long',day:'numeric',month:'long'})}t();setInterval(t,20000);
document.addEventListener('click',function(e){var p=document.querySelector('.tpf[open]');if(p&&!p.contains(e.target))p.removeAttribute('open')});
document.addEventListener('keydown',function(e){if(e.key==='Escape'){var p=document.querySelector('.tpf[open]');if(p)p.removeAttribute('open')}})})();</script><script>(function(){var W=document.getElementById('fx');if(!W)return;
var S=null,T=null;function $(i){return document.getElementById(i)}
function f(n,d){return n==null||isNaN(n)?'—':Number(n).toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d})}
function ch(el,v){if(!el)return;el.className=v>0?'up':v<0?'dn':'';el.textContent=v>0?'▲':v<0?'▼':''}
function conv(){if(!S||!S.ok)return;var per={ILS:1,USD:S.usd_ils,JOD:S.jod_ils},nm={ILS:['₪','شيكل'],USD:['$','دولار'],JOD:['JD','دينار']};
var a=parseFloat($('fxa').value),fr=$('fxf').value,o=['ILS','USD','JOD'].filter(function(x){return x!==fr});
for(var i=0;i<2;i++){var t=o[i];$('fx-l'+(i+1)).textContent=nm[t][1];$('fx-o'+(i+1)).textContent=isNaN(a)?'—':f(a*per[fr]/per[t],t==='JOD'?3:2)+' '+nm[t][0]}}
function draw(){var ok=S&&S.ok;W.classList.remove('ld');
if(!ok){$('fx-usd').textContent=$('fx-jod').textContent='—';$('t-usd').textContent=$('t-jod').textContent=$('t-ujd').textContent='—';
var s=$('fx-src');s.textContent='غير متاح';s.className='fxs x';$('fx-time').textContent='تعذّر جلب الأسعار — تأكد من الإنترنت أو اكتب سعراً يدوياً من الإعدادات.';ch($('fx-usd-c'),0);ch($('fx-jod-c'),0);return}
$('fx-usd').textContent=f(S.usd_ils,2);$('fx-jod').textContent=f(S.jod_ils,2);
$('t-usd').textContent=f(S.usd_ils,3);$('t-jod').textContent=f(S.jod_ils,3);$('t-ujd').textContent=f(S.usd_jod,4);
ch($('fx-usd-c'),S.chg_usd);ch($('fx-jod-c'),S.chg_jod);
var s=$('fx-src'),m=S.man_usd||S.man_jod;s.textContent=m?(S.man_usd&&S.man_jod?'يدوي':'يدوي جزئياً'):(S.stale?'قديم':'تلقائي');s.className='fxs'+(m||S.stale?' m':'');
var d=S.ts?new Date(S.ts*1000):null;$('fx-time').textContent=(d?'آخر تحديث: '+d.toLocaleTimeString('ar-u-nu-latn',{hour:'2-digit',minute:'2-digit'}):'')+(S.stale?' · تعذّر التحديث، معروض آخر سعر محفوظ':'')+(m?' · الأسعار اليدوية من الإعدادات':'');conv()}
function load(force){var b=$('fx-rf');if(force&&b)b.classList.add('sp');
fetch('/api/rates'+(force?'?force=1':''),{credentials:'same-origin',headers:{'Accept':'application/json'}}).then(function(r){return r.json()}).then(function(d){S=d;T=Date.now();draw()}).catch(function(){if(!S)S={ok:false};draw()}).then(function(){if(b)setTimeout(function(){b.classList.remove('sp')},400)})}
$('fx-rf').addEventListener('click',function(e){e.preventDefault();e.stopPropagation();load(true)});
$('fxa').addEventListener('input',conv);$('fxf').addEventListener('change',conv);
document.addEventListener('click',function(e){if(W.open&&!W.contains(e.target))W.removeAttribute('open')});
document.addEventListener('keydown',function(e){if(e.key==='Escape')W.removeAttribute('open')});
document.addEventListener('visibilitychange',function(){if(!document.hidden&&(!T||Date.now()-T>600000))load(false)});
load(false);setInterval(function(){load(false)},900000)})();</script><script>(function(){function cv(td){if(!td)return'';var s=td.querySelector('select');return(td.dataset.v||(s?s.value:td.textContent)).trim()}
function rowsOf(t){return[].slice.call(t.rows).slice(1).filter(function(r){return!r.querySelector('td[colspan]')})}
function apply(t){var ctl=[].slice.call(document.querySelectorAll('[data-f="'+t.id+'"]'));rowsOf(t).forEach(function(r){var ok=true;ctl.forEach(function(c){var v=c.value.trim();if(!v)return;
if(c.dataset.role==='search'){var txt=[].map.call(r.cells,cv).join(' ').toLowerCase();if(txt.indexOf(v.toLowerCase())<0)ok=false}
else if(c.dataset.role==='from'){if(cv(r.cells[c.dataset.col])<v)ok=false}else if(c.dataset.role==='to'){if(cv(r.cells[c.dataset.col])>v)ok=false}
else if(c.dataset.attr){if(r.dataset[c.dataset.attr]!==v)ok=false}else if(c.dataset.col){if(cv(r.cells[c.dataset.col])!==v)ok=false}});r.style.display=ok?'':'none'})}
document.querySelectorAll('table.srt').forEach(function(t){var hs=t.rows[0].cells;[].forEach.call(hs,function(h,i){if(h.classList.contains('ns'))return;h.classList.add('sb');h.addEventListener('click',function(){var d=h.dataset.d==='a'?'d':'a';[].forEach.call(hs,function(x){delete x.dataset.d});h.dataset.d=d;var rs=rowsOf(t);
rs.sort(function(a,b){var x=cv(a.cells[i]),y=cv(b.cells[i]),c;if(/^\\d{4}-\\d{2}-\\d{2}/.test(x)||!/^-?[\\d.,]+\\s*₪?$/.test(x)||!/^-?[\\d.,]+\\s*₪?$/.test(y))c=x.localeCompare(y,'ar',{numeric:true});else c=parseFloat(x.replace(/,/g,''))-parseFloat(y.replace(/,/g,''));return d==='a'?c:-c});
var tb=rs[0].parentNode;rs.forEach(function(r){tb.appendChild(r)})})});
document.querySelectorAll('[data-f="'+t.id+'"]').forEach(function(c){if(c.dataset.role==='from'||c.dataset.role==='to'){c.addEventListener('keydown',function(e){if(e.key==='Enter'){e.preventDefault();apply(t)}});return}c.addEventListener('input',function(){apply(t)})});
document.querySelectorAll('[data-apply="'+t.id+'"]').forEach(function(b){b.addEventListener('click',function(){apply(t)})})})})();</script><script>document.addEventListener('click',function(e){var o=e.target.closest('[data-open]');if(o){var d=document.getElementById(o.dataset.open);var h3=d.querySelector('.dh h3');if(h3){if(!h3.dataset.t0)h3.dataset.t0=h3.textContent;h3.textContent=h3.dataset.t0}if(!o.dataset.fill){var fm=d.querySelector('form');if(fm)fm.reset()}if(o.dataset.fill){var m=JSON.parse(o.dataset.fill);if(m._t&&h3)h3.textContent=m._t;for(var k in m){if(k==='_t')continue;var el=d.querySelector('[name='+JSON.stringify(k)+']');if(el)el.value=m[k]}}d.showModal();var f=d.querySelector('input:not([type=hidden])');if(f)f.focus();return}var vb=e.target.closest('.vt button');if(vb){var w=document.getElementById('pwrap');w.dataset.v=vb.dataset.v;document.querySelectorAll('.vt button').forEach(function(x){x.classList.toggle('on',x===vb)});try{localStorage.setItem('pv',vb.dataset.v)}catch(_){}return}
var sw=e.target.closest('.swb');if(sw){var c=sw.closest('.mc');c.style.setProperty('--bk',sw.dataset.h);c.querySelectorAll('.swb').forEach(function(x){x.classList.toggle('on',x===sw)});c.querySelectorAll('.cp').forEach(function(p){p.hidden=p.dataset.i!==sw.dataset.i});return}
if(e.target.closest('[data-close]')){e.target.closest('dialog').close();return}if(e.target.tagName==='DIALOG')e.target.close()});
(function(){var w=document.getElementById('pwrap');if(w){try{var v=localStorage.getItem('pv');if(v){w.dataset.v=v;document.querySelectorAll('.vt button').forEach(function(x){x.classList.toggle('on',x.dataset.v===v)})}}catch(_){}}
var g=document.getElementById('pg');if(g){var cs=[].slice.call(document.querySelectorAll('[data-g="pg"]'));
var run=function(){var cards=[].slice.call(g.querySelectorAll('.pc')),shown=0;
cards.forEach(function(c){var ok=true;cs.forEach(function(x){var v=x.value.trim(),r=x.dataset.role;if(!v||r==='sort')return;if(r==='search'){if((c.dataset.s||'').toLowerCase().indexOf(v.toLowerCase())<0)ok=false}else if(c.dataset[r]!==v)ok=false});c.style.display=ok?'':'none';if(ok)shown++});
var so=cs.filter(function(x){return x.dataset.role==='sort'})[0],k='i',d=1;if(so&&so.value){k=so.value.split(':')[0];d=so.value.split(':')[1]==='d'?-1:1}
g.querySelectorAll('.pg').forEach(function(box){[].slice.call(box.children).sort(function(a,b){var x=a.dataset[k],y=b.dataset[k];return(k==='name'?x.localeCompare(y,'ar'):parseFloat(x)-parseFloat(y))*d}).forEach(function(c){box.appendChild(c)})});
g.querySelectorAll('.grp').forEach(function(sc){sc.style.display=[].some.call(sc.querySelectorAll('.pc'),function(c){return c.style.display!=='none'})?'':'none'});
var nr=document.getElementById('nores');if(nr)nr.hidden=shown>0||!cards.length};
cs.forEach(function(x){x.addEventListener('input',run)})}
var bs=document.getElementById('bsearch');if(bs)bs.addEventListener('input',function(){var v=bs.value.toLowerCase();document.querySelectorAll('.mc').forEach(function(c){c.style.display=(c.dataset.s||'').toLowerCase().indexOf(v)<0?'none':''})})})();
if(/[?&]new=1/.test(location.search)){var a=document.querySelector('dialog[data-auto]');if(a){a.showModal();history.replaceState(null,'',location.pathname)}}</script><script>document.addEventListener('click',function(e){var p=e.target.closest('.cpill');if(p){document.querySelectorAll('.cpill').forEach(function(x){x.classList.toggle('on',x===p)});var sl=document.querySelector('select[data-role=cat]');if(sl){sl.value=p.dataset.cat;sl.dispatchEvent(new Event('input',{bubbles:true}))}return}
var ey=e.target.closest('.eye');if(ey){var i=ey.parentNode.querySelector('input');i.type=i.type==='password'?'text':'password';ey.classList.toggle('on')}});</script></html>""",
"index": """{% extends 'base' %}{% block c %}
<div class=hb><div><h2>أهلاً بك في {{shop}}</h2><p>{{dt}} · ملخص سريع لحال الشركة اليوم</p>
<div class=bt><a class=btn href="/repairs?new=1">+ صيانة جديدة</a><a class="btn o" href="/parts?new=1">+ إضافة قطعة</a></div></div></div>
{% if trial.state=='active' %}<div class=tb7><span class=ring style="--p:{{trial.pct}}"><b>{{trial.left}}</b></span><div><h3>الفترة التجريبية فعّالة <span class=tbd>تجريبي</span></h3><p>متبقي {{trial.left}} من 7 أيام · تنتهي بتاريخ {{trial.end}}</p></div></div>
{% elif trial.state=='paid' %}<div class=tb7 style="border-right-color:#059669"><span class=ring style="--p:{{trial.pct}}"><b>{{trial.left}}</b></span><div><h3>اشتراكك فعّال <span class=tbd style="background:#e7f8ef;color:#047857">مشترك</span></h3><p>متبقي {{trial.left}} يوم · ينتهي بتاريخ {{trial.end}}</p></div></div>
{% elif trial.state=='ended' %}<div class="tb7 end"><span class=ring style="--p:100"><b>0</b></span><div><h3>انتهت الفترة التجريبية</h3><p>انتهت التجربة بتاريخ {{trial.end}}. تواصل معنا لتفعيل النسخة الكاملة.</p></div></div>{% endif %}
<div class="sg4 sg3">
<div class=sc><span class="si f"><svg width=24 height=24 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=1.9 stroke-linecap=round stroke-linejoin=round><path d="M2 6h20v12H2zM12 15a3 3 0 100-6 3 3 0 000 6zM6 12h.01M18 12h.01"/></svg></span><div><small>الدخل اليومي</small><b>{{ '%g'|format(income) }} ₪</b></div></div>
<div class=sc><span class="si g"><svg width=24 height=24 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=1.9 stroke-linecap=round stroke-linejoin=round><path d="M3 17l6-6 4 4 8-8M15 7h6v6"/></svg></span><div><small>المربح اليومي</small><b>{{ '%g'|format(today) }} ₪</b></div></div>
<div class=sc><span class="si a"><svg width=24 height=24 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=1.9 stroke-linecap=round stroke-linejoin=round><path d="M3 17l6-6 4 4 8-8M15 7h6v6"/></svg></span><div><small>مربح الشهر</small><b>{{ '%g'|format(month) }} ₪</b></div></div>
<div class=sc><span class="si b"><svg width=24 height=24 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=1.9 stroke-linecap=round stroke-linejoin=round><path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z"/></svg></span><div><small>قيد الصيانة</small><b>{{open_n}}</b></div></div>
<div class=sc><span class="si c"><svg width=24 height=24 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=1.9 stroke-linecap=round stroke-linejoin=round><path d="M5 12.5l4.5 4.5L19 7.5"/></svg></span><div><small>جاهزة للتسليم</small><b>{{ready_n}}</b></div></div>
<div class=sc><span class="si {{'d' if low else 'e'}}"><svg width=24 height=24 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=1.9 stroke-linecap=round stroke-linejoin=round><path d="M12 3l10 18H2zM12 10v5M12 18h.01"/></svg></span><div><small>قطع ناقصة</small><b class="{{'low' if low}}">{{low|length}}</b></div></div></div>
<div class=g2><div class=card><div class=ch><h3>المربح اليومي</h3><small>آخر 14 يوم</small></div>
{% for d in days %}<div class=bar><span>{{d.done_date}}</span><div class=tr><i style="width:{{ ([d.p,0]|max / mx * 100)|round|int }}%"></i></div><b>{{ '%g'|format(d.p) }} ₪</b></div>
{% else %}<div class=em>ما في صيانات مسلّمة بعد. سجّل صيانة وغيّر حالتها إلى "تم التسليم".</div>{% endfor %}</div>
<div class=card><div class=ch><h3>قطع قربت تخلص</h3>{% if low %}<a href=/parts>المخزون</a>{% endif %}</div>
{% for p in low %}<div class=lw><span>{{p.name}}</span><span class="tag bad">{{p.qty}}</span></div>{% else %}<div class=em>كل القطع بكميات كافية ✓</div>{% endfor %}</div></div>
<div class=card><div class=ch><h3>آخر الصيانات</h3><a href=/repairs>عرض الكل</a></div>
<table><tr><th>التاريخ<th>الزبون<th>الجهاز<th>العطل<th>السعر<th>الحالة</tr>
{% for r in recent %}<tr><td>{{r.created}}<td>{{r.customer}}<td>{{r.device}}<td>{{r.issue}}<td>{{ '%g'|format(r.price) }} ₪<td><span class="pill {{ {'قيد الصيانة':'s0','جاهز':'s1','تم التسليم':'s2'}[r.status] }}">{{r.status}}</span></tr>
{% else %}<tr><td colspan=6 class=em>لا يوجد صيانات بعد.</tr>{% endfor %}</table></div>{% endblock %}""",
"parts": """{% extends 'base' %}{% block c %}
<div class=sg4><div class=sc><span class="si a"><svg width=24 height=24 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=1.9 stroke-linecap=round stroke-linejoin=round><path d="M21 8l-9-5-9 5v8l9 5 9-5zM3 8l9 5 9-5M12 13v8"/></svg></span><div><small>عدد القطع</small><b>{{st.n}}</b></div></div><div class=sc><span class="si b"><svg width=24 height=24 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=1.9 stroke-linecap=round stroke-linejoin=round><path d="M2 6h20v12H2zM12 15a3 3 0 100-6 3 3 0 000 6z"/></svg></span><div><small>قيمة المخزون (جملة)</small><b>{{ '%g'|format(st.val) }} ₪</b></div></div><div class=sc><span class="si f"><svg width=24 height=24 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=1.9 stroke-linecap=round stroke-linejoin=round><path d="M3 17l6-6 4 4 8-8M15 7h6v6"/></svg></span><div><small>قيمة البيع المتوقعة</small><b>{{ '%g'|format(st.sell) }} ₪</b></div></div><div class=sc><span class="si {{'d' if st.low else 'e'}}"><svg width=24 height=24 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=1.9 stroke-linecap=round stroke-linejoin=round><path d="M12 3l10 18H2zM12 10v5M12 18h.01"/></svg></span><div><small>قطع ناقصة</small><b><span class="{{'low' if st.low}}">{{st.low}}</span></b></div></div></div>
{% if not cat %}<div class=cats><button type=button class="cpill on" data-cat="">كل القطع <em>{{total}}</em></button>
{% for c in catlist %}<button type=button class=cpill data-cat="{{c}}">{{cic[c]}}{{cplural[c]}} <em>{{cnt[c]}}</em></button>{% endfor %}</div>{% endif %}
<div class=tools><div class=r1><label class=search>{{ic.sr}}<input data-f=ptbl data-g=pg data-role=search placeholder="ابحث بالاسم أو اللون أو المورد..."></label><div class=vt><button type=button class=on data-v=g title="عرض بطاقات"><svg width=18 height=18 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=1.9 stroke-linecap=round stroke-linejoin=round><path d="M3 3h7v7H3zM14 3h7v7h-7zM14 14h7v7h-7zM3 14h7v7H3z"/></svg></button><button type=button data-v=t title="عرض جدول"><svg width=18 height=18 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=1.9 stroke-linecap=round stroke-linejoin=round><path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/></svg></button></div>
<a class="btn ghost" href=/parts/import>📥 استيراد من Excel</a><button type=button data-open=dlg-part>+ إضافة قطعة</button></div>
<div class=r2>{% if not cat %}<select hidden data-f=ptbl data-g=pg data-role=cat data-col=2><option value="">كل الأنواع{% for c in catlist %}<option>{{c}}{% endfor %}</select>{% endif %}
<select data-f=ptbl data-g=pg data-role=brand data-col=3 aria-label="نوع الجهاز"><option value="">كل الأجهزة{% for b in brands %}<option>{{b}}{% endfor %}</select>
<select data-f=ptbl data-g=pg data-role=sup data-col=8 aria-label="المورد"><option value="">كل الموردين{% for s in sup %}<option>{{s.name}}{% endfor %}</select>
<select data-f=ptbl data-g=pg data-role=low data-attr=low aria-label="الكمية"><option value="">كل الكميات<option value=1>الناقصة فقط</select>
<select data-g=pg data-role=sort aria-label="الترتيب"><option value="">ترتيب: الافتراضي<option value="name:a">الاسم (أ ← ي)<option value="qty:a">الكمية: الأقل أولاً<option value="qty:d">الكمية: الأكثر أولاً<option value="price:d">سعر البيع: الأعلى<option value="price:a">سعر البيع: الأقل<option value="profit:d">الربح: الأعلى</select></div></div>
<dialog class=dlg id=dlg-part data-auto><form method=post enctype=multipart/form-data>
<div class=dh><h3>إضافة قطعة جديدة</h3><button type=button class=cl data-close aria-label="إغلاق">×</button></div>
<div class=db><div class=fg>
<label class=fa>اسم القطعة<input name=name required placeholder="مثال: شاشة Samsung A12"></label>
<label class=fa id=ad-mk hidden>الشركة المصنعة (اختياري)<input name=maker list=mklist maxlength=60 placeholder="مثال: أصلية، OEM، JK، GX، Incell..."></label><datalist id=mklist>{% for m in makers %}<option value="{{m}}">{% endfor %}</datalist><style>label[hidden]{display:none!important}.mk{display:inline-block;margin-inline-start:6px;padding:1px 9px;border-radius:99px;background:#eef2ff;color:#4338ca;font-size:11.5px;font-weight:700;vertical-align:middle}</style>
<label>سعر الجملة<input name=cost type=number step=any min=0 required></label><label>سعر البيع<input name=price type=number step=any min=0 required></label>
<label class=fa>الكمية<input name=qty type=number min=0 required></label></div>
<details class=more><summary>خيارات إضافية</summary><div class=fg>
<label>النوع<select name=category>{% for c in cats %}<option {{'selected' if c==cat}}>{{c}}{% endfor %}</select></label><label>حد التنبيه<input name=min_qty type=number value=2></label>
<label>الباركود (بيتولّد كود عشوائي تلقائياً)<input name=barcode dir=ltr inputmode=numeric autocomplete=off placeholder="اتركه فاضي لكود عشوائي، أو امسحه بالقارئ"></label>
<label class=fa style="display:flex;gap:10px;align-items:center;flex-wrap:wrap"><span style="display:flex;gap:6px;align-items:center"><input type=checkbox name=print_label value=1 style="width:auto;margin:0"> اطبع ملصق الباركود بعد الحفظ</span><select name=label_size style="width:auto;margin:0"><option value=50x30>رول 50×30<option value=40x25>رول 40×25<option value=a4>A4</select><input name=label_copies type=number min=1 max=100 value=1 title="عدد النسخ" style="width:70px;margin:0"></label>
<label>المورد<select name=supplier_id><option value="">بدون{% for s in sup %}<option value={{s.id}}>{{s.name}}{% endfor %}</select></label>
<label>صورة (اختياري)<input name=photo type=file accept="image/*"></label></div></details></div>
<div class=df><button>حفظ القطعة</button><button type=button class=ghost data-close>إلغاء</button></div></form></dialog>
{% include 'pedit' %}
<script>(function(){var s=document.querySelector('#dlg-part [name=category]'),l=document.getElementById('ad-mk');if(!s||!l)return;function t(){l.hidden=!(s.value=='شاشة'||s.value=='بطارية')}s.addEventListener('change',t);t()})()</script>
<div id=pwrap data-v=g>
{% if not parts %}<div class="card em">ما في قطع هون لسا. اضغط "إضافة قطعة" لإضافة أول قطعة.</div>{% endif %}
<div class=gv id=pg>
{% for g in groups %}<section class=grp><div class=gh><span class="gi k{{g.k}}">{{g.icon}}</span><h3>{{g.title}}</h3><span class=gc>{{g.rows|length}} صنف · {{g.qty}} قطعة</span></div><div class=pg>
{% for p in g.rows %}{% set lo = p.qty<=p.min_qty %}{% set pct = [100,(p.qty/([p.min_qty*3,1]|max)*100)|round|int]|min %}
<div class=pc data-s="{{p.name}} {{p.maker or ''}} {{p.color or ''}} {{p.category}} {{p.brand}} {{p.sname or ''}} {{p.barcode or ''}}" data-i="{{p.i}}" data-name="{{p.name}}" data-qty="{{p.qty}}" data-price="{{p.price}}" data-profit="{{p.price-p.cost}}" data-low="{{1 if lo else 0}}" data-sup="{{p.sname or '-'}}" data-cat="{{p.category}}" data-brand="{{p.brand}}">
<div class="pm k{{kc.get(p.category,5)}}">{% if p.photo %}<img src=/photo/{{p.photo}} alt="">{% else %}{{cic.get(p.category,cic['أخرى'])}}{% endif %}<span class=cb>{{p.category}}</span><span class="pill ss {{'s3' if p.qty==0 else 's0' if lo else 's2'}}">{{'نفد' if p.qty==0 else 'منخفض' if lo else 'متوفر'}}</span></div>
<div class=pb><div class=pn>{% if p.hex %}<span class=dot style="background:{{p.hex}}"></span>{% endif %}<span>{{p.name}}{{ ' · '+p.color if p.color }}{% if p.maker %}<em class=mk style="font-style:normal">{{p.maker}}</em>{% endif %}</span></div><div class=ps>{{ p.brand ~ ' · ' if p.brand != 'أخرى' }}{{p.sname or 'بدون مورد'}}</div><div class=bcc><a href=# onclick="rxBc({{p.id}},'{{p.barcode or ''}}');return false" title="تعديل الباركود"><svg viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2 stroke-linecap=round><path d="M3 5v14M7 5v14M11 5v14M14 5v14M18 5v14M21 5v14"/></svg>{{p.barcode or '—'}}</a><a href="/barcodes?ids={{p.id}}" title="طباعة ملصق باركود">🖨</a></div>
<div class=pr3><div><small>الجملة</small><b>{{ '%g'|format(p.cost) }} ₪</b></div><div><small>البيع</small><b>{{ '%g'|format(p.price) }} ₪</b></div><div class=g><small>الربح</small><b>{{ '%g'|format(p.price-p.cost) }} ₪</b></div></div>
<div><div class=qb><span>الكمية</span><b class="{{'low' if lo}}">{{p.qty}}</b></div><div class=qt><i class="{{'r' if p.qty==0 else 'w' if lo}}" style="width:{{pct}}%"></i></div></div></div>
<div class=pf><form method=post action=/parts/{{p.id}}/stock><input name=n type=number value=1 class=sm><button>+ مخزون</button></form>
<label class=ib title="رفع صورة" style="cursor:pointer">{{ic.im}}<input type=file name=photo accept="image/*" hidden form=ph{{p.id}} onchange="this.form.submit()"></label>
<button type=button class="ib ed" title="تعديل" aria-label="تعديل" data-open=dlg-pedit data-fill='{{ {"_t":"تعديل: "~p.name,"_id":p.id,"_back":(1 if p.category=="ظهر" else 0),"name":p.name,"cost":p.cost,"price":p.price,"qty":p.qty,"min_qty":p.min_qty,"supplier_id":p.supplier_id or "","category":p.category,"color":p.color or "","hex":p.hex or "#888888","maker":p.maker or ""}|tojson }}'>{{ic.ed}}</button><a class="ib dl" title="حذف" href=/parts/{{p.id}}/delete onclick="return confirm('حذف؟')">{{ic.dl}}</a></div>
<form id=ph{{p.id}} method=post action=/parts/{{p.id}}/photo enctype=multipart/form-data hidden></form></div>
{% endfor %}</div></section>{% endfor %}
<div class="card em" id=nores hidden>ما في نتائج مطابقة للبحث أو الفلتر.</div></div>
<div class="card tv"><table class=srt id=ptbl><tr><th class=ns><th>القطعة<th>النوع<th>الجهاز<th>الكمية<th>سعر الجملة<th>سعر البيع<th>الربح<th>المورد<th class=ns></tr>
{% for p in parts %}<tr data-low="{{1 if p.qty<=p.min_qty else 0}}"><td>{% if p.photo %}<a href=/photo/{{p.photo}} target=_blank><img class=th src=/photo/{{p.photo}} alt=""></a>{% else %}<span class=th></span>{% endif %}
<td><b>{{p.name}}{{ ' · '+p.color if p.color }}</b>{% if p.maker %}<em class=mk style="font-style:normal">{{p.maker}}</em>{% endif %}<div class=bcc><a href=# onclick="rxBc({{p.id}},'{{p.barcode or ''}}');return false" title="تعديل الباركود"><svg viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2 stroke-linecap=round><path d="M3 5v14M7 5v14M11 5v14M14 5v14M18 5v14M21 5v14"/></svg>{{p.barcode or '—'}}</a><a href="/barcodes?ids={{p.id}}" title="طباعة ملصق باركود">🖨</a></div><td>{{p.category}}<td>{{p.brand}}<td><span class="tag {{'bad' if p.qty<=p.min_qty}}">{{p.qty}}</span><td class=nw>{{ '%g'|format(p.cost) }} ₪<td class=nw>{{ '%g'|format(p.price) }} ₪<td class=nw>{{ '%g'|format(p.price-p.cost) }} ₪<td>{{p.sname or '-'}}
<td><div class=ac><form method=post action=/parts/{{p.id}}/stock class=il><input name=n type=number value=1 class=sm><button>+ مخزون</button></form>
<button type=button class="ib ed" title="تعديل" aria-label="تعديل" data-open=dlg-pedit data-fill='{{ {"_t":"تعديل: "~p.name,"_id":p.id,"_back":(1 if p.category=="ظهر" else 0),"name":p.name,"cost":p.cost,"price":p.price,"qty":p.qty,"min_qty":p.min_qty,"supplier_id":p.supplier_id or "","category":p.category,"color":p.color or "","hex":p.hex or "#888888","maker":p.maker or ""}|tojson }}'>{{ic.ed}}</button><a class="ib dl" title="حذف" href=/parts/{{p.id}}/delete onclick="return confirm('حذف؟')">{{ic.dl}}</a></div></tr>
{% else %}<tr><td colspan=10 class=em>لا يوجد.</tr>{% endfor %}</table></div></div>{% endblock %}""",
"suppliers": "",
"repairs": """{% extends 'base' %}{% block c %}
<div class=sg4>
<div class=sc><span class="si f"><svg width=24 height=24 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=1.9 stroke-linecap=round stroke-linejoin=round><path d="M2 6h20v12H2zM12 15a3 3 0 100-6 3 3 0 000 6zM6 12h.01M18 12h.01"/></svg></span><div><small>{{lab_inc}}</small><b>{{ '%g'|format(tot.inc) }} ₪</b></div></div>
<div class=sc><span class="si g"><svg width=24 height=24 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=1.9 stroke-linecap=round stroke-linejoin=round><path d="M3 17l6-6 4 4 8-8M15 7h6v6"/></svg></span><div><small>{{lab_prof}}</small><b>{{ '%g'|format(tot.inc - tot.c) }} ₪</b></div></div>
<div class=sc><span class="si e"><svg width=24 height=24 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=1.9 stroke-linecap=round stroke-linejoin=round><path d="M21 8l-9-5-9 5v8l9 5 9-5zM3 8l9 5 9-5M12 13v8"/></svg></span><div><small>مجموع الجملة <em style="font-style:normal">(للشركة فقط)</em></small><b>{{ '%g'|format(tot.c) }} ₪</b></div></div>
<div class=sc><span class="si b"><svg width=24 height=24 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=1.9 stroke-linecap=round stroke-linejoin=round><path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z"/></svg></span><div><small>عدد الصيانات</small><b>{{tot.n}}</b></div></div></div>
{% if split %}<div class='card ptsc'><h3>تقسيم المربح على الأطراف</h3><small>{{lab_prof}}</small><div class=ptsg>{% for p in split %}<div class=pts><small>{{p.name}} · {{ '%g'|format(p.pct) }}%</small><b>{{ '%g'|format(p.amt) }} ₪</b></div>{% endfor %}</div></div>
<style>.ptsc{margin:0 0 14px}.ptsg{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin-top:6px}.pts{border:1px solid var(--line);border-radius:14px;padding:10px 14px;display:flex;flex-direction:column;gap:2px}.pts small{color:var(--mut)}.pts b{font-size:20px}.shr{color:var(--mut)}</style>{% endif %}
<div class=tools><div class=r1><label class=search>{{ic.sr}}<input data-f=rtbl data-role=search placeholder="بحث بالصفحة: اسم، هاتف، جهاز، عطل..."></label><button type=button data-open=dlg-rep>+ تسجيل صيانة</button></div>
<div class=r2><select data-f=rtbl data-col=8><option value="">كل الحالات{% for s in st %}<option>{{s}}{% endfor %}</select>
<span class=qd><a class="qb{{' on' if mode=='today'}}" href=/repairs>اليوم</a><a class="qb{{' on' if mode=='yday'}}" href="/repairs?from={{yday}}&to={{yday}}">أمس</a><a class="qb{{' on' if mode=='7'}}" href="/repairs?from={{d7}}&to={{today}}">آخر 7 أيام</a><a class="qb{{' on' if mode=='month'}}" href="/repairs?from={{m1}}&to={{today}}">هذا الشهر</a><a class="qb op{{' on' if mode=='open'}}" href="/repairs?open=1" title="كل الأجهزة اللي لسا قيد الصيانة بأي تاريخ">قيد الصيانة{% if n_open %} <i>{{n_open}}</i>{% endif %}</a></span>
<form class=dr method=get action=/repairs><span class=lb>من</span><input type=date name=from value="{{d1}}" max="{{today}}"><span class=lb>إلى</span><input type=date name=to value="{{d2}}" max="{{today}}">
<button class=ib2 title="عرض" aria-label="عرض">{{ic.sr}}</button><span class=sep></span>
<button type=button class="ib2 xl" id=xl title="تصدير كشف الدخل والمربح لكل يوم (Excel) للفترة المعروضة" aria-label="تصدير Excel"><svg viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2 stroke-linecap=round stroke-linejoin=round><path d="M12 3v12M7 11l5 5 5-5M4 21h16"/></svg></button></form></div></div>
<style>.qd{display:inline-flex;gap:6px;flex-wrap:wrap}.qb{padding:8px 15px;border-radius:99px;background:#eef1fa;color:var(--ink)!important;font-weight:600;font-size:13.5px;text-decoration:none!important;transition:.15s;white-space:nowrap}.qb:hover{background:#e0e6f8}.qb.on{background:linear-gradient(135deg,var(--br),var(--br2));color:#fff!important;box-shadow:0 8px 16px -10px var(--br)}.qb i{font-style:normal;background:#f59e0b;color:#fff;border-radius:99px;padding:1px 7px;font-size:12px;margin-right:4px}.dtl{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:2px 4px 12px}.dtl b{font-size:16.5px}.dtl span{color:var(--mut);font-size:13px}.dtl .nv{margin-right:auto;display:flex;gap:6px}.dtl .nv a{padding:6px 12px;border-radius:10px;background:#eef1fa;font-size:13px;font-weight:600;color:var(--ink)}.dtl .nv a:hover{background:#e0e6f8;text-decoration:none}</style>
<script>(function(){var b=document.getElementById('xl');if(!b)return;b.addEventListener('click',function(){var f=document.querySelector('input[name=from]').value,t=document.querySelector('input[name=to]').value;
if(!f||!t){alert('اختر تاريخ من وتاريخ إلى أولاً ثم اضغط تصدير');return}location.href='/repairs/export?from='+f+'&to='+t})})();</script>
<dialog class=dlg id=dlg-rep data-auto><form method=post>
<div class=dh><h3>تسجيل صيانة جديدة</h3><button type=button class=cl data-close aria-label="إغلاق">×</button></div>
<div class=db><div class=fg><label class=fa>تاريخ الصيانة<input type=date name=created id=rdate value="{{today}}" max="{{today}}" required></label>
<label>اسم الزبون<input name=customer required></label><label>الهاتف<input name=phone></label>
<label>الجهاز<input name=device required></label><label>سعر البيع للزبون <small>(بيتعبّى من القطع)</small><input name=price id=rpr type=number step=any min=0 required></label>
<label>التكلفة (الجملة) <small>(للشركة فقط · بتتعبّى من القطع)</small><input name=cost id=rco type=number step=any min=0 placeholder="0"></label>
<label class=fa>العطل / المطلوب<input name=issue required></label></div>
<div class=psb><div class=pslb>القطع المستخدمة <small>(ابحث واختر قطعة أو أكثر)</small></div>
<label class="search psi">{{ic.sr}}<input id=psq type=search autocomplete=off placeholder="ابحث عن قطعة: شاشة، بطارية، iPhone 11، Samsung..."></label>
<div id=psr class=psr hidden></div><div id=pssel class=pssel></div>
<script id=pdata type=application/json>{{ plist|tojson }}</script>
<script>(function(){var d=JSON.parse(document.getElementById('pdata').textContent),q=document.getElementById('psq'),r=document.getElementById('psr'),sel=document.getElementById('pssel'),ch={};
function norm(x){return(x||'').toLowerCase()}
function show(){var v=norm(q.value).trim();r.innerHTML='';if(!v){r.hidden=true;return}
var ws=v.split(' ').filter(Boolean),L=d.filter(function(p){if(ch[p.id])return false;var t=norm(p.n+' '+p.c);return ws.every(function(w){return t.indexOf(w)>=0})}).slice(0,8);
if(!L.length){r.innerHTML='<div class=psn>ما في قطعة مطابقة</div>';r.hidden=false;return}
L.forEach(function(p){var b=document.createElement('button');b.type='button';b.className='psit';b.dataset.id=p.id;b.innerHTML='<span></span><em></em>';b.firstChild.textContent=p.n;b.lastChild.textContent=p.c+' · متوفر '+p.q;r.appendChild(b)});r.hidden=false}
function num(v){v=parseFloat(v);return isNaN(v)?0:v}
function tot(){var f=q.form,c=0,p=0,rows=sel.querySelectorAll('.pkr');if(!rows.length)return;rows.forEach(function(r){c+=num(r.querySelector('[name=part_cost]').value);p+=num(r.querySelector('[name=part_price]').value)});
f.elements.cost.value=Math.round(c*100)/100;f.elements.price.value=Math.round(p*100)/100}
function fld(lbl,nm,v){var l=document.createElement('label'),i=document.createElement('input');l.appendChild(document.createTextNode(lbl));i.type='number';i.name=nm;i.step='any';i.min='0';i.value=v;i.inputMode='decimal';i.addEventListener('input',tot);l.appendChild(i);return l}
function add(id){var p=d.filter(function(x){return String(x.id)===String(id)})[0];if(!p||ch[p.id])return;ch[p.id]=1;
var l=document.createElement('div');l.className='pkr';var n=document.createElement('b');n.textContent=p.n;l.appendChild(n);var h=document.createElement('input');h.type='hidden';h.name='part_id';h.value=p.id;l.appendChild(h);
l.appendChild(fld('جملة ₪','part_cost',p.cost||0));l.appendChild(fld('بيع ₪','part_price',p.price||0));
var x=document.createElement('button');x.type='button';x.className='prm';x.setAttribute('aria-label','إزالة');x.textContent='×';x.onclick=function(){delete ch[p.id];l.remove();tot()};l.appendChild(x);sel.appendChild(l);tot();q.value='';show();q.focus()}
q.addEventListener('input',show);q.addEventListener('keydown',function(e){if(e.key==='Enter'){e.preventDefault();var f=r.querySelector('.psit');if(f)add(f.dataset.id)}});
r.addEventListener('click',function(e){var b=e.target.closest('.psit');if(b)add(b.dataset.id)})})();</script></div></div>
<div class=df><button>تسجيل الصيانة</button><button type=button class=ghost data-close>إلغاء</button></div></form></dialog>
<dialog class=dlg id=dlg-rr><form method=post id=rrf><div class=dh><h3>مرتجع قطعة من الصيانة <span id=rrid></span></h3><button type=button class=cl data-close aria-label='إغلاق'>×</button></div>
<div class=db><div class=fg><label class=fa>القطعة المركّبة اللي بدك ترجعها<select name=rp_id id=rrp required></select></label>
<label>سبب المرتجع<select name=reason>{% for x in reasons %}<option>{{x}}</option>{% endfor %}</select></label><label>ملاحظة<input name=note></label>
<label class=fa>قطعة بديلة من المخزون <small>(اختياري: بتنخصم من الكمية وبتتركب بنفس الصيانة)</small><select name=new_part_id><option value=''>بدون قطعة بديلة</option>{% for p in plist %}<option value='{{p.id}}'>{{p.n}} · متوفر {{p.q}}</option>{% endfor %}</select></label></div>
<p class=hint style='color:var(--mut);font-size:13px;margin:10px 0 0'>القطعة المرتجعة بتنسجّل بصفحة «البضاعة المرتجعة» وبتنتسب لمورّدها. ما بتنخصم من المخزون مرة تانية لأنها انخصمت وقت التركيب، وتكلفتها بتنشال من تكلفة الصيانة.</p></div>
<div class=df><button>تسجيل المرتجع</button><button type=button class=ghost data-close>إلغاء</button></div></form></dialog>
<script>(function(){var f=document.getElementById('rrf'),sel=document.getElementById('rrp'),idl=document.getElementById('rrid');if(!f)return;document.addEventListener('click',function(e){var b=e.target.closest&&e.target.closest('.rrb');if(!b)return;var L=[];try{L=JSON.parse(b.getAttribute('data-rps')||'[]')}catch(x){}f.action='/repairs/'+b.getAttribute('data-id')+'/return';idl.textContent='#'+b.getAttribute('data-id');sel.innerHTML='';L.forEach(function(z){var o=document.createElement('option');o.value=z.id;o.textContent=z.n+' — '+z.c+' ₪';sel.appendChild(o)})})})();</script>
<div class=dtl><b>{{rtitle}}</b><span>{{tot.n}} صيانة{% if mode!='open' %} · {{tot.nd}} تم تسليمها{% endif %}</span>{% if prev %}<span class=nv><a href="/repairs?from={{prev}}&to={{prev}}">‹ اليوم السابق</a>{% if nxt %}<a href="{{'/repairs' if nxt==today else '/repairs?from='+nxt+'&to='+nxt}}">اليوم التالي ›</a>{% endif %}</span>{% endif %}</div>
<div class=card><table class=srt id=rtbl><tr><th>#<th>التاريخ<th>الزبون<th>الجهاز<th>العطل<th>القطع<th>سعر البيع<th>التكلفة (الجملة)<th>الحالة<th class=ns></tr>
{% for r in rows %}<tr><td class=nw>{{r.id}}<td class=nw>{% if r.status==st[2] %}{{r.done_date or r.created}}{% if r.done_date and r.done_date!=r.created %}<br><small>سُجّل {{r.created}}</small>{% endif %}{% else %}{{r.created}}{% endif %}<td><b>{{r.customer}}</b><br><small>{{r.phone}}</small><td>{{r.device}}<td>{{r.issue}}<td>{{r.pn or '-'}}<td class=nw data-v="{{r.price}}"><b>{{ '%g'|format(r.price) }} ₪</b><br><small>{% if r.status==st[2] or mode=='open' %}ربح {{ '%g'|format(r.price - r.cost) }} ₪{% else %}يُحسب عند التسليم{% endif %}</small>{% if r.sh %}<br><small class=shr>{{r.sh}}</small>{% endif %}
<td class=nw data-v="{{r.cost}}">{{ '%g'|format(r.cost) }} ₪
<td data-v="{{r.status}}"><form method=post action=/repairs/{{r.id}}/status><select name=status onchange=this.form.submit()>
{% for s in st %}<option {{'selected' if s==r.status}}>{{s}}{% endfor %}</select></form>
<td class=nw><a class=ib title="طباعة" href=/repairs/{{r.id}}/print target=_blank>{{ic.pr}}</a><a class=ib title="تعديل" href=/repairs/{{r.id}}/edit>{{ic.ed}}</a>{% if r.rps %}<button type=button class='ib rrb' title='مرتجع' aria-label='مرتجع' data-open=dlg-rr data-id='{{r.id}}' data-rps='{{r.rps|tojson}}'><svg viewBox='0 0 24 24' width=18 height=18 fill=none stroke=currentColor stroke-width=2 stroke-linecap=round stroke-linejoin=round><path d='M9 14L4 9l5-5'/><path d='M4 9h10a6 6 0 010 12h-3'/></svg></button>{% endif %}<a class="ib dl" title="حذف" href=/repairs/{{r.id}}/delete onclick="return confirm('حذف؟ القطع بترجع للمخزون')">{{ic.dl}}</a></tr>
{% else %}<tr><td colspan=10 class=em>{{ 'ما في أجهزة قيد الصيانة.' if mode=='open' else 'ما في صيانات مسجّلة بهالتاريخ.' }}</tr>{% endfor %}</table></div>{% endblock %}""",
"edit": """{% extends 'base' %}{% block c %}<div class=card><h3>تعديل صيانة</h3><form method=post><div class=fg><label class=fa>تاريخ الصيانة<input type=date name=created value="{{r.created}}" max="{{today}}" required></label>
{% if r.status=='تم التسليم' %}<label class=fa>تاريخ التسليم <small>(على هالتاريخ بينحسب الدخل والمربح)</small><input type=date name=done_date value="{{r.done_date or r.created}}" max="{{today}}"></label>{% endif %}
<label>اسم الزبون<input name=customer value="{{r.customer}}" required></label><label>الهاتف<input name=phone value="{{r.phone}}"></label><label>الجهاز<input name=device value="{{r.device}}" required></label>
<label>سعر البيع للزبون<input name=price type=number step=any min=0 value={{r.price}} required></label><label>التكلفة (الجملة) <small>(للشركة فقط)</small><input name=cost type=number step=any min=0 value={{r.cost}}></label><label class=fa>العطل<input name=issue value="{{r.issue}}" required></label></div>
<p><button>حفظ</button> <a class="btn ghost" href=/repairs>رجوع</a></p></form></div>
<div class=card style='margin-top:16px'><h3>القطع المركّبة بهالصيانة</h3>
{% for z in rps %}<div class=erp><span>{{z.n}} — <b>{{ '%g'|format(z.c) }} ₪</b></span><form method=post action=/repairs/{{r.id}}/unpart/{{z.id}} onsubmit="return confirm('إزالة القطعة وإرجاعها للمخزون؟')"><button class=ghost>إزالة وإرجاع للمخزون</button></form></div>{% else %}<small>ما في قطع مركّبة.</small>{% endfor %}
<form method=post action=/repairs/{{r.id}}/addpart><div class=fg><label class=fa>إضافة قطعة <small>(بتنخصم من المخزون وبتنضاف لتكلفة الصيانة)</small><select name=part_id required><option value=''>— اختر قطعة —</option>{% for p in plist %}<option value='{{p.id}}'>{{p.n}} · متوفر {{p.q}}</option>{% endfor %}</select></label></div><p><button>إضافة القطعة</button></p></form>
<style>.erp{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:8px 0;border-bottom:1px solid var(--line)}.erp form{margin:0}</style></div>{% endblock %}""",
"settings": """{% extends 'base' %}{% block c %}<div class=card><h3>إعدادات الشركة</h3><form method=post enctype=multipart/form-data><div class=fg>
<label>اسم الشركة<input name=shop_name value="{{st.shop_name}}" required></label>
<label>اسم المستخدم (لتسجيل الدخول)<input name=username value="{{un}}" dir=ltr pattern="[A-Za-z0-9._-]{3,30}" required></label>
<label class=fa>عنوان الشركة (بيظهر أعلى الفواتير)<input name=address value="{{st.address or ''}}" placeholder="مثال: نابلس، شارع ..."></label>
<label>مفتاح الدولة (970 أو 972)<input name=cc value="{{st.cc}}" required></label>
<div class=fa><b style="display:block;margin-bottom:6px">شعار القائمة العلوية</b>
<div class=lgx><div class=lgp id=lgp>{% if tb_logo %}<img id=lgi src="/shoplogo?v={{tb_logo}}" alt="الشعار الحالي">{% else %}<img id=lgi alt="" hidden><span id=lgph>{{ (st.shop_name or 'م')|trim|first|upper }}</span>{% endif %}</div>
<div class=lgb><label class="btn ghost lgf" for=lgin style="margin:0"><svg width=18 height=18 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2 stroke-linecap=round stroke-linejoin=round><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12"/></svg>{{ 'تغيير الشعار' if tb_logo else 'رفع شعار' }}</label>
<input type=file id=lgin name=logo accept="image/png,image/jpeg,image/webp" hidden>
<small id=lgn>PNG / JPG / WEBP · حتى 2 ميجا · الأفضل صورة مربعة بخلفية شفافة أو بيضاء</small>
{% if tb_logo %}<label class=lgr><input type=checkbox name=rm_logo value=1 id=lgrm> حذف الشعار والرجوع للحرف التلقائي</label>{% endif %}</div></div></div>
<div class=fa><b style="display:block;margin:10px 0 2px">أسعار الصرف (القائمة العلوية)</b><small style="color:var(--mut)">بتتحدث تلقائياً من الإنترنت. إذا بدك تثبّت سعر معيّن (مثلاً سعر الصرافة عندك) اكتبه بالخانة، واتركها فاضية للتلقائي.</small></div>
<label>سعر الدولار بالشيكل (₪)<input name=fx_usd type=number step=0.0001 min=0 inputmode=decimal value="{{ st.fx_usd or '' }}" placeholder="تلقائي"></label>
<label>سعر الدينار بالشيكل (₪)<input name=fx_jod type=number step=0.0001 min=0 inputmode=decimal value="{{ st.fx_jod or '' }}" placeholder="تلقائي"></label>
<style>.lgx{display:flex;align-items:center;gap:16px;flex-wrap:wrap;padding:14px;border:1px dashed #cdd5e8;border-radius:16px;background:#f8f9fe}.lgp{width:84px;height:84px;border-radius:22px;background:linear-gradient(135deg,#4338ca,#7c6bff 55%,#22d3ee);display:grid;place-items:center;color:#fff;font:800 38px/1 Cairo,system-ui,sans-serif;overflow:hidden;flex-shrink:0;box-shadow:0 14px 22px -14px #5b4ef0}.lgp.im{background:#fff;box-shadow:0 0 0 1px var(--line)}.lgp img{width:100%;height:100%;object-fit:contain;display:block}.lgp img[hidden],.lgp span[hidden]{display:none}.lgb{display:flex;flex-direction:column;gap:8px;align-items:flex-start}.lgb small{color:var(--mut)}.lgr{display:flex;align-items:center;gap:8px;font-size:13.5px;color:#be123c;font-weight:600;cursor:pointer}.lgr input{width:auto;margin:0}</style>
<script>(function(){var i=document.getElementById('lgin'),p=document.getElementById('lgp'),im=document.getElementById('lgi'),ph=document.getElementById('lgph'),n=document.getElementById('lgn'),rm=document.getElementById('lgrm');if(!i)return;
if(im&&!im.hidden)p.classList.add('im');
i.addEventListener('change',function(){var f=i.files[0];if(!f)return;
if(f.size>2*1024*1024){n.textContent='حجم الصورة أكبر من 2 ميجا، اختر صورة أصغر';n.style.color='#be123c';i.value='';return}
if(!/^image[/](png|jpeg|webp)$/.test(f.type)){n.textContent='الصيغة غير مدعومة، اختر PNG أو JPG أو WEBP';n.style.color='#be123c';i.value='';return}
var r=new FileReader();r.onload=function(e){im.src=e.target.result;im.hidden=false;if(ph)ph.hidden=true;p.classList.add('im');n.style.color='';n.textContent='جاهزة للحفظ: '+f.name+' — اضغط "حفظ" لتثبيت الشعار';if(rm)rm.checked=false};r.readAsDataURL(f)});
if(rm)rm.addEventListener('change',function(){if(rm.checked){i.value='';im.hidden=true;if(ph)ph.hidden=false;else{p.classList.remove('im')}n.textContent='رح يتحذف الشعار عند الحفظ'}else{location.reload()}})})();</script>
</div>
<div class='card2 ptn'><h4 class=ptt>تقسيم المربح بين الأطراف</h4><small>إذا الشركة بين أكثر من طرف (شركاء)، حدد عددهم ونسبة كل طرف. بتظهر حصة كل طرف من المربح بصفحة الصيانة.</small>
<div class=fg><label>عدد الأطراف<select name=ptn_n id=ptnn>{% for n in range(1,6) %}<option value={{n}}{{' selected' if n==(ptn|length or 1)}}>{{ 'طرف واحد (بدون تقسيم)' if n==1 else (n|string)+' أطراف' }}</option>{% endfor %}</select></label></div>
<div id=ptnr>{% for k in range(5) %}{% set pp = ptn[k] if k < ptn|length else none %}<div class=ptr data-k={{k}}><label>اسم الطرف {{k+1}}<input name=ptn_name{{k}} value='{{pp.name if pp else ''}}' placeholder='مثال: أنا / شريكي'></label><label>النسبة %<input name=ptn_pct{{k}} type=number step=any min=0 max=100 value='{{pp.pct if pp else ''}}'></label></div>{% endfor %}</div>
<div id=ptns class=ptns></div></div>
<style>.ptn{margin-top:18px;padding-top:14px;border-top:1px dashed var(--line)}.ptt{margin:0 0 4px;font-size:16px}.ptr{display:grid;grid-template-columns:2fr 1fr;gap:12px;margin-top:10px}.ptr[hidden]{display:none}.ptns{margin-top:10px;font-weight:700;color:#059669}.ptns.bad{color:#be123c}@media(max-width:600px){.ptr{grid-template-columns:1fr}}</style>
<script>(function(){var n=document.getElementById('ptnn'),rows=document.querySelectorAll('#ptnr .ptr'),sm=document.getElementById('ptns');if(!n)return;
function upd(){var c=parseInt(n.value,10)||1,t=0;rows.forEach(function(r,k){r.hidden=k>=c;if(k<c){t+=parseFloat(r.querySelector('input[type=number]').value)||0}});
var ok=Math.abs(t-100)<0.06;sm.textContent=c<2?'':(ok?'المجموع 100% ✓':'المجموع '+(Math.round(t*100)/100)+'% — لازم يكون 100%');sm.className='ptns'+(c>=2&&!ok?' bad':'')}
n.addEventListener('change',function(){var c=parseInt(n.value,10)||1,eq=Math.round(10000/c)/100;rows.forEach(function(r,k){r.querySelector('input[type=number]').value=k<c&&c>1?eq:''});upd()});
rows.forEach(function(r){r.querySelector('input[type=number]').addEventListener('input',upd)});upd()})();</script>
<p><button>حفظ</button></p></form><small>اسم الشركة والشعار بيظهروا بالقائمة العلوية، والاسم بيظهر كمان بالإيصال وبرسائل واتساب. مفتاح الدولة بيتحط قبل أرقام الزباين اللي بتبدأ بـ 0.</small></div>
<div class=card style="margin-top:16px"><h3>تغيير كلمة السر</h3>
{% if pw_err %}<div class=err role=alert>{{pw_err}}</div>{% endif %}{% if pw_ok %}<div class=okb>تم تغيير كلمة السر بنجاح.</div>{% endif %}
<small>الحساب: <b>{{email}}</b></small>
<form method=post action=/settings/password><div class=fg>
<label>كلمة السر الحالية<input name=old type=password required autocomplete=current-password></label>
<label>كلمة السر الجديدة (6 أحرف على الأقل)<input name=new type=password minlength=6 required autocomplete=new-password></label>
<label>تأكيد كلمة السر الجديدة<input name=new2 type=password minlength=6 required autocomplete=new-password></label></div>
<p><button>تغيير كلمة السر</button></p></form></div>{% endblock %}""",
"receipt": """<!doctype html><html lang=ar dir=rtl><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>إيصال صيانة #{{r.id}}</title>
{% include 'thcss' %}
<div class=bar><button type=button onclick="history.length>1?history.back():location.href='/repairs'">← رجوع</button><button onclick="print()">طباعة</button><button onclick="sw('w80')">ورق 80 مم</button><button onclick="sw('w58')">ورق 58 مم</button></div>
<div class=tk>
<span class=ttl>إيصال صيانة</span>
<div class=ref dir=ltr>#{{r.id}}</div>
<div class=head><span class=lg>{{thic.store}}</span><h1 class=shop>{{st.shop_name}}</h1></div>{% if st.address %}<div style="text-align:center;font-size:11px;margin:2px 0 4px">{{st.address}}</div>{% endif %}
<div class=inf>
<div class=f><span class=k>{{thic.user}}الزبون</span><span class=dl></span><span class=v>{{r.customer}}</span></div>
{% if r.phone %}<div class=f><span class=k>{{thic.phone}}الهاتف</span><span class=dl></span><span class=v dir=ltr>{{r.phone}}</span></div>{% endif %}
<div class=f><span class=k>{{thic.cal}}تاريخ الاستلام</span><span class=dl></span><span class=v dir=ltr>{{r.created}}</span></div>
{% if r.status=='تم التسليم' and r.done_date %}<div class=f><span class=k>{{thic.cal}}تاريخ التسليم</span><span class=dl></span><span class=v dir=ltr>{{r.done_date}}</span></div>{% endif %}
</div>
<hr class=dash>
<div class=inf>
<div class=f><span class=k>الجهاز</span><span class=dl></span><span class=v>{{r.device}}</span></div>
<div class=f><span class=k>العطل</span><span class=dl></span><span class=v>{{r.issue}}</span></div>
{% if r.pn %}<div class=f><span class=k>القطع</span><span class=dl></span><span class=v>{{r.pn}}</span></div>{% endif %}
<div class=f><span class=k>الحالة</span><span class=dl></span><span class=v><span class=st>{{r.status}}</span></span></div>
</div>
<div class=tot><span>المبلغ</span><b>{{ '%g'|format(r.price) }} ₪</b></div>
<div class=ft>شكراً لثقتكم<small>نتمنى لكم يوماً سعيداً</small></div>
<div class=cut><span>✂</span></div>
</div></html>""",
"notifs": """{% extends 'base' %}{% block c %}<div class=card><h3>الإشعارات <a href=/notifications/clear style="font-size:14px">مسح الكل</a></h3>
<table>{% for n in rows %}<tr class="{{'new' if not n.seen}}"><td>{{'⚠️' if n.kind=='warn' else '✅' if n.kind=='ok' else 'ℹ️'}}<td>{{n.msg}}<td><small>{{n.created}}</small></tr>
{% else %}<tr><td>لا يوجد إشعارات</tr>{% endfor %}</table></div>{% endblock %}""",
"requirements": """{% extends 'base' %}{% block c %}
<div class="sg4"><div class=sc><span class="si a">{{ic.pl}}</span><div><small>بنود شراء مفتوحة</small><b>{{cnt['شراء']}}</b></div></div>
<div class=sc><span class="si d">{{ic.rt}}</span><div><small>مرتجعات مفتوحة</small><b>{{cnt['مرتجع']}}</b></div></div>
<div class=sc><span class="si c">₪</span><div><small>الصافي المفتوح (شراء − مرتجع)</small><b dir=ltr>{{ '%g'|format(net) }} ₪</b></div></div></div>
<div class=tools><div class=r1><label class=search>{{ic.sr}}<input data-f=ntbl data-role=search placeholder="بحث في البنود..."></label>
<a class="btn {{'' if not kind else 'ghost'}}" href=/requirements>الكل ({{cnt['شراء']+cnt['مرتجع']}})</a><a class="btn {{'' if kind=='شراء' else 'ghost'}}" href="/requirements?kind=شراء">شراء ({{cnt['شراء']}})</a><a class="btn {{'' if kind=='مرتجع' else 'ghost'}}" href="/requirements?kind=مرتجع">مرتجعات ({{cnt['مرتجع']}})</a>
<span class=sp></span><a class="btn ghost" href=/requirements/auto title="القطع الناقصة بتنضاف لحالها، هاد الزر بس للتحديث الفوري">تحديث النواقص</a><button type=button data-open=dlg-need>+ إضافة بند</button></div></div>
<dialog class=dlg id=dlg-need data-auto><form method=post id=nf>
<div class=dh><h3>إضافة بند</h3><button type=button class=cl data-close aria-label="إغلاق">×</button></div>
<div class=db><div class=fg>
<label>النوع<select name=kind id=nk><option value="شراء">شراء<option value="مرتجع">مرتجع</select></label>
<label>الكمية<input name=qty id=nq type=number min=1 value=1 required inputmode=numeric></label>
<label class=fa>الصنف — اكتب أو اختر من المخزون<input name=name id=nn list=nlist autocomplete=off required placeholder="مثلاً: شاشة iPhone XR"></label>
<datalist id=nlist>{% for o in opts %}<option value="{{o.label}}">{% endfor %}</datalist><input type=hidden name=part_id id=np>
<label>سعر الوحدة (₪) — بيتعبّى تلقائياً<input name=cost id=nc type=number step=any min=0 inputmode=decimal></label>
<label>المورد (بيتحدد تلقائياً من القطعة)<select name=supplier_id id=ns><option value="">— اختر المورد —{% for s in sup %}<option value={{s.id}}>{{s.name}}{% endfor %}</select></label>
<label class=fa id=nrw style="display:none">سبب الإرجاع<select name=reason>{% for r in reasons %}<option>{{r}}{% endfor %}</select></label>
<label class=fa>ملاحظة<input name=note></label></div>
<p class=hint id=nh></p></div>
<div class=df><button>إضافة البند</button><button type=button class=ghost data-close>إلغاء</button></div></form></dialog>
<script id=nopts type="application/json">{{ opts|tojson }}</script>
{% if groups %}<div class=card id=grp><h3>حسب المورد <small style="font-weight:400;color:var(--mut)">— كل بند بينتسب تلقائياً لمورد القطعة، والفاتورة بتجمع الشراء والمرتجع للمورد</small></h3>
<div style="display:flex;flex-wrap:wrap;gap:12px">{% for g in groups %}<form method=post action=/invoices/new class=il style="border:1px solid var(--line);border-radius:14px;padding:12px 14px;flex-direction:column;align-items:stretch;gap:6px;min-width:210px;background:#fff">
<input type=hidden name=all value=1><input type=hidden name=kind value="{{kind}}"><input type=hidden name=sid value="{{g.id or ''}}">
<b>{{g.name}}</b><small>{{g.nbuy}} شراء · {{g.nret}} مرتجع</small><span dir=ltr style="text-align:right;font-weight:700">{{ '%g'|format(g.net) }} ₪</span>
{% if g.id %}<button class=ghost style="padding:6px 12px;font-size:13px">إنشاء فاتورة</button>{% else %}<small style="color:var(--red)">حدّد المورد من الجدول تحت</small>{% endif %}</form>{% endfor %}</div>
{% if groups|length > 1 or (groups and groups[0].id) %}<form method=post action=/invoices/new style="margin-top:14px"><input type=hidden name=all value=1><input type=hidden name=kind value="{{kind}}">
<button>إنشاء فواتير {{ 'المرتجعات' if kind=='مرتجع' else 'الشراء' if kind=='شراء' else 'الشراء والمرتجعات' }} لكل المورّدين تلقائياً</button></form>{% endif %}</div>{% endif %}
<form method=post action=/invoices/new><input type=hidden name=kind value="{{kind}}"><div class=card><h3>البنود المفتوحة</h3><small class=hint style="display:block;margin:0 0 8px">الكمية المقترحة للنواقص = (ضعف حد التنبيه − المتوفر بالمخزن)؛ يعني قطعة كميتها 0 وحدّها 2 بتطلع 4. تقدر تعدّل الكمية المطلوبة بالضغط على الرقم.</small><table class=srt id=ntbl><tr><th class=ns><input type=checkbox id=nall title="تحديد الكل"><th>النوع<th>الصنف<th>الكمية المطلوبة<th>سعر الوحدة<th>المجموع<th>المورد<th>ملاحظة<th class=ns></tr>
{% for n in items %}<tr><td><input type=checkbox name=item_id value={{n.id}}><td data-v="{{n.kind}}"><span class="tag {{'bad' if n.kind=='مرتجع'}}">{{n.kind}}</span><td><b>{{n.name}}</b>{% if n.auto %} <small style="color:var(--mut)">(تلقائي)</small>{% endif %}{% if n.part_id and n.stock is not none %}<br><small style="color:{{ 'var(--red)' if n.stock<=0 else 'var(--mut)' }}">{{ 'نفد من المخزن (0)' if n.stock<=0 else 'بالمخزن: ' ~ n.stock }} · حد التنبيه: {{ n.pmin if n.pmin is not none else 2 }}</small>{% endif %}<td data-v="{{n.qty}}">{% if n.kind=='شراء' %}<input type=number min=1 class=nqty data-id={{n.id}} value={{n.qty}} style="width:72px" title="الكمية المطلوبة — عدّلها وبتنحفظ لحالها">{% else %}{{n.qty}}{% endif %}<td>{{ '%g'|format(n.cost or 0) }}<td class=nw>{{ '-' if n.kind=='مرتجع' }}{{ '%g'|format(n.total) }} ₪
<td data-v="{{n.sname or ''}}"><select class=sps data-id={{n.id}} style="min-width:150px{{';border-color:var(--red)' if not n.sid}}"><option value="">— حدّد المورد —{% for s in sup %}<option value={{s.id}} {{'selected' if s.id==n.sid}}>{{s.name}}{% endfor %}</select>
<td>{{n.note}}<td><a class="ib dl" title="حذف" href="/requirements/{{n.id}}/delete?kind={{kind}}" onclick="return confirm('حذف البند؟ (حذف مرتجع من هون ما بيرجّع الكمية للمخزن — لإلغاء المرتجع كامل احذفه من صفحة المرتجعات)')">{{ic.dl}}</a></tr>
{% else %}<tr><td colspan=9 class=em>ما في بنود مفتوحة. القطع الناقصة بتنضاف لحالها، أو اضغط "+ إضافة بند".</tr>{% endfor %}</table>
<p><button>إنشاء فاتورة للبنود المحددة</button> <small>ممكن تحدّد بنود أكثر من مورد — بينعمل فاتورة لكل مورد تلقائياً. المرتجعات بتنخصم من الإجمالي.</small></p></div></form>
<div class=card id=invs><h3>فواتير الموردين</h3><table><tr><th>الرقم<th>التاريخ<th>المورد<th>الصافي<th></tr>
{% for i in invs %}<tr><td>INV-{{'%04d'|format(i.id)}}<td>{{i.created}}<td>{{i.sname}}<td>{{ '%g'|format(i.total) }} ₪<td><a href=/invoices/{{i.id}} target=_blank>A4</a> · <a href=/invoices/{{i.id}}/thermal target=_blank>حرارية</a></tr>
{% else %}<tr><td colspan=5 class=em>ما في فواتير بعد.</tr>{% endfor %}</table></div>
<script>(function(){function $(i){return document.getElementById(i)}
var all=$('nall');if(all)all.addEventListener('change',function(){document.querySelectorAll('#ntbl input[name=item_id]').forEach(function(c){if(c.closest('tr').style.display!=='none')c.checked=all.checked})});
document.querySelectorAll('select.sps').forEach(function(sl){sl.addEventListener('change',function(){var fd=new FormData();fd.append('supplier_id',sl.value);fetch('/requirements/'+sl.dataset.id+'/supplier',{method:'POST',body:fd,credentials:'same-origin'}).then(function(){location.reload()})})});
document.querySelectorAll('input.nqty').forEach(function(i){i.addEventListener('change',function(){var v=parseInt(i.value);if(!(v>=1)){v=1;i.value=1}var fd=new FormData();fd.append('qty',v);fetch('/requirements/'+i.dataset.id+'/qty',{method:'POST',body:fd,credentials:'same-origin'}).then(function(){location.reload()})})});
var d=$('nopts');if(!d)return;var O=JSON.parse(d.textContent),M={};O.forEach(function(o){M[o.label.trim().toLowerCase()]=o});
var nn=$('nn'),np=$('np'),nc=$('nc'),ns=$('ns'),nh=$('nh'),nk=$('nk'),nq=$('nq'),nrw=$('nrw');
function kind(){var r=nk.value==='مرتجع';nrw.style.display=r?'':'none';var o=M[nn.value.trim().toLowerCase()];if(o&&o.pid&&r&&o.qty!=null){nq.max=o.qty}else{nq.removeAttribute('max')}}
function pick(){var o=M[nn.value.trim().toLowerCase()];if(!o){np.value='';nh.textContent='';kind();return}
np.value=o.pid||'';nc.value=o.cost?o.cost:'';ns.value=o.sup||'';
var sn=o.sup?ns.options[ns.selectedIndex].text:'';
nh.textContent=(o.pid?'متوفر بالمخزن: '+o.qty+' · ':'')+(o.cost?'السعر: '+o.cost+' ₪':'ما في سعر مسجّل — اكتبه')+' · '+(sn?'المورد: '+sn:'ما في مورد مسجّل — اختره');kind()}
nn.addEventListener('input',pick);nn.addEventListener('change',pick);nk.addEventListener('change',kind);
document.addEventListener('click',function(e){if(e.target.closest('[data-open=dlg-need]')){setTimeout(function(){nh.textContent='';np.value='';nrw.style.display='none';nq.removeAttribute('max')},0)}});
$('nf').addEventListener('submit',function(e){if(!ns.value&&!np.value){if(!confirm('ما اخترت مورد للبند. بيضل بدون مورد لحد ما تحدده من الجدول. تكمل؟'))e.preventDefault()}})})();</script>{% endblock %}""",
"invoice": """<!doctype html><html lang=ar dir=rtl><meta charset=utf-8><title>INV-{{'%04d'|format(inv.id)}}</title>
<style>body{font-family:Tahoma,sans-serif;max-width:760px;margin:24px auto;color:#0f172a}.lk{display:flex;align-items:center;gap:10px;direction:ltr}.wm{font:700 22px sans-serif;color:#1c2760}.tg{font:600 8px sans-serif;letter-spacing:.12em;color:#64748b}
.top{display:flex;justify-content:space-between;align-items:center;border-bottom:3px solid #1c2760;padding-bottom:14px}table{width:100%;border-collapse:collapse;margin-top:18px}
th{background:#1c2760;color:#fff;padding:8px;text-align:right}td{padding:8px;border-bottom:1px solid #ddd}.r{color:#e11d48}.tot{font-size:20px;font-weight:bold;text-align:left;margin-top:14px}.sg{display:flex;justify-content:space-between;margin-top:50px}@media print{button{display:none}}</style>
<div class=top>{{logo}}<div style="text-align:left"><b>فاتورة مورد INV-{{'%04d'|format(inv.id)}}</b><br>{{inv.created}}</div></div>
<p><b>من:</b> {{st.shop_name}}{% if st.address %} — {{st.address}}{% endif %}<br><b>إلى المورد:</b> {{inv.sname}} {{inv.sphone or ''}}</p>
<table><tr><th>النوع<th>الصنف<th>الكمية<th>سعر الوحدة<th>المجموع</tr>
{% for n in lines %}<tr class="{{'r' if n.kind=='مرتجع'}}"><td>{{n.kind}}<td>{{n.name}}<td>{{n.qty}}<td>{{ '%g'|format(n.cost) }}<td>{{ '-' if n.kind=='مرتجع' }}{{ '%g'|format(n.qty*n.cost) }}</tr>{% endfor %}</table>
<div class=tot>الصافي المستحق: {{ '%g'|format(inv.total) }} ₪</div>
<p><button onclick="print()">طباعة</button> <a href=/invoices/{{inv.id}}/thermal style="margin-right:10px">طباعة حرارية</a></p></html>""",
"report": """{% extends 'base' %}{% block c %}
<div class=tools><div class=r1><form method=get><input type=month name=m value={{m}}><button>عرض</button></form><span class=sp></span><a class="btn ghost" href="/export?m={{m}}">تصدير Excel</a></div></div>
<div class=sg4><div class=sc><span class="si a">#</span><div><small>الصيانات</small><b>{{n}}</b></div></div>
<div class=sc><span class="si b">₪</span><div><small>الإيرادات</small><b>{{ '%g'|format(rev) }} ₪</b></div></div>
<div class=sc><span class="si e">₪</span><div><small>تكلفة القطع</small><b>{{ '%g'|format(cost) }} ₪</b></div></div>
<div class=sc><span class="si c">₪</span><div><small>الربح</small><b class=big style="font-size:28px">{{ '%g'|format(rev-cost) }} ₪</b></div></div></div>
<div class=card><h3>حسب اليوم</h3><table><tr><th>التاريخ<th>العدد<th>الربح</tr>{% for d,v in days %}<tr><td>{{d}}<td>{{v[0]}}<td>{{ '%g'|format(v[1]) }} ₪</tr>{% else %}<tr><td colspan=3 class=em>لا يوجد بيانات لهذا الشهر.</tr>{% endfor %}</table></div>
<div class=card><h3>أكثر القطع استهلاكاً</h3>{% for t in top %}<div class=lw><span>{{t.name}}</span><span class=tag>{{t.n}}</span></div>{% else %}<div class=em>لا يوجد</div>{% endfor %}</div>{% endblock %}"""}
T["landing"] = """<!doctype html><html lang=ar dir=rtl><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>REPAIRIX — نظام إدارة محلات الصيانة والمخزون</title>
<meta name=description content="REPAIRIX نظام عربي لإدارة محلات صيانة الجوالات: صيانة، مخزون بالألوان، كاشير سريع، موظفين وعهدة، موردين، صندوق وتقارير أرباح. جرّب مجاناً 7 أيام.">
<meta name=theme-color content="#060a22">
<link rel=preconnect href="https://fonts.googleapis.com"><link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&display=swap" rel=stylesheet>
{% raw %}<style>
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;font-family:"Cairo","Tajawal",system-ui,-apple-system,"Segoe UI",Tahoma,Arial,sans-serif;background:#060a22;color:#e7ebff;line-height:1.7;-webkit-font-smoothing:antialiased;overflow-x:hidden}
a{color:inherit;text-decoration:none}
.bg{position:fixed;inset:0;z-index:-1;background:radial-gradient(900px 520px at 85% -10%,#4f46e555,transparent 60%),radial-gradient(800px 520px at 5% 30%,#06b6d433,transparent 60%),radial-gradient(700px 500px at 60% 110%,#c026d322,transparent 60%),#060a22}
.bg:before{content:'';position:absolute;inset:0;background-image:linear-gradient(#8ea2ff0f 1px,transparent 1px),linear-gradient(90deg,#8ea2ff0f 1px,transparent 1px);background-size:56px 56px;-webkit-mask-image:linear-gradient(180deg,#000,transparent 70%);mask-image:linear-gradient(180deg,#000,transparent 70%)}
.wrap{max-width:1180px;margin:0 auto;padding:0 22px}
.lk{display:flex;align-items:center;gap:11px;direction:ltr}.wm{font:800 21px/1.1 system-ui,sans-serif;letter-spacing:.06em;color:#fff}.tg{font:600 7.4px/1.4 system-ui,sans-serif;letter-spacing:.1em;white-space:nowrap;color:#8d9be0;margin-top:3px}
/* nav */
.nav{position:sticky;top:0;z-index:20;backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);background:#060a22cc;border-bottom:1px solid #ffffff14}
.nav .wrap{display:flex;align-items:center;gap:14px;height:68px}.nav .sp{flex:1}
.nav .links{display:flex;gap:22px;color:#b9c2f0;font-weight:600;font-size:15px}.nav .links a:hover{color:#fff}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;padding:11px 20px;border-radius:12px;font:700 15px/1 inherit;font-family:inherit;border:1.5px solid #ffffff2e;background:#ffffff0d;color:#fff;cursor:pointer;transition:.18s}
.btn:hover{background:#ffffff1c;transform:translateY(-1px)}
.btn.p{background:linear-gradient(135deg,#6d5efc,#3b82f6);border-color:transparent;box-shadow:0 10px 28px -10px #6d5efccc}.btn.p:hover{box-shadow:0 14px 34px -10px #6d5efc}
.btn.g{background:#22c55e1f;border-color:#22c55e66;color:#86efac}
.btn.lg{padding:15px 26px;font-size:17px;border-radius:14px}
/* hero */
.hero{padding:64px 0 30px;display:grid;grid-template-columns:1fr 1.15fr;gap:46px;align-items:center}
.badge{display:inline-block;padding:5px 14px;border-radius:999px;border:1px solid #6d5efc66;background:#6d5efc1f;color:#b8b2ff;font-size:13.5px;font-weight:700}
h1{font-size:clamp(34px,5vw,56px);line-height:1.2;margin:16px 0 14px;font-weight:800;letter-spacing:-.5px}
h1 em{display:block;font-style:normal;background:linear-gradient(90deg,#818cf8,#22d3ee);-webkit-background-clip:text;background-clip:text;color:transparent}
.lead{color:#b4bde8;font-size:17.5px;max-width:560px;margin:0 0 24px}
.cta{display:flex;gap:12px;flex-wrap:wrap}
.checks{display:flex;gap:18px;flex-wrap:wrap;margin-top:22px;color:#98a3d8;font-size:14.5px}.checks span:before{content:'✓';color:#22d3ee;font-weight:800;margin-inline-end:6px}
.shot{position:relative}.shot:before{content:'';position:absolute;inset:6% 4% -6%;background:linear-gradient(135deg,#6d5efc,#22d3ee);filter:blur(60px);opacity:.35;border-radius:40px;z-index:-1}
.win{border-radius:16px;overflow:hidden;border:1px solid #ffffff26;background:#0c1233;box-shadow:0 40px 80px -30px #000c}
.win .bar{display:flex;gap:7px;align-items:center;padding:10px 14px;background:#0f1640;border-bottom:1px solid #ffffff14;direction:ltr}.win .bar i{width:11px;height:11px;border-radius:50%;background:#ff5f57}.win .bar i:nth-child(2){background:#febc2e}.win .bar i:nth-child(3){background:#28c840}
.win .bar b{margin-inline-start:12px;font:600 12px system-ui,sans-serif;color:#8d9be0;background:#ffffff0f;padding:3px 12px;border-radius:8px}
.win img{display:block;width:100%;height:auto}
/* sections */
section{padding:74px 0}
.sh{text-align:center;max-width:720px;margin:0 auto 40px}.sh h2{font-size:clamp(26px,3.6vw,38px);margin:0 0 10px;font-weight:800}.sh p{color:#a5afe0;margin:0;font-size:17px}
.sh .kicker{color:#22d3ee;font-weight:700;font-size:14px;letter-spacing:.04em;margin-bottom:6px;display:block}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:16px}
.card{padding:22px;border-radius:20px;border:1px solid #ffffff1c;background:linear-gradient(160deg,#ffffff12,#ffffff06);transition:.2s}
.card:hover{transform:translateY(-4px);border-color:#6d5efc88;background:linear-gradient(160deg,#6d5efc22,#ffffff08)}
.ic{width:48px;height:48px;border-radius:14px;display:grid;place-items:center;font-size:24px;background:linear-gradient(135deg,#6d5efc55,#22d3ee33);margin-bottom:14px}
.card h3{margin:0 0 6px;font-size:19px}.card p{margin:0;color:#aab4e3;font-size:15px}
/* gallery */
.tabs{display:flex;gap:8px;justify-content:center;flex-wrap:wrap;margin-bottom:22px}
.tabs button{font-family:inherit;font-weight:700;font-size:14.5px;padding:9px 18px;border-radius:999px;border:1.5px solid #ffffff26;background:#ffffff0a;color:#c3caf0;cursor:pointer;transition:.15s}
.tabs button:hover{background:#ffffff18}.tabs button.on{background:linear-gradient(135deg,#6d5efc,#3b82f6);border-color:transparent;color:#fff}
.gal{max-width:980px;margin:0 auto}.gal .pane{display:none}.gal .pane.on{display:block;animation:fi .35s}
.cap{text-align:center;color:#a5afe0;margin-top:16px;font-size:16px}
@keyframes fi{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
/* steps */
.steps{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;counter-reset:s}
.step{position:relative;padding:26px 22px;border-radius:20px;border:1px solid #ffffff1c;background:#ffffff08}
.step:before{counter-increment:s;content:counter(s);display:grid;place-items:center;width:38px;height:38px;border-radius:50%;background:linear-gradient(135deg,#6d5efc,#22d3ee);font-weight:800;margin-bottom:12px}
.step h3{margin:0 0 4px;font-size:18px}.step p{margin:0;color:#aab4e3;font-size:15px}
/* cta band */
.band{text-align:center;padding:46px 24px;border-radius:28px;border:1px solid #6d5efc66;background:radial-gradient(500px 220px at 50% 0%,#6d5efc55,transparent 70%),#0d1440}
.band h2{margin:0 0 8px;font-size:clamp(24px,3.4vw,34px)}.band p{margin:0 0 22px;color:#b4bde8}
.band .cta{justify-content:center}
/* footer */
footer{border-top:1px solid #ffffff14;padding:34px 0 40px;margin-top:30px}
footer .wrap{display:flex;gap:26px;flex-wrap:wrap;align-items:center;justify-content:space-between}
.dev{direction:ltr;text-align:left;font:600 15px/1.8 system-ui,-apple-system,"Segoe UI",Arial,sans-serif;color:#b4bde8}
.dev b{color:#fff}.dev a{color:#7dd3fc}.dev a:hover{text-decoration:underline}
.fl{display:flex;gap:18px;color:#98a3d8;font-weight:600;font-size:14.5px}.fl a:hover{color:#fff}
.rv{opacity:0;transform:translateY(18px);transition:opacity .6s,transform .6s}.rv.in{opacity:1;transform:none}
@media(max-width:900px){.hero{grid-template-columns:1fr;padding-top:40px}.nav .links{display:none}.steps{grid-template-columns:1fr}.nav .wrap{height:60px}.btn.lg{width:100%}}
@media(max-width:520px){.nav .btn.hide{display:none}.lead{font-size:16px}}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}.rv{opacity:1;transform:none}}
</style>{% endraw %}</head><body>
<div class=bg></div>
<header class=nav><div class=wrap>{{logo}}<span class=sp></span>
<nav class=links><a href="#features">المميزات</a><a href="#screens">شاشات البرنامج</a><a href="#start">كيف تبدأ</a><a href="#contact">تواصل معنا</a></nav>
<a class="btn hide" href="/login">تسجيل الدخول</a><a class="btn p" href="/register">جرّب مجاناً</a></div></header>

<main>
<div class=wrap><div class=hero>
<div><span class=badge>تجربة مجانية 7 أيام · بدون بطاقة</span>
<h1>أدر محل الصيانة كله من مكان واحد<em>صيانة، مخزون، موظفين، ومحاسبة</em></h1>
<p class=lead>REPAIRIX نظام عربي لمحلات صيانة الجوالات والإكسسوارات: سجّل الصيانات واحسب مربحك تلقائياً، تابع المخزون بالألوان والموديلات، بيع بسرعة من الكاشير، وسلّم الموظفين بضاعة بفواتير ودفعات منظمة — كله من المتصفح على الكمبيوتر أو الجوال.</p>
<div class=cta><a class="btn p lg" href="/register">ابدأ التجربة المجانية ←</a><a class="btn lg" href="/login">تسجيل الدخول</a><a class="btn g lg" target=_blank rel=noopener href="https://wa.me/970598485827">💬 تواصل على واتساب</a></div>
<div class=checks><span>إعداد فوري</span><span>واجهة عربية بالكامل</span><span>كمبيوتر وهاتف</span></div></div>
<div class=shot><div class=win><div class=bar><i></i><i></i><i></i><b>REPAIRIX · لوحة التحكم</b></div><img src="/landing-img/dashboard.webp" width=1280 height=764 alt="لوحة تحكم REPAIRIX" fetchpriority=high></div></div>
</div></div>

<section id=features><div class=wrap>
<div class=sh><span class=kicker>المميزات</span><h2>كل اللي يحتاجه محلك بنظام واحد</h2><p>من استلام الجهاز لحد إقفال الصندوق، بدون دفاتر ولا برامج متفرقة.</p></div>
<div class=grid>
<div class="card rv"><div class=ic>🔧</div><h3>إدارة الصيانة</h3><p>سجّل الجهاز والعطل والقطع المستخدمة، تابع الحالة (قيد الصيانة / جاهز / تم التسليم)، واطبع الإيصال أو ابعته واتساب. المربح بينحسب تلقائياً لكل صيانة.</p></div>
<div class="card rv"><div class=ic>⚡</div><h3>كاشير سريع</h3><p>بيع بالباركود أو بالبحث بالاسم، خصم، دفع نقداً أو ديناً، وطباعة الفاتورة تلقائياً على الطابعة الحرارية أو A4.</p></div>
<div class="card rv"><div class=ic>📦</div><h3>مخزون ذكي</h3><p>شاشات، بطاريات، آيسيات، قواعد شحن، سماعات، وموديلات الظهور بكل ألوانها. تنبيه فوري لما تقل الكمية، وملصقات باركود جاهزة للطباعة.</p></div>
<div class="card rv"><div class=ic>👥</div><h3>الموظفون والعهدة</h3><p>سلّم الموظف بضاعة بفاتورة مستقلة، وخليه يرحّل دفعاته (نقد أو بنك مع صورة الوصل). حساب كل موظف مع الشركة واضح: كم استلم، كم دفع، وكم باقي.</p></div>
<div class="card rv"><div class=ic>🚚</div><h3>الموردون</h3><p>بيانات الموردين، المشتريات من كل مورد، الدفعات مع وصل التحويل، وكشف حساب جاهز للطباعة.</p></div>
<div class="card rv"><div class=ic>💰</div><h3>الصندوق والديون والشيكات</h3><p>صندوق مالي يومي، ديون الزبائن، متابعة الشيكات (صُرف / راجع)، وسجل المرتجعات مع الأسباب والصور.</p></div>
<div class="card rv"><div class=ic>📊</div><h3>تقارير الأرباح</h3><p>إيراداتك وتكلفتك ومربحك يومياً وشهرياً، مع تصدير كشف الأيام إلى Excel بضغطة وحدة.</p></div>
<div class="card rv"><div class=ic>💱</div><h3>أسعار الصرف والإشعارات</h3><p>شريط علوي بأسعار الدولار والدينار والشيكل، وإشعارات لنقص المخزون ولكل دفعة أو حركة يعملها موظفوك.</p></div>
</div></div></section>

<section id=screens><div class=wrap>
<div class=sh><span class=kicker>شاشات البرنامج</span><h2>شوف البرنامج بنفسك</h2><p>هاي صور حقيقية من النظام، بتصميم واضح وسريع ومريح للعين.</p></div>
<div class=tabs id=tabs>
<button class=on data-p=0>لوحة التحكم</button><button data-p=1>الصيانة</button><button data-p=2>الكاشير السريع</button><button data-p=3>الظهور والألوان</button><button data-p=4>عهدة الموظف</button><button data-p=5>فواتير التسليم</button><button data-p=6>التقارير</button><button data-p=7>أدوات الصيانة</button></div>
<div class=gal id=gal>
<div class="pane on"><div class=win><div class=bar><i></i><i></i><i></i><b>لوحة التحكم</b></div><img loading=lazy src="/landing-img/dashboard.webp" width=1280 height=764 alt="لوحة التحكم"></div><p class=cap>ملخص يومك: الدخل، المربح، الصيانات المفتوحة، وتنبيهات المخزون.</p></div>
<div class=pane><div class=win><div class=bar><i></i><i></i><i></i><b>الصيانة</b></div><img loading=lazy src="/landing-img/repairs.webp" width=1280 height=764 alt="الصيانة"></div><p class=cap>كل الصيانات بحالاتها، بحث وتصفية بالتاريخ، وتصدير لـ Excel.</p></div>
<div class=pane><div class=win><div class=bar><i></i><i></i><i></i><b>الكاشير السريع</b></div><img loading=lazy src="/landing-img/pos.webp" width=1280 height=764 alt="الكاشير السريع"></div><p class=cap>بيع بالباركود أو بالاسم، وأتمم الفاتورة بضغطة.</p></div>
<div class=pane><div class=win><div class=bar><i></i><i></i><i></i><b>الظهور</b></div><img loading=lazy src="/landing-img/backs.webp" width=1918 height=946 alt="الظهور"></div><p class=cap>موديلات الظهور بألوانها وكمياتها مع أزرار زيادة ونقصان سريعة.</p></div>
<div class=pane><div class=win><div class=bar><i></i><i></i><i></i><b>عهدة الموظف</b></div><img loading=lazy src="/landing-img/employee.webp" width=1280 height=764 alt="عهدة الموظف"></div><p class=cap>بضاعة الموظف، حسابه مع الشركة، ودفعاته النقدية والبنكية.</p></div>
<div class=pane><div class=win><div class=bar><i></i><i></i><i></i><b>فواتير التسليم</b></div><img loading=lazy src="/landing-img/invoices.webp" width=1280 height=764 alt="فواتير التسليم"></div><p class=cap>كل تسليم بضاعة له فاتورة: عرض، طباعة، تعديل أو حذف.</p></div>
<div class=pane><div class=win><div class=bar><i></i><i></i><i></i><b>التقرير الشهري</b></div><img loading=lazy src="/landing-img/report.webp" width=1280 height=764 alt="التقرير الشهري"></div><p class=cap>إيرادات وتكلفة ومربح كل يوم، جاهزة للتصدير.</p></div>
<div class=pane><div class=win><div class=bar><i></i><i></i><i></i><b>أدوات الصيانة</b></div><img loading=lazy src="/landing-img/tools.webp" width=1918 height=944 alt="أدوات الصيانة"></div><p class=cap>جرد أدوات الورشة بالصور والأعداد وأماكن التخزين، وإمكانية بيعها من المتجر.</p></div>
</div></div></section>

<section id=start><div class=wrap>
<div class=sh><span class=kicker>كيف تبدأ</span><h2>جاهز للشغل خلال دقائق</h2></div>
<div class=steps>
<div class="step rv"><h3>أنشئ حسابك</h3><p>سجّل بإيميلك وابدأ فترة تجريبية مجانية لمدة 7 أيام بدون أي بطاقة.</p></div>
<div class="step rv"><h3>أضف محلك</h3><p>أدخل قطعك وموردينك وموظفينك، وارفع شعارك وبيانات محلك للإيصالات.</p></div>
<div class="step rv"><h3>اشتغل وتابع</h3><p>سجّل الصيانات والمبيعات، وراقب الأرباح والمخزون وحسابات الموظفين لحظة بلحظة.</p></div>
</div></div></section>

<div class=wrap id=contact><div class="band rv"><h2>جاهز تنظم محلك؟</h2><p>جرّب REPAIRIX مجاناً، أو تواصل معنا وبنساعدك بالبداية.</p>
<div class=cta><a class="btn p lg" href="/register">ابدأ التجربة المجانية ←</a><a class="btn g lg" target=_blank rel=noopener href="https://wa.me/970598485827">💬 واتساب</a><a class="btn lg" href="tel:0598485827">📞 اتصال</a></div></div></div>
</main>

<footer><div class=wrap>
<div>{{logo}}</div>
<div class=dev><div>Developer: <b>diaa jdeea</b></div><div>Phone: <a href="tel:0598485827">0598485827</a></div></div>
<div class=fl><a href="/login">تسجيل الدخول</a><a href="/register">حساب جديد</a></div>
</div></footer>
{% raw %}<script>
(function(){var t=document.getElementById('tabs'),p=document.querySelectorAll('#gal .pane');
t.addEventListener('click',function(e){var b=e.target.closest('button');if(!b)return;var i=+b.dataset.p;t.querySelectorAll('button').forEach(function(x){x.classList.toggle('on',x===b)});p.forEach(function(x,k){x.classList.toggle('on',k===i)})});
var r=document.querySelectorAll('.rv');if('IntersectionObserver' in window){var o=new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting){e.target.classList.add('in');o.unobserve(e.target)}})},{threshold:.12});r.forEach(function(x){o.observe(x)})}else{r.forEach(function(x){x.classList.add('in')})}})();
</script>{% endraw %}
</body></html>
"""

T["auth"] = """{% extends 'base' %}{% block c %}
<style>
.lx{position:relative;min-height:100vh;display:grid;grid-template-columns:minmax(380px,.9fr) 1.1fr;direction:ltr;overflow:hidden;background:#060a22;isolation:isolate}
.lx>*{direction:rtl}
.lx-bg{position:absolute;inset:0;z-index:-1;background:linear-gradient(125deg,#060a22,#101a5c,#2a1d8f,#0b3b78,#060a22);background-size:400% 400%;animation:lxShift 22s ease-in-out infinite}
.lx-bg:before{content:'';position:absolute;inset:-50%;background-image:linear-gradient(#8ea2ff14 1px,transparent 1px),linear-gradient(90deg,#8ea2ff14 1px,transparent 1px);background-size:56px 56px;transform:perspective(700px) rotateX(58deg) translateY(0);transform-origin:50% 100%;animation:lxGrid 9s linear infinite;-webkit-mask-image:linear-gradient(0deg,#000 20%,transparent 75%);mask-image:linear-gradient(0deg,#000 20%,transparent 75%)}
.lx-orb{position:absolute;border-radius:50%;filter:blur(70px);opacity:.55;will-change:transform}
.lx-orb.o1{width:460px;height:460px;background:#4f46e5;top:-120px;left:-100px;animation:lxF1 16s ease-in-out infinite}
.lx-orb.o2{width:420px;height:420px;background:#06b6d4;bottom:-140px;right:12%;animation:lxF2 19s ease-in-out infinite}
.lx-orb.o3{width:320px;height:320px;background:#c026d3;top:30%;left:38%;opacity:.28;animation:lxF3 23s ease-in-out infinite}
.lx-dots{position:absolute;inset:0;overflow:hidden;pointer-events:none}
.lx-dots i{position:absolute;bottom:-12px;width:6px;height:6px;border-radius:50%;background:#7dd3fc;box-shadow:0 0 12px 2px #38bdf8aa;opacity:0;animation:lxUp linear infinite}
.lx-dots i:nth-child(1){left:6%;animation-duration:14s;animation-delay:0s}.lx-dots i:nth-child(2){left:14%;animation-duration:19s;animation-delay:3s;width:4px;height:4px}
.lx-dots i:nth-child(3){left:23%;animation-duration:16s;animation-delay:6s}.lx-dots i:nth-child(4){left:31%;animation-duration:21s;animation-delay:1s;width:8px;height:8px}
.lx-dots i:nth-child(5){left:42%;animation-duration:15s;animation-delay:8s;width:4px;height:4px}.lx-dots i:nth-child(6){left:51%;animation-duration:18s;animation-delay:2s}
.lx-dots i:nth-child(7){left:60%;animation-duration:13s;animation-delay:5s;width:5px;height:5px}.lx-dots i:nth-child(8){left:68%;animation-duration:20s;animation-delay:9s}
.lx-dots i:nth-child(9){left:76%;animation-duration:17s;animation-delay:4s;width:4px;height:4px}.lx-dots i:nth-child(10){left:84%;animation-duration:22s;animation-delay:7s;width:7px;height:7px}
.lx-dots i:nth-child(11){left:91%;animation-duration:15s;animation-delay:2s}.lx-dots i:nth-child(12){left:97%;animation-duration:18s;animation-delay:10s;width:4px;height:4px}
@keyframes lxShift{0%,100%{background-position:0 50%}50%{background-position:100% 50%}}
@keyframes lxGrid{to{background-position:0 56px,56px 0}}
@keyframes lxF1{0%,100%{transform:translate(0,0)}50%{transform:translate(140px,90px)}}
@keyframes lxF2{0%,100%{transform:translate(0,0)}50%{transform:translate(-160px,-70px)}}
@keyframes lxF3{0%,100%{transform:translate(0,0) scale(1)}50%{transform:translate(-90px,60px) scale(1.25)}}
@keyframes lxUp{0%{transform:translateY(0);opacity:0}12%{opacity:.9}85%{opacity:.5}100%{transform:translateY(-105vh);opacity:0}}
.lx-form{display:flex;align-items:center;justify-content:center;padding:32px 24px}
.lx-card{width:100%;max-width:430px;background:#ffffffeb;-webkit-backdrop-filter:blur(18px);backdrop-filter:blur(18px);border:1px solid #ffffff80;border-radius:26px;padding:38px 36px 30px;box-shadow:0 40px 90px -30px #000c,0 0 0 1px #ffffff14 inset;--wm:var(--navy);--tgc:#6b7799;animation:lxIn .8s cubic-bezier(.2,.8,.2,1) both}
@keyframes lxIn{from{opacity:0;transform:translateY(26px) scale(.98)}to{opacity:1;transform:none}}
.lx-card .fw{max-width:none}.lx-card .fw h1{margin:22px 0 4px;font-size:26px}
.lx-card input{border-radius:12px;transition:box-shadow .2s,border-color .2s}.lx-card input:focus{outline:none;border-color:var(--br);box-shadow:0 0 0 4px #4f46e51f}
.lx-card .wide{border-radius:12px;font-size:16px;background:linear-gradient(135deg,var(--br),var(--br2));box-shadow:0 14px 26px -12px var(--br);transition:transform .15s,box-shadow .2s}.lx-card .wide:hover{transform:translateY(-2px);box-shadow:0 18px 30px -12px var(--br)}
.lx-art{position:relative;display:flex;flex-direction:column;justify-content:center;align-items:center;padding:40px 48px;color:#fff;text-align:center}
.lx-stage{position:relative;width:min(100%,440px);aspect-ratio:1/1.05;margin-bottom:6px}
.lx-stage>svg{width:100%;height:100%;overflow:visible}
.lx-ph{animation:lxBob 6s ease-in-out infinite;transform-origin:50% 50%}
@keyframes lxBob{0%,100%{transform:translateY(0) rotate(-1.2deg)}50%{transform:translateY(-14px) rotate(1.2deg)}}
.lx-tr{stroke-dasharray:10 14;animation:lxDash 2.4s linear infinite}.lx-tr.s{animation-duration:3.6s;animation-direction:reverse}
@keyframes lxDash{to{stroke-dashoffset:-96}}
.lx-gear{transform-origin:50% 50%;transform-box:fill-box;animation:lxSpin 9s linear infinite}
@keyframes lxSpin{to{transform:rotate(360deg)}}
.lx-pulse{animation:lxPulse 2.4s ease-in-out infinite;transform-origin:50% 50%;transform-box:fill-box}
@keyframes lxPulse{0%,100%{opacity:.35;transform:scale(.8)}50%{opacity:1;transform:scale(1.15)}}
.lx-chip{position:absolute;display:flex;align-items:center;gap:10px;background:#ffffff1c;-webkit-backdrop-filter:blur(14px);backdrop-filter:blur(14px);border:1px solid #ffffff38;border-radius:16px;padding:10px 14px;text-align:right;font-size:13px;box-shadow:0 18px 36px -16px #000a;animation:lxChip 7s ease-in-out infinite}
.lx-chip b{display:block;font-size:15px;line-height:1.25}.lx-chip small{color:#c7d2ff;font-size:11.5px}
.lx-chip .ic{width:34px;height:34px;border-radius:11px;display:grid;place-items:center;flex-shrink:0}.lx-chip .ic svg{width:18px;height:18px}
.lx-chip.c1{top:6%;right:-4%}.lx-chip.c1 .ic{background:#10b98133;color:#6ee7b7}
.lx-chip.c2{top:44%;left:-8%;animation-delay:-2.3s}.lx-chip.c2 .ic{background:#f59e0b33;color:#fcd34d}
.lx-chip.c3{bottom:5%;right:2%;animation-delay:-4.6s}.lx-chip.c3 .ic{background:#22d3ee33;color:#67e8f9}
@keyframes lxChip{0%,100%{transform:translateY(0)}50%{transform:translateY(-12px)}}
.lx-art h2{font-size:30px;line-height:1.35;margin:10px 0 8px;text-shadow:0 4px 24px #0006}.lx-art p{color:#cbd3ff;margin:0;max-width:430px}
.lx-art .pts{list-style:none;margin:18px 0 0;padding:0;display:grid;gap:9px;color:#e3e8ff;text-align:right}.lx-art .pts li{display:flex;gap:10px;align-items:center}.lx-art .pts svg{width:18px;height:18px;flex-shrink:0;stroke:#67e8f9}
.lx-art .tg{margin-top:18px;letter-spacing:.2em;font-size:11px;color:#9fb0ff;font-weight:600}
@media(max-width:900px){.lx{grid-template-columns:1fr}.lx-art{padding:8px 24px 40px}.lx-stage{width:min(82%,320px)}.lx-chip{display:none}.lx-art h2{font-size:23px}.lx-card{padding:30px 22px 24px}}
@media(prefers-reduced-motion:reduce){.lx *,.lx-bg{animation:none!important}}
</style>
<div class=lx>
<div class=lx-bg><span class="lx-orb o1"></span><span class="lx-orb o2"></span><span class="lx-orb o3"></span><div class=lx-dots><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i></div></div>
<section class=lx-form><div class=lx-card><div class=fw>
{{logo}}
{% if mode=='register' %}<div class=tbp><svg viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2 stroke-linecap=round stroke-linejoin=round><path d="M12 3l1.8 4.6L18 9l-4.2 1.4L12 15l-1.8-4.6L6 9l4.2-1.4zM19 15l.7 1.8 1.8.7-1.8.7L19 20l-.7-1.8-1.8-.7 1.8-.7z"/></svg>تجربة مجانية {{trial_days}} أيام · بدون بطاقة دفع</div>{% endif %}
<h1>{{title}}</h1>
<p class=sub>{% if mode=='register' %}أنشئ حسابك وابدأ تجربتك.{% elif mode=='login' %}أهلاً بعودتك 👋 سجّل دخولك لمتابعة القطع والصيانات.{% elif mode=='forgot' %}اكتب إيميل حسابك وبنرسلك رابط لتعيين كلمة سر جديدة.{% elif mode=='reset' %}اختر كلمة سر جديدة لحسابك.{% else %}هذا الرابط منتهي أو تم استخدامه من قبل.{% endif %}</p>
{% if err %}<div class=err role=alert>{{err}}</div>{% endif %}
{% if mode in ('login','register') %}<form method=post{% if mode=='register' %} enctype=multipart/form-data{% endif %}>{% if mode=='register' %}
<label class=lgbx for=lgf><span class=lgt><b>شعار الشركة</b><small>اختياري · حتى 2 ميجا</small></span><span class=lgi id=lgi><svg viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=1.8 stroke-linecap=round stroke-linejoin=round><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12"/></svg></span></label><input type=file id=lgf name=logo accept="image/png,image/jpeg,image/webp" hidden>
<div class=nm2><label>الاسم الكامل <i class=rq>*</i><span class=fi><svg viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=1.8 stroke-linecap=round stroke-linejoin=round><circle cx=12 cy=8 r=4 /><path d="M4 21a8 8 0 0116 0"/></svg><input name=full_name required value="{{f.full_name if f}}" autocomplete=name></span></label><label>رقم الهاتف <i class=rq>*</i><span class=fi><svg viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=1.8 stroke-linecap=round stroke-linejoin=round><path d="M22 16.9v3a2 2 0 01-2.2 2 19.8 19.8 0 01-8.6-3.1 19.5 19.5 0 01-6-6A19.8 19.8 0 012.1 4.2 2 2 0 014.1 2h3a2 2 0 012 1.7c.1 1 .4 1.9.7 2.8a2 2 0 01-.5 2.1L8.1 9.9a16 16 0 006 6l1.3-1.3a2 2 0 012.1-.4c.9.3 1.8.6 2.8.7a2 2 0 011.7 2z"/></svg><input name=phone type=tel required dir=ltr value="{{f.phone if f}}" autocomplete=tel></span></label></div>
<div class=nm2><label>اسم الشركة <i class=rq>*</i><span class=fi><svg viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=1.8 stroke-linecap=round stroke-linejoin=round><path d="M3 9l1-5h16l1 5M3 9v11h18V9M3 9a3 3 0 006 0 3 3 0 006 0 3 3 0 006 0M9 20v-6h6v6"/></svg><input name=shop_name required value="{{f.shop_name if f}}"></span></label><label>المدينة <i class=rq>*</i><span class=fi><svg viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=1.8 stroke-linecap=round stroke-linejoin=round><path d="M12 21s7-6.2 7-11.5a7 7 0 10-14 0C5 14.8 12 21 12 21z"/><circle cx=12 cy=9.5 r=2.5 /></svg><input name=city required value="{{f.city if f}}" autocomplete=address-level2></span></label></div>
<script>(function(){var i=document.getElementById('lgf'),b=document.getElementById('lgi');if(!i)return;i.addEventListener('change',function(){var f=i.files[0];if(!f)return;var r=new FileReader();r.onload=function(e){b.innerHTML='';var m=document.createElement('img');m.src=e.target.result;b.appendChild(m);b.classList.add('has')};r.readAsDataURL(f)})})();</script>
<style>.nm2{display:grid;grid-template-columns:1fr 1fr;gap:12px}.nm2 label{min-width:0}.rq{color:#e11d48;font-style:normal}.fi{position:relative;display:block;margin-top:6px}.fi input{margin:0!important;padding-inline-end:40px!important}.fi svg{position:absolute;top:50%;inset-inline-end:12px;transform:translateY(-50%);width:18px;height:18px;opacity:.55;pointer-events:none}
.lgbx{display:flex!important;justify-content:space-between;align-items:center;gap:12px;border:1px solid var(--line);border-radius:14px;padding:16px;margin-top:6px!important;cursor:pointer}.lgt b{display:block;font-size:15px}.lgt small{color:var(--mut);font-weight:400}
.lgi{width:64px;height:64px;border:1.5px dashed var(--mut);border-radius:12px;display:grid;place-items:center;flex-shrink:0;overflow:hidden;color:var(--mut)}.lgi svg{width:24px;height:24px}.lgi img{width:100%;height:100%;object-fit:contain}.lgi.has{border-style:solid}
.tbp{display:inline-flex;align-items:center;gap:8px;background:#4f46e51a;color:#4f46e5;border:1px solid #4f46e533;border-radius:99px;padding:6px 14px;font-size:13px;font-weight:600;margin-top:18px}.tbp svg{width:15px;height:15px}
.pw{position:relative}.pw .lk{position:absolute;top:50%;left:12px;right:auto;transform:translateY(-50%);width:18px;height:18px;opacity:.55;pointer-events:none}.pw input[name=password]{padding-left:40px!important;padding-right:46px!important}@media(max-width:480px){.nm2{grid-template-columns:1fr}}</style>
{% endif %}<label>{{ 'الإيميل أو اسم المستخدم' if mode=='login' else 'الإيميل' }}{% if mode=='register' %} <i class=rq style="font-style:normal">*</i>{% endif %}{% if mode=='register' %}<span class=fi><svg viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=1.8 stroke-linecap=round stroke-linejoin=round><rect x=3 y=5 width=18 height=14 rx=2 /><path d="M3 7l9 6 9-6"/></svg><input name=email type="{{ 'text' if mode=='login' else 'email' }}" required autofocus autocomplete=username dir=ltr></span>{% else %}<input name=email type="{{ 'text' if mode=='login' else 'email' }}" required autofocus autocomplete=username dir=ltr>{% endif %}</label>
{% if mode=='register' %}<label>اسم المستخدم <i class=rq>*</i><span class=fi><svg viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=1.8 stroke-linecap=round stroke-linejoin=round><circle cx=12 cy=8 r=4 /><path d="M4 21a8 8 0 0116 0"/></svg><input name=username required dir=ltr pattern="[A-Za-z0-9._-]{3,30}" value="{{f.username if f}}" autocomplete=username title="3-30 حرف إنجليزي أو أرقام أو . _ -"></span></label>{% endif %}
<div class=lrow><label for=pw>كلمة السر{% if mode=='register' %} <i class=rq style="font-style:normal">*</i> <small style="font-weight:400;color:var(--mut)">(6 أحرف على الأقل)</small>{% endif %}</label>{% if mode=='login' %}<a class=fgt href=/forgot>هل نسيت كلمة السر؟</a>{% endif %}</div>
<div class=pw>{% if mode=='register' %}<svg class=lk viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=1.8 stroke-linecap=round stroke-linejoin=round><rect x=4 y=11 width=16 height=10 rx=2 /><path d="M8 11V7a4 4 0 018 0v4"/></svg>{% endif %}<input id=pw name=password type=password required autocomplete="{{'new-password' if mode=='register' else 'current-password'}}" minlength="{{6 if mode=='register' else 0}}" dir=ltr><button type=button class=eye aria-label="إظهار / إخفاء كلمة السر"><svg viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=1.9 stroke-linecap=round stroke-linejoin=round><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx=12 cy=12 r=3 /></svg></button></div>
<button class=wide>{{ 'إنشاء الحساب وبدء التجربة' if mode=='register' else 'دخول' }}</button></form>
<p class=sw>{% if mode=='register' %}عندك حساب؟ <a href=/login>سجّل دخولك</a>{% else %}شركتك جديد؟ <a href=/register>أنشئ حساب وجرّب مجاناً</a>{% endif %}</p>
{% elif mode=='forgot' %}{% if sent %}<div class=okb>إذا كان هذا الإيميل مسجّل عندنا، رح توصلك رسالة فيها رابط تعيين كلمة السر (صالح لمدة {{mins}} دقيقة). تأكد كمان من مجلد الرسائل غير المرغوبة.</div>
{% else %}<form method=post><label>الإيميل<input name=email type=email required autofocus autocomplete=email dir=ltr></label><button class=wide>أرسل رابط الاستعادة</button></form>{% endif %}
<p class=sw><a href=/login>→ العودة لتسجيل الدخول</a></p>
{% elif mode=='reset' %}<form method=post><label for=pw>كلمة السر الجديدة</label><div class=pw><input id=pw name=password type=password minlength=6 required autofocus autocomplete=new-password><button type=button class=eye aria-label="إظهار / إخفاء كلمة السر"><svg viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=1.9 stroke-linecap=round stroke-linejoin=round><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx=12 cy=12 r=3 /></svg></button></div>
<label for=pw2>تأكيد كلمة السر</label><div class=pw><input id=pw2 name=password2 type=password minlength=6 required autocomplete=new-password></div>
<button class=wide>حفظ كلمة السر</button></form>
{% else %}<a class="btn wide" href=/forgot>اطلب رابط جديد</a><p class=sw><a href=/login>→ العودة لتسجيل الدخول</a></p>{% endif %}
</div></div></section>
<section class=lx-art>
<div class=lx-stage>
<svg viewBox="0 0 400 420" fill=none aria-hidden=true>
<defs><linearGradient id=lg1 x1=0 y1=0 x2=1 y2=1><stop offset=0 stop-color="#6d5efc"/><stop offset=1 stop-color="#22d3ee"/></linearGradient>
<linearGradient id=lg2 x1=0 y1=0 x2=0 y2=1><stop offset=0 stop-color="#1a2370"/><stop offset=1 stop-color="#0a1038"/></linearGradient>
<radialGradient id=lg3><stop offset=0 stop-color="#22d3ee" stop-opacity=".45"/><stop offset=1 stop-color="#22d3ee" stop-opacity="0"/></radialGradient></defs>
<circle cx=200 cy=215 r=190 fill="url(#lg3)"/>
<g stroke="#67e8f9" stroke-width=2.4 stroke-linecap=round opacity=.85>
<path class=lx-tr d="M0 90H70L110 130H140"/><path class="lx-tr s" d="M400 120H330L290 160H262"/><path class=lx-tr d="M0 300H60L100 260H140"/><path class="lx-tr s" d="M400 330H340L300 290H262"/><path class=lx-tr d="M200 0V40"/><path class="lx-tr s" d="M200 420V388"/></g>
<g fill="#060a22" stroke="#67e8f9" stroke-width=2.4><circle cx=70 cy=90 r=5 /><circle cx=330 cy=120 r=5 /><circle cx=60 cy=300 r=5 /><circle cx=340 cy=330 r=5 /></g>
<g class=lx-ph>
<rect x=122 y=40 width=156 height=330 rx=30 fill="url(#lg2)" stroke="url(#lg1)" stroke-width=4 />
<rect x=134 y=56 width=132 height=298 rx=20 fill="#0d1450" stroke="#ffffff1f"/>
<rect x=176 y=62 width=48 height=9 rx=4.5 fill="#060a22"/>
<g class=lx-gear><circle cx=200 cy=170 r=34 stroke="url(#lg1)" stroke-width=7 /><circle cx=200 cy=170 r=14 fill="url(#lg1)"/>
<g stroke="url(#lg1)" stroke-width=9 stroke-linecap=round><path d="M200 120v10M200 210v10M150 170h10M240 170h10M165 135l7 7M228 198l7 7M235 135l-7 7M172 198l-7 7"/></g></g>
<rect x=152 y=240 width=96 height=10 rx=5 fill="#ffffff22"/><rect x=152 y=240 width=62 height=10 rx=5 fill="url(#lg1)"/>
<rect x=152 y=268 width=44 height=44 rx=11 fill="#ffffff14" stroke="#ffffff22"/><rect x=204 y=268 width=44 height=44 rx=11 fill="#ffffff14" stroke="#ffffff22"/>
<path d="M165 290l8 8 14-16" stroke="#6ee7b7" stroke-width=4 stroke-linecap=round stroke-linejoin=round/><circle class=lx-pulse cx=226 cy=290 r=7 fill="#fbbf24"/>
</g></svg>
<div class="lx-chip c1"><span class=ic><svg viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2.2 stroke-linecap=round stroke-linejoin=round><path d="M3 17l6-6 4 4 8-8"/><path d="M15 7h6v6"/></svg></span><div><b>مربح اليوم</b><small>محسوب تلقائياً</small></div></div>
<div class="lx-chip c2"><span class=ic><svg viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2.2 stroke-linecap=round stroke-linejoin=round><path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9L2.4 18a2 2 0 001.7 3h15.8a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z"/></svg></span><div><b>تنبيه نقص قطع</b><small>قبل ما تخلص</small></div></div>
<div class="lx-chip c3"><span class=ic><svg viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2.2 stroke-linecap=round stroke-linejoin=round><path d="M6 9V3h12v6"/><rect x=3 y=9 width=18 height=8 rx=2 /><path d="M7 14h10v7H7z"/></svg></span><div><b>إيصال جاهز للطباعة</b><small>حراري وA4</small></div></div>
</div>
{% if mode=='register' %}<h2>جرّب REPAIRIX مجاناً لمدة {{trial_days}} أيام</h2><p>سجّل القطع، تابع الصيانات، واعرف مربحك كل يوم، بدون أي التزام.</p>
<ul class=pts><li><svg viewBox="0 0 24 24" fill=none stroke-width=2.6 stroke-linecap=round stroke-linejoin=round><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>مخزون القطع مرتب حسب النوع والجهاز</li><li><svg viewBox="0 0 24 24" fill=none stroke-width=2.6 stroke-linecap=round stroke-linejoin=round><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>إيصالات وفواتير موردين جاهزة للطباعة</li><li><svg viewBox="0 0 24 24" fill=none stroke-width=2.6 stroke-linecap=round stroke-linejoin=round><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>تنبيهات تلقائية للقطع الناقصة</li></ul>
{% else %}<h2>مخزونك وصيانتك بمكان واحد</h2><p>سجّل القطع، تابع كل جهاز عندك، واعرف مربحك كل يوم.</p>{% endif %}
<p class=tg>REPAIR &amp; INVENTORY MANAGEMENT</p></section></div>{% endblock %}"""
T["backs"] = """{% extends 'base' %}{% block c %}
{% macro lens(cx,cy,r) %}<circle cx="{{cx}}" cy="{{cy}}" r="{{r+1.6}}" fill="#000" fill-opacity=".22"/><circle cx="{{cx}}" cy="{{cy}}" r="{{r}}" fill="url(#ringg)"/><circle cx="{{cx}}" cy="{{cy}}" r="{{r-2.4}}" fill="#07070b" stroke="#000" stroke-opacity=".7" stroke-width=".8"/><circle cx="{{cx}}" cy="{{cy}}" r="{{r-4.6}}" fill="url(#lensg)"/><circle cx="{{cx}}" cy="{{cy}}" r="{{(r*0.45)|round(1)}}" fill="none" stroke="#7f8fe6" stroke-opacity=".35" stroke-width=".8"/><circle cx="{{cx}}" cy="{{cy}}" r="{{(r*0.2)|round(1)}}" fill="#05060d"/><ellipse cx="{{(cx-r*0.3)|round(1)}}" cy="{{(cy-r*0.36)|round(1)}}" rx="{{(r*0.3)|round(1)}}" ry="{{(r*0.15)|round(1)}}" fill="#fff" fill-opacity=".6" transform="rotate(-35 {{(cx-r*0.3)|round(1)}} {{(cy-r*0.36)|round(1)}})"/><circle cx="{{(cx+r*0.32)|round(1)}}" cy="{{(cy+r*0.34)|round(1)}}" r="{{(r*0.09)|round(1)}}" fill="#a9b8ff" fill-opacity=".75"/>{% endmacro %}
{% macro phone(kind, qty=0) %}{% if kind=='ip' %}<div class=ipx><i class=ic></i><img class=il src="/phone-img/ip_lens.png" alt=""><span class=pq><small>الكمية</small><b data-pq>{{qty}}</b></span></div>{% else %}<div class="ipx sx"><i class=ic></i><img class=il src="/phone-img/{{ 'sm_lens' if kind=='sm' else 'an_lens' }}.png" alt=""><span class=pq><small>الكمية</small><b data-pq>{{qty}}</b></span></div>{% endif %}{% endmacro %}
<svg width=0 height=0 style="position:absolute"><defs>
<linearGradient id="glx" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".42"/><stop offset=".5" stop-color="#fff" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".2"/></linearGradient>
<linearGradient id="ringg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#f6f6fa"/><stop offset=".42" stop-color="#8c8c98"/><stop offset=".7" stop-color="#dcdce3"/><stop offset="1" stop-color="#4f4f59"/></linearGradient>
<radialGradient id="lensg" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="#4658ad"/><stop offset=".45" stop-color="#151b40"/><stop offset="1" stop-color="#05060c"/></radialGradient>
<linearGradient id="edgeg" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#fff" stop-opacity=".6"/><stop offset=".07" stop-color="#fff" stop-opacity="0"/><stop offset=".93" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".38"/></linearGradient>
<linearGradient id="plg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".36"/><stop offset="1" stop-color="#000" stop-opacity=".2"/></linearGradient>
<radialGradient id="shn" cx=".18" cy=".08" r=".95"><stop offset="0" stop-color="#fff" stop-opacity=".38"/><stop offset=".55" stop-color="#fff" stop-opacity="0"/></radialGradient>
</defs></svg>
<section class=bs>
<div class=bs-i><small>عدد الموديلات</small><b>{{st.models}}</b></div>
<div class=bs-i><small>إجمالي القطع</small><b>{{st.n}}</b></div>
<div class=bs-i><small>قيمة المخزون (جملة)</small><b>{{ '%g'|format(st.val) }} ₪</b></div>
<div class=bs-i><small>الربح المتوقع</small><b class=cy>{{ '%g'|format(st.sell - st.val) }} ₪</b></div>
<div class=bs-h><small>حالة المخزون ({{st.cols}} لون)</small>
<div class=hbar>{% if st.cols %}<i class=a style="flex:{{st.ok}}"></i><i class=b style="flex:{{st.lowc}}"></i><i class=c style="flex:{{st.out}}"></i>{% endif %}</div>
<div class=hl><em style="color:#34d399">متوفر {{st.ok}}</em><em style="color:#fbbf24">منخفض {{st.lowc}}</em><em style="color:#fb7185">نفد {{st.out}}</em></div></div>
</section>
<div class=tools><div class=r1>
<label class=search>{{ic.sr}}<input id=bq placeholder="ابحث عن موديل أو لون..."></label>
<select id=bst aria-label="حالة المخزون"><option value="">كل الحالات<option value=low>فيه ألوان منخفضة<option value=out>فيه ألوان نافدة<option value=ok>كله متوفر</select>
<select id=bso aria-label="الترتيب"><option value=name:a>الترتيب: الاسم<option value=qty:d>الأكثر مخزوناً<option value=qty:a>الأقل مخزوناً<option value=val:d>الأعلى قيمة</select>
<button type=button data-open=dlg-back>+ إضافة موديل</button></div>
{% if blist|length > 1 %}<div class=r2 style="gap:8px"><button type=button class="cpill on" data-b="">الكل <em>{{st.models}}</em></button>{% for b,n in blist %}<button type=button class=cpill data-b="{{b}}">{{b}} <em>{{n}}</em></button>{% endfor %}</div>{% endif %}</div>
<dialog class=dlg id=dlg-back data-auto><form method=post>
<div class=dh><h3>إضافة موديل ظهر</h3><button type=button class=cl data-close aria-label="إغلاق">×</button></div>
<div class=db><div class=fg><label class=fa>اسم الموديل<input name=name list=mlist required placeholder="مثال: iPhone 14 Pro Max"></label>
<datalist id=mlist>{% for m in models %}<option value="{{m}}">{% endfor %}</datalist>
<label>سعر الجملة<input name=cost type=number step=any min=0 required></label><label>سعر البيع<input name=price type=number step=any min=0 required></label>
<label class=fa>المورد<select name=supplier_id><option value="">بدون{% for s in sup %}<option value={{s.id}}>{{s.name}}{% endfor %}</select></label></div>
<div style="margin-top:16px;font-weight:700;font-size:14px">الألوان <small>(اختر اللون، اكتب اسمه وكميته. الصفوف اللي بدون اسم لون تُتجاهل)</small></div>
<div class=crh><span>اللون</span><span>اسم اللون</span><span>الكمية</span></div>
<div id=crs>{% for h in ['#1f2937','#e5e7eb','#4f46e5','#d4a373'] %}<div class=cr><input type=color name=hex value="{{h}}" aria-label="اختيار اللون"><input name=color placeholder="مثال: أسود" aria-label="اسم اللون"><input name=qty type=number min=0 step=1 value=1 inputmode=numeric placeholder="الكمية" aria-label="الكمية"></div>{% endfor %}</div>
<button type=button class=ghost id=addcr style="margin:10px 0 0">+ لون آخر</button></div>
<div class=df><button>حفظ الموديل</button><button type=button class=ghost data-close>إلغاء</button></div></form></dialog>
{% include 'pedit' %}
{% if not models %}<div class="card bempty"><svg viewBox="0 0 24 24" width=44 height=44 fill=none stroke=currentColor stroke-width=1.5 stroke-linecap=round stroke-linejoin=round><path d="M6 2h12a2 2 0 012 2v16a2 2 0 01-2 2H6a2 2 0 01-2-2V4a2 2 0 012-2zM8 6h5v5H8z"/></svg><b>ما في موديلات ظهر بعد</b><span>أضف أول موديل مع ألوانه وكمياته وسيظهر هنا بشكل بطاقة.</span><button type=button data-open=dlg-back>+ إضافة موديل</button></div>{% endif %}
<div class=bgrid id=bgrid>
{% for name, cols in models.items() %}{% set first = cols[0] %}{% set tot = cols|sum(attribute='qty') %}{% set bn = loop.index %}
<article class=bm style="--bk:{{first.hex or '#888888'}}" data-n="{{name}}" data-s="{{name}}{% for c in cols %} {{c.color}}{% endfor %}" data-b="{{brands[name]}}" data-qty="{{tot}}" data-val="{{ flags[name].val }}" data-low="{{ flags[name].low }}" data-out="{{ flags[name].out }}">
<div class=bm-s>{{ phone(kinds[name], first.qty) }}</div>
<div class=bm-b>
<div class=bm-h><div><h3>{{name}}</h3><div class=bm-m>{% if brands[name] != 'أخرى' %}<span class=bb style="margin:0">{{brands[name]}}</span>{% endif %}<small>{{cols|length}} ألوان · {{tot}} قطعة</small></div></div>
<button type=button class="ib bm-add" title="إضافة لون لهذا الموديل" aria-label="إضافة لون" data-open=dlg-back data-fill='{{ {"name":name,"cost":first.cost,"price":first.price,"supplier_id":first.supplier_id or "","_t":"إضافة لون لموديل " ~ name}|tojson }}'><svg viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2.2 stroke-linecap=round><path d="M12 5v14M5 12h14"/></svg></button></div>
<div class=dist title="توزيع الألوان بالمخزون">{% for c in cols %}{% if c.qty > 0 %}<i style="flex:{{c.qty}};background:{{c.hex or '#888888'}}"></i>{% endif %}{% endfor %}{% if tot <= 0 %}<i style="flex:1;background:#e4e8f1"></i>{% endif %}</div>
<div class=bsws>{% for c in cols %}{% set hx = c.hex or '#888888' %}{% set lum = hx[1:3]|int(0,16)*0.299 + hx[3:5]|int(0,16)*0.587 + hx[5:7]|int(0,16)*0.114 %}<button type=button class="bsw {{'on' if loop.first}} {{'lt' if lum>150}}" style="--h:{{hx}}" data-h="{{hx}}" data-i={{loop.index}} title="{{c.color}} · الكمية {{c.qty}}" aria-label="{{c.color}} الكمية {{c.qty}}"><em class="{{'z' if c.qty<=0}}">{{c.qty}}</em></button>{% endfor %}</div>
{% for c in cols %}{% set lo = c.qty<=c.min_qty %}{% set mg = ((c.price-c.cost)*100/c.price)|round|int if c.price else 0 %}
<div class=bp data-i={{loop.index}} {{'hidden' if not loop.first}}>
<div class=bp-t><span class=bp-n><span class=dot style="background:{{c.hex or '#888'}}"></span>{{c.color}}</span><span class="pill {{'s3' if c.qty==0 else 's0' if lo else 's2'}}">{{'نفد' if c.qty==0 else 'منخفض' if lo else 'متوفر'}} · {{c.qty}}</span></div><div class=bcc><a href=# onclick="rxBc({{c.id}},'{{c.barcode or ''}}');return false" title="تعديل الباركود"><svg viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2 stroke-linecap=round><path d="M3 5v14M7 5v14M11 5v14M14 5v14M18 5v14M21 5v14"/></svg>{{c.barcode or '—'}}</a><a href="/barcodes?ids={{c.id}}" title="طباعة ملصق باركود">🖨</a></div>
<div class=pr3><div><small>الجملة</small><b>{{ '%g'|format(c.cost) }} ₪</b></div><div><small>البيع</small><b>{{ '%g'|format(c.price) }} ₪</b></div><div class=g><small>الربح · {{mg}}%</small><b>{{ '%g'|format(c.price-c.cost) }} ₪</b></div></div>
<div class=bp-f><form method=post action=/parts/{{c.id}}/stock class=stp><button name=n value=-1 class=stb title="إنقاص قطعة" aria-label="إنقاص">−</button><span class=sq>{{c.qty}}</span><button name=n value=1 class=stb title="زيادة قطعة" aria-label="زيادة">+</button></form>
<form method=post action=/parts/{{c.id}}/stock class=stp2><input name=n type=number min=1 value=5 aria-label="الكمية"><button class=ghost>إضافة كمية</button></form>
<button type=button class="ib ed" title="تعديل اللون" aria-label="تعديل" data-open=dlg-pedit data-fill='{{ {"_t":"تعديل: "~c.name~" · "~c.color,"_id":c.id,"_back":1,"name":c.name,"cost":c.cost,"price":c.price,"qty":c.qty,"min_qty":c.min_qty,"supplier_id":c.supplier_id or "","color":c.color or "","hex":c.hex or "#888888"}|tojson }}'>{{ic.ed}}</button><a class="ib dl" title="حذف اللون" aria-label="حذف اللون" href=/parts/{{c.id}}/delete onclick="return confirm('حذف هذا اللون؟')">{{ic.dl}}</a></div></div>{% endfor %}
</div></article>{% endfor %}</div>
<div class="card em" id=bno hidden>لا توجد موديلات مطابقة للبحث أو التصفية.</div>
<script>(function(){var grid=document.getElementById('bgrid');if(!grid)return;
try{var y=sessionStorage.getItem('bsy');if(y){sessionStorage.removeItem('bsy');window.scrollTo(0,+y)}}catch(e){}
var cards=[].slice.call(grid.querySelectorAll('.bm'));
function pick(c,i,save){var sw=c.querySelector('.bsw[data-i="'+i+'"]');if(!sw)return;c.style.setProperty('--bk',sw.dataset.h);var pq=c.querySelector('[data-pq]');if(pq){var e=sw.querySelector('em');pq.textContent=e?e.textContent:'';pq.parentNode.classList.toggle('z',!!(e&&e.classList.contains('z')))}
c.querySelectorAll('.bsw').forEach(function(x){x.classList.toggle('on',x===sw)});c.querySelectorAll('.bp').forEach(function(p){p.hidden=p.dataset.i!==String(i)});
if(save){try{localStorage.setItem('bk:'+c.dataset.n,i)}catch(e){}}}
cards.forEach(function(c){try{var i=localStorage.getItem('bk:'+c.dataset.n);if(i)pick(c,i,false)}catch(e){}});
grid.addEventListener('click',function(e){var sw=e.target.closest('.bsw');if(sw)pick(sw.closest('.bm'),sw.dataset.i,true)});
grid.addEventListener('submit',function(){try{sessionStorage.setItem('bsy',window.scrollY)}catch(e){}});
var qi=document.getElementById('bq'),st=document.getElementById('bst'),so=document.getElementById('bso'),br='';
function run(){var v=qi.value.trim().toLowerCase(),s=st.value,shown=0;
cards.forEach(function(c){var ok=(c.dataset.s||'').toLowerCase().indexOf(v)>=0&&(!br||c.dataset.b===br);
if(ok&&s==='low')ok=c.dataset.low==='1';else if(ok&&s==='out')ok=c.dataset.out==='1';else if(ok&&s==='ok')ok=c.dataset.low!=='1'&&c.dataset.out!=='1';
c.style.display=ok?'':'none';if(ok)shown++});
var p=so.value.split(':'),k=p[0],d=p[1]==='d'?-1:1;
cards.slice().sort(function(a,b){if(k==='name')return a.dataset.n.localeCompare(b.dataset.n,'en',{numeric:true});return(parseFloat(a.dataset[k])-parseFloat(b.dataset[k]))*d}).forEach(function(c){grid.appendChild(c)});
var nb=document.getElementById('bno');if(nb)nb.hidden=shown>0||!cards.length}
[qi,st,so].forEach(function(x){x.addEventListener('input',run)});
document.addEventListener('click',function(e){var p=e.target.closest('.cpill[data-b]');if(p){br=p.dataset.b;run()}});
var add=document.getElementById('addcr');if(add)add.addEventListener('click',function(){var box=document.getElementById('crs'),r=box.lastElementChild.cloneNode(true);
r.querySelectorAll('input').forEach(function(i){if(i.type!=='color')i.value=i.name==='qty'?1:''});box.appendChild(r);r.querySelector('input[name=color]').focus()})})();</script>
{% endblock %}"""

T["pedit"] = """<style>label[hidden]{display:none!important}</style><dialog class=dlg id=dlg-pedit><form method=post action=/parts/0/edit id=pe-f>
<div class=dh><h3>تعديل القطعة</h3><button type=button class=cl data-close aria-label="إغلاق">×</button></div>
<div class=db><div class=fg>
<label class=fa>الاسم<input name=name required></label>
<label>سعر الجملة<input name=cost type=number step=any min=0 required></label><label>سعر البيع<input name=price type=number step=any min=0 required></label>
<label>الكمية<input name=qty type=number min=0 step=1 required></label><label>حد التنبيه<input name=min_qty type=number min=0 step=1></label>
<label id=pe-col class=fa hidden>اللون<span style="display:flex;gap:8px;align-items:center"><input type=color name=hex aria-label="اختيار اللون" style="width:56px;flex:none"><input name=color placeholder="اسم اللون" aria-label="اسم اللون" style="flex:1"></span></label>
<label class=fa id=pe-mk hidden>الشركة المصنعة<input name=maker list=mklist maxlength=60 placeholder="مثال: أصلية، OEM، JK، GX..."></label>
<label class=fa>المورد<select name=supplier_id><option value="">بدون{% for s in sup %}<option value={{s.id}}>{{s.name}}{% endfor %}</select></label>
{% if cats is defined %}<label class=fa id=pe-cat>النوع<select name=category>{% for c in cats %}<option>{{c}}{% endfor %}</select></label>{% endif %}
<label class=fa id=pe-all hidden style="display:flex;gap:8px;align-items:center"><input type=checkbox name=apply_all value=1 checked style="width:auto;margin:0"> طبّق الاسم وسعر الجملة والبيع على كل ألوان هذا الموديل</label>
</div></div>
<div class=df><button>حفظ التعديلات</button><button type=button class=ghost data-close>إلغاء</button></div></form></dialog>
<script>document.addEventListener('click',function(e){var b=e.target.closest('[data-open=dlg-pedit]');if(!b||!b.dataset.fill)return;var m=JSON.parse(b.dataset.fill),f=document.getElementById('pe-f'),bk=m._back==1;f.action='/parts/'+m._id+'/edit';document.getElementById('pe-col').hidden=!bk;document.getElementById('pe-all').hidden=!bk;document.getElementById('pe-mk').hidden=!(m.category=='شاشة'||m.category=='بطارية');var c=document.getElementById('pe-cat');if(c)c.hidden=bk;f.color.required=bk});</script>"""

T["suppliers"] = """{% extends 'base' %}{% block c %}
<div class=tools><div class=r1><label class=search>{{ic.sr}}<input data-f=stbl data-role=search placeholder="بحث عن مورد..."></label><button type=button data-open=dlg-sup>+ إضافة مورد</button></div></div>
<dialog class=dlg id=dlg-sup data-auto><form method=post>
<div class=dh><h3>إضافة مورد</h3><button type=button class=cl data-close aria-label="إغلاق">×</button></div>
<div class=db><div class=fg><label>الاسم<input name=name required></label><label>الهاتف<input name=phone></label><label class=fa>ملاحظات<input name=notes></label></div></div>
<div class=df><button>حفظ المورد</button><button type=button class=ghost data-close>إلغاء</button></div></form></dialog>
<dialog class=dlg id=dlg-supedit><form method=post action=/suppliers/edit><input type=hidden name=sid>
<div class=dh><h3>تعديل المورد</h3><button type=button class=cl data-close aria-label="إغلاق">×</button></div>
<div class=db><div class=fg><label>الاسم<input name=name required></label><label>الهاتف<input name=phone></label><label class=fa>ملاحظات<input name=notes></label></div></div>
<div class=df><button>حفظ التعديلات</button><button type=button class=ghost data-close>إلغاء</button></div></form></dialog>
<dialog class=dlg id=dlg-suppay><form method=post action=/suppliers/pay enctype=multipart/form-data onsubmit="if(this.pm.value==='بنك'&&!this.receipt.files.length){alert('أرفق وصل التحويل البنكي');return false}"><input type=hidden name=sid>
<div class=dh><h3>تسجيل دفعة لمورد</h3><button type=button class=cl data-close aria-label="إغلاق">×</button></div>
<div class=db><div class=fg><label class=fa>المورد<input name=sname readonly></label>
<label>المبلغ (₪)<input name=amount type=number step=any min=0.01 required></label>
<label>طريقة الدفع<select name=pm><option value=نقد>نقداً (كاش)<option value=بنك>تحويل بنكي</select></label>
<label>التاريخ (فاضي = اليوم)<input type=date name=created></label>
<label class=fa>وصل التحويل (إلزامي مع الدفعة البنكية) — صورة أو PDF<input type=file name=receipt accept="image/*,application/pdf"></label>
<label class=fa>ملاحظة<input name=note placeholder="اختياري"></label></div>
<p class=hint>الدفعة بتنسجّل لحالها بالصندوق المالي (نقد أو بنك) وبتنخصم من المتبقي للمورد.</p></div>
<div class=df><button>حفظ الدفعة</button><button type=button class=ghost data-close>إلغاء</button></div></form></dialog>
{% for s in sup %}{% set P = pur.get(s.id) %}{% set S = stk.get(s.id, []) %}
<dialog class="dlg wd" id="dlg-cart-{{s.id}}"><div class=dh><h3>المشتريات من: {{s.name}}</h3><button type=button class=cl data-close aria-label="إغلاق">×</button></div>
<div class=db>
<div class="hero3 h2"><div class=st>عدد القطع المشتراة (صافي)<b>{{ P.qty if P else 0 }}</b></div><div class=st>صافي المشتريات<b>{{ '%g'|format(P.net if P else 0) }} ₪</b></div><div class=st>آخر شراء<b style="font-size:17px">{{ (P.last if P and P.last else '—') }}</b></div></div>
{% set A = acc.get(s.id) or {'inv':0,'paid':0,'rem':0} %}{% set PY = pays.get(s.id, []) %}
<div class="hero3 h2"><div class=st>إجمالي فواتير المورد<b>{{ '%g'|format(A.inv) }} ₪</b></div><div class=st>المدفوع له<b>{{ '%g'|format(A.paid) }} ₪</b></div><div class=st>المتبقي عليك<b style="color:{{ 'var(--red)' if A.rem>0 else 'inherit' }}">{{ '%g'|format(A.rem) }} ₪</b></div></div>
<div class=dsec>دفعات للمورد</div>
<p style="margin:6px 0 10px"><button type=button data-open=dlg-suppay data-fill='{{ {"sid": s.id, "sname": s.name, "amount": (A.rem if A.rem>0 else ""), "pm": "نقد", "note": "", "created": "", "receipt": ""}|tojson }}'>+ تسجيل دفعة للمورد</button></p>
{% if PY %}<div style="overflow-x:auto"><table class=mini><tr><th>التاريخ<th>المبلغ<th>الطريقة<th>الوصل<th>ملاحظة<th></tr>
{% for p in PY %}<tr><td class=nw>{{p.created}}<td class=nw><b>{{ '%g'|format(p.amount) }} ₪</b><td><span class=tag>{{ 'تحويل بنكي' if p.account=='بنك' else 'نقداً' }}</span><td>{% if p.receipt %}<a href=/payreceipt/{{p.receipt}} target=_blank>🧾 عرض الوصل</a>{% else %}<small>—</small>{% endif %}<td>{{p.note}}<td><form method=post action=/suppliers/pay/{{p.id}}/delete class=il onsubmit="return confirm('حذف الدفعة؟ (بتنشال من الصندوق كمان)')"><button class="ib dl" title="حذف" aria-label="حذف">{{ic.dl}}</button></form></tr>{% endfor %}</table></div>
{% else %}<div class=em style="margin-bottom:10px">ما في دفعات مسجّلة لهذا المورد.</div>{% endif %}
<div class=pfx><button type=button data-pftoggle>+ فاتورة شراء جديدة</button>
<form method=post style="display:none;margin-top:14px;padding:14px;border:1px dashed #cdd5e8;border-radius:12px" action=/suppliers/{{s.id}}/purchase>
<div class="prow phd"><span>اسم القطعة</span><span>الكمية</span><span>سعر الجملة</span><span>المجموع</span><span></span></div>
<div class=prs>{% for _ in range(3) %}<div class=prow><input name=name placeholder="اسم القطعة"><input name=qty type=number min=1 value=1 inputmode=numeric><input name=cost type=number step=any min=0 placeholder=0 inputmode=decimal><input class=pt readonly tabindex=-1 value=0><button type=button class=rx aria-label="حذف السطر" title="حذف السطر">×</button></div>{% endfor %}</div>
<p style="margin:6px 0"><button type=button class=ghost data-addrow>+ سطر جديد</button></p>
<div class=gt><span>المجموع الكلي</span><span><span data-gt>0</span> ₪</span></div>
<p style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:0"><button name=print value=1>{{ic.pr}} حفظ وطباعة حرارية</button><button name=print value=2>{{ic.pr}} حفظ وطباعة A4</button><button name=print value=0 class=ghost>حفظ فقط</button></p>
</form></div>
<div class=dsec>القطع التي اشتريتها من هذا المورد</div>
{% if P %}<div style="overflow-x:auto"><table class=mini><tr><th>التاريخ<th>الصنف<th>النوع<th>الكمية<th>سعر الوحدة<th>المجموع<th>الفاتورة</tr>
{% for r in P.rows %}<tr><td class=nw>{{r.created}}<td><b>{{r.name}}</b>{% if r.note %}<br><small>{{r.note}}</small>{% endif %}<td><span class="tag {{'bad' if r.kind=='مرتجع'}}">{{r.kind}}</span><td>{{r.qty}}<td>{{ '%g'|format(r.cost) }}<td class=nw>{{ '%g'|format(r.total) }} ₪
<td class=nw>{% if r.invoice_id %}<a href=/invoices/{{r.invoice_id}}/thermal target=_blank>INV-{{'%04d'|format(r.invoice_id)}} · طباعة</a>{% else %}<small>بند مفتوح</small>{% endif %}</tr>{% endfor %}</table></div>
{% else %}<div class=em>ما في مشتريات مسجّلة من هذا المورد. أضف بنود شراء من صفحة "متطلبات الصيانة" واختر هذا المورد.</div>{% endif %}
{% if S %}<div class=dsec>قطع المخزون المرتبطة بهذا المورد</div><div style="overflow-x:auto"><table class=mini><tr><th>القطعة<th>النوع<th>الكمية بالمخزن<th>سعر الجملة</tr>
{% for r in S %}<tr><td><b>{{r.name}}</b>{% if r.color %} · {{r.color}}{% endif %}<td>{{r.category}}<td>{{r.qty}}<td>{{ '%g'|format(r.cost) }} ₪</tr>{% endfor %}</table></div>{% endif %}
</div>
<div class=df><a class=btn target=_blank href=/suppliers/{{s.id}}/print>{{ic.pr}} طباعة حرارية</a><a class="btn ghost" target=_blank href=/suppliers/{{s.id}}/a4>{{ic.pr}} طباعة A4</a><button type=button class=ghost data-close>إغلاق</button></div></dialog>
{% endfor %}
<div class=card><table class=srt id=stbl><tr><th>المورد<th>الهاتف<th>ملاحظات<th>المتبقي للمورد<th class=ns>إجراءات</tr>
{% for s in sup %}<tr><td><b>{{s.name}}</b><td>{{s.phone}}<td>{{s.notes}}<td class=nw>{% set a_ = acc.get(s.id) %}{% if a_ %}<b style="color:{{ 'var(--red)' if a_.rem>0 else 'inherit' }}">{{ '%g'|format(a_.rem) }} ₪</b>{% else %}<small>—</small>{% endif %}<td><div class=sa><button type=button class="ib ed" title="تسجيل دفعة للمورد" aria-label="تسجيل دفعة للمورد" data-open=dlg-suppay data-fill='{{ {"sid": s.id, "sname": s.name, "amount": ((a_.rem if a_.rem>0 else "") if a_ else ""), "pm": "نقد", "note": "", "created": "", "receipt": ""}|tojson }}'>₪</button>
<button type=button class="ib ct" title="المشتريات من المورد" aria-label="المشتريات من المورد" data-open="dlg-cart-{{s.id}}">{{ic.ct}}{% if pur.get(s.id) %}<span class=cn>{{ pur.get(s.id).rows|length }}</span>{% endif %}</button>
<button type=button class="ib ed" title="تعديل" aria-label="تعديل" data-open=dlg-supedit data-fill='{{ {"sid": s.id, "name": s.name, "phone": s.phone or "", "notes": s.notes or ""}|tojson }}'>{{ic.ed}}</button>
<a class="ib pr" title="طباعة حرارية" aria-label="طباعة حرارية" target=_blank href=/suppliers/{{s.id}}/print>{{ic.pr}}</a><a class="ib pr" title="طباعة A4" aria-label="طباعة A4" target=_blank href=/suppliers/{{s.id}}/a4>{{ic.pr}}<small style="font-size:9px;font-weight:800">A4</small></a>
<a class="ib dl" title="حذف" aria-label="حذف" href=/suppliers/{{s.id}}/delete onclick="return confirm('حذف المورد؟')">{{ic.dl}}</a></div></tr>
{% else %}<tr><td colspan=5 class=em>ما في موردين بعد.</tr>{% endfor %}</table></div>
<script>(function(){function calc(f){var t=0;f.querySelectorAll('.prs .prow').forEach(function(r){var i=r.querySelectorAll('input'),v=(parseFloat(i[1].value)||0)*(parseFloat(i[2].value)||0);i[3].value=v?+v.toFixed(2):0;t+=v});f.querySelector('[data-gt]').textContent=+t.toFixed(2)}
document.addEventListener('input',function(e){var f=e.target.closest('.pfx form');if(f)calc(f)});
document.addEventListener('click',function(e){var tg=e.target.closest('[data-pftoggle]');if(tg){var fm=tg.parentNode.querySelector('form');fm.style.display=fm.style.display==='none'?'block':'none';return}var f=e.target.closest('.pfx form');if(!f)return;var a=e.target.closest('[data-addrow]');
if(a){var b=f.querySelector('.prs'),c=b.lastElementChild.cloneNode(true);c.querySelectorAll('input').forEach(function(i){if(!i.readOnly)i.value='';else i.value=0});c.querySelector('[name=qty]').value=1;b.appendChild(c);c.querySelector('input').focus();return}
var x=e.target.closest('.rx');if(x){var b=f.querySelector('.prs');if(b.children.length>1)x.parentNode.remove();else x.parentNode.querySelectorAll('input').forEach(function(i){i.value=i.name=='qty'?1:0;if(i.name=='name')i.value=''});calc(f)}});
document.addEventListener('submit',function(e){var f=e.target.closest('.pfx form');if(!f)return;var ok=[].some.call(f.querySelectorAll('.prs [name=name]'),function(i){return i.value.trim()});if(!ok){e.preventDefault();alert('اكتب اسم قطعة واحدة على الأقل')}});})();</script>
<script>(function(){var m=/[?&]open=([0-9]+)/.exec(location.search);if(m){var d=document.getElementById('dlg-cart-'+m[1]);if(d&&!d.open)d.showModal();history.replaceState(null,'','/suppliers')}})();</script>{% endblock %}"""

T["thcss"] = """<style id=pg>@page{size:80mm auto;margin:0}</style>
<style>
*{box-sizing:border-box;-webkit-print-color-adjust:exact;print-color-adjust:exact}
html,body{background:#fff;color:#000}
body{margin:0;font-family:Tahoma,"Segoe UI",Arial,sans-serif;font-weight:700;font-size:12.5px;line-height:1.5}
.tk{width:72mm;margin:0 auto;padding:4mm 0 12mm}
body.w58 .tk{width:50mm;font-size:11px}
.i{width:15px;height:15px;flex:none}
.head{text-align:center;padding-bottom:6px;border-bottom:2px solid #000}
.head .lg{display:inline-grid;place-items:center;width:44px;height:44px;border:2.5px solid #000;border-radius:50%}
.head .lg .i{width:24px;height:24px}
.shop{font-size:20px;font-weight:900;margin:5px 0 0;line-height:1.3}
.ttl{display:block;width:max-content;max-width:100%;margin:9px auto 8px;padding:3px 16px;border:2px solid #000;border-radius:99px;font-size:13.5px;font-weight:900;text-align:center}
.ref{text-align:center;font-size:15px;font-weight:900;letter-spacing:.5px;margin:-2px 0 6px}
.inf{margin:2px 0 4px}
.f{display:flex;align-items:flex-end;gap:5px;padding:2.5px 0}
.f .k{font-weight:900;white-space:nowrap;display:flex;align-items:center;gap:4px}
.f .dl{flex:1;border-bottom:1.5px dotted #000;min-width:6px;margin-bottom:4px}
.f .v{word-break:break-word;text-align:left;max-width:62%}
.dash{border:0;border-top:2px dashed #000;margin:8px 0}
table{width:100%;border-collapse:collapse;table-layout:fixed;margin-top:4px}
th{padding:4px 2px;text-align:center;font-size:11.5px;font-weight:900;border-top:2px solid #000;border-bottom:2px solid #000}
td{padding:5px 2px;text-align:center;vertical-align:middle;word-break:break-word;overflow-wrap:anywhere;border-bottom:1.5px dashed #000}
td.nm{text-align:right;padding:5px 3px 5px 5px;font-size:12px}
td small{display:block;font-size:10px;font-weight:700}
.rt{display:inline-block;border:1.5px solid #000;border-radius:4px;padding:0 4px;font-size:10px;font-weight:900;margin-top:1px}
tr{page-break-inside:avoid}
body.w58 .cn{display:none}
.sum{margin-top:6px}.sum td{border:0;font-size:12.5px;padding:2.5px 3px}.sum .k{text-align:right;font-weight:900;width:60%}.sum .k .i{vertical-align:-3px;margin-left:3px}.sum td:last-child{text-align:left}
.tot{display:flex;justify-content:space-between;align-items:center;margin-top:8px;padding:7px 10px;background:#000;color:#fff;border-radius:8px;font-size:15px;font-weight:900}
.tot b{font-size:19px;font-weight:900;direction:ltr}
.st{display:inline-block;border:2px solid #000;border-radius:6px;padding:0 8px;font-weight:900}
.nt{text-align:center;border:2px solid #000;border-radius:8px;padding:6px;margin:6px 0}
.ft{text-align:center;margin-top:12px;font-size:13px;font-weight:900}
.ft small{display:block;font-weight:700;font-size:10.5px;margin-top:2px}
.cut{margin-top:12px;border-top:2px dashed #000;text-align:center;height:0}
.cut span{position:relative;top:-10px;background:#fff;padding:0 8px;font-size:14px}
.bar{background:#eee;padding:10px;text-align:center;font-family:Tahoma,sans-serif;font-weight:400}
.bar button{margin:3px 4px;padding:8px 18px;font:inherit;border:1px solid #333;background:#fff;border-radius:6px;cursor:pointer}
@media print{.bar{display:none}.tk{padding-top:0}}
</style>
<script>function sw(w){document.body.className=w==='w58'?'w58':'';document.getElementById('pg').textContent='@page{size:'+(w==='w58'?'58':'80')+'mm auto;margin:0}';try{localStorage.setItem('tw',w)}catch(e){}}
try{var w=localStorage.getItem('tw');if(w==='w58')sw(w)}catch(e){}
if(/[?&]auto=1/.test(location.search))window.addEventListener('load',function(){setTimeout(print,300)});</script>"""

T["thermal"] = """<!doctype html><html lang=ar dir=rtl><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>{{doc_title}} {{ref}}</title>
{% include 'thcss' %}
<div class=bar><button type=button onclick="history.length>1?history.back():location.href='{{back}}'">← رجوع</button><button onclick="print()">طباعة</button><button onclick="sw('w80')">ورق 80 مم</button><button onclick="sw('w58')">ورق 58 مم</button><a href="{{a4_url}}"><button type=button>نسخة A4</button></a>{% if can_stock %}<a href="?{{ '' if with_stock else 'stock=1' }}"><button type=button>{{ 'بدون قطع المخزون' if with_stock else 'مع قطع المخزون' }}</button></a>{% endif %}</div>
<div class=tk>
<span class=ttl>{{doc_title}}</span>
{% if ref %}<div class=ref dir=ltr>{{ref}}</div>{% endif %}
<div class=head><span class=lg>{{thic.store}}</span><h1 class=shop>{{st.shop_name}}</h1></div>{% if st.address %}<div style="text-align:center;font-size:11px;margin:2px 0 4px">{{st.address}}</div>{% endif %}
<div class=inf>
<div class=f><span class=k>{{thic.user}}{{ party_label or 'المورد' }}</span><span class=dl></span><span class=v>{{party or '—'}}</span></div>
{% if phone %}<div class=f><span class=k>{{thic.phone}}الهاتف</span><span class=dl></span><span class=v dir=ltr>{{phone}}</span></div>{% endif %}
<div class=f><span class=k>{{thic.cal}}التاريخ</span><span class=dl></span><span class=v dir=ltr>{{now}}</span></div>
</div>
{% if lines %}
<table><colgroup><col class=cn style="width:8%"><col style="width:38%"><col style="width:14%"><col style="width:18%"><col style="width:22%"></colgroup>
<tr><th class=cn>#<th>الصنف<th>الكمية<th>السعر<th>المجموع</tr>
{% for l in lines %}<tr><td class=cn>{{l.n}}<td class=nm>{{l.name}}{% if l.kind=='مرتجع' %}<br><span class=rt>مرتجع</span>{% endif %}{% if not ref %}<small dir=ltr>{{l.date}}</small>{% endif %}<td>{{l.qty}}<td dir=ltr>{{ '%g'|format(l.cost) }}<td dir=ltr>{{ '%g'|format(l.signed) }}</tr>{% endfor %}</table>
<table class=sum><tr><td class=k>عدد البنود<td dir=ltr>{{lines|length}}</tr>
<tr><td class=k>عدد القطع<td dir=ltr>{{qty}}</tr>
{% if ret_total %}<tr><td class=k>{{ lbl_buy or 'المشتريات' }}<td dir=ltr>{{ '%g'|format(buy_total) }} ₪</tr><tr><td class=k>{{ lbl_ret or 'المرتجعات' }}<td dir=ltr>-{{ '%g'|format(ret_total) }} ₪</tr>{% endif %}</table>
<div class=tot><span>الصافي</span><b>{{ '%g'|format(net) }} ₪</b></div>
{% else %}<div class=nt>{{ empty_msg or 'لا توجد مشتريات مسجّلة' }}</div>{% endif %}
{% if stk %}<span class=ttl>قطع المخزون من هذا المورد</span>
<table><colgroup><col style="width:56%"><col style="width:20%"><col style="width:24%"></colgroup><tr><th>الصنف<th>الكمية<th>الجملة</tr>
{% for r in stk %}<tr><td class=nm>{{r.name}}{% if r.color %} · {{r.color}}{% endif %}<td>{{r.qty}}<td dir=ltr>{{ '%g'|format(r.cost) }}</tr>{% endfor %}</table>{% endif %}
{% if sigs %}<div style="margin-top:16px;font-size:12px">توقيع المستلم: ______________</div>{% endif %}<div class=ft>شكراً لتعاملكم معنا</div>
<div class=cut><span>✂</span></div>
</div></html>
"""

T["a4doc"] = """<!doctype html><html lang=ar dir=rtl><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>{{doc_title}} {{ref}}</title>
<style>
@page{size:A4;margin:10mm 10mm 15mm;@bottom-left{content:"صفحة " counter(page) " من " counter(pages);font:600 10px Tahoma,Arial,sans-serif;color:#5b6b68}}
*{box-sizing:border-box;-webkit-print-color-adjust:exact;print-color-adjust:exact}
:root{--g:#0b6b5e;--g2:#0f9d8a;--gl:#e6f5f2;--am:#f59e0b;--rose:#e11d48;--ink:#16322e;--mut:#5b6b68;--ln:#d5e4e0}
html,body{margin:0;background:#dfe7e5;color:var(--ink)}
body{font-family:Tahoma,"Segoe UI",Arial,sans-serif;font-size:13px;line-height:1.55}
.bar{background:#0b2f2a;padding:10px;text-align:center;position:sticky;top:0;z-index:5}
.bar button{margin:3px 4px;padding:8px 18px;font:inherit;border:0;background:#fff;color:#0b2f2a;border-radius:8px;cursor:pointer;font-weight:700}
.bar button.p{background:var(--am)}
.sheet{width:210mm;margin:14px auto;background:#fff;box-shadow:0 6px 28px rgba(0,0,0,.2)}
table.pg{width:100%;border-collapse:collapse}
table.pg>thead{display:table-header-group}table.pg>tfoot{display:table-footer-group}
table.pg>thead>tr>td,table.pg>tfoot>tr>td,table.pg>tbody>tr>td{padding:0}
.run{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:7px 10mm;background:var(--g);color:#fff;font-weight:700;font-size:12px}
.run .l{display:flex;align-items:center;gap:8px;font-size:14px}.run .l svg{width:22px;height:22px;fill:#fff}
.run .m{background:rgba(255,255,255,.16);padding:2px 12px;border-radius:99px}
.runf{display:flex;justify-content:space-between;gap:10px;padding:6px 10mm;border-top:3px solid var(--g2);color:var(--mut);font-size:10.5px;background:#f4faf8}
.body{padding:6mm 10mm 4mm}
.hero{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:16px 20px;border-radius:18px;color:#fff;background:linear-gradient(120deg,var(--g) 0%,var(--g2) 100%)}
.hero h1{margin:0;font-size:25px;line-height:1.2}.hero .ref{display:inline-block;margin-top:6px;background:var(--am);color:#3a2600;font-weight:800;padding:2px 14px;border-radius:99px;font-size:12.5px}
.hero .amt{text-align:left}.hero .amt small{display:block;opacity:.85;font-size:12px}.hero .amt b{font-size:30px;letter-spacing:.3px}
.cards{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:12px}
.card{border:1.5px solid var(--ln);border-radius:16px;padding:10px 14px;background:#fff}
.card h3{margin:0 0 6px;font-size:13px;color:var(--g)}
.row{display:flex;align-items:center;gap:10px;padding:4px 0}
.row .t{width:30px;height:30px;border-radius:9px;display:flex;align-items:center;justify-content:center;flex:none}
.row .t svg{width:17px;height:17px;fill:currentColor}
.t.a{background:#ddf3ee;color:var(--g)}.t.b{background:#fff1d6;color:#b86e00}.t.c{background:#ffe3ea;color:var(--rose)}.t.d{background:#e4e9ff;color:#3b4cca}
.row small{display:block;color:var(--mut);font-size:10.5px;line-height:1.2}.row b{font-size:13.5px}
.items{width:100%;border-collapse:separate;border-spacing:0;margin-top:14px;border:1.5px solid var(--ln);border-radius:14px;overflow:hidden}
.items thead{display:table-header-group}
.items th{background:var(--g);color:#fff;padding:8px 8px;font-size:12px;text-align:right}
.items td{padding:7px 8px;border-top:1px solid var(--ln);vertical-align:middle}
.items tr{break-inside:avoid;page-break-inside:avoid}
.items tbody tr:nth-child(even) td{background:#f4faf8}
.items tr.rt td{background:#fff0f3!important;color:#9c1239}
.n{width:34px;text-align:center;color:var(--mut)}.num{white-space:nowrap;text-align:left;font-variant-numeric:tabular-nums}
.chip{display:inline-block;padding:0 9px;border-radius:99px;font-size:10.5px;font-weight:800;background:var(--rose);color:#fff;margin-right:6px}
.dt{display:block;color:var(--mut);font-size:10.5px}
.bottom{display:grid;grid-template-columns:1fr 280px;gap:14px;margin-top:14px;break-inside:avoid;page-break-inside:avoid}
.note svg{width:14px;height:14px;fill:var(--g);vertical-align:-2px;margin-left:4px}
.note{border:1.5px dashed var(--ln);border-radius:14px;padding:10px 14px;color:var(--mut);font-size:11.5px}
.sum{border-radius:16px;overflow:hidden;border:1.5px solid var(--ln)}
.sum div{display:flex;justify-content:space-between;padding:7px 14px;border-top:1px solid var(--ln)}.sum div:first-child{border-top:0}
.sum .net{background:var(--g);color:#fff;font-size:16px;font-weight:800}
.sigs{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:16px;break-inside:avoid;page-break-inside:avoid}
.sigs div{border-top:2px solid var(--ink);padding-top:5px;text-align:center;color:var(--mut);padding-bottom:18px;font-size:12px}
.sigs svg{width:14px;height:14px;fill:var(--g);vertical-align:-2px}
.h2{margin:16px 0 0;font-size:14px;color:var(--g)}
@media print{html,body{background:#fff}.bar{display:none}.sheet{width:auto;margin:0;box-shadow:none}}
</style>
<div class=bar><button type=button onclick="history.length>1?history.back():location.href='{{back}}'">← رجوع</button><button class=p onclick="print()">طباعة / حفظ PDF</button><a href="{{th_url}}"><button type=button>نسخة حرارية</button></a>{% if can_stock %}<a href="?{{ '' if with_stock else 'stock=1' }}"><button type=button>{{ 'بدون قطع المخزون' if with_stock else 'مع قطع المخزون' }}</button></a>{% endif %}</div>
<div class=sheet><table class=pg>
<thead><tr><td><div class=run><span class=l>{{a4ic.shop}}<span>{{st.shop_name}}</span></span><span class=m>{{doc_title}}{% if ref %} · {{ref}}{% endif %}</span><span dir=ltr>{{now}}</span></div></td></tr></thead>
<tfoot><tr><td><div class=runf><span>{{st.shop_name}} — {{doc_title}}{% if ref %} {{ref}}{% endif %}</span><span>{{party or ''}}</span></div></td></tr></tfoot>
<tbody><tr><td><div class=body>
<div class=hero><div><h1>{{doc_title}}</h1>{% if ref %}<span class=ref dir=ltr>{{ref}}</span>{% endif %}</div><div class=amt><small>{{ net_label or 'الصافي المستحق' }}</small><b dir=ltr>{{ '%g'|format(net) }} ₪</b></div></div>
<div class=cards>
<div class=card><h3>{{ party_card or 'بيانات المورد' }}</h3>
<div class=row><span class="t a">{{a4ic.truck}}</span><div><small>الاسم</small><b>{{party or '—'}}</b></div></div>
<div class=row><span class="t b">{{a4ic.phone}}</span><div><small>الهاتف</small><b dir=ltr>{{phone or '—'}}</b></div></div></div>
<div class=card><h3>بيانات المستند</h3>
<div class=row><span class="t d">{{a4ic.cal}}</span><div><small>التاريخ</small><b dir=ltr>{{now}}</b></div></div>
<div class=row><span class="t c">{{a4ic.doc}}</span><div><small>عدد البنود / القطع</small><b>{{lines|length}} بند · {{qty}} قطعة</b></div></div></div>
</div>
{% if lines %}
<table class=items><thead><tr><th class=n>#<th>الصنف<th>الكمية<th class=num>سعر الوحدة<th class=num>المجموع</tr></thead><tbody>
{% for l in lines %}<tr class="{{'rt' if l.kind=='مرتجع'}}"><td class=n>{{l.n}}<td>{{l.name}}{% if l.kind=='مرتجع' %}<span class=chip>مرتجع</span>{% endif %}{% if not ref %}<span class=dt dir=ltr>{{l.date}}</span>{% endif %}<td>{{l.qty}}<td class=num>{{ '%g'|format(l.cost) }} ₪<td class=num><b>{{ '%g'|format(l.signed) }} ₪</b></tr>{% endfor %}</tbody></table>
<div class=bottom><div class=note>{{a4ic.doc}} {{ note_msg or 'يرجى مطابقة الكميات والأسعار عند الاستلام، وأي ملاحظة تُبلَّغ خلال 48 ساعة من تاريخ المستند.' }}</div>
<div class=sum><div><span>{{ lbl_buy_full or 'إجمالي المشتريات' }}</span><b dir=ltr>{{ '%g'|format(buy_total) }} ₪</b></div>{% if ret_total %}<div><span>{{ lbl_ret or 'المرتجعات' }}</span><b dir=ltr style="color:var(--rose)">-{{ '%g'|format(ret_total) }} ₪</b></div>{% endif %}<div class=net><span>{{ net_label or 'الصافي المستحق' }}</span><span dir=ltr>{{ '%g'|format(net) }} ₪</span></div></div></div>
{% if sigs %}<div class=sigs><div>توقيع الموظف (المستلم)</div><div>توقيع الشركة</div></div>{% endif %}{% else %}<div class=note style="margin-top:14px;text-align:center">{{ empty_msg or 'لا توجد مشتريات مسجّلة' }}</div>{% endif %}
{% if stk %}<h2 class=h2>قطع المخزون من هذا المورد</h2>
<table class=items><thead><tr><th class=n>#<th>الصنف<th>الكمية<th class=num>الجملة</tr></thead><tbody>{% for r in stk %}<tr><td class=n>{{loop.index}}<td>{{r.name}}{% if r.color %} · {{r.color}}{% endif %}<td>{{r.qty}}<td class=num>{{ '%g'|format(r.cost) }} ₪</tr>{% endfor %}</tbody></table>{% endif %}
</div></td></tr></tbody></table></div>
<script>if(/[?&]auto=1/.test(location.search))window.addEventListener('load',function(){setTimeout(print,300)});</script></html>
"""

T["locked"] = """<!doctype html><html lang=ar dir=rtl><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>الحساب مقفل</title>
<style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:linear-gradient(140deg,#0c1233,#262d8a 60%,#4f46e5);font-family:system-ui,Tahoma,Arial,sans-serif;color:#0f172a}
.bx{background:#fff;border-radius:24px;padding:38px 34px;width:min(480px,92vw);text-align:center;box-shadow:0 40px 90px -30px #000a}
.ic{width:74px;height:74px;border-radius:50%;background:#fff1f3;color:#e11d48;display:grid;place-items:center;margin:0 auto 14px}
h1{margin:0 0 8px;font-size:24px}p{color:#64748b;line-height:1.8;margin:6px 0}.mail{display:inline-block;margin:14px 0 4px;padding:11px 22px;border-radius:12px;background:linear-gradient(135deg,#4f46e5,#6d5efc);color:#fff;text-decoration:none;font-weight:700}
.out{display:block;margin-top:14px;color:#64748b}</style>
<div class=bx><div class=ic><svg width=36 height=36 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2 stroke-linecap=round stroke-linejoin=round><path d="M5 11h14v10H5zM8 11V7a4 4 0 018 0v4"/></svg></div>
{% if st.state=='blocked' %}<h1>تم إيقاف حسابك</h1><p>تم إيقاف هذا الحساب من قبل مالك البرنامج. لإعادة التفعيل يرجى التواصل معه.</p>
{% elif st.kind=='paid' %}<h1>انتهى اشتراكك</h1><p>انتهى اشتراك البرنامج بتاريخ {{st.last}} وتم قفل الحساب. جدّد الاشتراك ليرجع كل شيء كما كان، وبياناتك محفوظة.</p>
{% else %}<h1>انتهت الفترة التجريبية</h1><p>انتهت التجربة المجانية وتم قفل الحساب. فعّل الاشتراك لتكمل الشغل، وبياناتك محفوظة.</p>{% endif %}
<a class=mail href="mailto:{{owner_email}}?subject=تفعيل اشتراك REPAIRIX">تواصل لتفعيل الاشتراك</a><p dir=ltr>{{owner_email}}</p>
<a class=out href=/logout>تسجيل الخروج</a></div></html>"""

T["owner"] = """{% extends 'base' %}{% block c %}
<div class="sg4 o6">
<div class=sc><span class="si a"><b>{{k.total}}</b></span><div><small>كل المستخدمين</small></div></div>
<div class=sc><span class="si e"><b>{{k.active}}</b></span><div><small>فترة تجريبية</small></div></div>
<div class=sc><span class="si c"><b>{{k.paid}}</b></span><div><small>مشتركون</small></div></div>
<div class=sc><span class="si d"><b>{{k.ended}}</b></span><div><small>منتهي الاشتراك</small></div></div>
<div class=sc><span class="si d"><b>{{k.blocked}}</b></span><div><small>موقوفون</small></div></div>
<div class=sc><span class="si b"><b>{{k.online}}</b></span><div><small>متصلون الآن</small></div></div></div>
<div class=tools><div class=r1><label class=search>{{ic.sr}}<input data-f=utbl data-role=search placeholder="بحث بالإيميل أو اسم الشركة..."></label>
<select data-f=utbl data-col=2 aria-label="الحالة"><option value="">كل الحالات<option>تجربة<option>مشترك<option>منتهي<option>موقوف</select></div></div>
<dialog class=dlg id=dlg-ext><form method=post action=/owner/extend><input type=hidden name=sid>
<div class=dh><h3>تفعيل / تمديد اشتراك</h3><button type=button class=cl data-close aria-label="إغلاق">×</button></div>
<div class=db><label style="font-weight:600;color:var(--mut);font-size:13px">عدد الأيام المضافة<input class=sm style="width:100%;display:block;margin:5px 0 0" name=days type=number min=1 max=3650 value=30 required></label>
<div class=chp><button type=button class=ghost data-days=7>7 أيام</button><button type=button class=ghost data-days=30>شهر</button><button type=button class=ghost data-days=90>3 أشهر</button><button type=button class=ghost data-days=180>6 أشهر</button><button type=button class=ghost data-days=365>سنة</button></div>
<p><small>بتنضاف على الأيام المتبقية للمستخدم. إذا كان الاشتراك منتهياً أو الحساب موقوفاً بيرجع يشتغل فوراً.</small></p></div>
<div class=df><button>تفعيل</button><button type=button class=ghost data-close>إلغاء</button></div></form></dialog>
<dialog class=dlg id=dlg-date><form method=post action=/owner/setdate><input type=hidden name=sid>
<div class=dh><h3>تحديد آخر يوم للاشتراك</h3><button type=button class=cl data-close aria-label="إغلاق">×</button></div>
<div class=db><label style="font-weight:600;color:var(--mut);font-size:13px">آخر يوم يعمل فيه الحساب<input style="width:100%;display:block;margin:5px 0 0" name=date type=date></label>
<p><small>بعد هذا التاريخ بيتقفل الحساب تلقائياً. اختر تاريخاً قديماً لقفله فوراً، أو اترك الحقل فارغاً للرجوع للفترة التجريبية.</small></p></div>
<div class=df><button>حفظ</button><button type=button class=ghost data-close>إلغاء</button></div></form></dialog>
<div class=card><table class=srt id=utbl><tr><th>#<th>المستخدم<th>الحالة<th>الأيام المتبقية<th>آخر يوم<th>آخر دخول<th class=ns>إجراءات</tr>
{% for u in users %}<tr><td>{{u.id}}<td><div class=uc>{% if u.online %}<span class=dot-on title="متصل الآن"></span>{% endif %}<b>{{u.email}}</b></div><small>{{u.shop_name or 'بدون اسم شركة'}} · سجّل {{u.created}}</small>
<td><span class="pill {{u.pc}}">{{u.label}}</span>
<td data-v="{{u.st.left}}">{% if u.st.state=='blocked' %}<small>موقوف يدوياً</small>{% elif u.st.left>0 %}<b>{{u.st.left}}</b> يوم{% else %}<span class=low>منتهي</span>{% endif %}
<td class=nw>{{u.st.last or '—'}}<td class=nw dir=ltr>{{ (u.last_login or '—')[:16] }}
<td><div class=sa>
<button type=button class="ib pr" title="تفعيل / تمديد اشتراك" aria-label="تفعيل / تمديد اشتراك" data-open=dlg-ext data-fill='{{ {"sid": u.id, "days": 30}|tojson }}'>{{ic.cp}}</button>
<button type=button class="ib ed" title="تحديد آخر يوم" aria-label="تحديد آخر يوم" data-open=dlg-date data-fill='{{ {"sid": u.id, "date": u.st.last or ""}|tojson }}'>{{ic.cd}}</button>
<form method=post action=/owner/block onsubmit="return confirm('{{ 'تفعيل' if u.blocked else 'إيقاف' }} هذا الحساب؟')"><input type=hidden name=sid value="{{u.id}}"><button class="ib {{'' if u.blocked else 'dl'}}" title="{{ 'تفعيل الحساب' if u.blocked else 'إيقاف الحساب' }}" aria-label="إيقاف أو تفعيل">{{ ic.ul if u.blocked else ic.lk }}</button></form>
<form method=post action=/owner/delete onsubmit="return confirm('حذف هذا المستخدم مع كل بياناته نهائياً؟')"><input type=hidden name=sid value="{{u.id}}"><button class="ib dl" title="حذف المستخدم" aria-label="حذف المستخدم">{{ic.dl}}</button></form></div></tr>
{% else %}<tr><td colspan=7 class=em>ما في مستخدمين مسجلين بعد.</tr>{% endfor %}</table></div>
<script>document.addEventListener('click',function(e){var b=e.target.closest('[data-days]');if(b){b.closest('form').querySelector('[name=days]').value=b.dataset.days}})</script>
{% endblock %}"""

app.jinja_loader = DictLoader(T)
app.jinja_env.autoescape = True  # أسماء القطع/الزبائن تُعرض كنص آمن وليس كـ HTML
today = lambda: datetime.date.today().isoformat()

TT = {"ok": "تمت العملية بنجاح", "warn": "تنبيه", "info": "معلومة"}

def notify(msg, kind="info", title=None):
    ex("insert into notifications(user_id,msg,kind,created) values(?,?,?,?)",
       (uid(), f"{title}: {msg}" if title else msg, kind, datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))
    flash(f"{title or TT[kind]}|{msg}", kind)


# أيقونات الطباعة الحرارية: أسود صلب وخط سميك (الطابعة الحرارية بتطبع أبيض/أسود بس، فما في رمادي ولا تدرّج)
def _th(inner, c="#000"):
    return Markup(f'<svg class=i viewBox="0 0 24 24" fill=none stroke="{c}" stroke-width=2.6 stroke-linecap=round stroke-linejoin=round shape-rendering=geometricPrecision>{inner}</svg>')
_THP = {"store": '<path d="M3 9l1.5-5h15L21 9M3 9a3 3 0 006 0 3 3 0 006 0 3 3 0 006 0M5 12v8h14v-8M10 20v-5h4v5" />',
        "user": '<circle cx=12 cy=8 r=4 /><path d="M4 21c0-4.5 3.5-7 8-7s8 2.5 8 7" />',
        "phone": '<path d="M5 3h4l2 5-2.5 1.5a11 11 0 006 6L16 13l5 2v4a2 2 0 01-2 2A16 16 0 013 5a2 2 0 012-2z" />',
        "cal": '<rect x=3 y=5 width=18 height=16 rx=2 /><path d="M3 10h18M8 3v4M16 3v4" />',
        "hash": '<path d="M5 9h15M4 15h15M10 3L8 21M16 3l-2 18" />',
        "box": '<path d="M3 7l9-4 9 4v10l-9 4-9-4zM3 7l9 4 9-4M12 11v10" />',
        "cart": '<path d="M3 4h3l2.5 11h10L21 7H7" /><circle cx=10 cy=19 r=1.5 /><circle cx=17 cy=19 r=1.5 />',
        "pen": '<path d="M4 20h4L19 9l-4-4L4 16zM13 7l4 4" />'}
THIC = {k: _th(v) for k, v in _THP.items()}
THIC.update({k + "_w": _th(_THP[k], "#fff") for k in ("box", "cart")})

# أيقونات A4: مصمتة (Filled) بألوان، تصميم مختلف تماماً عن الحرارية
def _a4(inner): return Markup(f'<svg viewBox="0 0 24 24" aria-hidden=true>{inner}</svg>')
A4IC = {"shop": _a4('<path fill-rule=evenodd d="M4 21V5l8-3 8 3v16h-6v-5h-4v5zM8 8h2v2H8zm6 0h2v2h-2zm-6 4h2v2H8zm6 0h2v2h-2z" />'),
        "truck": _a4('<path d="M2 6h11v9H2zM13 9h4l3 3v3h-7z" /><circle cx=6.5 cy=17.5 r=2 /><circle cx=16.5 cy=17.5 r=2 />'),
        "phone": _a4('<path d="M6.6 2h3l1.6 4.4-2 1.4a10 10 0 005 5l1.4-2 4.4 1.6v3A3 3 0 0117.6 18 15 15 0 012 4.4 3 3 0 016.6 2z" />'),
        "cal": _a4('<path fill-rule=evenodd d="M5 4h14a2 2 0 012 2v14a2 2 0 01-2 2H5a2 2 0 01-2-2V6a2 2 0 012-2zm0 6v10h14V10z" /><rect x=7 y=2 width=2 height=4 rx=1 /><rect x=15 y=2 width=2 height=4 rx=1 />'),
        "doc": _a4('<path fill-rule=evenodd d="M6 2h8l5 5v15H6zm7 1.5V8h4.5zM9 12h7v1.6H9zm0 3.5h7v1.6H9z" />'),
        "pen": _a4('<path d="M3 21l1-5L16.5 3.5l4 4L8 20zM15 5l4 4" />')}

@app.context_processor
def inject():
    d = {"brand": BRAND, "logo": Markup(LOCKUP), "ic": ICONS, "cic": CIC, "kc": KC, "thic": THIC, "a4ic": A4IC}
    if uid(): d["trial"] = trial_info(); d["is_owner"] = is_owner()
    if uid():
        _s = settings(); d["tb_shop"] = (_s.get("shop_name") or "").strip() or "شركة الصيانة"; d["tb_logo"] = _s.get("logo") or ""
        d["tb_inc"] = q(f"select coalesce(sum(price),0) p from repairs where {DD}=? and status={DELIV} and user_id=?", (today(), uid()))[0]["p"] + q("select coalesce(sum(total),0) p from sales where user_id=? and created like ?", (uid(), today() + "%"))[0]["p"]
        d["tb_open"] = q("select count(*) n from repairs where user_id=? and status=?", (uid(), ST[0]))[0]["n"]
        d["tb_mail"] = ((cur_user() or {}).get("email") or "").strip() or "user"
    if uid(): d["unread"] = q("select count(*) n from notifications where user_id=? and seen=0", (uid(),))[0]["n"]
    return d

@app.route("/notifications")
def notifications():
    rows = [dict(x) for x in q("select * from notifications where user_id=? order by id desc limit 100", (uid(),))]
    ex("update notifications set seen=1 where user_id=?", (uid(),))
    return render_template("notifs", rows=rows)

@app.route("/notifications/clear")
def clear_notifs():
    ex("delete from notifications where user_id=?", (uid(),)); return redirect("/notifications")

uid = lambda: session.get("uid")

def cur_user():
    if "cu" not in g:
        r = q("select u.*, s.trial_start from users u left join settings s on s.user_id=u.id where u.id=?", (uid(),)) if uid() else []
        g.cu = dict(r[0]) if r else None
    return g.cu

def is_owner():
    u = cur_user()
    return bool(u and (u["email"] or "").lower() == OWNER_EMAIL)

@app.before_request
def guard():
    ep = request.endpoint
    if session.get("emp") and not uid():   # جلسة موظف: بيشوف صفحته بس
        er = q("select * from employees where id=?", (session["emp"],))
        if not er or not er[0]["pw"] or not er[0]["login"]: session.clear(); return redirect("/login")
        if ep in ("logout", "static"): return
        ou = q("select u.*, s.trial_start from users u left join settings s on s.user_id=u.id where u.id=?", (er[0]["user_id"],))
        stt = sub_state(dict(ou[0])) if ou else {"state": "ended"}
        if stt["state"] in ("ended", "blocked"): return render_template("locked", st=stt, owner_email=OWNER_EMAIL), 403
        if er[0]["must_change"] and ep not in ("emp_settings", "emp_password", "login"): return redirect("/my/settings")   # لازم يغيّر كلمة السر المؤقتة أول
        if ep not in ("emp_home", "emp_settings", "emp_password", "emp_my_statement", "emp_sell", "emp_return", "emp_sales", "emp_customers", "emp_customer_add", "emp_customer_edit", "emp_cust_pay", "emp_copay_me", "pay_receipt_file", "emp_queue", "emp_queue_add", "emp_queue_act", "emp_customer_del", "rphoto", "login"): return redirect("/my")
        return
    if not uid():
        if ep == "index": return redirect("/welcome")   # الزائر الجديد بيشوف الصفحة التعريفية أول
        if ep not in ("login", "register", "forgot", "reset", "healthz", "i18n_js", "welcome", "landing_img", "phone_img", "static"): return redirect("/login")
        return
    u = cur_user()
    if not u: session.clear(); return redirect("/login")
    now = datetime.datetime.now()
    if now.timestamp() - session.get("ls", 0) > 60:   # آخر نشاط (للوحة المالك)
        ex("update users set last_seen=? where id=?", (now.strftime("%Y-%m-%d %H:%M:%S"), u["id"])); session["ls"] = now.timestamp()
    if (u.get("status") or "active") == "pending" and ep not in ("pending", "activate", "logout", "static", "shop_logo", "healthz", "i18n_js"): return redirect("/pending")   # حساب بانتظار موافقة المالك
    if ep and ep.startswith("owner_") and not is_owner(): abort(404)   # صفحات المالك فقط
    st = sub_state(u)
    if st["state"] in ("ended", "blocked") and ep not in ("logout", "static"):   # قفل فوري عند انتهاء الاشتراك أو الإيقاف
        return render_template("locked", st=st, owner_email=OWNER_EMAIL), 403

@app.route("/landing-img/<name>.webp")
def landing_img(name):
    import landing_assets
    b = landing_assets.get(name)
    if not b: abort(404)
    r = Response(b, mimetype="image/webp"); r.headers["Cache-Control"] = "public, max-age=86400"; return r

@app.route("/phone-img/<name>.png")
def phone_img(name):
    import phone_assets
    b = phone_assets.get(name)
    if not b: abort(404)
    r = Response(b, mimetype="image/png"); r.headers["Cache-Control"] = "public, max-age=86400"; return r

@app.route("/welcome")
def welcome():
    if uid(): return redirect("/")
    return render_template("landing")

@app.route("/login", methods=["GET", "POST"])
def login():
    err = None
    if request.method == "POST":
        _id = request.form["email"].strip().lower()
        u = q("select * from users where email=? or lower(username)=?", (_id, _id))
        if u and check_password_hash(u[0]["pw"], request.form["password"]):
            session["uid"] = u[0]["id"]; now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ex("update users set last_login=?, last_seen=? where id=?", (now, now, u[0]["id"])); session["ls"] = datetime.datetime.now().timestamp()
            return redirect("/owner" if (u[0]["email"] or "").lower() == OWNER_EMAIL else "/")
        em = q("select * from employees where lower(login)=? and pw is not null and pw<>''", (request.form["email"].strip().lower(),))
        if em and check_password_hash(em[0]["pw"], request.form["password"]):
            session.clear(); session["emp"] = em[0]["id"]
            if em[0]["must_change"]:
                flash("غيّر كلمة السر الآن|كلمة السر اللي دخلت فيها مؤقتة من المدير. اختر كلمة سر خاصة فيك قبل ما تكمل.", "warn")
                return redirect("/my/settings")
            return redirect("/my")
        err = "الإيميل (أو اسم المستخدم) أو كلمة السر غلط"
    return render_template("auth", title="تسجيل الدخول", err=err, mode="login")

def username_taken(un, me=None):
    """اسم المستخدم مأخوذ؟ (بنفحص المستخدمين والإيميلات وحسابات الموظفين). me = id المستخدم الحالي لاستثنائه."""
    for r in q("select id from users where lower(username)=? or lower(email)=?", (un, un)):
        if r["id"] != me: return True
    return bool(q("select 1 from employees where lower(login)=?", (un,)))

@app.route("/register", methods=["GET", "POST"])
def register():
    err = None; f = request.form
    if request.method == "POST":
        e, p = f.get("email", "").strip().lower(), f.get("password", "")
        full = f.get("full_name", "").strip(); parts = full.split(None, 1)
        fn, ln = (parts[0] if parts else ""), (parts[1] if len(parts) > 1 else "")
        ph = "".join(ch for ch in f.get("phone", "") if ch.isdigit() or ch == "+")
        shop = f.get("shop_name", "").strip(); city = f.get("city", "").strip()[:100]; un = f.get("username", "").strip().lower()
        if not full or not ph or not e or not shop or not city or not un: err = "عبّي الاسم الكامل ورقم الهاتف واسم الشركة والمدينة والإيميل واسم المستخدم"
        elif not re.fullmatch(r"[a-z0-9._-]{3,30}", un): err = "اسم المستخدم: 3-30 حرف إنجليزي أو أرقام أو . _ -"
        elif username_taken(un): err = "اسم المستخدم مأخوذ، اختر غيره"
        elif len("".join(c for c in ph if c.isdigit())) < 8: err = "رقم الهاتف غير صالح"
        elif len(p) < 6: err = "كلمة السر لازم 6 أحرف على الأقل"
        elif q("select 1 from users where lower(email)=?", (e,)): err = "الإيميل مسجل من قبل"
        else:
            logo, lerr = save_logo(request.files.get("logo"))
            if lerr: err = lerr
        if not err:
            is_own = e == OWNER_EMAIL; nowm = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            ex("insert into users(email,pw,created,first_name,last_name,full_name,phone,status,approval_requested,username) values(?,?,?,?,?,?,?,?,?,?)",
               (e, generate_password_hash(p), today(), fn, ln, full, ph, "active" if is_own else "pending", nowm, un))
            i = q("select id from users where email=?", (e,))[0]["id"]
            ex("insert into settings(user_id,shop_name,cc,trial_start,logo,address) values(?,?,?,?,?,?)", (i, shop, "970", today() if is_own else None, logo, city))
            session["uid"] = i; _n = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"); ex("update users set last_login=?, last_seen=? where id=?", (_n, _n, i))
            if is_own: return redirect("/owner")
            ow = q("select id from users where lower(email)=?", (OWNER_EMAIL,))
            if ow: ex("insert into notifications(user_id,msg,kind,created) values(?,?,?,?)", (ow[0]["id"], f"طلب حساب جديد: {full} · {ph}", "info", nowm))
            return redirect("/pending")
    return render_template("auth", title="إنشاء حساب جديد", err=err, mode="register", trial_days=TRIAL_DAYS, f=f)

def send_reset_mail(to, link):
    body = (f"مرحباً،\n\nوصلنا طلب لإعادة تعيين كلمة السر لحسابك في {BRAND}.\n"
            f"اضغط على الرابط التالي لتعيين كلمة سر جديدة (صالح لمدة {RESET_MIN} دقيقة):\n{link}\n\n"
            "إذا ما طلبت هذا الإجراء، تجاهل هذه الرسالة وكلمة سرك الحالية تبقى كما هي.")
    host = os.environ.get("SMTP_HOST")
    if host:
        try:
            m = EmailMessage(); m["Subject"] = f"{BRAND} | إعادة تعيين كلمة السر"
            m["From"] = os.environ.get("SMTP_FROM") or os.environ.get("SMTP_USER") or "no-reply@localhost"; m["To"] = to; m.set_content(body)
            port = int(os.environ.get("SMTP_PORT", 587))
            with (smtplib.SMTP_SSL(host, port, timeout=15) if port == 465 else smtplib.SMTP(host, port, timeout=15)) as c:
                if port != 465: c.starttls()
                if os.environ.get("SMTP_USER"): c.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASS", ""))
                c.send_message(m)
            return
        except Exception as e:
            print("[SMTP] failed:", e)
    # بدون إعداد SMTP: الرابط بيظهر بنافذة التشغيل (الكونسول) لصاحب البرنامج
    print("\n" + "=" * 64 + "\n[PASSWORD RESET] " + to + "\n" + link + "\n" + "=" * 64 + "\n", flush=True)

@app.route("/forgot", methods=["GET", "POST"])
def forgot():
    sent = False
    if request.method == "POST":
        e = request.form["email"].strip().lower(); u = q("select id from users where email=?", (e,))
        now = datetime.datetime.now()
        if u and q("select count(*) n from password_resets where user_id=? and created>?", (u[0]["id"], (now - datetime.timedelta(hours=1)).isoformat()))[0]["n"] < 5:
            tok = secrets.token_urlsafe(32)
            ex("insert into password_resets(user_id,token_hash,expires,created) values(?,?,?,?)",
               (u[0]["id"], hashlib.sha256(tok.encode()).hexdigest(), (now + datetime.timedelta(minutes=RESET_MIN)).isoformat(), now.isoformat()))
            send_reset_mail(e, (os.environ.get("APP_URL") or request.host_url).rstrip("/") + "/reset/" + tok)
        sent = True  # نفس الرد دائماً حتى ما نكشف إذا الإيميل مسجل أو لا
    return render_template("auth", title="استعادة كلمة السر", err=None, mode="forgot", sent=sent, mins=RESET_MIN)

@app.route("/reset/<token>", methods=["GET", "POST"])
def reset(token):
    h = hashlib.sha256(token.encode()).hexdigest()
    r = q("select * from password_resets where token_hash=? and used=0 and expires>?", (h, datetime.datetime.now().isoformat()))
    if not r: return render_template("auth", title="الرابط غير صالح", err=None, mode="invalid")
    err = None
    if request.method == "POST":
        p, p2 = request.form["password"], request.form.get("password2", "")
        if len(p) < 6: err = "كلمة السر لازم 6 أحرف على الأقل"
        elif p != p2: err = "كلمتا السر غير متطابقتين"
        else:
            ex("update users set pw=? where id=?", (generate_password_hash(p), r[0]["user_id"]))
            ex("update password_resets set used=1 where user_id=?", (r[0]["user_id"],))
            flash("تم تغيير كلمة السر|سجّل دخولك بكلمة السر الجديدة.", "ok")
            return redirect("/login")
    return render_template("auth", title="كلمة سر جديدة", err=err, mode="reset")

@app.route("/logout")
def logout():
    session.clear(); return redirect("/login")

@app.route("/")
def index():
    t, inc = [q("select coalesce(sum(%s),0) p from repairs where created=? and user_id=?" % e, (today(), uid()))[0]["p"] for e in ("price-cost", "price")]
    days = q("select created done_date,count(*) n,sum(price-cost) p from repairs where user_id=? group by created order by created desc limit 14", (uid(),))
    low = q("select id,qty,min_qty,name || coalesce(' · ' || maker, '') || coalesce(' · ' || color, '') as name from parts where qty<=min_qty and user_id=?", (uid(),))
    n = lambda st: q("select count(*) n from repairs where user_id=? and status=?", (uid(), st))[0]["n"]
    mx = max([d["p"] for d in days] + [1])
    month = q("select coalesce(sum(price-cost),0) p from repairs where created like ? and user_id=?", (today()[:7] + "%", uid()))[0]["p"]
    recent = q("select * from repairs where user_id=? order by id desc limit 6", (uid(),))
    parts_n = q("select coalesce(sum(qty),0) n from parts where user_id=?", (uid(),))[0]["n"]
    return render_template("index", today=t, income=inc, month=month, days=days, low=low, open_n=n(ST[0]), ready_n=n(ST[1]), mx=mx,
                           recent=recent, parts_n=parts_n, shop=settings()["shop_name"], dt=today())

TITLES = {None: ("قطع الغيار", "كل القطع في مكان واحد، مع بحث وفرز وتصفية"),
          "بطارية": ("البطاريات", "مخزون البطاريات بالكميات والأسعار والصور"),
          "آيسي": ("الآيسيات", "مخزون الآيسيات (شحن، طاقة، صوت...) بالكميات والصور"),
          "شاشة": ("شاشات", "مخزون الشاشات لكل الأجهزة بالأسعار والكميات"),
          "قاعدة شحن": ("قواعد شحن", "قواعد الشحن لكل الموديلات بالأسعار والكميات"),
          "كونكتر": ("الكونكترات", "الكونكترات (شحن، بطارية، شاشة...) بالأسعار والكميات والصور"),
          "سماعات": ("سماعات", "السماعات بأنواعها بالأسعار والكميات")}

def save_photo(f):
    if not f or not f.filename: return None
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp"): return None
    name = uuid.uuid4().hex + ext; put_file(name, f.read())
    return name

@app.route("/photo/<name>")
def photo(name):
    if not q("select 1 from parts where photo=? and user_id=?", (name, uid())): abort(404)
    return send_from_directory(UP, name)

@app.post("/parts/<int:i>/photo")
def set_photo(i):
    n = save_photo(request.files.get("photo"))
    if n and q("select 1 from parts where id=? and user_id=?", (i, uid())):
        ex("update parts set photo=? where id=? and user_id=?", (n, i, uid())); notify("تم حفظ الصورة للقطعة", "ok", "تم رفع الصورة")
    else: notify("اختر صورة بصيغة JPG أو PNG أو WEBP", "warn", "تعذّر رفع الصورة")
    return redirect(request.referrer or "/parts")

@app.route("/parts", defaults={"cat": None}, methods=["GET", "POST"])
@app.route("/batteries", defaults={"cat": "بطارية"}, methods=["GET", "POST"])
@app.route("/ics", defaults={"cat": "آيسي"}, methods=["GET", "POST"])
@app.route("/screens", defaults={"cat": "شاشة"}, methods=["GET", "POST"])
@app.route("/chargers", defaults={"cat": "قاعدة شحن"}, methods=["GET", "POST"])
@app.route("/headphones", defaults={"cat": "سماعات"}, methods=["GET", "POST"])
@app.route("/connectors", defaults={"cat": "كونكتر"}, methods=["GET", "POST"])
def parts(cat):
    if request.method == "POST":
        f = request.form
        bc = "".join(ch for ch in (f.get("barcode") or "").strip() if 32 < ord(ch) < 127)[:40] or None
        if bc and barcode_taken(bc): notify(f"الباركود {bc} مستعمل لقطعة ثانية، انحفظت القطعة بباركود عشوائي جديد", "warn", "الباركود مكرر"); bc = None
        bc = bc or new_barcode()   # كل قطعة جديدة بتاخد كود عشوائي فوراً
        ex("insert into parts(name,category,qty,min_qty,cost,price,supplier_id,user_id,photo,barcode,maker) values(?,?,?,?,?,?,?,?,?,?,?)",
           (f["name"], f["category"], _i(f["qty"]), _i(f["min_qty"], 2), _f(f["cost"]), _f(f["price"]), f["supplier_id"] or None, uid(), save_photo(request.files.get("photo")), bc,
            ((f.get("maker") or "").strip()[:60] or None) if f["category"] in ("شاشة", "بطارية") else None))
        notify(f"{f['name']} · الكمية {f['qty']}" + (" · وظهرت تلقائياً بصفحة قطع الغيار" if cat else ""), "ok", "تمت إضافة القطعة")
        if int(f["qty"]) <= int(f["min_qty"] or 2): notify(f"كمية {f['name']} منخفضة", "warn", "تنبيه مخزون")
        if f.get("print_label"):   # طباعة ملصق الباركود فوراً على ماكنة الطباعة
            _n = q("select id from parts where user_id=? and barcode=?", (uid(), bc))
            if _n: return redirect("/barcodes/print?ids=%d&copies=%d&size=%s&auto=1&back=%s" % (_n[0]["id"], max(1, _i(f.get("label_copies"), 1)), f.get("label_size") or "50x30", request.path))
        return redirect(request.path)
    rows = [dict(r, brand=brand_of(r["name"])) for r in q("select p.*,s.name sname from parts p left join suppliers s on s.id=p.supplier_id where p.user_id=? and (cast(? as text) is null or p.category=?)", (uid(), cat, cat))]
    corder = lambda c: CATS.index(c) if c in CATS else 99
    rows.sort(key=lambda r: ((corder(r["category"]) if not cat else 0), BRAND_ORDER.get(r["brand"], 99), r["name"], r["color"] or ""))
    for n, r in enumerate(rows): r["i"] = n
    # الصفحة العامة: أقسام حسب نوع القطعة | صفحة نوع معيّن: أقسام حسب الجهاز
    key = "category" if not cat else "brand"; groups = []
    for r in rows:
        if not groups or groups[-1]["key"] != r[key]:
            groups.append({"key": r[key], "title": CAT_PLURAL.get(r[key], r[key]) if not cat else r[key], "rows": [],
                           "icon": CIC.get(r[key], CIC["أخرى"]) if not cat else ICONS["ph"], "k": KC.get(r[key], 5) if not cat else 1})
        groups[-1]["rows"].append(r)
    for g in groups: g["qty"] = sum(x["qty"] for x in g["rows"])
    st = {"n": sum(x["qty"] for x in rows), "val": sum(x["qty"] * x["cost"] for x in rows), "low": sum(1 for x in rows if x["qty"] <= x["min_qty"]),
          "sell": sum(x["qty"] * x["price"] for x in rows)}
    brands = sorted({r["brand"] for r in rows}, key=lambda b: BRAND_ORDER.get(b, 99))
    cnt = {c: sum(1 for r in rows if r["category"] == c) for c in CATS}
    makers = sorted({r["maker"] for r in rows if r["maker"]})
    return render_template("parts", makers=makers, parts=rows, groups=groups, brands=brands, cnt=cnt, total=len(rows), cat=cat, ttl=TITLES[cat], st=st,
                           cats=[c for c in CATS if c != "ظهر"], catlist=CATS, cplural=CAT_PLURAL, sup=q("select * from suppliers where user_id=?", (uid(),)))

@app.route("/backs", methods=["GET", "POST"])
def backs():
    if request.method == "POST":
        f = request.form; name = f["name"].strip(); n = 0
        for c, h, qty in zip(f.getlist("color"), f.getlist("hex"), f.getlist("qty")):
            if c.strip() and name:
                ex("insert into parts(name,category,qty,min_qty,cost,price,supplier_id,user_id,color,hex) values(?,?,?,?,?,?,?,?,?,?)",
                   (name, "ظهر", int(qty or 0), 2, _f(f["cost"]), _f(f["price"]), f["supplier_id"] or None, uid(), c.strip(), h or "#888888")); n += 1
        if n: notify(f"{name} · {n} ألوان · وظهرت تلقائياً بصفحة قطع الغيار", "ok", "تمت إضافة الموديل")
        else: notify("اكتب اسم الموديل واسم لون واحد على الأقل", "warn", "البيانات ناقصة")
        return redirect("/backs")
    rows = q("select p.*, s.name sname from parts p left join suppliers s on s.id=p.supplier_id where p.user_id=? and p.category='ظهر' order by p.name,p.id", (uid(),))
    models = {}
    for r in rows: models.setdefault(r["name"], []).append(r)
    out = sum(1 for x in rows if x["qty"] <= 0); lowc = sum(1 for x in rows if 0 < x["qty"] <= x["min_qty"])
    st = {"models": len(models), "cols": len(rows), "n": sum(x["qty"] for x in rows), "val": sum(x["qty"] * x["cost"] for x in rows),
          "sell": sum(x["qty"] * x["price"] for x in rows), "low": out + lowc, "out": out, "lowc": lowc, "ok": len(rows) - out - lowc}
    flags = {m: {"val": sum(c["qty"] * c["cost"] for c in cs), "out": int(any(c["qty"] <= 0 for c in cs)),
                 "low": int(any(0 < c["qty"] <= c["min_qty"] for c in cs))} for m, cs in models.items()}
    brands = {m: brand_of(m) for m in models}
    blist = sorted(((b, sum(1 for x in brands.values() if x == b)) for b in set(brands.values())), key=lambda t: BRAND_ORDER.get(t[0], 99))
    return render_template("backs", models=models, kinds={m: phone_kind(m) for m in models}, brands=brands, blist=blist, flags=flags, st=st,
                           ttl=("ظهور", "موديلات الهواتف وألوان الظهر لكل موديل"), sup=q("select * from suppliers where user_id=?", (uid(),)))

@app.post("/parts/<int:i>/stock")
def stock(i):
    n = int(request.form["n"]); p = q("select name from parts where id=? and user_id=?", (i, uid()))
    if p:
        ex("update parts set qty=greatest(0, qty+?) where id=? and user_id=?", (n, i, uid()))
        notify(f"{p[0]['name']} {n:+d}", "ok", "تم تحديث المخزون")
    return redirect(request.referrer or "/parts")

@app.post("/parts/<int:i>/edit")
def edit_part(i):
    r = q("select * from parts where id=? and user_id=?", (i, uid()))
    if not r: return redirect(request.referrer or "/parts")
    r = r[0]; f = request.form; back = r["category"] == "ظهر"
    name = (f.get("name") or "").strip() or r["name"]
    cost = max(_f(f.get("cost"), r["cost"] or 0), 0); price = max(_f(f.get("price"), r["price"] or 0), 0)
    qty = max(_i(f.get("qty"), r["qty"] or 0), 0); mn = max(_i(f.get("min_qty"), r["min_qty"] if r["min_qty"] is not None else 2), 0)
    sid = None
    if f.get("supplier_id"):
        sr = q("select id from suppliers where id=? and user_id=?", (f.get("supplier_id"), uid())); sid = sr[0]["id"] if sr else None
    cat = r["category"]; nc = f.get("category")
    if not back and nc in CATS and nc != "ظهر": cat = nc
    maker = r["maker"]
    if cat in ("شاشة", "بطارية"): maker = (f.get("maker") or "").strip()[:60] or None
    color, hx = r["color"], r["hex"]
    if back:
        color = (f.get("color") or "").strip() or color; hx = f.get("hex") or hx
    ex("update parts set name=?, category=?, qty=?, min_qty=?, cost=?, price=?, supplier_id=?, color=?, hex=?, maker=? where id=? and user_id=?",
       (name, cat, qty, mn, cost, price, sid, color, hx, maker, i, uid()))
    if back and f.get("apply_all"):   # الاسم والجملة والبيع مشتركين بين ألوان الموديل
        ex("update parts set name=?, cost=?, price=? where user_id=? and category='ظهر' and name=?", (name, cost, price, uid(), r["name"]))
    notify(f"{name}" + (f" · {color}" if back and color else "") + f" · جملة {cost:g} · بيع {price:g} · الكمية {qty}", "ok", "تم تعديل القطعة")
    if qty <= mn: notify(f"كمية {name} منخفضة", "warn", "تنبيه مخزون")
    return redirect(request.referrer or "/parts")

@app.route("/parts/<int:i>/delete")
def del_part(i):
    p = q("select name from parts where id=? and user_id=?", (i, uid()))
    if p:
        ex("delete from parts where id=? and user_id=?", (i, uid())); notify(p[0]['name'], "warn", "تم حذف القطعة")
    return redirect(request.referrer or "/parts")

def supplier_purchases(sid=None):
    """مشتريات كل مورد (بنود الشراء والمرتجعات من صفحة متطلبات الصيانة)"""
    sql = "select * from needs where user_id=? and supplier_id is not null" + (" and supplier_id=?" if sid else "") + " order by id desc"
    out = {}
    for r in q(sql, (uid(), sid) if sid else (uid(),)):
        d = out.setdefault(r["supplier_id"], {"rows": [], "qty": 0, "net": 0.0, "last": ""})
        sg = -1 if r["kind"] == "مرتجع" else 1
        d["rows"].append(dict(r, total=sg * r["qty"] * r["cost"]))
        d["qty"] += sg * r["qty"]; d["net"] += sg * r["qty"] * r["cost"]; d["last"] = max(d["last"], r["created"] or "")
    return out

def supplier_stock(sid=None):
    sql = "select * from parts where user_id=? and supplier_id is not null" + (" and supplier_id=?" if sid else "") + " order by category,name,color"
    out = {}
    for r in q(sql, (uid(), sid) if sid else (uid(),)): out.setdefault(r["supplier_id"], []).append(dict(r))
    return out

@app.route("/suppliers", methods=["GET", "POST"])
def suppliers():
    if request.method == "POST":
        f = request.form
        ex("insert into suppliers(name,phone,notes,user_id) values(?,?,?,?)", (f["name"], f["phone"], f["notes"], uid()))
        notify(f"تمت إضافة المورد: {f['name']}", "ok")
        return redirect("/suppliers")
    acc, pays = supplier_accounts()
    return render_template("suppliers", sup=q("select * from suppliers where user_id=?", (uid(),)), pur=supplier_purchases(), stk=supplier_stock(), acc=acc, pays=pays)

def supplier_accounts():
    """حساب كل مورد: إجمالي فواتيره، المدفوع له (من الصندوق)، والمتبقي + قائمة دفعاته."""
    inv = {r["supplier_id"]: r["t"] or 0 for r in q("select supplier_id, sum(total) t from invoices where user_id=? group by supplier_id", (uid(),))}
    pays = {}
    for r in q("select * from cash_entries where user_id=? and kind='دفعة مورد' and supplier_id is not null order by created desc, id desc", (uid(),)):
        pays.setdefault(r["supplier_id"], []).append(dict(r))
    acc = {}
    for sid in set(inv) | set(pays):
        paid = sum(x["amount"] or 0 for x in pays.get(sid, []))
        acc[sid] = {"inv": round(inv.get(sid, 0), 2), "paid": round(paid, 2), "rem": round(inv.get(sid, 0) - paid, 2)}
    return acc, pays

def save_receipt(f):
    """وصل دفعة (صورة أو PDF، لحد 8MB). بيرجع اسم الملف أو None."""
    if not f or not f.filename: return None
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".pdf"): return None
    data = f.read()
    if not data or len(data) > 8 * 1024 * 1024: return None
    name = uuid.uuid4().hex + ext; put_file(name, data)
    return name

@app.route("/payreceipt/<name>")
def pay_receipt_file(name):
    if uid():
        ok = q("select 1 from cash_entries where receipt=? and user_id=?", (name, uid())) or q("select 1 from emp_co_pay where receipt=? and user_id=?", (name, uid()))
    else:   # موظف: بس وصولات دفعاته هو
        ok = bool(session.get("emp")) and q("select 1 from emp_co_pay where receipt=? and emp_id=?", (name, session["emp"]))
    if not ok: abort(404)
    return send_from_directory(UP, name)

@app.post("/suppliers/pay")
def sup_pay():
    f = request.form; sid = _i(f.get("sid"))
    sp = q("select * from suppliers where id=? and user_id=?", (sid, uid()))
    if not sp: abort(404)
    back = f"/suppliers?open={sid}"
    amt = round(_f(f.get("amount")), 2); bank = f.get("pm") == "بنك"
    if amt <= 0: notify("اكتب مبلغ صحيح", "warn", "تعذّر تسجيل الدفعة"); return redirect(back)
    fl = request.files.get("receipt"); rc = save_receipt(fl)
    if fl and fl.filename and not rc: notify("الوصل لازم يكون صورة (JPG/PNG/WEBP) أو PDF وأقل من 8MB", "warn", "الوصل غير صالح"); return redirect(back)
    if bank and not rc: notify("الدفعة البنكية لازم يرفق معها وصل التحويل", "warn", "الوصل مطلوب"); return redirect(back)
    d = f.get("created") or today()
    if d > today(): d = today()
    ex("insert into cash_entries(user_id,created,kind,direction,amount,account,category,supplier_id,note,created_at,receipt) values(?,?,?,?,?,?,?,?,?,?,?)",
       (uid(), d, "دفعة مورد", "out", amt, "بنك" if bank else "نقد", "", sid, (f.get("note") or "").strip()[:200], now_s(), rc))
    notify(f"{sp[0]['name']} · {amt:g} ₪ · {'تحويل بنكي' if bank else 'نقداً'}" + (" · مع وصل" if rc else ""), "ok", "تم تسجيل دفعة المورد")
    return redirect(back)

@app.post("/suppliers/pay/<int:i>/delete")
def sup_pay_del(i):
    r = q("select * from cash_entries where id=? and user_id=? and kind='دفعة مورد'", (i, uid()))
    if not r: abort(404)
    del_file(r[0]["receipt"]); ex("delete from cash_entries where id=? and user_id=?", (i, uid()))
    notify("تم حذف الدفعة", "info"); return redirect(f"/suppliers?open={r[0]['supplier_id']}")

@app.post("/suppliers/<int:i>/purchase")
def sup_purchase(i):
    sp = q("select * from suppliers where id=? and user_id=?", (i, uid()))
    if not sp: abort(404)
    f = request.form; rows = []
    for n, a, c in zip(f.getlist("name"), f.getlist("qty"), f.getlist("cost")):
        n = n.strip()
        if not n: continue
        try: qty = max(int(float(a or 1)), 1); cost = max(float(c or 0), 0.0)
        except ValueError: continue
        rows.append((n, qty, cost))
    if not rows:
        notify("اكتب اسم قطعة واحدة على الأقل", "warn", "الفاتورة فاضية"); return redirect("/suppliers")
    total = sum(a * c for _, a, c in rows)
    cur = db().execute("insert into invoices(user_id,supplier_id,created,total) values(?,?,?,?)", (uid(), i, today(), total))
    for n, a, c in rows:
        db().execute("insert into needs(user_id,kind,part_id,name,qty,cost,supplier_id,note,invoice_id,created) values(?,?,?,?,?,?,?,?,?,?)",
                     (uid(), "شراء", None, n, a, c, i, "", cur.lastrowid, today()))
    db().commit(); notify(f"INV-{cur.lastrowid:04d} · {total:g} ₪", "ok", "تمت إضافة القطع")
    return redirect({"1": f"/invoices/{cur.lastrowid}/thermal", "2": f"/invoices/{cur.lastrowid}"}.get(f.get("print"), "/suppliers"))

@app.post("/suppliers/edit")
def edit_sup():
    f = request.form
    if f.get("name", "").strip() and q("select 1 from suppliers where id=? and user_id=?", (f.get("sid"), uid())):
        ex("update suppliers set name=?, phone=?, notes=? where id=? and user_id=?", (f["name"].strip(), f.get("phone", ""), f.get("notes", ""), f["sid"], uid()))
        notify(f"تم تعديل بيانات المورد: {f['name'].strip()}", "ok", "تم الحفظ")
    else: notify("اكتب اسم المورد", "warn", "تعذّر التعديل")
    return redirect("/suppliers")

def _doc_lines(raw):
    """يرقّم البنود ويحسب الإشارة: المرتجع سالب. بيرجع (lines, buy_total, ret_total)."""
    lines, buy, ret = [], 0.0, 0.0
    for n, r in enumerate(raw, 1):
        t = abs(r["total"] or 0); rt = r["kind"] == "مرتجع"
        lines.append(dict(r, n=n, signed=-t if rt else t)); ret += t if rt else 0; buy += 0 if rt else t
    return lines, buy, ret

def _sup_ctx(i):
    sp = q("select * from suppliers where id=? and user_id=?", (i, uid()))
    if not sp: abort(404)
    P = supplier_purchases(i).get(i, {"rows": [], "qty": 0, "net": 0.0, "last": ""}); ws = bool(request.args.get("stock"))
    lines, buy, ret = _doc_lines([{"name": r["name"], "kind": r["kind"], "qty": r["qty"], "cost": r["cost"], "total": r["total"], "date": r["created"]} for r in P["rows"]])
    return dict(doc_title="كشف مشتريات من مورد", ref="", party=sp[0]["name"], phone=sp[0]["phone"], lines=lines, net=P["net"], qty=P["qty"], buy_total=buy, ret_total=ret,
                stk=supplier_stock(i).get(i, []) if ws else [], with_stock=ws, can_stock=True, st=settings(), now=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                th_url=f"/suppliers/{i}/print", a4_url=f"/suppliers/{i}/a4", back="/suppliers")

def _inv_ctx(i):
    inv = q("select i.*, s.name sname, s.phone sphone from invoices i left join suppliers s on s.id=i.supplier_id where i.id=? and i.user_id=?", (i, uid()))
    if not inv: return None
    rows = q("select * from needs where invoice_id=? and user_id=?", (i, uid()))
    lines, buy, ret = _doc_lines([{"name": r["name"], "kind": r["kind"], "qty": r["qty"], "cost": r["cost"], "date": r["created"], "total": r["qty"] * r["cost"]} for r in rows])
    return dict(doc_title="فاتورة مشتريات من مورد", ref="INV-%04d" % inv[0]["id"], party=inv[0]["sname"] or "", phone=inv[0]["sphone"], lines=lines, net=inv[0]["total"],
                qty=sum(l["qty"] * (-1 if l["kind"] == "مرتجع" else 1) for l in lines), buy_total=buy, ret_total=ret, stk=[], with_stock=False, can_stock=False, st=settings(), now=inv[0]["created"],
                th_url=f"/invoices/{i}/thermal", a4_url=f"/invoices/{i}", back="/requirements")

@app.route("/suppliers/<int:i>/print")
def sup_print(i): return render_template("thermal", **_sup_ctx(i))

@app.route("/suppliers/<int:i>/a4")
def sup_a4(i): return render_template("a4doc", **_sup_ctx(i))

@app.route("/invoices/<int:i>/thermal")
def invoice_thermal(i):
    c = _inv_ctx(i)
    if not c: abort(404)
    return render_template("thermal", **c)

# ---------- لوحة المالك ----------
OWNER_LABEL = {"active": ("تجربة", "pl-a"), "none": ("تجربة", "pl-a"), "paid": ("مشترك", "pl-g"), "ended": ("منتهي", "pl-r"), "blocked": ("موقوف", "pl-r"), "pending": ("بانتظار الموافقة", "pl-a")}

def _target_user():
    r = q("select u.*, s.trial_start from users u left join settings s on s.user_id=u.id where u.id=? and lower(u.email)<>?", (request.form.get("sid"), OWNER_EMAIL))
    return dict(r[0]) if r else None

@app.route("/owner")
def owner_home():
    now = datetime.datetime.now(); users = []
    k = {"total": 0, "active": 0, "paid": 0, "ended": 0, "blocked": 0, "online": 0}
    for r in q("select u.*, s.trial_start, s.shop_name from users u left join settings s on s.user_id=u.id where lower(u.email)<>? and coalesce(u.status,'active')<>'pending' order by u.id desc", (OWNER_EMAIL,)):
        r = dict(r); st = sub_state(r); lab, pc = OWNER_LABEL[st["state"]]
        try: online = (now - datetime.datetime.fromisoformat(r["last_seen"])).total_seconds() < ONLINE_MIN * 60
        except (TypeError, ValueError): online = False
        users.append(dict(r, st=st, label=lab, pc=pc, online=online, created=r["created"] or r["trial_start"] or "—"))
        k["total"] += 1; k["online"] += online
        k["active" if st["state"] in ("active", "none") else st["state"]] += 1
    _w = q("select v from meta where k='owner_whatsapp'")
    return render_template("owner", users=users, k=k, pend=pend_rows(), owner_wa_raw=(_w[0]["v"] if _w else ""), ttl=("لوحة المالك", "المستخدمون المسجّلون وأيام الاشتراك المتبقية، مع التفعيل والإيقاف"), today=today())

@app.post("/owner/extend")
def owner_extend():
    u = _target_user()
    try: days = max(1, min(int(request.form.get("days") or 30), 3650))
    except ValueError: days = 0
    if not u or not days: flash("تعذّر التمديد|تأكد من المستخدم وعدد الأيام", "warn"); return redirect("/owner")
    st = sub_state(u); td = datetime.date.today()
    base = datetime.date.fromisoformat(st["last"]) if st["left"] > 0 and st["last"] else td - datetime.timedelta(days=1)
    new_last = base + datetime.timedelta(days=days)
    ex("update users set sub_end=?, blocked=0 where id=?", (new_last.isoformat(), u["id"]))
    flash(f"تم تفعيل الاشتراك|{u['email']} · أُضيف {days} يوم · ينتهي بعد آخر يوم {new_last.isoformat()}", "ok"); return redirect("/owner")

@app.post("/owner/setdate")
def owner_setdate():
    u = _target_user(); d = (request.form.get("date") or "").strip()
    if not u: return redirect("/owner")
    if d:
        try: datetime.date.fromisoformat(d)
        except ValueError: flash("تاريخ غير صالح|اختر تاريخاً صحيحاً", "warn"); return redirect("/owner")
    ex("update users set sub_end=? where id=?", (d or None, u["id"]))
    flash(f"تم تعديل الاشتراك|{u['email']} · " + (f"آخر يوم {d}" if d else "رجع للفترة التجريبية"), "ok"); return redirect("/owner")

@app.post("/owner/block")
def owner_block():
    u = _target_user()
    if u:
        nb = 0 if u.get("blocked") else 1
        ex("update users set blocked=? where id=?", (nb, u["id"]))
        flash(("تم إيقاف الحساب|" if nb else "تم تفعيل الحساب|") + u["email"], "warn" if nb else "ok")
    return redirect("/owner")

@app.post("/owner/delete")
def owner_delete():
    u = _target_user()
    if u:
        for p in q("select photo from parts where user_id=? and photo is not null", (u["id"],)):
            del_file(p["photo"])
        for p in q("select photo from tools where user_id=? and photo is not null", (u["id"],)):
            del_file(p["photo"])
        for p in q("select logo from settings where user_id=? and logo is not null", (u["id"],)):
            del_file(p["logo"])
        for t in ("repair_parts", "settings", "notifications", "needs", "invoices", "password_resets", "suppliers", "parts", "repairs", "employees", "emp_stock_log", "emp_customers", "emp_cust_pay", "emp_co_pay", "emp_queue", "cheques", "cash_entries", "cash_counts", "debtors", "debt_entries", "returns_log", "needs_dismissed", "sale_items", "sales", "tools"):
            db().execute("delete from %s where user_id=?" % t, (u["id"],))
        db().execute("delete from users where id=?", (u["id"],)); db().commit()
        flash(f"تم حذف المستخدم|{u['email']} مع كل بياناته", "warn")
    return redirect("/owner")

@app.route("/suppliers/<int:i>/delete")
def del_sup(i):
    ex("delete from suppliers where id=? and user_id=?", (i, uid())); notify("تم حذف مورد", "warn")
    return redirect("/suppliers")

def settings():
    x = q("select * from settings where user_id=?", (uid(),))
    return dict(x[0]) if x else {"shop_name": "شركة الصيانة", "cc": "970", "trial_start": None}

def partners(st=None):
    """أطراف الشركة (شركاء) ونسبهم من الإعدادات. بيرجع [] إذا طرف واحد أو ما في تقسيم."""
    try: L = json.loads((st if st is not None else settings()).get("partners") or "[]")
    except Exception: L = []
    out = []
    for k, x in enumerate(L if isinstance(L, list) else []):
        if isinstance(x, dict):
            out.append({"name": (x.get("name") or "").strip() or f"الطرف {k + 1}", "pct": _f(x.get("pct"), 0.0)})
    return out if len(out) >= 2 else []

def sub_state(r):
    """حالة وصول المستخدم: active=تجربة، paid=مشترك، ended=منتهي، blocked=موقوف يدوياً، owner، none"""
    if not r: return {"state": "none", "kind": "trial", "left": TRIAL_DAYS, "pct": 0, "end": "", "last": ""}
    if (r.get("email") or "").lower() == OWNER_EMAIL: return {"state": "owner", "kind": "owner", "left": 0, "pct": 0, "end": "", "last": ""}
    if (r.get("status") or "active") == "pending": return {"state": "pending", "kind": "trial", "left": TRIAL_DAYS, "pct": 0, "end": "", "last": ""}
    td = datetime.date.today(); one = datetime.timedelta(days=1)
    try:
        if r.get("sub_end"):
            last = datetime.date.fromisoformat(r["sub_end"]); kind = "paid"; left = (last - td).days + 1
            pct = 0 if left > 30 else round((30 - max(left, 0)) / 30 * 100)
        elif r.get("trial_start"):
            start = datetime.date.fromisoformat(r["trial_start"]); kind = "trial"; used = (td - start).days
            last = start + datetime.timedelta(days=TRIAL_DAYS - 1); left = TRIAL_DAYS - used; pct = round(used / TRIAL_DAYS * 100)
        else:
            return {"state": "blocked" if r.get("blocked") else "none", "kind": "trial", "left": TRIAL_DAYS, "pct": 0, "end": "", "last": ""}
    except ValueError:
        last = td - one; kind = "paid"; left = 0; pct = 100
    st = {"kind": kind, "left": max(left, 0), "pct": min(100, max(0, pct)), "end": (last + one).isoformat(), "last": last.isoformat()}
    st["state"] = "ended" if left <= 0 else ("paid" if kind == "paid" else "active")
    if r.get("blocked"): st["state"] = "blocked"
    return st

def trial_info():
    return sub_state(cur_user())

MSG = {ST[0]: "مرحباً {c}، استلمنا جهازك ({d}) في {s}. رقم الطلب #{i}. بنبلغك أول ما يجهز.",
       ST[1]: "مرحباً {c}، جهازك ({d}) جاهز للاستلام من {s}. المبلغ المطلوب: {p} ₪.",
       ST[2]: "شكراً لثقتك {c}! نتمنى تكون راضي عن خدمتنا في {s}."}

def wa(r, cfg):
    ph = "".join(ch for ch in (r["phone"] or "") if ch.isdigit())
    ph = ph[2:] if ph.startswith("00") else cfg["cc"] + ph[1:] if ph.startswith("0") else ph
    t = MSG[r["status"]].format(c=r["customer"], d=r["device"], s=cfg["shop_name"], i=r["id"], p=f"{r['price']:g}")
    return f"https://wa.me/{ph}?text={quote(t)}"

# ===== أسعار الصرف (بتتجلب من الإنترنت وبتنحفظ مؤقتاً، ولو انقطع النت بنعرض آخر سعر محفوظ) =====
FX_URL = os.environ.get("FX_URL", "https://open.er-api.com/v6/latest/USD")
FX_TTL = 30 * 60          # كل قديش نحدّث السعر تلقائياً (ثواني)
FX_RETRY = 90             # أقل فترة بين محاولتين فاشلتين
_fx_lock = threading.Lock()
_fx_mem = {"data": None, "tried": 0.0}

def _fx_saved():
    try:
        with pgdb.connect() as c: r = c.execute("select v from meta where k='fx_cache'").fetchone()
        return json.loads(r[0]) if r else None
    except Exception:
        return None

def _fx_save(d):
    try:
        with pgdb.connect() as c:
            c.execute("insert into meta(k,v) values('fx_cache',?) on conflict(k) do update set v=excluded.v", (json.dumps(d),))
    except Exception:
        pass

def _fx_fetch():
    req = urllib.request.Request(FX_URL, headers={"User-Agent": "REPAIRIX/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=6) as r: j = json.loads(r.read().decode("utf-8"))
    rt = j.get("rates") or {}
    ils, jod = float(rt["ILS"]), float(rt["JOD"])
    if not (0.5 < ils < 50 and 0.1 < jod < 5): raise ValueError("bad rates")
    return ils, jod

def fx_rates(force=False):
    """بترجع dict فيه usd_ils و jod_ils (تلقائي) أو None لو ما في ولا سعر محفوظ."""
    now = time.time()
    with _fx_lock:
        d = _fx_mem["data"] or _fx_saved(); _fx_mem["data"] = d
        fresh = d and now - d.get("ts", 0) < FX_TTL
        if (force and now - _fx_mem["tried"] < 30) or (not force and (fresh or now - _fx_mem["tried"] < FX_RETRY)):
            return d
        _fx_mem["tried"] = now
        try:
            ils, jod = _fx_fetch()
            prev = d or {}
            n = {"usd_ils": ils, "jod_ils": ils / jod, "ts": now,
                 "p_usd": prev.get("usd_ils") if prev.get("usd_ils") not in (None, ils) else prev.get("p_usd"),
                 "p_jod": prev.get("jod_ils") if prev.get("jod_ils") not in (None, ils / jod) else prev.get("p_jod")}
            _fx_mem["data"] = n; _fx_save(n); return n
        except Exception:
            return d

def _sgn(a, b):
    if a is None or b is None or abs(a - b) < 0.0005: return 0
    return 1 if a > b else -1

@app.route("/api/rates")
def api_rates():
    d = fx_rates(force=bool(request.args.get("force")))
    st = settings(); mu = st.get("fx_usd") or 0; mj = st.get("fx_jod") or 0
    usd = mu or (d or {}).get("usd_ils"); jod = mj or (d or {}).get("jod_ils")
    r = jsonify(ok=bool(usd and jod), usd_ils=usd, jod_ils=jod, usd_jod=(usd / jod if usd and jod else None),
                ts=(d or {}).get("ts"), stale=bool(d and not (mu and mj) and time.time() - d.get("ts", 0) > FX_TTL * 2),
                man_usd=bool(mu), man_jod=bool(mj),
                chg_usd=0 if mu else _sgn((d or {}).get("usd_ils"), (d or {}).get("p_usd")),
                chg_jod=0 if mj else _sgn((d or {}).get("jod_ils"), (d or {}).get("p_jod")))
    r.headers["Cache-Control"] = "no-store"; return r

def _fxf(v):
    try: x = float(str(v or "").replace(",", ".").strip()); return x if 0.01 < x < 1000 else None
    except ValueError: return None

def save_logo(f):
    """شعار الشركة: بنتحقق من الصيغة الفعلية للملف (مو بس الامتداد) وإنه أقل من 2 ميجا."""
    if not f or not f.filename: return None, None
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp"): return None, "اختر صورة بصيغة JPG أو PNG أو WEBP"
    head = f.stream.read(12); f.stream.seek(0, 2); size = f.stream.tell(); f.stream.seek(0)
    if size > 2 * 1024 * 1024: return None, "حجم الشعار أكبر من 2 ميجا"
    ok = head[:8] == b"\x89PNG\r\n\x1a\n" or head[:3] == b"\xff\xd8\xff" or (head[:4] == b"RIFF" and head[8:12] == b"WEBP")
    if not ok: return None, "الملف مو صورة صالحة"
    name = uuid.uuid4().hex + ext; put_file(name, f.read())
    return name, None

@app.route("/settings", methods=["GET", "POST"])
def settings_page():
    if request.method == "POST":
        old_logo = settings().get("logo")
        un = (request.form.get("username") or "").strip().lower()
        if un != (cur_user().get("username") or ""):
            if not re.fullmatch(r"[a-z0-9._-]{3,30}", un): notify("اسم المستخدم: 3-30 حرف إنجليزي أو أرقام أو . _ -", "warn", "اسم المستخدم")
            elif username_taken(un, uid()): notify("اسم المستخدم مأخوذ، اختر غيره", "warn", "اسم المستخدم")
            else: ex("update users set username=? where id=?", (un, uid())); notify("تم تغيير اسم المستخدم — سجّل دخولك فيه من الآن", "ok")
        ex("insert into settings(user_id,shop_name,cc) values(?,?,?) on conflict(user_id) do update set shop_name=excluded.shop_name, cc=excluded.cc", (uid(), request.form["shop_name"], request.form["cc"].strip()))
        ex("update settings set fx_usd=?, fx_jod=?, address=? where user_id=?", (_fxf(request.form.get("fx_usd")), _fxf(request.form.get("fx_jod")), (request.form.get("address") or "").strip()[:200], uid()))
        f = request.files.get("logo"); new_logo = None
        if request.form.get("rm_logo"):
            ex("update settings set logo=null where user_id=?", (uid(),)); new_logo = ""
        elif f and f.filename:
            n, err = save_logo(f)
            if n: ex("update settings set logo=? where user_id=?", (n, uid())); new_logo = n
            else: notify(err or "اختر صورة بصيغة JPG أو PNG أو WEBP", "warn", "تعذّر رفع الشعار")
        if old_logo and new_logo is not None and new_logo != old_logo:
            del_file(old_logo)
        n = max(1, min(5, _i(request.form.get("ptn_n"), 1)))
        if n < 2:
            ex("update settings set partners=null where user_id=?", (uid(),))
        else:
            L = [{"name": (request.form.get(f"ptn_name{k}") or "").strip()[:40], "pct": _f(request.form.get(f"ptn_pct{k}"), 0.0)} for k in range(n)]
            if sum(x["pct"] for x in L) <= 0: L = [dict(x, pct=round(100 / n, 2)) for x in L]
            if abs(sum(x["pct"] for x in L) - 100) > 0.05 or any(x["pct"] < 0 for x in L):
                notify("مجموع نسب الأطراف لازم يكون 100% — ما انحفظ تقسيم المربح", "warn", "نسب الأطراف")
            else:
                ex("update settings set partners=? where user_id=?", (json.dumps(L, ensure_ascii=False), uid()))
        notify("تم حفظ الإعدادات", "ok")
        return redirect("/settings")
    return render_template("settings", st=settings(), ptn=partners(), email=cur_user()["email"], un=(cur_user().get("username") or ""), pw_err=None, pw_ok=bool(request.args.get("pw")))

@app.route("/shoplogo")
def shop_logo():
    n = settings().get("logo")
    if not n: abort(404)
    r = send_from_directory(UP, n); r.headers["Cache-Control"] = "private, max-age=86400"; return r

@app.route("/settings/password", methods=["POST"])
def settings_password():
    u = cur_user(); old, n1, n2 = request.form.get("old", ""), request.form.get("new", ""), request.form.get("new2", "")
    err = None
    if not check_password_hash(u["pw"], old): err = "كلمة السر الحالية غلط"
    elif len(n1) < 6: err = "كلمة السر الجديدة لازم تكون 6 أحرف على الأقل"
    elif n1 != n2: err = "تأكيد كلمة السر ما بيطابق"
    elif n1 == old: err = "اختر كلمة سر مختلفة عن الحالية"
    if err: return render_template("settings", st=settings(), email=u["email"], un=(u.get("username") or ""), pw_err=err, pw_ok=False)
    ex("update users set pw=? where id=?", (generate_password_hash(n1), u["id"]))
    ex("update password_resets set used=1 where user_id=?", (u["id"],))
    notify("تم تغيير كلمة السر", "ok")
    return redirect("/settings?pw=1")

@app.route("/repairs/<int:i>/print")
def receipt(i):
    x = q(f"select r.*, {PN} from repairs r where r.id=? and r.user_id=?", (i, uid()))
    return render_template("receipt", r=x[0], st=settings()) if x else redirect("/repairs")

# ---------- المتطلبات والمرتجعات ----------
def _sup_ok(sid, u=None):
    """بيرجع رقم المورد إذا موجود فعلاً عند هالمستخدم، وإلا None."""
    u = u or uid()
    if not sid: return None
    return sid if q("select 1 from suppliers where id=? and user_id=?", (sid, u)) else None

def need_defaults(p, u=None):
    """السعر والمورد تلقائياً لقطعة: من بيانات القطعة، وإذا ناقصين من آخر بند سابق لنفس القطعة."""
    u = u or uid()
    cost = p["cost"] or 0; sid = _sup_ok(p["supplier_id"], u)
    if not cost or not sid:
        for r in q("select cost, supplier_id from needs where user_id=? and part_id=? order by id desc", (u, p["id"])):
            if not cost and (r["cost"] or 0) > 0: cost = r["cost"]
            if not sid: sid = _sup_ok(r["supplier_id"], u)
            if cost and sid: break
    return cost, sid

def sync_needs(u=None):
    """بيضيف القطع الناقصة (الكمية <= حد التنبيه) لبنود المتطلبات تلقائياً، بسعرها ومورّدها. بيرجع عدد اللي انضاف."""
    u = u or uid()
    if not u: return 0
    low = q("select * from parts where user_id=? and qty<=coalesce(min_qty,2)", (u,))
    have = {r["part_id"] for r in q("select part_id from needs where user_id=? and invoice_id is null and kind='شراء' and part_id is not null", (u,))}
    dis = {r["part_id"]: r["qty"] for r in q("select part_id, qty from needs_dismissed where user_id=?", (u,))}
    add = 0; lowq = {}
    for p in low:
        lowq[p["id"]] = p["qty"]; mn = p["min_qty"] if p["min_qty"] is not None else 2; want = max(mn * 2 - p["qty"], 1)
        if p["id"] in have:
            db().execute("update needs set qty=? where user_id=? and part_id=? and invoice_id is null and kind='شراء' and auto=1 and coalesce(qty_locked,0)=0", (want, u, p["id"])); continue
        if dis.get(p["id"]) == p["qty"]: continue          # المستخدم حذفه وما تغيّرت الكمية من وقتها
        cost, sid = need_defaults(p, u)
        db().execute("insert into needs(user_id,kind,part_id,name,qty,cost,supplier_id,note,created,auto) values(?,?,?,?,?,?,?,?,?,1)",
                     (u, "شراء", p["id"], plabel(p), want, cost, sid, "نقص مخزون", today())); add += 1
    for pid_, dq in dis.items():
        if lowq.get(pid_) != dq: db().execute("delete from needs_dismissed where user_id=? and part_id=?", (u, pid_))
    # القطع اللي رجع مخزونها طبيعي: بندها التلقائي بينشال
    db().execute("delete from needs where user_id=? and auto=1 and invoice_id is null and kind='شراء' and part_id in (select id from parts where user_id=? and qty>coalesce(min_qty,2))", (u, u))
    # أي بند مفتوح بدون مورد أو بدون سعر وقطعته معروفة: بنعبّيه من القطعة
    for n in q("select n.id nid, n.cost ncost, n.supplier_id nsid, n.part_id from needs n where n.user_id=? and n.invoice_id is null and n.part_id is not null and (n.supplier_id is null or n.cost is null or n.cost=0)", (u,)):
        pr = q("select * from parts where id=? and user_id=?", (n["part_id"], u))
        if not pr: continue
        dc, ds = need_defaults(pr[0], u)
        db().execute("update needs set supplier_id=coalesce(?, supplier_id), cost=case when cost is null or cost=0 then ? else cost end where id=?", (None if _sup_ok(n["nsid"], u) else ds, dc, n["nid"]))
    db().commit()
    return add

@app.after_request
def _auto_sync_needs(resp):
    """أي عملية بتغيّر المخزون (صيانة، تسليم موظف، مرتجع، تعديل كمية...) بتحدّث النواقص لحالها."""
    try:
        if request.method == "POST" and uid() and request.endpoint not in ("static", "login", "register", "forgot", "reset") and resp.status_code in (200, 302, 303):
            sync_needs()
    except Exception:
        pass
    return resp

def need_options():
    """قائمة الأصناف للبحث بنافذة الإضافة: قطع المخزون + أصناف اشتريتها قبل، مع سعرها ومورّدها."""
    out, seen = [], set()
    for p in q("select * from parts where user_id=? order by category,name,color", (uid(),)):
        lab = plabel(p)
        if lab.lower() in seen: lab = f"{lab} ({p['category']}) #{p['id']}"
        seen.add(lab.lower()); cost, sid = need_defaults(p)
        out.append({"label": lab, "pid": p["id"], "cost": cost, "sup": sid or "", "qty": p["qty"]})
    for r in q("select name, cost, supplier_id from needs where user_id=? and part_id is null and id in (select max(id) from needs where user_id=? and part_id is null group by lower(name))", (uid(), uid())):
        if (r["name"] or "").lower() in seen: continue
        seen.add(r["name"].lower()); out.append({"label": r["name"], "pid": "", "cost": r["cost"] or 0, "sup": _sup_ok(r["supplier_id"]) or "", "qty": None})
    return out

def _fix_invoice(inv, u):
    rows = q("select kind,qty,cost from needs where invoice_id=? and user_id=?", (inv, u))
    if not rows: db().execute("delete from invoices where id=? and user_id=?", (inv, u))
    else: db().execute("update invoices set total=? where id=? and user_id=?", (sum(r["qty"] * r["cost"] * (-1 if r["kind"] == "مرتجع" else 1) for r in rows), inv, u))

def _drop_ret_needs(rids, u=None):
    """لما بينحذف مرتجع: بنشيل بنده من المتطلبات وبنصحّح الفاتورة إذا كان داخلها."""
    u = u or uid()
    for rid in rids:
        for n in q("select id, invoice_id from needs where user_id=? and ret_id=?", (u, rid)):
            db().execute("delete from needs where id=?", (n["id"],))
            if n["invoice_id"]: _fix_invoice(n["invoice_id"], u)
    db().commit()

def add_return_need(u, part_id, name, qty, cost, sid, note, ret_id, created):
    db().execute("insert into needs(user_id,kind,part_id,name,qty,cost,supplier_id,note,created,auto,ret_id) values(?,?,?,?,?,?,?,?,?,0,?)",
                 (u, "مرتجع", part_id, name, qty, cost or 0, sid, note, created, ret_id)); db().commit()

@app.route("/requirements", methods=["GET", "POST"])
def requirements():
    if request.method == "POST":
        f = request.form; kind = "مرتجع" if f.get("kind") == "مرتجع" else "شراء"
        name = f.get("name", "").strip(); n = max(_i(f.get("qty"), 1), 1); pid = _i(f.get("part_id")) or None
        p = q("select * from parts where id=? and user_id=?", (pid, uid())) if pid else []
        if not p and name:   # كتب اسم قطعة موجودة بالمخزون بدون ما يختارها من القائمة
            for x in q("select * from parts where user_id=?", (uid(),)):
                if plabel(x).strip().lower() == name.lower(): p = [x]; break
        p = p[0] if p else None
        if not name and not p:
            notify("اكتب اسم الصنف أو اختر قطعة من القائمة", "warn", "البند ناقص"); return redirect("/requirements")
        cost = _f(f.get("cost")) if f.get("cost", "").strip() != "" else None
        sup = _sup_ok(_i(f.get("supplier_id")) or None)
        if p:
            name = plabel(p); pid = p["id"]; dc, ds = need_defaults(p)
            if cost is None: cost = dc
            sup = sup or ds
        else:
            pid = None
            last = q("select cost, supplier_id from needs where user_id=? and lower(name)=lower(?) order by id desc limit 1", (uid(), name))
            if last:
                if cost is None: cost = last[0]["cost"]
                sup = sup or _sup_ok(last[0]["supplier_id"])
        cost = cost or 0; note = f.get("note", "").strip(); rid = None
        if kind == "مرتجع":
            if p and n > p["qty"]:
                notify(f"المتوفر بالمخزن الرئيسي {p['qty']} فقط", "warn", "الكمية غير كافية"); return redirect("/requirements?kind=مرتجع")
            reason = f.get("reason") if f.get("reason") in RET_REASONS else "أخرى"
            sn = q("select name from suppliers where id=? and user_id=?", (sup, uid()))[0]["name"] if sup else ""
            if p: db().execute("update parts set qty=qty-? where id=? and user_id=?", (n, pid, uid()))
            rid = db().execute("insert into returns_log(user_id,part_id,part_name,category,qty,unit_cost,total,supplier_id,supplier_name,reason,note,created) values(?,?,?,?,?,?,?,?,?,?,?,?)",
                               (uid(), pid, name, (p["category"] if p else "أخرى"), n, cost, round(n * cost, 2), sup, sn, reason, note, today())).lastrowid
            note = " · ".join(x for x in (reason, note) if x)
        db().execute("insert into needs(user_id,kind,part_id,name,qty,cost,supplier_id,note,created,auto,ret_id) values(?,?,?,?,?,?,?,?,?,0,?)", (uid(), kind, pid, name, n, cost, sup, note, today(), rid))
        db().commit()
        tail = "" if sup else " — بدون مورد، حدّده من الجدول"
        if kind == "مرتجع": notify(f"{name} · {n}" + tail, "warn", "تم تسجيل مرتجع")
        else: notify(f"{name} · {n}" + tail, "ok", "تمت إضافة بند للمتطلبات")
        return redirect("/requirements?kind=" + kind if kind == "مرتجع" else "/requirements")
    sync_needs()
    kind = request.args.get("kind", ""); kind = kind if kind in ("شراء", "مرتجع") else ""
    allr = [dict(r) for r in q("select n.*, s.name sname, p.qty stock, p.min_qty pmin from needs n left join suppliers s on s.id=n.supplier_id and s.user_id=n.user_id left join parts p on p.id=n.part_id where n.user_id=? and n.invoice_id is null order by n.id desc", (uid(),))]
    cnt = {"شراء": sum(1 for r in allr if r["kind"] == "شراء"), "مرتجع": sum(1 for r in allr if r["kind"] == "مرتجع")}
    items = [r for r in allr if not kind or r["kind"] == kind]; groups = {}; net = 0.0
    for r in items:
        r["sid"] = r["supplier_id"] if r["sname"] else None; sg = -1 if r["kind"] == "مرتجع" else 1; r["total"] = (r["qty"] or 0) * (r["cost"] or 0)
        g_ = groups.setdefault(r["sid"], {"id": r["sid"], "name": r["sname"] or "بدون مورد", "nbuy": 0, "nret": 0, "net": 0.0})
        g_["nret" if sg < 0 else "nbuy"] += 1; g_["net"] += sg * r["total"]; net += sg * r["total"]
    gl = sorted(groups.values(), key=lambda x: (x["id"] is None, x["name"]))
    invs = q("select i.*, s.name sname from invoices i left join suppliers s on s.id=i.supplier_id where i.user_id=? order by i.id desc limit 30", (uid(),))
    return render_template("requirements", items=items, groups=gl, cnt=cnt, kind=kind, net=net, invs=invs, opts=need_options(), reasons=RET_REASONS,
                           sup=q("select * from suppliers where user_id=? order by name", (uid(),)))

@app.route("/requirements/auto")
def needs_auto():
    c = sync_needs()
    if c: notify(f"أُضيف {c} بند من القطع الناقصة", "ok", "تمت إضافة النواقص")
    else: notify("ما في نواقص جديدة حالياً", "info", "المخزون كافٍ")
    return redirect("/requirements")

@app.route("/requirements/<int:i>/delete")
def del_need(i):
    r = q("select * from needs where id=? and user_id=? and invoice_id is null", (i, uid()))
    if r and r[0]["auto"] and r[0]["part_id"]:
        pr = q("select qty from parts where id=? and user_id=?", (r[0]["part_id"], uid()))
        if pr: ex("insert into needs_dismissed(user_id,part_id,qty) values(?,?,?) on conflict(user_id,part_id) do update set qty=excluded.qty", (uid(), r[0]["part_id"], pr[0]["qty"]))
    ex("delete from needs where id=? and user_id=? and invoice_id is null", (i, uid()))
    k = request.args.get("kind", "")
    return redirect("/requirements" + ("?kind=" + k if k in ("شراء", "مرتجع") else ""))

@app.post("/requirements/<int:i>/qty")
def need_qty(i):
    n = max(_i(request.form.get("qty"), 1), 1)
    ex("update needs set qty=?, qty_locked=1 where id=? and user_id=? and invoice_id is null and kind='شراء'", (n, i, uid()))
    return ("", 204)

@app.post("/requirements/<int:i>/supplier")
def need_supplier(i):
    sid = _sup_ok(_i(request.form.get("supplier_id")) or None)
    ex("update needs set supplier_id=? where id=? and user_id=? and invoice_id is null", (sid, i, uid()))
    return ("", 204)

@app.post("/invoices/new")
def new_invoice():
    f = request.form; kind = f.get("kind") if f.get("kind") in ("شراء", "مرتجع") else ""; back = _safe_back("/requirements")
    if f.get("all"):   # كل البنود المفتوحة (أو بنود مورد واحد) بتتوزع على موردينها تلقائياً
        sql, par = "select * from needs where user_id=? and invoice_id is null", [uid()]
        if kind: sql += " and kind=?"; par.append(kind)
        if f.get("sid"): sql += " and supplier_id=?"; par.append(_i(f.get("sid")))
        items = q(sql, par)
    else:
        items = [x for i in f.getlist("item_id") for x in q("select * from needs where id=? and user_id=? and invoice_id is null", (i, uid()))]
    if not items: notify("ما في بنود لإنشاء فاتورة منها", "warn", "ما في بنود محددة"); return redirect(back)
    by, nosup = {}, 0
    for x in items:
        sid = _sup_ok(x["supplier_id"])
        if not sid and x["part_id"]:
            pr = q("select * from parts where id=? and user_id=?", (x["part_id"], uid()))
            if pr: sid = need_defaults(pr[0])[1]
        if not sid: nosup += 1; continue
        by.setdefault(sid, []).append(x)
    made = []
    for sid, xs in by.items():
        net = sum(x["qty"] * x["cost"] * (-1 if x["kind"] == "مرتجع" else 1) for x in xs)
        cur = db().execute("insert into invoices(user_id,supplier_id,created,total) values(?,?,?,?)", (uid(), sid, today(), net))
        for x in xs: db().execute("update needs set invoice_id=?, supplier_id=? where id=?", (cur.lastrowid, sid, x["id"]))
        made.append(cur.lastrowid)
    db().commit()
    if nosup: notify(f"{nosup} بند بدون مورد ما انضمّوا لأي فاتورة — حدّد موردهم من الجدول", "warn", "بنود بدون مورد")
    if not made: return redirect(back)
    if len(made) == 1:
        notify(f"فاتورة INV-{made[0]:04d}", "ok", "تم إنشاء فاتورة المورد"); return redirect(f"/invoices/{made[0]}")
    notify(f"تم إنشاء {len(made)} فواتير، واحدة لكل مورد", "ok", "فواتير الموردين"); return redirect(back + "#invs")

@app.route("/invoices/<int:i>")
def invoice(i):
    c = _inv_ctx(i)
    return render_template("a4doc", **c) if c else redirect("/requirements")

# الدخل والمربح بيُحسبوا فقط للصيانات "تم التسليم"، وبتاريخ التسليم (done_date). غير المسلَّمة بتضل على تاريخ تسجيلها.
DELIV = "'تم التسليم'"
EFF = "(case when r.status='تم التسليم' then coalesce(r.done_date, r.created) else r.created end)"   # تاريخ ظهور الصيانة
DD = "coalesce(done_date, created)"                                                                 # تاريخ التسليم (بدون alias)

PN = "(select string_agg(p.name || coalesce(' · ' || p.maker, '') || coalesce(' · ' || p.color, ''), '، ') from repair_parts rp join parts p on p.id=rp.part_id where rp.repair_id=r.id) pn"

@app.route("/repairs", methods=["GET", "POST"])
def repairs():
    if request.method == "POST":
        f = request.form; used = []; pcs = f.getlist("part_cost"); seen = set()
        for k, pid in enumerate(f.getlist("part_id")):
            if pid in seen: continue
            seen.add(pid)
            p = q("select * from parts where id=? and user_id=? and qty>0", (pid, uid()))
            if p:
                pc = max(_f(pcs[k], p[0]["cost"] or 0) if k < len(pcs) else (p[0]["cost"] or 0), 0)   # جملة القطعة (المسجّلة أو المعدّلة)
                used.append((p[0], pc))
        cost = _f(f.get("cost")) if (f.get("cost") or "").strip() != "" else sum(pc for _, pc in used)
        rd = _vdate(f.get("created"), today())
        if rd > today(): rd = today()   # ما بنسجل بتاريخ مستقبلي
        cur = db().execute("insert into repairs(created,customer,phone,device,issue,cost,price,user_id) values(?,?,?,?,?,?,?,?)",
                           (rd, f["customer"], f["phone"], f["device"], f["issue"], cost, _f(f["price"]), uid()))
        for p, pc in used:
            db().execute("update parts set qty=qty-1 where id=?", (p["id"],))
            db().execute("insert into repair_parts(repair_id,part_id,cost,user_id) values(?,?,?,?)", (cur.lastrowid, p["id"], pc, uid()))
        db().commit()
        notify(f"تم تسجيل صيانة جديدة #{cur.lastrowid} للزبون {f['customer']}" + (f" بتاريخ {rd}" if rd != today() else ""), "ok")
        for p, _pc in used:
            n = q("select name,qty,min_qty from parts where id=?", (p["id"],))[0]
            if n["qty"] <= n["min_qty"]:
                notify(f"نفدت القطعة {n['name']}" if n["qty"] == 0 else f"قطعة {n['name']} قربت تخلص (الكمية {n['qty']})", "warn")
        return redirect("/repairs" if rd == today() else f"/repairs?from={rd}&to={rd}")   # بيفتح جدول نفس اليوم اللي سجّلت فيه
    td = today(); t0 = datetime.date.fromisoformat(td); yd = (t0 - datetime.timedelta(days=1)).isoformat()
    d7 = (t0 - datetime.timedelta(days=6)).isoformat(); m1 = t0.replace(day=1).isoformat()
    n_open = q("select count(*) n from repairs where user_id=? and status=?", (uid(), ST[0]))[0]["n"]
    if request.args.get("open"):
        mode = "open"; d1 = d2 = td
        where, args = "r.status=?", (ST[0],)
        rtitle = "الأجهزة اللي لسا قيد الصيانة (بكل التواريخ)"; lab_inc, lab_prof = "إجمالي أسعارها", "المربح المتوقع"
    else:
        af = request.args.get("from"); at = request.args.get("to")
        d1 = _vdate(af, td); d2 = _vdate(at, d1 if af else td)
        if d2 < d1: d1, d2 = d2, d1
        d1, d2 = min(d1, td), min(d2, td)
        where, args = f"{EFF} between ? and ?", (d1, d2)
        mode = "today" if d1 == d2 == td else "yday" if d1 == d2 == yd else "7" if (d1, d2) == (d7, td) else "month" if (d1, d2) == (m1, td) else "custom"
        if d1 == d2:
            wd = AR_DAYS[datetime.date.fromisoformat(d1).weekday()]
            rtitle = ("صيانات اليوم · " if d1 == td else "صيانات يوم ") + f"{wd} {d1}"
            lab_inc, lab_prof = "الدخل اليومي (تم التسليم)", "مربح اليوم (تم التسليم)"
        else:
            rtitle = f"صيانات من {d1} إلى {d2}"; lab_inc, lab_prof = "دخل الفترة (تم التسليم)", "مربح الفترة (تم التسليم)"
    rows = q(f"select r.*, {PN} from repairs r where r.user_id=? and {where} order by {EFF} desc, r.id desc limit 3000", (uid(),) + args)
    # الدخل/المربح/الجملة: للمسلَّم فقط (إلا بعرض "قيد الصيانة" فبيعرض المتوقع لكل الأجهزة)
    cnt = "true" if mode == "open" else "r.status='تم التسليم'"
    tot = q(f"select count(*) n, coalesce(sum(case when {cnt} then price end),0) inc, coalesce(sum(case when {cnt} then cost end),0) c, "
            f"coalesce(sum(case when r.status='تم التسليم' then 1 end),0) nd from repairs r where r.user_id=? and {where}", (uid(),) + args)[0]
    prev = nxt = None
    if mode in ("today", "yday", "custom") and d1 == d2:
        prev = (datetime.date.fromisoformat(d1) - datetime.timedelta(days=1)).isoformat()
        nxt = (datetime.date.fromisoformat(d1) + datetime.timedelta(days=1)).isoformat() if d1 < td else None
    cfg = settings(); ptn = partners(cfg)
    ids = [x["id"] for x in rows]; rps = {}
    if ids:
        for z in q("select rp.id, rp.repair_id, rp.cost, p.name, p.color from repair_parts rp left join parts p on p.id=rp.part_id where rp.user_id=? and rp.repair_id in (%s) order by rp.id" % ",".join("?" * len(ids)), (uid(),) + tuple(ids)):
            rps.setdefault(z["repair_id"], []).append({"id": z["id"], "n": (z["name"] or "قطعة محذوفة") + (" · " + z["color"] if z["color"] else ""), "c": round(z["cost"] or 0, 2)})
    def _sh(x):
        if not ptn or not (x["status"] == ST[2] or mode == "open"): return ""
        pr = (x["price"] or 0) - (x["cost"] or 0)
        return " · ".join(f"{p['name']} {round(pr * p['pct'] / 100, 2):g}" for p in ptn)
    rows = [dict(x, wa=wa(x, cfg), rps=rps.get(x["id"], []), sh=_sh(x)) for x in rows]
    prof = (tot["inc"] or 0) - (tot["c"] or 0); split = [dict(p, amt=round(prof * p["pct"] / 100, 2)) for p in ptn]
    return render_template("repairs", rows=rows, tot=tot, d1=d1, d2=d2, mode=mode, rtitle=rtitle, lab_inc=lab_inc, lab_prof=lab_prof, prev=prev, nxt=nxt, n_open=n_open,
                           plist=[{"id": p["id"], "n": p["name"] + (" · " + p["maker"] if p["maker"] else "") + (" · " + p["color"] if p["color"] else ""), "c": p["category"], "q": p["qty"], "cost": p["cost"] or 0, "price": p["price"] or 0} for p in q("select * from parts where qty>0 and user_id=? order by category,name", (uid(),))], st=ST,
                           today=td, yday=yd, d7=d7, m1=m1, split=split, reasons=RET_REASONS)

AR_DAYS = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]  # date.weekday(): الاثنين = 0

@app.route("/repairs/export")
def export_range():
    """كشف يومي (اليوم | التاريخ | الدخل | المربح) لفترة محددة، حسب تاريخ التسليم (الصيانات بحالة تم التسليم)."""
    try:
        d1 = datetime.date.fromisoformat(request.args.get("from", "")); d2 = datetime.date.fromisoformat(request.args.get("to", ""))
    except ValueError:
        notify("اختر تاريخ البداية وتاريخ النهاية ثم أعد المحاولة", "warn", "تعذّر التصدير"); return redirect("/repairs")
    if d1 > d2: d1, d2 = d2, d1
    if (d2 - d1).days > 731:
        notify("الحد الأقصى لفترة التصدير سنتان", "warn", "فترة طويلة"); return redirect("/repairs")
    got = {r["done_date"]: r for r in q(f"select {DD} done_date, sum(price) inc, sum(price-cost) p from repairs where user_id=? and status={DELIV} and {DD} between ? and ? group by {DD}",
                                          (uid(), d1.isoformat(), d2.isoformat()))}
    days, d = [], d1
    while d <= d2:
        r = got.get(d.isoformat()); days.append((d, AR_DAYS[d.weekday()], (r["inc"] if r else 0) or 0, (r["p"] if r else 0) or 0)); d += datetime.timedelta(days=1)
    ti, tp = sum(x[2] for x in days), sum(x[3] for x in days); fname = f"income_{d1}_{d2}"
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.worksheet.properties import PageSetupProperties
    except ImportError:  # بدون openpyxl: ملف CSV يفتحه Excel أيضاً
        out = io.StringIO(); w = csv.writer(out); w.writerow(["اليوم", "التاريخ", "الدخل", "المربح"])
        for d, n, inc, p in days: w.writerow([n, d.strftime("%d/%m/%Y"), inc, p])
        w.writerow(["المجموع", "", ti, tp])
        return Response("\ufeff" + out.getvalue(), mimetype="text/csv; charset=utf-8", headers={"Content-Disposition": f"attachment; filename={fname}.csv"})
    wb = Workbook(); ws = wb.active; ws.title = "الدخل اليومي"; ws.sheet_view.rightToLeft = True
    thin = Side(style="thin", color="E4E8F1"); box = Border(left=thin, right=thin, top=thin, bottom=thin)
    ctr = Alignment(horizontal="center", vertical="center"); NUM = "#,##0.00"
    ws.merge_cells("A1:D1"); ws["A1"] = f"{settings()['shop_name']} — كشف الدخل والمربح اليومي"
    ws["A1"].font = Font(bold=True, size=16, color="0C1233"); ws["A1"].alignment = ctr; ws.row_dimensions[1].height = 32
    ws.merge_cells("A2:D2"); ws["A2"] = f"الفترة: من {d1:%d/%m/%Y} إلى {d2:%d/%m/%Y}  ·  حسب تاريخ التسليم"
    ws["A2"].font = Font(size=11, color="64748B"); ws["A2"].alignment = ctr
    for c, h in enumerate(["اليوم", "التاريخ", "الدخل (₪)", "المربح (₪)"], 1):
        x = ws.cell(row=4, column=c, value=h); x.font = Font(bold=True, color="FFFFFF", size=12); x.fill = PatternFill("solid", fgColor="4F46E5"); x.alignment = ctr; x.border = box
    ws.row_dimensions[4].height = 26
    for n, (d, name, inc, p) in enumerate(days):
        r = 5 + n; fill = PatternFill("solid", fgColor="F6F8FD") if n % 2 else None
        for c, v in enumerate([name, d, inc, p], 1):
            x = ws.cell(row=r, column=c, value=v); x.alignment = ctr; x.border = box
            if fill: x.fill = fill
        ws.cell(row=r, column=2).number_format = "DD/MM/YYYY"; ws.cell(row=r, column=3).number_format = NUM; ws.cell(row=r, column=4).number_format = NUM
        if d.weekday() == 4:  # الجمعة
            ws.cell(row=r, column=1).font = Font(color="E11D48", bold=True)
    r = 5 + len(days); ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=2); ws.cell(row=r, column=1, value="المجموع")
    ws.cell(row=r, column=3, value=ti); ws.cell(row=r, column=4, value=tp)
    for c in range(1, 5):
        x = ws.cell(row=r, column=c); x.font = Font(bold=True, size=12, color="0C1233"); x.fill = PatternFill("solid", fgColor="E0E7FF"); x.alignment = ctr; x.border = box
        if c > 2: x.number_format = NUM
    for col, wd in zip("ABCD", (16, 16, 18, 18)): ws.column_dimensions[col].width = wd
    ws.freeze_panes = "A5"; ws.print_title_rows = "4:4"; ws.page_setup.orientation = "portrait"; ws.page_setup.fitToWidth = 1; ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    buf = io.BytesIO(); wb.save(buf)
    return Response(buf.getvalue(), mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename={fname}.xlsx"})

def _back_repairs():
    """بيرجّعك لنفس الجدول (نفس اليوم/الفلتر) اللي كنت فيه بدل ما يرجع لجدول اليوم."""
    ref = request.referrer or ""
    try:
        from urllib.parse import urlparse
        u = urlparse(ref)
        if u.netloc == request.host and u.path == "/repairs": return redirect(u.path + ("?" + u.query if u.query else ""))
    except ValueError:
        pass
    return redirect("/repairs")

@app.route("/repairs/<int:i>/edit", methods=["GET", "POST"])
def edit_repair(i):
    r = q("select * from repairs where id=? and user_id=?", (i, uid()))
    if not r: return redirect("/repairs")
    if request.method == "POST":
        f = request.form
        rd = min(_vdate(f.get("created"), r[0]["created"]), today())
        dd = r[0]["done_date"]
        if r[0]["status"] == ST[2]:   # تاريخ التسليم قابل للتعديل (ما بيصير قبل تاريخ التسجيل ولا بعد اليوم)
            dd = min(max(_vdate(f.get("done_date"), dd or rd), rd), today())
        ex("update repairs set customer=?,phone=?,device=?,issue=?,price=?,cost=?,created=?,done_date=? where id=? and user_id=?",
           (f["customer"], f["phone"], f["device"], f["issue"], _f(f["price"]), _f(f["cost"]), rd, dd, i, uid()))
        notify(f"تم تعديل الصيانة #{i}")
        shown = dd if r[0]["status"] == ST[2] else rd
        return redirect("/repairs" if shown == today() else f"/repairs?from={shown}&to={shown}")
    return render_template("edit", r=r[0], today=today(), rps=_repair_parts(i), plist=_plist())

@app.route("/repairs/<int:i>/delete")
def del_repair(i):
    if q("select 1 from repairs where id=? and user_id=?", (i, uid())):
        db().execute("update parts set qty=qty+1 where user_id=? and id in (select part_id from repair_parts where repair_id=?)", (uid(), i))
        db().execute("delete from repair_parts where repair_id=?", (i,))
        db().execute("delete from repairs where id=?", (i,)); db().commit()
        notify(f"تم حذف الصيانة #{i} وإرجاع قطعها للمخزون", "warn")
    return _back_repairs()

def _plist():
    return [{"id": p["id"], "n": p["name"] + (" · " + p["maker"] if p["maker"] else "") + (" · " + p["color"] if p["color"] else ""), "c": p["category"], "q": p["qty"], "cost": p["cost"] or 0, "price": p["price"] or 0} for p in q("select * from parts where qty>0 and user_id=? order by category,name", (uid(),))]

def _repair_parts(i):
    return [{"id": z["id"], "n": (z["name"] or "قطعة محذوفة") + (" · " + z["color"] if z["color"] else ""), "c": round(z["cost"] or 0, 2)} for z in
            q("select rp.id, rp.cost, p.name, p.color from repair_parts rp left join parts p on p.id=rp.part_id where rp.repair_id=? and rp.user_id=? order by rp.id", (i, uid()))]

def _low_stock_notify(pid):
    n = q("select name,qty,min_qty from parts where id=?", (pid,))
    if n and n[0]["qty"] <= n[0]["min_qty"]:
        notify(f"نفدت القطعة {n[0]['name']}" if n[0]["qty"] == 0 else f"قطعة {n[0]['name']} قربت تخلص (الكمية {n[0]['qty']})", "warn")

@app.post("/repairs/<int:i>/addpart")
def repair_addpart(i):
    if not q("select 1 from repairs where id=? and user_id=?", (i, uid())): return redirect("/repairs")
    p = q("select * from parts where id=? and user_id=? and qty>0", (_i(request.form.get("part_id")), uid()))
    if not p:
        notify("القطعة غير متوفرة بالمخزون", "warn", "تعذّرت الإضافة"); return redirect(f"/repairs/{i}/edit")
    p = p[0]
    db().execute("update parts set qty=qty-1 where id=? and user_id=?", (p["id"], uid()))
    db().execute("insert into repair_parts(repair_id,part_id,cost,user_id) values(?,?,?,?)", (i, p["id"], p["cost"] or 0, uid()))
    db().execute("update repairs set cost=coalesce(cost,0)+? where id=? and user_id=?", (p["cost"] or 0, i, uid())); db().commit()
    notify(f"{plabel(p)} انخصمت من المخزون وانضافت للصيانة #{i}", "ok", "تمت إضافة القطعة"); _low_stock_notify(p["id"])
    return redirect(f"/repairs/{i}/edit")

@app.post("/repairs/<int:i>/unpart/<int:rid>")
def repair_unpart(i, rid):
    z = q("select * from repair_parts where id=? and repair_id=? and user_id=?", (rid, i, uid()))
    if z and q("select 1 from repairs where id=? and user_id=?", (i, uid())):
        z = z[0]
        db().execute("update parts set qty=qty+1 where id=? and user_id=?", (z["part_id"], uid()))
        db().execute("delete from repair_parts where id=?", (rid,))
        db().execute("update repairs set cost=greatest(0, coalesce(cost,0)-?) where id=? and user_id=?", (z["cost"] or 0, i, uid())); db().commit()
        notify("القطعة رجعت للمخزون وانشالت من تكلفة الصيانة", "info", "تمت الإزالة")
    return redirect(f"/repairs/{i}/edit")

@app.post("/repairs/<int:i>/return")
def repair_return(i):
    """مرتجع قطعة مركّبة: بتروح لصفحة المرتجعات (منسوبة لمورّدها) وبتنشال من تكلفة الصيانة، ومعها بديلة اختيارية بتنخصم من المخزون."""
    r = q("select * from repairs where id=? and user_id=?", (i, uid()))
    if not r: return redirect("/repairs")
    r = r[0]; f = request.form
    z = q("select * from repair_parts where id=? and repair_id=? and user_id=?", (_i(f.get("rp_id")), i, uid()))
    if not z:
        notify("اختر القطعة المركّبة اللي بدك ترجعها", "warn", "تعذّر تسجيل المرتجع"); return _back_repairs()
    z = z[0]; nid = _i(f.get("new_part_id")) or None; newp = None
    if nid:
        newp = q("select * from parts where id=? and user_id=? and qty>0", (nid, uid()))
        if not newp:
            notify("القطعة البديلة غير متوفرة بالمخزون، وما تغيّر شي", "warn", "تعذّر تسجيل المرتجع"); return _back_repairs()
        newp = newp[0]
    p = q("select * from parts where id=? and user_id=?", (z["part_id"], uid())); p = p[0] if p else None
    cost = z["cost"] or 0; rd = today(); reason = (f.get("reason") or "").strip(); note = (f.get("note") or "").strip()
    full_note = " · ".join(x for x in (f"من صيانة #{i} ({r['customer']})", note) if x)
    sid, sn, label, cat = None, "", "قطعة محذوفة", ""
    if p:
        label, cat = plabel(p), p["category"]; sid = need_defaults(p)[1]
        sn = (q("select name from suppliers where id=? and user_id=?", (sid, uid())) or [{"name": ""}])[0]["name"] if sid else ""
    rid = db().execute("insert into returns_log(user_id,part_id,part_name,category,qty,unit_cost,total,supplier_id,supplier_name,reason,note,created,repair_id) values(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (uid(), z["part_id"], label, cat, 1, cost, round(cost, 2), sid, sn, reason, full_note, rd, i)).lastrowid
    db().execute("delete from repair_parts where id=?", (z["id"],))
    db().execute("update repairs set cost=greatest(0, coalesce(cost,0)-?) where id=? and user_id=?", (cost, i, uid()))
    if newp:
        db().execute("update parts set qty=qty-1 where id=? and user_id=?", (newp["id"], uid()))
        db().execute("insert into repair_parts(repair_id,part_id,cost,user_id) values(?,?,?,?)", (i, newp["id"], newp["cost"] or 0, uid()))
        db().execute("update repairs set cost=coalesce(cost,0)+? where id=? and user_id=?", (newp["cost"] or 0, i, uid()))
    db().commit()
    if p: add_return_need(uid(), p["id"], label, 1, cost, sid, " · ".join(x for x in (reason, full_note) if x), rid, rd)   # بينتسب لمورده وبيدخل فاتورته
    notify(f"{label} انسجلت بصفحة المرتجعات" + (f" وانتسبت للمورد {sn}" if sn else "") + (f"، وانخصمت بديلتها {plabel(newp)} من المخزون" if newp else ""), "ok", "تم تسجيل المرتجع")
    if newp: _low_stock_notify(newp["id"])
    return _back_repairs()

def month_rows(m):
    return q(f"select r.*, {EFF} eff, {PN} from repairs r where r.user_id=? and r.status={DELIV} and {EFF} like ? order by {EFF}",
             (uid(), m + "%"))

@app.route("/report")
def report():
    m = request.args.get("m") or today()[:7]; rows = month_rows(m); days = {}
    for r in rows:
        d = days.setdefault(r["eff"], [0, 0]); d[0] += 1; d[1] += r["price"] - r["cost"]
    top = q("select p.name, count(*) n from repair_parts rp join parts p on p.id=rp.part_id join repairs r on r.id=rp.repair_id "
            f"where r.user_id=? and r.status={DELIV} and {EFF} like ? group by p.id order by n desc limit 5", (uid(), m + "%"))
    return render_template("report", m=m, n=len(rows), rev=sum(r["price"] for r in rows), cost=sum(r["cost"] for r in rows),
                           days=sorted(days.items()), top=top)

@app.route("/export")
def export():
    m = request.args.get("m") or today()[:7]; out = io.StringIO(); w = csv.writer(out)
    w.writerow(["تاريخ التسليم", "الزبون", "الجهاز", "العطل", "القطع", "السعر", "التكلفة", "الربح"])
    for r in month_rows(m):
        w.writerow([r["eff"], r["customer"], r["device"], r["issue"], r["pn"] or "", r["price"], r["cost"], r["price"] - r["cost"]])
    return Response("\ufeff" + out.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename=report-{m}.csv"})

@app.post("/repairs/<int:i>/status")
def status(i):
    s = request.form["status"]
    ex("update repairs set status=?, done_date=? where id=? and user_id=?", (s, today() if s == ST[2] else None, i, uid()))
    notify(f"الصيانة #{i} صارت: {s}", "info" if s == ST[0] else "ok")
    return _back_repairs()


# ===================== الموظفين / الديون والشيكات / المرتجعات =====================
ICONS.update({"pk": _ic("M3 7l9-4 9 4v10l-9 4-9-4zM3 7l9 4 9-4M12 11v10"), "sl": _ic("M6 2L3 6v14a2 2 0 002 2h14a2 2 0 002-2V6l-3-4zM3 6h18M16 10a4 4 0 01-8 0"), "pl": _ic("M12 5v14M5 12h14"), "rt": _ic("M9 14L4 9l5-5M4 9h10a6 6 0 016 6v5"),
              "go": _ic("M5 12h14M12 5l7 7-7 7"), "us": _ic("M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2M9 11a4 4 0 100-8 4 4 0 000 8zM23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75"),
              "ck": _ic("M5 12.5l4.5 4.5L19 7.5"), "eye": _ic("M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12zM12 9a3 3 0 100 6 3 3 0 000-6z"),
              "bk": _ic("M15 18l-6-6 6-6")})
K_GIVE, K_BACK, K_USED = "تسليم", "إرجاع", "استهلاك"
K_SELL, K_RETP = "بيع", "مرتجع"   # بيع الموظف، ومرتجع الموظف لصاحب الشركة (بصورة/ملاحظة)
RET_REASONS = ["تالفة", "عيب مصنعي", "غير مطابقة للمواصفات", "طلب خاطئ / زيادة", "لا تعمل بعد التركيب", "أخرى"]
now_s = lambda: datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

def _f(v, d=0.0):
    try: return float(str(v).replace(",", ".").strip() or d)
    except ValueError: return d

def _i(v, d=0):
    try: return int(float(str(v).strip() or d))
    except ValueError: return d

def _pg(p, k):
    try: return p[k]
    except (KeyError, IndexError): return None
def plabel(p): return (p["name"] or "") + (" · " + _pg(p, "maker") if _pg(p, "maker") else "") + (" · " + p["color"] if p["color"] else "")

# ---------- الموظفون ----------
def emp_or_404(i):
    r = q("select * from employees where id=? and user_id=?", (i, uid()))
    if not r: abort(404)
    return dict(r[0])

def emp_holdings(eid=None, owner=None):
    ow = owner or uid()
    sql = ("select l.emp_id, l.part_id, max(l.part_name) pname, sum(case l.kind when 'تسليم' then l.qty else -l.qty end) held, "
           "coalesce((select sum(g.qty*g.emp_price)/sum(g.qty) from emp_stock_log g where g.emp_id=l.emp_id and g.part_id=l.part_id and g.kind='تسليم' and g.emp_price is not null), p.cost, 0) cost, coalesce(p.cost,0) ccost, coalesce(p.price,0) price, coalesce(p.qty,0) stock, coalesce(p.min_qty,2) min_qty from emp_stock_log l left join parts p on p.id=l.part_id "
           "where l.user_id=?" + (" and l.emp_id=?" if eid else "") + " group by l.emp_id, l.part_id, p.cost, p.price, p.qty, p.min_qty having sum(case l.kind when 'تسليم' then l.qty else -l.qty end)>0 order by pname")
    return [dict(r) for r in q(sql, (ow, eid) if eid else (ow,))]

def emp_held(eid, pid):
    return q("select coalesce(sum(case kind when 'تسليم' then qty else -qty end),0) n from emp_stock_log where user_id=? and emp_id=? and part_id=?", (uid(), eid, pid))[0]["n"]

# ---------- حساب الموظف مع الشركة + قائمة انتظار الزبائن ----------
def emp_avg(owner, emp_id, pid):
    """متوسط سعر الموظف (وتكلفة الشركة) للقطعة من تسليماته المسجّلة بنظام الحساب. بيرجع (None, None) إذا ما في."""
    r = q("select coalesce(sum(qty),0) n, coalesce(sum(qty*emp_price),0) a, coalesce(sum(qty*coalesce(co_cost,0)),0) c from emp_stock_log where user_id=? and emp_id=? and part_id=? and kind=? and emp_price is not null", (owner, emp_id, pid, K_GIVE))[0]
    if not r["n"]: return None, None
    return round(r["a"] / r["n"], 4), round(r["c"] / r["n"], 4)

def emp_account(owner, emp_id):
    """حساب الموظف مع الشركة: بضاعة مسلّمة بسعره (بعد المرتجع) - اللي دفعه = المتبقي عليه."""
    r = q("select coalesce(sum(case when kind=? then qty*emp_price end),0) g, coalesce(sum(case when kind in (?,?) then qty*emp_price end),0) r, "
          "coalesce(sum(case when kind=? then qty*(emp_price-coalesce(co_cost,0)) end),0) mg, coalesce(sum(case when kind in (?,?) then qty*(emp_price-coalesce(co_cost,0)) end),0) mr "
          "from emp_stock_log where user_id=? and emp_id=? and emp_price is not null", (K_GIVE, K_BACK, K_RETP, K_GIVE, K_BACK, K_RETP, owner, emp_id))[0]
    paid = q("select coalesce(sum(amount),0) t from emp_co_pay where user_id=? and emp_id=?", (owner, emp_id))[0]["t"] or 0
    goods = round(r["g"] - r["r"], 2)
    return {"goods": goods, "paid": round(paid, 2), "left": round(max(goods - paid, 0), 2), "over": round(max(paid - goods, 0), 2), "margin": round(r["mg"] - r["mr"], 2)}

def emp_queue_rows(ow, eid, status="waiting", limit=300):
    rows = [dict(r) for r in q("select w.*, (select phone from emp_customers c where c.id=w.customer_id) cphone, (select shop from emp_customers c where c.id=w.customer_id) cshop "
                               f"from emp_queue w where w.user_id=? and w.emp_id=? and w.status=? order by w.id {'asc' if status == 'waiting' else 'desc'} limit {int(limit)}", (ow, eid, status))]
    held = {h["part_id"]: h["held"] for h in emp_holdings(eid, ow)}
    for r in rows:
        r["held"] = held.get(r["part_id"], 0) if r["part_id"] else None
        r["ready"] = r["held"] is not None and r["held"] >= (r["qty"] or 1)
    return rows

# ---------- دفعات زبائن الموظفين ----------
def cust_accounts(owner, emp_id=None):
    """حساب كل زبون: مجموع مشترياته (المسجّلة بنظام الدفعات)، المدفوع، والمتبقي."""
    w = " and emp_id=?" if emp_id else ""
    par = [owner] + ([emp_id] if emp_id else [])
    sold = {r["customer_id"]: r["t"] for r in q("select customer_id, coalesce(sum(qty*unit_price),0) t from emp_stock_log where kind=? and pay_tracked=1 and customer_id is not null and user_id=?" + w + " group by customer_id", [K_SELL] + par)}
    paid = {r["customer_id"]: r["t"] for r in q("select customer_id, coalesce(sum(amount),0) t from emp_cust_pay where user_id=?" + w + " group by customer_id", par)}
    out = {}
    for cid in set(sold) | set(paid):
        t, p = round(sold.get(cid, 0) or 0, 2), round(paid.get(cid, 0) or 0, 2)
        out[cid] = {"trk": t, "paid": p, "left": round(max(t - p, 0), 2)}
    return out

ZERO_ACC = {"trk": 0, "paid": 0, "left": 0}

def sale_status(rows, owner):
    """بيضيف لكل عملية بيع: st (paid/part/unpaid/na) والمدفوع والمتبقي منها. دفعات الزبون بتتوزع على أقدم بيع أول."""
    cids = {r["customer_id"] for r in rows if r.get("customer_id")}
    alloc = {}
    if cids:
        ph = ",".join("?" * len(cids))
        allsales = q(f"select id, customer_id, qty*unit_price t from emp_stock_log where user_id=? and kind=? and pay_tracked=1 and customer_id in ({ph}) order by id", [owner, K_SELL, *cids])
        direct = {r["log_id"]: r["t"] for r in q(f"select log_id, coalesce(sum(amount),0) t from emp_cust_pay where user_id=? and log_id is not null and customer_id in ({ph}) group by log_id", [owner, *cids])}
        pool = {r["customer_id"]: r["t"] for r in q(f"select customer_id, coalesce(sum(amount),0) t from emp_cust_pay where user_id=? and log_id is null and customer_id in ({ph}) group by customer_id", [owner, *cids])}
        for sl in allsales: alloc[sl["id"]] = round(min(direct.get(sl["id"], 0) or 0, sl["t"] or 0), 2)
        for cid in cids:
            rem = pool.get(cid, 0) or 0
            for sl in allsales:
                if sl["customer_id"] != cid or rem <= 0: continue
                a = min(rem, (sl["t"] or 0) - alloc[sl["id"]]); a = max(a, 0); alloc[sl["id"]] = round(alloc[sl["id"]] + a, 2); rem -= a
    for r in rows:
        if not r.get("pay_tracked") or not r.get("customer_id"):
            r["st"], r["paid_part"], r["left"] = "na", 0, 0; continue
        t = r.get("total") or 0; a = alloc.get(r["id"], 0)
        r["paid_part"], r["left"] = a, round(max(t - a, 0), 2)
        r["st"] = "paid" if r["left"] <= 0.005 else ("part" if a > 0.005 else "unpaid")
    return rows

def _pay_back(b, d):
    return b if b and b.startswith("/") and not b.startswith("//") else d

def _do_cust_pay(ow, e, cid, f, by_owner, back):
    cu = q("select * from emp_customers where id=? and emp_id=? and user_id=?", (cid, e["id"], ow))
    if not cu: abort(404)
    cu = cu[0]; amt = round(_f(f.get("amount"), 0), 2); left = cust_accounts(ow, e["id"]).get(cid, ZERO_ACC)["left"]
    if amt <= 0: flash("مبلغ غير صحيح|اكتب المبلغ المدفوع.", "warn"); return redirect(back)
    if amt > left + 0.005: flash("المبلغ أكبر من المتبقي|المتبقي على " + cu["name"] + f" هو {left:g} ₪ فقط.", "warn"); return redirect(back)
    ex("insert into emp_cust_pay(user_id,emp_id,customer_id,amount,note,created,by_owner) values(?,?,?,?,?,?,?)", (ow, e["id"], cid, amt, (f.get("note") or "").strip(), now_s(), 1 if by_owner else 0))
    rest = round(max(left - amt, 0), 2)
    if not by_owner:
        _tell_owner(ow, f"💵 الموظف {e['name']} سجّل دفعة {amt:g} ₪ من الزبون {cu['name']} — المتبقي {rest:g} ₪", "ok")
    flash("تم تسجيل الدفعة|" + cu["name"] + f" دفع {amt:g} ₪ — " + ("المتبقي " + f"{rest:g} ₪" if rest > 0 else "سدّد كل اللي عليه ✓"), "ok")
    return redirect(back)

@app.route("/employees", methods=["GET", "POST"])
def employees():
    if request.method == "POST":
        f = request.form; nm = f.get("name", "").strip()
        if nm:
            ex("insert into employees(user_id,name,phone,role,notes,created) values(?,?,?,?,?,?)", (uid(), nm, f.get("phone", "").strip(), f.get("role", "").strip(), f.get("notes", "").strip(), today()))
            notify(f"تمت إضافة الموظف: {nm}", "ok")
        return redirect("/employees")
    emps = [dict(r, nq=0, cost=0.0, val=0.0, kinds=0) for r in q("select * from employees where user_id=? order by id", (uid(),))]
    by = {e["id"]: e for e in emps}; tot = {"n": len(emps), "nq": 0, "cost": 0.0, "val": 0.0}
    for h in emp_holdings():
        e = by.get(h["emp_id"])
        if e:
            e["nq"] += h["held"]; e["kinds"] += 1; e["cost"] += h["held"] * h["cost"]; e["val"] += h["held"] * h["price"]
            tot["nq"] += h["held"]; tot["cost"] += h["held"] * h["cost"]; tot["val"] += h["held"] * h["price"]
    sold = {r["emp_id"]: r["t"] for r in q("select emp_id, coalesce(sum(qty*unit_price),0) t from emp_stock_log where user_id=? and kind=? and pay_tracked=1 group by emp_id", (uid(), K_SELL))}
    paid = {r["emp_id"]: r["t"] for r in q("select emp_id, coalesce(sum(amount),0) t from emp_cust_pay where user_id=? group by emp_id", (uid(),))}
    for e in emps: e["owed"] = round(max((sold.get(e["id"], 0) or 0) - (paid.get(e["id"], 0) or 0), 0), 2)
    tot["owed"] = round(sum(e["owed"] for e in emps), 2)
    return render_template("emps", emps=emps, tot=tot, ttl=("الموظفين", "كل موظف له عهدة منفصلة، وكل ما تسلّمه له بينخصم من المخزون الرئيسي"))

@app.route("/employees/<int:i>")
def employee(i):
    e = emp_or_404(i); H = emp_holdings(i)
    tot = {"nq": sum(h["held"] for h in H), "cost": sum(h["held"] * h["cost"] for h in H), "val": sum(h["held"] * h["price"] for h in H)}
    log = [dict(r) for r in q("select * from emp_stock_log where user_id=? and emp_id=? order by id desc limit 200", (uid(), i))]
    given = q("select coalesce(sum(qty),0) n from emp_stock_log where user_id=? and emp_id=? and kind=?", (uid(), i, K_GIVE))[0]["n"]
    used = q("select coalesce(sum(qty),0) n from emp_stock_log where user_id=? and emp_id=? and kind=?", (uid(), i, K_USED))[0]["n"]
    parts_ok = [dict(r) for r in q("select * from parts where user_id=? and qty>0 order by category,name,color", (uid(),))]
    acc = emp_account(uid(), i)
    copays = [dict(r) for r in q("select * from emp_co_pay where user_id=? and emp_id=? order by id desc limit 50", (uid(), i))]
    invs = _emp_invs(uid(), i)
    ninv = len(invs)
    return render_template("emp", invs=invs, ninv=ninv, open_invs=bool(request.args.get("invs")), acc=acc, copays=copays, e=e, H=H, tot=tot, log=log, given=given, used=used, parts=parts_ok, plabel=plabel, ttl=("عهدة الموظف", "كل البضاعة اللي تسلّمها " + e["name"] + " وحركاته"))

AR_DAYS = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]

def _emp_invs(ow, i, limit=None):
    """فواتير التسليم، كل فاتورة لحالها ومعها بنودها."""
    invs = [dict(r) for r in q("select * from emp_invoices where user_id=? and emp_id=? order by id desc" + (f" limit {int(limit)}" if limit else ""), (ow, i))]
    if invs:
        ph = ",".join("?" * len(invs))
        items = {}
        for r in q(f"select * from emp_stock_log where user_id=? and emp_id=? and inv_id in ({ph}) order by id", [ow, i] + [v["id"] for v in invs]):
            items.setdefault(r["inv_id"], []).append(dict(r))
        for v in invs:
            v["lines"] = items.get(v["id"], []); v["nq"] = sum(x["qty"] for x in v["lines"])
            try: d = datetime.datetime.strptime((v["created"] or "")[:16], "%Y-%m-%d %H:%M"); v["day"] = AR_DAYS[d.weekday()]; v["date"] = d.strftime("%Y-%m-%d")
            except ValueError: v["day"] = ""; v["date"] = (v["created"] or "")[:10]
    return invs

def _inv_or_404(i, inv):
    r = q("select * from emp_invoices where id=? and user_id=? and emp_id=?", (inv, uid(), i))
    if not r: abort(404)
    return dict(r[0])

@app.post("/employees/<int:i>/invoice/<int:inv>/delete")
def emp_invoice_delete(i, inv):
    emp_or_404(i); _inv_or_404(i, inv); back = f"/employees/{i}?invs=1"
    rows = [dict(r) for r in q("select * from emp_stock_log where user_id=? and emp_id=? and inv_id=? and kind=?", (uid(), i, inv, K_GIVE))]
    need = {}
    for r in rows: need[r["part_id"]] = need.get(r["part_id"], 0) + r["qty"]
    for pid, n in need.items():
        if emp_held(i, pid) - n < 0:
            notify("جزء من بضاعة هالفاتورة انباع أو رجع أو انستهلك، احذف حركاته أول.", "warn", "ما بنقدر نحذف الفاتورة"); return redirect(back)
    for r in rows:
        if q("select 1 from parts where id=? and user_id=?", (r["part_id"], uid())): ex("update parts set qty=qty+? where id=? and user_id=?", (r["qty"], r["part_id"], uid()))
        ex("delete from emp_stock_log where id=? and user_id=?", (r["id"], uid()))
    ex("delete from emp_invoices where id=? and user_id=?", (inv, uid()))
    notify(f"EINV-{inv:04d} — رجعت القطع للمخزن", "info", "تم حذف الفاتورة"); return redirect(back)

@app.route("/employees/<int:i>/invoice/<int:inv>/edit", methods=["GET", "POST"])
def emp_invoice_edit(i, inv):
    e = emp_or_404(i); v = _inv_or_404(i, inv); back = f"/employees/{i}?invs=1"
    lines = [dict(r) for r in q("select * from emp_stock_log where user_id=? and emp_id=? and inv_id=? and kind=? order by id", (uid(), i, inv, K_GIVE))]
    if request.method == "POST":
        f = request.form; new, delta, errs = {}, {}, []
        for x in lines:
            nq = _i(f.get("q_%d" % x["id"]), x["qty"]); ne = round(_f(f.get("ep_%d" % x["id"]), x["emp_price"] or 0), 2)
            if nq < 1 or ne < 0: errs.append(f"{x['part_name']}: كمية أو سعر غير صحيح"); continue
            new[x["id"]] = (nq, ne); delta[x["part_id"]] = delta.get(x["part_id"], 0) + (nq - x["qty"])
        for pid, d in delta.items():
            if d > 0:
                pr = q("select qty from parts where id=? and user_id=?", (pid, uid()))
                if pr and pr[0]["qty"] < d: errs.append(f"المتوفر بالمخزن {pr[0]['qty']} فقط (طلبت زيادة {d})")
            elif d < 0 and emp_held(i, pid) + d < 0: errs.append("جزء من هالقطع انباع أو رجع، ما بنقدر ننقص الكمية")
        if errs: notify(" — ".join(errs), "warn", "ما انحفظ التعديل"); return redirect(request.path)
        for x in lines:
            nq, ne = new[x["id"]]
            ex("update emp_stock_log set qty=?, emp_price=?, note=? where id=? and user_id=?", (nq, ne, (f.get("note") or "").strip(), x["id"], uid()))
        for pid, d in delta.items():
            if d and q("select 1 from parts where id=? and user_id=?", (pid, uid())): ex("update parts set qty=qty-? where id=? and user_id=?", (d, pid, uid()))
        dt = _vdate(f.get("date"), (v["created"] or "")[:10]); created = dt + " " + ((v["created"] or "")[11:16] or "00:00")
        ex("update emp_stock_log set created=? where inv_id=? and user_id=? and kind=?", (created, inv, uid(), K_GIVE))
        ex("update emp_invoices set created=?, note=? where id=? and user_id=?", (created, (f.get("note") or "").strip(), inv, uid()))
        _fix_emp_inv(inv); notify(f"EINV-{inv:04d}", "ok", "تم تعديل الفاتورة"); return redirect(back)
    v["date"] = (v["created"] or "")[:10]
    return render_template("einvedit", e=e, v=v, lines=lines, ttl=("تعديل فاتورة", e["name"]))

@app.route("/employees/<int:i>/invoices")
def emp_invoices_all(i):
    e = emp_or_404(i); invs = _emp_invs(uid(), i)
    return render_template("empinvs", e=e, invs=invs, ttl=("فواتير التسليم", "كل فواتير " + e["name"] + " — كل فاتورة لحالها"))

@app.route("/employees/<int:i>/report")
def employee_report(i):
    e = emp_or_404(i); a = request.args; td = datetime.date.today(); iso = lambda d: d.isoformat()
    d1, d2 = _vdate(a.get("from")), _vdate(a.get("to"))
    where, par = "user_id=? and emp_id=? and kind=?", [uid(), i, K_SELL]
    if d1: where += " and substr(created,1,10)>=?"; par.append(d1)
    if d2: where += " and substr(created,1,10)<=?"; par.append(d2)
    sales = [dict(r) for r in q(f"select l.*, qty*unit_price total, qty*coalesce(cost,0) wtotal, qty*(coalesce(unit_price,0)-coalesce(cost,0)) profit, "
                                f"(select phone from emp_customers c where c.id=l.customer_id) cphone from emp_stock_log l where {where} order by id desc limit 300", par)]
    sm = q(f"select count(*) n, coalesce(sum(qty),0) pcs, coalesce(sum(qty*unit_price),0) tot, coalesce(sum(qty*coalesce(cost,0)),0) w, "
           f"coalesce(sum(qty*(coalesce(unit_price,0)-coalesce(cost,0))),0) pr from emp_stock_log where {where}", par)[0]
    H = emp_holdings(i)
    for h in H: h["low"] = h["held"] <= (h.get("min_qty") or 0); h["out"] = h["held"] <= 0
    low = [h for h in H if h["low"]]
    mine = {h["part_id"]: h["held"] for h in H}
    shop_parts = []
    for r in q("select * from parts where user_id=? order by category,name,color", (uid(),)):
        r = dict(r); r["label"] = plabel(r); r["qty"] = r["qty"] or 0; r["low"] = r["qty"] <= (r["min_qty"] if r["min_qty"] is not None else 2); r["mine"] = mine.get(r["id"], 0); shop_parts.append(r)
    custs = [dict(r) for r in q("select c.*, (select count(*) from emp_stock_log l where l.customer_id=c.id and l.kind=?) ns, (select coalesce(sum(l.qty*l.unit_price),0) from emp_stock_log l where l.customer_id=c.id and l.kind=?) tot "
                                "from emp_customers c where c.emp_id=? and c.user_id=? order by lower(c.name)", (K_SELL, K_SELL, i, uid()))]
    sale_status(sales, uid())
    queue = emp_queue_rows(uid(), i)
    acc = cust_accounts(uid(), i)
    for c in custs: c.update(acc.get(c["id"], ZERO_ACC))
    owed = round(sum(a["left"] for a in acc.values()), 2); got = round(sum(a["paid"] for a in acc.values()), 2)
    pays = [dict(r) for r in q("select p.*, (select name from emp_customers c where c.id=p.customer_id) cname from emp_cust_pay p where p.user_id=? and p.emp_id=? order by p.id desc limit 50", (uid(), i))]
    notes = [dict(r) for r in q("select * from notifications where user_id=? and msg like ? order by id desc limit 30", (uid(), f"%الموظف {e['name']}%"))]
    quick = [("اليوم", iso(td), iso(td)), ("آخر 7 أيام", iso(td - datetime.timedelta(days=6)), iso(td)), ("هذا الشهر", iso(td.replace(day=1)), iso(td))]
    return render_template("empreport", queue=queue, owed=owed, got=got, pays=pays, e=e, sales=sales, sm=sm, H=H, low=low, shop_parts=shop_parts, custs=custs, notes=notes, d1=d1 or "", d2=d2 or "", quick=quick,
                           ttl=("لوحة الموظف", "مبيعات " + e["name"] + " وصافي ربحه ومخزونه وزبائنه"))

@app.route("/notifications/poll")
def notifications_poll():
    after = _i(request.args.get("after"))
    rows = [dict(r) for r in q("select id,msg,kind,created from notifications where user_id=? and id>? order by id desc limit 10", (uid(), after))]
    mx = q("select coalesce(max(id),0) m from notifications where user_id=?", (uid(),))[0]["m"]
    return {"unread": q("select count(*) n from notifications where user_id=? and seen=0", (uid(),))[0]["n"], "max": mx, "new": rows}

@app.post("/employees/<int:i>/customers/<int:c>/pay")
def emp_cust_pay_owner(i, c):
    e = emp_or_404(i)
    return _do_cust_pay(uid(), e, c, request.form, True, _pay_back(request.form.get("back"), f"/employees/{i}/report"))

@app.post("/employees/<int:i>/pay/<int:p>/delete")
def emp_pay_delete(i, p):
    emp_or_404(i); ex("delete from emp_cust_pay where id=? and emp_id=? and user_id=?", (p, i, uid()))
    flash("تم حذف الدفعة|", "ok"); return redirect(f"/employees/{i}/report")

@app.post("/employees/<int:i>/copay")
def emp_copay(i):
    e = emp_or_404(i); f = request.form; back = f"/employees/{i}"; amt = round(_f(f.get("amount"), 0), 2); left = emp_account(uid(), i)["left"]
    if amt <= 0: notify("اكتب المبلغ المدفوع", "warn"); return redirect(back)
    if amt > left + 0.005: notify(f"المتبقي على الموظف {left:g} ₪ فقط", "warn", "المبلغ أكبر من المتبقي"); return redirect(back)
    bank = f.get("pm") == "بنك"; fl = request.files.get("receipt"); rc = save_receipt(fl)
    if fl and fl.filename and not rc: notify("الوصل لازم يكون صورة (JPG/PNG/WEBP) أو PDF وأقل من 8MB", "warn", "الوصل غير صالح"); return redirect(back)
    if bank and not rc: notify("الدفعة البنكية لازم يرفق معها صورة الوصل", "warn", "الوصل مطلوب"); return redirect(back)
    ex("insert into emp_co_pay(user_id,emp_id,amount,note,created,method,receipt) values(?,?,?,?,?,?,?)", (uid(), i, amt, (f.get("note") or "").strip(), now_s(), "بنك" if bank else "نقد", rc))
    rest = round(max(left - amt, 0), 2)
    notify(f"{e['name']} دفع {amt:g} ₪ ({'تحويل بنكي' if bank else 'نقداً'}) — " + (f"المتبقي عليه {rest:g} ₪" if rest > 0 else "سدّد كل حسابه ✓"), "ok", "تم تسجيل الدفعة"); return redirect(back)

@app.post("/my/pay")
def emp_copay_me():
    """الموظف بيرحّل دفعة للشركة (نقد أو بنك). بتنسجّل مباشرة بحسابه وبيوصل إشعار لصاحب الشركة."""
    e = emp_or_404_any(session["emp"]); ow = e["user_id"]; f = request.form; back = "/my"
    amt = round(_f(f.get("amount"), 0), 2); left = emp_account(ow, e["id"])["left"]
    if amt <= 0: flash("مبلغ غير صحيح|اكتب المبلغ اللي بدك ترحّله.", "warn"); return redirect(back)
    if amt > left + 0.005: flash("المبلغ أكبر من المتبقي|المتبقي عليك " + f"{left:g} ₪ فقط.", "warn"); return redirect(back)
    bank = f.get("pm") == "بنك"; fl = request.files.get("receipt"); rc = save_receipt(fl)
    if fl and fl.filename and not rc: flash("الوصل غير صالح|لازم يكون صورة (JPG/PNG/WEBP) أو PDF وأقل من 8MB.", "warn"); return redirect(back)
    if bank and not rc: flash("الوصل مطلوب|الدفعة البنكية لازم يرفق معها صورة الوصل.", "warn"); return redirect(back)
    ex("insert into emp_co_pay(user_id,emp_id,amount,note,created,method,receipt,by_emp) values(?,?,?,?,?,?,?,?)", (ow, e["id"], amt, (f.get("note") or "").strip(), now_s(), "بنك" if bank else "نقد", rc, 1))
    rest = round(max(left - amt, 0), 2)
    _tell_owner(ow, f"💳 الموظف {e['name']} رحّل دفعة {amt:g} ₪ ({'تحويل بنكي' if bank else 'نقداً'}) — " + (f"المتبقي عليه {rest:g} ₪" if rest > 0 else "سدّد كل حسابه ✓"), "ok")
    flash("تم ترحيل الدفعة|" + f"{amt:g} ₪ ({'تحويل بنكي' if bank else 'نقداً'}) — " + (f"المتبقي عليك {rest:g} ₪" if rest > 0 else "سدّدت كل حسابك ✓"), "ok")
    return redirect(back)

@app.post("/employees/<int:i>/copay/<int:p>/delete")
def emp_copay_delete(i, p):
    emp_or_404(i)
    for _r in q("select receipt from emp_co_pay where id=? and emp_id=? and user_id=?", (p, i, uid())): del_file(_r["receipt"])
    ex("delete from emp_co_pay where id=? and emp_id=? and user_id=?", (p, i, uid())); notify("تم حذف الدفعة", "info"); return redirect(f"/employees/{i}")

@app.post("/employees/<int:i>/edit")
def emp_edit(i):
    emp_or_404(i); f = request.form
    if f.get("name", "").strip():
        ex("update employees set name=?, phone=?, role=?, notes=? where id=? and user_id=?", (f["name"].strip(), f.get("phone", "").strip(), f.get("role", "").strip(), f.get("notes", "").strip(), i, uid()))
        notify("تم حفظ بيانات الموظف", "ok")
    return redirect(f"/employees/{i}")

@app.post("/employees/<int:i>/delete")
def emp_delete(i):
    e = emp_or_404(i)
    if emp_holdings(i):
        notify("لسا في بضاعة بعهدة الموظف. رجّعها للمخزن (أو سجّلها استهلاك) أول، وبعدين احذفه.", "warn", "ما بنقدر نحذف الموظف")
        return redirect(f"/employees/{i}")
    ex("delete from emp_stock_log where emp_id=? and user_id=?", (i, uid())); ex("delete from employees where id=? and user_id=?", (i, uid()))
    notify(e["name"], "warn", "تم حذف الموظف"); return redirect("/employees")

@app.post("/employees/<int:i>/give")
def emp_give(i):
    e = emp_or_404(i); f = request.form; back = f"/employees/{i}"; note = f.get("note", "").strip()
    items, errs = [], []
    for pid in dict.fromkeys(f.getlist("pick")):
        qty = _i(f.get("q_" + pid)); p = q("select * from parts where id=? and user_id=?", (_i(pid), uid()))
        if not p: continue
        p = p[0]
        if qty < 1: errs.append(f"{plabel(p)}: كمية غير صحيحة")
        elif qty > p["qty"]: errs.append(f"{plabel(p)}: المتوفر {p['qty']} فقط")
        else:
            ep = _f(f.get("ep_" + pid), -1)
            if ep < 0: ep = p["emp_price"] if p["emp_price"] is not None else (p["cost"] or 0)
            items.append((p, qty, round(ep, 2)))
    if errs: notify(" — ".join(errs), "warn", "ما تم تسليم شي"); return redirect(back)
    if not items: notify("اختر قطعة واحدة على الأقل", "warn"); return redirect(back)
    inv = db().execute("insert into emp_invoices(user_id,emp_id,created,total,note) values(?,?,?,?,?)", (uid(), i, now_s(), round(sum(qty * ep for _p, qty, ep in items), 2), note)).lastrowid
    db().commit()
    for p, qty, ep in items:
        ex("update parts set qty=qty-?, emp_price=? where id=? and user_id=?", (qty, ep, p["id"], uid()))
        ex("insert into emp_stock_log(user_id,emp_id,part_id,part_name,kind,qty,note,created,emp_price,co_cost,inv_id) values(?,?,?,?,?,?,?,?,?,?,?)", (uid(), i, p["id"], plabel(p), K_GIVE, qty, note, now_s(), ep, p["cost"] or 0, inv))
    notify(f"{len(items)} قطعة ← {e['name']} (" + "، ".join(f"{qty} × {plabel(p)}" for p, qty, _ep in items[:4]) + ("..." if len(items) > 4 else "") + f") — على حسابه {sum(qty * ep for _p, qty, ep in items):g} ₪", "ok", "تم تسليم البضاعة")
    return redirect(f"/employees/{i}/invoice/{inv}")

def _fix_emp_inv(inv_id, u=None):
    """بعد إلغاء حركة تسليم: بنصحّح مجموع فاتورة الموظف أو بنحذفها إذا فضيت."""
    u = u or uid()
    if not inv_id: return
    rows = q("select qty, emp_price from emp_stock_log where inv_id=? and user_id=?", (inv_id, u))
    if not rows: ex("delete from emp_invoices where id=? and user_id=?", (inv_id, u))
    else: ex("update emp_invoices set total=? where id=? and user_id=?", (round(sum(r["qty"] * (r["emp_price"] or 0) for r in rows), 2), inv_id, u))

def _emp_lines(ow, eid, rows):
    """بنود فاتورة/كشف الموظف: التسليم بسعر الموظف، والإرجاع بالسالب (بمتوسط سعره إذا ما انسجّل سعر)."""
    avg = {}
    for r in q("select part_id, sum(qty) n, sum(qty*coalesce(emp_price,0)) a from emp_stock_log where user_id=? and emp_id=? and kind=? group by part_id", (ow, eid, K_GIVE)):
        avg[r["part_id"]] = (r["a"] / r["n"]) if r["n"] else 0
    raw = []
    for r in rows:
        back = r["kind"] != K_GIVE
        up = r["emp_price"] if r["emp_price"] is not None else avg.get(r["part_id"], 0)
        up = up or 0
        raw.append({"name": r["part_name"] or "", "kind": "مرتجع" if back else "تسليم", "qty": r["qty"], "cost": round(up, 2), "total": round(r["qty"] * up, 2), "date": (r["created"] or "")[:16]})
    return _doc_lines(raw)

def _emp_doc_ctx(ow, e, rows, title, ref, now, base, back):
    s_ = q("select * from settings where user_id=?", (ow,)); st = dict(s_[0]) if s_ else {}
    st["shop_name"] = st.get("shop_name") or ""; st["address"] = st.get("address") or ""
    lines, buy, ret = _emp_lines(ow, e["id"], rows)
    return dict(doc_title=title, ref=ref, party=e["name"], phone=e.get("phone") or "", lines=lines, net=round(buy - ret, 2), qty=sum(l["qty"] * (-1 if l["kind"] == "مرتجع" else 1) for l in lines),
                buy_total=buy, ret_total=ret, stk=[], with_stock=False, can_stock=False, st=st, now=now, th_url=base + "?fmt=th", a4_url=base, back=back,
                party_label="الموظف", party_card="بيانات الموظف", net_label="الإجمالي على حساب الموظف", lbl_buy="البضاعة المسلّمة", lbl_buy_full="البضاعة المسلّمة", lbl_ret="المُرجَع للمخزن",
                empty_msg="لا توجد بضاعة مسلّمة", note_msg="يرجى مطابقة القطع والكميات عند الاستلام، وأي ملاحظة تُبلَّغ فوراً لصاحب الشركة.", sigs=True)

def _emp_render(ctx): return render_template("thermal" if request.args.get("fmt") == "th" else "a4doc", **ctx)

def _emp_inv_view(ow, e, inv, base, back):
    r = q("select * from emp_invoices where id=? and user_id=? and emp_id=?", (inv, ow, e["id"]))
    if not r: abort(404)
    rows = q("select * from emp_stock_log where user_id=? and emp_id=? and inv_id=? order by id", (ow, e["id"], inv))
    return _emp_render(_emp_doc_ctx(ow, e, rows, "فاتورة تسليم بضاعة لموظف", "EINV-%04d" % inv, r[0]["created"], base, back))

def _emp_stmt_view(ow, e, base, back):
    rows = q("select * from emp_stock_log where user_id=? and emp_id=? and kind in (?,?,?) order by id", (ow, e["id"], K_GIVE, K_BACK, K_RETP))
    return _emp_render(_emp_doc_ctx(ow, e, rows, "كشف البضاعة المسلّمة للموظف", "", now_s(), base, back))

@app.route("/employees/<int:i>/invoice/<int:inv>")
def emp_invoice(i, inv):
    e = emp_or_404(i); return _emp_inv_view(uid(), e, inv, f"/employees/{i}/invoice/{inv}", f"/employees/{i}?invs=1")

@app.route("/employees/<int:i>/statement")
def emp_statement(i):
    e = emp_or_404(i); return _emp_stmt_view(uid(), e, f"/employees/{i}/statement", f"/employees/{i}")

@app.route("/my/statement")
def emp_my_statement():
    if not session.get("emp"): return redirect("/")
    e = emp_or_404_any(session["emp"]); return _emp_stmt_view(e["user_id"], e, "/my/statement", "/my")

@app.post("/employees/<int:i>/move")
def emp_move(i):
    e = emp_or_404(i); f = request.form
    kind, qty, pid, note = f.get("kind"), _i(f.get("qty")), _i(f.get("part_id")), f.get("note", "").strip()
    back = f"/employees/{i}"
    if kind not in (K_GIVE, K_BACK, K_USED) or qty < 1: notify("اكتب كمية صحيحة (1 أو أكثر)", "warn"); return redirect(back)
    p = q("select * from parts where id=? and user_id=?", (pid, uid())); p = p[0] if p else None
    if kind == K_GIVE:
        if not p: notify("اختر القطعة", "warn"); return redirect(back)
        if qty > p["qty"]: notify(f"المتوفر بالمخزن الرئيسي {p['qty']} فقط", "warn", "الكمية غير كافية"); return redirect(back)
        ex("update parts set qty=qty-? where id=? and user_id=?", (qty, pid, uid())); pname = plabel(p)
        msg = f"{qty} × {pname} ← {e['name']}"
    else:
        held = emp_held(i, pid)
        if qty > held: notify(f"بعهدة الموظف {held} فقط من هالقطعة", "warn", "الكمية غير صحيحة"); return redirect(back)
        pname = plabel(p) if p else (q("select max(part_name) n from emp_stock_log where emp_id=? and part_id=? and user_id=?", (i, pid, uid()))[0]["n"] or "")
        if kind == K_BACK:
            if not p: notify("القطعة انحذفت من المخزن، سجّلها استهلاك بدل الإرجاع", "warn"); return redirect(back)
            ex("update parts set qty=qty+? where id=? and user_id=?", (qty, pid, uid()))
        msg = f"{qty} × {pname} ← " + ("رجعت للمخزن من " if kind == K_BACK else "استهلاك/بيع من ") + e["name"]
    ep = co = None
    if kind == K_GIVE and p:
        ep = _f(f.get("price"), -1); ep = round(ep if ep >= 0 else (p["emp_price"] if p["emp_price"] is not None else (p["cost"] or 0)), 2); co = p["cost"] or 0
    elif kind == K_BACK: ep, co = emp_avg(uid(), i, pid)
    ex("insert into emp_stock_log(user_id,emp_id,part_id,part_name,kind,qty,note,created,emp_price,co_cost) values(?,?,?,?,?,?,?,?,?,?)", (uid(), i, pid, pname, kind, qty, note, now_s(), ep, co))
    notify(msg, "ok", {K_GIVE: "تم تسليم البضاعة", K_BACK: "تم الإرجاع للمخزن", K_USED: "تم تسجيل الاستهلاك"}[kind])
    return redirect(back)

@app.post("/employees/log/<int:lid>/delete")
def emp_log_delete(lid):
    r = q("select * from emp_stock_log where id=? and user_id=?", (lid, uid()))
    if not r: abort(404)
    r = dict(r[0]); back = f"/employees/{r['emp_id']}"; p = q("select 1 from parts where id=? and user_id=?", (r["part_id"], uid()))
    if r["kind"] == K_GIVE:
        if emp_held(r["emp_id"], r["part_id"]) - r["qty"] < 0: notify("جزء من هالكمية رجع أو انستهلك، احذف سجلاتها أول.", "warn", "ما بنقدر نلغي التسليم"); return redirect(back)
        if p: ex("update parts set qty=qty+? where id=? and user_id=?", (r["qty"], r["part_id"], uid()))
    elif r["kind"] == K_BACK:
        pr = q("select qty from parts where id=? and user_id=?", (r["part_id"], uid()))
        if not pr or pr[0]["qty"] < r["qty"]: notify("الكمية الحالية بالمخزن أقل من اللي رجعت، ما بنقدر نلغي الإرجاع.", "warn"); return redirect(back)
        ex("update parts set qty=qty-? where id=? and user_id=?", (r["qty"], r["part_id"], uid()))
    for ph in q("select photo from returns_log where emp_log_id=? and user_id=?", (lid, uid())):
        if ph["photo"]:
            del_file(ph["photo"])
    _drop_ret_needs([x["id"] for x in q("select id from returns_log where emp_log_id=? and user_id=?", (lid, uid()))])
    ex("delete from returns_log where emp_log_id=? and user_id=?", (lid, uid()))
    ex("delete from emp_stock_log where id=? and user_id=?", (lid, uid())); _fix_emp_inv(r.get("inv_id")); notify("تم إلغاء السجل وتعديل المخزون", "info"); return redirect(back)


@app.post("/employees/<int:i>/login")
def emp_login_set(i):
    e = emp_or_404(i); f = request.form; lg = f.get("login", "").strip().lower(); pw = f.get("password", "")
    back = f"/employees/{i}"
    if not lg or " " in lg or len(lg) < 3: notify("اسم الدخول لازم يكون 3 أحرف على الأقل وبدون مسافات", "warn"); return redirect(back)
    if q("select 1 from employees where lower(login)=? and id<>?", (lg, i)) or q("select 1 from users where lower(email)=?", (lg,)):
        notify("اسم الدخول هذا مستخدم، اختر اسم ثاني", "warn"); return redirect(back)
    if pw:
        if len(pw) < 6: notify("كلمة السر 6 أحرف على الأقل", "warn"); return redirect(back)
        ex("update employees set login=?, pw=?, must_change=1 where id=? and user_id=?", (lg, generate_password_hash(pw), i, uid()))
    elif e.get("pw"): ex("update employees set login=? where id=? and user_id=?", (lg, i, uid()))
    else: notify("اكتب كلمة سر للموظف", "warn"); return redirect(back)
    notify(f"{e['name']} بيدخل باسم: {lg}", "ok", "تم تفعيل دخول الموظف"); return redirect(back)

@app.post("/employees/<int:i>/login/off")
def emp_login_off(i):
    e = emp_or_404(i); ex("update employees set login=null, pw=null, must_change=0 where id=? and user_id=?", (i, uid()))
    notify(e["name"], "warn", "تم إيقاف دخول الموظف"); return redirect(f"/employees/{i}")

@app.route("/my")
def emp_home():
    e = emp_or_404_any(session["emp"]); ow = e["user_id"]; H = emp_holdings(e["id"], ow)
    tot = {"nq": sum(h["held"] for h in H), "val": sum(h["held"] * h["price"] for h in H)}
    log = [dict(r) for r in q("select * from emp_stock_log where user_id=? and emp_id=? order by id desc limit 100", (ow, e["id"]))]
    shop = (q("select shop_name from settings where user_id=?", (ow,)) or [{"shop_name": ""}])[0]["shop_name"] or ""
    sales = q("select coalesce(sum(qty*unit_price),0) n from emp_stock_log where user_id=? and emp_id=? and kind=?", (ow, e["id"], K_SELL))[0]["n"]
    mine = {h["part_id"]: h["held"] for h in H}   # للموظف: بس "موجود / غير موجود" بالشركة، بدون كميات أو أسعار
    avail = [{"name": plabel(p), "cat": p["category"], "ok": (p["qty"] or 0) > 0, "qty": p["qty"] or 0, "mine": mine.get(p["id"], 0)}
             for p in q("select * from parts where user_id=? order by category,name,color", (ow,))]
    for h in H: h["low"] = h["held"] <= (h.get("min_qty") or 0)
    custs = [dict(r) for r in q("select * from emp_customers where emp_id=? and user_id=? order by lower(name)", (e["id"], ow))]
    net = q("select coalesce(sum(qty*(coalesce(unit_price,0)-coalesce(cost,0))),0) n from emp_stock_log where user_id=? and emp_id=? and kind=?", (ow, e["id"], K_SELL))[0]["n"]
    owed = round(sum(a["left"] for a in cust_accounts(ow, e["id"]).values()), 2)
    qall = emp_queue_rows(ow, e["id"])
    mypays = [dict(r) for r in q("select * from emp_co_pay where user_id=? and emp_id=? order by id desc limit 30", (ow, e["id"]))]
    return render_template("empme", mypays=mypays, open_pay=bool(request.args.get("pay")), acc=emp_account(ow, e["id"]), qtop=qall[:5], qn=len(qall), owed=owed, e=e, H=H, tot=tot, log=log, shop=shop, reasons=RET_REASONS, sales=sales, avail=avail, custs=custs, custs_json=json.dumps([{k: c.get(k) or '' for k in ('id','name','shop','phone','location')} for c in custs], ensure_ascii=False).replace('<', '\\u003c'), net=net,
                           nlow=sum(1 for h in H if h["low"]))

@app.route("/my/settings")
def emp_settings():
    e = emp_or_404_any(session["emp"])
    return render_template("empset", e=e, shop=_emp_shop(e), pw_err=None, pw_ok=bool(request.args.get("ok")), forced=bool(e.get("must_change")))

@app.post("/my/settings/password")
def emp_password():
    e = emp_or_404_any(session["emp"]); f = request.form
    old, n1, n2 = f.get("old", ""), f.get("new", ""), f.get("new2", "")
    err = None
    if not check_password_hash(e["pw"], old): err = "كلمة السر الحالية غلط"
    elif len(n1) < 6: err = "كلمة السر الجديدة لازم تكون 6 أحرف على الأقل"
    elif n1 != n2: err = "تأكيد كلمة السر ما بيطابق"
    elif n1 == old: err = "اختر كلمة سر مختلفة عن الحالية"
    if err: return render_template("empset", e=e, shop=_emp_shop(e), pw_err=err, pw_ok=False, forced=bool(e.get("must_change")))
    ex("update employees set pw=?, must_change=0 where id=?", (generate_password_hash(n1), e["id"]))
    flash("تم تغيير كلمة السر|سجّل دخولك فيها المرة الجاية.", "ok")
    return redirect("/my")

def _held_of(ow, eid, pid):
    return q("select coalesce(sum(case kind when 'تسليم' then qty else -qty end),0) n from emp_stock_log where user_id=? and emp_id=? and part_id=?", (ow, eid, pid))[0]["n"]

def _tell_owner(ow, msg, kind="info"):
    ex("insert into notifications(user_id,msg,kind,created) values(?,?,?,?)", (ow, msg, kind, now_s()))

def _vdate(v, default=None):
    try: return datetime.date.fromisoformat((v or "").strip()).isoformat()
    except ValueError: return default

SALE_SORTS = {"date_desc": ("الأحدث أولاً", "id desc"), "date_asc": ("الأقدم أولاً", "id asc"), "total_desc": ("الأعلى مبلغاً", "qty*unit_price desc"),
              "total_asc": ("الأقل مبلغاً", "qty*unit_price asc"), "qty_desc": ("الأكثر كمية", "qty desc"), "name": ("اسم القطعة (أ-ي)", "lower(part_name) asc")}

@app.route("/my/sales")
def emp_sales():
    e = emp_or_404_any(session["emp"]); a = request.args; td = datetime.date.today()
    d1, d2 = _vdate(a.get("from")), _vdate(a.get("to")); qs = a.get("q", "").strip(); sort = a.get("sort") if a.get("sort") in SALE_SORTS else "date_desc"
    where, par = "user_id=? and emp_id=? and kind=?", [e["user_id"], e["id"], K_SELL]
    if d1: where += " and substr(created,1,10)>=?"; par.append(d1)
    if d2: where += " and substr(created,1,10)<=?"; par.append(d2)
    if qs: where += " and part_name like ?"; par.append(f"%{qs}%")
    cid = _i(a.get("cust"))
    if cid: where += " and customer_id=?"; par.append(cid)
    rows = [dict(r) for r in q(f"select l.*, qty*unit_price total, qty*coalesce(cost,0) wtotal, qty*(coalesce(unit_price,0)-coalesce(cost,0)) profit, "
                               f"(select phone from emp_customers c where c.id=l.customer_id) cphone, (select location from emp_customers c where c.id=l.customer_id) cloc "
                               f"from emp_stock_log l where {where} order by {SALE_SORTS[sort][1]}", par)]
    custs = [dict(r) for r in q("select id,name from emp_customers where emp_id=? and user_id=? order by lower(name)", (e["id"], e["user_id"]))]
    sale_status(rows, e["user_id"])
    iso = lambda d: d.isoformat()
    quick = [("اليوم", iso(td), iso(td)), ("أمس", iso(td - datetime.timedelta(days=1)), iso(td - datetime.timedelta(days=1))),
             ("آخر 7 أيام", iso(td - datetime.timedelta(days=6)), iso(td)), ("هذا الشهر", iso(td.replace(day=1)), iso(td))]
    return render_template("empsales", e=e, shop=_emp_shop(e), rows=rows, d1=d1 or "", d2=d2 or "", qs=qs, sort=sort, sorts=SALE_SORTS, quick=quick, forced=False,
                           n=len(rows), pcs=sum(r["qty"] for r in rows), tot=sum(r["total"] or 0 for r in rows), filtered=bool(d1 or d2 or qs or cid),
                           wtot=sum(r["wtotal"] or 0 for r in rows), profit=sum(r["profit"] or 0 for r in rows), custs=custs, cid=cid)

@app.post("/my/sell")
def emp_sell():
    e = emp_or_404_any(session["emp"]); ow = e["user_id"]; f = request.form
    pid, qty, price = _i(f.get("part_id")), _i(f.get("qty")), _f(f.get("price"), -1)
    p = q("select * from parts where id=? and user_id=?", (pid, ow)); p = p[0] if p else None
    held = _held_of(ow, e["id"], pid)
    if qty < 1 or price < 0: flash("بيانات ناقصة|اكتب كمية صحيحة وسعر البيع.", "warn"); return redirect("/my")
    if qty > held: flash(f"الكمية غير صحيحة|بعهدتك {held} فقط من هالقطعة.", "warn"); return redirect("/my")
    cu = q("select * from emp_customers where id=? and emp_id=? and user_id=?", (_i(f.get("customer_id")), e["id"], ow))
    if not cu: flash("اختر الزبون|كل قطعة لازم تنسجّل باسم الزبون اللي أخدها. أضفه من صفحة \"زبائني\" أول.", "warn"); return redirect("/my")
    cu = cu[0]
    pname = plabel(p) if p else (q("select max(part_name) n from emp_stock_log where emp_id=? and part_id=? and user_id=?", (e["id"], pid, ow))[0]["n"] or "")
    _ea, _ = emp_avg(ow, e["id"], pid)
    cost = _ea if _ea is not None else ((p["cost"] or 0) if p else 0); tot = round(qty * price, 2); profit = round(qty * (price - cost), 2)
    paid = tot if not str(f.get("paid", "")).strip() else round(_f(f.get("paid"), 0), 2)
    if paid < 0 or paid > tot + 0.005: flash("المدفوع غير صحيح|المبلغ المدفوع لازم يكون بين 0 و " + f"{tot:g} ₪.", "warn"); return redirect("/my")
    left_s = round(max(tot - paid, 0), 2)
    note = f"بسعر {price:g} ₪ للقطعة · المجموع {tot:g} ₪" + (f" · {f.get('note').strip()}" if f.get("note", "").strip() else "")
    ex("insert into emp_stock_log(user_id,emp_id,part_id,part_name,kind,qty,note,created,unit_price,cost,customer_id,customer_name,pay_tracked) values(?,?,?,?,?,?,?,?,?,?,?,?,1)",
       (ow, e["id"], pid, pname, K_SELL, qty, note, now_s(), price, cost, cu["id"], cu["name"]))
    if paid > 0:
        lid = q("select max(id) m from emp_stock_log where user_id=? and emp_id=? and kind=?", (ow, e["id"], K_SELL))[0]["m"]
        ex("insert into emp_cust_pay(user_id,emp_id,customer_id,amount,note,created,by_owner,log_id) values(?,?,?,?,?,?,0,?)", (ow, e["id"], cu["id"], paid, "دفعة عند البيع", now_s(), lid))
    _tell_owner(ow, f"🛒 بيع من الموظف {e['name']}: {qty} × {pname} للزبون {cu['name']}" + (f" ({cu['phone']})" if cu["phone"] else "") +
                f" — المجموع {tot:g} ₪، مدفوع {paid:g} ₪" + (f"، متبقي عليه {left_s:g} ₪" if left_s > 0 else " (مدفوع كامل)") + f"، صافي الربح {profit:g} ₪", "ok")
    left = held - qty; mn = (p["min_qty"] if p and p["min_qty"] is not None else 2)
    if left <= 0: _tell_owner(ow, f"⛔ نفدت من عهدة {e['name']}: {pname}", "warn")
    elif left <= mn: _tell_owner(ow, f"⚠️ مخزون منخفض عند {e['name']}: {pname} — باقي {left} فقط", "warn")
    flash(f"تم تسجيل البيع|{qty} × {pname} للزبون {cu['name']} — المجموع {tot:g} ₪ · " + (f"مدفوع {paid:g} ₪ والمتبقي {left_s:g} ₪" if left_s > 0 else "مدفوع كامل ✓"), "ok"); return redirect("/my")

# ---------- زبائن الموظف ----------
def _cust_form(f):
    return (f.get("name", "").strip(), f.get("shop", "").strip(), f.get("location", "").strip(), f.get("phone", "").strip())

@app.route("/my/customers")
def emp_customers():
    e = emp_or_404_any(session["emp"]); ow = e["user_id"]; qs = request.args.get("q", "").strip()
    sql, par = "select c.*, (select count(*) from emp_stock_log l where l.customer_id=c.id and l.kind=?) ns, (select coalesce(sum(l.qty*l.unit_price),0) from emp_stock_log l where l.customer_id=c.id and l.kind=?) tot from emp_customers c where c.emp_id=? and c.user_id=?", [K_SELL, K_SELL, e["id"], ow]
    if qs: sql += " and (c.name like ? or c.shop like ? or c.phone like ? or c.location like ?)"; par += [f"%{qs}%"] * 4
    rows = [dict(r) for r in q(sql + " order by lower(c.name)", par)]
    acc = cust_accounts(ow, e["id"])
    for r in rows: r.update(acc.get(r["id"], ZERO_ACC))
    return render_template("empcust", e=e, shop=_emp_shop(e), rows=rows, qs=qs, forced=False, back=request.args.get("back", ""))

@app.post("/my/customers/add")
def emp_customer_add():
    e = emp_or_404_any(session["emp"]); nm, sh, lo, ph = _cust_form(request.form)
    if not nm or not ph: flash("بيانات ناقصة|اسم الزبون ورقم الهاتف مطلوبين.", "warn"); return redirect("/my/customers")
    ex("insert into emp_customers(user_id,emp_id,name,shop,location,phone,created) values(?,?,?,?,?,?,?)", (e["user_id"], e["id"], nm, sh, lo, ph, today()))
    _tell_owner(e["user_id"], f"👤 الموظف {e['name']} أضاف زبون جديد: {nm}" + (f" ({sh})" if sh else "") + f" — {ph}", "info")
    flash("تمت إضافة الزبون|" + nm, "ok")
    return redirect("/my" if request.form.get("back") == "home" else "/my/customers")

@app.post("/my/customers/<int:i>/pay")
def emp_cust_pay(i):
    e = emp_or_404_any(session["emp"])
    return _do_cust_pay(e["user_id"], e, i, request.form, False, _pay_back(request.form.get("back"), "/my/customers"))

@app.route("/my/queue")
def emp_queue():
    e = emp_or_404_any(session["emp"]); ow = e["user_id"]; st = "done" if request.args.get("s") == "done" else "waiting"
    rows = emp_queue_rows(ow, e["id"], st)
    nwait = q("select count(*) n from emp_queue where user_id=? and emp_id=? and status='waiting'", (ow, e["id"]))[0]["n"]
    custs = [dict(r) for r in q("select id,name,shop from emp_customers where emp_id=? and user_id=? order by lower(name)", (e["id"], ow))]
    held = {h["part_id"]: h["held"] for h in emp_holdings(e["id"], ow)}
    parts = [{"id": p["id"], "label": plabel(p), "held": held.get(p["id"], 0)} for p in q("select * from parts where user_id=? order by category,name,color", (ow,))]
    return render_template("empq", e=e, shop=_emp_shop(e), forced=False, rows=rows, s=st, nwait=nwait, custs=custs, parts=parts)

@app.post("/my/queue/add")
def emp_queue_add():
    e = emp_or_404_any(session["emp"]); ow = e["user_id"]; f = request.form
    cid = _i(f.get("customer_id")); cu = q("select * from emp_customers where id=? and emp_id=? and user_id=?", (cid, e["id"], ow)) if cid else None
    cname = cu[0]["name"] if cu else f.get("customer_name", "").strip(); cid = cu[0]["id"] if cu else None
    pid = _i(f.get("part_id")); p = q("select * from parts where id=? and user_id=?", (pid, ow)) if pid else None; p = p[0] if p else None
    item = ((plabel(p) if p else "") + (" · " if p and f.get("item", "").strip() else "") + f.get("item", "").strip()).strip()
    if not cname: flash("اكتب اسم الزبون|اختر زبون من القائمة أو اكتب اسمه.", "warn"); return redirect("/my/queue")
    if not item: flash("اكتب المطلوب|اختر قطعة أو اكتب شو الزبون بده.", "warn"); return redirect("/my/queue")
    ex("insert into emp_queue(user_id,emp_id,customer_id,customer_name,part_id,item,qty,note,status,created) values(?,?,?,?,?,?,?,?,'waiting',?)",
       (ow, e["id"], cid, cname, p["id"] if p else None, item, max(_i(f.get("qty"), 1), 1), f.get("note", "").strip(), now_s()))
    flash("انضاف لقائمة الانتظار|" + cname + " — " + item, "ok"); return redirect("/my/queue")

@app.post("/my/queue/<int:i>/<act>")
def emp_queue_act(i, act):
    e = emp_or_404_any(session["emp"])
    if act not in ("done", "undo", "delete"): abort(404)
    if not q("select 1 from emp_queue where id=? and emp_id=? and user_id=?", (i, e["id"], e["user_id"])): abort(404)
    if act == "delete": ex("delete from emp_queue where id=? and emp_id=?", (i, e["id"])); flash("انحذف من القائمة|", "ok"); return redirect(request.referrer or "/my/queue")
    ex("update emp_queue set status=?, done_at=? where id=? and emp_id=?", ("done" if act == "done" else "waiting", now_s() if act == "done" else None, i, e["id"]))
    flash("تم ✓|" if act == "done" else "رجع للانتظار|", "ok"); return redirect(request.referrer or "/my/queue")

@app.post("/my/customers/<int:i>/edit")
def emp_customer_edit(i):
    e = emp_or_404_any(session["emp"]); nm, sh, lo, ph = _cust_form(request.form)
    if not nm or not ph: flash("بيانات ناقصة|اسم الزبون ورقم الهاتف مطلوبين.", "warn"); return redirect("/my/customers")
    ex("update emp_customers set name=?, shop=?, location=?, phone=? where id=? and emp_id=? and user_id=?", (nm, sh, lo, ph, i, e["id"], e["user_id"]))
    ex("update emp_stock_log set customer_name=? where customer_id=? and emp_id=?", (nm, i, e["id"]))
    flash("تم حفظ التعديل|" + nm, "ok"); return redirect("/my/customers")

@app.post("/my/customers/<int:i>/delete")
def emp_customer_del(i):
    e = emp_or_404_any(session["emp"])
    if q("select 1 from emp_stock_log where customer_id=? and emp_id=? and kind=? limit 1", (i, e["id"], K_SELL)):
        flash("ما بنقدر نحذفه|هذا الزبون عليه مبيعات مسجّلة. عدّل بياناته بدل الحذف.", "warn"); return redirect("/my/customers")
    ex("delete from emp_customers where id=? and emp_id=? and user_id=?", (i, e["id"], e["user_id"])); flash("تم حذف الزبون|", "ok"); return redirect("/my/customers")

@app.template_filter("maplink")
def _maplink(loc):
    loc = (loc or "").strip()
    if not loc: return ""
    return loc if loc.lower().startswith(("http://", "https://")) else "https://www.google.com/maps/search/?api=1&query=" + urllib.parse.quote(loc)

@app.post("/my/return")
def emp_return():
    e = emp_or_404_any(session["emp"]); ow = e["user_id"]; f = request.form
    pid, qty = _i(f.get("part_id")), _i(f.get("qty")); note = f.get("note", "").strip(); reason = f.get("reason", "") if f.get("reason") in RET_REASONS else "أخرى"
    ph = save_photo(request.files.get("photo"))
    if qty < 1: flash("كمية غير صحيحة|اكتب كمية 1 أو أكثر.", "warn"); return redirect("/my")
    if not ph and not note: flash("أرفق صورة أو اكتب ملاحظة|لازم توضّح مشكلة القطعة المرتجعة.", "warn"); return redirect("/my")
    held = _held_of(ow, e["id"], pid)
    if qty > held: flash(f"الكمية غير صحيحة|بعهدتك {held} فقط من هالقطعة.", "warn"); return redirect("/my")
    p = q("select * from parts where id=? and user_id=?", (pid, ow)); p = p[0] if p else None
    pname = plabel(p) if p else (q("select max(part_name) n from emp_stock_log where emp_id=? and part_id=? and user_id=?", (e["id"], pid, ow))[0]["n"] or "")
    cost = (p["cost"] or 0) if p else 0; sid = p["supplier_id"] if p else None
    if p: dc, ds = need_defaults(p, ow); cost = cost or dc; sid = sid if _sup_ok(sid, ow) else ds
    sn = (q("select name from suppliers where id=? and user_id=?", (sid, ow)) or [{"name": ""}])[0]["name"] if sid else ""
    _ep, _co = emp_avg(ow, e["id"], pid)
    c = db().execute("insert into emp_stock_log(user_id,emp_id,part_id,part_name,kind,qty,note,created,cost,emp_price,co_cost) values(?,?,?,?,?,?,?,?,?,?,?)",
                     (ow, e["id"], pid, pname, K_RETP, qty, ("مرتجع: " + reason + (" · " + note if note else "")), now_s(), cost, _ep, _co)); db().commit()
    rid = db().execute("insert into returns_log(user_id,part_id,part_name,category,qty,unit_cost,total,supplier_id,supplier_name,reason,note,created,emp_id,emp_name,photo,emp_log_id) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (ow, pid, pname, (p["category"] if p else "أخرى"), qty, cost, round(qty * cost, 2), sid, sn, reason, note, today(), e["id"], e["name"], ph, c.lastrowid)).lastrowid; db().commit()
    add_return_need(ow, pid, pname, qty, cost, sid, " · ".join(x for x in (reason, note) if x), rid, today())   # بينتسب لمورد القطعة وبيدخل فاتورته
    _tell_owner(ow, f"مرتجع جديد من الموظف {e['name']}: {qty} × {pname} ({reason})" + (" مع صورة" if ph else ""), "warn")
    flash(f"وصل المرتجع لصاحب الشركة|{qty} × {pname}", "ok"); return redirect("/my")

@app.route("/rphoto/<name>")
def rphoto(name):
    if session.get("emp") and not uid(): ok = q("select 1 from returns_log where photo=? and emp_id=?", (name, session["emp"]))
    else: ok = q("select 1 from returns_log where photo=? and user_id=?", (name, uid()))
    if not ok: abort(404)
    return send_from_directory(UP, name)

def _emp_shop(e):
    return (q("select shop_name from settings where user_id=?", (e["user_id"],)) or [{"shop_name": ""}])[0]["shop_name"] or ""

def emp_or_404_any(i):
    r = q("select * from employees where id=?", (i,))
    if not r: abort(404)
    return dict(r[0])

# ---------- الديون والشيكات ----------
def debtor_or_404(i):
    r = q("select * from debtors where id=? and user_id=?", (i, uid()))
    if not r: abort(404)
    return dict(r[0])

CH_WAIT, CH_OK, CH_BAD = "لم يُصرف", "صُرف", "راجع"

def person_figs(debts, cheqs):
    """debts: سجلات debt_entries لشخص، cheqs: شيكاته. الشيك المصروف (المحسوب على الدين) بينقص من الدين."""
    d = {"debt": 0.0, "cash": 0.0, "chk_ok": 0.0, "chk_wait": 0.0, "chk_bad": 0.0, "overdue": 0, "n_chk": len(cheqs), "last": ""}
    for r in debts:
        a = r["amount"] or 0
        if r["kind"] == "دين": d["debt"] += a
        else: d["cash"] += a
        d["last"] = max(d["last"], r["created"] or "")
    for c in cheqs:
        a = c["amount"] or 0
        if not c["on_debt"]: continue
        if c["status"] == CH_OK: d["chk_ok"] += a
        elif c["status"] == CH_BAD: d["chk_bad"] += a
        else:
            d["chk_wait"] += a
            if c["due"] and c["due"] < today(): d["overdue"] += 1
    d["paid"] = d["cash"] + d["chk_ok"]; d["rem"] = d["debt"] - d["paid"]; d["after"] = d["rem"] - d["chk_wait"]
    d["pct"] = min(100, round(100 * d["paid"] / d["debt"])) if d["debt"] > 0 else 0
    return {k: (round(v, 2) if isinstance(v, float) else v) for k, v in d.items()}

def people_rows():
    ents, chs = {}, {}
    for r in q("select * from debt_entries where user_id=?", (uid(),)): ents.setdefault(r["debtor_id"], []).append(dict(r))
    for r in q("select * from cheques where user_id=?", (uid(),)): chs.setdefault(r["person_id"], []).append(dict(r))
    rows = []
    for dr in q("select * from debtors where user_id=? order by lower(name)", (uid(),)):
        fg = person_figs(ents.get(dr["id"], []), chs.get(dr["id"], []))
        cl = chs.get(dr["id"], [])
        fg.update(n_wait=sum(1 for c in cl if c["status"] == CH_WAIT), n_bad=sum(1 for c in cl if c["status"] == CH_BAD), n_ok=sum(1 for c in cl if c["status"] == CH_OK),
                  n_debt=sum(1 for r in ents.get(dr["id"], []) if r["kind"] == "دين"))
        rows.append(dict(dr, **fg))
    return rows

def _safe_back(default):
    b = request.form.get("back") or ""
    return b if b.startswith("/") and not b.startswith("//") else default

def person_by_name(name, phone=""):
    nm = (name or "").strip()
    if not nm: return None
    r = q("select id from debtors where user_id=? and lower(name)=?", (uid(), nm.lower()))
    if r: return r[0]["id"]
    c = db().execute("insert into debtors(user_id,name,phone,note,created) values(?,?,?,?,?)", (uid(), nm, phone.strip(), "", today())); db().commit()
    return c.lastrowid

def _pid_from_form(f):
    pid = _i(f.get("person_id"))
    if pid and q("select 1 from debtors where id=? and user_id=?", (pid, uid())): return pid
    return person_by_name(f.get("person_name"), f.get("phone", ""))

def add_debt_entry(did, kind, amt, f, item=""):
    ex("insert into debt_entries(user_id,debtor_id,kind,amount,method,check_no,bank,due,status,note,created,item) values(?,?,?,?,?,?,?,?,?,?,?,?)",
       (uid(), did, kind, amt, "نقد" if kind == "دفعة" else "", "", "", "", "", f.get("note", "").strip(), f.get("date") or today(), item))

# ---------- الأشخاص (يجمع أصحاب الديون وأصحاب الشيكات) ----------
@app.route("/people", methods=["GET", "POST"])
def people():
    if request.method == "POST":
        f = request.form; nm = f.get("name", "").strip()
        if nm:
            if q("select 1 from debtors where user_id=? and lower(name)=?", (uid(), nm.lower())): notify("هذا الاسم موجود، افتحه من القائمة.", "warn", "الشخص موجود")
            else:
                did = db().execute("insert into debtors(user_id,name,phone,note,created) values(?,?,?,?,?)", (uid(), nm, f.get("phone", "").strip(), f.get("note", "").strip(), today())).lastrowid; db().commit()
                notify(nm, "ok", "تمت إضافة الشخص"); return redirect(f"/people/{did}")
        return redirect("/people")
    rows = people_rows()
    T_ = {"n": len(rows), "debtors": sum(1 for r in rows if r["rem"] > 0), "rem": sum(r["rem"] for r in rows if r["rem"] > 0), "wait": sum(r["chk_wait"] for r in rows)}
    return render_template("people", rows=rows, T=T_, ttl=("الأشخاص", "كل أصحاب الديون والشيكات بمكان واحد — اضغط على الاسم لتفاصيله"))

@app.route("/people/<int:i>")
def person_page(i):
    d = debtor_or_404(i)
    ents = [dict(r) for r in q("select * from debt_entries where user_id=? and debtor_id=? order by created desc, id desc", (uid(), i))]
    chs = [dict(r) for r in q("select * from cheques where user_id=? and person_id=? order by coalesce(nullif(due,''),created) desc, id desc", (uid(), i))]
    F = person_figs(ents, chs)
    return render_template("person", d=d, debts=[r for r in ents if r["kind"] == "دين"], pays=[r for r in ents if r["kind"] == "دفعة"], chs=chs, F=F, today=today(),
                           ttl=("حساب " + d["name"], "الديون والدفعات والشيكات الخاصة بهذا الشخص"))

@app.post("/people/<int:i>/edit")
def person_edit(i):
    debtor_or_404(i); f = request.form
    if f.get("name", "").strip():
        ex("update debtors set name=?, phone=?, note=? where id=? and user_id=?", (f["name"].strip(), f.get("phone", "").strip(), f.get("note", "").strip(), i, uid())); notify("تم حفظ البيانات", "ok")
    return redirect(f"/people/{i}")

@app.post("/people/<int:i>/delete")
def person_delete(i):
    d = debtor_or_404(i)
    for c in q("select photo from cheques where person_id=? and user_id=? and photo is not null", (i, uid())):
        del_file(c["photo"])
    ex("delete from debt_entries where debtor_id=? and user_id=?", (i, uid())); ex("delete from cheques where person_id=? and user_id=?", (i, uid())); ex("delete from debtors where id=? and user_id=?", (i, uid()))
    notify(d["name"], "warn", "تم حذف الشخص وكل سجلاته"); return redirect("/people")

# ---------- الديون ----------
@app.route("/debts")
def debts():
    rows = [r for r in people_rows() if r["debt"] > 0 or r["cash"] > 0]
    rows.sort(key=lambda r: -r["rem"])
    T_ = {"debt": sum(r["debt"] for r in rows), "paid": sum(r["paid"] for r in rows), "rem": sum(r["rem"] for r in rows if r["rem"] > 0), "n": sum(1 for r in rows if r["rem"] > 0)}
    recent = [dict(r) for r in q("select e.*, d.name pname from debt_entries e join debtors d on d.id=e.debtor_id where e.user_id=? order by e.created desc, e.id desc limit 60", (uid(),))]
    names = [r["name"] for r in people_rows()]
    return render_template("debts", rows=rows, T=T_, recent=recent, names=names, today=today(), ttl=("الديون", "شو أخذ كل شخص، كم دفع منو نقداً، وكم باقي عليه"))

@app.post("/debts/entry")
def debt_entry():
    f = request.form; kind = "دفعة" if f.get("kind") == "دفعة" else "دين"; amt = _f(f.get("amount"))
    did = _pid_from_form(f)
    if not did: notify("اكتب اسم الشخص", "warn"); return redirect(_safe_back("/debts"))
    d = debtor_or_404(did)
    if kind == "دين":
        if amt <= 0 or not f.get("item", "").strip(): notify("اكتب شو أخذ ومبلغ أكبر من صفر", "warn"); return redirect(_safe_back("/debts"))
        add_debt_entry(did, "دين", amt, f, f.get("item", "").strip())
        paid = _f(f.get("paid"))
        if paid > 0: add_debt_entry(did, "دفعة", paid, dict(f, note="دفعة عند الاستلام"))
        notify(f"{d['name']}: {f.get('item', '').strip()} — {amt:g} ₪" + (f"، دفع منها {paid:g} ₪" if paid > 0 else ""), "ok", "تم تسجيل الدين")
    else:
        if amt <= 0: notify("اكتب مبلغ أكبر من صفر", "warn"); return redirect(_safe_back("/debts"))
        add_debt_entry(did, "دفعة", amt, f); notify(f"{amt:g} ₪ — {d['name']}", "ok", "تم تسجيل الدفعة")
    return redirect(_safe_back(f"/people/{did}"))

@app.post("/debts/entry/<int:eid>/delete")
def debt_entry_del(eid):
    r = q("select debtor_id from debt_entries where id=? and user_id=?", (eid, uid()))
    if not r: abort(404)
    ex("delete from debt_entries where id=? and user_id=?", (eid, uid())); notify("تم حذف السجل", "info"); return redirect(_safe_back(f"/people/{r[0]['debtor_id']}"))

@app.route("/debts/<int:i>")
def debt_page_old(i): return redirect(f"/people/{i}")

# ---------- الشيكات ----------
@app.route("/cheques")
def cheques():
    a = request.args; st = a.get("status") if a.get("status") in (CH_WAIT, CH_OK, CH_BAD) else ""; qs = a.get("q", "").strip(); d1, d2 = _vdate(a.get("from")), _vdate(a.get("to"))
    where, par = "c.user_id=?", [uid()]
    if st: where += " and c.status=?"; par.append(st)
    if d1: where += " and c.due>=?"; par.append(d1)
    if d2: where += " and c.due<=?"; par.append(d2)
    if qs: where += " and (c.number like ? or c.bank like ? or c.drawer like ? or d.name like ? or c.note like ?)"; par += [f"%{qs}%"] * 5
    rows = [dict(r) for r in q(f"select c.*, d.name pname from cheques c left join debtors d on d.id=c.person_id where {where} order by case c.status when ? then 0 when ? then 1 else 2 end, coalesce(nullif(c.due,''),'9999'), c.id desc", par + [CH_WAIT, CH_BAD])]
    allc = [dict(r) for r in q("select * from cheques where user_id=?", (uid(),))]
    td = today(); sm = {"wait": 0.0, "n_wait": 0, "late": 0, "today": 0, "ok": 0.0, "n_ok": 0, "bad": 0.0, "n_bad": 0}
    for c in allc:
        am = c["amount"] or 0
        if c["status"] == CH_WAIT:
            sm["wait"] += am; sm["n_wait"] += 1
            if c["due"] and c["due"] < td: sm["late"] += 1
            elif c["due"] == td: sm["today"] += 1
        elif c["status"] == CH_OK: sm["ok"] += am; sm["n_ok"] += 1
        else: sm["bad"] += am; sm["n_bad"] += 1
    return render_template("cheques", rows=rows, sm=sm, names=[r["name"] for r in q("select name from debtors where user_id=? order by lower(name)", (uid(),))],
                           st=st, qs=qs, d1=d1 or "", d2=d2 or "", today=td, ttl=("الشيكات", "صاحب الشيك، تاريخه، صورته، وهل انصرف أو لا"))

@app.post("/cheques/add")
def cheque_add():
    f = request.form; amt = _f(f.get("amount")); did = _pid_from_form(f)
    if not did or amt <= 0 or not f.get("number", "").strip():
        notify("لازم: اسم الشخص، رقم الشيك، ومبلغ أكبر من صفر", "warn"); return redirect(_safe_back("/cheques"))
    d = debtor_or_404(did); ph = save_photo(request.files.get("photo"))
    status = f.get("status") if f.get("status") in (CH_WAIT, CH_OK, CH_BAD) else CH_WAIT
    ex("insert into cheques(user_id,person_id,number,bank,amount,drawer,due,status,photo,note,on_debt,created,cashed_date) values(?,?,?,?,?,?,?,?,?,?,?,?,?)",
       (uid(), did, f["number"].strip(), f.get("bank", "").strip(), amt, f.get("drawer", "").strip() or d["name"], _vdate(f.get("due"), ""), status, ph,
        f.get("note", "").strip(), 1 if f.get("on_debt") else 0, today(), today() if status == CH_OK else None))
    cash = _f(f.get("cash"))
    if cash > 0 and f.get("on_debt"): add_debt_entry(did, "دفعة", cash, dict(f, note=f"نقد مع الشيك رقم {f['number'].strip()}", date=today()))
    notify(f"شيك {amt:g} ₪ — {d['name']}" + (f" + نقد {cash:g} ₪" if cash > 0 and f.get("on_debt") else ""), "ok", "تم تسجيل الشيك")
    return redirect(_safe_back(f"/people/{did}" if f.get("from_person") else "/cheques"))

def chq_or_404(i):
    r = q("select * from cheques where id=? and user_id=?", (i, uid()))
    if not r: abort(404)
    return dict(r[0])

@app.post("/cheques/<int:i>/status")
def cheque_status(i):
    c = chq_or_404(i); st = request.form.get("status")
    if st in (CH_WAIT, CH_OK, CH_BAD):
        ex("update cheques set status=?, cashed_date=? where id=? and user_id=?", (st, today() if st == CH_OK else None, i, uid()))
        notify({CH_OK: "انصرف الشيك" + (" وانحسب من دين الشخص" if c["on_debt"] else ""), CH_BAD: "الشيك رجع ولم ينحسب من المدفوع", CH_WAIT: "رجع الشيك لحالة: لم يُصرف"}[st], "ok" if st == CH_OK else "info", f"شيك رقم {c['number']}")
    return redirect(_safe_back("/cheques"))

@app.post("/cheques/<int:i>/edit")
def cheque_edit(i):
    c = chq_or_404(i); f = request.form; amt = _f(f.get("amount"))
    if amt <= 0 or not f.get("number", "").strip(): notify("رقم الشيك والمبلغ مطلوبين", "warn"); return redirect(_safe_back("/cheques"))
    ph = save_photo(request.files.get("photo")) or c["photo"]
    if ph != c["photo"] and c["photo"]:
        del_file(c["photo"])
    ex("update cheques set number=?, bank=?, amount=?, drawer=?, due=?, note=?, on_debt=?, photo=? where id=? and user_id=?",
       (f["number"].strip(), f.get("bank", "").strip(), amt, f.get("drawer", "").strip(), _vdate(f.get("due"), ""), f.get("note", "").strip(), 1 if f.get("on_debt") else 0, ph, i, uid()))
    notify(f"شيك رقم {f['number'].strip()}", "ok", "تم حفظ التعديل"); return redirect(_safe_back("/cheques"))

@app.post("/cheques/<int:i>/delete")
def cheque_delete(i):
    c = chq_or_404(i)
    if c["photo"]:
        del_file(c["photo"])
    ex("delete from cheques where id=? and user_id=?", (i, uid())); notify(f"شيك رقم {c['number']}", "info", "تم حذف الشيك"); return redirect(_safe_back("/cheques"))

@app.route("/chkphoto/<name>")
def chkphoto(name):
    if not q("select 1 from cheques where photo=? and user_id=?", (name, uid())): abort(404)
    return send_from_directory(UP, name)

# ---------- البضاعة المرتجعة ----------
@app.route("/returns", methods=["GET", "POST"])
def returns():
    if request.method == "POST":
        f = request.form; pid, qty = _i(f.get("part_id")), _i(f.get("qty"))
        p = q("select * from parts where id=? and user_id=?", (pid, uid()))
        if not p or qty < 1: notify("اختر القطعة واكتب كمية صحيحة", "warn"); return redirect("/returns")
        p = p[0]
        if qty > p["qty"]: notify(f"المتوفر بالمخزن الرئيسي {p['qty']} فقط", "warn", "الكمية غير كافية"); return redirect("/returns")
        dc, ds = need_defaults(p); cost = _f(f.get("unit_cost"), dc); sid = _sup_ok(_i(f.get("supplier_id")) or None) or ds   # السعر والمورد تلقائياً من القطعة
        sn = (q("select name from suppliers where id=? and user_id=?", (sid, uid())) or [{"name": ""}])[0]["name"] if sid else ""
        ex("update parts set qty=qty-? where id=? and user_id=?", (qty, pid, uid()))
        rd = _vdate(f.get("date"), today())
        rid = db().execute("insert into returns_log(user_id,part_id,part_name,category,qty,unit_cost,total,supplier_id,supplier_name,reason,note,created) values(?,?,?,?,?,?,?,?,?,?,?,?)",
                           (uid(), pid, plabel(p), p["category"], qty, cost, round(qty * cost, 2), sid, sn, f.get("reason", ""), f.get("note", "").strip(), rd)).lastrowid
        add_return_need(uid(), pid, plabel(p), qty, cost, sid, " · ".join(x for x in (f.get("reason", ""), f.get("note", "").strip()) if x), rid, rd)   # بينتسب لمورده وبيدخل فاتورته
        notify(f"{qty} × {plabel(p)} — انخصمت من المخزن الرئيسي" + (f" وانتسبت للمورد {sn}" if sn else " (بدون مورد — حدّده من المتطلبات)"), "ok", "تم تسجيل المرتجع"); return redirect("/returns")
    rows = [dict(r) for r in q("select r.*, n.invoice_id ninv, n.id nid from returns_log r left join needs n on n.ret_id=r.id where r.user_id=? order by r.created desc, r.id desc", (uid(),))]
    mo = today()[:7]; st = {"n": len(rows), "qty": sum(r["qty"] for r in rows), "val": sum(r["total"] or 0 for r in rows), "mqty": sum(r["qty"] for r in rows if (r["created"] or "")[:7] == mo),
                            "open": sum(1 for r in rows if r["nid"] and not r["ninv"])}
    parts_ok = []
    for r in q("select * from parts where user_id=? and qty>0 order by category,name,color", (uid(),)):
        d = dict(r); d["cost"], d["supplier_id"] = need_defaults(r); parts_ok.append(d)
    return render_template("rets", rows=rows, st=st, parts=parts_ok, sup=q("select * from suppliers where user_id=? order by name", (uid(),)), reasons=RET_REASONS, today=today(), plabel=plabel,
                           ttl=("البضاعة المرتجعة", "كل قطعة بترجّعها بتنخصم تلقائياً من المخزن الرئيسي"))

@app.post("/returns/<int:i>/delete")
def ret_delete(i):
    r = q("select * from returns_log where id=? and user_id=?", (i, uid()))
    if not r: abort(404)
    r = r[0]; _drop_ret_needs([i])
    if r["repair_id"]:   # مرتجع من صيانة: القطعة كانت مركّبة أصلاً فما في كمية ترجع للمخزن
        ex("delete from returns_log where id=? and user_id=?", (i, uid())); notify("تم حذف سجل المرتجع (ما تغيّر شي بالمخزون ولا بتكلفة الصيانة)", "info"); return redirect("/returns")
    if r["emp_log_id"]:
        if r["photo"]:
            del_file(r["photo"])
        ex("delete from emp_stock_log where id=? and user_id=?", (r["emp_log_id"], uid())); ex("delete from returns_log where id=? and user_id=?", (i, uid()))
        notify("تم حذف المرتجع ورجعت القطعة لعهدة الموظف", "info"); return redirect("/returns")
    if q("select 1 from parts where id=? and user_id=?", (r["part_id"], uid())):
        ex("update parts set qty=qty+? where id=? and user_id=?", (r["qty"], r["part_id"], uid())); extra = " ورجعت الكمية للمخزن الرئيسي"
    else: extra = " (القطعة محذوفة من المخزن فما انرجعت كميتها)"
    ex("delete from returns_log where id=? and user_id=?", (i, uid())); notify("تم حذف سجل المرتجع" + extra, "info"); return redirect("/returns")


T["paydlg"] = """<dialog class=dlg id=dlg-cpay><form method=post id=cpay-f action=/my/customers/0/pay><div class=dh><h3>تسجيل دفعة من <span id=cp_name></span></h3><button type=button class=cl data-close aria-label="إغلاق">×</button></div>
<div class=db><p style="margin:0 0 10px">المتبقي على الزبون: <b id=cp_left></b> ₪</p>
<div class=fg><label>المبلغ المدفوع (₪)<input name=amount id=cp_amt type=number step=any min=0.01 required inputmode=decimal></label><label>ملاحظة (اختياري)<input name=note placeholder="مثلاً: نقداً، حوالة، شيك"></label></div></div>
<div class=df><button>حفظ الدفعة</button><button type=button class=ghost data-close>إلغاء</button></div></form></dialog>
<script>document.addEventListener('click',function(e){var b=e.target.closest('.paybtn');if(!b)return;var f=document.getElementById('cpay-f');f.action=b.dataset.act;document.getElementById('cp_name').textContent=b.dataset.name;document.getElementById('cp_left').textContent=b.dataset.left;var a=document.getElementById('cp_amt');a.value=b.dataset.left;a.max=b.dataset.left;document.getElementById('dlg-cpay').showModal()});</script>"""



T["emps"] = """{% extends 'base' %}{% block c %}
<div class="sg4"><div class=sc><span class="si a">{{ic.us}}</span><div><small>عدد الموظفين</small><b>{{tot.n}}</b></div></div>
<div class=sc><span class="si b">{{cic['أخرى']}}</span><div><small>قطع بعهدة الموظفين</small><b>{{tot.nq}}</b></div></div>
<div class=sc><span class="si e">₪</span><div><small>قيمة العهد (جملة)</small><b>{{ '%g'|format(tot.cost) }} ₪</b></div></div>
<div class=sc><span class="si c">₪</span><div><small>قيمة البيع المتوقعة</small><b>{{ '%g'|format(tot.val) }} ₪</b></div></div>
<div class=sc><span class="si d">₪</span><div><small>متبقي عند زبائن الموظفين</small><b>{{ '%g'|format(tot.owed) }} ₪</b></div></div></div>
<div class=tools><div class=r1><span class=lb>اختر موظف لتسليمه بضاعة أو لمتابعة عهدته</span><span class=sp></span><button type=button data-open=dlg-emp>{{ic.pl}} إضافة موظف</button></div></div>
<dialog class=dlg id=dlg-emp><form method=post><div class=dh><h3>إضافة موظف</h3><button type=button class=cl data-close aria-label="إغلاق">×</button></div>
<div class=db><div class=fg><label>الاسم<input name=name required></label><label>الهاتف<input name=phone inputmode=tel></label><label class=fa>الوظيفة / المهمة<input name=role placeholder="مثلاً: فني صيانة، مندوب مبيعات"></label><label class=fa>ملاحظات<input name=notes></label></div></div>
<div class=df><button>حفظ الموظف</button><button type=button class=ghost data-close>إلغاء</button></div></form></dialog>
<div class=eg>{% for e in emps %}<a class=ec href=/employees/{{e.id}} style="--h:{{(e.id*67)%360}}"><div class=ech><div class=av>{{e.name[:1]}}</div><div class=en><b>{{e.name}}</b><small>{{e.role or 'موظف'}}{% if e.phone %} · {{e.phone}}{% endif %}</small></div></div>
<div class=ec3><div><small>قطع بعهدته</small><b>{{e.nq}}</b></div><div><small>أصناف</small><b>{{e.kinds}}</b></div><div><small>قيمة البيع</small><b>{{ '%g'|format(e.val) }} ₪</b></div></div>
{% if e.owed %}<div style="padding:6px 16px;color:#b45309;font-weight:700;font-size:13px">💰 متبقي عند زبائنه: {{ '%g'|format(e.owed) }} ₪</div>{% endif %}<div class=ecf>فتح صفحة الموظف {{ic.go}}</div></a>
{% else %}<div class="card em" style="grid-column:1/-1">ما في موظفين بعد. اضغط "إضافة موظف" وابدأ بتسليمه بضاعة من المخزن.</div>{% endfor %}</div>{% endblock %}"""

T["einvlist"] = """{% macro ico(p) %}<svg viewBox="0 0 24 24" width=18 height=18 fill=none stroke=currentColor stroke-width=2 stroke-linecap=round stroke-linejoin=round>{{p|safe}}</svg>{% endmacro %}
<style>.ivl{display:flex;flex-direction:column;gap:8px}.ivr{display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:10px 12px;border:1.5px solid #dfe4f7;border-radius:14px;background:#fff}.ivd{flex:1;min-width:150px;line-height:1.35}.ivd b{display:block;font-size:14px}.ivd small{color:#6a74a8}.ivm{font-weight:800;white-space:nowrap}.iva{display:flex;gap:6px;align-items:center}.ivi{display:grid;place-items:center;width:36px;height:36px;border-radius:10px;border:0;background:#eef0ff;color:#4f46e5;cursor:pointer;padding:0;text-decoration:none}.ivi:hover{background:#4f46e5;color:#fff}.ivi{box-shadow:none!important}.ivi.x{background:#fff1f2!important;color:#e11d48!important}.ivi.x:hover{background:#e11d48!important;color:#fff!important}
.ivd b,.ivm{color:var(--ink,#1b2350)}.ivd small{color:var(--mut,#6a74a8)}
html[data-theme=dark] .ivr{background:#141b3a!important;border-color:#27315a!important}html[data-theme=dark] .ivd b,html[data-theme=dark] .ivm{color:#e6e9f7!important}html[data-theme=dark] .ivd small{color:#9aa5c8!important}
html[data-theme=dark] .ivr a.ivi,html[data-theme=dark] .ivr button.ivi{background:#1d2656!important;color:#cfd6f5!important}html[data-theme=dark] .ivr a.ivi:hover,html[data-theme=dark] .ivr button.ivi:hover{background:#4f46e5!important;color:#fff!important}
html[data-theme=dark] .ivr button.ivi.x{background:#40152a!important;color:#fda4af!important}html[data-theme=dark] .ivr button.ivi.x:hover{background:#e11d48!important;color:#fff!important}</style>
<div class=ivl>{% for v in invs %}<div class=ivr><div class=ivd><b>{{v.day}} · <span dir=ltr>{{v.date}}</span></b><small>EINV-{{'%04d'|format(v.id)}} · {{v.nq}} قطعة{% if v.note %} · {{v.note}}{% endif %}</small></div><span class=ivm>{{ '%g'|format(v.total or 0) }} ₪</span>
<div class=iva><a class=ivi target=_blank href=/employees/{{e.id}}/invoice/{{v.id}} title="عرض الفاتورة" aria-label="عرض الفاتورة">{{ ico('<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8S1 12 1 12z"/><circle cx=12 cy=12 r=3 />') }}</a>
<a class=ivi target=_blank href="/employees/{{e.id}}/invoice/{{v.id}}?fmt=th" title="طباعة حرارية" aria-label="طباعة حرارية">{{ ico('<path d="M6 9V2h12v7M6 18H4a2 2 0 01-2-2v-5a2 2 0 012-2h16a2 2 0 012 2v5a2 2 0 01-2 2h-2"/><rect x=6 y=14 width=12 height=8 />') }}</a>
<a class=ivi href=/employees/{{e.id}}/invoice/{{v.id}}/edit title="تعديل الفاتورة" aria-label="تعديل الفاتورة">{{ ico('<path d="M12 20h9M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4z"/>') }}</a>
<form method=post action=/employees/{{e.id}}/invoice/{{v.id}}/delete class=il style="margin:0" onsubmit="return confirm('حذف الفاتورة EINV-{{'%04d'|format(v.id)}}؟ رح ترجع القطع للمخزن.')"><button class="ivi x" title="حذف الفاتورة" aria-label="حذف الفاتورة">{{ ico('<path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6M10 11v6M14 11v6"/>') }}</button></form></div></div>
{% else %}<div class="card em">ما في فواتير تسليم بعد. أول ما تسلّم بضاعة بتنعمل فاتورة تلقائياً.</div>{% endfor %}</div>"""

T["einvedit"] = """{% extends 'base' %}{% block c %}
<div class="card ehd" style="--h:{{(e.id*67)%360}}"><div class=av>{{e.name[:1]}}</div><div class=en><b>تعديل الفاتورة EINV-{{'%04d'|format(v.id)}}</b><small>{{e.name}}</small></div><span class=sp></span><a class="btn ghost" href="/employees/{{e.id}}?invs=1">{{ic.bk}} رجوع للفواتير</a></div>
<form method=post class=card style="padding:18px"><div class=fg><label>التاريخ<input type=date name=date value="{{v.date}}" required></label><label>ملاحظة<input name=note value="{{v.note or ''}}"></label></div>
<div style="overflow-x:auto;margin-top:12px"><table><tr><th>القطعة<th>الكمية<th>سعر الموظف (₪)</tr>
{% for x in lines %}<tr><td><b>{{x.part_name}}</b><td><input type=number min=1 name="q_{{x.id}}" value="{{x.qty}}" required inputmode=numeric style="width:90px"><td><input type=number step=any min=0 name="ep_{{x.id}}" value="{{x.emp_price or 0}}" required inputmode=decimal style="width:110px"></tr>{% endfor %}</table></div>
<p class=hint>تغيير الكمية بيعدّل المخزن تلقائياً. لإزالة الفاتورة كلها استخدم زر الحذف من قائمة الفواتير.</p>
<div class=df><button>حفظ التعديل</button><a class="btn ghost" href="/employees/{{e.id}}?invs=1">إلغاء</a></div></form>{% endblock %}"""

T["empinvs"] = """{% extends 'base' %}{% block c %}
<div class="card ehd" style="--h:{{(e.id*67)%360}}"><div class=av>{{e.name[:1]}}</div><div class=en><b>{{e.name}}</b><small>كل فواتير التسليم · {{invs|length}} فاتورة</small></div><span class=sp></span><a class="btn ghost" href=/employees/{{e.id}}>{{ic.bk}} رجوع لصفحة الموظف</a></div>
<div class=card><div class=ch><h3>🧾 فواتير التسليم</h3><small>كل تسليم بضاعة = فاتورة لحالها بتاريخها</small></div>{% include 'einvlist' %}</div>{% endblock %}"""

T["emp"] = """{% extends 'base' %}{% block c %}
<div class="card ehd" style="--h:{{(e.id*67)%360}}"><div class=av>{{e.name[:1]}}</div><div class=en><b>{{e.name}}</b><small>{{e.role or 'موظف'}}{% if e.phone %} · {{e.phone}}{% endif %} · منذ {{e.created}}</small>{% if e.notes %}<small>{{e.notes}}</small>{% endif %}</div><span class=sp></span>
<a class="btn ghost" href=/employees>{{ic.bk}} كل الموظفين</a><a class=btn href=/employees/{{e.id}}/report>📊 لوحة الموظف</a><a class="btn ghost" target=_blank href=/employees/{{e.id}}/statement>🧾 كشف ما أخذه</a><button type=button data-open=dlg-give>{{ic.go}} تسليم بضاعة</button><button type=button class=ghost data-open=dlg-invs title="فواتير التسليم" aria-label="فواتير التسليم">🧾 فواتير التسليم · {{ninv}}</button><button type=button data-open=dlg-copay title="استلام دفعة من الموظف" data-fill='{{ {"amount": acc.left, "pm": "نقد", "note": "", "receipt": ""}|tojson }}'>💵 دفعة · عليه {{ '%g'|format(acc.left) }} ₪</button>
<button type=button class="ghost" data-open=dlg-elogin data-fill='{{ {"login": e.login or ""}|tojson }}'>{{ic.us}} {{ 'دخول الموظف: مفعّل' if e.login else 'إعطاء دخول للموظف' }}</button>
<button type=button class="ib ed" title="تعديل" aria-label="تعديل" data-open=dlg-eedit data-fill='{{ {"name": e.name, "phone": e.phone or "", "role": e.role or "", "notes": e.notes or ""}|tojson }}'>{{ic.ed}}</button>
<form method=post action=/employees/{{e.id}}/delete class=il onsubmit="return confirm('حذف الموظف؟')"><button class="ib dl" title="حذف" aria-label="حذف">{{ic.dl}}</button></form></div>
<div class="sg4"><div class=sc><span class="si b">{{cic['أخرى']}}</span><div><small>قطع بعهدته الآن</small><b>{{tot.nq}}</b></div></div>
<div class=sc><span class="si e">₪</span><div><small>قيمة العهدة (بسعر الموظف)</small><b>{{ '%g'|format(tot.cost) }} ₪</b></div></div>
<div class=sc><span class="si c">₪</span><div><small>قيمة البيع المتوقعة</small><b>{{ '%g'|format(tot.val) }} ₪</b></div></div>
<div class=sc><span class="si a">{{ic.go}}</span><div><small>إجمالي ما تسلّمه · استهلك</small><b>{{given}} · {{used}}</b></div></div></div>
<dialog class=dlg id=dlg-invs style="width:min(760px,96vw);padding:0"><div class=dh><h3>🧾 فواتير التسليم ({{ninv}})</h3><button type=button class=cl data-close aria-label="إغلاق">×</button></div><div class=db style="max-height:72vh;overflow:auto">{% include 'einvlist' %}</div></dialog>
{% if open_invs %}<script>document.getElementById('dlg-invs').showModal()</script>{% endif %}
<dialog class=dlg id=dlg-eedit><form method=post action=/employees/{{e.id}}/edit><div class=dh><h3>تعديل بيانات الموظف</h3><button type=button class=cl data-close aria-label="إغلاق">×</button></div>
<div class=db><div class=fg><label>الاسم<input name=name required></label><label>الهاتف<input name=phone></label><label class=fa>الوظيفة<input name=role></label><label class=fa>ملاحظات<input name=notes></label></div></div>
<div class=df><button>حفظ</button><button type=button class=ghost data-close>إلغاء</button></div></form></dialog>
<dialog class=dlg id=dlg-elogin><form method=post action=/employees/{{e.id}}/login><div class=dh><h3>دخول {{e.name}} لصفحته</h3><button type=button class=cl data-close aria-label="إغلاق">×</button></div>
<div class=db><div class=fg><label>اسم الدخول (إيميل أو اسم بالإنجليزي)<input name=login dir=ltr required minlength=3 autocomplete=off placeholder="ahmad أو ahmad@gmail.com"></label>
<label>كلمة السر{% if e.login %} (اتركها فاضية للإبقاء على الحالية){% endif %}<input name=password id=epw dir=ltr minlength=6 autocomplete=new-password {{ '' if e.login else 'required' }}></label></div>
<p style="margin:10px 0 0"><button type=button class=ghost id=egen>توليد كلمة سر</button></p>
<p class=hint>🔒 أي كلمة سر بتحطها هون بتكون مؤقتة: أول ما الموظف يدخل بتجيه رسالة وبينجبر يغيّرها لكلمة سر خاصة فيه، وبعدها بيقدر يغيّرها وقت ما بدو من زر "الإعدادات" بصفحته.<br>الموظف بيفتح نفس صفحة تسجيل الدخول: <b dir=ltr>{{ request.host_url }}login</b> ويكتب اسم الدخول وكلمة السر. بيشوف بس بضاعته وحركاته (قراءة فقط) وما بيقدر يفتح أي صفحة ثانية.</p></div>
<div class=df><button>حفظ</button>{% if e.login %}<button type=submit formaction=/employees/{{e.id}}/login/off formnovalidate class=ghost onclick="return confirm('إيقاف دخول الموظف؟')">إيقاف الدخول</button>{% endif %}<button type=button class=ghost data-close>إلغاء</button></div></form></dialog>
<script>document.getElementById('egen').addEventListener('click',function(){var c='abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789',p='';for(var i=0;i<8;i++)p+=c[Math.floor(Math.random()*c.length)];var f=document.getElementById('epw');f.value=p;f.type='text'})</script>
<style>
#dlg-give .pkmain{padding:16px 18px;color:#16213f;background:#fff}
#dlg-give .pkcta{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:14px}
#dlg-give .pkopen{display:inline-flex;align-items:center;gap:10px;padding:12px 20px;font-size:15px}
#dlg-give .pkopen svg{width:22px;height:22px;flex:none}
#dlg-give .pkopen i{font-style:normal;background:#fff;color:#1c2760;border-radius:99px;min-width:26px;height:26px;display:none;align-items:center;justify-content:center;font-size:13px;font-weight:800;padding:0 7px}
#dlg-give .pkopen.has i{display:inline-flex}
#dlg-give .pkhint{color:#6a74a8;font-size:13px}
#dlg-give .pkhead{display:flex;align-items:center;gap:10px;margin:4px 0 8px}#dlg-give .pkhead b{font-size:15px}#dlg-give .pkhead span{color:#6a74a8;font-size:13px;flex:1}
#dlg-give .pkbasket{border:1.5px dashed #cfd6f3;border-radius:16px;padding:8px;min-height:92px;max-height:36vh;overflow:auto;background:#fafbff}
#dlg-give .pkempty{color:#7a84b4;text-align:center;padding:24px 10px;line-height:1.8}
#dlg-give .pkbr{display:flex;align-items:center;gap:10px;background:#fff;border:1.5px solid #e1e6f7;border-radius:14px;padding:8px 12px;margin-bottom:7px}
#dlg-give .pkbr:last-child{margin-bottom:0}
#dlg-give .pkepl{display:flex;flex-direction:column;gap:2px;font-size:11px;color:#6a74a8;font-weight:700}#dlg-give .pkepl input{width:88px;padding:6px 8px;border-radius:10px;font-size:14px}
#dlg-give .pkbn{flex:1;min-width:0;line-height:1.4}#dlg-give .pkbn b{display:block}#dlg-give .pkbn small{color:#6a74a8}
#dlg-give .pksum{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:12px 0}
#dlg-give .pksum div{background:#eef1fb;border-radius:14px;padding:9px 12px}#dlg-give .pksum small{display:block;color:#5a6499;font-size:12px}#dlg-give .pksum b{font-size:17px;color:#1c2760}
#dlg-give .pknote{display:block;margin-top:10px}#dlg-give .pknote input{display:block;width:100%;margin-top:6px}
.pkqs{display:flex;align-items:center;border:1.5px solid #dfe4f6;border-radius:11px;overflow:hidden;flex:none;background:#fff}
.pkqs button{all:unset;box-sizing:border-box;display:flex;align-items:center;justify-content:center;width:34px;height:34px;font-size:20px;font-weight:800;line-height:1;cursor:pointer;background:#eef1fb;color:#1c2760!important}
.pkqs button:hover{background:#dfe5fb}
.pkqs input{width:46px;height:34px;border:0!important;text-align:center;font-weight:800;padding:0!important;box-shadow:none!important;-moz-appearance:textfield;background:#fff!important;color:#16213f!important}
.pkqs input::-webkit-outer-spin-button,.pkqs input::-webkit-inner-spin-button{-webkit-appearance:none}
.pkrm{all:unset;box-sizing:border-box;cursor:pointer;color:#c0314e!important;font-size:22px;line-height:1;padding:2px 7px;border-radius:8px}.pkrm:hover{background:#ffe9ee}
#dlg-pick .pkw{color:#16213f;background:#fff;display:flex;flex-direction:column;max-height:76vh}
#dlg-pick .pktb{position:sticky;top:0;z-index:3;background:#fff;padding:12px 16px 10px;border-bottom:1px solid #e1e6f7}
#dlg-pick .pktb .tr{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
#dlg-pick .pktb .search{display:flex;flex:1;min-width:200px;margin:0}
#dlg-pick .pktb select{width:auto;min-width:150px}
#dlg-pick .pkchips{display:flex;gap:6px;overflow-x:auto;padding:9px 0 1px}
#dlg-pick .pkchip{all:unset;box-sizing:border-box;flex:none;cursor:pointer;border:1.5px solid #dfe4f6;border-radius:99px;padding:4px 14px;font-size:13px;font-weight:700;background:#fff;color:#33407a!important}
#dlg-pick .pkchip.on{background:#1c2760;border-color:#1c2760;color:#fff!important}
#dlg-pick .pkcols,#dlg-pick .pkrow{display:grid;grid-template-columns:minmax(0,1fr) 90px 84px 84px 142px;gap:10px;align-items:center;padding:9px 16px}
#dlg-pick .pkcols{background:#1c2760;color:#fff;font-size:12.5px;font-weight:800;position:sticky;top:0}
#dlg-pick .pklist{overflow:auto;flex:1;min-height:120px}
#dlg-pick .pkrow{border-bottom:1px solid #edf0fb;cursor:pointer;transition:background .12s}
#dlg-pick .pkrow:nth-child(even){background:#fafbff}#dlg-pick .pkrow:hover{background:#eef1fb}#dlg-pick .pkrow.sel{background:#e7ecff;box-shadow:inset 4px 0 0 #1c2760}
#dlg-pick .pkrow .pkn b{display:block;line-height:1.35}#dlg-pick .pkrow .pkn small{color:#6a74a8}
#dlg-pick .pkbd{display:inline-block;min-width:38px;text-align:center;padding:2px 10px;border-radius:99px;font-weight:800;font-size:13px;background:#dff6e8;color:#15703b}
#dlg-pick .pkbd.low{background:#fff1d6;color:#a35d00}
#dlg-pick .pkp{font-weight:700;white-space:nowrap}#dlg-pick .pkp small{display:none}
#dlg-pick .pkadd{all:unset;box-sizing:border-box;display:inline-flex;align-items:center;gap:6px;cursor:pointer;padding:7px 16px;border-radius:11px;background:#1c2760;color:#fff!important;font-weight:800;font-size:13.5px}
#dlg-pick .pkadd:hover{background:#2a3880}
#dlg-pick .pkempty{color:#7a84b4;text-align:center;padding:30px 10px}
#dlg-pick .pkft{display:flex;align-items:center;gap:12px;padding:12px 16px;border-top:1px solid #e1e6f7;background:#f6f8ff}#dlg-pick .pkft span{flex:1;font-weight:700}
@media (max-width:760px){
 #dlg-give .pksum{grid-template-columns:1fr 1fr 1fr}#dlg-give .pksum b{font-size:14.5px}
 #dlg-pick .pkcols{display:none}
 #dlg-pick .pkrow{grid-template-columns:1fr 1fr 1fr;gap:6px 8px}
 #dlg-pick .pkrow .pkn{grid-column:1/-1}
 #dlg-pick .pkp small{display:block;color:#6a74a8;font-weight:600;font-size:11px}
 #dlg-pick .pkrow .pkct{grid-column:1/-1;justify-self:stretch;display:flex;justify-content:flex-end}
 #dlg-pick .pkadd{width:100%;justify-content:center}
}
</style>
<dialog class=dlg id=dlg-give style="width:min(720px,96vw);padding:0"><form method=post action=/employees/{{e.id}}/give id=gform autocomplete=off><div class=dh><h3>تسليم بضاعة إلى {{e.name}}</h3><button type=button class=cl data-close aria-label="إغلاق">×</button></div>
<div class=pkmain>{% if parts %}
<div class=pkcta><button type=button id=gopen class=pkopen>{{ic.pk}}<span>عرض القطع المتوفرة</span><i id=gopencnt></i></button><span class=pkhint>{{parts|length}} صنف متوفر بالمخزن الرئيسي</span></div>
<div class=pkhead><b>القطع المختارة</b><span id=gcnt></span><button type=button class=ghost id=gclear hidden style="padding:4px 12px;font-size:12.5px">مسح الكل</button></div>
<div id=gbasket class=pkbasket></div>
<div id=gsum class=pksum hidden><div><small>عدد القطع</small><b id=s_n>0</b></div><div><small>حسابه على الشركة (بسعره)</small><b id=s_c>0</b></div><div><small>قيمة البيع</small><b id=s_p>0</b></div></div>
<div id=ginputs></div>
<label class=pknote>ملاحظة (اختياري، لكل القطع)<input name=note></label>
{% else %}<div class=em>ما في قطع متوفرة بالمخزن الرئيسي.</div>{% endif %}</div>
<div class=df>{% if parts %}<button id=gok disabled>موافق</button>{% endif %}<button type=button class=ghost data-close>إلغاء</button></div></form></dialog>
{% if parts %}{% set cats = parts|map(attribute='category')|unique|list %}
<dialog class=dlg id=dlg-pick style="width:min(1040px,97vw);padding:0"><div class=dh><h3>القطع المتوفرة بالمخزن الرئيسي</h3><button type=button class=cl data-close aria-label="إغلاق">×</button></div>
<div class=pkw><div class=pktb><div class=tr><label class=search>{{ic.sr}}<input id=gsearch type=search placeholder="ابحث عن قطعة: شاشة، بطارية، iPhone 11..." autocomplete=off></label>
<select id=gsort aria-label="الترتيب"><option value=def>الترتيب: حسب النوع</option><option value=name>الاسم (أ-ي)</option><option value=qty_d>الأكثر كمية</option><option value=qty_a>الأقل كمية</option><option value=price_d>السعر الأعلى</option><option value=price_a>السعر الأقل</option></select></div>
<div class=pkchips id=gchips><button type=button class="pkchip on" data-c="">الكل ({{parts|length}})</button>{% for c in cats %}<button type=button class=pkchip data-c="{{c}}">{{c}}</button>{% endfor %}</div></div>
<div class=pkcols><span>القطعة</span><span>المتوفر</span><span>الجملة</span><span>البيع</span><span>الكمية</span></div>
<div class=pklist id=glist>{% for p in parts %}<div class=pkrow data-id={{p.id}} data-max={{p.qty}} data-name="{{plabel(p)}}" data-c="{{p.category}}" data-t="{{p.category}} {{plabel(p)}}" data-cost="{{ '%g'|format(p.cost or 0) }}" data-price="{{ '%g'|format(p.price or 0) }}" data-emp="{{ '%g'|format(p.emp_price if p.emp_price is not none else (p.cost or 0)) }}" data-i={{loop.index}}>
<div class=pkn><b>{{plabel(p)}}</b><small>{{p.category}}</small></div>
<div class=pkp><small>المتوفر</small><span class="pkbd {{ 'low' if p.qty <= (p.min_qty or 0) }}">{{p.qty}}</span></div>
<div class=pkp><small>الجملة</small>{{ '%g'|format(p.cost or 0) }} ₪</div><div class=pkp><small>البيع</small>{{ '%g'|format(p.price or 0) }} ₪</div>
<div class=pkct></div></div>{% endfor %}<div class=pkempty id=gnone hidden>ما في قطع بهالبحث.</div></div>
<div class=pkft><span id=gpsum>ما اخترت شي بعد</span><button type=button data-close>تم</button></div></div></dialog>
<script>(function(){var g=document.getElementById('dlg-give'),pk=document.getElementById('dlg-pick'),ok=document.getElementById('gok');if(!g||!pk||!ok)return;
var $=function(i){return document.getElementById(i)},list=$('glist'),bk=$('gbasket'),inp=$('ginputs'),sel={},cat='';
var rows=[].slice.call(list.querySelectorAll('.pkrow'));
function esc(t){return String(t).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
function m(x){return String(Math.round(x*100)/100)}
function stepper(id,s){return '<span class=pkqs><button type=button data-a=minus aria-label="نقص">−</button><input type=number inputmode=numeric min=1 max='+s.max+' value='+s.q+' aria-label="الكمية"><button type=button data-a=plus aria-label="زيادة">+</button></span>'}
function filt(){var v=$('gsearch').value.trim().toLowerCase(),n=0;rows.forEach(function(r){var okv=(!cat||r.dataset.c===cat)&&(r.dataset.t||'').toLowerCase().indexOf(v)>-1;r.style.display=okv?'':'none';if(okv)n++});$('gnone').hidden=n>0}
function sortRows(){var k=$('gsort').value,f={def:function(a,b){return a.dataset.i-b.dataset.i},name:function(a,b){return a.dataset.name.localeCompare(b.dataset.name,'ar')},qty_d:function(a,b){return b.dataset.max-a.dataset.max},qty_a:function(a,b){return a.dataset.max-b.dataset.max},price_d:function(a,b){return b.dataset.price-a.dataset.price},price_a:function(a,b){return a.dataset.price-b.dataset.price}}[k];
rows.sort(f);rows.forEach(function(r){list.insertBefore(r,$('gnone'))})}
function paint(){var ids=Object.keys(sel),tot=0,cv=0,pv=0,h='',hi='';
rows.forEach(function(r){var s=sel[r.dataset.id],c=r.querySelector('.pkct');r.classList.toggle('sel',!!s);c.innerHTML=s?stepper(r.dataset.id,s):'<button type=button class=pkadd data-a=add>+ إضافة</button>'});
ids.forEach(function(id){var s=sel[id];tot+=s.q;cv+=s.q*s.ep;pv+=s.q*s.price;
h+='<div class=pkbr data-id='+id+'><span class=pkbn><b>'+esc(s.name)+'</b><small>سعر الشركة '+m(s.cost)+' · بيع '+m(s.price)+' ₪ · متوفر '+s.max+'</small></span><label class=pkepl>سعر الموظف ₪<input class=pkep type=number step=any min=0 value='+m(s.ep)+' aria-label="سعر الموظف"></label>'+stepper(id,s)+'<button type=button class=pkrm data-a=rm aria-label="حذف" title="حذف">×</button></div>';
hi+='<input type=hidden name=pick value='+id+'><input type=hidden name=q_'+id+' value='+s.q+'><input type=hidden name=ep_'+id+' value='+s.ep+'>'});
bk.innerHTML=h||'<div class=pkempty>ما اخترت قطع لسا.<br><small>اضغط "عرض القطع المتوفرة" واختر اللي بدك تسلّمه.</small></div>';inp.innerHTML=hi;
$('gcnt').textContent=ids.length?ids.length+' صنف':'';$('gclear').hidden=!ids.length;$('gsum').hidden=!ids.length;$('s_n').textContent=tot;$('s_c').textContent=m(cv)+' ₪';$('s_p').textContent=m(pv)+' ₪';
$('gopen').classList.toggle('has',tot>0);$('gopencnt').textContent=tot;$('gpsum').textContent=ids.length?'المختار: '+ids.length+' صنف · '+tot+' قطعة':'ما اخترت شي بعد';
ok.disabled=!ids.length;ok.textContent=ids.length?'موافق ('+tot+' قطعة)':'موافق'}
function add(r){var id=r.dataset.id,x=+r.dataset.max;if(!sel[id])sel[id]={name:r.dataset.name,max:x,q:0,cost:+r.dataset.cost,price:+r.dataset.price,ep:+r.dataset.emp};if(sel[id].q<x)sel[id].q++;paint()}
function act(e,scope){var a=e.target.closest('[data-a]');if(!a)return false;var el=e.target.closest('[data-id]'),id=el&&el.dataset.id;if(!id)return false;e.stopPropagation();
if(a.dataset.a==='add'){add(el)}else{var s=sel[id];if(!s)return true;if(a.dataset.a==='plus'){if(s.q<s.max)s.q++}else if(a.dataset.a==='minus')s.q--;else if(a.dataset.a==='rm')s.q=0;if(s.q<1)delete sel[id];paint()}return true}
function chg(e){if(e.target.classList.contains('pkep')){var el0=e.target.closest('[data-id]'),s0=el0&&sel[el0.dataset.id];if(s0){s0.ep=Math.max(0,+e.target.value||0);paint()}return}if(e.target.type!=='number')return;var el=e.target.closest('[data-id]'),s=el&&sel[el.dataset.id];if(!s)return;s.q=Math.max(1,Math.min(s.max,Math.floor(+e.target.value||1)));paint()}
list.addEventListener('click',function(e){if(act(e))return;if(e.target.closest('.pkqs'))return;var r=e.target.closest('.pkrow');if(r)add(r)});
bk.addEventListener('click',act);list.addEventListener('change',chg);bk.addEventListener('change',chg);
$('gchips').addEventListener('click',function(e){var c=e.target.closest('.pkchip');if(!c)return;cat=c.dataset.c;[].slice.call(this.children).forEach(function(x){x.classList.toggle('on',x===c)});filt()});
$('gsearch').addEventListener('input',filt);$('gsort').addEventListener('change',sortRows);
$('gsearch').addEventListener('keydown',function(e){if(e.key==='Enter'){e.preventDefault();var f=rows.filter(function(r){return r.style.display!=='none'});if(f.length===1){add(f[0]);this.select()}}});
$('gclear').addEventListener('click',function(){sel={};paint()});
$('gform').addEventListener('keydown',function(e){if(e.key==='Enter'&&e.target.tagName==='INPUT')e.preventDefault()});
$('gopen').addEventListener('click',function(){pk.showModal();if(window.innerWidth>760)setTimeout(function(){$('gsearch').focus()},60)});
pk.addEventListener('close',function(){$('gsearch').value='';cat='';[].slice.call($('gchips').children).forEach(function(x,i){x.classList.toggle('on',i===0)});$('gsort').value='def';sortRows();filt()});
paint()})();</script>{% endif %}
<dialog class=dlg id=dlg-back><form method=post action=/employees/{{e.id}}/move><div class=dh><h3>إرجاع أو استهلاك من عهدة {{e.name}}</h3><button type=button class=cl data-close aria-label="إغلاق">×</button></div>
<div class=db>{% if H %}<div class=fg><label class=fa>العملية<select name=kind><option value="إرجاع">إرجاع للمخزن الرئيسي (بتزيد كمية المخزن)</option><option value="استهلاك">استهلاك / بيع (بتنقص من عهدته بدون ما ترجع للمخزن)</option></select></label>
<label class=fa>القطعة<select name=part_id required>{% for h in H %}<option value={{h.part_id}}>{{h.pname}} — بعهدته {{h.held}}</option>{% endfor %}</select></label>
<label>الكمية<input name=qty type=number min=1 value=1 required inputmode=numeric></label><label>ملاحظة<input name=note placeholder="اختياري"></label></div>{% else %}<div class=em>ما في بضاعة بعهدة الموظف.</div>{% endif %}</div>
<div class=df>{% if H %}<button>حفظ</button>{% endif %}<button type=button class=ghost data-close>إلغاء</button></div></form></dialog>
<div class=card><div class=ch><h3>💼 حساب الموظف مع الشركة</h3><button type=button data-open=dlg-copay data-fill='{{ {"amount": acc.left, "pm": "نقد", "note": "", "receipt": ""}|tojson }}'>💵 استلام دفعة من الموظف</button></div>
<div class=sg4 style="padding:0 18px 14px"><div class=sc><span class="si b">₪</span><div><small>بضاعة مسلّمة (بسعر الموظف)</small><b>{{ '%g'|format(acc.goods) }} ₪</b></div></div>
<div class=sc><span class="si c">₪</span><div><small>دفع للشركة</small><b>{{ '%g'|format(acc.paid) }} ₪</b></div></div>
<div class=sc><span class="si d">₪</span><div><small>المتبقي عليه</small><b style="color:{{ '#e11d48' if acc.left>0 else '#059669' }}">{{ '%g'|format(acc.left) }} ₪</b></div></div>
<div class=sc><span class="si e">₪</span><div><small>ربح الشركة من البضاعة</small><b>{{ '%g'|format(acc.margin) }} ₪</b></div></div></div>
{% if copays %}<div style="overflow-x:auto"><table><tr><th>التاريخ<th>المبلغ<th>الطريقة<th>الوصل<th>ملاحظة<th></tr>{% for p in copays %}<tr><td class=nw dir=ltr>{{p.created}}<td class=nw><b style="color:#059669">{{ '%g'|format(p.amount) }} ₪</b><td><span class=tag>{{ 'تحويل بنكي' if p.method=='بنك' else 'نقداً' }}</span><td>{% if p.receipt %}<a href=/payreceipt/{{p.receipt}} target=_blank>🧾 عرض الوصل</a>{% else %}<small>—</small>{% endif %}<td><small>{{p.note or ''}}</small>{% if p.by_emp %} <span class="pill s2">رحّلها الموظف</span>{% endif %}
<td><form method=post action=/employees/{{e.id}}/copay/{{p.id}}/delete class=il onsubmit="return confirm('حذف هذه الدفعة؟ رح يرجع المبلغ كمتبقي على الموظف.')"><button class="ib dl" title="حذف" aria-label="حذف">{{ic.dl}}</button></form></tr>{% endfor %}</table></div>{% endif %}
<p class=hint style="padding:0 18px 10px">سعر الموظف بيتحدد وقت التسليم (بيتحفظ كآخر سعر للقطعة). الموظف بيبيع بالسعر اللي بده، وربحه = سعر البيع − سعره.</p></div>
<dialog class=dlg id=dlg-copay><form method=post action=/employees/{{e.id}}/copay enctype=multipart/form-data onsubmit="if(this.pm.value==='بنك'&&!this.receipt.files.length){alert('أرفق صورة وصل التحويل');return false}"><div class=dh><h3>استلام دفعة من {{e.name}}</h3><button type=button class=cl data-close aria-label="إغلاق">×</button></div>
<div class=db><p style="margin:0 0 10px">الشركة بدها منه: <b style="color:#e11d48">{{ '%g'|format(acc.left) }} ₪</b> <small>(بضاعة {{ '%g'|format(acc.goods) }} ₪ − مدفوع {{ '%g'|format(acc.paid) }} ₪)</small></p><div class=fg><label>المبلغ اللي دفعه (₪)<input name=amount type=number step=any min=0.01 max="{{acc.left}}" required inputmode=decimal></label>
<label>طريقة الدفع<select name=pm><option value=نقد>نقداً (كاش)<option value=بنك>تحويل بنكي</select></label>
<label class=fa>صورة الوصل (إلزامية مع الدفعة البنكية)<input type=file name=receipt accept="image/*,application/pdf"></label>
<label class=fa>ملاحظة (اختياري)<input name=note></label></div></div>
<div class=df><button>حفظ الدفعة</button><button type=button class=ghost data-close>إلغاء</button></div></form></dialog>
<div class=card><div class=ch><h3>البضاعة اللي بعهدته الآن</h3></div>
<div style="padding:0 18px 4px"><label class=search style="display:flex;margin:6px 0 10px">{{ic.sr}}<input data-tsearch=htbl placeholder="🔍 ابحث في البضاعة (اسم القطعة، اللون...)" autocomplete=off></label><small class=hint data-tcount=htbl></small></div>
<table class=srt id=htbl><tr><th>القطعة<th>الكمية بعهدته<th>سعر الشركة<th>سعر الموظف<th>سعر البيع المقترح<th>قيمة البيع<th class=ns>إجراءات</tr>
{% for h in H %}<tr><td><b>{{h.pname}}</b><td data-v={{h.held}}><span class=tag>{{h.held}}</span><td>{{ '%g'|format(h.ccost) }} ₪<td><b>{{ '%g'|format(h.cost) }} ₪</b><td>{{ '%g'|format(h.price) }} ₪<td class=nw>{{ '%g'|format(h.held*h.price) }} ₪
<td><div class=sa><button type=button class=ghost data-open=dlg-back data-fill='{{ {"part_id": h.part_id, "kind": "إرجاع", "qty": h.held}|tojson }}' style="padding:6px 12px;font-size:13px">{{ic.rt}} إرجاع</button>
<button type=button class=ghost data-open=dlg-back data-fill='{{ {"part_id": h.part_id, "kind": "استهلاك", "qty": 1}|tojson }}' style="padding:6px 12px;font-size:13px">{{ic.ck}} استهلاك</button></div></tr>
{% else %}<tr><td colspan=6 class=em>ما في بضاعة بعهدة {{e.name}}. اضغط "تسليم بضاعة".</tr>{% endfor %}</table></div>
<div class=card><div class=ch><h3>سجل الحركات</h3><small>آخر {{log|length}} حركة</small></div>
<table class=srt id=ltbl><tr><th>التاريخ<th>القطعة<th>العملية<th>الكمية<th>ملاحظة<th class=ns></tr>
{% for l in log %}<tr><td class=nw>{{l.created}}<td><b>{{l.part_name}}</b><td><span class="pill {{ {'تسليم':'s1','إرجاع':'s2','استهلاك':'s0','بيع':'s2','مرتجع':'s3'}.get(l.kind,'s0') }}">{{l.kind}}</span><td>{{l.qty}}<td>{{l.note}}{% if l.inv_id %} <a href=/employees/{{e.id}}/invoice/{{l.inv_id}} target=_blank><small>EINV-{{'%04d'|format(l.inv_id)}}</small></a>{% endif %}
<td><form method=post action=/employees/log/{{l.id}}/delete class=il onsubmit="return confirm('إلغاء هالحركة وتعديل المخزون؟')"><button class="ib dl" title="إلغاء الحركة" aria-label="إلغاء الحركة">{{ic.dl}}</button></form></tr>
{% else %}<tr><td colspan=6 class=em>ما في حركات بعد.</tr>{% endfor %}</table></div>{% endblock %}"""

T["people"] = """{% extends 'base' %}{% block c %}
<div class="sg4"><div class=sc><span class="si a">{{ic.us}}</span><div><small>عدد الأشخاص</small><b>{{T.n}}</b></div></div>
<div class=sc><span class="si d">₪</span><div><small>إجمالي المتبقي من الديون</small><b>{{ '%g'|format(T.rem) }} ₪</b></div></div>
<div class=sc><span class="si e">{{ic.cp}}</span><div><small>شيكات لم تُصرف</small><b>{{ '%g'|format(T.wait) }} ₪</b></div></div>
<div class=sc><span class="si c">{{ic.us}}</span><div><small>أشخاص عليهم مبلغ</small><b>{{T.debtors}}</b></div></div></div>
<div class=tools><div class=r1><label class=search>{{ic.sr}}<input data-f=ptbl data-role=search placeholder="بحث عن شخص..."></label><button type=button data-open=dlg-pnew>{{ic.pl}} شخص جديد</button></div></div>
<dialog class=dlg id=dlg-pnew><form method=post><div class=dh><h3>إضافة شخص</h3><button type=button class=cl data-close aria-label="إغلاق">×</button></div>
<div class=db><div class=fg><label>الاسم<input name=name required></label><label>الهاتف<input name=phone inputmode=tel dir=ltr></label><label class=fa>ملاحظة<input name=note></label></div>
<p class=hint>بعد الإضافة بتفتح صفحة الشخص وبتقدر تسجّل له ديون ودفعات وشيكات.</p></div><div class=df><button>حفظ</button><button type=button class=ghost data-close>إلغاء</button></div></form></dialog>
<div class=card><table class=srt id=ptbl><tr><th>الشخص<th>الدين المتبقي<th>الشيكات<th>آخر حركة<th class=ns></tr>
{% for r in rows %}<tr><td><a href=/people/{{r.id}} style="font-weight:800;font-size:15px">{{r.name}}</a>{% if r.phone %}<br><small dir=ltr>{{r.phone}}</small>{% endif %}
<td data-v={{r.rem}} class=nw>{% if r.debt or r.cash %}{% if r.rem > 0 %}<span class="amt up">{{ '%g'|format(r.rem) }} ₪</span>{% elif r.rem < 0 %}<span class="amt dn">له {{ '%g'|format(-r.rem) }} ₪</span>{% else %}<span class=tag>مسدّد</span>{% endif %}{% else %}<small>لا ديون</small>{% endif %}
<td>{% if r.n_chk %}{% if r.n_wait %}<span class="pill s0">{{r.n_wait}} لم يُصرف</span> {% endif %}{% if r.n_ok %}<span class="pill s2">{{r.n_ok}} صُرف</span> {% endif %}{% if r.n_bad %}<span class="pill s3">{{r.n_bad}} راجع</span>{% endif %}{% if r.overdue %}<br><small class=low>{{r.overdue}} متأخر</small>{% endif %}{% else %}<small>—</small>{% endif %}
<td class=nw><small>{{r.last or r.created}}</small>
<td><div class=sa><a class="ib" title="فتح الحساب" aria-label="فتح الحساب" href=/people/{{r.id}}>{{ic.eye}}</a></div></tr>
{% else %}<tr><td colspan=5 class=em>ما في أشخاص بعد. اضغط "شخص جديد" أو سجّل دين/شيك وبينضاف الشخص تلقائياً.</tr>{% endfor %}</table></div>{% endblock %}"""

T["person"] = """{% extends 'base' %}{% block c %}
<div class="card ehd" style="--h:{{(d.id*67)%360}}"><div class=av>{{d.name[:1]}}</div><div class=en><b>{{d.name}}</b><small>{% if d.phone %}<span dir=ltr>{{d.phone}}</span> · {% endif %}منذ {{d.created}}</small>{% if d.note %}<small>{{d.note}}</small>{% endif %}</div><span class=sp></span>
<a class="btn ghost" href=/people>{{ic.bk}} كل الأشخاص</a><button type=button class=ghost data-open=dlg-adebt>{{ic.pl}} دين جديد</button><button type=button class=ghost data-open=dlg-apay>{{ic.ck}} دفعة نقدية</button><button type=button data-open=dlg-achq>{{ic.cp}} شيك جديد</button>
<button type=button class="ib ed" title="تعديل" aria-label="تعديل" data-open=dlg-dedit data-fill='{{ {"name": d.name, "phone": d.phone or "", "note": d.note or ""}|tojson }}'>{{ic.ed}}</button>
<form method=post action=/people/{{d.id}}/delete class=il onsubmit="return confirm('حذف الشخص مع كل ديونه وشيكاته؟')"><button class="ib dl" title="حذف" aria-label="حذف">{{ic.dl}}</button></form></div>
<div class="sg4"><div class=sc><span class="si a">₪</span><div><small>إجمالي ما أخذه (دين)</small><b>{{ '%g'|format(F.debt) }} ₪</b></div></div>
<div class=sc><span class="si c">{{ic.ck}}</span><div><small>دفع نقداً</small><b>{{ '%g'|format(F.cash) }} ₪</b></div></div>
<div class=sc><span class="si f">{{ic.cp}}</span><div><small>شيكات صُرفت</small><b>{{ '%g'|format(F.chk_ok) }} ₪</b></div></div>
<div class=sc><span class="si e">{{ic.cp}}</span><div><small>شيكات لم تُصرف{% if F.overdue %} · <span class=low>{{F.overdue}} متأخر</span>{% endif %}</small><b>{{ '%g'|format(F.chk_wait) }} ₪</b></div></div></div>
<div class="card rem"><div><small>المتبقي عليه</small><b class="{{'up' if F.rem>0 else 'dn'}}">{% if F.rem>0 %}{{ '%g'|format(F.rem) }} ₪{% elif F.rem<0 %}له {{ '%g'|format(-F.rem) }} ₪{% elif F.debt %}مسدّد بالكامل ✓{% else %}لا ديون{% endif %}</b>
{% if F.chk_wait and F.rem>0 %}<small>وإذا انصرفت الشيكات اللي ما انصرفت بيصير المتبقي {{ '%g'|format(F.after if F.after>0 else 0) }} ₪</small>{% endif %}</div>
<div style="flex:1;min-width:200px"><div class=pgb><i style="width:{{F.pct}}%;background:linear-gradient(90deg,#34d399,#059669)"></i></div><small>سدّد {{F.pct}}% · المدفوع {{ '%g'|format(F.paid) }} ₪{% if F.chk_bad %} · شيكات راجعة {{ '%g'|format(F.chk_bad) }} ₪{% endif %}</small></div></div>

<div class=card><div class=ch><h3>🧾 الديون (شو أخذ)</h3><button type=button class=ghost data-open=dlg-adebt style="padding:6px 12px;font-size:13px">{{ic.pl}} دين جديد</button></div>
<div style="overflow-x:auto"><table><tr><th>التاريخ<th>شو أخذ<th>المبلغ<th>ملاحظة<th></tr>
{% for r in debts %}<tr><td class=nw>{{r.created}}<td><b>{{r.item or r.note or '—'}}</b><td class=nw><span class="amt up">{{ '%g'|format(r.amount) }} ₪</span><td><small>{{ r.note if r.item else '' }}</small>
<td><form method=post action=/debts/entry/{{r.id}}/delete class=il onsubmit="return confirm('حذف هالدين؟')"><input type=hidden name=back value=/people/{{d.id}}><button class="ib dl" title="حذف" aria-label="حذف">{{ic.dl}}</button></form></tr>
{% else %}<tr><td colspan=5 class=em>ما في ديون مسجّلة.</tr>{% endfor %}</table></div></div>

<div class=card><div class=ch><h3>💵 الدفعات النقدية</h3><button type=button class=ghost data-open=dlg-apay style="padding:6px 12px;font-size:13px">{{ic.pl}} دفعة</button></div>
<div style="overflow-x:auto"><table><tr><th>التاريخ<th>المبلغ<th>ملاحظة<th></tr>
{% for r in pays %}<tr><td class=nw>{{r.created}}<td class=nw><span class="amt dn">{{ '%g'|format(r.amount) }} ₪</span><td><small>{{r.note}}</small>
<td><form method=post action=/debts/entry/{{r.id}}/delete class=il onsubmit="return confirm('حذف الدفعة؟')"><input type=hidden name=back value=/people/{{d.id}}><button class="ib dl" title="حذف" aria-label="حذف">{{ic.dl}}</button></form></tr>
{% else %}<tr><td colspan=4 class=em>ما في دفعات نقدية.</tr>{% endfor %}</table></div></div>

<div class=card><div class=ch><h3>🏦 الشيكات</h3><button type=button class=ghost data-open=dlg-achq style="padding:6px 12px;font-size:13px">{{ic.pl}} شيك</button></div>
<div style="overflow-x:auto">{% set back='/people/%d'|format(d.id) %}{% include 'chqtable' %}</div></div>

<dialog class=dlg id=dlg-adebt><form method=post action=/debts/entry><input type=hidden name=person_id value={{d.id}}><input type=hidden name=kind value="دين"><input type=hidden name=back value=/people/{{d.id}}><div class=dh><h3>دين جديد على {{d.name}}</h3><button type=button class=cl data-close aria-label="إغلاق">×</button></div>
<div class=db><div class=fg><label class=fa>شو أخذ؟<input name=item required placeholder="مثلاً: شاشة iPhone 11 + بطارية"></label>
<label>إجمالي المبلغ (₪)<input name=amount type=number step=any min=0 required inputmode=decimal></label><label>كم دفع الآن؟ (₪)<input name=paid type=number step=any min=0 inputmode=decimal placeholder="اختياري"></label>
<label>التاريخ<input name=date type=date value="{{today}}"></label><label>ملاحظة<input name=note></label></div></div>
<div class=df><button>حفظ الدين</button><button type=button class=ghost data-close>إلغاء</button></div></form></dialog>
<dialog class=dlg id=dlg-apay><form method=post action=/debts/entry><input type=hidden name=person_id value={{d.id}}><input type=hidden name=kind value="دفعة"><input type=hidden name=back value=/people/{{d.id}}><div class=dh><h3>دفعة نقدية من {{d.name}}</h3><button type=button class=cl data-close aria-label="إغلاق">×</button></div>
<div class=db><div class=fg><label>المبلغ (₪)<input name=amount type=number step=any min=0 required inputmode=decimal></label><label>التاريخ<input name=date type=date value="{{today}}"></label><label class=fa>ملاحظة<input name=note></label></div>
<p class=hint>للدفع بشيك استخدم زر "شيك جديد" (وفيه خانة لنقد يجي مع الشيك).</p></div><div class=df><button>حفظ الدفعة</button><button type=button class=ghost data-close>إلغاء</button></div></form></dialog>
<dialog class=dlg id=dlg-achq><form method=post action=/cheques/add enctype=multipart/form-data><input type=hidden name=person_id value={{d.id}}><input type=hidden name=from_person value=1><input type=hidden name=back value=/people/{{d.id}}><div class=dh><h3>شيك جديد من {{d.name}}</h3><button type=button class=cl data-close aria-label="إغلاق">×</button></div>
<div class=db>{% set show_person=false %}{% include 'chqfields' %}</div><div class=df><button>حفظ الشيك</button><button type=button class=ghost data-close>إلغاء</button></div></form></dialog>
<dialog class=dlg id=dlg-dedit><form method=post action=/people/{{d.id}}/edit><div class=dh><h3>تعديل البيانات</h3><button type=button class=cl data-close aria-label="إغلاق">×</button></div>
<div class=db><div class=fg><label>الاسم<input name=name required></label><label>الهاتف<input name=phone></label><label class=fa>ملاحظة<input name=note></label></div></div>
<div class=df><button>حفظ</button><button type=button class=ghost data-close>إلغاء</button></div></form></dialog>
{% include 'chqedit' %}{% endblock %}"""

T["chqfields"] = """<div class=fg>
{% if show_person %}<label class=fa>الشخص (اكتب للبحث أو اسم جديد)<input name=person_name list=plist required autocomplete=off placeholder="🔍 ابحث أو اكتب اسم جديد"><datalist id=plist>{% for n in names %}<option value="{{n}}">{% endfor %}</datalist></label>{% endif %}
<label>رقم الشيك<input name=number required></label><label>البنك<input name=bank></label>
<label>المبلغ (₪)<input name=amount type=number step=any min=0 required inputmode=decimal></label><label>تاريخ الشيك / الاستحقاق<input name=due type=date></label>
<label class=fa>صاحب الشيك (اتركه فاضي إذا هو نفس الشخص)<input name=drawer></label>
<label>حالة الشيك<select name=status><option>لم يُصرف</option><option>صُرف</option><option>راجع</option></select></label><label>نقد مع الشيك (₪)<input name=cash type=number step=any min=0 inputmode=decimal placeholder="اختياري"></label>
<label class=fa>صورة الشيك<input name=photo type=file accept="image/*" capture=environment></label>
<label class=fa>ملاحظة<input name=note></label>
<label class=fa style="display:flex;gap:8px;align-items:center;flex-direction:row"><input type=checkbox name=on_debt value=1 checked style="width:auto"> يُحتسب من دين هذا الشخص (لما ينصرف بينقص من المتبقي)</label></div>"""

T["chqtable"] = """<table><tr><th>صورة<th>رقم الشيك<th>صاحب الشيك<th>البنك<th>المبلغ<th>تاريخه<th>الحالة<th></tr>
{% for c in chs %}<tr><td>{% if c.photo %}<a href=/chkphoto/{{c.photo}} target=_blank rel=noopener><img src=/chkphoto/{{c.photo}} alt="صورة الشيك" style="width:54px;height:40px;object-fit:cover;border-radius:8px;border:1px solid #dfe4f5"></a>{% else %}<small>—</small>{% endif %}
<td><b dir=ltr>{{c.number}}</b>{% if c.note %}<br><small>{{c.note}}</small>{% endif %}<td>{{c.drawer or '—'}}<td>{{c.bank or '—'}}<td class=nw><b>{{ '%g'|format(c.amount) }} ₪</b>{% if not c.on_debt %}<br><small>خارج الدين</small>{% endif %}
<td class=nw>{{c.due or '—'}}{% if c.status=='لم يُصرف' and c.due %}{% if c.due < today %}<br><small class=low>متأخر</small>{% elif c.due == today %}<br><small class=low>مستحق اليوم</small>{% endif %}{% endif %}
<td><span class="pill {{ {'لم يُصرف':'s0','صُرف':'s2','راجع':'s3'}[c.status] }}">{{c.status}}</span>
<div class=sa style="margin-top:6px">{% if c.status!='صُرف' %}<form method=post action=/cheques/{{c.id}}/status class=il><input type=hidden name=back value="{{back}}"><input type=hidden name=status value="صُرف"><button class=ghost style="padding:4px 10px;font-size:12.5px;margin:0">صُرف ✓</button></form>{% endif %}
{% if c.status=='لم يُصرف' %}<form method=post action=/cheques/{{c.id}}/status class=il><input type=hidden name=back value="{{back}}"><input type=hidden name=status value="راجع"><button class=ghost style="padding:4px 10px;font-size:12.5px;margin:0">راجع ✗</button></form>{% endif %}
{% if c.status!='لم يُصرف' %}<form method=post action=/cheques/{{c.id}}/status class=il><input type=hidden name=back value="{{back}}"><input type=hidden name=status value="لم يُصرف"><button class=ghost style="padding:4px 10px;font-size:12.5px;margin:0">لم يُصرف</button></form>{% endif %}</div>
<td class=nw><button type=button class="ib ed" title="تعديل" aria-label="تعديل" data-open=dlg-cedit data-fill='{{ {"number": c.number, "bank": c.bank or "", "amount": c.amount, "drawer": c.drawer or "", "due": c.due or "", "note": c.note or "", "_action": "/cheques/%d/edit"|format(c.id), "_on": c.on_debt}|tojson }}'>{{ic.ed}}</button>
<form method=post action=/cheques/{{c.id}}/delete class=il onsubmit="return confirm('حذف الشيك؟')"><input type=hidden name=back value="{{back}}"><button class="ib dl" title="حذف" aria-label="حذف">{{ic.dl}}</button></form></tr>
{% else %}<tr><td colspan=8 class=em>ما في شيكات.</tr>{% endfor %}</table>"""

T["chqedit"] = """<dialog class=dlg id=dlg-cedit><form method=post id=cedit-f action=/cheques/0/edit enctype=multipart/form-data><input type=hidden name=back value="{{ back }}"><div class=dh><h3>تعديل الشيك</h3><button type=button class=cl data-close aria-label="إغلاق">×</button></div>
<div class=db><div class=fg><label>رقم الشيك<input name=number required></label><label>البنك<input name=bank></label><label>المبلغ (₪)<input name=amount type=number step=any min=0 required inputmode=decimal></label><label>تاريخ الشيك / الاستحقاق<input name=due type=date></label>
<label class=fa>صاحب الشيك<input name=drawer></label><label class=fa>استبدال صورة الشيك<input name=photo type=file accept="image/*" capture=environment></label><label class=fa>ملاحظة<input name=note></label>
<label class=fa style="display:flex;gap:8px;align-items:center;flex-direction:row"><input type=checkbox name=on_debt value=1 id=cedit-on style="width:auto"> يُحتسب من دين الشخص</label></div></div>
<div class=df><button>حفظ</button><button type=button class=ghost data-close>إلغاء</button></div></form></dialog>
<script>document.addEventListener('click',function(e){var b=e.target.closest('[data-open=dlg-cedit]');if(b&&b.dataset.fill){try{var m=JSON.parse(b.dataset.fill);document.getElementById('cedit-f').action=m._action;document.getElementById('cedit-on').checked=!!m._on}catch(x){}}});</script>"""

T["debts"] = """{% extends 'base' %}{% block c %}
<div class="sg4"><div class=sc><span class="si d">₪</span><div><small>إجمالي المتبقي على الناس</small><b>{{ '%g'|format(T.rem) }} ₪</b></div></div>
<div class=sc><span class="si a">₪</span><div><small>إجمالي الديون المسجّلة</small><b>{{ '%g'|format(T.debt) }} ₪</b></div></div>
<div class=sc><span class="si c">{{ic.ck}}</span><div><small>المدفوع (نقد + شيكات مصروفة)</small><b>{{ '%g'|format(T.paid) }} ₪</b></div></div>
<div class=sc><span class="si e">{{ic.us}}</span><div><small>أشخاص عليهم مبلغ</small><b>{{T.n}}</b></div></div></div>
<div class=tools><div class=r1><label class=search>{{ic.sr}}<input data-f=dtbl data-role=search placeholder="بحث عن شخص..."></label>
<button type=button class=ghost data-open=dlg-pay>{{ic.ck}} دفعة نقدية</button><button type=button data-open=dlg-pdebt>{{ic.pl}} دين جديد</button></div></div>
<dialog class=dlg id=dlg-pdebt><form method=post action=/debts/entry><input type=hidden name=kind value="دين"><input type=hidden name=back value=/debts><div class=dh><h3>دين جديد</h3><button type=button class=cl data-close aria-label="إغلاق">×</button></div>
<div class=db><div class=fg><label class=fa>الشخص (اكتب للبحث أو اسم جديد)<input name=person_name list=plist required autocomplete=off placeholder="🔍 ابحث أو اكتب اسم جديد"><datalist id=plist>{% for n in names %}<option value="{{n}}">{% endfor %}</datalist></label>
<label class=fa>شو أخذ؟<input name=item required placeholder="مثلاً: شاشة iPhone 11 + بطارية"></label>
<label>إجمالي المبلغ (₪)<input name=amount type=number step=any min=0 required inputmode=decimal></label><label>كم دفع الآن؟ (₪)<input name=paid type=number step=any min=0 inputmode=decimal placeholder="اختياري"></label>
<label>التاريخ<input name=date type=date value="{{today}}"></label><label>ملاحظة<input name=note></label></div></div><div class=df><button>حفظ الدين</button><button type=button class=ghost data-close>إلغاء</button></div></form></dialog>
<dialog class=dlg id=dlg-pay><form method=post action=/debts/entry><input type=hidden name=kind value="دفعة"><input type=hidden name=back value=/debts><div class=dh><h3>دفعة نقدية</h3><button type=button class=cl data-close aria-label="إغلاق">×</button></div>
<div class=db><div class=fg><label class=fa>الشخص<input name=person_name list=plist2 required autocomplete=off placeholder="🔍 ابحث عن الشخص"><datalist id=plist2>{% for r in rows %}<option value="{{r.name}}">متبقي {{ '%g'|format(r.rem) }} ₪</option>{% endfor %}</datalist></label>
<label>المبلغ (₪)<input name=amount type=number step=any min=0 required inputmode=decimal></label><label>التاريخ<input name=date type=date value="{{today}}"></label><label class=fa>ملاحظة<input name=note></label></div></div>
<div class=df><button>حفظ الدفعة</button><button type=button class=ghost data-close>إلغاء</button></div></form></dialog>
<div class=card><table class=srt id=dtbl><tr><th>الشخص<th>إجمالي الدين<th>دفع نقداً<th>شيكات مصروفة<th>المتبقي<th>نسبة السداد<th class=ns></tr>
{% for r in rows %}<tr><td><a href=/people/{{r.id}} style="font-weight:800">{{r.name}}</a>{% if r.phone %}<br><small dir=ltr>{{r.phone}}</small>{% endif %}<td data-v={{r.debt}} class=nw>{{ '%g'|format(r.debt) }} ₪
<td class=nw>{{ '%g'|format(r.cash) }} ₪<td class=nw>{{ '%g'|format(r.chk_ok) }} ₪{% if r.chk_wait %}<br><small>+ {{ '%g'|format(r.chk_wait) }} ₪ لم تُصرف</small>{% endif %}
<td data-v={{r.rem}} class=nw>{% if r.rem > 0 %}<span class="amt up">{{ '%g'|format(r.rem) }} ₪</span>{% elif r.rem < 0 %}<span class="amt dn">له {{ '%g'|format(-r.rem) }} ₪</span>{% else %}<span class=tag>مسدّد</span>{% endif %}
<td data-v={{r.pct}} style="min-width:110px"><div class=pgb><i style="width:{{r.pct}}%;background:linear-gradient(90deg,#34d399,#059669)"></i></div><small>{{r.pct}}%</small>
<td><div class=sa><a class="ib" title="فتح الحساب" aria-label="فتح الحساب" href=/people/{{r.id}}>{{ic.eye}}</a></div></tr>
{% else %}<tr><td colspan=7 class=em>ما في ديون مسجّلة. اضغط "دين جديد".</tr>{% endfor %}</table></div>
<div class=card><div class=ch><h3>آخر السجلات</h3></div><div style="overflow-x:auto"><table><tr><th>التاريخ<th>الشخص<th>العملية<th>التفاصيل<th>المبلغ</tr>
{% for r in recent %}<tr><td class=nw>{{r.created}}<td><a href=/people/{{r.debtor_id}}><b>{{r.pname}}</b></a><td>{% if r.kind=='دين' %}<span class="pill s3">دين</span>{% else %}<span class="pill s2">دفعة</span>{% endif %}<td><small>{{ r.item or r.note or '' }}</small>
<td class=nw><span class="amt {{'up' if r.kind=='دين' else 'dn'}}">{{ '+' if r.kind=='دين' else '−' }}{{ '%g'|format(r.amount) }} ₪</span></tr>{% else %}<tr><td colspan=5 class=em>ما في سجلات.</tr>{% endfor %}</table></div></div>{% endblock %}"""

T["cheques"] = """{% extends 'base' %}{% block c %}
<div class="sg4"><div class=sc><span class="si e">{{ic.cp}}</span><div><small>لم تُصرف ({{sm.n_wait}})</small><b>{{ '%g'|format(sm.wait) }} ₪</b></div></div>
<div class=sc><span class="si d">{{ic.cp}}</span><div><small>مستحقة اليوم · متأخرة</small><b>{{sm.today}} · <span class=low>{{sm.late}}</span></b></div></div>
<div class=sc><span class="si c">{{ic.ck}}</span><div><small>صُرفت ({{sm.n_ok}})</small><b>{{ '%g'|format(sm.ok) }} ₪</b></div></div>
<div class=sc><span class="si a">✗</span><div><small>راجعة ({{sm.n_bad}})</small><b>{{ '%g'|format(sm.bad) }} ₪</b></div></div></div>
<div class=card><form method=get class=fg style="align-items:end"><label>بحث<input name=q value="{{qs}}" placeholder="رقم، صاحب الشيك، بنك، شخص"></label>
<label>الحالة<select name=status><option value="">الكل</option>{% for x in ['لم يُصرف','صُرف','راجع'] %}<option {{'selected' if x==st}}>{{x}}</option>{% endfor %}</select></label>
<label>من تاريخ<input type=date name=from value="{{d1}}"></label><label>إلى تاريخ<input type=date name=to value="{{d2}}"></label>
<p style="margin:0;grid-column:1/-1;display:flex;gap:8px;flex-wrap:wrap"><button>تصفية</button><a class="btn ghost" href=/cheques>مسح</a><span style="flex:1"></span><button type=button data-open=dlg-cnew>{{ic.pl}} شيك جديد</button></p></form></div>
<dialog class=dlg id=dlg-cnew><form method=post action=/cheques/add enctype=multipart/form-data><input type=hidden name=back value=/cheques><div class=dh><h3>شيك جديد</h3><button type=button class=cl data-close aria-label="إغلاق">×</button></div>
<div class=db>{% set show_person=true %}{% include 'chqfields' %}</div><div class=df><button>حفظ الشيك</button><button type=button class=ghost data-close>إلغاء</button></div></form></dialog>
<div class=card><div style="overflow-x:auto">{% set chs=rows %}{% set back='/cheques' %}<table><tr><th>صورة<th>رقم الشيك<th>صاحب الشيك<th>الشخص<th>البنك<th>المبلغ<th>تاريخه<th>الحالة<th></tr>
{% for c in rows %}<tr><td>{% if c.photo %}<a href=/chkphoto/{{c.photo}} target=_blank rel=noopener><img src=/chkphoto/{{c.photo}} alt="صورة الشيك" style="width:54px;height:40px;object-fit:cover;border-radius:8px;border:1px solid #dfe4f5"></a>{% else %}<small>—</small>{% endif %}
<td><b dir=ltr>{{c.number}}</b>{% if c.note %}<br><small>{{c.note}}</small>{% endif %}<td>{{c.drawer or '—'}}<td><a href=/people/{{c.person_id}}>{{c.pname or '—'}}</a><td>{{c.bank or '—'}}<td class=nw><b>{{ '%g'|format(c.amount) }} ₪</b>{% if not c.on_debt %}<br><small>خارج الدين</small>{% endif %}
<td class=nw>{{c.due or '—'}}{% if c.status=='لم يُصرف' and c.due %}{% if c.due < today %}<br><small class=low>متأخر</small>{% elif c.due == today %}<br><small class=low>مستحق اليوم</small>{% endif %}{% endif %}
<td><span class="pill {{ {'لم يُصرف':'s0','صُرف':'s2','راجع':'s3'}[c.status] }}">{{c.status}}</span>
<div class=sa style="margin-top:6px">{% if c.status!='صُرف' %}<form method=post action=/cheques/{{c.id}}/status class=il><input type=hidden name=back value="{{ request.full_path.rstrip('?') }}"><input type=hidden name=status value="صُرف"><button class=ghost style="padding:4px 10px;font-size:12.5px;margin:0">صُرف ✓</button></form>{% endif %}
{% if c.status=='لم يُصرف' %}<form method=post action=/cheques/{{c.id}}/status class=il><input type=hidden name=back value="{{ request.full_path.rstrip('?') }}"><input type=hidden name=status value="راجع"><button class=ghost style="padding:4px 10px;font-size:12.5px;margin:0">راجع ✗</button></form>{% endif %}
{% if c.status!='لم يُصرف' %}<form method=post action=/cheques/{{c.id}}/status class=il><input type=hidden name=back value="{{ request.full_path.rstrip('?') }}"><input type=hidden name=status value="لم يُصرف"><button class=ghost style="padding:4px 10px;font-size:12.5px;margin:0">لم يُصرف</button></form>{% endif %}</div>
<td class=nw><button type=button class="ib ed" title="تعديل" aria-label="تعديل" data-open=dlg-cedit data-fill='{{ {"number": c.number, "bank": c.bank or "", "amount": c.amount, "drawer": c.drawer or "", "due": c.due or "", "note": c.note or "", "_action": "/cheques/%d/edit"|format(c.id), "_on": c.on_debt}|tojson }}'>{{ic.ed}}</button>
<form method=post action=/cheques/{{c.id}}/delete class=il onsubmit="return confirm('حذف الشيك؟')"><input type=hidden name=back value=/cheques><button class="ib dl" title="حذف" aria-label="حذف">{{ic.dl}}</button></form></tr>
{% else %}<tr><td colspan=9 class=em>ما في شيكات.</tr>{% endfor %}</table></div></div>
{% include 'chqedit' %}{% endblock %}"""

T["rets"] = """{% extends 'base' %}{% block c %}
<div class="sg4"><div class=sc><span class="si d">{{ic.rt}}</span><div><small>عمليات الإرجاع</small><b>{{st.n}}</b></div></div>
<div class=sc><span class="si e">{{cic['أخرى']}}</span><div><small>إجمالي القطع المرتجعة</small><b>{{st.qty}}</b></div></div>
<div class=sc><span class="si a">{{ic.cd}}</span><div><small>قطع مرتجعة هالشهر</small><b>{{st.mqty}}</b></div></div>
<div class=sc><span class="si c">₪</span><div><small>قيمة المرتجعات (جملة)</small><b>{{ '%g'|format(st.val) }} ₪</b></div></div></div>
<div class=tools><div class=r1><label class=search>{{ic.sr}}<input data-f=rttbl data-role=search placeholder="بحث: قطعة، مورد، سبب..."></label><span class=sp></span><form method=post action=/invoices/new class=il><input type=hidden name=all value=1><input type=hidden name=kind value="مرتجع"><input type=hidden name=back value="/returns"><button class=ghost title="كل مرتجع بينتسب لمورده، وبينعمل فاتورة لكل مورد">إنشاء فواتير المرتجعات حسب المورد{% if st.open %} ({{st.open}}){% endif %}</button></form> <a class="btn ghost" href="/requirements?kind=مرتجع">المتطلبات والفواتير</a><button type=button data-open=dlg-ret>{{ic.pl}} تسجيل مرتجع</button></div></div>
<dialog class=dlg id=dlg-ret><form method=post><div class=dh><h3>تسجيل بضاعة مرتجعة</h3><button type=button class=cl data-close aria-label="إغلاق">×</button></div>
<div class=db>{% if parts %}<div class=fg><label class=fa>القطعة (من المخزن الرئيسي)<select name=part_id id=rp required>{% for p in parts %}<option value={{p.id}} data-cost="{{p.cost or 0}}" data-sup="{{p.supplier_id or ''}}">{{p.category}} · {{plabel(p)}} — متوفر {{p.qty}}</option>{% endfor %}</select></label>
<label>الكمية المرتجعة<input name=qty type=number min=1 value=1 required inputmode=numeric></label><label>سعر الوحدة (جملة ₪)<input name=unit_cost id=rc type=number step=any min=0 inputmode=decimal></label>
<label>المورد (بيتحدد تلقائياً من القطعة)<select name=supplier_id id=rs><option value="">— اختر المورد —</option>{% for s in sup %}<option value={{s.id}}>{{s.name}}</option>{% endfor %}</select></label><label>التاريخ<input name=date type=date value="{{today}}"></label>
<label class=fa>سبب الإرجاع<select name=reason>{% for r in reasons %}<option>{{r}}</option>{% endfor %}</select></label><label class=fa>ملاحظة<input name=note placeholder="اختياري"></label></div>
<p class=hint>الكمية بتنخصم فوراً من المخزن الرئيسي.</p>{% else %}<div class=em>ما في قطع متوفرة بالمخزن الرئيسي لترجيعها.</div>{% endif %}</div>
<div class=df>{% if parts %}<button>تسجيل وخصم من المخزن</button>{% endif %}<button type=button class=ghost data-close>إلغاء</button></div></form></dialog>
<div class=card><table class=srt id=rttbl><tr><th>التاريخ<th>القطعة<th>النوع<th>الكمية<th>المورد<th>السبب<th>القيمة<th>الفاتورة<th>الصورة<th class=ns></tr>
{% for r in rows %}<tr><td class=nw>{{r.created}}<td><b>{{r.part_name}}</b>{% if r.emp_name %}<br><span class="pill s3" style="font-size:12px">من الموظف: {{r.emp_name}}</span>{% endif %}{% if r.note %}<br><small>{{r.note}}</small>{% endif %}<td>{{r.category}}<td><span class="tag bad">{{r.qty}}</span><td>{{r.supplier_name or '—'}}<td>{{r.reason}}<td class=nw data-v={{r.total}}>{{ '%g'|format(r.total) }} ₪
<td>{% if r.ninv %}<a href=/invoices/{{r.ninv}} target=_blank>INV-{{'%04d'|format(r.ninv)}}</a>{% elif r.nid %}<span class="tag">بانتظار الفاتورة</span>{% else %}—{% endif %}
<td>{% if r.photo %}<a href=/rphoto/{{r.photo}} target=_blank><img src=/rphoto/{{r.photo}} alt="صورة المشكلة" style="width:54px;height:54px;object-fit:cover;border-radius:10px;border:1px solid var(--line)"></a>{% else %}—{% endif %}
<td><form method=post action=/returns/{{r.id}}/delete class=il onsubmit="return confirm('{{ 'حذف المرتجع؟ القطعة رح ترجع لعهدة الموظف.' if r.emp_log_id else 'حذف السجل؟ الكمية رح ترجع للمخزن الرئيسي.' }}')"><button class="ib dl" title="حذف وإرجاع الكمية للمخزن" aria-label="حذف">{{ic.dl}}</button></form></tr>
{% else %}<tr><td colspan=10 class=em>ما في مرتجعات مسجّلة.</tr>{% endfor %}</table></div>
<script>(function(){var p=document.getElementById('rp');if(!p)return;function sy(){var o=p.options[p.selectedIndex];if(!o)return;document.getElementById('rc').value=o.dataset.cost||0;document.getElementById('rs').value=o.dataset.sup||''}
p.addEventListener('change',sy);document.addEventListener('click',function(e){if(e.target.closest('[data-open=dlg-ret]'))setTimeout(sy,0)})})();</script>{% endblock %}"""

T["emphead"] = """<style>.emt{display:flex;align-items:center;gap:16px;flex-wrap:wrap;padding:14px 28px;background:radial-gradient(400px 160px at 0% 0%,#5b4ef066,transparent 70%),linear-gradient(135deg,#080d2b,#1b2380);color:#fff;box-shadow:0 20px 40px -24px #0c1233}.emt .sp{flex:1}.emu{text-align:right}.emu b{display:block}.emu small{color:#c4cbf3}
.emc{max-width:1060px;margin:0 auto;padding:28px 20px 50px}.emt .ghost{background:#ffffff1f!important;color:#fff!important;box-shadow:none!important}</style>
<header class=emt>{{logo}}<span class=sp></span><div class=emu><b>{{e.name}}</b><small>{{e.role or 'موظف'}}{% if shop %} · {{shop}}{% endif %}</small></div>{% if not forced %}<a class="btn ghost" href=/my>🏠 الرئيسية</a><a class="btn ghost" href=/my/customers>👥 زبائني</a><a class="btn ghost" href=/my/queue>📝 قائمة الانتظار</a><a class="btn ghost" href=/my/sales>{{ic.sl}} مبيعاتي</a><a class="btn ghost" href="/my?pay=1">💳 ترحيل دفعة</a><a class="btn ghost" target=_blank href=/my/statement>🧾 كشف بضاعتي</a><a class="btn ghost" href=/my/settings>{{ic.settings if ic.settings is defined else '⚙️'}} الإعدادات</a>{% endif %}<a class="btn ghost" href=/logout>تسجيل الخروج</a></header>
"""
T["empq"] = """{% extends 'base' %}{% block c %}{% include 'emphead' %}
<div class=emc><div class=ph><h2>📝 قائمة انتظار الزبائن</h2><p>سجّل اللي كل زبون طلبه ومو موجود معك الآن، عشان ما تنساه</p></div>
<div class=card><form method=post action=/my/queue/add class=fg style="align-items:end">
<label>الزبون (من زبائنك)<select name=customer_id><option value="">— اختر —</option>{% for c in custs %}<option value={{c.id}}>{{c.name}}{% if c.shop %} · {{c.shop}}{% endif %}</option>{% endfor %}</select></label>
<label>أو اكتب اسمه<input name=customer_name placeholder="زبون جديد أو عابر"></label>
<label>القطعة<select name=part_id><option value="">— قطعة أخرى (اكتبها تحت) —</option>{% for p in parts %}<option value={{p.id}}>{{p.label}}{% if p.held %} · بعهدتك {{p.held}}{% endif %}</option>{% endfor %}</select></label>
<label>تفاصيل / اسم القطعة<input name=item placeholder="مثلاً: شاشة سامسونج A12 أسود"></label>
<label>الكمية<input name=qty type=number min=1 value=1 inputmode=numeric></label>
<label class=fa>موصّى عليه / ملاحظة<input name=note placeholder="مثلاً: بده يجيبها الخميس، أو لازم أرجع أتصل فيه"></label>
<p style="margin:0;grid-column:1/-1"><button>➕ أضف للقائمة</button></p></form></div>
<p style="display:flex;gap:8px"><a class="btn {{ '' if s=='waiting' else 'ghost' }}" href=/my/queue>⏳ بالانتظار ({{nwait}})</a><a class="btn {{ '' if s=='done' else 'ghost' }}" href="/my/queue?s=done">✓ المنجزة</a></p>
<div class=card><div style="overflow-x:auto"><table><tr><th>الزبون<th>المطلوب<th>الكمية<th>ملاحظة<th>التاريخ<th>الحالة<th></tr>
{% for r in rows %}<tr><td><b>{{r.customer_name}}</b>{% if r.cshop %}<br><small>{{r.cshop}}</small>{% endif %}{% if r.cphone %}<br><a href="tel:{{r.cphone}}" dir=ltr><small>{{r.cphone}}</small></a> <a href="https://wa.me/{{ r.cphone|replace('+','')|replace(' ','')|replace('-','') }}" target=_blank rel=noopener title="واتساب">💬</a>{% endif %}
<td>{{r.item}}<td>{{r.qty}}<td><small>{{r.note or ''}}</small><td class=nw dir=ltr>{{r.created}}
<td>{% if s=='done' %}<span class="pill s2">تم {{ (r.done_at or '')[:10] }}</span>{% elif r.held is none %}<small>—</small>{% else %}<span class="pill {{ 's2' if r.ready else 's3' }}">{{ 'جاهز بعهدتك' if r.ready else 'ناقص — بعهدتك ' ~ r.held }}</span>{% endif %}
<td class=nw>{% if s=='done' %}<form method=post action=/my/queue/{{r.id}}/undo class=il><button class=ghost style="padding:6px 10px;font-size:13px">↩ رجّع</button></form>{% else %}<form method=post action=/my/queue/{{r.id}}/done class=il><button style="padding:6px 10px;font-size:13px">✓ تم</button></form>{% endif %}
<form method=post action=/my/queue/{{r.id}}/delete class=il onsubmit="return confirm('حذف الطلب؟')"><button class="ib dl" title="حذف" aria-label="حذف">{{ic.dl}}</button></form></tr>
{% else %}<tr><td colspan=7 class=em>{{ 'ما في طلبات بالانتظار 🎉' if s=='waiting' else 'ما في طلبات منجزة بعد.' }}</tr>{% endfor %}</table></div></div>
<p><a class="btn ghost" href=/my>{{ic.bk}} رجوع لصفحتي</a></p></div>{% endblock %}"""


T["empme"] = """{% extends 'base' %}{% block c %}
{% include 'emphead' %}
<div class=emc><div class=ph><h2>أهلاً {{e.name}} 👋</h2><p>هاي بضاعتك اللي بعهدتك وكل حركاتها</p></div>
<div class="sg4"><div class=sc><span class="si b">{{cic['أخرى']}}</span><div><small>قطع بعهدتك الآن</small><b>{{tot.nq}}</b></div></div><div class=sc><span class="si c">₪</span><div><small>قيمة البيع المتوقعة</small><b>{{ '%g'|format(tot.val) }} ₪</b></div></div><div class=sc><span class="si e">{{ic.sl}}</span><div><small>مبيعاتك (المجموع)</small><b>{{ '%g'|format(sales) }} ₪</b></div></div>
<div class=sc><span class="si c">₪</span><div><small>صافي ربحك</small><b>{{ '%g'|format(net) }} ₪</b></div></div>
<div class=sc><span class="si d">₪</span><div><small>متبقي عند زبائنك</small><b>{{ '%g'|format(owed) }} ₪</b></div></div></div>
{% if nlow %}<div class=err role=alert style="margin-bottom:14px">⚠️ عندك {{nlow}} قطعة مخزونها منخفض أو خلص: {% for h in H if h.low %}<b>{{h.pname}}</b> ({{h.held}}){{ '، ' if not loop.last }}{% endfor %}</div>{% endif %}
<div class=card><div class=ch><h3>📝 زبائن بانتظارك ({{qn}})</h3><a href=/my/queue style="font-size:14px">كل القائمة وإضافة طلب</a></div>
{% for w in qtop %}<div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:10px 18px;border-top:1px solid #edf0fb"><div style="flex:1;min-width:200px"><b>{{w.customer_name}}</b> — {{w.qty}} × {{w.item}}{% if w.note %}<br><small>📌 {{w.note}}</small>{% endif %}</div>{% if w.held is not none %}<span class="pill {{ 's2' if w.ready else 's3' }}">{{ 'جاهز بعهدتك' if w.ready else 'ناقص — بعهدتك ' ~ w.held }}</span>{% endif %}<form method=post action=/my/queue/{{w.id}}/done class=il><button style="padding:6px 12px;font-size:13px">✓ تم</button></form></div>
{% else %}<div class=em style="padding:14px 18px">ما في زبائن بالانتظار. 🎉</div>{% endfor %}</div>
<div class=card id=mypay><div class=ch><h3>💼 حسابك مع الشركة</h3><button type=button onclick="document.getElementById('dlg-mypay').showModal()" {{ 'disabled' if acc.left<=0 }}>💳 ترحيل دفعة</button></div><div class=sg4 style="padding:0 18px 14px"><div class=sc><span class="si b">₪</span><div><small>بضاعة استلمتها (بسعرك)</small><b>{{ '%g'|format(acc.goods) }} ₪</b></div></div><div class=sc><span class="si c">₪</span><div><small>دفعت للشركة</small><b>{{ '%g'|format(acc.paid) }} ₪</b></div></div><div class=sc><span class="si d">₪</span><div><small>المتبقي عليك</small><b style="color:{{ '#e11d48' if acc.left>0 else '#059669' }}">{{ '%g'|format(acc.left) }} ₪</b></div></div></div>
{% if mypays %}<div style="overflow-x:auto"><table><tr><th>التاريخ<th>المبلغ<th>الطريقة<th>الوصل<th>ملاحظة</tr>{% for p in mypays %}<tr><td class=nw dir=ltr>{{p.created}}<td class=nw><b style="color:#059669">{{ '%g'|format(p.amount) }} ₪</b><td><span class=tag>{{ 'تحويل بنكي' if p.method=='بنك' else 'نقداً' }}</span><td>{% if p.receipt %}<a href=/payreceipt/{{p.receipt}} target=_blank>🧾 عرض الوصل</a>{% else %}<small>—</small>{% endif %}<td><small>{{p.note or ''}}</small></tr>{% endfor %}</table></div>{% endif %}</div>
<dialog class=dlg id=dlg-mypay><form method=post action=/my/pay enctype=multipart/form-data onsubmit="if(this.pm.value==='بنك'&&!this.receipt.files.length){alert('أرفق صورة وصل التحويل');return false}"><div class=dh><h3>💳 ترحيل دفعة للشركة</h3><button type=button class=cl data-close aria-label="إغلاق">×</button></div>
<div class=db><p style="margin:0 0 10px">المتبقي عليك: <b style="color:#e11d48">{{ '%g'|format(acc.left) }} ₪</b></p><div class=fg><label>المبلغ (₪)<input name=amount type=number step=any min=0.01 max="{{acc.left}}" value="{{acc.left}}" required inputmode=decimal></label>
<label>طريقة الدفع<select name=pm><option value=نقد>💵 نقداً (كاش)<option value=بنك>🏦 تحويل بنكي</select></label>
<label class=fa>صورة الوصل (إلزامية مع التحويل البنكي)<input type=file name=receipt accept="image/*,application/pdf" capture=environment></label>
<label class=fa>ملاحظة (اختياري)<input name=note></label></div></div>
<div class=df><button>ترحيل الدفعة</button><button type=button class=ghost data-close>إلغاء</button></div></form></dialog>
{% if open_pay and acc.left>0 %}<script>document.getElementById('dlg-mypay').showModal()</script>{% endif %}
<div class=card><div class=ch><h3>بضاعتك الآن</h3></div><div style="padding:0 18px 4px"><label class=search style="display:flex;margin:6px 0 10px">{{ic.sr}}<input data-tsearch=mytbl placeholder="🔍 ابحث في البضاعة (اسم القطعة، اللون...)" autocomplete=off></label><small class=hint data-tcount=mytbl></small></div><div style="overflow-x:auto"><table id=mytbl><tr><th>القطعة<th>الكمية<th>سعرك (جملة)<th>سعر البيع المقترح<th>القيمة<th></tr>
{% for h in H %}<tr><td><b>{{h.pname}}</b><td><span class=tag>{{h.held}}</span>{% if h.low %} <span class="pill s3">منخفض</span>{% endif %}<td>{{ '%g'|format(h.cost) }} ₪<td>{{ '%g'|format(h.price) }} ₪<td class=nw>{{ '%g'|format(h.held*h.price) }} ₪
<td class=nw><button type=button class=sellbtn data-i='{{ {"id": h.part_id, "name": h.pname, "held": h.held, "cost": h.cost, "price": h.price}|tojson }}' title="بيع" aria-label="بيع" style="padding:6px 12px;font-size:13px">{{ic.sl}} بيع</button>
<button type=button class="ghost retbtn" data-i='{{ {"id": h.part_id, "name": h.pname, "held": h.held}|tojson }}' title="مرتجع" aria-label="مرتجع" style="padding:6px 12px;font-size:13px">{{ic.rt}} مرتجع</button></tr>
{% else %}<tr><td colspan=6 class=em>ما في بضاعة بعهدتك حالياً.</tr>{% endfor %}</table></div></div>
<dialog class=dlg id=dlg-sell><form method=post action=/my/sell><input type=hidden name=part_id id=s_id><div class=dh><h3>بيع قطعة</h3><button type=button class=cl data-close aria-label="إغلاق">×</button></div>
<div class=db><p style="margin:0 0 10px"><b id=s_name></b> <small>· بعهدتك <span id=s_held></span></small></p>
<div class=fg><label>سعر الجملة (₪)<input id=s_cost disabled></label><label>سعر البيع للقطعة (₪)<input name=price id=s_price type=number step=any min=0 required inputmode=decimal></label>
<label>الكمية<input name=qty id=s_qty type=number min=1 value=1 required inputmode=numeric></label><label>المجموع (₪)<input id=s_tot disabled></label>
<label>المدفوع الآن (₪)<input name=paid id=s_paid type=number step=any min=0 inputmode=decimal></label><label>المتبقي على الزبون<input id=s_left disabled></label>
<label class=fa>الزبون (مطلوب)<span style="position:relative;display:block"><input id=s_cq autocomplete=off placeholder="اكتب للبحث أو اضغط لاختيار الزبون ▾" style="padding-inline-start:12px"></span>
<input type=hidden name=customer_id id=s_cust><div id=s_list role=listbox style="display:none;max-height:190px;overflow:auto;margin-top:6px;border:1.5px solid #cfd6f3;border-radius:14px;background:#fff"></div></label>
<script type=application/json id=custdata>{{ custs_json|safe }}</script>
<label class=fa>ملاحظة (اختياري)<input name=note placeholder="أي ملاحظة على البيع"></label></div>
<p class=hint>مش لاقي الزبون؟ <a href=/my/customers>أضفه من صفحة زبائني</a> وارجع.</p>
<p class=hint id=s_profit></p></div><div class=df><button>تأكيد البيع</button><button type=button class=ghost data-close>إلغاء</button></div></form></dialog>
<dialog class=dlg id=dlg-ret><form method=post action=/my/return enctype=multipart/form-data><input type=hidden name=part_id id=r_id><div class=dh><h3>إرجاع قطعة لصاحب الشركة</h3><button type=button class=cl data-close aria-label="إغلاق">×</button></div>
<div class=db><p style="margin:0 0 10px"><b id=r_name></b> <small>· بعهدتك <span id=r_held></span></small></p>
<div class=fg><label>الكمية<input name=qty id=r_qty type=number min=1 value=1 required inputmode=numeric></label>
<label>سبب الإرجاع<select name=reason>{% for r in reasons %}<option>{{r}}</option>{% endfor %}</select></label>
<label class=fa>صورة المشكلة<input name=photo type=file accept="image/*" capture=environment></label>
<label class=fa>ملاحظة<input name=note placeholder="اشرح المشكلة"></label></div>
<p class=hint>لازم ترفق صورة أو تكتب ملاحظة (أو الاثنين). المرتجع بيوصل مباشرة لصفحة المرتجعات عند صاحب الشركة.</p></div>
<div class=df><button>إرسال المرتجع</button><button type=button class=ghost data-close>إلغاء</button></div></form></dialog>
<script>(function(){var $=function(i){return document.getElementById(i)},cur=null,pe=false;
function calc(){if(!cur)return;var q=+$('s_qty').value||0,p=+$('s_price').value||0;var T=Math.round(q*p*100)/100;$('s_tot').value=T+' ₪';if(!pe)$('s_paid').value=T;$('s_left').value=Math.max(Math.round((T-(+$('s_paid').value||0))*100)/100,0)+' ₪';var pr=(p-cur.cost)*q;$('s_profit').textContent='الربح المتوقع: '+(Math.round(pr*100)/100)+' ₪'}
document.addEventListener('click',function(e){var b=e.target.closest('.sellbtn');if(b){cur=JSON.parse(b.dataset.i);$('s_id').value=cur.id;$('s_name').textContent=cur.name;$('s_held').textContent=cur.held;$('s_cost').value=cur.cost+' ₪';$('s_price').value=cur.price;$('s_qty').value=1;$('s_qty').max=cur.held;pe=false;calc();$('dlg-sell').showModal();return}
b=e.target.closest('.retbtn');if(b){var d=JSON.parse(b.dataset.i);$('r_id').value=d.id;$('r_name').textContent=d.name;$('r_held').textContent=d.held;$('r_qty').value=1;$('r_qty').max=d.held;$('dlg-ret').showModal()}});
$('s_qty').addEventListener('input',calc);$('s_price').addEventListener('input',calc);$('s_paid').addEventListener('input',function(){pe=true;calc()})})();
(function(){var C=[];try{C=JSON.parse(document.getElementById('custdata').textContent)}catch(e){}
var hid=document.getElementById('s_cust'),inp=document.getElementById('s_cq'),box=document.getElementById('s_list');if(!hid)return;
function norm(x){return (x||'').toLowerCase().replace(/[\u064B-\u065F]/g,'').replace(/[أإآ]/g,'ا').replace(/ى/g,'ي').replace(/ة/g,'ه')}
function pick(c){hid.value=c.id;inp.value=c.name+(c.shop?' · '+c.shop:'');inp.setCustomValidity('');box.style.display='none'}
function render(all){var v=all?'':norm(inp.value.trim()),n=0;box.innerHTML='';
C.forEach(function(c){if(v&&norm(c.name+' '+c.shop+' '+c.phone+' '+c.location).indexOf(v)<0)return;n++;var d=document.createElement('div');d.setAttribute('role','option');d.style.cssText='padding:9px 12px;border-bottom:1px solid #eef1fb;cursor:pointer;line-height:1.5';
var b=document.createElement('b');b.textContent=c.name;d.appendChild(b);var sm=document.createElement('small');sm.style.cssText='display:block;color:#6a74a8';sm.textContent=[c.shop,c.phone].filter(Boolean).join(' · ');d.appendChild(sm);
d.addEventListener('mousedown',function(e){e.preventDefault();pick(c)});d.addEventListener('touchstart',function(){d._t=1},{passive:true});box.appendChild(d)});
if(!n){var e=document.createElement('div');e.style.cssText='padding:12px;color:#6a74a8';e.textContent=C.length?'ما في نتائج':'ما عندك زبائن، أضف زبون من صفحة زبائني';box.appendChild(e)}
box.style.display='block';return n}
inp.addEventListener('focus',function(){render(!hid.value||true)});
inp.addEventListener('click',function(){if(box.style.display==='none')render(true)});
inp.addEventListener('input',function(){hid.value='';inp.setCustomValidity('اختر الزبون من القائمة');var n=render(false);if(n===1&&norm(inp.value.trim()).length>1){}});
inp.addEventListener('keydown',function(e){if(e.key==='Enter'){var f=box.querySelector('[role=option]');if(f&&!hid.value){e.preventDefault();f.dispatchEvent(new MouseEvent('mousedown'))}}});
inp.addEventListener('blur',function(){setTimeout(function(){box.style.display='none'},150)});
inp.form.addEventListener('submit',function(e){if(!hid.value){e.preventDefault();inp.setCustomValidity('اختر الزبون من القائمة');inp.reportValidity();render(true)}});
document.addEventListener('click',function(e){if(e.target.closest('.sellbtn')){hid.value='';inp.value='';inp.setCustomValidity('');box.style.display='none'}})})();</script>
<div class=card><div class=ch><h3>المتوفر بالشركة</h3><small>ابحث عن أي قطعة وشوف إذا موجودة وكم عددها</small></div>
<div style="padding:0 18px 14px"><label class=search style="display:flex;margin:6px 0 12px">{{ic.sr}}<input id=asearch placeholder="ابحث عن قطعة (مثلاً: شاشة ايفون 11)" autocomplete=off></label>
<div id=alist style="max-height:52vh;overflow:auto;border:1px solid var(--line);border-radius:14px">
{% for a in avail %}{% if loop.first or avail[loop.index0-1].cat != a.cat %}<div data-cat style="position:sticky;top:0;background:#eef1fb;padding:6px 14px;font-weight:800;font-size:13px;color:#33407a">{{a.cat}}</div>{% endif %}
<div class=arow data-t="{{a.cat}} {{a.name}}" style="display:flex;align-items:center;gap:10px;padding:9px 14px;border-bottom:1px solid var(--line)"><b style="flex:1">{{a.name}}</b>{% if a.mine %}<small style="color:var(--mut)">بعهدتك</small>{% endif %}<span class="pill {{ 's2' if a.ok else 's3' }}">{{ ('موجود · ' ~ a.qty) if a.ok else 'غير موجود' }}</span></div>
{% else %}<div class=em style="padding:16px">ما في قطع مسجلة بالشركة.</div>{% endfor %}<div id=anone class=em style="padding:16px;display:none">ما في نتائج للبحث.</div></div></div></div>
<script>(function(){var i=document.getElementById('asearch'),l=document.getElementById('alist');if(!i)return;i.addEventListener('input',function(){var v=this.value.trim().toLowerCase(),n=0;
l.querySelectorAll('.arow').forEach(function(r){var ok=(r.dataset.t||'').toLowerCase().indexOf(v)>-1;r.style.display=ok?'flex':'none';if(ok)n++});
l.querySelectorAll('[data-cat]').forEach(function(h){var x=h.nextElementSibling,any=false;while(x&&x.hasAttribute&&!x.hasAttribute('data-cat')&&x.id!=='anone'){if(x.style.display!=='none')any=true;x=x.nextElementSibling}h.style.display=any?'':'none'});
document.getElementById('anone').style.display=n?'none':'block'})})();</script>
<div class=card><div class=ch><h3>سجل الحركات</h3></div><table><tr><th>التاريخ<th>القطعة<th>العملية<th>الكمية<th>ملاحظة</tr>
{% for l in log %}<tr><td class=nw>{{l.created}}<td><b>{{l.part_name}}</b><td><span class="pill {{ {'تسليم':'s1','إرجاع':'s2','استهلاك':'s0','بيع':'s2','مرتجع':'s3'}.get(l.kind,'s0') }}">{{l.kind}}</span><td>{{l.qty}}<td>{{l.note}}</tr>{% else %}<tr><td colspan=5 class=em>ما في حركات بعد.</tr>{% endfor %}</table></div></div>{% endblock %}"""

T["empset"] = """{% extends 'base' %}{% block c %}{% include 'emphead' %}
<div class=emc><div class=ph><h2>⚙️ إعداداتي</h2><p>حسابك: <b dir=ltr>{{e.login}}</b></p></div>
{% if forced %}<div class=err role=alert style="padding:14px 16px;font-size:15px;line-height:1.9"><b>🔒 لازم تغيّر كلمة السر أول.</b><br>كلمة السر الحالية مؤقتة ولّدها المدير لك. اكتبها بخانة "كلمة السر الحالية" واختر كلمة سر جديدة خاصة فيك، وبعدها بتقدر تفتح صفحتك.</div>{% endif %}
<div class=card style="max-width:560px"><h3>تغيير كلمة السر</h3>
{% if pw_err %}<div class=err role=alert>{{pw_err}}</div>{% endif %}{% if pw_ok %}<div class=okb>تم تغيير كلمة السر بنجاح.</div>{% endif %}
<form method=post action=/my/settings/password><div class=fg>
<label class=fa>كلمة السر الحالية<input name=old type=password required autocomplete=current-password></label>
<label class=fa>كلمة السر الجديدة (6 أحرف على الأقل)<input name=new type=password minlength=6 required autocomplete=new-password></label>
<label class=fa>تأكيد كلمة السر الجديدة<input name=new2 type=password minlength=6 required autocomplete=new-password></label></div>
<p><button>تغيير كلمة السر</button>{% if not forced %} <a class="btn ghost" href=/my>رجوع</a>{% endif %}</p></form></div></div>{% endblock %}"""

T["empsales"] = """{% extends 'base' %}{% block c %}{% include 'emphead' %}
<div class=emc><div class=ph><h2>🧾 مبيعاتي</h2><p>كل القطع اللي بعتها، مع التصفية والفرز</p></div>
<div class=card><form method=get class=fg style="align-items:end">
<label>من تاريخ<input type=date name=from value="{{d1}}"></label><label>إلى تاريخ<input type=date name=to value="{{d2}}"></label>
<label>بحث باسم القطعة<input name=q value="{{qs}}" placeholder="مثلاً: شاشة"></label>
<label>الزبون<select name=cust><option value="">الكل</option>{% for c in custs %}<option value={{c.id}} {{'selected' if c.id==cid}}>{{c.name}}</option>{% endfor %}</select></label>
<label>الفرز<select name=sort>{% for k,v in sorts.items() %}<option value={{k}} {{'selected' if k==sort}}>{{v[0]}}</option>{% endfor %}</select></label>
<p style="margin:0;grid-column:1/-1;display:flex;gap:8px;flex-wrap:wrap;align-items:center"><button>تصفية</button><a class="btn ghost" href=/my/sales>مسح</a><span style="flex:1"></span>
{% for l,a,b in quick %}<a class="btn ghost" href="/my/sales?from={{a}}&to={{b}}&sort={{sort}}">{{l}}</a>{% endfor %}</p></form></div>
<div class=sg4><div class=sc><span class="si a">#</span><div><small>عدد العمليات</small><b>{{n}}</b></div></div>
<div class=sc><span class="si b">{{ic.sl}}</span><div><small>عدد القطع</small><b>{{pcs}}</b></div></div>
<div class=sc><span class="si c">₪</span><div><small>مجموع المبيعات</small><b>{{ '%g'|format(tot) }} ₪</b></div></div>
<div class=sc><span class="si d">₪</span><div><small>مجموع الجملة</small><b>{{ '%g'|format(wtot) }} ₪</b></div></div>
<div class=sc><span class="si e">₪</span><div><small>صافي الربح</small><b>{{ '%g'|format(profit) }} ₪</b></div></div></div>
<div class=card><div style="overflow-x:auto"><table><tr><th>التاريخ<th>القطعة<th>الزبون<th>الكمية<th>سعر الجملة<th>سعر البيع<th>المجموع<th>الدفع<th>صافي الربح<th>ملاحظة</tr>
{% for r in rows %}<tr><td class=nw dir=ltr>{{r.created}}<td><b>{{r.part_name}}</b><td>{% if r.customer_name %}<b>{{r.customer_name}}</b>{% if r.cphone %}<br><a href="tel:{{r.cphone}}" dir=ltr><small>{{r.cphone}}</small></a>{% endif %}{% if r.cloc %}<br><a href="{{r.cloc|maplink}}" target=_blank rel=noopener><small>📍 الموقع</small></a>{% endif %}{% else %}<small>—</small>{% endif %}<td>{{r.qty}}<td class=nw>{{ '%g'|format(r.cost or 0) }} ₪<td class=nw>{{ '%g'|format(r.unit_price or 0) }} ₪<td class=nw><b>{{ '%g'|format(r.total or 0) }} ₪</b><td class=nw>{% if r.st=='paid' %}<span class="pill s2">مدفوع</span>{% elif r.st=='part' %}<span class="pill s1">دفع {{ '%g'|format(r.paid_part) }} · باقي {{ '%g'|format(r.left) }} ₪</span>{% elif r.st=='unpaid' %}<span class="pill s3">غير مدفوع · {{ '%g'|format(r.left) }} ₪</span>{% else %}<small>—</small>{% endif %}<td class=nw><b style="color:{{ '#059669' if (r.profit or 0)>=0 else '#e11d48' }}">{{ '%g'|format(r.profit or 0) }} ₪</b><td><small>{{ (r.note or '').split(' · ',2)[2] if (r.note or '').count(' · ')>=2 else '' }}</small></tr>
{% else %}<tr><td colspan=10 class=em>{{ 'ما في مبيعات بهالتصفية.' if filtered else 'ما سجّلت أي مبيعات لسا.' }}</tr>{% endfor %}</table></div></div>
<p><a class="btn ghost" href=/my>{{ic.bk}} رجوع لصفحتي</a></p></div>{% endblock %}"""

T["empcust"] = """{% extends 'base' %}{% block c %}{% include 'emphead' %}
<div class=emc><div class=ph><h2>👥 زبائني</h2><p>كل زبون له اسمه ومحله وموقعه ورقمه، وكل قطعة بتبيعها بتتسجل باسمه</p></div>
<div class=card><form method=get class=fg style="align-items:end"><label class=fa>بحث<input name=q value="{{qs}}" placeholder="اسم الزبون أو المحل أو الهاتف"></label>
<p style="margin:0;grid-column:1/-1;display:flex;gap:8px;flex-wrap:wrap"><button>بحث</button><a class="btn ghost" href=/my/customers>مسح</a><span style="flex:1"></span><button type=button data-open=dlg-cadd>➕ زبون جديد</button></p></form></div>
<div class=card><div style="overflow-x:auto"><table><tr><th>الزبون<th>المحل<th>الهاتف<th>الموقع<th>عدد المشتريات<th>مجموعها<th>المدفوع<th>المتبقي<th></tr>
{% for c in rows %}<tr><td><b>{{c.name}}</b><td>{{c.shop or '—'}}<td class=nw><a href="tel:{{c.phone}}" dir=ltr>{{c.phone}}</a> <a href="https://wa.me/{{ c.phone|replace('+','')|replace(' ','')|replace('-','') }}" target=_blank rel=noopener title="واتساب">💬</a>
<td>{% if c.location %}<a href="{{c.location|maplink}}" target=_blank rel=noopener>📍 {{ c.location if not c.location.startswith('http') else 'فتح الخريطة' }}</a>{% else %}—{% endif %}
<td>{{c.ns}}<td class=nw>{{ '%g'|format(c.tot) }} ₪<td class=nw style="color:#059669;font-weight:700">{{ '%g'|format(c.paid) }} ₪<td class=nw>{% if c.left>0 %}<b style="color:#e11d48">{{ '%g'|format(c.left) }} ₪</b>{% elif c.trk>0 %}<span class="pill s2">مسدّد</span>{% else %}—{% endif %}
<td class=nw>{% if c.left>0 %}<button type=button class="paybtn" data-act="/my/customers/{{c.id}}/pay" data-name="{{c.name}}" data-left="{{c.left}}" style="padding:6px 10px;font-size:13px">💵 دفعة</button> {% endif %}<a class="btn ghost" href="/my/sales?cust={{c.id}}" style="padding:6px 10px;font-size:13px">مشترياته</a>
<button type=button class="ib ed" title="تعديل" aria-label="تعديل" data-open=dlg-cedit data-fill='{{ {"name": c.name, "shop": c.shop or "", "location": c.location or "", "phone": c.phone or "", "_action": "/my/customers/%d/edit" % c.id}|tojson }}'>{{ic.ed}}</button>
<form method=post action=/my/customers/{{c.id}}/delete class=il onsubmit="return confirm('حذف الزبون؟')"><button class="ib dl" title="حذف" aria-label="حذف">{{ic.dl}}</button></form></tr>
{% else %}<tr><td colspan=9 class=em>{{ 'ما في نتائج.' if qs else 'ما أضفت أي زبون لسا. اضغط "زبون جديد".' }}</tr>{% endfor %}</table></div></div>
<p class=hint>المدفوع والمتبقي بيحسبوا من المبيعات اللي انسجلت بعد تفعيل نظام الدفعات.</p>{% include 'paydlg' %}
<dialog class=dlg id=dlg-cadd><form method=post action=/my/customers/add><div class=dh><h3>زبون جديد</h3><button type=button class=cl data-close aria-label="إغلاق">×</button></div>
<div class=db><div class=fg><label>اسم الزبون<input name=name required></label><label>رقم الهاتف<input name=phone type=tel dir=ltr required inputmode=tel></label>
<label class=fa>اسم المحل<input name=shop placeholder="مثلاً: محل الأمين للاتصالات"></label>
<label class=fa>موقع المحل (عنوان أو رابط خريطة)<input name=location placeholder="مثلاً: نابلس - شارع رفيديا، أو رابط Google Maps"></label></div></div>
<div class=df><button>حفظ</button><button type=button class=ghost data-close>إلغاء</button></div></form></dialog>
<dialog class=dlg id=dlg-cedit><form method=post id=cedit-f action=/my/customers/0/edit><div class=dh><h3>تعديل بيانات الزبون</h3><button type=button class=cl data-close aria-label="إغلاق">×</button></div>
<div class=db><div class=fg><label>اسم الزبون<input name=name required></label><label>رقم الهاتف<input name=phone type=tel dir=ltr required inputmode=tel></label>
<label class=fa>اسم المحل<input name=shop></label><label class=fa>موقع المحل (عنوان أو رابط خريطة)<input name=location></label></div></div>
<div class=df><button>حفظ</button><button type=button class=ghost data-close>إلغاء</button></div></form></dialog>
<script>document.addEventListener('click',function(e){var b=e.target.closest('[data-open=dlg-cedit]');if(b&&b.dataset.fill){try{document.getElementById('cedit-f').action=JSON.parse(b.dataset.fill)._action}catch(x){}}});</script>
<p><a class="btn ghost" href=/my>{{ic.bk}} رجوع لصفحتي</a></p></div>{% endblock %}"""

T["empreport"] = """{% extends 'base' %}{% block c %}
<div class="card ehd" style="--h:{{(e.id*67)%360}}"><div class=av>{{e.name[:1]}}</div><div class=en><b>{{e.name}}</b><small>{{e.role or 'موظف'}}{% if e.phone %} · {{e.phone}}{% endif %}</small></div><span class=sp></span>
<a class="btn ghost" href=/employees/{{e.id}}>{{ic.bk}} عهدة الموظف</a><a class="btn ghost" href=/employees>كل الموظفين</a></div>
<div class=card><form method=get class=fg style="align-items:end"><label>من تاريخ<input type=date name=from value="{{d1}}"></label><label>إلى تاريخ<input type=date name=to value="{{d2}}"></label>
<p style="margin:0;display:flex;gap:8px;flex-wrap:wrap;align-items:center"><button>تصفية</button><a class="btn ghost" href=/employees/{{e.id}}/report>الكل</a>{% for l,a,b in quick %}<a class="btn ghost" href="/employees/{{e.id}}/report?from={{a}}&to={{b}}">{{l}}</a>{% endfor %}</p></form></div>
<div class="sg4"><div class=sc><span class="si a">#</span><div><small>عدد عمليات البيع</small><b>{{sm.n}} · {{sm.pcs}} قطعة</b></div></div>
<div class=sc><span class="si c">₪</span><div><small>مجموع المبيعات</small><b>{{ '%g'|format(sm.tot) }} ₪</b></div></div>
<div class=sc><span class="si d">₪</span><div><small>مجموع الجملة</small><b>{{ '%g'|format(sm.w) }} ₪</b></div></div>
<div class=sc><span class="si e">₪</span><div><small>صافي الربح</small><b>{{ '%g'|format(sm.pr) }} ₪</b></div></div>
<div class=sc><span class="si c">₪</span><div><small>مدفوع من زبائنه</small><b>{{ '%g'|format(got) }} ₪</b></div></div>
<div class=sc><span class="si d">₪</span><div><small>متبقي عند زبائنه</small><b>{{ '%g'|format(owed) }} ₪</b></div></div></div>
{% if low %}<div class=err role=alert style="margin-bottom:14px">⚠️ مخزون منخفض عند {{e.name}}: {% for h in low %}<b>{{h.pname}}</b> (باقي {{h.held}}){{ '، ' if not loop.last }}{% endfor %}</div>{% endif %}
<div class=card><div class=ch><h3>🧾 مبيعات الموظف</h3></div><div style="overflow-x:auto"><table><tr><th>التاريخ<th>القطعة<th>الزبون<th>الكمية<th>الجملة<th>البيع<th>المجموع<th>الدفع<th>صافي الربح</tr>
{% for r in sales %}<tr><td class=nw dir=ltr>{{r.created}}<td><b>{{r.part_name}}</b><td>{{r.customer_name or '—'}}{% if r.cphone %}<br><small dir=ltr>{{r.cphone}}</small>{% endif %}<td>{{r.qty}}<td class=nw>{{ '%g'|format(r.cost or 0) }} ₪<td class=nw>{{ '%g'|format(r.unit_price or 0) }} ₪<td class=nw><b>{{ '%g'|format(r.total or 0) }} ₪</b><td class=nw>{% if r.st=='paid' %}<span class="pill s2">مدفوع</span>{% elif r.st=='part' %}<span class="pill s1">دفع {{ '%g'|format(r.paid_part) }} · باقي {{ '%g'|format(r.left) }} ₪</span>{% elif r.st=='unpaid' %}<span class="pill s3">غير مدفوع · {{ '%g'|format(r.left) }} ₪</span>{% else %}<small>—</small>{% endif %}<td class=nw><b style="color:{{ '#059669' if (r.profit or 0)>=0 else '#e11d48' }}">{{ '%g'|format(r.profit or 0) }} ₪</b></tr>
{% else %}<tr><td colspan=9 class=em>ما في مبيعات.</tr>{% endfor %}</table></div></div>
<div class=card><div class=ch><h3>📦 مخزون الموظف (بعهدته)</h3></div><div style="padding:0 18px 4px"><label class=search style="display:flex;margin:6px 0 10px">{{ic.sr}}<input data-tsearch=rptbl placeholder="🔍 ابحث في البضاعة (اسم القطعة، اللون...)" autocomplete=off></label><small class=hint data-tcount=rptbl></small></div><div style="overflow-x:auto"><table id=rptbl><tr><th>القطعة<th>الكمية<th>الحالة<th>الجملة<th>سعر البيع<th>القيمة</tr>
{% for h in H %}<tr><td><b>{{h.pname}}</b><td><span class=tag>{{h.held}}</span><td><span class="pill {{ 's3' if h.low else 's2' }}">{{ 'منخفض' if h.low else 'متوفر' }}</span><td>{{ '%g'|format(h.cost) }} ₪<td>{{ '%g'|format(h.price) }} ₪<td class=nw>{{ '%g'|format(h.held*h.price) }} ₪</tr>
{% else %}<tr><td colspan=6 class=em>ما في بضاعة بعهدته.</tr>{% endfor %}</table></div></div>
<div class=card><div class=ch><h3>🏬 القطع المتوفرة بالشركة</h3><small>منخفضة المخزون بتظهر أول</small></div><div style="overflow-x:auto;max-height:50vh"><table><tr><th>القطعة<th>بالشركة<th>الحالة<th>عند الموظف</tr>
{% for p in shop_parts|sort(attribute='low', reverse=true) %}<tr><td><b>{{p.label}}</b><td>{{p.qty}}<td><span class="pill {{ 's3' if p.qty<=0 else ('s1' if p.low else 's2') }}">{{ 'نفدت' if p.qty<=0 else ('منخفض' if p.low else 'متوفر') }}</span><td>{{p.mine or '—'}}</tr>
{% else %}<tr><td colspan=4 class=em>ما في قطع.</tr>{% endfor %}</table></div></div>
<div class=card><div class=ch><h3>👥 زبائن الموظف</h3></div><div style="overflow-x:auto"><table><tr><th>الزبون<th>المحل<th>الهاتف<th>الموقع<th>المشتريات<th>المجموع<th>المدفوع<th>المتبقي<th></tr>
{% for c in custs %}<tr><td><b>{{c.name}}</b><td>{{c.shop or '—'}}<td class=nw><a href="tel:{{c.phone}}" dir=ltr>{{c.phone}}</a><td>{% if c.location %}<a href="{{c.location|maplink}}" target=_blank rel=noopener>📍 {{ c.location if not c.location.startswith('http') else 'فتح الخريطة' }}</a>{% else %}—{% endif %}<td>{{c.ns}}<td class=nw>{{ '%g'|format(c.tot) }} ₪<td class=nw style="color:#059669;font-weight:700">{{ '%g'|format(c.paid) }} ₪<td class=nw>{% if c.left>0 %}<b style="color:#e11d48">{{ '%g'|format(c.left) }} ₪</b>{% elif c.trk>0 %}<span class="pill s2">مسدّد</span>{% else %}—{% endif %}
<td class=nw>{% if c.left>0 %}<button type=button class=paybtn data-act="/employees/{{e.id}}/customers/{{c.id}}/pay" data-name="{{c.name}}" data-left="{{c.left}}" style="padding:6px 10px;font-size:13px">💵 دفعة</button>{% endif %}</tr>
{% else %}<tr><td colspan=9 class=em>ما أضاف زبائن بعد.</tr>{% endfor %}</table></div></div>
<div class=card><div class=ch><h3>💵 آخر دفعات الزبائن</h3></div><div style="overflow-x:auto"><table><tr><th>التاريخ<th>الزبون<th>المبلغ<th>ملاحظة<th>سجّلها<th></tr>
{% for p in pays %}<tr><td class=nw dir=ltr>{{p.created}}<td><b>{{p.cname or '—'}}</b><td class=nw><b style="color:#059669">{{ '%g'|format(p.amount) }} ₪</b><td><small>{{p.note or ''}}</small><td>{{ 'صاحب الشركة' if p.by_owner else e.name }}
<td><form method=post action=/employees/{{e.id}}/pay/{{p.id}}/delete class=il onsubmit="return confirm('حذف هذه الدفعة؟ رح يرجع المبلغ كمتبقي على الزبون.')"><button class="ib dl" title="حذف" aria-label="حذف">{{ic.dl}}</button></form></tr>
{% else %}<tr><td colspan=6 class=em>ما في دفعات مسجّلة.</tr>{% endfor %}</table></div></div>{% include 'paydlg' %}
<div class=card><div class=ch><h3>📝 قائمة انتظار زبائن الموظف ({{queue|length}})</h3></div><div style="overflow-x:auto"><table><tr><th>الزبون<th>المطلوب<th>الكمية<th>ملاحظة<th>التاريخ<th>بعهدته؟</tr>
{% for r in queue %}<tr><td><b>{{r.customer_name}}</b>{% if r.cphone %}<br><small dir=ltr>{{r.cphone}}</small>{% endif %}<td>{{r.item}}<td>{{r.qty}}<td><small>{{r.note or ''}}</small><td class=nw dir=ltr>{{r.created}}<td>{% if r.held is none %}<small>—</small>{% else %}<span class="pill {{ 's2' if r.ready else 's3' }}">{{ 'جاهز' if r.ready else 'ناقص — عنده ' ~ r.held }}</span>{% endif %}</tr>
{% else %}<tr><td colspan=6 class=em>ما في طلبات بالانتظار.</tr>{% endfor %}</table></div></div>
<div class=card><div class=ch><h3>🔔 آخر إشعارات الموظف</h3><a href=/notifications style="font-size:14px">كل الإشعارات</a></div><table>
{% for n in notes %}<tr><td class=nw dir=ltr>{{n.created}}<td>{{n.msg}}</tr>{% else %}<tr><td class=em>ما في إشعارات.</tr>{% endfor %}</table></div>{% endblock %}"""

import store; store.register(globals())
import accounts; accounts.register(globals())
import pos; pos.register(globals())
import cashbox; cashbox.register(globals())   # الصندوق المالي   # باركود + كاشير سريع + ملصقات   # الثيم + طلب الحساب بموافقة واتساب + A4 بسيط   # المتجر (تصنيفات المنتجات + السلة + الفواتير) وأدوات الصيانة
import backup; backup.register(globals())   # نسخ احتياطي واسترجاع
import partsimport; partsimport.register(globals())   # استيراد القطع من Excel/CSV

if __name__ == "__main__":
    start(); app.run(debug=os.environ.get("FLASK_DEBUG") == "1")   # debug بس لو طلبته صراحة (ممنوع على السيرفر العام)
