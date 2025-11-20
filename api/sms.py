# api/sms.py
import os
import logging
import re
import html
from typing import List, Optional, Tuple
from flask import Flask, request
import requests

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

MONDAY_API_URL = "https://api.monday.com/v2"
MONDAY_ITEMS_PAGE_LIMIT = 500  # adjust if board has more than 500 rows


def send_notification_to_monday(user_id: int, target_id: str, target_type: str, text: str) -> bool:
    """Send a notification to a Monday user (fallback when no contact item)."""
    query = """
            mutation ($user_id: ID!, $target_id: ID!, $target_type: NotificationTargetType!, $text: String!) {
            create_notification(user_id: $user_id, target_id: $target_id, target_type: $target_type, text: $text) {
                id
            }
            }
            """
    variables = {
        "user_id": str(user_id),
        "target_id": str(target_id),
        "target_type": target_type,
        "text": text,
    }
    monday_api_key = os.environ.get("MONDAY_API_KEY")
    headers = {"Authorization": monday_api_key, "Content-Type": "application/json"}

    try:
        logging.info("Posting fallback notification with variables: %s", variables)
        resp = requests.post(
            MONDAY_API_URL,
            json={"query": query, "variables": variables},
            headers=headers,
            timeout=10,
        )
        data = resp.json()
        if "errors" in data:
            logging.error("Monday notification failed: %s", data["errors"])
            return False
        logging.info("Notification sent to user %s", user_id)
        return True
    except Exception as exc:
        logging.exception("Failed to send Monday notification: %s", exc)
        return False


def get_monday_user_ids() -> List[int]:
    """Read MONDAY_USER_IDS (comma-separated) or fallback to MONDAY_USER_ID."""
    ids_value = os.environ.get("MONDAY_USER_IDS")
    user_ids: List[int] = []

    if ids_value:
        for raw in ids_value.split(","):
            candidate = raw.strip()
            if not candidate:
                continue
            try:
                user_ids.append(int(candidate))
            except ValueError:
                logging.error("Invalid MONDAY_USER_IDS entry: %s", candidate)

    if user_ids:
        return user_ids

    single_user_id = os.environ.get("MONDAY_USER_ID")
    if single_user_id:
        try:
            return [int(single_user_id)]
        except ValueError:
            logging.error("MONDAY_USER_ID invalid: %s", single_user_id)

    return []


def normalize_phone_number(number: Optional[str]) -> str:
    """Strip to digits and normalize leading country code for comparisons."""
    if not number:
        return ""
    digits = re.sub(r"\D+", "", number)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits


def lookup_contact_by_phone(phone_number: str) -> Optional[Tuple[str, str]]:
    """Fetch the Monday contact name and item ID matching the provided phone number."""
    normalized = normalize_phone_number(phone_number)
    if not normalized:
        logging.info("Skipping contact lookup: phone number missing/invalid")
        return None

    board_id = os.environ.get("MONDAY_CONTACT_BOARD_ID")
    phone_column_id = os.environ.get("MONDAY_PHONE_COLUMN_ID")
    if not board_id or not phone_column_id:
        logging.info(
            "Skipping contact lookup: MONDAY_CONTACT_BOARD_ID (%s) or MONDAY_PHONE_COLUMN_ID (%s) missing",
            bool(board_id),
            bool(phone_column_id),
        )
        return None

    query = """
            query ($board_id: [ID!], $limit: Int!, $column_ids: [String!]) {
            boards(ids: $board_id) {
                items_page(limit: $limit) {
                items {
                    id
                    name
                    column_values(ids: $column_ids) {
                    id
                    text
                    }
                }
                }
            }
            }
            """
    variables = {
        "board_id": board_id,
        "limit": MONDAY_ITEMS_PAGE_LIMIT,
        "column_ids": [phone_column_id],
    }

    monday_api_key = os.environ.get("MONDAY_API_KEY")
    headers = {"Authorization": monday_api_key, "Content-Type": "application/json"}

    try:
        resp = requests.post(
            MONDAY_API_URL,
            json={"query": query, "variables": variables},
            headers=headers,
            timeout=10,
        )
        data = resp.json()

        if "errors" in data:
            logging.error("Contact lookup failed: %s", data["errors"])
            return None

        boards = data.get("data", {}).get("boards", [])
        for board in boards:
            items_page = board.get("items_page", {})
            for item in items_page.get("items", []):
                col_values = item.get("column_values", [])
                for column in col_values:
                    current = normalize_phone_number(column.get("text"))
                    if current and current == normalized:
                        name = item.get("name")
                        item_id = item.get("id")
                        logging.info(
                            "Matched contact %s (item %s) for phone %s",
                            name,
                            item_id,
                            phone_number,
                        )
                        return name, item_id
    except Exception as exc:
        logging.exception("Contact lookup request failed: %s", exc)

    logging.info("No contact found on board %s for phone %s", board_id, phone_number)
    return None


def create_update_for_item(item_id: str, sender_label: str, message: str) -> Optional[str]:
    """Post an update to the matched contact's item so it shows up in the All Updates inbox."""
    text_html = html.escape(message).replace("\n", "<br/>")
    body = f"<p><strong>New SMS from {html.escape(sender_label)}</strong></p><p>{text_html}</p>"

    query = """
mutation ($item_id: ID!, $body: String!) {
  create_update(item_id: $item_id, body: $body) {
    id
  }
}
"""
    variables = {"item_id": item_id, "body": body}
    monday_api_key = os.environ.get("MONDAY_API_KEY")
    headers = {"Authorization": monday_api_key, "Content-Type": "application/json"}

    try:
        logging.info("Posting update to Monday item %s", item_id)
        response = requests.post(
            MONDAY_API_URL,
            json={"query": query, "variables": variables},
            headers=headers,
            timeout=10,
        )
        data = response.json()
        if "errors" in data:
            logging.error("Failed to create update: %s", data["errors"])
            return None

        update_id = data.get("data", {}).get("create_update", {}).get("id")
        logging.info("Created Monday update %s for item %s", update_id, item_id)
        return update_id
    except Exception as exc:
        logging.exception("Error while creating Monday update: %s", exc)
        return None


@app.route("/sms", methods=["POST"])
def receive_sms():
    """Receive Twilio SMS webhook (form-encoded)."""

    logging.info("MONDAY_USER_ID present at request time: %s", bool(os.environ.get("MONDAY_USER_ID")))
    logging.info("MONDAY_USER_IDS present at request time: %s", bool(os.environ.get("MONDAY_USER_IDS")))
    
    try:
        # Extract from form data (Twilio uses application/x-www-form-urlencoded)
        from_number = request.form.get("From")
        body = request.form.get("Body")
        
        logging.info(f"Received SMS from {from_number}: {body}")

        if not from_number or not body:
            logging.warning("Missing From or Body in webhook")
            return ("", 200)

        contact_match = lookup_contact_by_phone(from_number)
        contact_name = contact_item_id = None
        if contact_match:
            contact_name, contact_item_id = contact_match

        sender_label = f"{contact_name} ({from_number})" if contact_name else from_number

        # Prepare notification
        notification_text = f"New SMS from {sender_label}:\n\n{body}"

        user_ids = get_monday_user_ids()
        if not user_ids:
            logging.error("No valid MONDAY user IDs configured (MONDAY_USER_IDS or MONDAY_USER_ID)")
            return ("", 200)

        if not contact_item_id:
            logging.info(
                "No contact match for %s; ignoring SMS for Monday workflow",
                from_number,
            )
            return ("", 200)

        update_id = create_update_for_item(contact_item_id, sender_label, body)
        if not update_id:
            logging.error("Failed to create update for item %s", contact_item_id)
            return ("", 200)

        for user_id in user_ids:
            logging.info(
                "Sending update-linked notification to user %s for update %s",
                user_id,
                update_id,
            )
            send_notification_to_monday(
                user_id,
                update_id,
                "Post",
                notification_text,
            )

        return ("", 200)

    except Exception as e:
        logging.exception(f"Error in /sms: {e}")
        return ("", 200)


@app.route("/", methods=["GET"])
def health():
    # Temporary debug: log presence (but never the value) of important env vars
    api_present = bool(os.environ.get("MONDAY_API_KEY"))
    user_present = bool(os.environ.get("MONDAY_USER_ID"))
    users_present = bool(os.environ.get("MONDAY_USER_IDS"))
    board_present = bool(os.environ.get("MONDAY_CONTACT_BOARD_ID"))
    phone_column_present = bool(os.environ.get("MONDAY_PHONE_COLUMN_ID"))
    logging.info("MONDAY_API_KEY present at runtime: %s", api_present)
    logging.info("MONDAY_USER_ID present at runtime: %s", user_present)
    logging.info("MONDAY_USER_IDS present at runtime: %s", users_present)
    logging.info("MONDAY_CONTACT_BOARD_ID present at runtime: %s", board_present)
    logging.info("MONDAY_PHONE_COLUMN_ID present at runtime: %s", phone_column_present)
    return ("Twilio -> Monday webhook running", 200)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
