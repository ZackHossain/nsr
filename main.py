# Import gspread (Google Sheets library) and authentication tools
import shutil
import gspread
import json
import time
import os
import re
import logging
import tempfile
from google.oauth2.service_account import Credentials
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

RESPONSES_SHEET = "https://docs.google.com/spreadsheets/d/1HSMegzu1GZuFtxzBuady3-IUlJCNZ7A6tz7Q60tl8wQ/edit?usp=sharing"
TEST_SHEET = "https://docs.google.com/spreadsheets/d/1leXM8H6rX2aeyPzFUqSEWjTv4LTIDqbiBPrvoYD5OTY/edit?usp=sharing"
STATE_FILE = "responses.json"
VOTE_LINK = "https://www.bigpulse.com/p83591/register"
DRIVER_SERVICE = Service("/usr/local/bin/chromedriver")

################################
#                              #
#        LOAD RESPONSES        #
#                              #
################################
def load_responses():
    # Define the API scope
    scope = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

    # Load the credentials.json file
    creds = Credentials.from_service_account_file("credential.json", scopes=scope)
    # Authorize gspread with the loaded credentials
    client = gspread.authorize(creds)

    # Open the spreadsheet linked to the Google Form
    sheet = client.open_by_url(RESPONSES_SHEET).sheet1

    # Fetch all rows (as a list of dictionaries or values)
    responses = sheet.get_all_records()

    # Load existing responses
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            seen = set(json.load(f))  # list of strings
    else:
        seen = set()

    # Find new responses (ones not in 'seen')
    new_responses = []
    for r in responses:
        key = json.dumps(r, sort_keys=True)
        if key not in seen:
            new_responses.append(r)
            seen.add(key)

    # Save updated seen set back to file
    with open(STATE_FILE, "w") as f:
        json.dump(list(seen), f, indent=2)
    
    return new_responses

################################
#                              #
#    VALIDATE NEW RESPONSES    #
#                              #
################################
def validate(responses):
    validated = []
    
    for res in responses:
        email = res['Email (MUST BE zID@ad.unsw.edu.au)'].lower()
        zId = res['zID (z0000000)'].lower()
        
        if not re.fullmatch(r'[zZ]\d{7}', zId):
            save_failed(zId, "Invalid zID")
            continue
        
        # Check email matches student ID and domain
        expected_domain = "@ad.unsw.edu.au"
        if not (email.startswith(zId) and email.endswith(expected_domain)):
            save_failed(zId, "Invalid Email")
            continue
        
        validated.append(res)
    return validated

################################
#                              #
#          BIG PULSE           #
#                              #
################################
def submit(responses):
    # responses.append({
    #     'Email (MUST BE zID@ad.unsw.edu.au)': "z0000003@ad.unsw.edu.au",
    #     "zID (z0000000)": "z0000003",
    #     "First Name": 'z',
    #     "Last Name": 'z'
    # })
    for res in responses:
        payload = {
            'email': res['Email (MUST BE zID@ad.unsw.edu.au)'].lower(),
            'zid': res['zID (z0000000)'].lower(),
            'first_name': res['First Name'],
            'last_name': res['Last Name'],
            'campus': 'UNSW'
        }
        submit_vote(payload)

def submit_vote(payload):
    logging.info(f"Submitting vote for {payload['zid']} ({payload['email']})")
    try:
        options = Options()
        options.add_argument("--headless")  # run in background
        options.add_argument("--disable-gpu")  # recommended for headless
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.binary_location = "/usr/local/bin/chrome/chrome"

        # Use a temporary directory for Chrome user data
        tmp_user_data_dir = tempfile.mkdtemp()
        options.add_argument(f"--user-data-dir={tmp_user_data_dir}")
        
        driver = webdriver.Chrome(service=DRIVER_SERVICE, options=options)
        driver.get("https://www.bigpulse.com/p83591/register")
        time.sleep(2)
        
        email_field = driver.find_element(By.NAME, "email")
        first_name_field = driver.find_element(By.NAME, "firstname")
        last_name_field = driver.find_element(By.NAME, "lastname")
        campus_field = driver.find_element(By.NAME, "orgname")
        zid_field = driver.find_element(By.NAME, "custom1")
        
        email_field.send_keys(payload['email'])
        first_name_field.send_keys(payload['first_name'])
        last_name_field.send_keys(payload['last_name'])
        campus_field.send_keys(payload['campus'])
        zid_field.send_keys(payload['zid'])
        
        submit_btn = driver.find_element(By.XPATH, '//input[@type="submit"]')
        submit_btn.click()
        
        time.sleep(2)
        
        # Checks if we are on the page which says "you have already registered"
        main_element = driver.find_element(By.TAG_NAME, "main")
        already_exists_text = "That email address is already in use"
        if already_exists_text in main_element.text:
            logging.info(f"ALREADY REGISTERED: {payload['zid']} has already registered.")
            driver.quit()
            shutil.rmtree(tmp_user_data_dir)
            return
        
        # If we aren't already registered, confirm the details
        continue_btn = driver.find_element(By.NAME, "act_confirm")
        continue_btn.click()
        
        time.sleep(2)
        main_element = driver.find_element(By.TAG_NAME, "main")
        worked_text = "Thank you for registering to vote in the Students for Palestine Referendum ballot."
        if worked_text in main_element.text:
            save_success(payload)
        else:
            save_failed(payload['zid'], "Failed to register")
            
        driver.quit()
        shutil.rmtree(tmp_user_data_dir)
    except Exception as e:
        logging.exception(f"ERROR: Exception on {payload['zid']}")
        save_failed(payload['zid'], "Exception when registering")
        driver.quit()
        shutil.rmtree(tmp_user_data_dir)

################################
#                              #
#          SAVE DATA           #
#                              #
################################
def save_failed(zid, reason):
    data = {}
    if os.path.exists("failed.json"):
        with open("failed.json", "r") as f:
            data = json.load(f)
    else:
        data = []
    
    data.append(zid)
    with open("failed.json", "w") as f:
        json.dump(data, f, indent=2)
        logging.error(f"FAILED to log {zid}: {reason}")

def save_success(res):
    data = []
    if os.path.exists("succeeded.json"):
        with open("succeeded.json", "r") as f:
            data = json.load(f)
    else:
        data = []
    
    data.append(res)
    with open("succeeded.json", "w") as f:
        json.dump(data, f, indent=2)
        print(json.dumps(res, indent=4))
        logging.info(f"REGISTERED {res['zid']}")

################################
#                              #
#             MAIN             #
#                              #
################################
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(processName)s - %(message)s",
    handlers=[
        logging.FileHandler("submission.log"),  # writes logs to file
        logging.StreamHandler()                 # also prints to console
    ]
)

if __name__ == "__main__":
    new_responses = load_responses()
    valid_responses = validate(new_responses)
    submit(valid_responses)