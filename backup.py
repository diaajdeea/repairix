# -*- coding: utf-8 -*-
"""
backup.py — نسخة احتياطية واسترجاع لبيانات الشركة (من صفحة الإعدادات).

النسخة = ملف JSON واحد فيه كل بيانات الشركة (قطع، صيانات، موردين، موظفين، ديون، شيكات، صندوق، مبيعات...) + الصور.
الاسترجاع بيستبدل بيانات الشركة الحالية بمحتوى الملف. الأرقام الداخلية (id) بتتجدّد والروابط بينها بتنحفظ،
فبيشتغل على نفس الحساب أو على حساب تاني، وعلى SQLite وعلى Neon.
حساب الدخول (الإيميل/كلمة السر) وفترة التجربة ما بتتأثر.
"""
import base64, datetime, json, re

FORMAT = "repairix-backup"
VERSION = 1
FILE_COLS = ("photo", "logo", "receipt")          # أعمدة بتشير لصور/وصولات مخزّنة بجدول files
_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")

# ترتيب الإدخال (الأب قبل الابن) + الأعمدة اللي بتشير لجداول تانية
TABLES = [
    ("suppliers", {}),
    ("parts", {"supplier_id": "suppliers"}),
    ("tools", {}),
    ("employees", {}),
    ("emp_customers", {"emp_id": "employees"}),
    ("emp_invoices", {"emp_id": "employees"}),
    ("emp_stock_log", {"emp_id": "employees", "part_id": "parts", "customer_id": "emp_customers", "inv_id": "emp_invoices"}),
    ("repairs", {"part_id": "parts"}),
    ("repair_parts", {"repair_id": "repairs", "part_id": "parts"}),
    ("debtors", {}),
    ("sales", {"person_id": "debtors"}),
    ("sale_items", {"sale_id": "sales", "part_id": "parts", "tool_id": "tools"}),
    ("debt_entries", {"debtor_id": "debtors", "sale_id": "sales"}),
    ("cheques", {"person_id": "debtors"}),
    ("returns_log", {"part_id": "parts", "supplier_id": "suppliers", "emp_id": "employees", "emp_log_id": "emp_stock_log", "repair_id": "repairs"}),
    ("invoices", {"supplier_id": "suppliers"}),
    ("needs", {"part_id": "parts", "supplier_id": "suppliers", "invoice_id": "invoices", "ret_id": "returns_log"}),
    ("needs_dismissed", {"part_id": "parts"}),
    ("emp_cust_pay", {"emp_id": "employees", "customer_id": "emp_customers", "log_id": "emp_stock_log"}),
    ("emp_co_pay", {"emp_id": "employees"}),
    ("emp_queue", {"emp_id": "employees", "customer_id": "emp_customers", "part_id": "parts"}),
    ("cash_entries", {"supplier_id": "suppliers"}),
    ("cash_counts", {}),
    ("day_closings", {"withdraw_entry_id": "cash_entries", "adjust_entry_id": "cash_entries"}),
]
SETTINGS_SKIP = {"user_id", "trial_start"}        # فترة التجربة ما بتنستبدل


def register(ns):
    app, T, q, uid = ns["app"], ns["T"], ns["q"], ns["uid"]
    request, redirect, Response, db, notify = ns["request"], ns["redirect"], ns["Response"], ns["db"], ns["notify"]
    _MIME = ns.get("_MIME", {})
    import os

    def cols_of(table):
        cur = db().execute("select * from %s where 1=0" % table)
        return [getattr(d, "name", None) or d[0] for d in cur._c.description]

    def file_blob(name):
        r = q("select mime,data from files where name=?", (name,))
        return (r[0]["mime"], bytes(r[0]["data"])) if r else None

    # ---------- تنزيل نسخة ----------
    @app.route("/settings/backup")
    def backup_download():
        u = uid(); data = {}; files = {}; counts = {}
        for t, _ in TABLES:
            rows = [dict(r) for r in q("select * from %s where user_id=? order by 1" % t, (u,))]
            data[t] = rows; counts[t] = len(rows)
        st = q("select * from settings where user_id=?", (u,))
        data["settings"] = [{k: v for k, v in dict(st[0]).items() if k not in SETTINGS_SKIP}] if st else []
        for rows in data.values():
            for r in rows:
                for c in FILE_COLS:
                    n = r.get(c)
                    if n and isinstance(n, str) and n not in files:
                        b = file_blob(n)
                        if b: files[n] = {"mime": b[0], "b64": base64.b64encode(b[1]).decode("ascii")}
        now = datetime.datetime.now()
        out = {"app": FORMAT, "version": VERSION, "created": now.strftime("%Y-%m-%d %H:%M:%S"),
               "shop": (data["settings"][0].get("shop_name") if data["settings"] else "") or "", "counts": counts,
               "data": data, "files": files}
        body = json.dumps(out, ensure_ascii=False, separators=(",", ":"), default=str)
        return Response(body, mimetype="application/json; charset=utf-8",
                        headers={"Content-Disposition": "attachment; filename=repairix-backup-%s.json" % now.strftime("%Y-%m-%d_%H%M"),
                                 "Cache-Control": "no-store"})

    # ---------- استرجاع ----------
    @app.post("/settings/restore")
    def backup_restore():
        try: request.max_content_length = 200 * 1024 * 1024   # النسخة (مع الصور) ممكن تكون أكبر من الحد العام
        except Exception: pass
        f = request.files.get("backup")
        if not f or not f.filename:
            notify("اختر ملف النسخة الاحتياطية أولاً", "warn", "الاسترجاع"); return redirect("/settings")
        if request.form.get("ok") != "1":
            notify("لازم تأكّد إنك فاهم إن البيانات الحالية رح تنستبدل", "warn", "الاسترجاع"); return redirect("/settings")
        try:
            b = json.loads(f.read().decode("utf-8-sig"))
            assert isinstance(b, dict) and b.get("app") == FORMAT and isinstance(b.get("data"), dict)
        except Exception:
            notify("الملف مش نسخة احتياطية صالحة (لازم ملف .json نازل من هالبرنامج)", "warn", "الاسترجاع"); return redirect("/settings")
        if int(b.get("version") or 0) > VERSION:
            notify("النسخة من إصدار أحدث من هالبرنامج، حدّث البرنامج أولاً", "warn", "الاسترجاع"); return redirect("/settings")

        u = uid(); d = db(); data = b["data"]; files = b.get("files") or {}
        old_files = set()
        for t, c in (("parts", "photo"), ("tools", "photo"), ("cheques", "photo"), ("returns_log", "photo"), ("settings", "logo"), ("cash_entries", "receipt"), ("emp_co_pay", "receipt")):
            for r in q("select %s n from %s where user_id=? and %s is not null" % (c, t, c), (u,)): old_files.add(r["n"])
        new_files = set(); idmap = {}; total = 0
        try:
            for t, _ in TABLES: d.execute("delete from %s where user_id=?" % t, (u,))
            for t, fk in TABLES:
                rows = data.get(t) or []
                if not rows: continue
                have = set(cols_of(t)); idmap[t] = {}
                for r in rows:
                    if not isinstance(r, dict): continue
                    rec = {}
                    for k, v in r.items():
                        if k in ("id", "user_id") or k not in have or not _IDENT.match(k): continue
                        if k in fk and v is not None: v = idmap.get(fk[k], {}).get(v)
                        rec[k] = v
                        if k in FILE_COLS and v: new_files.add(v)
                    if t == "needs_dismissed" and rec.get("part_id") is None: continue
                    rec["user_id"] = u
                    names = list(rec)
                    cur = d.execute("insert into %s(%s) values(%s)" % (t, ",".join(names), ",".join("?" * len(names))), [rec[k] for k in names])
                    if "id" in r and cur.lastrowid is not None: idmap[t][r["id"]] = cur.lastrowid
                    total += 1
            # الإعدادات: بنحدّث صف الشركة الحالي
            S = (data.get("settings") or [None])[0]
            if isinstance(S, dict):
                have = set(cols_of("settings")); sets = {k: v for k, v in S.items() if k in have and k not in SETTINGS_SKIP and _IDENT.match(k)}
                for k in FILE_COLS:
                    if sets.get(k): new_files.add(sets[k])
                if sets:
                    if not q("select 1 from settings where user_id=?", (u,)): d.execute("insert into settings(user_id) values(?)", (u,))
                    d.execute("update settings set %s where user_id=?" % ",".join("%s=?" % k for k in sets), list(sets.values()) + [u])
            # الصور
            for n in new_files:
                x = files.get(n)
                if not x or not isinstance(n, str) or "/" in n or "\\" in n: continue
                if not q("select 1 from files where name=?", (n,)):
                    d.execute("insert into files(name,mime,data,created) values(?,?,?,?)",
                              (n, x.get("mime") or _MIME.get(os.path.splitext(n)[1].lower(), "application/octet-stream"), base64.b64decode(x.get("b64") or ""), datetime.date.today().isoformat()))
            d.commit()
        except Exception as e:
            try: d.rollback()
            except Exception: pass
            notify("ما انسترجعت النسخة وما تغيّرت بياناتك الحالية. السبب: %s" % str(e)[:120], "warn", "فشل الاسترجاع"); return redirect("/settings")
        for n in old_files - new_files:      # صور النسخة القديمة اللي ما إلها لزوم
            ns["del_file"](n)
        notify("انسترجعت النسخة (%d سجل) المأخوذة بتاريخ %s" % (total, b.get("created") or "—"), "ok", "تم الاسترجاع")
        return redirect("/settings")

    CARD = """<div class=card style="margin-top:16px"><h3>النسخ الاحتياطي والاسترجاع</h3>
<small>النسخة بتشمل كل بيانات الشركة: القطع والصيانات والموردين والموظفين والديون والشيكات والصندوق والمبيعات والصور. حسابك وكلمة السر ما بدخلوا فيها.</small>
<div class=bkx><div class=bkb><b>💾 حفظ نسخة احتياطية</b><small>بينزل ملف على جهازك. احفظه بمكان آمن (فلاشة / إيميل / درايف).</small>
<a class="btn" href=/settings/backup download>تنزيل نسخة احتياطية</a></div>
<form class=bkb method=post action=/settings/restore enctype=multipart/form-data onsubmit="return confirm('رح تنستبدل كل بيانات الشركة الحالية ببيانات الملف. متأكد؟')"><b>♻️ استرجاع نسخة احتياطية</b>
<small>اختر ملف نسخة نازل من هالبرنامج. <b style="color:#e11d48">تنبيه:</b> البيانات الحالية بتنستبدل، فنزّل نسخة قبل ما تسترجع.</small>
<input type=file name=backup accept=".json,application/json" required>
<label class=bkc><input type=checkbox name=ok value=1 required> فاهم إن البيانات الحالية رح تنستبدل</label>
<button class=ghost>استرجاع النسخة</button></form></div>
<style>.bkx{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:14px}.bkb{display:flex;flex-direction:column;gap:10px;align-items:flex-start;padding:16px;border:1px dashed var(--line);border-radius:16px}.bkb small{color:var(--mut)}.bkb input[type=file]{width:100%}.bkc{display:flex;align-items:center;gap:8px;font-size:13.5px;font-weight:600}.bkc input{width:auto;margin:0}@media(max-width:700px){.bkx{grid-template-columns:1fr}}</style></div>"""
    tail = "<p><button>تغيير كلمة السر</button></p></form></div>{% endblock %}"
    assert tail in T["settings"]
    T["settings"] = T["settings"].replace(tail, "<p><button>تغيير كلمة السر</button></p></form></div>" + CARD + "{% endblock %}", 1)
