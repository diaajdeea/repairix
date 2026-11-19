# -*- coding: utf-8 -*-
"""استيراد القطع من ملف Excel/CSV «مخربط»: بيتعرف على الأعمدة والأقسام والصور وبيوزّع كل قطعة على صفحتها.

الخطوات: رفع الملف ← تحليل ومعاينة (مع تعديل الأعمدة لو لزم) ← استيراد.
"""
import io, re, csv, json, uuid, hashlib, base64

MAX_FILE = 20 * 1024 * 1024
MAX_ROWS = 5000          # أقصى عدد صفوف بنقرأه من الورقة الواحدة
MAX_IMG = 800            # أطول ضلع للصورة المحفوظة (بكسل)

AR_DIG = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_DIAC = re.compile("[\u064b-\u065f\u0670\u0640]")


def norm(s):
    """توحيد النص العربي/الإنجليزي للمطابقة: همزات، تاء مربوطة، تشكيل، أرقام هندية."""
    if s is None: return ""
    s = str(s).translate(AR_DIG).lower()
    s = _DIAC.sub("", s)
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ٱ", "ا"), ("ى", "ي"), ("ة", "ه"), ("ؤ", "و"), ("ئ", "ي")): s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip()


_CUR = re.compile(r"(₪|\$|€|شيكل|شيقل|ش\.?ج|\bnis\b|\bils\b|دينار|دولار|\busd\b|\bjd\b|د\.?أ|د\.?ا|ريال|درهم|جنيه)", re.I)


def num(v):
    """رقم من خلية: 12 / '12.5' / '١٢' / '25 ₪' / '95 شيكل' / '1,200' ... وإلا None.
    النص اللي فيه حروف غير العملة (مثل 'شاشة A12') مش رقم."""
    if v is None or isinstance(v, bool): return None
    if isinstance(v, (int, float)): return float(v)
    s = _CUR.sub("", str(v).translate(AR_DIG).replace("٫", ".").replace("٬", ",")).strip()
    if not re.fullmatch(r"-?\s*\d[\d.,\s]*", s): return None
    s = re.sub(r"\s+", "", s).rstrip(".,")
    if "," in s and "." in s: s = s.replace(",", "") if s.rfind(".") > s.rfind(",") else s.replace(".", "").replace(",", ".")
    elif "," in s:
        p = s.split(",")
        s = s.replace(",", "") if len(p) > 1 and len(p[-1]) == 3 else s.replace(",", ".")
    try: return float(s)
    except ValueError: return None


def text(v):
    if v is None: return ""
    if isinstance(v, float) and v.is_integer(): v = int(v)
    return re.sub(r"\s+", " ", str(v)).strip()


# عناوين الأعمدة (بالترتيب: الأدق أول)
HDR = [
    ("barcode", r"باركود|barcode|sku|^(ال)?كود$|^code$|رمز"),
    ("min_qty", r"حد.{0,12}(ادني|اقل|طلب)|\bmin\b|اقل كميه"),
    ("color", r"لون|الوان|colou?r"),
    ("category", r"^(ال)?(نوع|فئه|قسم|تصنيف)\b|category|\btype\b|\bgroup\b"),
    ("cost", r"شراء|تكلف|جمله|اصلي|\bcost\b|\bbuy|purchase|wholesale|اساسي|راس المال"),
    ("price", r"بيع|مفرق|سعر|price|\bsell|retail|مبيع|المبلغ"),
    ("qty", r"كميه|عدد|رصيد|مخزون|متوفر|\bqty\b|quant|stock|\bcount\b|\bpcs\b|pieces|^(ال)?قطع$|الموجود"),
    ("name", r"اسم|صنف|بيان|منتج|قطعه|موديل|model|name|item|product|desc|ماده|تفاصيل|الجهاز|مواصفات"),
]
HDR_RX = [(f, re.compile(p)) for f, p in HDR]
FIELDS = ["name", "category", "qty", "cost", "price", "color", "barcode", "min_qty"]
FIELD_AR = {"name": "اسم القطعة", "category": "النوع / القسم", "qty": "الكمية", "cost": "سعر الشراء", "price": "سعر البيع",
            "color": "اللون", "barcode": "الباركود", "min_qty": "الحد الأدنى"}


def hdr_field(cell):
    if cell is None or isinstance(cell, (int, float)) and not isinstance(cell, bool): return None
    t = norm(cell)
    if not t or len(t) > 40 or num(t) is not None: return None
    for f, rx in HDR_RX:
        if rx.search(t): return f
    return None


# تصنيف القطعة لقسمها (بالترتيب)
CAT_RX = [
    ("كونكتر", r"كونكتر|كنكتر|كونيكتر|connector|flex|فلكس|فليكس"),
    ("قاعدة شحن", r"(قاعده|قواعد|بورد|board|port|dock|بوردات).{0,14}(شحن|charg)|(شحن|charg).{0,14}(قاعده|قواعد|بورد|board|port|dock)|^(قاعده|قواعد) "),
    ("ظهر", r"ظهر|ظهور|غطاء خلفي|غطاء|back ?cover|backcover|rear cover|\bback\b|housing|هيكل"),
    ("بطارية", r"بطاري|batter|\bbatt\b"),
    ("شاشة", r"شاش|\blcd\b|display|screen|oled|amoled|تاتش|\btouch\b|digitizer"),
    ("آيسي", r"ايسي|اي سي|\bic\b|\bics\b|chip|شريحه باور|power ic"),
    ("سماعات", r"سماع|headphone|earphone|earbud|airpod|headset|ايربود|هيدفون"),
]
CAT_RX = [(c, re.compile(p)) for c, p in CAT_RX]
TOOLS = "أدوات"      # وجهة «أدوات الصيانة» (جدول tools مش parts)
CAT_EXTRA = [("قاعدة شحن", re.compile(r"شواحن|شاحن|charger")),
             (TOOLS, re.compile(r"(?<![ء-ي])(ال)?(ادوات|معدات|عده)(?![ء-ي])|\btools?\b|equipment|workshop"))]    # لما يكون النص اسم قسم صريح (عمود النوع / عنوان / اسم ورقة)
CAT_URL = {"شاشة": "/screens", "بطارية": "/batteries", "قاعدة شحن": "/chargers", "آيسي": "/ics", "كونكتر": "/connectors",
           "سماعات": "/headphones", "ظهر": "/backs", "أخرى": "/parts", TOOLS: "/tools"}
CAT_AR = {"شاشة": "شاشات", "بطارية": "بطاريات", "قاعدة شحن": "قواعد شحن", "آيسي": "آيسيات", "كونكتر": "كونكترات",
          "سماعات": "سماعات", "ظهر": "ظهور", "أخرى": "أخرى", TOOLS: "أدوات الصيانة"}


TOOL_RX = re.compile(
    r"طاول|ترابيز|كرسي|كراسي|خزان[هة]|\bرف\b|هيتر|هواء ساخن|heat ?gun|hot ?air|مكواه|لحام|قصدير|solder|محطه|station|"
    r"مفك|screwdriver|ملقط|tweezer|مايكروسكوب|مجهر|microscope|multimeter|ملتيميتر|افو ?متر|avometer|power ?supply|مصدر طاقه|باور سبلاي|"
    r"مكبس|فاكيوم|vacuum|فاصل شاشات|ماكينه فصل|مشرط|سكين|زرديه|زرادي|كماشه|مقص|مثقاب|drill|مطرقه|مسدس غراء|glue ?gun|"
    r"منفاخ|blower|مجفف|اداه|ادوات|عده |toolkit|tool ?kit|اضاءه|مصباح|ليزر|سبراي|spray|كحول|فرشاه|brush|pry|opening tool|اداة فتح")

TOOL_GROUPS = [
    ("مفكات", r"مفك|screwdriver"),
    ("لحام وقصدير", r"لحام|قصدير|solder|مكواه|معجون"),
    ("تسخين وهواء ساخن", r"هيتر|هواء ساخن|heat ?gun|hot ?air|منفاخ|blower|مجفف"),
    ("قياس وفحص", r"multimeter|ملتيميتر|افو|avometer|فحص|power ?supply|مصدر طاقه|باور سبلاي|مايكروسكوب|مجهر|microscope|قياس"),
    ("ملاقط وأدوات فتح", r"ملقط|tweezer|فتح|pry|مشرط|سكين|زرادي|زرديه|كماشه|مقص|فاصل شاشات|ماكينه فصل"),
    ("تنظيف", r"سبراي|spray|كحول|فرشاه|brush|تنظيف|clean"),
    ("طاولات وتجهيزات", r"طاول|ترابيز|كرسي|كراسي|خزان|\bرف\b|اضاءه|مصباح"),
]
TOOL_GROUPS = [(c, re.compile(p)) for c, p in TOOL_GROUPS]


def tool_cat(name):
    """تصنيف الأداة (نص حر بصفحة الأدوات) من اسمها، وإلا فاضي."""
    n = norm(name)
    for c, rx in TOOL_GROUPS:
        if rx.search(n): return c
    return ""


def detect_cat(t, explicit=False):
    n = norm(t)
    if not n: return None
    for c, rx in CAT_RX:
        if rx.search(n): return c
    if explicit:
        for c, rx in CAT_EXTRA:
            if rx.search(n): return c
    return None


_TITLE_NOISE = re.compile(r"\b(قسم|قائمه|قوائم|اسعار|سعر|مخزون|جرد|list|section|price|stock|ورقه|sheet|ال)\b")


def title_cat(t):
    """عنوان قسم (سطر فيه خلية وحدة): 'بطاريات' / 'قسم الشاشات' ... وإلا None."""
    n = norm(t)
    if not n or len(n) > 40 or num(n) is not None: return None
    core = _TITLE_NOISE.sub(" ", n); core = re.sub(r"\s+", " ", core).strip()
    if len(core.split()) > 3: return None
    return detect_cat(core, explicit=True)


COLORS = {"اسود": "#111111", "ابيض": "#f5f5f5", "ازرق": "#2563eb", "احمر": "#dc2626", "اخضر": "#16a34a", "ذهبي": "#d4af37", "فضي": "#c0c0c0",
          "رمادي": "#808080", "بنفسجي": "#7c3aed", "وردي": "#ec4899", "برتقالي": "#f97316", "اصفر": "#eab308", "بني": "#7c4a21", "تركوازي": "#14b8a6",
          "black": "#111111", "white": "#f5f5f5", "blue": "#2563eb", "red": "#dc2626", "green": "#16a34a", "gold": "#d4af37", "silver": "#c0c0c0",
          "gray": "#808080", "grey": "#808080", "purple": "#7c3aed", "pink": "#ec4899", "orange": "#f97316", "yellow": "#eab308", "titanium": "#8d8d8d",
          "graphite": "#4b5563", "midnight": "#0f172a", "starlight": "#f1e9d8"}


def color_hex(c):
    n = norm(c)
    for k, v in COLORS.items():
        if k in n: return v
    return "#888888"


# ---------------------------------------------------------------- قراءة الملف
def read_sheets(data, ext):
    """[(اسم الورقة, [صفوف], ورقة openpyxl أو None)] — CSV بيجي كورقة وحدة."""
    if ext == ".csv":
        txt = None
        for enc in ("utf-8-sig", "utf-16", "cp1256", "latin-1"):
            try: txt = data.decode(enc); break
            except (UnicodeDecodeError, UnicodeError): continue
        sample = txt[:4096]
        try: dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error: dialect = csv.excel
        rows = [r for r in csv.reader(io.StringIO(txt), dialect)][:MAX_ROWS]
        return [("CSV", [tuple(r) for r in rows], None)]
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(data), data_only=True)
    out = []
    for ws in wb.worksheets:
        if getattr(ws, "sheet_state", "visible") != "visible": continue
        rows = [r for r in ws.iter_rows(min_row=1, max_row=min(ws.max_row or 0, MAX_ROWS), values_only=True)]
        out.append((ws.title, rows, ws))
    return out


def col_letter(i):
    from openpyxl.utils import get_column_letter
    return get_column_letter(i + 1)


def find_header(rows, limit=40):
    """أول سطر فيه عمودين أو أكتر مفهومين كعناوين → (رقم السطر 1-based, {الحقل: [أعمدة]})."""
    for ri, row in enumerate(rows[:limit], 1):
        m = row_map(row)
        if len({f for f in m}) >= 2 and ({"name", "price", "qty", "cost"} & set(m)): return ri, m
    return None, None


def row_map(row):
    m = {}
    for ci, c in enumerate(row):
        f = hdr_field(c)
        if f: m.setdefault(f, []).append(ci)
    return m


def guess_map(rows):
    """ملف بدون عناوين: بنخمّن الأعمدة من محتواها."""
    sample = [r for r in rows[:60] if any(c not in (None, "") for c in r)]
    if not sample: return {}
    width = max(len(r) for r in sample)
    stats = []
    for ci in range(width):
        vals = [r[ci] for r in sample if ci < len(r) and r[ci] not in (None, "")]
        if not vals: continue
        nums = [num(v) for v in vals]; isn = [n is not None and not isinstance(v, str) or (isinstance(v, str) and n is not None and len(v) <= 12) for v, n in zip(vals, nums)]
        frac = sum(isn) / len(vals)
        stats.append({"ci": ci, "n": len(vals), "num": frac, "vals": [n for n, k in zip(nums, isn) if k],
                      "txt": sum(len(text(v)) for v in vals) / len(vals)})
    texts = [s for s in stats if s["num"] < .3]
    m = {}
    if texts:
        best = max(texts, key=lambda s: (s["n"], s["txt"]))
        m["name"] = [best["ci"]]
    nums_ = [s for s in stats if s["num"] >= .6 and (not texts or s["ci"] != m["name"][0])]
    qty = next((s for s in nums_ if s["vals"] and all(float(v).is_integer() and 0 <= v <= 1000 for v in s["vals"])), None)
    rest = [s for s in nums_ if s is not qty]
    if qty: m["qty"] = [qty["ci"]]
    if len(rest) >= 2:
        rest.sort(key=lambda s: sum(s["vals"]) / len(s["vals"]))
        m["cost"] = [rest[0]["ci"]]; m["price"] = [rest[-1]["ci"]]
    elif len(rest) == 1: m["price"] = [rest[0]["ci"]]
    return m


TOTAL_RX = re.compile(r"^(المجموع|مجموع|الاجمالي|اجمالي|الاجمالى|total|sum|grand total|subtotal)\b")


def parse_sheet(name, rows, override=None, sheet_cat=None, mode="parts"):
    """بيرجّع {rows:[قطع], skipped:[(سطر, سبب)], mapping, header_row, guessed, ncols, cols}"""
    hr, auto = find_header(rows)
    guessed = False
    if auto is None:
        auto = guess_map(rows); guessed = True; hr = 0
    mapping = {f: list(c) for f, c in auto.items()}
    if override:
        for f, v in override.items():
            if v is None: mapping.pop(f, None)
            else: mapping[f] = [v]
    # عمود النوع لازم قيمه تتحول لأقسام، وإلا بنتجاهله
    ccol = (mapping.get("category") or [None])[0]
    if ccol is not None and not override and mode != "tools":
        vals = [r[ccol] for r in rows[hr:hr + 80] if ccol < len(r) and text(r[ccol])]
        if vals and sum(1 for v in vals if detect_cat(v, True)) / len(vals) < .3: mapping.pop("category", None)
    ncols = max((len(r) for r in rows), default=0)
    heads = rows[hr - 1] if hr else ()
    cols = []
    for ci in range(min(ncols, 40)):
        h = text(heads[ci]) if ci < len(heads) else ""
        if not h:
            for r in rows[hr:hr + 8]:
                if ci < len(r) and text(r[ci]): h = text(r[ci])[:18]; break
        cols.append(f"{col_letter(ci)} — {h}" if h else col_letter(ci))
    out, skipped = [], []
    sec = None; last_cat = None
    base_cat = detect_cat(sheet_cat, True) if sheet_cat else None
    cur_map = mapping
    ncell = lambda r, ci: r[ci] if ci is not None and ci < len(r) else None
    for ri, row in enumerate(rows, 1):
        if ri <= hr: continue
        vals = [c for c in row if c not in (None, "") and text(c)]
        if not vals: continue
        # عنوان مكرر وسط الورقة (تعريف أعمدة جديد)
        rm = row_map(row)
        if not override and len(rm) >= 2 and ({"name", "price", "qty", "cost"} & set(rm)) and not guessed:
            cur_map = {f: list(c) for f, c in rm.items()}; continue
        # عنوان قسم: خلية وحدة ونصها اسم قسم
        if len(vals) == 1 and isinstance(vals[0], str):
            tc = title_cat(vals[0])
            if tc: sec = tc; continue
        mp = cur_map
        nm_cols = mp.get("name") or []
        name = " ".join(t for t in (text(ncell(row, ci)) for ci in nm_cols) if t and num(t) is None) if nm_cols else ""
        name = re.sub(r"\s+", " ", name).strip()
        if not name: skipped.append((ri, "بدون اسم")); continue
        if TOTAL_RX.search(norm(name)): continue
        if len(name) < 2 or num(name) is not None: skipped.append((ri, "اسم غير صالح")); continue
        g = lambda f: ncell(row, (mp.get(f) or [None])[0])
        catv = text(g("category"))
        if catv: last_cat = catv      # خلايا الدمج العمودي: القيمة بتنطبق على اللي تحتها
        col_cat = detect_cat(catv or last_cat or "", True) if (catv or (last_cat and "category" in mp)) else None
        nm_part = detect_cat(name)
        tool_hit = bool(TOOL_RX.search(norm(name))) and not nm_part
        sure, sug = True, ""
        if mode == "tools":                         # الاستيراد من صفحة أدوات الصيانة
            cat = TOOLS
            if nm_part: cat, sure, sug = nm_part, False, "الاسم شكله قطعة غيار مش أداة"
        else:
            ctx = col_cat or sec or base_cat
            if ctx == TOOLS:
                cat = TOOLS
                if nm_part: cat, sure, sug = nm_part, False, "الاسم شكله قطعة غيار مش أداة"
            elif ctx and tool_hit: cat, sure, sug = TOOLS, False, "الاسم شكله أداة صيانة مش قطعة غيار"
            elif ctx:
                cat = ctx
                if not col_cat and nm_part and nm_part != ctx: cat, sure, sug = nm_part, False, "الاسم بيدل على «%s» بس الورقة/القسم مكتوب فيه «%s»" % (CAT_AR.get(nm_part, nm_part), CAT_AR.get(ctx, ctx))
            elif nm_part: cat = nm_part
            elif tool_hit: cat, sure, sug = TOOLS, False, "الاسم شكله أداة صيانة"
            else: cat, sure, sug = "أخرى", False, "ما قدرت أعرف نوعها"
        qty = num(g("qty")); cost = num(g("cost")); price = num(g("price")); mq = num(g("min_qty"))
        color = text(g("color"))
        bc = "".join(ch for ch in text(g("barcode")) if 32 < ord(ch) < 127)[:40] or None
        out.append({"r": ri, "name": name[:120], "cat": cat, "qty": max(0, int(round(qty))) if qty is not None else 0,
                    "min_qty": max(0, int(round(mq))) if mq is not None else 2,
                    "cost": round(cost, 2) if cost and cost > 0 else 0.0, "price": round(price, 2) if price and price > 0 else 0.0,
                    "color": color[:40], "barcode": bc, "img": None, "sure": sure, "sug": sug,
                    "tcat": (catv if (mode == "tools" and catv and not detect_cat(catv)) else tool_cat(name))[:40]})
    return {
        "name": None, "rows": out, "skipped": skipped, "mapping": mapping, "auto": auto, "header_row": hr, "guessed": guessed,
        "ncols": ncols, "cols": cols}


# ---------------------------------------------------------------- الصور
def prep_image(data):
    """صورة (أي صيغة يفهمها PIL) ← JPEG مضغوط. None إذا مش صورة قابلة للقراءة أو صغيرة جداً."""
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(data)); im.load()
        if im.width < 28 or im.height < 28: return None
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA"); bg = Image.new("RGB", im.size, (255, 255, 255)); bg.paste(im, mask=im.split()[-1]); im = bg
        else: im = im.convert("RGB")
        im.thumbnail((MAX_IMG, MAX_IMG))
        buf = io.BytesIO(); im.save(buf, "JPEG", quality=82, optimize=True)
        return buf.getvalue()
    except Exception:
        return None


def sheet_images(ws):
    """[(مركز السطر, أول سطر, آخر سطر, bytes)] لكل صورة مدمجة بالورقة."""
    out = []
    for im in getattr(ws, "_images", []) or []:
        try:
            data = im._data(); a = im.anchor; r1 = a._from.row + 1
            to = getattr(a, "to", None); r2 = (to.row + 1) if to is not None else r1
        except Exception:
            continue
        out.append(((r1 + r2) / 2.0, r1, r2, data))
    return out


def attach_images(parsed_rows, images, limit=600):
    """بنربط كل صورة بأقرب قطعة على سطرها. الصور المتكررة (شعارات) بنتجاهلها."""
    if not parsed_rows or not images: return 0
    cnt = {}
    for _, _, _, d in images: cnt[hashlib.md5(d).hexdigest()] = cnt.get(hashlib.md5(d).hexdigest(), 0) + 1
    best = {}
    for center, r1, r2, d in images[:limit]:
        if cnt[hashlib.md5(d).hexdigest()] > 3: continue
        cand = None
        for p in parsed_rows:
            if r1 <= p["r"] <= r2: dist = 0 + abs(p["r"] - center) / 100.0
            else: dist = min(abs(p["r"] - r1), abs(p["r"] - r2)) + 0.5
            if cand is None or dist < cand[0]: cand = (dist, p)
        if cand and cand[0] <= 2.5:
            p = cand[1]
            if p["r"] not in best or len(d) > len(best[p["r"]][1]): best[p["r"]] = (p, d)
    n = 0
    for p, d in best.values():
        jp = prep_image(d)
        if jp: p["img"] = jp; n += 1
    return n


def parse_file(data, ext, overrides=None, images=True, only=None, mode="parts"):
    """التحليل الكامل. overrides = {رقم الورقة: {الحقل: رقم عمود أو None}}. only = مجموعة أرقام أوراق (لتخفيف الصور)."""
    sheets = []
    for si, (title, rows, ws) in enumerate(read_sheets(data, ext)):
        sh = parse_sheet(title, rows, (overrides or {}).get(si), sheet_cat=title, mode=mode)
        sh["name"] = title; sh["idx"] = si; sh["nimg"] = 0
        if images and ws is not None and (only is None or si in only):
            sh["nimg"] = attach_images(sh["rows"], sheet_images(ws))
        sheets.append(sh)
    return sheets


# ---------------------------------------------------------------- التسجيل بالتطبيق
T_UP = r"""{% extends 'base' %}{% block c %}
<style>.pi-drop{border:2px dashed var(--line,#cfd7f1);border-radius:20px;padding:26px;text-align:center;margin:14px 0}.pi-drop input{margin:12px auto;max-width:420px}.pi-li{margin:14px 0 0;padding:0;list-style:none;display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:10px}.pi-li li{padding:12px 14px;border-radius:14px;border:1px solid var(--line,#e3e8f8);font-size:14px}
html[data-theme=dark] .pi-drop{border-color:#33407a}html[data-theme=dark] .pi-li li{border-color:#27315a;background:#141b3a}</style>
<div class=card style="padding:22px"><div class=ch><h3>📥 {{ 'استيراد أدوات الصيانة من Excel' if mode=='tools' else 'استيراد القطع من Excel' }}</h3><a class="btn ghost" href="{{ '/tools' if mode=='tools' else '/parts' }}">{{ 'رجوع للأدوات' if mode=='tools' else 'رجوع للقطع' }}</a></div>
{% if mode=='tools' %}<p style="margin:6px 0 0">ارفع ملف Excel (‎.xlsx) أو CSV فيه أدوات الورشة (طاولة صيانة، هيتر، مفكات، محطة لحام...) وبتنضاف لصفحة <b>أدوات الصيانة</b>. إذا كان في الملف قطع غيار مخلوطة معها، بتطلع لك بالمعاينة وبتحدد أنت وين تروح.</p>{% else %}<p style="margin:6px 0 0">ارفع ملف Excel (‎.xlsx) أو CSV حتى لو كان مخربط: أوراق متعددة، عناوين أعمدة مختلفة، أقسام مخلوطة، وصور مدمجة. البرنامج بيتعرف على الأعمدة بحاله وبيوزّع كل قطعة على صفحتها (شاشات، بطاريات، آيسيات، ظهور...) وبتشوف معاينة وبتعدّل قبل ما يتأكد الاستيراد. أي قطعة مش واضح وين تروح (مثل طاولة صيانة أو هيتر) بتتعرض عليك وإنت بتحدد وجهتها.</p>{% endif %}
<form method=post enctype=multipart/form-data><div class=pi-drop><b>اختر الملف</b><br><input type=file name=file accept=".xlsx,.xlsm,.csv" required><br><button>تحليل الملف ←</button><br><small>الحد الأقصى 20 ميغا · ما بنقدر نقرأ ملفات ‎.xls القديمة (احفظها ‎.xlsx)</small></div></form>
<ul class=pi-li>
<li>🔎 <b>بيتعرف على الأعمدة</b><br><small>الاسم، النوع، الكمية، سعر الشراء والبيع، اللون، الباركود، بالعربي أو الإنجليزي.</small></li>
<li>🗂️ <b>بيفرز وإنت بتقرر</b><br><small>بيصنّف من عمود النوع أو عنوان القسم أو اسم القطعة، واللي مش متأكد منه بيعرضه عليك لتختار: قسم قطع، أو أدوات الصيانة، أو تخطّي.</small></li>
<li>🖼️ <b>بيسحب الصور</b><br><small>الصورة المدمجة بسطر القطعة بتنربط فيها وبتتحفظ كصورتها.</small></li>
<li>♻️ <b>ما بيكرر القطع</b><br><small>إذا القطعة موجودة بنفس الاسم بتزيد كميتها أو بتتخطاها حسب اختيارك.</small></li></ul>
<p style="margin:16px 0 0"><a class="btn ghost" href="{{ '/tools/import/template.xlsx' if mode=='tools' else '/parts/import/template.xlsx' }}">⬇️ تحميل ملف نموذجي</a></p></div>{% endblock %}"""

T_PV = r"""{% extends 'base' %}{% block c %}
<style>.pi-top{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:14px}.pi-top div{border:1px solid var(--line,#e3e8f8);border-radius:16px;padding:12px 14px;background:#fff}.pi-top b{display:block;font-size:24px}.pi-top small{color:var(--mut,#6a74a8)}
.pi-map{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px;margin:10px 0}.pi-map label{font-size:12.5px;font-weight:700}.pi-map select{margin-top:3px;width:100%}
.pi-th{width:42px;height:42px;border-radius:10px;object-fit:cover;display:block}.pi-w{background:#fff7ed;color:#9a3412;border:1px solid #fed7aa;border-radius:12px;padding:8px 12px;font-size:13.5px;margin:8px 0}
.pi-opt{display:flex;gap:16px;flex-wrap:wrap;align-items:end}.pi-tb{width:100%}.pi-tb td,.pi-tb th{padding:7px 8px;vertical-align:middle}.pi-tb select{min-width:180px;margin:0}
tr.pi-un td{background:#fff7ed}.pi-sug{display:block;color:#9a3412;font-size:12px;margin-top:2px}.pi-bulk{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:8px 0}.pi-bulk select{margin:0;min-width:200px}
details.pi-g{border:1px solid var(--line,#e3e8f8);border-radius:14px;padding:10px 14px;margin:8px 0}details.pi-g summary{cursor:pointer}
html[data-theme=dark] .pi-top div{background:#141b3a;border-color:#27315a}html[data-theme=dark] .pi-w{background:#40300f;color:#fcd34d;border-color:#5b4414}html[data-theme=dark] tr.pi-un td{background:#40300f}html[data-theme=dark] .pi-sug{color:#fcd34d}html[data-theme=dark] details.pi-g{border-color:#27315a}</style>
<form method=post action=/parts/import/{{job}}/run id=pi-form><input type=hidden name=dec id=pi-dec value="">
<div class=pi-top><div><small>أوراق</small><b>{{sheets|length}}</b></div><div><small>قطعة لقيتها</small><b>{{total}}</b></div><div><small>محتاجة قرارك</small><b>{{needs|length}}</b></div><div><small>صور مربوطة</small><b>{{nimg}}</b></div></div>
<div class="card" style="padding:16px"><div class=ch><h3>📥 {{fname}}</h3><a class="btn ghost" href=/parts/import/{{job}}/cancel>إلغاء</a></div>
<div class=pi-opt style="margin-top:10px"><label>إذا القطعة موجودة بنفس الاسم<select name=dup><option value=add>زيد الكمية وحدّث الأسعار<option value=skip>تخطّاها</select></label>
{% if mode!='tools' %}<label>المورد للقطع (اختياري)<select name=supplier_id><option value="">بدون<option disabled>──{% for s in sup %}<option value={{s.id}}>{{s.name}}{% endfor %}</select></label>{% endif %}</div></div>
{% macro rows_tbl(lst) %}<div style="overflow-x:auto"><table class=pi-tb><tr><th>ورقة · سطر<th>صورة<th>الاسم<th>الكمية<th>شراء<th>بيع<th>اللون<th>وجهتها</tr>
{% for r in lst %}<tr data-k="{{r.k}}" data-sh="{{r.si}}"><td class=nw><small>{{r.sh}} · {{r.r}}</small><td>{% if r.thumb %}<img class=pi-th src="data:image/jpeg;base64,{{r.thumb}}" alt="">{% else %}<small>—</small>{% endif %}<td><b>{{r.name}}</b>{% if r.sug %}<span class=pi-sug>💡 {{r.sug}}</span>{% endif %}<td>{{r.qty}}<td class=nw>{{ '%g'|format(r.cost) }}<td class=nw>{{ '%g'|format(r.price) }}<td>{{r.color or ''}}<td class=pi-sel data-v="{{r.dest}}"></tr>{% endfor %}</table></div>{% endmacro %}
{% if needs %}<div class="card" style="padding:16px" id=pi-needs><div class=ch><h3>🧐 محتاجة قرارك <span class=tag>{{needs|length}}</span></h3></div>
<p style="margin:4px 0">ما كنت متأكد وين لازم تروح هالقطع، فما حطيتها بمكان لحالي. اختر لكل وحدة وجهتها: قسم من قطع الغيار، أو <b>أدوات الصيانة</b>، أو تخطّي. أي وحدة بدون اختيار ما رح تنستورد.</p>
<div class=pi-bulk><span id=pi-bulk-w></span><button type=button class=ghost id=pi-bulk-go>طبّق على كل اللي بدون وجهة</button></div>
{{ rows_tbl(needs) }}</div>{% endif %}
<div class="card" style="padding:16px"><div class=ch><h3>🗂️ تصنيفها واضح <span class=tag>{{ total - needs|length }}</span></h3></div>
<p style="margin:4px 0"><small>افتح أي مجموعة إذا بدك تنقل قطعة منها لوجهة ثانية.</small></p>
{% for g in groups %}<details class=pi-g><summary><b>{{g.title}}</b> · {{g.n}}</summary>{{ rows_tbl(g.rows) }}{% if g.more %}<small>... و {{g.more}} قطعة غيرها بنفس القسم (بتنستورد بنفس التصنيف)</small>{% endif %}</details>{% endfor %}</div>
{% for sh in sheets %}<div class=card style="padding:16px"><div class=ch><h3>📄 {{sh.name}} <span class=tag>{{sh.rows|length}} قطعة</span>{% if sh.nimg %} <span class=tag>🖼️ {{sh.nimg}}</span>{% endif %}</h3>
<label style="font-weight:700"><input type=checkbox name=use{{sh.idx}} value=1 {{ 'checked' if sh.rows else 'disabled' }} data-n={{sh.rows|length}} class=pi-use> استيراد هالورقة</label></div>
{% if sh.guessed and sh.rows %}<div class=pi-w>⚠️ ما لقيت عناوين أعمدة بهالورقة، فخمّنت الأعمدة من محتواها. راجع الأعمدة وعدّل إذا لزم.</div>{% endif %}
{% if not sh.rows %}<div class=pi-w>ما لقيت قطع بهالورقة. اختر عمود الاسم تحت (وبعدين اضغط «تحديث المعاينة») أو ألغِ هالورقة.</div>{% endif %}
<details {{ 'open' if (not sh.rows or sh.guessed) }}><summary style="cursor:pointer;font-weight:700">الأعمدة المكتشفة (اضغط للتعديل)</summary><div class=pi-map>
{% for f in fields %}<label>{{fa[f]}}<select name=m{{sh.idx}}_{{f}}><option value="">— بدون —{% for c in sh.cols %}<option value={{loop.index0}} {{ 'selected' if (sh.mapping.get(f) and sh.mapping[f][0]==loop.index0) }}>{{c}}{% endfor %}</select><input type=hidden name=a{{sh.idx}}_{{f}} value="{{ sh.auto.get(f)[0] if sh.auto.get(f) else '' }}"></label>{% endfor %}</div>
<button type=submit formaction=/parts/import/{{job}}/refresh class=ghost>🔄 تحديث المعاينة</button></details>
{% if sh.skipped %}<small>تخطّيت {{sh.skipped|length}} سطر (بدون اسم أو غير صالح).</small>{% endif %}</div>{% endfor %}
<div class=card style="padding:16px;position:sticky;bottom:10px"><button id=pi-go style="font-size:16px;padding:12px 26px">استيراد <span id=pi-n>{{total}}</span> قطعة ←</button> <small id=pi-hint>كل قطعة بتنضاف للوجهة اللي حددتها، وبتقدر تعدّلها أو تحذفها بعدين.</small></div></form>
<script type=application/json id=pi-dests>{{ dests|tojson }}</script>
<script>(function(){var D=JSON.parse(document.getElementById('pi-dests').textContent);
function mk(v){var s=document.createElement('select');s.className='pi-d';var o=document.createElement('option');o.value='';o.textContent='— اختر الوجهة —';s.appendChild(o);D.forEach(function(d){var p=document.createElement('option');p.value=d[0];p.textContent=d[1];s.appendChild(p)});s.value=v||'';return s}
document.querySelectorAll('td.pi-sel').forEach(function(td){td.appendChild(mk(td.dataset.v))});
var bw=document.getElementById('pi-bulk-w');if(bw){var bs=mk('');bs.id='pi-bulk';bw.appendChild(bs)}
function on(si){var c=document.querySelector('input[name=use'+si+']');return c&&c.checked}
function calc(){var n=0,un=0,sk=0;document.querySelectorAll('.pi-use').forEach(function(c){if(c.checked)n+=+c.dataset.n});
document.querySelectorAll('tr[data-k]').forEach(function(tr){var v=tr.querySelector('select').value;tr.classList.toggle('pi-un',!v);if(!on(tr.dataset.sh))return;if(!v)un++;else if(v==='skip')sk++});
var go=Math.max(0,n-un-sk);document.getElementById('pi-n').textContent=go;document.getElementById('pi-go').disabled=!go;
var h=document.getElementById('pi-hint');if(un)h.textContent='⚠️ '+un+' قطعة لسا ما حددت وجهتها، رح تنتخطّى.';else h.textContent='كل قطعة بتنضاف للوجهة اللي حددتها، وبتقدر تعدّلها أو تحذفها بعدين.'}
document.addEventListener('change',function(e){var t=e.target;if(t.classList&&(t.classList.contains('pi-use')||t.classList.contains('pi-d')))calc()});
var bg=document.getElementById('pi-bulk-go');if(bg)bg.addEventListener('click',function(){var v=document.getElementById('pi-bulk').value;if(!v)return;document.querySelectorAll('#pi-needs tr[data-k] select').forEach(function(s){if(!s.value)s.value=v});calc()});
document.getElementById('pi-form').addEventListener('submit',function(){var d={};document.querySelectorAll('tr[data-k]').forEach(function(tr){d[tr.dataset.k]=tr.querySelector('select').value});document.getElementById('pi-dec').value=JSON.stringify(d)});
calc()})()</script>{% endblock %}"""

T_DONE = r"""{% extends 'base' %}{% block c %}
<style>.pd-g{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:12px 0}.pd-g a{display:block;border:1px solid var(--line,#e3e8f8);border-radius:16px;padding:14px;background:#fff;text-decoration:none;color:inherit}.pd-g b{display:block;font-size:26px}html[data-theme=dark] .pd-g a{background:#141b3a;border-color:#27315a}</style>
<div class=card style="padding:22px"><div class=ch><h3>✅ تم الاستيراد</h3><a class="btn ghost" href=/parts>كل القطع</a> <a class="btn ghost" href=/tools>أدوات الصيانة</a></div>
<p style="margin:6px 0">جديدة: <b>{{res.new}}</b> · محدّثة (زادت كميتها): <b>{{res.upd}}</b> · متخطّاة (موجودة أصلاً): <b>{{res.skip}}</b>{% if res.merged %} · مدموجة (مكررة بالملف): <b>{{res.merged}}</b>{% endif %}{% if res.photos %} · صور: <b>{{res.photos}}</b>{% endif %}{% if res.dropped %} · اخترت تخطّيها: <b>{{res.dropped}}</b>{% endif %}{% if res.unres %} · بدون وجهة (ما انستوردت): <b>{{res.unres}}</b>{% endif %}</p>
<div class=pd-g>{% for c,n in res.cats %}<a href="{{urls.get(c,'/parts')}}"><small>{{cplural.get(c,c)}}</small><b>{{n}}</b><small>افتح الصفحة ←</small></a>{% endfor %}</div>
{% if res.note %}<p><small>{{res.note}}</small></p>{% endif %}</div>{% endblock %}"""


def register(ns):
    app, T, q, ex, db, uid = ns["app"], ns["T"], ns["q"], ns["ex"], ns["db"], ns["uid"]
    render_template, redirect, request, abort, Response = ns["render_template"], ns["redirect"], ns["request"], ns["abort"], ns["Response"]
    notify, today = ns["notify"], ns["today"]
    CAT_PLURAL, CATS = ns["CAT_PLURAL"], ns["CATS"]
    CPL = dict(CAT_PLURAL); CPL[TOOLS] = "أدوات الصيانة"
    VALID = set(CATS) | {TOOLS, "skip"}
    T["pimport"], T["pimport2"], T["pimport3"] = T_UP, T_PV, T_DONE

    def dests():
        """خيارات «وين تروح» بالمعاينة."""
        return [[TOOLS, "🛠️ أدوات الصيانة"]] + [[c, "قطع: " + CPL.get(c, c)] for c in CATS] + [["skip", "⛔ تخطّي (لا تستورد)"]]

    def parse_dec(raw):
        try: d = json.loads(raw or "{}")
        except Exception: return {}
        if not isinstance(d, dict): return {}
        return {str(k): v for k, v in d.items() if isinstance(v, str) and (v == "" or v in VALID)}

    def dest_of(si, r, dec):
        """وجهة السطر: اللي اخترته إنت، وإلا التصنيف الواضح. اللي مش واضح (بدون اختيار) = '' يعني ما بينستورد."""
        k = "%d:%d" % (si, r["r"])
        if k in dec: return dec[k]
        return r["cat"] if (r["sure"] or r["cat"] != "أخرى") else ""

    def jname(job): return "imp-%s-%s" % (uid(), job)

    def load_job(job):
        if not re.fullmatch(r"[0-9a-f]{32}", job or ""): abort(404)
        r = q("select data,mime from files where name=?", (jname(job),))
        if not r: abort(404)
        p = (r[0]["mime"] or "").split("|", 2)
        mode = "tools" if len(p) == 3 and p[1] == "tools" else "parts"
        fname = p[-1] if len(p) >= 2 else "الملف"
        return bytes(r[0]["data"]), (".csv" if "csv" in p[0] else ".xlsx"), fname, mode

    def clean_old():
        try: ex("delete from files where name like 'imp-%' and created < ?", (today(),))
        except Exception: pass

    def big_upload():
        try: request.max_content_length = MAX_FILE + 1024 * 1024      # Flask 3.1+: حد خاص بهالطلب
        except Exception: pass

    def upload(mode):
        base = "/tools/import" if mode == "tools" else "/parts/import"
        if request.method == "POST":
            big_upload()
            f = request.files.get("file")
            if not f or not f.filename: notify("اختر ملف Excel أو CSV", "warn", "ما في ملف"); return redirect(base)
            ext = "." + f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
            if ext == ".xlsm": ext = ".xlsx"
            if ext not in (".xlsx", ".csv"): notify("الصيغ المدعومة: ‎.xlsx و ‎.csv. لو ملفك ‎.xls احفظه كـ ‎.xlsx من Excel.", "warn", "صيغة غير مدعومة"); return redirect(base)
            data = f.read()
            if len(data) > MAX_FILE: notify("الحد الأقصى 20 ميغا", "warn", "الملف كبير"); return redirect(base)
            try: parse_file(data, ext, images=False, mode=mode)
            except Exception as e:
                notify("الملف تالف أو مش Excel حقيقي: %s" % str(e)[:80], "warn", "تعذّر قراءة الملف"); return redirect(base)
            clean_old()
            job = uuid.uuid4().hex
            mime = ("text/csv" if ext == ".csv" else "application/x-xlsx") + "|" + mode + "|" + (f.filename or "file")[:80]
            ex("insert into files(name,mime,data,created) values(?,?,?,?)", (jname(job), mime, data, today()))
            return redirect("/parts/import/" + job)
        if mode == "tools":
            return render_template("pimport", mode=mode, ttl=("استيراد أدوات من Excel", "ارفع ملف الأدوات وإنت بتحدد وين تروح كل قطعة"))
        return render_template("pimport", mode=mode, ttl=("استيراد من Excel", "ارفع ملف الأعمدة والقطع وخلي البرنامج يفرزها وإنت بتقرر"))

    @app.route("/parts/import", methods=["GET", "POST"])
    def parts_import(): return upload("parts")

    @app.route("/tools/import", methods=["GET", "POST"])
    def tools_import(): return upload("tools")

    def overrides_from(form):
        ov = {}
        for k, v in form.items():
            m = re.fullmatch(r"m(\d+)_(\w+)", k)
            if not m or m.group(2) not in FIELDS: continue
            si, f = int(m.group(1)), m.group(2)
            auto = form.get("a%d_%s" % (si, f), "")
            if v == auto: continue                       # ما انلمس
            ov.setdefault(si, {})[f] = int(v) if v.isdigit() else None
        return ov

    def thumb(b):
        try:
            from PIL import Image
            im = Image.open(io.BytesIO(b)); im.thumbnail((84, 84)); buf = io.BytesIO(); im.convert("RGB").save(buf, "JPEG", quality=70)
            return base64.b64encode(buf.getvalue()).decode()
        except Exception: return None

    GROUP_CAP = 400

    def preview(job, ov=None, dec=None):
        data, ext, fname, mode = load_job(job)
        try: sheets = parse_file(data, ext, overrides=ov, images=True, mode=mode)
        except Exception as e:
            notify("تعذّر تحليل الملف: %s" % str(e)[:80], "warn", "خطأ"); return redirect("/parts/import")
        dec = dec or {}
        needs, groups = [], {}; nimg = 0; total = 0; nth = 0
        for sh in sheets:
            nimg += sh["nimg"]; total += len(sh["rows"])
            for n, r in enumerate(sh["rows"]):
                th = None
                if r["img"] and nth < 200 and (not r["sure"] or n < 15): th = thumb(r["img"]); nth += 1 if th else 0
                v = {"k": "%d:%d" % (sh["idx"], r["r"]), "si": sh["idx"], "sh": sh["name"], "r": r["r"], "name": r["name"], "qty": r["qty"], "cost": r["cost"],
                     "price": r["price"], "color": r["color"], "sug": r["sug"], "dest": dest_of(sh["idx"], r, dec), "thumb": th}
                r["img"] = None
                if not r["sure"]: needs.append(v)
                else: groups.setdefault(r["cat"], []).append(v)
        glist = [{"cat": c, "title": CPL.get(c, c), "n": len(rs), "rows": rs[:GROUP_CAP], "more": max(0, len(rs) - GROUP_CAP)} for c, rs in groups.items()]
        glist.sort(key=lambda g: -g["n"])
        return render_template("pimport2", job=job, fname=fname, sheets=sheets, total=total, nimg=nimg, needs=needs, groups=glist, mode=mode,
                               fields=FIELDS, fa=FIELD_AR, dests=dests(), sup=q("select * from suppliers where user_id=?", (uid(),)),
                               ttl=("معاينة الاستيراد", "راجع القطع وحدد وجهة كل وحدة قبل ما تتأكد"))

    @app.route("/parts/import/<job>")
    def parts_import_preview(job): return preview(job)

    @app.post("/parts/import/<job>/refresh")
    def parts_import_refresh(job): return preview(job, overrides_from(request.form), parse_dec(request.form.get("dec")))

    @app.route("/parts/import/<job>/cancel")
    def parts_import_cancel(job):
        back = "/parts"
        if re.fullmatch(r"[0-9a-f]{32}", job or ""):
            r = q("select mime from files where name=?", (jname(job),))
            if r and "|tools|" in (r[0]["mime"] or ""): back = "/tools"
            ex("delete from files where name=?", (jname(job),))
        return redirect(back)

    @app.post("/parts/import/<job>/run")
    def parts_import_run(job):
        data, ext, fname, mode = load_job(job); f = request.form
        ov = overrides_from(f); dec = parse_dec(f.get("dec"))
        use = {int(k[3:]) for k in f if re.fullmatch(r"use\d+", k)}
        if not use: notify("اختار ورقة وحدة على الأقل", "warn", "ما في شي للاستيراد"); return redirect("/parts/import/" + job)
        try: sheets = parse_file(data, ext, overrides=ov, images=True, only=use, mode=mode)
        except Exception as e:
            notify("تعذّر قراءة الملف: %s" % str(e)[:80], "warn", "خطأ"); return redirect("/parts/import")
        sup = f.get("supplier_id") or None
        if sup and not q("select 1 from suppliers where id=? and user_id=?", (sup, uid())): sup = None
        skip_dup = f.get("dup") == "skip"
        # توزيع القطع حسب قرارك + دمج المكرر داخل الملف نفسه
        merged_n = 0; unres = 0; dropped = 0; items = {}; titems = {}
        for sh in sheets:
            if sh["idx"] not in use: continue
            for r in sh["rows"]:
                dest = dest_of(sh["idx"], r, dec)
                if dest == "": unres += 1; continue
                if dest == "skip": dropped += 1; continue
                r = dict(r); r["cat"] = dest
                tgt = titems if dest == TOOLS else items
                key = (norm(r["name"]), dest, norm(r["color"]) if dest == "ظهر" else "")
                if key in tgt:
                    it = tgt[key]; it["qty"] += r["qty"]; merged_n += 1
                    for k2 in ("cost", "price"):
                        if not it[k2] and r[k2]: it[k2] = r[k2]
                    if not it["img"] and r["img"]: it["img"] = r["img"]
                else: tgt[key] = r
        u = uid(); d = db()
        existing = {}
        for p in q("select id,name,category,color,photo from parts where user_id=?", (u,)):
            existing[(norm(p["name"]), p["category"], norm(p["color"]) if p["category"] == "ظهر" else "")] = p
        existing_t = {}
        for t in q("select id,name,photo from tools where user_id=?", (u,)): existing_t[norm(t["name"])] = t
        used_bc = {r["barcode"] for r in q("select barcode from parts where user_id=? and barcode is not null", (u,))} | {r["barcode"] for r in q("select barcode from tools where user_id=? and barcode is not null", (u,))}
        res = {"new": 0, "upd": 0, "skip": 0, "photos": 0, "merged": merged_n, "unres": unres, "dropped": dropped, "cats": {}, "note": ""}

        def mkphoto(r):
            if not r["img"]: return None
            name = uuid.uuid4().hex + ".jpg"
            d.execute("insert into files(name,mime,data,created) values(?,?,?,?)", (name, "image/jpeg", r["img"], today()))
            return name
        try:
            for key, r in items.items():
                photo = None
                ex_row = existing.get(key)
                if ex_row:
                    if skip_dup: res["skip"] += 1; continue
                    photo = mkphoto(r) if not ex_row["photo"] else None
                    sets, args = ["qty=qty+?"], [r["qty"]]
                    if r["cost"]: sets.append("cost=?"); args.append(r["cost"])
                    if r["price"]: sets.append("price=?"); args.append(r["price"])
                    if photo: sets.append("photo=?"); args.append(photo); res["photos"] += 1
                    d.execute("update parts set %s where id=? and user_id=?" % ",".join(sets), args + [ex_row["id"], u])
                    res["upd"] += 1
                else:
                    photo = mkphoto(r)
                    bc = r["barcode"] if r["barcode"] and r["barcode"] not in used_bc else None
                    if bc: used_bc.add(bc)
                    color, hx = (r["color"] or "—", color_hex(r["color"])) if r["cat"] == "ظهر" else (None, None)
                    d.execute("insert into parts(name,category,qty,min_qty,cost,price,supplier_id,user_id,photo,barcode,color,hex) values(?,?,?,?,?,?,?,?,?,?,?,?)",
                              (r["name"], r["cat"], r["qty"], r["min_qty"], r["cost"], r["price"], sup, u, photo, bc, color, hx))
                    if photo: res["photos"] += 1
                    res["new"] += 1
                res["cats"][r["cat"]] = res["cats"].get(r["cat"], 0) + 1
            for key, r in titems.items():
                ex_row = existing_t.get(key[0])
                if ex_row:
                    if skip_dup: res["skip"] += 1; continue
                    photo = mkphoto(r) if not ex_row["photo"] else None
                    sets, args = ["qty=coalesce(qty,0)+?"], [r["qty"] or 0]
                    if r["cost"]: sets.append("cost=?"); args.append(r["cost"])
                    if r["price"]: sets.append("price=?"); args.append(r["price"])
                    if photo: sets.append("photo=?"); args.append(photo); res["photos"] += 1
                    d.execute("update tools set %s where id=? and user_id=?" % ",".join(sets), args + [ex_row["id"], u])
                    res["upd"] += 1
                else:
                    photo = mkphoto(r)
                    bc = r["barcode"] if r["barcode"] and r["barcode"] not in used_bc else None
                    if bc: used_bc.add(bc)
                    d.execute("insert into tools(user_id,name,category,qty,cost,location,notes,photo,created,price,barcode) values(?,?,?,?,?,?,?,?,?,?,?)",
                              (u, r["name"], r["tcat"] or "", r["qty"] if r["qty"] else 1, r["cost"], "", "", photo, today(), r["price"], bc))
                    if photo: res["photos"] += 1
                    res["new"] += 1
                res["cats"][TOOLS] = res["cats"].get(TOOLS, 0) + 1
            d.commit()
        except Exception as e:
            try: d.rollback()
            except Exception: pass
            notify("ما انحفظ شي: %s" % str(e)[:100], "warn", "فشل الاستيراد"); return redirect("/parts/import/" + job)
        ex("delete from files where name=?", (jname(job),))
        notify("جديد %d · محدّث %d · متخطّى %d%s" % (res["new"], res["upd"], res["skip"], " · صور %d" % res["photos"] if res["photos"] else ""), "ok", "تم الاستيراد")
        notes = []
        if any(r["qty"] <= 0 for r in items.values()): notes.append("بعض القطع انضافت بكمية 0 لأن الملف ما فيه كمية لها. عدّل الكمية من صفحتها.")
        if any(not r["qty"] for r in titems.values()): notes.append("الأدوات اللي ما إلها كمية بالملف انضافت بعدد 1.")
        if unres: notes.append("%d قطعة ما انستوردت لأنك ما حددت وجهتها. ارفع الملف مرة ثانية وحدد وجهتها (اللي انستورد بالمرة الأولى بتتخطاه أو بتزيد كميته حسب اختيارك)." % unres)
        res["note"] = " ".join(notes)
        res["cats"] = sorted(res["cats"].items(), key=lambda t: -t[1])
        return render_template("pimport3", res=res, urls=CAT_URL, cplural=CPL, ttl=("تم الاستيراد", "القطع انضافت للوجهات اللي حددتها"))

    def _xl_template(sheets, headers, widths, fname):
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
        wb = Workbook(); first = True
        for title, rows in sheets.items():
            ws = wb.active if first else wb.create_sheet(); first = False; ws.title = title; ws.sheet_view.rightToLeft = True
            ws.append(headers)
            for c in ws[1]: c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="4F46E5"); c.alignment = Alignment(horizontal="center")
            for r in rows: ws.append(r)
            for col, w in zip("ABCDEF", widths): ws.column_dimensions[col].width = w
        buf = io.BytesIO(); wb.save(buf)
        return Response(buf.getvalue(), mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": "attachment; filename=" + fname})

    @app.route("/parts/import/template.xlsx")
    def parts_import_template():
        data = {"شاشات": [["شاشة Samsung A12", 5, 60, 95, ""], ["شاشة iPhone 11", 3, 110, 160, ""]],
                "بطاريات": [["بطارية Redmi Note 9", 10, 18, 35, ""], ["بطارية iPhone XR", 4, 25, 45, ""]],
                "ظهور": [["ظهر iPhone 13", 2, 20, 40, "أسود"], ["ظهر iPhone 13", 1, 20, 40, "أزرق"]]}
        return _xl_template(data, ["اسم القطعة", "الكمية", "سعر الشراء", "سعر البيع", "اللون"], (30, 10, 12, 12, 14), "repairix_parts_template.xlsx")

    @app.route("/tools/import/template.xlsx")
    def tools_import_template():
        data = {"أدوات الصيانة": [["طاولة صيانة", 1, 350, 0, "طاولات وتجهيزات"], ["هيتر هواء ساخن", 2, 120, 0, "تسخين وهواء ساخن"], ["طقم مفكات", 3, 25, 40, "مفكات"]]}
        return _xl_template(data, ["اسم الأداة", "العدد", "سعر الشراء", "سعر البيع", "التصنيف"], (30, 10, 12, 12, 22), "repairix_tools_template.xlsx")
