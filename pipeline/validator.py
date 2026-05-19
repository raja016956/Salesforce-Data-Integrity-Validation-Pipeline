import re

def is_valid_lead(lead):

    email = (lead.get("Email") or "").strip()
    first = (lead.get("FirstName") or "").strip()
    last = (lead.get("LastName") or "").strip()
    company = (lead.get("Company") or "").strip()

    # Required fields
    if not email or not first or not last or not company:
        return False, "Missing required fields"

    # Email validation
    email_pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    if not re.match(email_pattern, email.lower()):
        return False, "Invalid Email Format"

    # Name should not contain numbers
    if any(char.isdigit() for char in first + last):
        return False, "Name contains numbers"

    # Name length check
    if len(first) < 2 or len(last) < 2:
        return False, "Name too short"

    return True, "Valid"