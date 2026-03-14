#!/usr/bin/env python3

import os
import requests
import json
import time
import uuid
import sys

# --- Configuration ---
BASE_URL = os.getenv("BASE_URL")
HEADERS = {
    '__requestverificationtoken': os.getenv("TOKEN"),
    'cookie': os.getenv("COOKIES"),
    'accept': 'application/json',
    'content-type': 'application/json',
}

def generate_page_nonce():
    """Generates a fresh UUID-based PageNonce."""
    return str(uuid.uuid4()).replace('-', '')

def get_org_keys(session):
    """Fetches organization keys and validates the session."""
    print("Validating session and fetching organizations...")
    try:
        resp = session.post(f"{BASE_URL}/GetOrganizations", headers=HEADERS, json={})
        orgs = resp.json().get("organizations", {})
        keys = list(orgs.keys())
        print(f"Connected to {len(keys)} organizations.")
        return keys
    except Exception as e:
        print(f"Error connecting to server: {e}")
        sys.exit(1)

def download_messages():
    # 1. Use a Session object for persistent connections (Efficiency)
    session = requests.Session()
    
    org_keys = get_org_keys(session)
    if not org_keys:
        return

    all_conversations = {}
    # Use a master address book to harvest doctor names from all threads
    master_address_book = {}
    
    tags_to_fetch = [1, 2] # 1: Inbox, 2: Archive
    
    for tag in tags_to_fetch:
        tag_name = "INBOX" if tag == 1 else "ARCHIVE"
        print(f"\n--- Starting Fetch for {tag_name} ---")
        
        anchors = {k: "" for k in org_keys}
        local_anchor = ""
        page_num = 1
        empty_page_retries = 0

        while True:
            current_nonce = generate_page_nonce()
            
            payload = {
                "tag": tag,
                "localLoadParams": {
                    "loadStartInstantISO": local_anchor,
                    "loadEndInstantISO": "",
                    "pagingInfo": 1
                },
                "externalLoadParams": {
                    k: {
                        "communicationCenter": {
                            "loadStartInstantISO": anchors[k],
                            "loadEndInstantISO": "",
                            "pagingInfo": 1
                        }
                    } for k in org_keys
                },
                "searchQuery": "",
                "PageNonce": current_nonce
            }

            try:
                url = f"{BASE_URL}/GetConversationList?cb={current_nonce}"
                response = session.post(url, headers=HEADERS, json=payload, timeout=30)
                
                if response.status_code != 200:
                    print(f"Warning: Page {page_num} failed (Status {response.status_code}). Skipping...")
                    break

                data = response.json()
                batch = data.get("conversations", [])
                
                # 2. Extract and merge address book data (Harvesting)
                # This ensures hydrate.py has the best possible name mapping
                page_overrides = data.get("userOverrideNames", {})
                master_address_book.update(page_overrides)

                if not batch:
                    # 3. Intelligent Lookback (Retry empty pages once to ensure end of history)
                    if empty_page_retries < 1:
                        empty_page_retries += 1
                        print(f"Page {page_num} empty, retrying once...")
                        time.sleep(2)
                        continue
                    print(f"End of {tag_name} reached.")
                    break

                empty_page_retries = 0 # Reset retries if we found data
                new_in_batch = 0
                for conv in batch:
                    cid = conv.get("hthId")
                    if cid not in all_conversations:
                        # 4. Save metadata about attachments if they exist
                        if conv.get("hasAttachments"):
                            print(f"  [File Found] In thread: {conv.get('subject')}")
                        
                        all_conversations[cid] = conv
                        new_in_batch += 1
                
                print(f"{tag_name} Page {page_num}: Received {len(batch)} items ({new_in_batch} new).")

                if new_in_batch == 0 and page_num > 1:
                    print(f"Overlapping history detected. Closing {tag_name}.")
                    break

                # Update anchors for the next page
                last_conv = batch[-1]
                if "messages" in last_conv and last_conv["messages"]:
                    last_ts = last_conv["messages"][-1].get("deliveryInstantISO")
                    local_anchor = last_ts
                    for k in org_keys:
                        anchors[k] = last_ts
                else:
                    break
                    
                page_num += 1
                # 5. Adaptive Throttling (Small delay to avoid lockout)
                time.sleep(1.0)

                # 6. Incremental Save (Saves progress every 5 pages in case of crash)
                if page_num % 5 == 0:
                    with open("mychart_all_messages_partial.json", "w") as f:
                        json.dump(list(all_conversations.values()), f, indent=2)

            except requests.exceptions.RequestException as e:
                print(f"Network error on page {page_num}: {e}")
                break

    # Final Save
    final_list = list(all_conversations.values())
    # Inject the harvested master address book into every conversation object
    for conv in final_list:
        if "userOverrideNames" not in conv:
            conv["userOverrideNames"] = {}
        conv["userOverrideNames"].update(master_address_book)

    with open("mychart_all_messages.json", "w") as f:
        json.dump(final_list, f, indent=2)
    
    # Clean up partial save
    if os.path.exists("mychart_all_messages_partial.json"):
        os.remove("mychart_all_messages_partial.json")
    
    print(f"\nSuccess! Total unique threads found: {len(all_conversations)}")

if __name__ == "__main__":
    download_messages()
