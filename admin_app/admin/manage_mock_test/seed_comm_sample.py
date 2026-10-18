import os
import sys

ADMIN_APP = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ADMIN_APP)
os.chdir(ADMIN_APP)

from config import Config
import mysql.connector

TEST_ID = sys.argv[1] if len(sys.argv) > 1 else '106281639723'
KEY = 'SET_A'

SECTIONS = [
    ('SEC_A', 'SECTION_A', 'Speaking (Read Aloud)', 'Read the sentences displayed on the screen aloud clearly and naturally.', 600, 1),
    ('SEC_B', 'SECTION_B', 'Speaking (Think & Speak)', 'You will see a topic. Think for 30 seconds, then speak about it for 60 seconds.', 900, 2),
    ('SEC_C', 'SECTION_C', 'Grammar & Vocabulary', 'Choose the correct option to complete the sentences.', 600, 3),
    ('SEC_D', 'SECTION_D', 'Listening Comprehension', 'Listen to the audio clip. The audio will play for all questions in this section.', 900, 4),
    ('SEC_E', 'SECTION_E', 'Writing Skills', 'Write a short response to the prompts provided within the word limit.', 1200, 5),
]

QUESTIONS = [
    ('SECTION_A', 'SPEAK', 'Read Aloud', 'The quick brown fox jumps over the lazy dog.', {'rec': 45}),
    ('SECTION_A', 'SPEAK', 'Read Aloud', 'Modern technology has revolutionized the way we communicate.', {'rec': 45}),
    ('SECTION_A', 'SPEAK', 'Read Aloud', 'Environmental sustainability is a global responsibility.', {'rec': 45}),
    ('SECTION_A', 'SPEAK', 'Read Aloud', 'Effective leadership requires empathy and decisive action.', {'rec': 45}),
    ('SECTION_B', 'THINK_SPEAK', 'Topic Speech', 'Describe your dream job and why it appeals to you.', {'think': 30, 'rec': 60}),
    ('SECTION_B', 'THINK_SPEAK', 'Topic Speech', 'Talk about a challenge you overcame recently.', {'think': 30, 'rec': 60}),
    ('SECTION_B', 'THINK_SPEAK', 'Topic Speech', 'Discuss the advantages and disadvantages of remote work.', {'think': 30, 'rec': 60}),
    ('SECTION_B', 'THINK_SPEAK', 'Topic Speech', 'Who is your role model and why?', {'think': 30, 'rec': 60}),
    ('SECTION_C', 'MCQ', 'Grammar', 'She ___ to the market yesterday.', {'ot': 'Select Option', 'a': 'go', 'b': 'went', 'c': 'gone', 'd': 'going', 'ans': 'b'}),
    ('SECTION_C', 'MCQ', 'Grammar', 'I look forward ___ you soon.', {'ot': 'Select Option', 'a': 'to meet', 'b': 'meeting', 'c': 'to meeting', 'd': 'meet', 'ans': 'c'}),
    ('SECTION_C', 'MCQ', 'Grammar', 'They have lived here ___ 2010.', {'ot': 'Select Option', 'a': 'since', 'b': 'for', 'c': 'from', 'd': 'until', 'ans': 'a'}),
    ('SECTION_C', 'MCQ', 'Grammar', 'He is the ___ of the two brothers.', {'ot': 'Select Option', 'a': 'smart', 'b': 'smarter', 'c': 'smartest', 'd': 'more smart', 'ans': 'b'}),
    ('SECTION_D', 'COMPREHENSION', 'Listen & Answer', 'Did you listen to the audio clearly?', {'media': '/static/audio/sample_convo.mp3', 'ot': 'Confirm:', 'a': 'Yes', 'b': 'No', 'ans': 'a'}),
    ('SECTION_D', 'COMPREHENSION', 'Listen & Answer', 'What is the main topic of the conversation?', {'ot': 'Choose Answer:', 'a': 'Travel', 'b': 'Business Strategy', 'c': 'Weather', 'd': 'Food', 'ans': 'b'}),
    ('SECTION_D', 'COMPREHENSION', 'Listen & Answer', 'Why was the manager upset?', {'ot': 'Choose Answer:', 'a': 'Late delivery', 'b': 'High cost', 'c': 'Poor quality', 'd': 'Lost file', 'ans': 'a'}),
    ('SECTION_D', 'COMPREHENSION', 'Listen & Answer', 'What was the final decision?', {'ot': 'Choose Answer:', 'a': 'Cancel project', 'b': 'Hire staff', 'c': 'Extend deadline', 'd': 'Reduce budget', 'ans': 'c'}),
    ('SECTION_E', 'WRITING', 'Email Writing', 'Write an email to your manager asking for sick leave.', {'wl': 150}),
    ('SECTION_E', 'WRITING', 'Essay', 'The impact of Social Media on youth.', {'wl': 200}),
    ('SECTION_E', 'WRITING', 'Scenario', 'A client is angry about a delay. How do you respond?', {'wl': 100}),
    ('SECTION_E', 'WRITING', 'Opinion', 'Is AI helpful or harmful? Explain.', {'wl': 150}),
]


def main():
    cnx = mysql.connector.connect(host=Config.DATABASE_HOST, user=Config.DATABASE_USER,
                                  password=Config.DATABASE_PASSWORD, database=Config.DATABASE_NAME)
    cur = cnx.cursor(dictionary=True)

    cur.execute("SELECT code FROM course_content WHERE section_id=%s", (TEST_ID,))
    row = cur.fetchone()
    if not row:
        print(f"course_content section_id {TEST_ID!r} not found — pass a valid section id.")
        sys.exit(1)
    code = row['code']

    cur.execute("SELECT id FROM assessment_rounds WHERE round_type='COMM' LIMIT 1")
    r = cur.fetchone()
    round_id = r['id'] if r else None

    cur.execute("DELETE FROM comm_questions WHERE test_key=%s", (KEY,))
    cur.execute("DELETE FROM comm_sections WHERE test_key=%s", (KEY,))
    cur.execute("DELETE FROM comm_description WHERE test_key=%s", (KEY,))

    cur.execute("""INSERT INTO comm_description
        (test_id, code, test_key, subject_title, subject_subtitle, total_questions,
         total_marks, total_duration_minutes, round_id, requires_seb, difficulty_level)
        VALUES (%s, %s, %s, 'Advanced Communication Assessment', 'Sample full communication round',
                %s, 100, 45, %s, 0, 'Medium')""",
        (TEST_ID, code, KEY, len(QUESTIONS), round_id))
    cur.execute("SELECT id FROM comm_description WHERE test_key=%s", (KEY,))
    desc_id = cur.fetchone()['id']

    for sid, name, title, instr, dur, order in SECTIONS:
        cur.execute("""INSERT INTO comm_sections
            (test_key, section_id, section_name, section_title, section_instruction,
             section_duration_seconds, section_order)
            VALUES (%s,%s,%s,%s,%s,%s,%s)""", (KEY, sid, name, title, instr, dur, order))

    sec_ids = {name: sid for sid, name, *_ in SECTIONS}
    counters = {}
    for section, qtype, instr, text, kw in QUESTIONS:
        n = counters.get(section, 0) + 1
        counters[section] = n
        cur.execute("""INSERT INTO comm_questions
            (test_id, test_key, test_description_id, section_id, section_name, question_number,
             question_type, instruction_text, question_text, media_url, options_title,
             option_a, option_b, option_c, option_d, correct_option,
             recording_time_seconds, thinking_time_seconds, word_limit,
             correct_marks, negative_marks, question_level, created_at, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),NOW())""",
            (TEST_ID, KEY, desc_id, sec_ids[section], section, n, qtype, instr, text,
             kw.get('media'), kw.get('ot'), kw.get('a'), kw.get('b'), kw.get('c'), kw.get('d'),
             kw.get('ans'), kw.get('rec', 0), kw.get('think', 0), kw.get('wl', 0), 5, 0, 'Medium'))

    cnx.commit()
    print(f"Seeded {KEY}: {len(SECTIONS)} sections, {len(QUESTIONS)} questions "
          f"(description id {desc_id}) under course_content {TEST_ID} / course {code}.")
    cur.close()
    cnx.close()


if __name__ == '__main__':
    main()
