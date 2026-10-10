import secrets

ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"


def new_learner_code():
    return "".join(secrets.choice(ALPHABET) for _ in range(6))
