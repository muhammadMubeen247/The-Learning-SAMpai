from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# password = "a_very_secure_password_that_is_longer_than_72_bytes_" * 3
# password2 = "plipplop"

def hash_password(password: str) -> str:
    # Safely truncate to 72 bytes (bcrypt limit)
    password = password.encode("utf-8")[:72].decode("utf-8", "ignore")
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    plain_password = plain_password.encode("utf-8")[:72].decode("utf-8", "ignore")
    return pwd_context.verify(plain_password, hashed_password)

# print(hash_password(password))
# print(hash_password(password2))
