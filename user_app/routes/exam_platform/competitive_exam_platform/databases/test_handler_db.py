import logging
from routes.exam_platform.competitive_exam_platform.databases.main_handler_db import UserOperation

logger = logging.getLogger(__name__)
user_op = UserOperation()

class TestHandler:

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
        user_written_answer = user_answer.get('written_answer')
        status_of_attempt = user_answer.get('status_from_client', 'not_visited')
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
            'time_spent_on_question_seconds': user_answer.get('time_spent_on_question', 0),
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
        for detail in processed_answers:
            cursor.execute(query, (
                test_id, test_key, email, detail['question_id'], 
                ','.join(detail['user_selected_option']) if isinstance(detail['user_selected_option'], list) else detail['user_selected_option'],
                detail['user_written_answer'], detail['is_correct'], detail['marks_awarded'],
                detail['status_of_attempt'], detail['time_spent_on_question_seconds'], attempt_number
            ))

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

            test_status_info = user_op.get_test_status_for_user(email, test_key)
            attempt_number = test_status_info.get('attempt_number', 1)
            
            if test_status_info.get('status') != 'in_progress':
                logger.warning(f"Submission received for test {test_key} from user {email} but test status was not 'in_progress' (was {test_status_info.get('status')}).")
                return None, "Invalid test session. Submission rejected."

            questions_map = {q['id']: q for q in all_questions}
            processed_answers = [self._process_user_answer(ans, questions_map[ans['question_id']]) for ans in submitted_data.get('answers', [])]

            summary = self._calculate_test_summary(len(all_questions), processed_answers)
            total_marks = self._get_total_marks_for_test(test_key)
            percentage = self._calculate_percentage(summary['net_score'], total_marks)
            time_taken = submitted_data.get('total_time_taken', 0)
            device_info = submitted_data.get('device_info', 'Not Provided')

            db_connection = user_op.connection()
            cursor = db_connection.cursor(dictionary=True)
            db_connection.start_transaction()

            rank = self._calculate_submission_rank(cursor, test_key, summary['net_score'], time_taken)
            
            result_id = self._save_test_result_summary(
                cursor, email, username, test_id_section, test_key, course_code, summary, percentage, rank, time_taken, attempt_number
            )
            
            self._save_test_attempt_details(cursor, test_id_section, test_key, email, processed_answers, attempt_number)
            
            db_connection.commit()

            user_op.complete_user_test(email, test_key, device_info, attempt_number=attempt_number)
            
            return result_id, None

        except Exception as e:
            if db_connection:
                db_connection.rollback()
            logger.exception(f"Error saving test submission for user {email}, test_key {test_key}: {e}")
            return None, "An error occurred while saving the test results."
        finally:
            if db_connection:
                db_connection.close()
