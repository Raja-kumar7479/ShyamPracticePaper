import json, os, sys, hmac, hashlib
from datetime import datetime, timedelta
import mysql.connector
from dotenv import dotenv_values

ROOT = '/Users/apple/Downloads/ShyamPracticePp'
EMAIL = 'rajakumarvijeta7087@gmail.com'
SID = 'SELFTESTPAYX'
SECRET = 'selftest-webhook-secret'
v = dotenv_values(f'{ROOT}/user_app/.env')

def db(q, p=()):
    c = mysql.connector.connect(host=v['DATABASE_HOST'], user=v['DATABASE_USER'], password=v['DATABASE_PASSWORD'], database=v['DATABASE_NAME'], autocommit=True)
    cur = c.cursor(dictionary=True); cur.execute(q, p); out = cur.fetchall() if cur.with_rows else []; cur.close(); c.close(); return out
results = []
def check(name, ok, detail=''):
    results.append(bool(ok)); print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ''))

def cleanup():
    db("DELETE FROM purchase WHERE payment_id LIKE 'pay_SELFTEST%'")
    db("DELETE FROM content_orders WHERE razorpay_order_id LIKE 'order_SELFTEST%'")
    db("DELETE FROM pcp_subscriptions WHERE razorpay_order_id LIKE 'order_SELFTEST%'")
    db("DELETE FROM course_content WHERE section_id=%s", (SID,))

cleanup()
enr = db("SELECT code, name, unique_code FROM enrollment WHERE email=%s ORDER BY id", (EMAIL,))
assert enr, 'the student must be enrolled somewhere'
CODE, NAME, U = enr[0]['code'], enr[0]['name'], enr[0]['unique_code']
db("INSERT INTO course_content (code,name,stream,section,section_id,title,subtitle,label,price,discount,details,status)"
   " VALUES (%s,%s,'Self test','mock_test',%s,'SELFTEST pay block','s','Paid',500,0,'<p>x</p>','active')", (CODE, NAME, SID))
CART = [{'title': 'SELFTEST pay block', 'subtitle': 's', 'price': 500.0, 'list_price': 500.0, 'item_discount': 0, 'saved': 0, 'section': 'mock_test', 'section_id': SID}]

def order(oid, minutes_ago=10, amount=50000, status='created'):
    db("INSERT INTO content_orders (email, username, phone, course_code, unique_code, razorpay_order_id, amount_paise, list_paise, discount_pct, cart_json, status, created_at)"
       " VALUES (%s,'SELFTEST',%s,%s,%s,%s,%s,%s,0,%s,%s,%s)",
       (EMAIL, '9876543210', CODE, U, oid, amount, amount, json.dumps(CART), status, datetime.now() - timedelta(minutes=minutes_ago)))

def sub_order(oid, minutes_ago=10, amount=100000):
    db("INSERT INTO pcp_subscriptions (email, course_code, plan, plan_label, amount_paise, list_paise, discount_pct, razorpay_order_id, status, created_at)"
       " VALUES (%s,%s,'selftest-pay','SELFTEST pay plan',%s,%s,0,%s,'created',%s)", (EMAIL, CODE, amount, amount, oid, datetime.now() - timedelta(minutes=minutes_ago)))

os.chdir(f'{ROOT}/user_app'); sys.path.insert(0, f'{ROOT}/user_app')
from app import app
from config import Config
from routes.courses_platform.payment.purchased_payment import payment_orders as po
from routes.exam_platform.placement_exam_portal.practice_coding import routes_billing
Config.RAZORPAY_WEBHOOK_SECRET = SECRET
po.send_content_receipt = lambda *a, **k: True
routes_billing._send_subscription_receipt = lambda *a, **k: True

class FakeGateway:
    def __init__(self): self.payments = {}
    class _Order:
        def __init__(self, outer): self.outer = outer
        def payments(self, oid): return {'items': self.outer.payments.get(oid, [])}
    class _Payment:
        def __init__(self, outer): self.outer = outer
        def fetch(self, pid):
            for items in self.outer.payments.values():
                for p in items:
                    if p['id'] == pid: return p
            raise Exception('The id provided does not exist')
    @property
    def order(self): return FakeGateway._Order(self)
    @property
    def payment(self): return FakeGateway._Payment(self)
fake = FakeGateway()
po.gateway = lambda: fake
def captured(oid, pid, amount, method='upi'): fake.payments[oid] = [{'id': pid, 'order_id': oid, 'status': 'captured', 'amount': amount, 'method': method}]
def failed(oid, pid): fake.payments[oid] = [{'id': pid, 'order_id': oid, 'status': 'failed', 'amount': 0}]

client = app.test_client()
def sign(body): return hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
def webhook(event, oid, pid, amount, signature=None):
    body = json.dumps({'event': event, 'payload': {'payment': {'entity': {'id': pid, 'order_id': oid, 'amount': amount, 'method': 'upi'}}}}).encode()
    return client.post('/api/purchase/webhook', data=body, content_type='application/json', headers={'X-Razorpay-Signature': signature if signature is not None else sign(body)})
purchases = lambda pid: db("SELECT status FROM purchase WHERE payment_id=%s", (pid,))
order_row = lambda oid: db("SELECT status, gateway_status, fulfilled_by, razorpay_payment_id FROM content_orders WHERE razorpay_order_id=%s", (oid,))[0]

try:
    print('\n== the webhook: money the browser never reported ==')
    order('order_SELFTESTA')
    r = webhook('payment.captured', 'order_SELFTESTA', 'pay_SELFTESTA', 50000, signature='bad')
    check('a webhook with a wrong signature is refused', r.status_code == 400 and not purchases('pay_SELFTESTA'), r.get_data(as_text=True)[:80])
    r = webhook('payment.captured', 'order_SELFTESTA', 'pay_SELFTESTA', 49900)
    check('a captured payment for the wrong amount is refused and logged, nothing granted', r.status_code == 400 and not purchases('pay_SELFTESTA'))
    r = webhook('payment.captured', 'order_SELFTESTA', 'pay_SELFTESTA', 50000)
    row = order_row('order_SELFTESTA')
    check('a genuine captured webhook records the purchase and opens access', r.status_code == 200 and purchases('pay_SELFTESTA')[0]['status'] == 'Paid'
          and row['status'] == 'paid' and row['fulfilled_by'] == 'webhook' and row['gateway_status'] == 'captured', str(row))
    r = webhook('order.paid', 'order_SELFTESTA', 'pay_SELFTESTA', 50000)
    check('the same webhook twice never duplicates the purchase', r.status_code == 200 and len(purchases('pay_SELFTESTA')) == 1, r.get_data(as_text=True)[:60])
    order('order_SELFTESTF')
    r = webhook('payment.failed', 'order_SELFTESTF', 'pay_SELFTESTF', 50000)
    check('a failed-payment webhook is noted on the order, no access', r.status_code == 200 and order_row('order_SELFTESTF')['gateway_status'] == 'failed' and not purchases('pay_SELFTESTF'))
    check('the webhook is off (404) when no secret is configured', (setattr(Config, 'RAZORPAY_WEBHOOK_SECRET', None) or webhook('payment.captured', 'order_SELFTESTA', 'pay_SELFTESTA', 50000).status_code) == 404)
    Config.RAZORPAY_WEBHOOK_SECRET = SECRET

    print('\n== reconciliation: the browser died, the webhook was missed ==')
    order('order_SELFTESTB', minutes_ago=12); captured('order_SELFTESTB', 'pay_SELFTESTB', 50000)
    order('order_SELFTESTC', minutes_ago=1); captured('order_SELFTESTC', 'pay_SELFTESTC', 50000)
    order('order_SELFTESTD', minutes_ago=60 * 24 * 8)
    order('order_SELFTESTE', minutes_ago=30); failed('order_SELFTESTE', 'pay_SELFTESTE')
    order('order_SELFTESTG', minutes_ago=30); captured('order_SELFTESTG', 'pay_SELFTESTG', 40000)
    sub_order('order_SELFTESTP', minutes_ago=15); captured('order_SELFTESTP', 'pay_SELFTESTP', 100000)
    with app.app_context():
        report = po.reconcile()
    rb = order_row('order_SELFTESTB')
    check('a paid order whose callback was lost is fulfilled by the job', rb['status'] == 'paid' and rb['fulfilled_by'] == 'reconcile' and purchases('pay_SELFTESTB'), str(rb))
    check('an order younger than 3 minutes is left alone (the browser may still be on its way)', order_row('order_SELFTESTC')['status'] == 'created')
    check('an unpaid order older than a week is marked failed, not deleted', order_row('order_SELFTESTD')['status'] == 'failed' and db("SELECT 1 FROM content_orders WHERE razorpay_order_id='order_SELFTESTD'"))
    check('an order whose payment failed is marked failed', order_row('order_SELFTESTE')['status'] == 'failed')
    check('a captured payment for the wrong amount is never fulfilled by the job', order_row('order_SELFTESTG')['status'] == 'created' and not purchases('pay_SELFTESTG'))
    sp = db("SELECT status, fulfilled_by, expires_at FROM pcp_subscriptions WHERE razorpay_order_id='order_SELFTESTP'")[0]
    check('a paid premium order is activated by the job', sp['status'] == 'active' and sp['fulfilled_by'] == 'reconcile' and sp['expires_at'] > datetime.now(), str(sp))
    check('the job reports what it did', report['paid'] == 2 and report['failed'] == 1 and report['expired'] == 1, str(report))

    print('\n== the student: Check now ==')
    def student(oid, email=EMAIL):
        with client.session_transaction() as sess:
            sess['user_email'] = email; sess['user_username'] = 'SELFTEST'; sess['_csrf_token'] = 'selftest-csrf'
        return client.post(f'/api/payment/check/{oid}', headers={'X-CSRFToken': 'selftest-csrf'}, json={})
    order('order_SELFTESTH', minutes_ago=5); captured('order_SELFTESTH', 'pay_SELFTESTH', 50000)
    r = student('order_SELFTESTH'); d = r.get_json()
    check('Check now finds the captured payment and opens access at once', r.status_code == 200 and d['status'] == 'paid' and purchases('pay_SELFTESTH')
          and order_row('order_SELFTESTH')['fulfilled_by'] == 'student', str(d)[:90])
    order('order_SELFTESTI', minutes_ago=5)
    r = student('order_SELFTESTI'); d = r.get_json()
    check('with no payment at Razorpay it says so and grants nothing', d['status'] == 'unpaid' and not purchases('pay_SELFTESTI'), d['message'][:70])
    r = student('order_SELFTESTI', email='someone.else@example.com')
    check('another student cannot check or claim your order', r.status_code == 404)
    with client.session_transaction() as sess:
        sess['user_email'] = EMAIL; sess['user_username'] = 'SELFTEST'; sess['_csrf_token'] = 'selftest-csrf'
    r = client.post('/api/payment/check/order_SELFTESTI', json={})
    check('a request without the CSRF token is refused', r.status_code == 403)
    order('order_SELFTESTJ', minutes_ago=5); failed('order_SELFTESTJ', 'pay_SELFTESTJ')
    d = student('order_SELFTESTJ').get_json()
    check('a failed payment is reported as failed and the order closed', d['status'] == 'failed' and order_row('order_SELFTESTJ')['status'] == 'failed')
    pend = po.pending_orders_for(EMAIL)
    check('the purchases page lists only the still-open orders (a failed attempt stays open - the student may retry it)',
          {p['razorpay_order_id'] for p in pend} == {'order_SELFTESTC', 'order_SELFTESTF', 'order_SELFTESTG', 'order_SELFTESTI'}, str([p['razorpay_order_id'] for p in pend]))
    r = client.get(f'/purchase/{CODE}/{U}')
    html = r.get_data(as_text=True)
    check('the page shows "Payments being confirmed" with a Check now button per open order', r.status_code == 200 and 'Payments being confirmed' in html and html.count('pend__check') >= 3, str(r.status_code))
    check('a fulfilled order shows up as a normal purchase, not as pending', 'order_SELFTESTB' not in html and 'SELFTEST pay block' in html)

    print('\n== nothing opens without a captured payment ==')
    check('no purchase row exists for any unpaid order', not db("SELECT 1 FROM purchase WHERE payment_id IN ('pay_SELFTESTE','pay_SELFTESTG','pay_SELFTESTI','pay_SELFTESTJ')"))
    check('every fulfilled order carries who confirmed it', {order_row(o)['fulfilled_by'] for o in ('order_SELFTESTA', 'order_SELFTESTB', 'order_SELFTESTH')} == {'webhook', 'reconcile', 'student'})
finally:
    cleanup()
left = db("SELECT COUNT(*) n FROM content_orders WHERE razorpay_order_id LIKE 'order_SELFTEST%'")[0]['n'] + db("SELECT COUNT(*) n FROM purchase WHERE payment_id LIKE 'pay_SELFTEST%'")[0]['n']
print(f"\nSELFTEST rows left: {left}")
print(f"RESULT: {sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) and left == 0 else 1)
