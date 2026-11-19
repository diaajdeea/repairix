# -*- coding: utf-8 -*-
"""
pgdb.py — طبقة قاعدة البيانات لـ REPAIRIX.

الافتراضي: قاعدة محلية SQLite (ملف repair_shop.db جنب البرنامج). ما بتحتاج إنترنت ولا Neon.
للتحويل لـ Neon (لما نرفع على سيرفر): عيّن USE_NEON=1 و DATABASE_URL (شوف DEPLOY_NEON.md).

نفس الواجهة بالحالتين:  connect() / init_schema() / conn.execute(sql_with_?, params) / r["col"] أو r[0]
"""
import os, re, sqlite3, threading


def _load_dotenv():
    """بيقرأ .env جنب البرنامج (متغيرات البيئة الحقيقية لها الأولوية)."""
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"), encoding="utf-8") as fh:
            for line in fh:
                k, sep, v = line.strip().partition("=")
                if sep and k.strip() and not k.startswith("#"):
                    os.environ.setdefault(k.strip(), v.strip().strip("\"'"))
    except OSError:
        pass


_load_dotenv()
HERE = os.path.dirname(os.path.abspath(__file__))
USE_NEON = os.environ.get("USE_NEON", "").strip().lower() in ("1", "true", "yes") or (os.environ.get("USE_NEON", "").strip() == "" and bool(os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")))   # وجود DATABASE_URL = تشغيل على Neon تلقائياً (USE_NEON=0 لإيقافه)
DB_PATH = os.environ.get("DB_PATH") or os.path.join(HERE, "repair_shop.db")

NO_ID = {"settings", "needs_dismissed", "meta", "files"}      # جداول بدون عمود id
_INS = re.compile(r"\s*insert\s+into\s+([a-z_]+)", re.I)
_GREATEST = re.compile(r"\bgreatest\s*\(", re.I)
_STRAGG = re.compile(r"\bstring_agg\s*\(", re.I)


class Row:
    """صف يشبه sqlite3.Row بس مع get(): r["col"] و r[0] و dict(r) و r.keys()."""
    __slots__ = ("_k", "_v")

    def __init__(self, keys, values):
        self._k, self._v = keys, values

    def __getitem__(self, i):
        if isinstance(i, str):
            try:
                return self._v[self._k.index(i)]
            except ValueError:
                raise KeyError(i) from None
        return self._v[i]

    def keys(self): return list(self._k)
    def get(self, k, d=None):
        try: return self[k]
        except (KeyError, IndexError): return d
    def __iter__(self): return iter(self._v)
    def __len__(self): return len(self._v)
    def __repr__(self): return "Row(%s)" % dict(zip(self._k, self._v))


def _row_factory(cur, values):
    return Row([d[0] for d in cur.description], tuple(values))


def translate(sql):
    """من لهجة Postgres اللي كتبنا فيها الاستعلامات للهجة SQLite."""
    sql = _GREATEST.sub("max(", sql)       # greatest(0, x) -> max(0, x)
    return _STRAGG.sub("group_concat(", sql)  # string_agg(x, sep) -> group_concat(x, sep)


class Cursor:
    def __init__(self, cur, lastrowid=None):
        self._c, self.lastrowid = cur, lastrowid

    @property
    def rowcount(self): return self._c.rowcount
    def fetchall(self): return self._c.fetchall() if self._c.description else []
    def fetchone(self): return self._c.fetchone() if self._c.description else None
    def __iter__(self): return iter(self.fetchall())


class Conn:
    def __init__(self, raw):
        self.raw = raw

    def execute(self, sql, params=()):
        cur = self.raw.execute(translate(sql), tuple(params) if params is not None else ())
        m = _INS.match(sql)
        rid = cur.lastrowid if (m and m.group(1).lower() not in NO_ID) else None
        return Cursor(cur, rid)

    def commit(self): self.raw.commit()
    def rollback(self): self.raw.rollback()

    def close(self):
        raw, self.raw = self.raw, None
        if raw is not None:
            raw.close()

    def __enter__(self): return self
    def __exit__(self, et, ev, tb):
        if self.raw is not None:
            (self.commit if et is None else self.rollback)()
        self.close()


def _connect_local():
    raw = sqlite3.connect(DB_PATH, timeout=30)
    raw.row_factory = _row_factory
    raw.execute("pragma journal_mode=wal")
    raw.execute("pragma synchronous=normal")
    raw.execute("pragma busy_timeout=30000")
    return Conn(raw)


_init_lock = threading.Lock()


def _split(script):
    """بيقسم سكربت SQL لجمل منفصلة (بعد حذف التعليقات)."""
    script = "\n".join(l for l in script.splitlines() if not l.strip().startswith("--"))
    out, buf = [], ""
    for line in script.splitlines():
        buf += line + "\n"
        if sqlite3.complete_statement(buf):
            out.append(buf.strip()); buf = ""
    return [s for s in out if s]


_ALTER = re.compile(r"alter\s+table\s+(\w+)\s+add\s+column\s+if\s+not\s+exists\s+(\w+)\s+(.+?);?$", re.I | re.S)


def _local_schema(schema):
    """schema.sql مكتوب لـ Postgres؛ هون بنترجمه لـ SQLite."""
    s = re.sub(r"\bserial\s+primary\s+key", "integer primary key autoincrement", schema, flags=re.I)
    s = re.sub(r"\bdouble\s+precision\b", "real", s, flags=re.I)
    s = re.sub(r"\bbytea\b", "blob", s, flags=re.I)
    return _split(s)


def _init_local():
    with open(os.path.join(HERE, "schema.sql"), encoding="utf-8") as fh:
        stmts = _local_schema(fh.read())
    with _init_lock, _connect_local() as c:
        for st in stmts:
            m = _ALTER.match(st)
            if m:   # SQLite ما بيدعم "add column if not exists": منفحص الأعمدة بنفسنا
                tbl, col, rest = m.group(1), m.group(2), m.group(3)
                cols = [r[1] for r in c.raw.execute("pragma table_info(%s)" % tbl).fetchall()]
                if col not in cols:
                    c.raw.execute("alter table %s add column %s %s" % (tbl, col, rest))
            else:
                c.raw.execute(st)


if USE_NEON:
    import pgdb_neon as _neon
    connect, init_schema, database_url = _neon.connect, _neon.init_schema, _neon.database_url
else:
    def connect(): return _connect_local()
    def init_schema(): _init_local()
