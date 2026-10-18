import re

_RULES = [
    (1062, r"Duplicate entry '([^']+)'",
     lambda m: f"Duplicate not allowed: a question with '{m.group(1)}' already exists. "
               f"Change the question_id (or delete the old one) and upload again."),
    (1406, r"Data too long for column '([^']+)'",
     lambda m: f"The value in column '{m.group(1)}' is too long for the database. "
               f"Shorten that field and upload again."),
    (1366, r"Incorrect .*? value: '([^']*)' for column '([^']+)'",
     lambda m: f"Column '{m.group(2)}' received an invalid value '{m.group(1)}'. "
               f"Check the allowed values in the template guide."),
    (1264, r"Out of range value for column '([^']+)'",
     lambda m: f"The number in column '{m.group(1)}' is too large or negative. Fix it and upload again."),
    (1048, r"Column '([^']+)' cannot be null",
     lambda m: f"Column '{m.group(1)}' is required but was empty. Fill it in every row."),
    (1452, None,
     lambda m: "This question refers to a test or paper that does not exist. "
               "Create the test description or paper first."),
]


def friendly_db_error(exc):
    errno = getattr(exc, 'errno', None)
    text = str(exc)
    for code, pattern, build in _RULES:
        if errno == code:
            if pattern:
                m = re.search(pattern, text)
                if m:
                    return build(m)
            return build(None)
    if 'Deadlock' in text or errno == 1213:
        return "The database was busy with another save. Nothing was stored - simply upload again."
    if errno in (2003, 2013) or 'Lost connection' in text:
        return "The database connection dropped. Nothing was stored - check the server and upload again."
    return None
