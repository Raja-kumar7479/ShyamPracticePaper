import logging
from routes.exam_platform.competitive_exam_platform.databases.main_handler_db import UserOperation

logger = logging.getLogger(__name__)
user_op = UserOperation()

class ResultHandler:

    def _get_total_marks_for_test(self, test_key):
        try:
            query = "SELECT SUM(correct_marks) as total_marks FROM test_questions WHERE test_key = %s"
            result = user_op.fetch_one(query, (test_key,))
            return float(result['total_marks']) if result and result['total_marks'] is not None else 0.0
        except Exception as e:
            logger.exception(f"Error fetching total marks for test_key: {test_key}")
            return 0.0

    def _calculate_width_percentage(self, value, max_value):
        if max_value is None or max_value == 0 or value is None:
            return 0.0
        return min(100, (float(value) / float(max_value)) * 100)

    def get_topper_list(self, test_key, limit=10):
        try:
            query = """
                WITH RankedResults AS (
                    SELECT
                        email,
                        username,
                        net_score,
                        total_time_taken_seconds,
                        accuracy,
                        percentage,
                        attempted_questions_count,
                        RANK() OVER (PARTITION BY test_key ORDER BY net_score DESC, total_time_taken_seconds ASC) as ranker
                    FROM test_result
                    WHERE test_key = %s
                )
                SELECT *
                FROM RankedResults
                ORDER BY ranker ASC
                LIMIT %s;
            """
            return user_op.fetch_all(query, (test_key, limit))
        except Exception as e:
            logger.exception(f"Error fetching topper list for test_key: {test_key}")
            return []

    def get_average_and_topper_performance(self, test_key):
        try:
            query_avg = "SELECT AVG(accuracy) as avg_accuracy, AVG(total_time_taken_seconds) as avg_time FROM test_result WHERE test_key = %s"
            avg_data = user_op.fetch_one(query_avg, (test_key,))
            query_topper = "SELECT accuracy, total_time_taken_seconds FROM test_result WHERE test_key = %s ORDER BY net_score DESC, total_time_taken_seconds ASC LIMIT 1"
            topper_data = user_op.fetch_one(query_topper, (test_key,))
            
            return {
                "average_accuracy": float(avg_data['avg_accuracy']) if avg_data and avg_data.get('avg_accuracy') is not None else 0.0,
                "average_time": float(avg_data['avg_time']) if avg_data and avg_data.get('avg_time') is not None else 0.0,
                "topper_accuracy": float(topper_data['accuracy']) if topper_data and topper_data.get('accuracy') is not None else 0.0,
                "topper_time": float(topper_data['total_time_taken_seconds']) if topper_data and topper_data.get('total_time_taken_seconds') is not None else 0.0,
            }
        except Exception as e:
            logger.exception(f"Error fetching average and topper performance for test_key: {test_key}")
            return {"average_accuracy": 0.0, "average_time": 0.0, "topper_accuracy": 0.0, "topper_time": 0.0}

    def get_test_summary_details(self, test_key, email):
        try:
            overall_summary = user_op.fetch_one("""
                SELECT tr.*, td.subject_title, td.subject_subtitle, td.total_questions AS test_total_questions
                FROM test_result tr
                JOIN test_description td ON tr.test_key = td.test_key
                WHERE tr.test_key = %s AND tr.email = %s ORDER BY tr.attempt_number DESC LIMIT 1
            """, (test_key, email))

            if not overall_summary:
                return None

            overall_summary['total_marks'] = self._get_total_marks_for_test(test_key)
            overall_summary['ranker'] = overall_summary.get('submission_ranker', 'N/A')
            overall_summary['total_participants'] = user_op.fetch_one("SELECT COUNT(id) as count FROM test_result WHERE test_key = %s", (test_key,)).get('count', 0)

            comparison_data = self.get_average_and_topper_performance(test_key)

            max_time = max(overall_summary.get('total_time_taken_seconds', 0), comparison_data['average_time'], comparison_data['topper_time'])
            if max_time == 0: max_time = 1 

            overall_summary['accuracy_width_percentage'] = self._calculate_width_percentage(overall_summary.get('accuracy'), 100)
            overall_summary['time_width_percentage'] = self._calculate_width_percentage(overall_summary.get('total_time_taken_seconds'), max_time)
            
            comparison_data['average_accuracy_width_percentage'] = self._calculate_width_percentage(comparison_data.get('average_accuracy'), 100)
            comparison_data['topper_accuracy_width_percentage'] = self._calculate_width_percentage(comparison_data.get('topper_accuracy'), 100)
            comparison_data['average_time_width_percentage'] = self._calculate_width_percentage(comparison_data.get('average_time'), max_time)
            comparison_data['topper_time_width_percentage'] = self._calculate_width_percentage(comparison_data.get('topper_time'), max_time)
            comparison_data['max_time_for_progress'] = max_time

            attempt_details = user_op.fetch_all("""
                SELECT tad.*, tq.id as question_id, tq.section_name, tq.question_number, tq.question_type,
                       tq.question_text, tq.option_a, tq.option_b, tq.option_c, tq.option_d,
                       tq.correct_option, tq.correct_marks, tq.negative_marks, tq.answer_text, tq.answer_link
                FROM test_attempt_details tad
                JOIN test_questions tq ON tad.question_id = tq.id
                WHERE tad.test_key = %s AND tad.email = %s AND tad.attempt_number = %s
                ORDER BY tq.section_id, tq.question_number
            """, (test_key, email, overall_summary.get('attempt_number')))
            
            toppers = self.get_topper_list(test_key)
            
            counts = {
                "all": overall_summary.get('test_total_questions', 0),
                "correct": overall_summary.get('correctly_answered_questions_count', 0),
                "incorrect": overall_summary.get('incorrectly_answered_questions_count', 0),
                "skipped": overall_summary.get('unattempted_questions_count', 0)
            }

            return {
                "overall": overall_summary,
                "details": attempt_details,
                "toppers": toppers,
                "counts": counts,
                "comparison": comparison_data
            }
        except Exception as e:
            logger.exception(f"Error fetching test summary for test_key: {test_key}, email: {email}")
            return None

    def update_email_for_guest_data(self, guest_email, actual_email, actual_username):
      try:
        db_connection = user_op.connection()
        cursor = db_connection.cursor(buffered=True)
        db_connection.start_transaction()
        
        query_result = "UPDATE test_result SET email = %s, username = %s WHERE email = %s"
        cursor.execute(query_result, (actual_email, actual_username, guest_email))
        
        query_details = "UPDATE test_attempt_details SET email = %s WHERE email = %s"
        cursor.execute(query_details, (actual_email, guest_email))
        
        query_feedback = "UPDATE test_feedback SET email = %s WHERE email = %s"
        cursor.execute(query_feedback, (actual_email, guest_email))
        
        db_connection.commit()
        logger.info(f"RESULT_HANDLER_DB: Updated email and username for guest data from {guest_email} to {actual_email}")
      except Exception as e:
        db_connection.rollback()
        logger.exception(f"Failed to update email and username in result tables for guest {guest_email}")
      finally:
        if db_connection:
            db_connection.close()
