import bcrypt
import sys

# Check if a password was provided as a command-line argument
if len(sys.argv) < 2:
    print("Usage: py generate_keys.py 'your_password_here'")
    sys.exit(1)

# 1. Get your plain-text password from the command line argument
plain_text_password = sys.argv[1]

# 2. Encode the password into bytes
password_bytes = plain_text_password.encode('utf-8')

# 3. Generate a salt
salt = bcrypt.gensalt()

# 4. Hash the password with the salt
hashed_password_bytes = bcrypt.hashpw(password_bytes, salt)

# 5. Decode the hashed bytes back into a string for the YAML file
hashed_password_string = hashed_password_bytes.decode('utf-8')

print("Your securely hashed password is:")
print(hashed_password_string)