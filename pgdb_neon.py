# -*- coding: utf-8 -*-
"""
pgdb.py — اتصال REPAIRIX بقاعدة Neon (Postgres) بنفس أسلوب sqlite3 المستخدم بالتطبيق.

  conn = pgdb.connect()
  conn.execute("select * from users where id=?", (1,)).fetchall()   # الصفوف: r["email"] أو r[0] أو dict(r)
  cur = conn.execute("insert into parts(name) values(?)", ("x",)); cur.lastrowid
  conn.commit(); conn.close()

متغيرات البيئة:
  DATABASE_URL  رابط الاتصال من Neon (postgresql://user:pass@ep-xxx-pooler.region.aws.neon.tech/db?sslmode=require)
  POOL_MIN / POOL_MAX   حجم مجمّع الاتصالات (الافتراضي 1 / 10)
"""
import os, re, threading
import psycopg

NO_ID = {"settings", "needs_dismissed", "meta", "files"}      # جداول بدون عمود id (ما في lastrowid)
_INS = re.compile(r"\s*insert\s+into\s+([a-z_]+)", re.I)
_LIKE = re.compile(r"\blike\b", re.I)                          # SQLite: LIKE بيتجاهل حالة الحروف، Postgres لا => ILIKE


def _load_dotenv():
    """بيقرأ DATABASE_URL من ملف .env جنب البرنامج (للتشغيل المحلي). متغيرات البيئة الحقيقية لها الأولوية."""
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"), encoding="utf-8") as fh:
            for line in fh:
                k, sep, v = line.strip().partition("=")
                if sep and k.strip() and not k.startswith("#"):
                    os.environ.setdefault(k.strip(), v.strip().strip("\"'"))
    except OSError:
        pass


def database_url():
    _load_dotenv()
    u = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not u:
        raise RuntimeError("DATABASE_URL غير معيّن. خذ رابط الاتصال من لوحة Neon (Connect) وحطه بمتغير البيئة DATABASE_URL.")
    return u


class Row:
    """صف يشبه sqlite3.Row: r["col"] و r[0] و dict(r) و r.keys()."""
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


def _row_factory(cursor):
    names = [c.name for c in (cursor.description or [])]
    return lambda values: Row(names, tuple(values))


def translate(sql):
    """من أسلوب SQLite (؟ و LIKE) لأسلوب psycopg."""
    return _LIKE.sub("ilike", sql.replace("%", "%%").replace("?", "%s"))


class Cursor:
    def __init__(self, cur, lastrowid=None):
        self._c, self.lastrowid = cur, lastrowid

    @property
    def rowcount(self): return self._c.rowcount
    def fetchall(self): return self._c.fetchall() if self._c.description else []
    def fetchone(self): return self._c.fetchone() if self._c.description else None
    def __iter__(self): return iter(self.fetchall())


_pool = None
_pool_lock = threading.Lock()


def _kwargs():
    # prepare_threshold=None: ضروري مع رابط Neon المجمّع (pgbouncer) لأنه ما بيدعم prepared statements
    return {"row_factory": _row_factory, "prepare_threshold": None, "connect_timeout": 20}


def _get_pool():
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                try:
                    from psycopg_pool import ConnectionPool
                    _pool = ConnectionPool(database_url(), kwargs=_kwargs(), open=True, timeout=30,
                                           min_size=int(os.environ.get("POOL_MIN", 1)), max_size=int(os.environ.get("POOL_MAX", 10)),
                                           max_idle=240, check=ConnectionPool.check_connection)
                except ImportError:
                    _pool = False
    return _pool


class Conn:
    def __init__(self, raw, pool=None):
        self.raw, self._pool = raw, pool

    def execute(self, sql, params=()):
        sql = translate(sql)
        m = _INS.match(sql)
        want_id = bool(m) and m.group(1).lower() not in NO_ID and not re.search(r"\breturning\b|\bon\s+conflict\b", sql, re.I)
        if want_id: sql = sql.rstrip().rstrip(";") + " returning id"
        cur = self.raw.cursor()
        cur.execute(sql, tuple(params) if params is not None else ())
        return Cursor(cur, cur.fetchone()[0] if want_id else None)

    def commit(self): self.raw.commit()
    def rollback(self): self.raw.rollback()

    def close(self):
        raw, self.raw = self.raw, None
        if raw is None: return
        if self._pool:
            try: raw.rollback()
            except Exception: pass
            self._pool.putconn(raw)
        else:
            raw.close()

    def __enter__(self): return self
    def __exit__(self, et, ev, tb):
        if self.raw is not None:
            (self.commit if et is None else self.rollback)()
        self.close()


def connect():
    p = _get_pool()
    if p: return Conn(p.getconn(), p)
    return Conn(psycopg.connect(database_url(), **_kwargs()))


def init_schema():
    """بينشئ الجداول إذا مش موجودة (قفل استشاري عشان ما يتعارض أكثر من worker بنفس اللحظة)."""
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql"), encoding="utf-8") as fh:
        schema = fh.read()
    with connect() as c:
        c.raw.execute("select pg_advisory_xact_lock(727001)")
        c.raw.execute(schema)
