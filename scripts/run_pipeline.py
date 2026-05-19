import os
import sys
import requests
import csv
import urllib.parse
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth

# Fix module path so Python can find /pipeline
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pipeline.validator import is_valid_lead


# -------------------------
# Load environment variables
# -------------------------
load_dotenv()

SF_CLIENT_ID = os.getenv("SF_CLIENT_ID")
SF_CLIENT_SECRET = os.getenv("SF_CLIENT_SECRET")
SF_LOGIN_URL = os.getenv("SF_LOGIN_URL")

JIRA_DOMAIN = os.getenv("JIRA_DOMAIN")
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
JIRA_PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY")


# -------------------------
# Salesforce Authentication
# -------------------------
def get_salesforce_session():

    payload = {
        "grant_type": "client_credentials",
        "client_id": SF_CLIENT_ID,
        "client_secret": SF_CLIENT_SECRET
    }

    response = requests.post(SF_LOGIN_URL, data=payload)
    data = response.json()

    if "access_token" not in data:
        print("❌ Salesforce login failed")
        exit()

    headers = {
        "Authorization": f"Bearer {data['access_token']}",
        "Content-Type": "application/json"
    }

    return headers, data["instance_url"]


# -------------------------
# Create Jira Ticket
# -------------------------
def create_jira_ticket(summary, description):

    url = f"{JIRA_DOMAIN}/rest/api/3/issue"
    auth = HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)

    payload = {
        "fields": {
            "project": {"key": JIRA_PROJECT_KEY},
            "summary": summary,
            "description": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {"type": "text", "text": description}
                        ]
                    }
                ]
            },
            "issuetype": {"name": "Task"}
        }
    }

    response = requests.post(url, json=payload, auth=auth)

    if response.status_code == 201:
        print(f"🐞 Jira Ticket Created: {summary}")
    else:
        print(f"❌ Jira Error: {response.text}")


# -------------------------
# Load Leads from CSV
# -------------------------
def load_leads_from_csv(file_path):

    leads = []

    with open(file_path, newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)

        for row in reader:
            leads.append(row)

    return leads


# -------------------------
# Save invalid leads locally
# -------------------------
def save_invalid_leads(invalid_leads):

    if not invalid_leads:
        return

    file_path = "data/invalid_leads.csv"

    existing_emails = set()

    try:
        with open(file_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                existing_emails.add(row["Email"])
    except FileNotFoundError:
        pass

    with open(file_path, "a", newline="", encoding="utf-8") as f:

        fieldnames = ["FirstName", "LastName", "Company", "Email", "Error"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)

        if f.tell() == 0:
            writer.writeheader()

        for lead in invalid_leads:
            if lead["Email"] not in existing_emails:
                writer.writerow(lead)


# -------------------------
# Salesforce Upsert Logic
# -------------------------
def upsert_lead(lead, headers, instance_url):

    query = f"SELECT Id FROM Lead WHERE Email = '{lead['Email']}'"
    encoded_query = urllib.parse.quote(query)

    query_url = f"{instance_url}/services/data/v59.0/query?q={encoded_query}"

    result = requests.get(query_url, headers=headers).json()

    # Update existing lead
    if result.get("totalSize", 0) > 0:

        lead_id = result["records"][0]["Id"]

        url = f"{instance_url}/services/data/v59.0/sobjects/Lead/{lead_id}"

        res = requests.patch(url, headers=headers, json=lead)

        if res.status_code == 204:
            print(f"🔄 Lead Updated: {lead['Email']}")
        else:
            print(f"❌ Update error: {res.text}")

    else:

        url = f"{instance_url}/services/data/v59.0/sobjects/Lead/"

        res = requests.post(url, headers=headers, json=lead)

        if res.status_code == 201:

            lead_id = res.json()["id"]
            print(f"✅ Lead Created: {lead['Email']} ({lead_id})")

        else:
            print(f"❌ Creation error: {res.text}")


# -------------------------
# Main Pipeline
# -------------------------
def run_pipeline():

    print("🚀 Starting Data Integrity Pipeline")

    headers, instance_url = get_salesforce_session()

    leads = load_leads_from_csv("data/incoming_leads.csv")

    invalid_leads = []

    for lead in leads:

        valid, message = is_valid_lead(lead)

        if not valid:

            print(f"⚠️ Validation Failed: {lead.get('Email')} - {message}")

            lead_copy = lead.copy()
            lead_copy["Error"] = message

            invalid_leads.append(lead_copy)

        else:
            upsert_lead(lead, headers, instance_url)

    # Save invalid leads locally
    save_invalid_leads(invalid_leads)

    # Create ONE Jira ticket for the batch
    if invalid_leads:

        description_lines = ["Invalid Leads Detected:\n"]

        for lead in invalid_leads:
            description_lines.append(
                f"{lead['Email']} | {lead['FirstName']} {lead['LastName']} | {lead['Error']}"
            )

        create_jira_ticket(
            summary="Lead Validation Failed - Batch Report",
            description="\n".join(description_lines)
        )


# -------------------------
# Execute pipeline
# -------------------------
if __name__ == "__main__":
    run_pipeline()