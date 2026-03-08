#!/usr/bin/env python3

import os
import requests
import json
import time
import uuid

BASE_URL = "https://mychart.umms.org/MyChart/api/conversations"
HEADERS = {
    '__requestverificationtoken': os.getenv("TOKEN"),
    'cookie': os.getenv("COOKIES"),
    'accept': 'application/json',
    'content-type': 'application/json',
}

def generate_page_nonce():
    """Generates a fresh UUID-based PageNonce."""
    return str(uuid.uuid4()).replace('-', '')

def get_org_keys():
    """Fetches organization keys dynamically."""
    print("Fetching linked organizations...")
    try:
        resp = requests.post(f"{BASE_URL}/GetOrganizations", headers=HEADERS, json={})
        orgs = resp.json().get("organizations", {})
        return list(orgs.keys())
    except Exception as e:
        print(f"Error fetching orgs: {e}")
        return []

def download_messages():
    org_keys = get_org_keys()
    if not org_keys:
        return

    # Use a dictionary to store all messages (de-duplicates by hthId)
    all_conversations = {}
    
    # Tag 1 = Current/Inbox, Tag 2 = Archive/History
    tags_to_fetch = [1, 2]
    
    for tag in tags_to_fetch:
        tag_name = "INBOX" if tag == 1 else "ARCHIVE"
        print(f"\n--- Starting Fetch for {tag_name} (Tag {tag}) ---")
        
        # Reset anchors for each tag
        anchors = {k: "" for k in org_keys}
        local_anchor = ""
        page_num = 1

        while True:
            current_nonce = generate_page_nonce()
            
            ext_params = {
                k: {
                    "communicationCenter": {
                        "loadStartInstantISO": anchors[k],
                        "loadEndInstantISO": "",
                        "pagingInfo": 1
                    }
                } for k in org_keys
            }
            
            payload = {
                "tag": tag,
                "localLoadParams": {
                    "loadStartInstantISO": local_anchor,
                    "loadEndInstantISO": "",
                    "pagingInfo": 1
                },
                "externalLoadParams": ext_params,
                "searchQuery": "",
                "PageNonce": current_nonce
            }

            url = f"{BASE_URL}/GetConversationList?cb={current_nonce}"
            response = requests.post(url, headers=HEADERS, json=payload)
            
            if response.status_code != 200:
                print(f"Request failed for Tag {tag}. Status: {response.status_code}")
                break

            data = response.json()
            batch = data.get("conversations", [])
            
            if not batch:
                print(f"No more messages in {tag_name}.")
                break

            new_in_batch = 0
            for conv in batch:
                cid = conv.get("hthId")
                if cid not in all_conversations:
                    all_conversations[cid] = conv
                    new_in_batch += 1
            
            print(f"{tag_name} Page {page_num}: Received {len(batch)} items ({new_in_batch} new). Total Unique: {len(all_conversations)}")

            # If the batch returned items but 0 were new, we've overlapped with what we already have
            if new_in_batch == 0:
                print(f"End of unique {tag_name} history reached.")
                break

            # Update anchors using the timestamp of the last message in the batch
            last_conv = batch[-1]
            if "messages" in last_conv and last_conv["messages"]:
                last_ts = last_conv["messages"][-1].get("deliveryInstantISO")
                local_anchor = last_ts
                for k in org_keys:
                    anchors[k] = last_ts
            else:
                break
                
            page_num += 1
            time.sleep(1.2) # Throttling to prevent server lockout

    with open("mychart_all_messages.json", "w") as f:
        json.dump(list(all_conversations.values()), f, indent=2)
    
    print(f"\nSuccess! Total items in combined history: {len(all_conversations)}")

if __name__ == "__main__":
    download_messages()
