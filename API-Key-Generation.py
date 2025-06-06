import secrets
import string

def generate_api_key(length=32):
    characters = string.ascii_letters + string.digits + "-_."
    return ''.join(secrets.choice(characters) for i in range(length))

api_key = generate_api_key()
print(f"Your new custom API Key: {api_key}")