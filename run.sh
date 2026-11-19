#!/bin/sh
# تشغيل محلي: القاعدة ملف repair_shop.db جنب البرنامج (ما بتحتاج إنترنت)
pip install -r requirements.txt
# python3 seed_demo.py   # اختياري: حساب تجريبي demo@demo.com / demo123 (للتجربة فقط)
python3 app.py
