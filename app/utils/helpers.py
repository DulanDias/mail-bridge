from email.utils import parseaddr

def extract_email_metadata(msg):
    """ Extracts name and email from 'From' header """
    name, email = parseaddr(msg["From"])
    return {"name": name, "email": email}
