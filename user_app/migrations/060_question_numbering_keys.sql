ALTER TABLE test_questions
    ADD UNIQUE KEY uq_tq_section_number (test_description_id, section_id, question_number);

ALTER TABLE comm_questions
    ADD UNIQUE KEY uq_cq_section_number (test_key, section_name, question_number);
