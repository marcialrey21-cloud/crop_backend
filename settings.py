import os
from dotenv import load_dotenv
from datetime import timedelta

# Load the environment variables from the .env file
load_dotenv()

INSTALLED_APPS = [
    # ... your other apps ...
    'rest_framework',
    # --- JWT LIFESPAN SETTINGS ---
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=30), # The wristband lasts for 30 days
    'REFRESH_TOKEN_LIFETIME': timedelta(days=90),
}
    'scanner_app', # Assuming you created an app named this
]