CREATE TABLE IF NOT EXISTS auth (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    password VARCHAR(255) DEFAULT NULL,
    oauth_id VARCHAR(255) DEFAULT NULL,
    auth_type ENUM('manual', 'google', 'both') NOT NULL DEFAULT 'manual',
    is_verified BOOLEAN DEFAULT 0,
    cookie_consent JSON DEFAULT NULL,
    last_active DATETIME DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_auth_email (email),
    INDEX idx_auth_username (username),
    INDEX idx_auth_type (auth_type),
    INDEX idx_auth_created_at (created_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS course_groups (
    group_name  VARCHAR(40) NOT NULL PRIMARY KEY,
    label       VARCHAR(80) NOT NULL,
    position    INT DEFAULT 0,
    is_active   TINYINT(1) DEFAULT 1
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS course_group_codes (
    group_name  VARCHAR(40) NOT NULL,
    code        VARCHAR(20) NOT NULL,
    label       VARCHAR(80) NULL,
    position    INT DEFAULT 0,
    PRIMARY KEY (group_name, code),
    UNIQUE KEY uq_code (code),
    FOREIGN KEY (group_name) REFERENCES course_groups(group_name) ON UPDATE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS content_sections (
    section_key  VARCHAR(40) NOT NULL PRIMARY KEY,
    label        VARCHAR(80) NOT NULL,
    help_text    VARCHAR(255) NULL,
    portal       VARCHAR(30) NULL,
    editor       VARCHAR(30) NULL,
    is_available TINYINT(1) DEFAULT 1,
    position     INT DEFAULT 0
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS course_group_sections (
    group_name  VARCHAR(40) NOT NULL,
    section_key VARCHAR(40) NOT NULL,
    position    INT DEFAULT 0,
    PRIMARY KEY (group_name, section_key),
    FOREIGN KEY (group_name)  REFERENCES course_groups(group_name)     ON UPDATE CASCADE ON DELETE CASCADE,
    FOREIGN KEY (section_key) REFERENCES content_sections(section_key) ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS courses (
    id INT AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(40) NOT NULL,
    subgroup VARCHAR(100) DEFAULT NULL,
    description TEXT,
    guest_access_code VARCHAR(100) DEFAULT NULL UNIQUE,
    INDEX idx_courses_name (name)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS course_content (
    id INT AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(100) NOT NULL,
    name VARCHAR(100),
    stream VARCHAR(255),
    section VARCHAR(40) NOT NULL,
    title VARCHAR(255) NOT NULL,
    subtitle VARCHAR(255),
    label ENUM('Free', 'Paid') NOT NULL,
    price DECIMAL(10,2) DEFAULT 0.00,
    details TEXT,
    status VARCHAR(20) DEFAULT 'active',
    image_url TEXT,
    section_id VARCHAR(100) NOT NULL UNIQUE,
    preview_url TEXT DEFAULT NULL,
    validity_expires_at DATETIME DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_cc_code (code),
    INDEX idx_cc_label (label),
    INDEX idx_cc_status (status),
    INDEX idx_cc_section (section),
    INDEX idx_cc_created_at (created_at),
    INDEX idx_cc_validity (validity_expires_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS enrollment (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    name VARCHAR(100) NOT NULL,
    code VARCHAR(100) NOT NULL,
    unique_code TEXT NOT NULL,
    payment_id VARCHAR(100) DEFAULT NULL,
    enrollment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unique_enrollment (email, code),
    INDEX idx_enroll_email (email),
    INDEX idx_enroll_payment_id (payment_id),
    CONSTRAINT fk_enrollment_auth FOREIGN KEY (email) REFERENCES auth(email) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS enrollment_payment (
    id INT AUTO_INCREMENT PRIMARY KEY,
    payment_id VARCHAR(100) NOT NULL UNIQUE,
    razorpay_order_id VARCHAR(100) DEFAULT NULL,
    enrollment_id INT NOT NULL,
    user_email VARCHAR(255) NOT NULL,
    course_code VARCHAR(100) NOT NULL,
    amount_paid DECIMAL(10,2) NOT NULL,
    currency VARCHAR(10) NOT NULL DEFAULT 'INR',
    payment_method VARCHAR(50) DEFAULT NULL,
    payment_status VARCHAR(50) NOT NULL DEFAULT 'Pending',
    transaction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_ep_user_email (user_email),
    INDEX idx_ep_course (course_code),
    INDEX idx_ep_payment_status (payment_status),
    CONSTRAINT fk_ep_enrollment FOREIGN KEY (enrollment_id) REFERENCES enrollment(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS coupone (
    coupon_id INT AUTO_INCREMENT PRIMARY KEY,
    coupon_code VARCHAR(50) NOT NULL,
    discount DECIMAL(5,2) NOT NULL,
    min_purchase DECIMAL(10,2) NOT NULL,
    uses_count INT DEFAULT 0,
    status BOOLEAN DEFAULT TRUE,
    expiry_date DATE,
    valid_until DATE,
    email VARCHAR(255),
    UNIQUE INDEX idx_coupon_code (coupon_code),
    INDEX idx_coupon_email (email),
    INDEX idx_coupon_status (status),
    INDEX idx_coupon_expiry (expiry_date),
    INDEX idx_coupon_valid_until (valid_until),
    CONSTRAINT fk_coupon_auth FOREIGN KEY (email) REFERENCES auth(email) ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS purchase (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255) DEFAULT NULL,
    username VARCHAR(255) DEFAULT NULL,
    phone VARCHAR(20) DEFAULT NULL,
    course_code VARCHAR(100) NOT NULL,
    section_id VARCHAR(100) DEFAULT NULL,
    section VARCHAR(255) DEFAULT NULL,
    title VARCHAR(255) NOT NULL,
    subtitle VARCHAR(255) DEFAULT NULL,
    price DECIMAL(10,2) NOT NULL,
    original_price DECIMAL(10,2) NOT NULL,
    discount_percent DECIMAL(5,2) DEFAULT 0.00,
    final_price DECIMAL(10,2) NOT NULL,
    payment_id VARCHAR(255) NOT NULL,
    payment_mode VARCHAR(50) DEFAULT NULL,
    payment_date DATETIME NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'Pending',
    purchase_code VARCHAR(50) NOT NULL,
    INDEX idx_purchase_email (email),
    INDEX idx_purchase_payment_id (payment_id),
    INDEX idx_purchase_course_code (course_code),
    INDEX idx_purchase_code (purchase_code),
    CONSTRAINT fk_purchase_auth FOREIGN KEY (email) REFERENCES auth(email) ON DELETE SET NULL,
    CONSTRAINT fk_purchase_content FOREIGN KEY (section_id) REFERENCES course_content(section_id) ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS notes_content (
    id INT AUTO_INCREMENT PRIMARY KEY,
    test_id VARCHAR(100),
    code VARCHAR(100),
    type ENUM('notes', 'sub_notes', 'books', 'practice_questions', 'pyq', 'news') NOT NULL,
    heading TEXT,
    sub_heading TEXT,
    title TEXT,
    sub_title TEXT,
    file_path TEXT,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_notes_test_id (test_id),
    CONSTRAINT fk_notes_content FOREIGN KEY (test_id) REFERENCES course_content(section_id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS practice_questions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(100) NOT NULL,
    section ENUM('Topic-wise', 'Subject-wise', 'Year-wise') NOT NULL,
    title VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_pq_code (code)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS questions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    paper_code VARCHAR(255) NOT NULL,
    subject VARCHAR(255) NOT NULL,
    question_id INT NOT NULL,
    question_type ENUM('MCQ', 'MSQ', 'NAT') NOT NULL,
    topic VARCHAR(255),
    question_text TEXT,
    option_a TEXT,
    option_b TEXT,
    option_c TEXT,
    option_d TEXT,
    correct_option VARCHAR(255),
    answer_text TEXT,
    year INT,
    paper_set VARCHAR(255),
    explanation_link TEXT,
    question_image VARCHAR(255),
    option_regions JSON,
    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY idx_paper_subject_question (paper_code, subject, question_id),
    INDEX idx_q_topic (topic),
    INDEX idx_q_type (question_type),
    INDEX idx_q_year (year)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS guest_codes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(100) NOT NULL,
    unique_code TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_guest_code (code)
) ENGINE=InnoDB;

-- `code`, `show_calculator` and `access_label` were added to the live database
-- over time but never here, so a database built from this file was missing
-- columns the application writes to: adding a test description failed with
-- "Unknown column 'code'", and migration 007 could not copy the rows.
CREATE TABLE IF NOT EXISTS test_description (
    id INT AUTO_INCREMENT PRIMARY KEY,
    test_id VARCHAR(100) NOT NULL,
    code VARCHAR(100) DEFAULT NULL,
    test_key VARCHAR(100) NOT NULL UNIQUE,
    subject_title VARCHAR(255) NOT NULL,
    subject_subtitle VARCHAR(255) NOT NULL,
    total_questions INT NOT NULL,
    total_marks FLOAT NOT NULL,
    total_duration_minutes INT NOT NULL,
    show_calculator TINYINT(1) NOT NULL DEFAULT 0,
    access_label VARCHAR(20) DEFAULT 'inherit',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_td_test_id (test_id),
    INDEX idx_td_code (code),
    CONSTRAINT fk_test_content FOREIGN KEY (test_id) REFERENCES course_content(section_id) ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS test_questions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    test_id VARCHAR(100),
    test_key VARCHAR(100) NOT NULL,
    test_description_id INT,
    section_id VARCHAR(10),
    section_name VARCHAR(100),
    question_number INT,
    question_type VARCHAR(10),
    question_text TEXT,
    option_a TEXT,
    option_b TEXT,
    option_c TEXT,
    option_d TEXT,
    correct_option VARCHAR(10),
    correct_marks FLOAT,
    negative_marks FLOAT,
    question_level VARCHAR(50),
    answer_text TEXT,
    answer_link TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_tq_test_key (test_key),
    CONSTRAINT fk_test_question_desc FOREIGN KEY (test_key) REFERENCES test_description(test_key) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS user_test_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    test_id VARCHAR(100) NOT NULL,
    test_key VARCHAR(100) NOT NULL,
    username VARCHAR(100),
    start_time DATETIME,
    last_heartbeat DATETIME DEFAULT NULL,
    end_time DATETIME,
    status VARCHAR(50),
    device_info TEXT,
    attempt_number INT,
    is_checkbox_checked TINYINT(1) DEFAULT 0,
    ready_to_begin TINYINT(1) DEFAULT 0,
    accepted_at DATETIME DEFAULT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_utl_email (email),
    INDEX idx_utl_test_key (test_key),
    CONSTRAINT fk_user_log_desc FOREIGN KEY (test_key) REFERENCES test_description(test_key) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS test_result (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255),
    username VARCHAR(100),
    test_id VARCHAR(100),
    test_key VARCHAR(100) NOT NULL,
    test_code VARCHAR(50),
    attempted_questions_count INT,
    unattempted_questions_count INT,
    correctly_answered_questions_count INT,
    incorrectly_answered_questions_count INT,
    marks_for_correct_answers FLOAT,
    penalty_for_incorrect_answers FLOAT,
    net_score FLOAT,
    accuracy FLOAT,
    percentage FLOAT,
    submission_ranker INT,
    total_time_taken_seconds INT,
    attempt_number INT DEFAULT 1,
    submission_timestamp DATETIME,
    INDEX idx_tr_email (email),
    INDEX idx_tr_test_key (test_key),
    CONSTRAINT fk_test_result_desc FOREIGN KEY (test_key) REFERENCES test_description(test_key) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS test_attempt_details (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255),
    test_id VARCHAR(100),
    test_key VARCHAR(100) NOT NULL,
    question_id INT,
    user_selected_option VARCHAR(10),
    user_written_answer TEXT,
    is_correct BOOLEAN,
    marks_awarded FLOAT,
    status_of_attempt VARCHAR(50),
    time_spent_on_question_seconds INT,
    attempt_number INT DEFAULT 1,
    INDEX idx_tad_email (email),
    INDEX idx_tad_test_key (test_key),
    INDEX idx_tad_question (question_id),
    CONSTRAINT fk_attempt_desc FOREIGN KEY (test_key) REFERENCES test_description(test_key) ON DELETE CASCADE,
    CONSTRAINT fk_attempt_question FOREIGN KEY (question_id) REFERENCES test_questions(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS test_feedback (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    test_id VARCHAR(100) NOT NULL,
    test_key VARCHAR(100) NOT NULL,
    feedback_software VARCHAR(50),
    feedback_content VARCHAR(255),
    feedback_speed VARCHAR(50),
    suggestions TEXT,
    submission_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_tf_email (email),
    INDEX idx_tf_test_key (test_key),
    CONSTRAINT fk_feedback_desc FOREIGN KEY (test_key) REFERENCES test_description(test_key) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS assessment_rounds (
    id INT AUTO_INCREMENT PRIMARY KEY,
    round_name VARCHAR(50),
    round_type ENUM('COMM','CODING','APTITUDE','APTITUDE_CODING') NOT NULL DEFAULT 'COMM',
    round_description TEXT,
    is_active TINYINT DEFAULT 1
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS comm_description (
    id INT AUTO_INCREMENT PRIMARY KEY,
    test_id VARCHAR(100) NOT NULL,
    code VARCHAR(50),
    test_key VARCHAR(100) NOT NULL UNIQUE,
    subject_title VARCHAR(255) NOT NULL,
    subject_subtitle VARCHAR(255) NOT NULL,
    total_questions INT NOT NULL,
    total_marks FLOAT NOT NULL,
    total_duration_minutes INT NOT NULL,
    round_id INT NULL,
    requires_seb TINYINT DEFAULT 0,
    difficulty_level VARCHAR(20) DEFAULT 'Medium',
    show_calculator TINYINT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_cd_test_id (test_id),
    CONSTRAINT fk_cd_round FOREIGN KEY (round_id) REFERENCES assessment_rounds(id) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=1000000;

CREATE TABLE IF NOT EXISTS comm_sections (
    id INT AUTO_INCREMENT PRIMARY KEY,
    test_key VARCHAR(100) NOT NULL,
    section_id VARCHAR(50),
    section_name VARCHAR(50),
    section_title VARCHAR(100),
    section_instruction TEXT,
    section_duration_seconds INT,
    section_order INT,
    INDEX idx_cs_test_key (test_key),
    CONSTRAINT fk_cs_desc FOREIGN KEY (test_key) REFERENCES comm_description(test_key) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS comm_questions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    test_id VARCHAR(100),
    test_key VARCHAR(100) NOT NULL,
    test_description_id INT,
    section_id VARCHAR(50),
    section_name VARCHAR(100),
    question_number INT,
    question_type ENUM('MCQ','SPEAK','THINK_SPEAK','WRITING','COMPREHENSION','LISTEN_SPEAK','FILL_BLANK') NOT NULL DEFAULT 'MCQ',
    question_text TEXT,
    option_a TEXT,
    option_b TEXT,
    option_c TEXT,
    option_d TEXT,
    correct_option VARCHAR(10),
    correct_marks FLOAT,
    negative_marks FLOAT,
    question_level VARCHAR(50),
    answer_text TEXT,
    answer_link TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    instruction_text TEXT,
    media_url VARCHAR(255),
    options_title VARCHAR(100),
    recording_time_seconds INT DEFAULT 0,
    thinking_time_seconds INT DEFAULT 0,
    word_limit INT DEFAULT 0,
    sub_questions JSON,
    INDEX idx_cq_test_key (test_key),
    CONSTRAINT fk_comm_question_desc FOREIGN KEY (test_key) REFERENCES comm_description(test_key) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=1000000;

CREATE TABLE IF NOT EXISTS comm_result (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255),
    username VARCHAR(100),
    test_id VARCHAR(100),
    test_key VARCHAR(100) NOT NULL,
    test_code VARCHAR(50),
    attempted_questions_count INT,
    unattempted_questions_count INT,
    correctly_answered_questions_count INT,
    incorrectly_answered_questions_count INT,
    marks_for_correct_answers FLOAT,
    penalty_for_incorrect_answers FLOAT,
    net_score FLOAT,
    accuracy FLOAT,
    percentage FLOAT,
    submission_ranker INT,
    total_time_taken_seconds INT,
    attempt_number INT DEFAULT 1,
    submission_timestamp DATETIME,
    INDEX idx_cr_email (email),
    INDEX idx_cr_test_key (test_key)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS comm_feedback (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    test_id VARCHAR(100) NOT NULL,
    test_key VARCHAR(100) NOT NULL,
    feedback_software VARCHAR(50),
    feedback_content VARCHAR(255),
    feedback_speed VARCHAR(50),
    suggestions TEXT,
    submission_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_cf_email (email),
    INDEX idx_cf_test_key (test_key)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS comm_user_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(100),
    test_key VARCHAR(50),
    course_code VARCHAR(50),
    unique_code VARCHAR(50),
    status VARCHAR(20) DEFAULT 'started',
    session_token VARCHAR(64),
    token_expiry DATETIME,
    audio_check_passed TINYINT DEFAULT 0,
    start_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    end_time DATETIME,
    UNIQUE KEY unique_session (email, test_key)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS comm_attempt_details (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(100),
    test_key VARCHAR(50),
    question_id INT,
    section_name VARCHAR(50),
    selected_option CHAR(1),
    text_response TEXT,
    audio_response_path VARCHAR(255),
    transcription_text TEXT,
    accuracy_score FLOAT DEFAULT 0,
    recording_duration FLOAT DEFAULT 0,
    is_submitted TINYINT DEFAULT 0,
    is_marked_for_review TINYINT DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unique_attempt (email, test_key, question_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS comm_proctoring_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(100),
    test_key VARCHAR(50),
    snapshot_path VARCHAR(255),
    log_type VARCHAR(50),
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;
