import logging
from routes.exam_platform.competitive_exam_platform.databases.main_handler_db import UserOperation

logger = logging.getLogger(__name__)
user_op = UserOperation()

def _whole_seconds(value, limit=864000):
    try:
        seconds = int(float(value))
    except (TypeError, ValueError):
        return 0
    return max(0, min(seconds, limit))


class TestHandler:
    REJECTED = "Invalid test session. Submission rejected."

    def _get_total_marks_for_test(self, test_key):
        try:
            query = "SELECT SUM(correct_marks) as total_marks FROM test_questions WHERE test_key = %s"
            result = user_op.fetch_one(query, (test_key,))
            return float(result['total_marks']) if result and result['total_marks'] is not None else 0.0
        except Exception as e:
            logger.exception(f"Error fetching total marks for test_key: {test_key}")
            return 0.0

    def _calculate_percentage(self, net_score, total_test_marks):
        if total_test_marks is None or total_test_marks == 0:
            return 0.0
        try:
            percentage = (float(net_score) / float(total_test_marks)) * 100
            return round(percentage, 2)
        except TypeError:
            return 0.0

    def _calculate_submission_rank(self, cursor, test_key, net_score, time_taken):
        try:
            query = """
                SELECT COUNT(1) + 1 AS `rank` FROM test_result
                WHERE test_key = %s AND (net_score > %s OR (net_score = %s AND total_time_taken_seconds < %s))
            """
            cursor.execute(query, (test_key, net_score, net_score, time_taken))
            result = cursor.fetchone()
            return result['rank'] if result and result.get('rank') is not None else 1
        except Exception as e:
            logger.exception(f"Error calculating submission rank for test_key {test_key}: {e}")
            return 1

    def _process_user_answer(self, user_answer, question_details):
        user_selected_option = user_answer.get('selected_option')
        if isinstance(user_selected_option, (list, tuple)):
            user_selected_option = [str(opt).strip()[:1] for opt in user_selected_option if opt is not None][:8]
        elif user_selected_option is not None:
            user_selected_option = str(user_selected_option).strip()[:10]
        user_written_answer = user_answer.get('written_answer')
        if user_written_answer is not None:
            user_written_answer = str(user_written_answer)[:5000]
        status_of_attempt = str(user_answer.get('status_from_client') or 'not_visited')[:50]
        is_attempted = status_of_attempt in ['answered', 'answered_review', 'correct', 'incorrect', 'answered_marked_review']
        marks_awarded = 0.0
        is_correct = None

        if is_attempted:
            correct_option = str(question_details.get('correct_option', '')).strip().lower()
            q_type = question_details.get('question_type')

            if q_type == 'MSQ':
                user_ans_msq = sorted([str(opt).strip().lower() for opt in (user_selected_option or []) if opt])
                correct_ans_msq = sorted([str(opt).strip().lower() for opt in correct_option.split(',') if opt])
                is_correct = user_ans_msq == correct_ans_msq and bool(user_ans_msq)
            else:
                user_provided_answer = str(user_selected_option or user_written_answer or '').strip().lower()
                is_correct = user_provided_answer == correct_option

            if is_correct:
                marks_awarded = float(question_details.get('correct_marks', 0))
                status_of_attempt = 'correct'
            else:
                marks_awarded = -float(question_details.get('negative_marks', 0))
                status_of_attempt = 'incorrect'

        return {
            'question_id': user_answer.get('question_id'),
            'user_selected_option': user_selected_option,
            'user_written_answer': user_written_answer,
            'is_correct': is_correct,
            'marks_awarded': marks_awarded,
            'status_of_attempt': status_of_attempt,
            'time_spent_on_question_seconds': _whole_seconds(user_answer.get('time_spent_on_question', 0)),
            'is_attempted': is_attempted,
        }

    def _calculate_test_summary(self, total_questions, processed_answers):
        attempted_count = sum(1 for a in processed_answers if a['is_attempted'])
        correct_count = sum(1 for a in processed_answers if a['is_correct'])
        incorrect_count = attempted_count - correct_count
        net_score = sum(a['marks_awarded'] for a in processed_answers)
        accuracy = (correct_count / attempted_count * 100) if attempted_count > 0 else 0.0

        return {
            'attempted_questions_count': attempted_count,
            'unattempted_questions_count': total_questions - attempted_count,
            'correctly_answered_questions_count': correct_count,
            'incorrectly_answered_questions_count': incorrect_count,
            'marks_for_correct_answers': sum(a['marks_awarded'] for a in processed_answers if a['is_correct']),
            'penalty_for_incorrect_answers': abs(sum(a['marks_awarded'] for a in processed_answers if not a['is_correct'] and a['is_attempted'])),
            'net_score': round(net_score, 2),
            'accuracy': round(accuracy, 2),
        }

    def _save_test_result_summary(self, cursor, email, username, test_id, test_key, test_code, summary_data, percentage, rank, time_taken, attempt_number):
        query = """
            INSERT INTO test_result (
                email, username, test_id, test_key, test_code, attempted_questions_count,
                unattempted_questions_count, correctly_answered_questions_count,
                incorrectly_answered_questions_count, marks_for_correct_answers,
                penalty_for_incorrect_answers, net_score, accuracy,
                percentage, submission_ranker, total_time_taken_seconds, submission_timestamp, attempt_number
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s)
        """
        params = (
            email, username, test_id, test_key, test_code, 
            summary_data['attempted_questions_count'], summary_data['unattempted_questions_count'],
            summary_data['correctly_answered_questions_count'], summary_data['incorrectly_answered_questions_count'],
            summary_data['marks_for_correct_answers'], summary_data['penalty_for_incorrect_answers'],
            summary_data['net_score'], summary_data['accuracy'],
            percentage, rank, time_taken, attempt_number
        )
        cursor.execute(query, params)
        return cursor.lastrowid

    def _save_test_attempt_details(self, cursor, test_id, test_key, email, processed_answers, attempt_number):
        query = """
            INSERT INTO test_attempt_details (
                test_id, test_key, email, question_id, user_selected_option, user_written_answer,
                is_correct, marks_awarded, status_of_attempt, time_spent_on_question_seconds, attempt_number
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        if not processed_answers:
            return
        cursor.executemany(query, [(
            test_id, test_key, email, detail['question_id'],
            ','.join(detail['user_selected_option'])[:10] if isinstance(detail['user_selected_option'], list) else detail['user_selected_option'],
            detail['user_written_answer'], detail['is_correct'], detail['marks_awarded'],
            detail['status_of_attempt'], detail['time_spent_on_question_seconds'], attempt_number
        ) for detail in processed_answers])

    def completed_result_id(self, email, test_key, within_minutes=30):
        try:
            row = user_op.fetch_one(
                "SELECT l.status, r.id AS result_id, "
                "       TIMESTAMPDIFF(MINUTE, l.end_time, NOW()) AS minutes_ago "
                "FROM user_test_log l "
                "LEFT JOIN test_result r ON r.email = l.email AND r.test_key = l.test_key "
                "     AND r.attempt_number = l.attempt_number "
                "WHERE l.email = %s AND l.test_key = %s "
                "ORDER BY l.attempt_number DESC LIMIT 1",
                (email, test_key),
            )
        except Exception:
            logger.exception(f"Error reading the last attempt of {email} for {test_key}")
            return None
        if not row or row.get('status') != 'completed' or not row.get('result_id'):
            return None
        minutes_ago = row.get('minutes_ago')
        if minutes_ago is None or minutes_ago > within_minutes:
            return None
        return row['result_id']

    def save_test_submission(self, email, username, test_key, submitted_data):
        db_connection = None
        try:
            all_questions = user_op.get_all_test_questions(test_key)
            if not all_questions:
                return None, "Could not retrieve test questions."

            test_details = user_op.get_test_details(test_key)
            if not test_details:
                return None, "Could not retrieve test details."

            test_id_section = test_details['test_id']
            course_code = user_op.get_course_code_from_test_id(test_id_section)
            if not course_code:
                return None, "Could not resolve course details for the test."

            questions_map = {q['id']: q for q in all_questions}
            answers = {}
            raw_answers = submitted_data.get('answers')
            for ans in (raw_answers if isinstance(raw_answers, list) else []):
                if not isinstance(ans, dict):
                    continue
                try:
                    question_id = int(ans.get('question_id'))
                except (TypeError, ValueError):
                    continue
                if question_id in questions_map:
                    answers[question_id] = dict(ans, question_id=question_id)
            processed_answers = [self._process_user_answer(ans, questions_map[question_id])
                                 for question_id, ans in answers.items()]

            summary = self._calculate_test_summary(len(all_questions), processed_answers)
            total_marks = sum(float(q.get('correct_marks') or 0) for q in all_questions)
            percentage = self._calculate_percentage(summary['net_score'], total_marks)
            time_taken = _whole_seconds(submitted_data.get('total_time_taken', 0))
            device_info = str(submitted_data.get('device_info') or 'Not Provided')[:1000]

            db_connection = user_op.connection()
            cursor = db_connection.cursor(dictionary=True)
            db_connection.start_transaction()

            cursor.execute(
                "SELECT attempt_number, status FROM user_test_log "
                "WHERE email = %s AND test_key = %s ORDER BY attempt_number DESC LIMIT 1 FOR UPDATE",
                (email, test_key),
            )
            attempt_row = cursor.fetchone()
            if attempt_row and attempt_row.get('status') == 'completed':
                cursor.execute(
                    "SELECT id FROM test_result WHERE email = %s AND test_key = %s AND attempt_number = %s",
                    (email, test_key, attempt_row['attempt_number']),
                )
                saved = cursor.fetchone()
                if saved:
                    db_connection.rollback()
                    logger.info(f"Submission repeated for test {test_key} by {email}; the saved result {saved['id']} is returned.")
                    return saved['id'], None
            if not attempt_row or attempt_row.get('status') != 'in_progress':
                db_connection.rollback()
                logger.warning(f"Submission received for test {test_key} from user {email} but test status was "
                               f"not 'in_progress' (was {attempt_row.get('status') if attempt_row else 'missing'}).")
                return None, self.REJECTED
            attempt_number = attempt_row['attempt_number']

            rank = self._calculate_submission_rank(cursor, test_key, summary['net_score'], time_taken)
            
            result_id = self._save_test_result_summary(
                cursor, email, username, test_id_section, test_key, course_code, summary, percentage, rank, time_taken, attempt_number
            )
            
            self._save_test_attempt_details(cursor, test_id_section, test_key, email, processed_answers, attempt_number)

            cursor.execute(
                "UPDATE user_test_log SET status = 'completed', end_time = NOW(), device_info = %s "
                "WHERE email = %s AND test_key = %s AND attempt_number = %s AND status = 'in_progress'",
                (device_info, email, test_key, attempt_number),
            )
            db_connection.commit()
            return result_id, None

        except Exception as e:
            if db_connection:
                db_connection.rollback()
            logger.exception(f"Error saving test submission for user {email}, test_key {test_key}: {e}")
            return None, "An error occurred while saving the test results."
        finally:
            if db_connection:
                db_connection.close()
