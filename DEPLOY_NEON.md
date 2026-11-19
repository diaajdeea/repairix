# REPAIRIX على Neon (Postgres)

كل البيانات **والصور** صارت بقاعدة Neon. ما في SQLite ولا Firestore ولا مجلد uploads.
النتيجة: السيرفر بلا حالة، فبتقدر تشغّل أكثر من نسخة وتنشر على أي استضافة (Cloud Run، Render، Fly، VPS...).

## 1) تجهيز Neon (مرة وحدة)
1. console.neon.tech ← New Project (اختر المنطقة الأقرب لسيرفرك).
2. زر **Connect** ← انسخ الرابط **Pooled connection** (اسم الهوست فيه `-pooler`). شكله:
   `postgresql://user:pass@ep-xxxx-pooler.region.aws.neon.tech/neondb?sslmode=require`
3. حطه كمتغير بيئة `DATABASE_URL`، أو بملف `.env` جنب `app.py` (للتشغيل المحلي):
   ```
   DATABASE_URL=postgresql://...
   ```
   لا ترفع `.env` لأي مكان ولا ترسل الرابط لأحد (فيه كلمة السر).

الجداول بتنعمل تلقائياً أول تشغيل من `schema.sql`.

## 2) تشغيل محلي
```
pip install -r requirements.txt
python app.py          # أو run.bat / run.sh
```
حساب المالك: `OWNER_EMAIL` و`OWNER_PASSWORD` (إذا ما عيّنت كلمة سر بتنطبع مؤقتة بالكونسول أول مرة).
حساب تجريبي (للتجربة بس): `python seed_demo.py` ← demo@demo.com / demo123.

## 3) نقل بياناتك القديمة
شغّل سكربت واحد، حسب وين بياناتك:

**من ملف shop.db (SQLite):**
```
python migrate_to_neon.py --sqlite shop.db --uploads uploads
```
**مباشرة من Firebase (Firestore + Storage):**
```
pip install firebase-admin
python migrate_to_neon.py --firebase --key firebase-key.json --bucket my-project.firebasestorage.app
```
- جرّب أول: `--dry-run` (بيعدّ الصفوف بدون كتابة).
- إذا Neon فيه بيانات بيرفض، إلا مع `--wipe` (بيمسح Neon وينقل من جديد).
- الصور بتنتقل لجدول `files`، وبيطبع لك أي صورة ناقصة بالمصدر.
- الترحيل بيحافظ على أرقام الـ id، وبيضبط العدّادات عشان الإدخالات الجديدة تكمل صح.

## 4) النشر (مثال Cloud Run)
```
gcloud run deploy repairix --source . --region europe-west1 --allow-unauthenticated \
  --set-env-vars DATABASE_URL=...,SECRET_KEY=...,OWNER_PASSWORD=...,APP_URL=https://رابط-الخدمة
```
- `SECRET_KEY` لازم يكون ثابت (`python -c "import secrets;print(secrets.token_hex(32))"`).
- الأفضل تحط `DATABASE_URL` و`SECRET_KEY` و`OWNER_PASSWORD` بـ Secret Manager.
- ما عاد في قيد `max-instances 1` ولا `workers 1`.

## ملاحظات
- **الرابط المجمّع (-pooler)** هو المطلوب للتطبيق؛ الكود بيعطّل prepared statements تلقائياً عشان يشتغل معه.
- Neon بيوقف الحساب المجاني بعد فترة خمول، فأول طلب بعدها ممكن ياخد ثانية أو ثانيتين.
- الصور بتتخزن بالقاعدة (حد الرفع 6 ميجا للطلب). الخطة المجانية فيها مساحة محدودة، فراقب حجم جدول `files` إذا في صور كثيرة.
- حذف قطعة/شيك/مرتجع بيحذف صورته من القاعدة تلقائياً.
- للتجربة الآمنة: أنشئ **Branch** من Neon وشغّل `python tests/smoke_neon.py` عليه قبل ما تحط بيانات حقيقية.
- فحص صفحات المتجر الجديدة (/store, /sales, /tools) مضمّن بـ `tests/smoke_neon.py` لأنه بيفتح كل صفحات GET.
- لو عندك بيانات قديمة فيها المتجر/الأدوات (من ملف shop.db)، `migrate_to_neon.py` بينقل جداول tools وsales وsale_items وصور الأدوات كمان.
