# -*- coding: utf-8 -*-
"""
serve.py - تشغيل موقع REPAIRIX على الشبكة المحلية (هاتف / تابلت / كمبيوتر آخر)
الاستخدام:
    python serve.py                 -> تشغيل عادي على المنفذ 5000
    python serve.py --port 8080     -> منفذ مختلف
    python serve.py --tunnel        -> رابط إنترنت مؤقت عبر cloudflared (إن كان مثبّتاً)
الهاتف والكمبيوتر لازم يكونوا على نفس شبكة الواي فاي.
"""
import os, sys, socket, secrets, argparse, subprocess, shutil, re, threading

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)

# مفتاح سرّي ثابت (حتى ما ينفصل المستخدمون عند إعادة التشغيل)
if not os.environ.get("SECRET_KEY"):
    kf = os.path.join(HERE, ".secret_key")
    if not os.path.exists(kf):
        with open(kf, "w") as f: f.write(secrets.token_hex(32))
    os.environ["SECRET_KEY"] = open(kf).read().strip()


def lan_ips():
    ips = set()
    try:                            # الطريقة الأدق: IP الواجهة اللي بتطلع للشبكة
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1)); ips.add(s.getsockname()[0]); s.close()
    except Exception:
        pass
    try:
        for i in socket.gethostbyname_ex(socket.gethostname())[2]: ips.add(i)
    except Exception:
        pass
    return sorted(i for i in ips if not i.startswith("127."))


def show_qr(url):
    try:
        import qrcode
        q = qrcode.QRCode(border=1); q.add_data(url); q.make(fit=True); q.print_ascii(invert=True)
    except Exception:
        print("   (لعرض QR للمسح بالهاتف: pip install qrcode)")


def banner(port):
    print("\n" + "=" * 58)
    print("  REPAIRIX شغّال ✅")
    print("  على هذا الكمبيوتر :  http://127.0.0.1:%d" % port)
    ips = lan_ips()
    if ips:
        print("  من الهاتف/الأجهزة الأخرى (نفس الواي فاي):")
        for ip in ips: print("      http://%s:%d" % (ip, port))
        show_qr("http://%s:%d" % (ips[0], port))
    else:
        print("  ما لقيت عنوان شبكة، تأكد إنك متصل بالواي فاي.")
    print("  للإيقاف: Ctrl+C")
    print("=" * 58 + "\n", flush=True)


def start_tunnel(port):
    exe = shutil.which("cloudflared")
    if not exe:
        print("⚠ cloudflared غير مثبّت. نزّله من:\n  https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/\n  (بدونه الموقع يشتغل على الواي فاي فقط)")
        return
    p = subprocess.Popen([exe, "tunnel", "--url", "http://127.0.0.1:%d" % port],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    def rd():
        for line in p.stdout:
            m = re.search(r"https://[-a-z0-9]+\.trycloudflare\.com", line)
            if m:
                print("\n🌍 رابط الإنترنت المؤقت (يفتح من أي مكان): %s\n" % m.group(0), flush=True)
                os.environ["APP_URL"] = m.group(0)
    threading.Thread(target=rd, daemon=True).start()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 5000)))
    ap.add_argument("--tunnel", action="store_true", help="رابط إنترنت مؤقت عبر cloudflared")
    ap.add_argument("--seed", action="store_true", help="أضف الحساب التجريبي demo@demo.com (للتجربة فقط، لا تستخدمه على قاعدة حقيقية)")
    a = ap.parse_args()

    import app as shop
    shop.start()
    if a.seed:
        try:
            import seed_demo   # حساب تجريبي: demo@demo.com / demo123
        except SystemExit:
            pass

    if a.tunnel: start_tunnel(a.port)
    banner(a.port)
    try:
        from waitress import serve        # أفضل للإنتاج إن كان مثبّتاً
        serve(shop.app, host="0.0.0.0", port=a.port, threads=8)
    except ImportError:
        shop.app.run(host="0.0.0.0", port=a.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
