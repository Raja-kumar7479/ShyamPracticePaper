import mysql.connector
import logging
import sys
import uuid
import datetime
import os
import json
from config import Config

from routes.exam_platform.placement_exam_portal.rounds import classify_round

logger = logging.getLogger(__name__)

class ProctorDB:
    def __init__(self):
        pass

    def get_conn(self):
        try:
            from routes.db_pool import get_connection
            return get_connection()
        except mysql.connector.Error as err:
            logger.critical(f"DB: Connection Failed: {err}")
            raise Exception("Database Connection Failed")

    CONCURRENT_ACTIVE_SECONDS = 90

    def check_concurrent_session(self, email, current_test_key):
        conn = None
        cursor = None
        try:
            conn = self.get_conn()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                UPDATE comm_user_log
                SET status = 'terminated', session_token = NULL, tab_id = NULL
                WHERE email = %s AND status = 'started' AND test_key != %s
                  AND TIMESTAMPDIFF(SECOND, COALESCE(last_heartbeat, start_time), NOW()) > %s
            """, (email, current_test_key, self.CONCURRENT_ACTIVE_SECONDS))
            if cursor.rowcount:
                logger.info(f"CONCURRENT: released {cursor.rowcount} stale comm session(s) for {email}")
            conn.commit()
            cursor.execute("""
                SELECT test_key, status, start_time
                FROM comm_user_log
                WHERE email = %s AND status = 'started' AND test_key != %s
                  AND TIMESTAMPDIFF(SECOND, COALESCE(last_heartbeat, start_time), NOW()) <= %s
            """, (email, current_test_key, self.CONCURRENT_ACTIVE_SECONDS))
            return cursor.fetchone()
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def generate_session_token(self, email, test_key, course_code, unique_code):
        conn = None
        cursor = None
        if not email or not test_key:
            logger.warning(f"DB: Token Gen refused for email={email!r} test_key={test_key!r}")
            return None
        try:
            conn = self.get_conn()
            cursor = conn.cursor()
            
            check_query = "SELECT status FROM comm_user_log WHERE email=%s AND test_key=%s"
            cursor.execute(check_query, (email, test_key))
            existing = cursor.fetchone()
            
            if existing and existing[0] == 'completed':
                return None 

            token = str(uuid.uuid4())
            expiry = datetime.datetime.now() + datetime.timedelta(hours=4)
            
            query = """
                INSERT INTO comm_user_log (email, test_key, course_code, unique_code, status, session_token, token_expiry, start_time)
                VALUES (%s, %s, %s, %s, 'started', %s, %s, NOW())
                ON DUPLICATE KEY UPDATE 
                session_token=%s, token_expiry=%s, status='started', course_code=%s, unique_code=%s
            """
            cursor.execute(query, (email, test_key, course_code, unique_code, token, expiry, token, expiry, course_code, unique_code))
            conn.commit()
            return token
        except Exception as e:
            logger.error(f"DB: Token Gen Error: {e}")
            return None
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def validate_token(self, email, test_key, token):
        conn = None
        cursor = None
        if not email or not test_key or not token:
            return False
        try:
            conn = self.get_conn()
            cursor = conn.cursor(dictionary=True)
            query = """
                SELECT * FROM comm_user_log 
                WHERE email=%s AND test_key=%s AND session_token=%s AND status='started'
            """
            cursor.execute(query, (email, test_key, token))
            res = cursor.fetchone()
            if res and res['token_expiry'] > datetime.datetime.now():
                return True
            return False
        except Exception as e:
            logger.error(f"DB: Validate Token Error: {e}")
            return False
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def calculate_score(self, q_id_str, user_ans, test_key=None):
        if not user_ans:
            return 0

        real_id = q_id_str
        sub_idx = None
        
        if "_" in str(q_id_str):
            parts = str(q_id_str).split('_')
            real_id = parts[0]
            try:
                sub_idx = int(parts[1])
            except (ValueError, IndexError):
                sub_idx = None

        conn = None
        cursor = None
        try:
            conn = self.get_conn()
            cursor = conn.cursor(dictionary=True)
            if test_key:
                cursor.execute("SELECT correct_option, sub_questions FROM comm_questions WHERE id=%s AND test_key=%s", (real_id, test_key))
            else:
                cursor.execute("SELECT correct_option, sub_questions FROM comm_questions WHERE id=%s", (real_id,))
            row = cursor.fetchone()

            if not row:
                return 0

            correct_val = None
            
            if sub_idx is not None and row['sub_questions']:
                try:
                    subs = json.loads(row['sub_questions']) if isinstance(row['sub_questions'], str) else row['sub_questions']
                    if 0 <= sub_idx < len(subs):
                        correct_val = subs[sub_idx].get('correct_option')
                except (ValueError, TypeError, KeyError, IndexError):
                    pass
            else:
                correct_val = row['correct_option']

            if correct_val and str(correct_val).strip().lower() == str(user_ans).strip().lower():
                return 100
            
            return 0
        except Exception as e:
            logger.error(f"Score Calc Error: {e}")
            return 0
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def get_assessment_sections(self, test_key):
        conn = self.get_conn()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("""
                SELECT s.section_id, s.section_name, s.section_title, s.section_instruction,
                       s.section_duration_seconds, s.section_order,
                       (SELECT COUNT(*) FROM comm_questions q
                        WHERE q.test_key = s.test_key AND q.section_name = s.section_name) AS question_count
                FROM comm_sections s
                WHERE s.test_key = %s
                ORDER BY s.section_order, s.id
            """, (test_key,))
            rows = cursor.fetchall()
            if rows:
                return rows
            cursor.execute("""
                SELECT q.section_name,
                       q.section_name AS section_title,
                       '' AS section_instruction,
                       FLOOR(cd.total_duration_minutes * 60 /
                             (SELECT COUNT(DISTINCT section_name) FROM comm_questions WHERE test_key = q.test_key)
                       ) AS section_duration_seconds,
                       COUNT(q.id) AS question_count
                FROM comm_questions q
                JOIN comm_description cd ON cd.test_key = q.test_key
                WHERE q.test_key = %s
                GROUP BY q.section_name, cd.total_duration_minutes
                ORDER BY MIN(q.question_number)
            """, (test_key,))
            return cursor.fetchall()
        finally:
            cursor.close(); conn.close()

    def get_assessment_meta(self, test_key):
        conn = self.get_conn(); cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("""
                SELECT cd.subject_title AS assessment_title, cd.test_id,
                       cd.total_duration_minutes AS duration_minutes,
                       (SELECT COUNT(*) FROM comm_questions q WHERE q.test_key = cd.test_key) AS total_questions,
                       COALESCE(NULLIF((SELECT COUNT(*) FROM comm_sections s WHERE s.test_key = cd.test_key), 0),
                                (SELECT COUNT(DISTINCT q.section_name) FROM comm_questions q WHERE q.test_key = cd.test_key)
                       ) AS total_sections,
                       cd.total_marks, COALESCE(cd.requires_seb, 0) AS requires_seb,
                       COALESCE((SELECT SUM(s.section_duration_seconds) FROM comm_sections s WHERE s.test_key = cd.test_key),
                                cd.total_duration_minutes * 60) AS total_duration
                FROM comm_description cd WHERE cd.test_key = %s
            """, (test_key,))
            return cursor.fetchone()
        finally:
            cursor.close(); conn.close()

    def get_all_questions(self, test_key):
        conn = self.get_conn(); cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("""
                SELECT *, UPPER(question_type) AS question_type
                FROM comm_questions
                WHERE test_key = %s
                ORDER BY section_name, question_number, id
            """, (test_key,))
            return cursor.fetchall()
        finally:
            cursor.close(); conn.close()

    def submit_attempt(self, data):
        conn = self.get_conn(); cursor = conn.cursor()
        try:
            query = "INSERT INTO comm_attempt_details (email, test_key, question_id, section_name, selected_option, text_response, audio_response_path, transcription_text, accuracy_score, recording_duration, is_submitted, is_marked_for_review) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, 0) ON DUPLICATE KEY UPDATE selected_option=%s, text_response=%s, audio_response_path=%s, transcription_text=%s, accuracy_score=%s, recording_duration=%s, is_submitted=1, created_at=NOW()"
            p = (data['email'], data['test_key'], data['question_id'], data['section_name'], data['selected_option'], data['text_response'], data['audio_path'], data['transcription'], data['score'], data['rec_time'], data['selected_option'], data['text_response'], data['audio_path'], data['transcription'], data['score'], data['rec_time'])
            cursor.execute(query, p); conn.commit(); return True
        except Exception as e:
            logger.error(f"DB: submit_attempt Error: {e}"); return False
        finally:
            cursor.close(); conn.close()

    def get_round_for_test_key(self, test_key):
        conn = self.get_conn(); cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("""
                SELECT r.round_name FROM comm_description cd
                JOIN assessment_rounds r ON r.id = cd.round_id
                WHERE cd.test_key = %s LIMIT 1
            """, (test_key,))
            row = cursor.fetchone()
            if row and row['round_name']:
                return row['round_name']
            cursor.execute("""
                SELECT cc.title FROM comm_description cd
                JOIN course_content cc ON cc.section_id = cd.test_id
                WHERE cd.test_key = %s LIMIT 1
            """, (test_key,))
            row = cursor.fetchone()
            return classify_round(row['title']) if row else None
        finally:
            cursor.close(); conn.close()

    def finish_test_session(self, email, test_key):
        conn = self.get_conn(); cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("UPDATE comm_user_log SET status='completed', end_time=NOW(), session_token=NULL WHERE email=%s AND test_key=%s", (email, test_key))
            cursor.execute("""
                SELECT COUNT(*) AS attempted,
                       SUM(CASE WHEN accuracy_score = 100 THEN 1 ELSE 0 END) AS correct,
                       COALESCE(AVG(accuracy_score), 0) AS accuracy
                FROM comm_attempt_details WHERE email=%s AND test_key=%s AND is_submitted=1
            """, (email, test_key))
            stats = cursor.fetchone()
            cursor.execute("SELECT test_id, code, total_questions, total_marks FROM comm_description WHERE test_key=%s", (test_key,))
            cd = cursor.fetchone()
            if cd:
                attempted = int(stats['attempted'] or 0)
                correct = int(stats['correct'] or 0)
                total_q = int(cd['total_questions'] or 0)
                cursor.execute("""
                    INSERT INTO comm_result (
                        email, test_id, test_key, test_code, attempted_questions_count,
                        unattempted_questions_count, correctly_answered_questions_count,
                        incorrectly_answered_questions_count, net_score, accuracy,
                        percentage, submission_timestamp
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                """, (email, cd['test_id'], test_key, cd['code'], attempted,
                      max(0, total_q - attempted), correct, attempted - correct,
                      correct, round(float(stats['accuracy'] or 0), 2),
                      round((correct / total_q * 100) if total_q else 0, 2)))
            conn.commit(); return True
        except Exception:
            logger.exception(f"finish_test_session failed for {email}, {test_key}")
            conn.rollback(); return False
        finally: cursor.close(); conn.close()

    def get_question_text(self, q_id_str, test_key):
        real_id = str(q_id_str)
        sub_idx = None
        if '_' in real_id:
            parts = real_id.split('_')
            real_id = parts[0]
            try:
                sub_idx = int(parts[1])
            except (ValueError, IndexError):
                sub_idx = None
        conn = self.get_conn(); cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT question_text, sub_questions FROM comm_questions WHERE id=%s AND test_key=%s",
                           (real_id, test_key))
            row = cursor.fetchone()
            if not row:
                return ''
            if sub_idx is not None and row.get('sub_questions'):
                try:
                    subs = json.loads(row['sub_questions']) if isinstance(row['sub_questions'], str) else row['sub_questions']
                    if 0 <= sub_idx < len(subs):
                        return subs[sub_idx].get('text') or ''
                except (ValueError, TypeError, KeyError):
                    pass
            return row.get('question_text') or ''
        finally:
            cursor.close(); conn.close()

    def ensure_comm_share_code(self, email, test_key):
        import secrets
        conn = self.get_conn(); cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT share_code FROM comm_user_log WHERE email=%s AND test_key=%s",
                           (email, test_key))
            row = cursor.fetchone()
            if not row:
                return None
            if row.get('share_code'):
                return row['share_code']
            code = secrets.token_urlsafe(12)[:16]
            cursor.execute("UPDATE comm_user_log SET share_code=%s "
                           "WHERE email=%s AND test_key=%s AND share_code IS NULL",
                           (code, email, test_key))
            conn.commit()
            cursor.execute("SELECT share_code FROM comm_user_log WHERE email=%s AND test_key=%s",
                           (email, test_key))
            row = cursor.fetchone()
            return row['share_code'] if row else code
        finally:
            cursor.close(); conn.close()

    def get_comm_certificate(self, code):
        conn = self.get_conn(); cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("""
                SELECT l.test_key, l.share_code,
                       u.username,
                       cd.subject_title AS test_title,
                       cd.total_duration_minutes AS duration_minutes,
                       r.net_score, r.percentage, r.submission_timestamp
                FROM comm_user_log l
                JOIN auth u ON u.email = l.email
                JOIN comm_description cd ON cd.test_key = l.test_key
                LEFT JOIN comm_result r ON r.email = l.email AND r.test_key = l.test_key
                WHERE l.share_code = %s AND l.status = 'completed'
                ORDER BY r.attempt_number DESC, r.id DESC
                LIMIT 1
            """, (code,))
            return cursor.fetchone()
        finally:
            cursor.close(); conn.close()

    def clear_attempt_details(self, email, test_key):
        conn = self.get_conn(); cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM comm_attempt_details WHERE email=%s AND test_key=%s",
                           (email, test_key))
            removed = cursor.rowcount
            conn.commit()
            return removed
        finally:
            cursor.close(); conn.close()

    def get_result_report(self, email, test_key):
        conn = self.get_conn(); cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT subject_title AS title, test_id FROM comm_description WHERE test_key=%s", (test_key,))
            meta = cursor.fetchone() or {}

            try:
                cursor.execute("""
                    SELECT section_name, section_title, section_order FROM comm_sections
                    WHERE test_key = %s ORDER BY section_order
                """, (test_key,))
                rows = cursor.fetchall()
                section_order = [r['section_name'] for r in rows]
                section_titles = {r['section_name']: r['section_title'] for r in rows}
            except Exception:
                section_order = []
                section_titles = {}

            cursor.execute("""
                SELECT id, section_name, question_text, UPPER(question_type) AS question_type,
                       instruction_text, media_url, word_limit,
                       recording_time_seconds, thinking_time_seconds,
                       correct_option, options_title, option_a, option_b, option_c, option_d,
                       sub_questions
                FROM comm_questions WHERE test_key = %s
                ORDER BY section_name, question_number, id
            """, (test_key,))
            raw_questions = cursor.fetchall()

            cursor.execute("""
                SELECT question_id, selected_option, text_response, audio_response_path,
                       transcription_text, accuracy_score, recording_duration, section_name
                FROM comm_attempt_details WHERE email=%s AND test_key=%s
            """, (email, test_key))
            attempts = {str(a['question_id']): a for a in cursor.fetchall()}

            questions = []
            for q in raw_questions:
                if q.get('sub_questions'):
                    try:
                        subs = json.loads(q['sub_questions']) if isinstance(q['sub_questions'], str) else q['sub_questions']
                        for idx, sub in enumerate(subs):
                            item = dict(q)
                            item['id'] = f"{q['id']}_{idx}"
                            item['question_text'] = sub.get('text')
                            item['correct_option'] = sub.get('correct_option')
                            questions.append(item)
                        continue
                    except (ValueError, TypeError, KeyError):
                        pass
                questions.append(dict(q))

            sections = {}
            for q in questions:
                sec = q.get('section_name') or 'General'
                entry = sections.setdefault(sec, {
                    'name': sec, 'questions': [], 'total': 0, 'attempted': 0,
                    'correct': 0, 'scorable': 0, 'spoken_seconds': 0.0, 'has_audio': False
                })
                a = attempts.get(str(q['id']))
                qtype = (q.get('question_type') or '').upper()
                scorable = bool(q.get('correct_option')) and qtype not in ('AUDIO', 'SPEAKING', 'RECORDING')
                answer_text = None
                status = 'skipped'
                if a:
                    answer_text = a.get('selected_option') or a.get('text_response')
                    if a.get('audio_response_path'):
                        status = 'recorded'
                        entry['has_audio'] = True
                        entry['spoken_seconds'] += float(a.get('recording_duration') or 0)
                    elif answer_text:
                        status = 'answered'
                    if scorable and answer_text is not None:
                        status = 'correct' if (a.get('accuracy_score') or 0) >= 100 else 'incorrect'
                entry['total'] += 1
                entry['attempted'] += 1 if (a and (answer_text or a.get('audio_response_path'))) else 0
                if scorable:
                    entry['scorable'] += 1
                    if status == 'correct':
                        entry['correct'] += 1
                speech = None
                if a and a.get('audio_response_path'):
                    from routes.exam_platform.placement_exam_portal.communication_portal.utils.speech_analysis import analyse_speech
                    speech = analyse_speech(q.get('question_text'), a.get('transcription_text'),
                                            float(a.get('recording_duration') or 0))
                    if a.get('transcription_text') and speech.get('accuracy_pct') is not None:
                        entry.setdefault('speech_scores', []).append(speech['accuracy_pct'])
                entry['questions'].append({
                    'id': q['id'], 'text': q.get('question_text'), 'type': qtype,
                    'instruction': q.get('instruction_text'),
                    'word_limit': q.get('word_limit') or 0,
                    'recording_time': q.get('recording_time_seconds') or 0,
                    'thinking_time': q.get('thinking_time_seconds') or 0,
                    'options': {k: q.get('option_' + k) for k in ('a', 'b', 'c', 'd') if q.get('option_' + k)},
                    'options_title': q.get('options_title'),
                    'correct_option': q.get('correct_option'),
                    'your_answer': answer_text,
                    'audio_path': (a or {}).get('audio_response_path'),
                    'transcription': (a or {}).get('transcription_text'),
                    'duration': float((a or {}).get('recording_duration') or 0),
                    'status': status, 'scorable': scorable,
                    'speech': speech,
                })

            ordered = [sections[s] for s in section_order if s in sections]
            ordered += [v for k, v in sections.items() if k not in section_order]
            for sec in ordered:
                sec['title'] = section_titles.get(sec['name']) or sec['name'].replace('_', ' ').title()
                sec['score_pct'] = round(100.0 * sec['correct'] / sec['scorable'], 1) if sec['scorable'] else None
                sec['attempt_pct'] = round(100.0 * sec['attempted'] / sec['total'], 1) if sec['total'] else 0
                voiced = [v for v in sec.get('speech_scores', []) if v is not None]
                sec['speech_accuracy'] = round(sum(voiced) / len(voiced), 1) if voiced else None
                sec.pop('speech_scores', None)

            total_q = sum(s['total'] for s in ordered)
            attempted = sum(s['attempted'] for s in ordered)
            scorable = sum(s['scorable'] for s in ordered)
            correct = sum(s['correct'] for s in ordered)
            report = {
                'title': meta.get('title') or 'Assessment',
                'test_key': test_key,
                'total_questions': total_q,
                'attempted': attempted,
                'skipped': total_q - attempted,
                'scorable': scorable,
                'correct': correct,
                'overall_pct': round(100.0 * correct / scorable, 1) if scorable else None,
                'speaking_accuracy': (lambda v: round(sum(v) / len(v), 1) if v else None)(
                    [s['speech_accuracy'] for s in ordered if s.get('speech_accuracy') is not None]),
                'spoken_seconds': round(sum(s['spoken_seconds'] for s in ordered)),
                'sections': ordered,
            }
            logger.info(f"RESULT REPORT: [{email}] {test_key} -> {total_q} Q, {attempted} attempted, "
                        f"{correct}/{scorable} correct, {len(ordered)} section(s)")
            return report
        finally: cursor.close(); conn.close()

    SECTION_ICONS = {
        'SPEAK': 'fa-microphone-lines', 'THINK_SPEAK': 'fa-comment-dots',
        'WRITING': 'fa-pen-nib', 'COMPREHENSION': 'fa-headphones', 'MCQ': 'fa-list-check',
    }

    def _dominant_type(self, section):
        counts = {}
        for q in section['questions']:
            counts[q['type']] = counts.get(q['type'], 0) + 1
        return max(counts, key=counts.get) if counts else 'MCQ'

    def get_result_overview(self, email, test_key):
        report = self.get_result_report(email, test_key)
        cards = []
        for idx, sec in enumerate(report['sections'], start=1):
            dom = self._dominant_type(sec)
            if sec['score_pct'] is not None:
                headline, metric = f"{sec['score_pct']}%", 'score'
            elif sec.get('speech_accuracy') is not None:
                headline, metric = f"{sec['speech_accuracy']}%", 'speech match'
            else:
                headline, metric = f"{sec['attempted']}/{sec['total']}", 'attempted'
            cards.append({
                'index': idx,
                'name': sec['name'],
                'title': sec['title'],
                'icon': self.SECTION_ICONS.get(dom, 'fa-layer-group'),
                'type': dom,
                'total': sec['total'],
                'attempted': sec['attempted'],
                'headline': headline,
                'metric': metric,
                'score_pct': sec['score_pct'],
                'speech_accuracy': sec.get('speech_accuracy'),
                'attempt_pct': sec['attempt_pct'],
            })
        return {
            'title': report['title'], 'test_key': test_key,
            'total_questions': report['total_questions'], 'attempted': report['attempted'],
            'skipped': report['skipped'], 'scorable': report['scorable'], 'correct': report['correct'],
            'overall_pct': report['overall_pct'], 'speaking_accuracy': report['speaking_accuracy'],
            'spoken_seconds': report['spoken_seconds'], 'cards': cards,
        }

    def get_full_analysis(self, email, test_key):
        report = self.get_result_report(email, test_key)
        from routes.exam_platform.placement_exam_portal.communication_portal.utils.content_analysis import analyse_content
        for idx, sec in enumerate(report['sections'], start=1):
            sec['index'] = idx
            dom = self._dominant_type(sec)
            sec['dom_type'] = dom
            sec['icon'] = self.SECTION_ICONS.get(dom, 'fa-layer-group')
            if sec['score_pct'] is not None:
                sec['headline'], sec['metric'] = f"{sec['score_pct']}%", 'score'
            elif sec.get('speech_accuracy') is not None:
                sec['headline'], sec['metric'] = f"{sec['speech_accuracy']}%", 'speech match'
            else:
                sec['headline'], sec['metric'] = f"{sec['attempted']}/{sec['total']}", 'attempted'
            sec['ring_pct'] = (sec['score_pct'] if sec['score_pct'] is not None
                               else (sec.get('speech_accuracy') if sec.get('speech_accuracy') is not None
                                     else sec['attempt_pct']))
            for q in sec['questions']:
                q['content'] = None
                is_open = q['type'] in ('WRITING', 'THINK_SPEAK') or (q['type'] == 'SPEAK' and q.get('transcription'))
                source = q.get('transcription') if q['type'] in ('SPEAK', 'THINK_SPEAK') else q.get('your_answer')
                if is_open and source:
                    mode = 'speaking' if q['type'] in ('SPEAK', 'THINK_SPEAK') else 'writing'
                    q['content'] = analyse_content(q.get('text'), source, mode=mode,
                                                   word_limit=q.get('word_limit') or 0,
                                                   duration_seconds=q.get('duration') or 0)
        return report

    def get_section_detail(self, email, test_key, index):
        report = self.get_result_report(email, test_key)
        sections = report['sections']
        if index < 1 or index > len(sections):
            return None
        sec = sections[index - 1]
        dom = self._dominant_type(sec)

        from routes.exam_platform.placement_exam_portal.communication_portal.utils.content_analysis import analyse_content
        for q in sec['questions']:
            q['content'] = None
            written = q.get('your_answer')
            is_open = q['type'] in ('WRITING', 'THINK_SPEAK') or (q['type'] == 'SPEAK' and q.get('transcription'))
            source = q.get('transcription') if q['type'] in ('SPEAK', 'THINK_SPEAK') else written
            if is_open and source:
                mode = 'speaking' if q['type'] in ('SPEAK', 'THINK_SPEAK') else 'writing'
                q['content'] = analyse_content(q.get('text'), source, mode=mode,
                                               duration_seconds=q.get('duration') or 0)

        return {
            'title': report['title'], 'test_key': test_key,
            'index': index, 'total_sections': len(sections),
            'section': sec, 'dom_type': dom,
            'icon': self.SECTION_ICONS.get(dom, 'fa-layer-group'),
            'prev_index': index - 1 if index > 1 else None,
            'next_index': index + 1 if index < len(sections) else None,
        }

    def get_proctor_snaps(self, email, test_key):
        conn = self.get_conn(); cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("""
                SELECT snapshot_path, log_type, timestamp
                FROM comm_proctoring_logs
                WHERE email = %s AND test_key = %s AND snapshot_path IS NOT NULL
                ORDER BY timestamp
            """, (email, test_key))
            snaps = []
            for r in cursor.fetchall():
                path = (r['snapshot_path'] or '').replace('\\', '/')
                if not path:
                    continue
                snaps.append({
                    'url': path if path.startswith('/') else '/' + path,
                    'log_type': r['log_type'] or 'interval_snap',
                    'timestamp': r['timestamp'],
                })
            return snaps
        finally:
            cursor.close(); conn.close()

    def get_result_history(self, email, test_key):
        conn = self.get_conn(); cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("""
                SELECT accuracy, percentage, attempted_questions_count,
                       correctly_answered_questions_count, submission_timestamp
                FROM comm_result
                WHERE email = %s AND test_key = %s
                ORDER BY submission_timestamp
            """, (email, test_key))
            history = []
            for r in cursor.fetchall():
                history.append({
                    'when': r['submission_timestamp'].strftime('%d %b %I:%M %p') if r['submission_timestamp'] else '',
                    'accuracy': float(r['accuracy'] or 0),
                    'percentage': float(r['percentage'] or 0),
                    'correct': int(r['correctly_answered_questions_count'] or 0),
                    'attempted': int(r['attempted_questions_count'] or 0),
                })
            return history
        finally:
            cursor.close(); conn.close()

    def get_test_percentile(self, email, test_key):
        conn = self.get_conn(); cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("""
                SELECT email, MAX(percentage) AS best
                FROM comm_result WHERE test_key = %s
                GROUP BY email
            """, (test_key,))
            rows = cursor.fetchall()
            if len(rows) < 3:
                return None
            mine = None
            others = []
            for r in rows:
                score = float(r['best'] or 0)
                if r['email'] == email:
                    mine = score
                else:
                    others.append(score)
            if mine is None or not others:
                return None
            below = sum(1 for s in others if s < mine)
            return {
                'percentile': round(100.0 * below / len(others)),
                'takers': len(rows),
                'best': mine,
            }
        finally:
            cursor.close(); conn.close()

    def get_completion_time(self, email, test_key):
        conn = self.get_conn(); cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT end_time FROM comm_user_log WHERE email=%s AND test_key=%s", (email, test_key))
            row = cursor.fetchone()
            return row['end_time'] if row else None
        finally:
            cursor.close(); conn.close()

    def get_user_test_status(self, email, test_key):
        conn = self.get_conn(); cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT status FROM comm_user_log WHERE email=%s AND test_key=%s",
                           (email, test_key))
            row = cursor.fetchone()
            return row['status'] if row else None
        finally:
            cursor.close(); conn.close()

    def save_feedback(self, email, test_key, rating, comments):
        conn = self.get_conn(); cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT test_id FROM comm_description WHERE test_key=%s", (test_key,))
            cd = cursor.fetchone()
            cursor.execute("""
                INSERT INTO comm_feedback (email, test_id, test_key, feedback_content, suggestions)
                VALUES (%s, %s, %s, %s, %s)
            """, (email, cd['test_id'] if cd else '', test_key, rating, comments))
            conn.commit(); return True
        except Exception:
            logger.exception(f"save_feedback failed for {email}, {test_key}")
            return False
        finally: cursor.close(); conn.close()

    def cleanup_user_data(self, email, test_key):
        conn = self.get_conn(); cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT audio_response_path FROM comm_attempt_details WHERE email=%s AND test_key=%s", (email, test_key))
            for rec in cursor.fetchall():
                if rec['audio_response_path'] and os.path.exists(rec['audio_response_path']): os.remove(rec['audio_response_path'])
            cursor.execute("SELECT snapshot_path FROM comm_proctoring_logs WHERE email=%s AND test_key=%s", (email, test_key))
            for rec in cursor.fetchall():
                if rec['snapshot_path'] and os.path.exists(rec['snapshot_path']): os.remove(rec['snapshot_path'])
            cursor.execute("DELETE FROM comm_attempt_details WHERE email=%s AND test_key=%s", (email, test_key))
            cursor.execute("DELETE FROM comm_proctoring_logs WHERE email=%s AND test_key=%s", (email, test_key))
            conn.commit(); return True
        except Exception: return False
        finally: cursor.close(); conn.close()