# -*- coding: utf-8 -*-
"""
migrate_to_neon.py — نقل بيانات REPAIRIX القديمة إلى Neon (Postgres).

المصدر (اختر واحد):
  --sqlite shop.db            ملف SQLite المحلي (+ --uploads uploads لنقل الصور)
  --firebase                  مباشرة من Firestore + Storage (يحتاج: pip install firebase-admin)
                              مع: --key firebase-key.json  --bucket my-project.firebasestorage.app  [--prefix repairix_]

الهدف: DATABASE_URL (متغير بيئة أو ملف .env).

أمثلة:
  python migrate_to_neon.py --sqlite shop.db --uploads uploads
  python migrate_to_neon.py --firebase --key firebase-key.json --bucket my-project.firebasestorage.app

- إذا الجداول بـ Neon فيها بيانات بيرفض يكمل، إلا لو حطيت --wipe (بيمسح بيانات Neon كلها قبل النقل).
- --dry-run بيعدّ الصفوف بدون ما يكتب شي.
- الصور بتنتقل لجدول files. الصور المحذوفة/الناقصة من المصدر بتنطبع بتحذير.
"""
import os, sys, argparse, sqlite3, datetime
import pgdb_neon as pgdb

TABLES = ["users", "settings", "password_resets", "notifications", "suppliers", "parts", "invoices", "needs", "needs_dismissed",
          "repairs", "repair_parts", "employees", "emp_stock_log", "emp_customers", "emp_cust_pay", "emp_co_pay", "emp_queue", "emp_invoices", "debtors", "debt_entries", "cheques", "returns_log", "tools", "sales", "sale_items", "meta"]
SERIAL = [t for t in TABLES if t not in ("settings", "needs_dismissed", "meta")]
PHOTO_COLS = [("parts", "photo"), ("cheques", "photo"), ("returns_log", "photo"), ("tools", "photo"), ("settings", "logo")]
MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
SKIP_META = {"fs_linked"}


def src_sqlite(path):
    c = sqlite3.connect("file:%s?mode=ro" % path, uri=True); c.row_factory = sqlite3.Row
    have = {r[0] for r in c.execute("select name from sqlite_master where type='table'")}
    return {t: [dict(r) for r in c.execute(f'select * from "{t}"')] for t in TABLES if t in have}


def src_firebase(key, bucket, prefix):
    import firebase_admin
    from firebase_admin import credentials, firestore
    firebase_admin.initialize_app(credentials.Certificate(key), {"storageBucket": bucket} if bucket else {})
    fs = firestore.client()
    return {t: [d.to_dict() for d in fs.collection(prefix + t).stream()] for t in TABLES}


def cast(v, typ):
    if v is None: return None
    if typ in ("integer", "bigint", "smallint"):
        if isinstance(v, str) and not v.strip(): return None
        return int(float(v))
    if typ in ("double precision", "real", "numeric"):
        if isinstance(v, str) and not v.strip(): return None
        return float(v)
    if isinstance(v, bytes): return v.decode("utf-8", "replace")
    return v if isinstance(v, str) else str(v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sqlite"); ap.add_argument("--uploads")
    ap.add_argument("--firebase", action="store_true"); ap.add_argument("--key", default="firebase-key.json")
    ap.add_argument("--bucket"); ap.add_argument("--prefix", default="repairix_")
    ap.add_argument("--wipe", action="store_true"); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if bool(a.sqlite) == bool(a.firebase): ap.error("اختر مصدر واحد: --sqlite shop.db أو --firebase")

    data = src_sqlite(a.sqlite) if a.sqlite else src_firebase(a.key, a.bucket, a.prefix)
    print("المصدر:", ", ".join(f"{t}={len(r)}" for t, r in data.items() if r))
    if a.dry_run: return

    pgdb.init_schema()
    with pgdb.connect() as c:
        cur = c.raw.cursor()
        if a.wipe:
            cur.execute("truncate " + ",".join(TABLES + ["files"]) + " restart identity")
        else:
            busy = [t for t in TABLES + ["files"] if t != "meta" and cur.execute(f"select 1 from {t} limit 1").fetchone()]
            if busy: sys.exit("Neon فيه بيانات أصلاً بالجداول: " + ", ".join(busy) + "\nاستخدم --wipe إذا بدك تمسحها وتنقل من جديد.")
        types = {}
        for t, col, typ in cur.execute("select table_name, column_name, data_type from information_schema.columns where table_schema=current_schema()").fetchall():
            types.setdefault(t, {})[col] = typ
        for t in TABLES:
            rows = data.get(t) or []
            if t == "meta": rows = [r for r in rows if r.get("k") not in SKIP_META]
            if not rows: continue
            cols = [k for k in rows[0] if k in types[t]]
            sql = f'insert into {t}({",".join(cols)}) values({",".join(["%s"] * len(cols))})' + (" on conflict do nothing" if t == "meta" else "")
            cur.executemany(sql, [[cast(r.get(k), types[t][k]) for k in cols] for r in rows])
            print(f"  {t}: {len(rows)}")
        for t in SERIAL:     # عشان الإدخالات الجديدة تكمل بعد أكبر id موجود
            cur.execute(f"select setval(pg_get_serial_sequence('{t}','id'), coalesce((select max(id) from {t}), 1), (select max(id) from {t}) is not null)")

        # ---- الصور ----
        names = set()
        for t, col in PHOTO_COLS:
            names |= {r[col] for r in data.get(t, []) if r.get(col)}
        bucket = None
        if a.firebase and a.bucket:
            from firebase_admin import storage; bucket = storage.bucket()
        ok, missing = 0, []
        for n in sorted(names):
            blob = None
            p = os.path.join(a.uploads, n) if a.uploads else None
            if p and os.path.exists(p):
                blob = open(p, "rb").read()
            elif bucket:
                b = bucket.blob("uploads/" + n)
                if b.exists(): blob = b.download_as_bytes()
            if blob is None: missing.append(n); continue
            cur.execute("insert into files(name,mime,data,created) values(%s,%s,%s,%s) on conflict do nothing",
                        (n, MIME.get(os.path.splitext(n)[1].lower(), "application/octet-stream"), blob, datetime.date.today().isoformat()))
            ok += 1
        print(f"  الصور: {ok} اننقلت" + (f"، {len(missing)} غير موجودة بالمصدر: {', '.join(missing[:10])}{'...' if len(missing) > 10 else ''}" if missing else ""))
    print("تم النقل ✅")


if __name__ == "__main__":
    main()
