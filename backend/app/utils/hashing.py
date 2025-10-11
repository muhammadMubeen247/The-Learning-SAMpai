from passlib.context import CryptContext
import bcrypt

# Configure CryptContext specifically for bcrypt
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__default_rounds=12,
    bcrypt__truncate_error=False  # This prevents the 72-byte error
)

def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    # Convert to bytes and truncate if necessary
    password_bytes = password.encode('utf-8')[:72]
    # Generate salt and hash
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash"""
    # Convert inputs to bytes and truncate plain password
    plain_bytes = plain_password.encode('utf-8')[:72]
    hash_bytes = hashed_password.encode('utf-8')
    try:
        return bcrypt.checkpw(plain_bytes, hash_bytes)
    except ValueError:
        return False