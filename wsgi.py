# نقطة الدخول لـ gunicorn:  gunicorn wsgi:application
import app as shop
shop.start()          # الجداول + حساب المالك
application = shop.app
