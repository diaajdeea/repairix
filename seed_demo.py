# يعبّي حساب تجريبي ببيانات جاهزة: demo@demo.com / demo123
import random, datetime
from werkzeug.security import generate_password_hash
import app, pgdb

app.init()
c = pgdb.connect()
EMAIL = "demo@demo.com"
if c.execute("select 1 from users where email=?", (EMAIL,)).fetchone():
    print("الحساب التجريبي موجود من قبل."); c.close(); raise SystemExit
random.seed(7)
today = datetime.date.today()
uid = c.execute("insert into users(email,pw) values(?,?)", (EMAIL, generate_password_hash("demo123"))).lastrowid
c.execute("insert into settings(user_id,shop_name,cc,trial_start) values(?,?,?,?)", (uid, "شركة النور للصيانة", "970", today.isoformat()))

sup = [c.execute("insert into suppliers(name,phone,notes,user_id) values(?,?,?,?)", (n, p, t, uid)).lastrowid for n, p, t in [
    ("مؤسسة الأمل للاتصالات", "0599111222", "شاشات وبطاريات، التوصيل خلال يومين"),
    ("محلات النجاح", "0569333444", "قواعد شحن وآيسيات"),
    ("مورد الخليل", "0598555666", "أسعار جملة، الدفع أسبوعي")]]
P = [("بطارية iPhone 11", "بطارية", 8, 3, 35, 80, 0), ("بطارية Samsung A12", "بطارية", 2, 3, 20, 55, 0),
     ("شاشة Samsung A12", "شاشة", 5, 2, 60, 140, 0), ("شاشة iPhone XR", "شاشة", 1, 2, 90, 200, 0),
     ("قاعدة شحن Redmi Note 10", "قاعدة شحن", 10, 3, 8, 30, 1), ("قاعدة شحن iPhone 11", "قاعدة شحن", 6, 3, 15, 45, 1),
     ("آيسي شحن Samsung A50", "آيسي", 4, 2, 12, 50, 1), ("آيسي طاقة Redmi 9", "آيسي", 3, 2, 18, 65, 2),
     ("شاشة iPhone 13", "شاشة", 3, 2, 150, 320, 0), ("شاشة Redmi Note 10", "شاشة", 4, 2, 55, 130, 2),
     ("قاعدة شحن Samsung A12", "قاعدة شحن", 9, 3, 7, 28, 1), ("بطارية Redmi Note 10", "بطارية", 6, 3, 22, 60, 0),
     ("سماعة AirPods Pro (نسخة)", "سماعات", 6, 2, 45, 110, 1), ("سماعة JBL سلكية", "سماعات", 12, 3, 6, 25, 1)]
pid = [c.execute("insert into parts(name,category,qty,min_qty,cost,price,supplier_id,user_id) values(?,?,?,?,?,?,?,?)",
                 (n, k, q, m, co, pr, sup[s], uid)).lastrowid for n, k, q, m, co, pr, s in P]

BACKS = [("iPhone 14 Pro Max", 90, 200, [("بنفسجي داكن", "#594f63", 3), ("ذهبي", "#f4e8ce", 5), ("فضي", "#e6e8ea", 1), ("أسود فضائي", "#3b3b3d", 4)]),
         ("iPhone 13 Pro Max", 80, 180, [("أزرق سييرا", "#9bb5ce", 2), ("أخضر ألباين", "#4e5851", 3), ("ذهبي", "#fad7bd", 4), ("جرافيت", "#54524f", 2)]),
         ("Samsung S23 Ultra", 70, 160, [("أخضر", "#3f5a4e", 4), ("كريمي", "#e8dfd0", 2), ("أسود", "#1c1c1e", 6), ("لافندر", "#c9bfd8", 3)])]
for m, co, pr, cols in BACKS:
    for cn, hx, qy in cols:
        c.execute("insert into parts(name,category,qty,min_qty,cost,price,supplier_id,user_id,color,hex) values(?,?,?,?,?,?,?,?,?,?)", (m, "ظهر", qy, 2, co, pr, sup[0], uid, cn, hx))

jobs = [("Samsung A12", "شاشة مكسورة", [2]), ("iPhone 11", "البطارية بتخلص بسرعة", [0]), ("Redmi Note 10", "ما بيشحن", [4]),
        ("iPhone XR", "شاشة مكسورة", [3]), ("Samsung A50", "ما بيشحن", [6]), ("Redmi 9", "ما بيشتغل", [7]),
        ("Samsung A12", "شاشة وبطارية", [2, 1]), ("iPhone 11", "ما بيشحن", [5])]
names = ["أحمد", "محمد", "سامر", "خالد", "ليلى", "رنا", "عمر", "يوسف", "هبة", "ناصر"]

def add(day, status, done):
    dev, issue, ps = random.choice(jobs)
    cost = sum(P[i][4] for i in ps); price = sum(P[i][5] for i in ps) + random.choice([20, 30, 40])
    rid = c.execute("insert into repairs(created,customer,phone,device,issue,cost,price,status,done_date,user_id) values(?,?,?,?,?,?,?,?,?,?)",
                    (day.isoformat(), random.choice(names), "05%s%07d" % (random.choice("96"), random.randint(0, 9999999)),
                     dev, issue, cost, price, status, day.isoformat() if done else None, uid)).lastrowid
    for i in ps:
        c.execute("insert into repair_parts(repair_id,part_id,cost,user_id) values(?,?,?,?)", (rid, pid[i], P[i][4], uid))

for _ in range(22): add(today - datetime.timedelta(days=random.randint(0, 12)), "تم التسليم", True)
for _ in range(3): add(today, "قيد الصيانة", False)
for _ in range(2): add(today - datetime.timedelta(days=1), "جاهز", False)

now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
for kind, msg in [("warn", "قطعة بطارية Samsung A12 قربت تخلص (الكمية 2)"), ("warn", "قطعة شاشة iPhone XR قربت تخلص (الكمية 1)"),
                  ("ok", "تمت إضافة قطعة: آيسي طاقة Redmi 9 (الكمية 3)"), ("ok", "تم تسجيل صيانة جديدة للزبون أحمد")]:
    c.execute("insert into notifications(user_id,msg,kind,created) values(?,?,?,?)", (uid, msg, kind, now))
c.commit(); c.close()
print("تم! سجّل دخول بـ demo@demo.com وكلمة السر demo123")
