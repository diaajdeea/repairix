-- REPAIRIX: مخطط Postgres (Neon). آمن للتشغيل أكثر من مرة (if not exists).
-- ملاحظة: كل المبالغ double precision (مثل real في SQLite) والتواريخ نص ISO زي ما كانت.

create table if not exists users(
  id serial primary key, email text unique, pw text,
  created text, last_login text, last_seen text, sub_end text, blocked int default 0);

create table if not exists settings(
  user_id integer primary key, shop_name text, cc text,
  trial_start text, logo text, fx_usd double precision, fx_jod double precision);

create table if not exists password_resets(
  id serial primary key, user_id int, token_hash text, expires text, created text, used int default 0);

create table if not exists notifications(
  id serial primary key, user_id int, msg text, kind text, created text, seen int default 0);

create table if not exists suppliers(
  id serial primary key, name text, phone text, notes text, user_id int);

create table if not exists parts(
  id serial primary key, name text, category text, qty int default 0, min_qty int default 2,
  cost double precision default 0, price double precision default 0, supplier_id int, user_id int,
  photo text, color text, hex text);

create table if not exists invoices(
  id serial primary key, user_id int, supplier_id int, created text, total double precision);

create table if not exists needs(
  id serial primary key, user_id int, kind text, part_id int, name text, qty int,
  cost double precision, supplier_id int, note text, invoice_id int, created text,
  auto int default 0, ret_id int);

create table if not exists needs_dismissed(
  user_id int, part_id int, qty int, primary key(user_id, part_id));

create table if not exists repairs(
  id serial primary key, created text, customer text, phone text, device text, issue text, part_id int,
  cost double precision default 0, price double precision default 0,
  status text default 'قيد الصيانة', done_date text, user_id int);

create table if not exists repair_parts(
  id serial primary key, repair_id int, part_id int, cost double precision, user_id int);

create table if not exists employees(
  id serial primary key, user_id int, name text, phone text, role text, notes text, created text,
  login text, pw text, must_change int default 0);

create table if not exists emp_stock_log(
  id serial primary key, user_id int, emp_id int, part_id int, part_name text, kind text, qty int,
  note text, created text, unit_price double precision, cost double precision,
  customer_id int, customer_name text);

create table if not exists emp_customers(
  id serial primary key, user_id int, emp_id int, name text, shop text, location text, phone text, created text);

create table if not exists debtors(
  id serial primary key, user_id int, name text, phone text, note text, created text);

create table if not exists debt_entries(
  id serial primary key, user_id int, debtor_id int, kind text, amount double precision, method text,
  check_no text, bank text, due text, status text, note text, created text, item text);

create table if not exists cheques(
  id serial primary key, user_id int, person_id int, number text, bank text, amount double precision,
  drawer text, due text, status text default 'لم يُصرف', photo text, note text, on_debt int default 1,
  created text, cashed_date text);

create table if not exists returns_log(
  id serial primary key, user_id int, part_id int, part_name text, category text, qty int,
  unit_cost double precision, total double precision, supplier_id int, supplier_name text,
  reason text, note text, created text, emp_id int, emp_name text, photo text, emp_log_id int);

create table if not exists meta(k text primary key, v text);

-- المتجر: أدوات الصيانة + فواتير البيع
create table if not exists tools(
  id serial primary key, user_id int, name text, category text, qty int default 1,
  cost double precision default 0, location text, notes text, photo text, created text,
  price double precision default 0);

create table if not exists sales(
  id serial primary key, user_id int, person_id int, person_name text, person_phone text, created text,
  subtotal double precision default 0, discount double precision default 0, total double precision default 0,
  paid double precision default 0, method text, note text);

create table if not exists sale_items(
  id serial primary key, user_id int, sale_id int, part_id int, tool_id int, name text, category text,
  qty int, price double precision, cost double precision);

alter table debt_entries add column if not exists sale_id int;

-- الصور (قطع، شيكات، مرتجعات، شعار) بتتخزن بالقاعدة بدل مجلد uploads
create table if not exists files(
  name text primary key, mime text, data bytea not null, created text);

-- فهارس للاستعلامات الشائعة (كلها حسب الشركة user_id)
create index if not exists ix_parts_user on parts(user_id);
create index if not exists ix_repairs_user on repairs(user_id, created);
create index if not exists ix_repair_parts_repair on repair_parts(repair_id);
create index if not exists ix_needs_user on needs(user_id);
create index if not exists ix_needs_invoice on needs(invoice_id);
create index if not exists ix_notif_user on notifications(user_id, id);
create index if not exists ix_suppliers_user on suppliers(user_id);
create index if not exists ix_invoices_user on invoices(user_id);
create index if not exists ix_emp_user on employees(user_id);
create index if not exists ix_esl_emp on emp_stock_log(user_id, emp_id);
create index if not exists ix_ecust_emp on emp_customers(emp_id);
create index if not exists ix_debtors_user on debtors(user_id);
create index if not exists ix_debt_entries_debtor on debt_entries(user_id, debtor_id);
create index if not exists ix_cheques_person on cheques(user_id, person_id);
create index if not exists ix_returns_user on returns_log(user_id);
create index if not exists ix_emp_login on employees(lower(login));
create index if not exists ix_tools_user on tools(user_id);
create index if not exists ix_sales_user on sales(user_id, id);
create index if not exists ix_sale_items_sale on sale_items(sale_id);
create index if not exists ix_debt_entries_sale on debt_entries(sale_id);

-- حسابات جديدة: بيانات التسجيل + حالة الموافقة عبر واتساب
alter table users add column if not exists first_name text;
alter table users add column if not exists last_name text;
alter table users add column if not exists full_name text;
alter table users add column if not exists phone text;
alter table users add column if not exists status text default 'active';
alter table users add column if not exists approval_code text;
alter table users add column if not exists approval_tries int default 0;
alter table users add column if not exists approval_requested text;
alter table users add column if not exists approved_at text;
alter table users add column if not exists username text;
create unique index if not exists users_username_uq on users (lower(username)) where username is not null;
alter table parts add column if not exists barcode text;
alter table tools add column if not exists barcode text;
alter table settings add column if not exists address text;
create unique index if not exists parts_barcode_uq on parts (user_id, barcode) where barcode is not null and barcode <> '';

-- الصندوق المالي
create table if not exists cash_entries(
  id serial primary key, user_id int, created text, kind text, direction text, amount double precision,
  account text, category text, supplier_id int, note text, created_at text);
create table if not exists cash_counts(
  id serial primary key, user_id int, created text, expected double precision, counted double precision, note text);
alter table settings add column if not exists cash_open double precision default 0;
alter table settings add column if not exists bank_open double precision default 0;
create index if not exists ix_cash_user on cash_entries(user_id);

-- مرتجع من صيانة + أطراف تقسيم المربح
alter table returns_log add column if not exists repair_id int;
alter table settings add column if not exists partners text;

create table if not exists emp_cust_pay(
  id serial primary key, user_id int, emp_id int, customer_id int, amount double precision,
  note text, created text, by_owner int default 0, log_id int);
alter table emp_stock_log add column if not exists pay_tracked int default 0;

alter table parts add column if not exists emp_price double precision;
alter table emp_stock_log add column if not exists emp_price double precision;
alter table emp_stock_log add column if not exists co_cost double precision;
create table if not exists emp_co_pay(
  id serial primary key, user_id int, emp_id int, amount double precision, note text, created text);
create table if not exists emp_queue(
  id serial primary key, user_id int, emp_id int, customer_id int, customer_name text, part_id int, item text,
  qty int default 1, note text, status text default 'waiting', created text, done_at text);

-- دفعات الموردين: وصل التحويل البنكي (صورة/PDF بجدول files)
alter table cash_entries add column if not exists receipt text;
-- كمية مطلوبة معدّلة يدوياً (ما بتنكتب فوقها من النواقص التلقائية)
alter table needs add column if not exists qty_locked int default 0;
-- فواتير تسليم البضاعة للموظفين
create table if not exists emp_invoices(
  id serial primary key, user_id int, emp_id int, created text, total double precision default 0, note text);
alter table emp_stock_log add column if not exists inv_id int;
create index if not exists ix_emp_inv on emp_invoices(user_id, emp_id);

-- دفعات الموظفين للشركة: الطريقة (نقد/بنك) + وصل التحويل
alter table emp_co_pay add column if not exists method text;
alter table emp_co_pay add column if not exists receipt text;

-- دفعة رحّلها الموظف بنفسه
alter table emp_co_pay add column if not exists by_emp int default 0;

-- إقفال الصندوق اليومي: لقطة لكل يوم (دخل، مصاريف، مربح، المعدود، المسحوب)
create table if not exists day_closings(
  id serial primary key, user_id int, day text, closed_at text, expected double precision, counted double precision,
  withdrawn double precision, diff double precision, income double precision, expenses double precision, profit double precision,
  note text, withdraw_entry_id int, adjust_entry_id int);
create index if not exists ix_day_closings on day_closings(user_id, day);

-- الشركة المصنعة للقطعة (شاشات وبطاريات: أصلية، OEM، JK...)
alter table parts add column if not exists maker text;
