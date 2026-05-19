import os
import requests
import pandas as pd
import urllib.parse
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth
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
# Salesforce Upsert Logic
# -------------------------
def upsert_lead(lead, headers, instance_url):

    # Validate lead
    valid, message = is_valid_lead(lead)

    if not valid:

        print(f"⚠️ Validation Failed: {message}")

        create_jira_ticket(
            summary=f"Lead Validation Failed - {lead.get('Email')}",
            description=f"""
Lead Validation Error

Name: {lead.get('FirstName')} {lead.get('LastName')}
Company: {lead.get('Company')}
Email: {lead.get('Email')}
Issue: {message}
"""
        )

        return

    # -------------------------
    # Check duplicates
    # -------------------------

    query = f"SELECT Id FROM Lead WHERE Email = '{lead['Email']}'"

    encoded_query = urllib.parse.quote(query)

    query_url = f"{instance_url}/services/data/v59.0/query?q={encoded_query}"

    result = requests.get(query_url, headers=headers).json()

    # -------------------------
    # Update existing lead
    # -------------------------

    if result.get("totalSize", 0) > 0:

        lead_id = result["records"][0]["Id"]

        url = f"{instance_url}/services/data/v59.0/sobjects/Lead/{lead_id}"

        res = requests.patch(url, headers=headers, json=lead)

        if res.status_code == 204:
            print(f"🔄 Lead Updated: {lead['Email']}")

        else:
            print(f"❌ Update error: {res.text}")

    # -------------------------
    # Create new lead
    # -------------------------

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

    # Load incoming leads file
    df = pd.read_csv("data/incoming_leads.csv")

    for _, row in df.iterrows():

        lead = row.to_dict()

        upsert_lead(lead, headers, instance_url)


# -------------------------
# Execute pipeline
# -------------------------
if __name__ == "__main__":

    run_pipeline()