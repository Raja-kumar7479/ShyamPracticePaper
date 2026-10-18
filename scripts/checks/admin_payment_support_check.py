import json, os, sys
from datetime import datetime, timedelta
import mysql.connector
from dotenv import dotenv_values

ROOT = '/Users/apple/Downloads/ShyamPracticePp'
ADMIN_EMAIL = 'rajakumarvijeta7087@gmail.com'
STUDENT = 'selftest.payments@example.com'
SID = 'SELFTESTADMPAY'
v = dotenv_values(f'{ROOT}/user_app/.env')

def db(q, p=()):
    c = mysql.connector.connect(host=v['DATABASE_HOST'], user=v['DATABASE_USER'], password=v['DATABASE_PASSWORD'], database=v['DATABASE_NAME'], autocommit=True)
    cur = c.cursor(dictionary=True); cur.execute(q, p); out = cur.fetchall() if cur.with_rows else []; cur.close(); c.close(); return out
results = []
def check(name, ok, detail=''):
    results.append(bool(ok)); print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ''))

def cleanup():
    db("DELETE FROM purchase WHERE email=%s OR payment_id LIKE 'pay_SELFTESTADM%'", (STUDENT,))
    db("DELETE FROM content_orders WHERE email=%s", (STUDENT,))
    db("DELETE FROM pcp_subscriptions WHERE email=%s", (STUDENT,))
    db("DELETE FROM enrollment WHERE email=%s", (STUDENT,))
    db("DELETE FROM auth WHERE email=%s", (STUDENT,))
    db("DELETE FROM course_content WHERE section_id=%s", (SID,))

cleanup()
course = db("SELECT code, name FROM courses ORDER BY code LIMIT 1")[0]
CODE, NAME = course['code'], course['name']
db("INSERT INTO auth (username, email, password, auth_type, is_verified) VALUES ('SELFTEST Payments', %s, 'x', 'manual', 1)", (STUDENT,))
db("INSERT INTO course_content (code,name,stream,section,section_id,title,subtitle,label,price,discount,details,status)"
   " VALUES (%s,%s,'Self test','mock_test',%s,'SELFTEST admin pay block','s','Paid',700,0,'<p>x</p>','active')", (CODE, NAME, SID))
CART = [{'title': 'SELFTEST admin pay block', 'subtitle': 's', 'price': 700.0, 'section': 'mock_test', 'section_id': SID}]
ago = lambda m: datetime.now() - timedelta(minutes=m)
def order(oid, status='created', pid=None, minutes=10, amount=70000):
    db("INSERT INTO content_orders (email, username, phone, course_code, razorpay_order_id, razorpay_payment_id, amount_paise, list_paise, discount_pct, cart_json, status, created_at)"
       " VALUES (%s,'SELFTEST Payments','9999999999',%s,%s,%s,%s,%s,0,%s,%s,%s)", (STUDENT, CODE, oid, pid, amount, amount, json.dumps(CART), status, ago(minutes)))
def sub(oid, status='created', pid=None, minutes=10, amount=120000, ends=None):
    db("INSERT INTO pcp_subscriptions (email, course_code, plan, plan_label, amount_paise, list_paise, discount_pct, razorpay_order_id, razorpay_payment_id, status, starts_at, expires_at, plan_ends_at, created_at)"
       " VALUES (%s,%s,'selftest-adm','SELFTEST admin plan',%s,%s,0,%s,%s,%s,%s,%s,%s,%s)",
       (STUDENT, CODE, amount, amount, oid, pid, status, ago(minutes) if status == 'active' else None,
        (datetime.now() + timedelta(days=200)) if status == 'active' else None, ends or datetime.now() + timedelta(days=200), ago(minutes)))
def purchase(pid, status='Paid'):
    db("INSERT INTO purchase (email, username, phone, title, subtitle, price, original_price, discount_percent, final_price, payment_date, payment_id, status, purchase_code, course_code, section, section_id, payment_mode)"
       " VALUES (%s,'SELFTEST Payments','9999999999','SELFTEST admin pay block','s',700,700,0,700,NOW(),%s,%s,'SELFTESTPC1',%s,'mock_test',%s,'razorpay')", (STUDENT, pid, status, CODE, SID))

os.chdir(f'{ROOT}/admin_app'); sys.path.insert(0, f'{ROOT}/admin_app')
from app import app
from admin.manage_purchase import purchase_handle as ph

class Fake:
    def __init__(self): self.by_order = {}; self.by_pid = {}
    def add(self, oid, pid, status, amount, refund=None):
        p = {'id': pid, 'order_id': oid, 'status': status, 'amount': amount, 'method': 'upi', 'refund_status': refund}
        self.by_order.setdefault(oid, []).append(p); self.by_pid[pid] = p
    @property
    def order(self):
        outer = self
        class O:
            def payments(self, oid): return {'items': outer.by_order.get(oid, [])}
        return O()
    @property
    def payment(self):
        outer = self
        class P:
            def fetch(self, pid):
                if pid in outer.by_pid: return outer.by_pid[pid]
                raise Exception('The id provided does not exist')
        return P()
fake = Fake()
ph._get_razorpay = lambda: fake
ph._LIVE_CACHE.clear()
client = app.test_client()
from admin.auth.admin_utils import password_fingerprint
from admin.auth.admin_db import UserOperation as _AdminOps
with app.app_context():
    _found, _pw_hash = _AdminOps().get_admin_auth_state(ADMIN_EMAIL)
    _fp = password_fingerprint(_pw_hash)
with client.session_transaction() as sess:
    sess['admin_email'] = ADMIN_EMAIL; sess['admin_username'] = 'SELFTEST admin'; sess['_admin_csrf_token'] = 'selftest-admin-csrf'
    sess['admin_pw_fp'] = _fp; sess['admin_role'] = 'admin'
H = {'X-CSRFToken': 'selftest-admin-csrf'}
get = lambda url: client.get(url).get_json()
post = lambda url, body: client.post(url, json=body, headers=H)

try:
    print('\n== one search box, everything ==')
    order('order_SELFTESTADM1', 'created'); sub('order_SELFTESTADMS1', 'active', 'pay_SELFTESTADMS1'); purchase('pay_SELFTESTADMP1')
    fake.add('order_SELFTESTADMS1', 'pay_SELFTESTADMS1', 'captured', 120000); fake.add('order_SELFTESTADMP1', 'pay_SELFTESTADMP1', 'captured', 70000)
    rows = get('/api/purchases/search-all?q=selftest.payments')
    me = next((r for r in rows if r['email'] == STUDENT), None)
    check('search by part of the email finds the student with premium, paid and unconfirmed counts',
          me and me['premium'] == 1 and me['paid_items'] == 1 and me['pending'] == 1, str(me)[:120])
    check('search by part of a payment id finds them too', any(r['email'] == STUDENT for r in get('/api/purchases/search-all?q=SELFTESTADMP')))
    check('search by part of an order id finds them', any(r['email'] == STUDENT for r in get('/api/purchases/search-all?q=SELFTESTADM1')))
    check('search by phone works', any(r['email'] == STUDENT for r in get('/api/purchases/search-all?q=99999999')))
    check('search by name works', any(r['email'] == STUDENT for r in get('/api/purchases/search-all?q=SELFTEST Pay')))
    check('one letter is not enough', get('/api/purchases/search-all?q=s') == [])

    print('\n== the customer view: premium and paid apart, every course ==')
    d = get(f'/api/purchases/customer-detail?email={STUDENT}')
    check('premium subscriptions carry their course code and access', d['subscriptions'][0]['course_code'] == CODE and d['subscriptions'][0]['access'] == 'granted')
    check('paid content is listed separately with its course', d['purchases'][0]['course_code'] == CODE and d['purchases'][0]['kind'] == 'paid')
    check('unconfirmed orders are listed with their items', d['orders'][0]['razorpay_order_id'] == 'order_SELFTESTADM1' and 'SELFTEST admin pay block' in d['orders'][0]['items'])
    check('the summary counts each kind', d['summary']['subscriptions'] == 1 and d['summary']['items'] == 1 and d['summary']['pending'] == 1 and d['summary']['premium_active'])

    print('\n== live gateway vs access: the five verdicts ==')
    fake.add('order_SELFTESTADM1', 'pay_SELFTESTADM1', 'captured', 70000)
    order('order_SELFTESTADM2', 'created', minutes=20); fake.add('order_SELFTESTADM2', 'pay_SELFTESTADM2', 'failed', 0)
    purchase('pay_SELFTESTADMR1'); order('order_SELFTESTADMR1', 'paid', 'pay_SELFTESTADMR1'); fake.add('order_SELFTESTADMR1', 'pay_SELFTESTADMR1', 'captured', 70000, refund='full')
    purchase('pay_SELFTESTADMX1'); order('order_SELFTESTADMX1', 'paid', 'pay_SELFTESTADMX1')
    order('order_SELFTESTADM3', 'created', minutes=20); fake.add('order_SELFTESTADM3', 'pay_SELFTESTADM3', 'authorized', 70000)
    ph._LIVE_CACHE.clear()
    live = get('/api/purchases/live?payments=pay_SELFTESTADMP1,pay_SELFTESTADMR1,pay_SELFTESTADMX1&orders=order_SELFTESTADM1,order_SELFTESTADM2,order_SELFTESTADM3')['results']
    vc = lambda k: live[k]['verdict']['code']
    check('captured + granted = all good', vc('pay_SELFTESTADMP1') == 'ok', vc('pay_SELFTESTADMP1'))
    check('captured + not granted = student paid, system failed -> Grant', vc('order_SELFTESTADM1') == 'paid_no_access' and live['order_SELFTESTADM1']['verdict']['action'] == 'grant')
    check('failed + not granted = claim is false', vc('order_SELFTESTADM2') == 'not_paid' and not live['order_SELFTESTADM2']['verdict']['action'])
    check('refunded + granted = Revoke', vc('pay_SELFTESTADMR1') == 'refunded_with_access' and live['pay_SELFTESTADMR1']['verdict']['action'] == 'revoke')
    check('unknown at Razorpay + granted = access without payment -> Revoke', vc('pay_SELFTESTADMX1') == 'access_without_payment')
    check('authorized = money on hold, no action', vc('order_SELFTESTADM3') == 'authorized' and not live['order_SELFTESTADM3']['verdict']['action'])

    print('\n== Grant: only after Razorpay confirms ==')
    r = post('/api/purchases/grant', {'order_id': 'order_SELFTESTADM2'}); d = r.get_json()
    check('grant is refused when the gateway shows no captured payment', r.status_code == 409 and not d['success'] and not db("SELECT 1 FROM purchase WHERE payment_id='pay_SELFTESTADM2'"), d['message'][:80])
    r = post('/api/purchases/grant', {'order_id': 'order_SELFTESTADM1'}); d = r.get_json()
    row = db("SELECT status, fulfilled_by, razorpay_payment_id FROM content_orders WHERE razorpay_order_id='order_SELFTESTADM1'")[0]
    check('grant opens access for a captured payment and records who did it', d['success'] and db("SELECT 1 FROM purchase WHERE payment_id='pay_SELFTESTADM1' AND status='Paid'")
          and row['status'] == 'paid' and row['fulfilled_by'].startswith('admin:'), str(row))
    r = post('/api/purchases/grant', {'order_id': 'order_SELFTESTADM1'})
    check('granting twice is refused, no duplicate rows', r.status_code == 409 and len(db("SELECT 1 FROM purchase WHERE payment_id='pay_SELFTESTADM1'")) == 1)
    sub('order_SELFTESTADMS2', 'created', minutes=15); fake.add('order_SELFTESTADMS2', 'pay_SELFTESTADMS2', 'captured', 120000)
    r = post('/api/purchases/grant', {'order_id': 'order_SELFTESTADMS2'}); d = r.get_json()
    srow = db("SELECT status, expires_at, fulfilled_by FROM pcp_subscriptions WHERE razorpay_order_id='order_SELFTESTADMS2'")[0]
    check('a premium order is activated until the plan end stored on it', d['success'] and srow['status'] == 'active' and srow['expires_at'] > datetime.now() + timedelta(days=199), str(srow))
    r = client.post('/api/purchases/grant', json={'order_id': 'order_SELFTESTADM3'})
    check('grant without the CSRF token is refused', r.status_code in (400, 403))

    print('\n== Revoke: only refunded or unpaid ==')
    r = post('/api/purchases/revoke', {'payment_id': 'pay_SELFTESTADMP1'}); d = r.get_json()
    check('a real captured payment cannot be revoked by accident', r.status_code == 409 and db("SELECT 1 FROM purchase WHERE payment_id='pay_SELFTESTADMP1' AND status='Paid'"), d['message'][:80])
    r = post('/api/purchases/revoke', {'payment_id': 'pay_SELFTESTADMR1'}); d = r.get_json()
    check('a refunded payment is revoked: purchase closed, order marked refunded', d['success'] and db("SELECT 1 FROM purchase WHERE payment_id='pay_SELFTESTADMR1' AND status='Refunded'")
          and db("SELECT 1 FROM content_orders WHERE razorpay_order_id='order_SELFTESTADMR1' AND status='refunded'"))
    r = post('/api/purchases/revoke', {'payment_id': 'pay_SELFTESTADMX1'}); d = r.get_json()
    check('access with no payment behind it is revoked', d['success'] and db("SELECT 1 FROM purchase WHERE payment_id='pay_SELFTESTADMX1' AND status='Refunded'"))
    check('the platform no longer counts a revoked item as bought', not db("SELECT 1 FROM purchase WHERE email=%s AND status='Paid' AND payment_id IN ('pay_SELFTESTADMR1','pay_SELFTESTADMX1')", (STUDENT,)))

    print('\n== Needs attention ==')
    order('order_SELFTESTADM4', 'created', minutes=30); fake.add('order_SELFTESTADM4', 'pay_SELFTESTADM4', 'captured', 70000)
    purchase('pay_SELFTESTADMR2'); order('order_SELFTESTADMR2', 'paid', 'pay_SELFTESTADMR2', minutes=40); fake.add('order_SELFTESTADMR2', 'pay_SELFTESTADMR2', 'captured', 70000, refund='full')
    ph._LIVE_CACHE.clear()
    d = get('/api/purchases/attention')
    codes = {(i['razorpay_order_id'], i['verdict']['code']) for i in d['items']}
    check('a paid-but-not-granted order is flagged with Grant', ('order_SELFTESTADM4', 'paid_no_access') in codes, str(codes)[:160])
    check('a refunded-but-still-granted payment is flagged with Revoke', ('order_SELFTESTADMR2', 'refunded_with_access') in codes)
    check('good rows and false claims are not flagged', not any(o in ('order_SELFTESTADM2', 'order_SELFTESTADMP1') for o, _ in codes))
    check('nothing needing attention is ever fixed silently - the admin clicks', db("SELECT status FROM content_orders WHERE razorpay_order_id='order_SELFTESTADM4'")[0]['status'] == 'created')
finally:
    cleanup()
left = db("SELECT COUNT(*) n FROM content_orders WHERE email=%s", (STUDENT,))[0]['n'] + db("SELECT COUNT(*) n FROM purchase WHERE email=%s", (STUDENT,))[0]['n'] + db("SELECT COUNT(*) n FROM auth WHERE email=%s", (STUDENT,))[0]['n']
print(f"\nSELFTEST rows left: {left}")
print(f"RESULT: {sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) and left == 0 else 1)
