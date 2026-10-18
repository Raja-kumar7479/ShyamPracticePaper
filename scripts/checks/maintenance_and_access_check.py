import re, subprocess, sys, time
from datetime import datetime, timedelta
import mysql.connector, requests
from urllib3.util.retry import Retry
from dotenv import dotenv_values

ROOT = '/Users/apple/Downloads/ShyamPracticePp'
USER, ADMIN = 'http://127.0.0.1:5002', 'http://127.0.0.1:5001'
ADMIN_EMAIL, ADMIN_PASSWORD = 'rajakumarvijeta7087@gmail.com', 'Raja@7479'
sys.path.insert(0, f'{ROOT}/scripts/checks')
import selftest_student
EMAIL, PASSWORD = selftest_student.EMAIL, selftest_student.PASSWORD
TAG = 'SELFTEST'
SID = 'SELFTESTNOTES'
v = dotenv_values(f'{ROOT}/user_app/.env')

def db(q, p=()):
    c = mysql.connector.connect(host=v['DATABASE_HOST'], user=v['DATABASE_USER'], password=v['DATABASE_PASSWORD'],
                                database=v['DATABASE_NAME'], autocommit=True)
    cur = c.cursor(dictionary=True); cur.execute(q, p)
    out = cur.fetchall() if cur.with_rows else []
    cur.close(); c.close(); return out

results = []
def check(name, ok, detail=''):
    results.append(bool(ok)); print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ''))

def cleanup():
    db("DELETE FROM notes_content WHERE test_id=%s", (SID,))
    db("DELETE FROM course_content WHERE section_id=%s", (SID,))
    db("DELETE FROM pcp_subscriptions WHERE razorpay_order_id LIKE 'SELFTEST%'")
    db("DELETE FROM questions WHERE subject LIKE 'SELFTEST%'")
    db("DELETE FROM purchase WHERE payment_id='SELFTEST_PAY_TAG'")
    db("DELETE FROM test_description WHERE test_id='SELFTESTPAID'")
    db("DELETE FROM course_content WHERE section_id='SELFTESTPAID'")

cleanup()
student = selftest_student.setup(db)
FREE_CODE, FU = student['code'], student['unique_code']
enr = {FREE_CODE: {'code': FREE_CODE, 'name': student['name'], 'unique_code': FU}}

s = requests.Session()
s.mount('http://', requests.adapters.HTTPAdapter(max_retries=Retry(total=4, connect=4, read=4, backoff_factor=1.5, allowed_methods=False)))
page = s.get(f'{USER}/user_login').text
tok = (re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page) or re.search(r'name="csrf-token"[^>]*content="([^"]+)"', page))
tok = tok.group(1) if tok else ''
s.post(f'{USER}/user_login', data={'email': EMAIL, 'csrf_token': tok})
s.post(f'{USER}/user_login', data={'password': PASSWORD, 'csrf_token': tok})

print('\n== premium notes ==')
db("INSERT INTO course_content (code,name,stream,section,section_id,title,subtitle,label,price,discount,details,status)"
   " VALUES (%s,%s,'Self test','notes',%s,'SELFTEST notes block','s','Free',0,0,'<p>x</p>','active')",
   (FREE_CODE, enr[FREE_CODE]['name'], SID))
for title, access, path in (('SELFTEST free note', 'free', f'/static/uploads/{TAG}_free.pdf'),
                            ('SELFTEST premium note', 'paid', f'/static/uploads/{TAG}_prem.pdf')):
    db("INSERT INTO notes_content (test_id, code, type, access_label, heading, sub_heading, title, sub_title, file_path)"
       " VALUES (%s,%s,'Notes',%s,'SELFTEST head','SELFTEST sub',%s,'',%s)", (SID, FREE_CODE, access, title, path))
r = s.get(f'{USER}/open/hnotes/{SID}/{FREE_CODE}/{FU}')
body = r.text
check('the notes list opens', r.status_code == 200, str(r.status_code))
check('the premium note is tagged Premium and links to the premium page',
      'SELFTEST premium note' in body and 'note-locked' in body and f'/courses/{FREE_CODE}/{FU}/premium' in body)
check('the free note still links to the file', f'{TAG}_free.pdf' in body.replace('%2F', '/'))
check('a locked premium note does not expose its file path', f'{TAG}_prem.pdf' not in body.replace('%2F', '/'))
r = s.get(f'{USER}/view_note_file/static/uploads/{TAG}_prem.pdf', allow_redirects=False)
check('opening the premium note file is refused without a subscription', r.status_code == 403, str(r.status_code))
r = s.get(f'{USER}/view_note_file/static/uploads/{TAG}_free.pdf', allow_redirects=False)
check('the free note passes the access guard', r.status_code in (200, 404), str(r.status_code))
db("INSERT INTO pcp_subscriptions (email, course_code, plan, amount_paise, razorpay_order_id, razorpay_payment_id, status, starts_at, expires_at)"
   " VALUES (%s,%s,'monthly',100000,'SELFTEST_SUBBED','SELFTEST_SUBBED_PAY','active',%s,%s)",
   (EMAIL, FREE_CODE, datetime.now() - timedelta(days=1), datetime.now() + timedelta(days=30)))
r = s.get(f'{USER}/view_note_file/static/uploads/{TAG}_prem.pdf', allow_redirects=False)
check(f'a subscriber to {FREE_CODE} passes the guard (404 = file missing, guard cleared)', r.status_code == 404, str(r.status_code))
db("DELETE FROM pcp_subscriptions WHERE razorpay_order_id='SELFTEST_SUBBED'")

print('\n== Paid is never labelled Premium ==')
PAID_SID = 'SELFTESTPAID'
PAID_KEY = 'free_' + '9' * 20
db("DELETE FROM test_questions WHERE test_key=%s", (PAID_KEY,))
db("DELETE FROM test_description WHERE test_key=%s", (PAID_KEY,))
db("DELETE FROM course_content WHERE section_id=%s", (PAID_SID,))
db("INSERT INTO course_content (code,name,stream,section,section_id,title,subtitle,label,price,discount,details,status)"
   " VALUES (%s,%s,'Self test','mock_test',%s,'SELFTEST paid block','s','Paid',100,0,'<p>x</p>','active')",
   (FREE_CODE, enr[FREE_CODE]['name'], PAID_SID))
db("INSERT INTO test_description (test_id,test_key,subject_title,subject_subtitle,total_questions,total_marks,"
   "total_duration_minutes,show_calculator,access_label) VALUES (%s,%s,'SELFTEST paid test','x',1,1,5,1,'free')",
   (PAID_SID, PAID_KEY))
r = s.get(f'{USER}/open/mock_test/{PAID_SID}/{FREE_CODE}/{FU}')
check('an unbought Paid block shows none of its tests', 'SELFTEST paid test' not in r.text, str(r.status_code))
db("INSERT INTO purchase (email, username, course_code, section_id, section, title, subtitle, price, original_price,"
   " discount_percent, final_price, payment_id, payment_mode, payment_date, status, purchase_code)"
   " VALUES (%s,'SELFTEST',%s,%s,'mock_test','SELFTEST paid block','s',100,100,0,100,'SELFTEST_PAY_TAG','Razorpay',NOW(),'Paid','SELFTESTTAG')",
   (EMAIL, FREE_CODE, PAID_SID))
r = s.get(f'{USER}/open/mock_test/{PAID_SID}/{FREE_CODE}/{FU}')
card = r.text
tags = card[card.find('tags-container'):card.find('tags-container') + 400] if 'tags-container' in card else ''
check('once bought, its test appears with a Paid tag', 'SELFTEST paid test' in card and 'tag-paid' in tags, str(r.status_code))
check('...and it is not called Premium', 'tag-premium' not in tags, tags[:90].replace('\n', ' '))
db("DELETE FROM purchase WHERE payment_id='SELFTEST_PAY_TAG'")
db("DELETE FROM test_description WHERE test_key=%s", (PAID_KEY,))
db("DELETE FROM course_content WHERE section_id=%s", (PAID_SID,))

print('\n== abandoned orders and reminders ==')
db("INSERT INTO pcp_subscriptions (email, course_code, plan, amount_paise, razorpay_order_id, status, created_at)"
   " VALUES (%s,%s,'monthly',100000,'SELFTEST_OLD_ORDER','failed',%s)", (EMAIL, FREE_CODE, datetime.now() - timedelta(days=31)))
db("INSERT INTO pcp_subscriptions (email, course_code, plan, amount_paise, razorpay_order_id, status, created_at)"
   " VALUES (%s,%s,'monthly',100000,'SELFTEST_STALE_ORDER','created',%s)", (EMAIL, FREE_CODE, datetime.now() - timedelta(days=3)))
db("INSERT INTO pcp_subscriptions (email, course_code, plan, amount_paise, razorpay_order_id, status, created_at)"
   " VALUES (%s,%s,'monthly',100000,'SELFTEST_NEW_ORDER','created',%s)", (EMAIL, FREE_CODE, datetime.now()))
db("INSERT INTO pcp_subscriptions (email, course_code, plan, amount_paise, razorpay_order_id, razorpay_payment_id, status, starts_at, expires_at)"
   " VALUES (%s,%s,'monthly',100000,'SELFTEST_SOON','SELFTEST_SOON_PAY','active',%s,%s)",
   (EMAIL, FREE_CODE, datetime.now() - timedelta(days=28), datetime.now() + timedelta(days=2)))
live_before = db("SELECT COUNT(*) n FROM pcp_subscriptions WHERE status='active'")[0]['n']
out = subprocess.run([sys.executable, '-m', 'admin.manage_modules.cleanup_script'], cwd=f'{ROOT}/admin_app',
                     capture_output=True, text=True, timeout=180)
log = out.stdout + out.stderr
check('the job runs clean', out.returncode == 0, log.strip().splitlines()[-1][:70] if log.strip() else '')
check('a failed order older than a month is removed', not db("SELECT 1 FROM pcp_subscriptions WHERE razorpay_order_id='SELFTEST_OLD_ORDER'"))
check('an unconfirmed order is never deleted by the purge - reconciliation owns it', bool(db("SELECT 1 FROM pcp_subscriptions WHERE razorpay_order_id='SELFTEST_STALE_ORDER'")))
check('a fresh unpaid order is kept', bool(db("SELECT 1 FROM pcp_subscriptions WHERE razorpay_order_id='SELFTEST_NEW_ORDER'")))
check('paid subscriptions are never touched', db("SELECT COUNT(*) n FROM pcp_subscriptions WHERE status='active'")[0]['n'] == live_before)
due = db("SELECT id FROM pcp_subscriptions WHERE razorpay_order_id='SELFTEST_SOON'")
row = db("SELECT reminder_sent_at FROM pcp_subscriptions WHERE razorpay_order_id='SELFTEST_SOON'")[0]
check('a subscription ending in 2 days gets its reminder and is marked so it is not sent twice',
      row['reminder_sent_at'] is not None, str(row['reminder_sent_at']))
out2 = subprocess.run([sys.executable, '-m', 'admin.manage_modules.cleanup_script'], cwd=f'{ROOT}/admin_app',
                      capture_output=True, text=True, timeout=180)
again = db("SELECT reminder_sent_at FROM pcp_subscriptions WHERE razorpay_order_id='SELFTEST_SOON'")[0]
check('a second run does not send it again', again['reminder_sent_at'] == row['reminder_sent_at'])

print('\n== admin has the same rights as an owner ==')
csrf = lambda h: (re.search(r'name="csrf-token"[^>]*content="([^"]+)"', h) or [None, ''])[1]
a = requests.Session(); a.mount('http://', requests.adapters.HTTPAdapter(max_retries=Retry(total=4, connect=4, read=4, backoff_factor=1.5, allowed_methods=False))); t = csrf(a.get(f'{ADMIN}/admin_login').text)
a.post(f'{ADMIN}/admin_login', data={'email': ADMIN_EMAIL, '_csrf_token': t})
a.post(f'{ADMIN}/admin_login', data={'password': ADMIN_PASSWORD, '_csrf_token': t})
H = {'X-CSRFToken': csrf(a.get(f'{ADMIN}/manage_course_content').text) or t}
role = db("SELECT role FROM auth_admin WHERE email=%s", (ADMIN_EMAIL,))[0]['role']
q = {'paper_code': FREE_CODE, 'subject': f'{TAG} probe', 'question_id': '99931', 'question_type': 'MCQ',
     'question_text': f'{TAG} q', 'option_a': '1', 'option_b': '2', 'option_c': '3', 'option_d': '4',
     'correct_option': 'A', 'topic': 'x', 'year': '2026'}
r = a.post(f'{ADMIN}/api/questions/add-manual', json=q, headers=H)
row = db("SELECT id FROM questions WHERE subject=%s", (f'{TAG} probe',))
check(f'role is {role} and it can add a paper question', r.status_code in (200, 201) and bool(row), f'{r.status_code}')
if row:
    r = a.delete(f'{ADMIN}/api/questions/delete/{row[0]["id"]}', headers=H)
    check('...and delete it, with no owner-only refusal', r.status_code == 200 and 'owner' not in r.text.lower(), r.text[:70])
r = a.get(f'{ADMIN}/api/purchases/customer?email={EMAIL}')
data = r.json() if r.status_code == 200 else {}
check('the admin customer lookup reports premium', r.status_code == 200 and 'premium_active' in (data.get('summary') or {}),
      f"{r.status_code} premium_active={(data.get('summary') or {}).get('premium_active')}")

cleanup()
selftest_student.remove(db)
left = (db("SELECT COUNT(*) n FROM notes_content WHERE title LIKE 'SELFTEST%'")[0]['n']
        + db("SELECT COUNT(*) n FROM course_content WHERE section_id=%s", (SID,))[0]['n']
        + db("SELECT COUNT(*) n FROM pcp_subscriptions WHERE razorpay_order_id LIKE 'SELFTEST%'")[0]['n']
        + db("SELECT COUNT(*) n FROM questions WHERE subject LIKE 'SELFTEST%'")[0]['n'])
print(f"\n{TAG} rows left: {left}")
print(f"RESULT: {sum(1 for r in results if r)}/{len(results)} passed")
sys.exit(0 if all(results) and left == 0 else 1)
