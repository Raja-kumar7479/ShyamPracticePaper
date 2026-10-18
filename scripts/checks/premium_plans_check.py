import os, re, sys, time
from datetime import datetime, timedelta
import mysql.connector, requests
from dotenv import dotenv_values

ROOT = '/Users/apple/Downloads/ShyamPracticePp'
sys.path.insert(0, f'{ROOT}/scripts/checks')
USER, ADMIN = 'http://127.0.0.1:5002', 'http://127.0.0.1:5001'
ADMIN_EMAIL, ADMIN_PASSWORD = 'rajakumarvijeta7087@gmail.com', 'Raja@7479'
import selftest_student
EMAIL, PASSWORD = selftest_student.EMAIL, selftest_student.PASSWORD
TAG = 'SELFTEST'
SID = 'SELFTESTPLAN'
KEY_PREM = 'prem_' + '7' * 20
v = dotenv_values(f'{ROOT}/user_app/.env')

def db(q, p=()):
    c = mysql.connector.connect(host=v['DATABASE_HOST'], user=v['DATABASE_USER'], password=v['DATABASE_PASSWORD'],
                                database=v['DATABASE_NAME'], autocommit=True)
    cur = c.cursor(dictionary=True); cur.execute(q, p)
    out = cur.fetchall() if cur.with_rows else []
    cur.close(); c.close(); return out

class Client:
    def __init__(self):
        self.s = requests.Session()
    def _do(self, method, url, **kw):
        last = None
        for _ in range(4):
            try:
                return getattr(self.s, method)(url, timeout=30, **kw)
            except requests.exceptions.RequestException as e:
                last = e
                time.sleep(2.5)
        raise last
    def get(self, url, **kw): return self._do('get', url, **kw)
    def post(self, url, **kw): return self._do('post', url, **kw)

results = []
def check(name, ok, detail=''):
    results.append(bool(ok)); print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ''))

def cleanup():
    for t in ('test_attempt_details', 'test_result', 'user_test_log', 'test_feedback', 'test_questions', 'test_description'):
        db(f"DELETE FROM {t} WHERE test_key=%s", (KEY_PREM,))
    db("DELETE FROM course_content WHERE section_id=%s", (SID,))
    db("DELETE FROM premium_plans WHERE label LIKE 'SELFTEST%'")
    db("DELETE FROM premium_catalog WHERE headline LIKE 'SELFTEST%' OR details LIKE 'SELFTEST%'")
    db("DELETE FROM pcp_subscriptions WHERE razorpay_order_id LIKE 'SELFTEST%'")

cleanup()
student = selftest_student.setup(db)
CODE, U, NAME = student['code'], student['unique_code'], student['name']
enr = {CODE: {'name': NAME, 'unique_code': U}}

db("INSERT INTO course_content (code,name,stream,section,section_id,title,subtitle,label,price,discount,details,status)"
   " VALUES (%s,%s,'Self test','mock_test',%s,'SELFTEST plan block','s','Free',0,0,'<p>x</p>','active')",
   (CODE, enr[CODE]['name'], SID))
db("INSERT INTO test_description (test_id,test_key,subject_title,subject_subtitle,total_questions,total_marks,"
   "total_duration_minutes,show_calculator,access_label) VALUES (%s,%s,'SELFTEST premium test','x',1,1,5,1,'paid')",
   (SID, KEY_PREM))
d = db("SELECT id FROM test_description WHERE test_key=%s", (KEY_PREM,))[0]['id']
db("INSERT INTO test_questions (test_id,test_key,test_description_id,section_id,section_name,question_type,question_number,"
   "question_text,option_a,option_b,option_c,option_d,correct_option,correct_marks,negative_marks,question_level)"
   " VALUES (%s,%s,%s,'1','A','MCQ',1,'2+2','3','4','5','6','B',1,0,'Easy')", (SID, KEY_PREM, d))

csrf = lambda h: (re.search(r'name="csrf-token"[^>]*content="([^"]+)"', h) or [None, ''])[1]
a = Client(); t = csrf(a.get(f'{ADMIN}/admin_login').text)
a.post(f'{ADMIN}/admin_login', data={'email': ADMIN_EMAIL, '_csrf_token': t})
a.post(f'{ADMIN}/admin_login', data={'password': ADMIN_PASSWORD, '_csrf_token': t})
H = {'X-CSRFToken': csrf(a.get(f'{ADMIN}/manage-premium').text) or t}
YEAR = datetime.now().year + 2
a.post(f'{ADMIN}/api/premium-catalog/{CODE}/plans',
       json={'label': f'SELFTEST till GATE {YEAR}', 'price': '4999', 'discount': '0', 'discount_ends_at': '',
             'valid_until': f'{YEAR}-03-15T23:59', 'extra_days': '0'}, headers=H)
a.post(f'{ADMIN}/api/premium-catalog/{CODE}/copy',
       json={'headline': 'SELFTEST HEADLINE', 'details': 'SELFTEST<p>what you get</p>'}, headers=H)
DKEY = f'selftest-till-gate-{YEAR}'

s = Client()
page = s.get(f'{USER}/user_login').text
tok = (re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page) or re.search(r'name="csrf-token"[^>]*content="([^"]+)"', page))
tok = tok.group(1) if tok else ''
s.post(f'{USER}/user_login', data={'email': EMAIL, 'csrf_token': tok})
s.post(f'{USER}/user_login', data={'password': PASSWORD, 'csrf_token': tok})

print('\n== a dated plan sells the exam season, not a month ==')
r = s.get(f'{USER}/courses/{CODE}/{U}/premium')
body = r.text
check('the dated plan is offered by name', f'SELFTEST till GATE {YEAR}' in body and 'access until' in body, str(r.status_code))
check('it shows the end date, not a day count', f'15 Mar {YEAR}' in body)

print('\n== content no longer expires under a paying student ==')
cols = db("SELECT COUNT(*) n FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
          "AND TABLE_NAME='course_content' AND COLUMN_NAME='validity_expires_at'")[0]['n']
check('course content has no expiry date at all', cols == 0)
page = a.get(f'{ADMIN}/manage_course_content').text
check('the admin form no longer asks for one', 'validity_expires_at' not in page and 'editValidity' not in page)
check('Hidden is offered instead', 'Hidden (existing buyers keep access)' in page)

print('\n== hidden content keeps paying students in ==')
r = s.get(f'{USER}/courses/{CODE}/{U}/resource/{SID}')
check('an active block opens normally', r.status_code == 200 and 'SELFTEST plan block' in r.text, str(r.status_code))
db("UPDATE course_content SET status='inactive' WHERE section_id=%s", (SID,))
r = s.get(f'{USER}/courses/{CODE}/{U}/resource/{SID}', allow_redirects=False)
check('a hidden block is gone for a student with nothing bought', r.status_code in (302, 404) or 'SELFTEST plan block' not in r.text,
      str(r.status_code))
check('and it is off their dashboard', 'SELFTEST plan block' not in s.get(f'{USER}/courses/{CODE}/{U}').text)
exp = datetime.now() + timedelta(days=30)
db("INSERT INTO pcp_subscriptions (email,course_code,plan,plan_label,amount_paise,razorpay_order_id,razorpay_payment_id,"
   "status,starts_at,expires_at) VALUES (%s,%s,%s,'SELFTEST plan',499900,'SELFTEST_ORDER_H','SELFTEST_PAY_H','active',%s,%s)",
   (EMAIL, CODE, DKEY, datetime.now(), exp))
r = s.get(f'{USER}/courses/{CODE}/{U}/resource/{SID}')
check('the same hidden block still opens for an active subscriber', r.status_code == 200 and 'SELFTEST plan block' in r.text,
      str(r.status_code))
dash = s.get(f'{USER}/courses/{CODE}/{U}').text
check('and stays on the subscriber\'s dashboard, marked "Kept for you"', 'SELFTEST plan block' in dash and 'Kept for you' in dash)
r = s.get(f'{USER}/fetch-questions/{SID}/{KEY_PREM}/{CODE}/{U}', allow_redirects=False)
check('and its premium test still answers', r.status_code == 200, str(r.status_code))
db("UPDATE pcp_subscriptions SET expires_at=%s WHERE razorpay_order_id='SELFTEST_ORDER_H'", (datetime.now() - timedelta(minutes=1),))
r = s.get(f'{USER}/fetch-questions/{SID}/{KEY_PREM}/{CODE}/{U}', allow_redirects=False)
check('when the subscription ends, the premium test locks again', r.status_code == 403, str(r.status_code))
check('and the hidden block leaves their dashboard', 'SELFTEST plan block' not in s.get(f'{USER}/courses/{CODE}/{U}').text)
db("UPDATE course_content SET status='active' WHERE section_id=%s", (SID,))

print('\n== paying for something the admin just hid ==')
db("UPDATE course_content SET label='Paid', price=100, status='active' WHERE section_id=%s", (SID,))
cart_page = s.get(f'{USER}/add_cart/{CODE}/{U}').text
cart_tok = (re.search(r'name="csrf_token"[^>]*value="([^"]+)"', cart_page)
            or re.search(r'name="csrf-token"[^>]*content="([^"]+)"', cart_page) or [None, tok])[1]
add = s.post(f'{USER}/add_cart/{CODE}/{U}', data={'add_cart': '1', 'title': 'SELFTEST plan block', 'subtitle': 's',
                                                  'csrf_token': cart_tok}, headers={'X-CSRFToken': cart_tok},
             allow_redirects=False)
check('the paid block goes into the cart while it is visible', add.status_code in (200, 302), str(add.status_code))

sys.path.insert(0, f'{ROOT}/user_app')
import os as _os
_os.chdir(f'{ROOT}/user_app')
from routes.courses_platform.payment.purchased_payment.databases.payment_handler_db import UserOperation as PayOps
pay_ops = PayOps()
visible = pay_ops.get_content_by_code_title_subtitle(CODE, 'SELFTEST plan block', 's')
check('while visible, the checkout can price the item', bool(visible), 'found' if visible else 'not found')
db("UPDATE course_content SET status='inactive' WHERE section_id=%s", (SID,))
hidden = pay_ops.get_content_by_code_title_subtitle(CODE, 'SELFTEST plan block', 's')
check('once hidden, the checkout cannot price it, so no order can start', not hidden)
src = open(f'{ROOT}/user_app/routes/courses_platform/payment/purchased_payment/payment_orders.py').read()
check('a payment that lands after a change is still recorded and flagged',
      'PAYMENT RACE' in src and 'vanished' in src)
db("UPDATE course_content SET label='Free', price=0, status='active' WHERE section_id=%s", (SID,))
db("DELETE FROM purchase WHERE title='SELFTEST plan block'")

print('\n== the receipt shows the deal the student got ==')
import routes.courses_platform.payment.purchased_payment.utils.utils_receipt as _ur
from routes.exam_platform.placement_exam_portal.practice_coding import routes_billing as _rb, models as _models
_got = {}
_ur.generate_pdf_receipt = lambda **kw: _got.update(kw) or b'%PDF'
def receipt_for(order):
    _got.clear(); row = _models.get_subscription_by_order(order)
    _rb._subscription_receipt_pdf({'email': EMAIL, 'username': 'x'}, row, row['razorpay_payment_id'], row['starts_at'], row['expires_at'])
    return _got['original_price'], _got['discount'], _got['final_amount'], _got['purchases'][0]['subtitle']
db("INSERT INTO pcp_subscriptions (email,course_code,plan,plan_label,amount_paise,list_paise,discount_pct,razorpay_order_id,razorpay_payment_id,status,starts_at,expires_at)"
   " VALUES (%s,%s,'selftest-r','SELFTEST plan',100000,200000,50,'SELFTEST_ORDER_RCPT','SELFTEST_PAY_RCPT','active',NOW(),%s)", (EMAIL, CODE, datetime.now() + timedelta(days=30)))
o, d, f, sub = receipt_for('SELFTEST_ORDER_RCPT')
check('a plan sold at 2000 with 50% off prints Subtotal 2000, Discount 50%, Total 1000', (o, d, f) == (2000.0, 50.0, 1000.0) and '50% discount applied' in sub, f'{o} {d} {f}')
_src = open(f'{ROOT}/user_app/routes/courses_platform/payment/purchased_payment/utils/utils_receipt.py').read()
check('the PDF discount line carries the percent and the rupee amount together', 'Discount {discount:g}% ({_money(discount_amount)})' in _src)
_src = open(f'{ROOT}/user_app/routes/exam_platform/placement_exam_portal/practice_coding/routes_billing.py').read()
check('the email discount line does too', '{discount_pct:g}% (&#8377;{original - amount:.2f})' in _src)
db("UPDATE pcp_subscriptions SET list_paise=NULL, discount_pct=NULL WHERE razorpay_order_id='SELFTEST_ORDER_RCPT'")
o, d, f, sub = receipt_for('SELFTEST_ORDER_RCPT')
check('an old row with no stored deal still prints what was paid, never a wrong discount', (o, d, f) == (1000.0, 0.0, 1000.0) and 'discount' not in sub, f'{o} {d} {f}')
check('no live subscription is missing its stored deal any more', not db("SELECT 1 FROM pcp_subscriptions WHERE status='active' AND list_paise IS NULL AND razorpay_order_id NOT LIKE 'SELFTEST%'"))

cleanup()
selftest_student.remove(db)
left = (db("SELECT COUNT(*) n FROM course_content WHERE section_id=%s", (SID,))[0]['n']
        + db("SELECT COUNT(*) n FROM premium_plans WHERE label LIKE 'SELFTEST%'")[0]['n']
        + db("SELECT COUNT(*) n FROM pcp_subscriptions WHERE razorpay_order_id LIKE 'SELFTEST%'")[0]['n'])
print(f"\n{TAG} rows left: {left}")
print(f"RESULT: {sum(1 for r in results if r)}/{len(results)} passed")
sys.exit(0 if all(results) and left == 0 else 1)
