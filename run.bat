@echo off
rem تشغيل محلي: القاعدة ملف repair_shop.db جنب البرنامج (ما بتحتاج إنترنت)
pip install -r requirements.txt
rem python seed_demo.py   (اختياري: حساب تجريبي demo@demo.com / demo123 - للتجربة فقط)
start http://127.0.0.1:5000
python app.py
