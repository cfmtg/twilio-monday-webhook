# api/sms.py
import os
import logging
from flask import Flask, request
import requests

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

MONDAY_API_URL = "https://api.monday.com/v2"

def send_notification_to_monday(user_id: int, text: str):
    """Send a notification to a specific Monday.com user."""
    query = """
mutation ($user_id: ID!, $target_id: ID!, $target_type: NotificationTargetType!, $text: String!) {
  create_notification(user_id: $user_id, target_id: $target_id, target_type: $target_type, text: $text) {
    id
  }
}
"""

    variables = {
        "user_id": str(user_id),
        "target_id": str(user_id),  # Monday expects ID!, so coerce to string
        "target_type": "USER",
        "text": text,
    }
    # Read API key at call-time (safer for serverless imports)
    monday_api_key = os.environ.get("MONDAY_API_KEY")
    headers = {"Authorization": monday_api_key, "Content-Type": "application/json"}

    try:
        # Log the outgoing variables (safe: does not include API key)
        logging.info("Posting to Monday API with variables: %s", variables)
        response = requests.post(
            MONDAY_API_URL,
            json={"query": query, "variables": variables},
            headers=headers,
            timeout=10
        )
        response_data = response.json()
        
        if "errors" in response_data:
            logging.error(f"Monday API errors: {response_data['errors']}")
            return False
        
        logging.info(f"Notification sent to user {user_id}")
        return True
    except Exception as e:
        logging.error(f"Failed to send notification: {e}")
        return False


@app.route("/sms", methods=["POST"])
def receive_sms():
    """Receive Twilio SMS webhook (form-encoded)."""

    logging.info("MONDAY_USER_ID at request time: %s", bool(os.environ.get("MONDAY_USER_ID"))) 
    logging.info("MONDAY_USER_ID value at runtime: %r", os.environ.get("MONDAY_USER_ID"))
    
    try:
        # Extract from form data (Twilio uses application/x-www-form-urlencoded)
        from_number = request.form.get("From")
        body = request.form.get("Body")
        
        logging.info(f"Received SMS from {from_number}: {body}")

        if not from_number or not body:
            logging.warning("Missing From or Body in webhook")
            return ("", 200)

        # Prepare notification
        notification_text = f"New SMS from {from_number}:\n\n{body}"

        # Read MONDAY_USER_ID at request time (avoid import-time captures)
        monday_user_id = os.environ.get("MONDAY_USER_ID")
        if not monday_user_id:
            logging.error("MONDAY_USER_ID not set in environment at runtime")
            return ("", 200)

        try:
            user_id = int(monday_user_id)
        except (ValueError, TypeError):
            logging.error(f"MONDAY_USER_ID invalid: {monday_user_id}")
            return ("", 200)

        send_notification_to_monday(user_id, notification_text)
        return ("", 200)

    except Exception as e:
        logging.exception(f"Error in /sms: {e}")
        return ("", 200)


@app.route("/", methods=["GET"])
def health():
    # Temporary debug: log presence (but never the value) of important env vars
    api_present = bool(os.environ.get("MONDAY_API_KEY"))
    user_present = bool(os.environ.get("MONDAY_USER_ID"))
    logging.info("MONDAY_API_KEY present at runtime: %s", api_present)
    logging.info("MONDAY_USER_ID present at runtime: %s", user_present)
    return ("Twilio -> Monday webhook running", 200)


if __name__ == "__main__":
    app.run(debug=True, port=5000)

