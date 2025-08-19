# Import gspread (Google Sheets library) and authentication tools
import gspread
import json
import time
import os
import re
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
        email = res['Email (MUST BE zID@ad.unsw.edu.au)']
        zId = res['zID (z0000000)']
        
        if not re.fullmatch(r'[zZ]\d{7}', zId):
            continue
        
        # Check email matches student ID and domain
        expected_domain = "@ad.unsw.edu.au"
        if not (email.startswith(zId) and email.endswith(expected_domain)):
            continue
        validated.append(res)
    
    ###! WE SHOULD COLLECT SUCCESS AND FAIL DATA
    ###! SO WE CAN FOLLOW UP PEOPLE WHO SUBMITTED INVALID INFO
    
    return validated

################################
#                              #
#          BIG PULSE           #
#                              #
################################
def submit(responses):
    # for res in responses:
        # payload = {
        #     'email': res['Email (MUST BE zID@ad.unsw.edu.au)'],
        #     'zid': res['zID (z0000000)'],
        #     'first_name': res['First Name'],
        #     'last_name': res['Last Name'],
        #     'campus': 'UNSW'
        # }
    payload = {
        'email': 'z5488642@ad.unsw.edu.au',
        'zid': 'z5488642',
        'first_name': 'Seb',
        'last_name': 'K',
        'campus': 'UNSW'
    }
    submit_vote(payload)

def submit_vote(payload):
    options = Options()
    options.add_argument("--headless")  # run in background
    options.add_argument("--disable-gpu")  # recommended for headless
    
    driver = webdriver.Chrome(service=DRIVER_SERVICE, options=options)
    driver.get("https://www.bigpulse.com/p83591/register")
    time.sleep(5)
    
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
    
    time.sleep(5)
    
    continue_btn = driver.find_element(By.NAME, "act_confirm")
    continue_btn.click()
    
    # validate it was successful
    main_element = driver.find_element(By.TAG_NAME, "main")
    worked_text = "Thank you for registering to vote in the Students for Palestine Referendum ballot."
    if worked_text not in main_element.text:
        #! FAILED
        pass
    
    driver.quit()
    

################################
#                              #
#             MAIN             #
#                              #
################################
if __name__ == "__main__":
    new_responses = load_responses()
    new_responses = validate(new_responses)
    
    print("All new form responses:")
    for r in new_responses:
        print(r)



''' Google Form Info
1. Data
    - Email
    - First Name
    - Last Name
    - Campus
    - zID
2. Submitted Message
    - YOU'LL RECEIVE AN EMAIL SOON (title, so it's clear this was not the vote)
    - You can only vote once
    - You will receive a voting link in your email
    - contact 0430 460 872 if you do not receive your link within 5 minutes
'''
