#!/usr/bin/env python3

import os
import requests
import json
import time
import uuid
import re
import html
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- Configuration ---
BASE_URL = os.getenv("BASE_URL")
HEADERS = {
    '__requestverificationtoken': os.getenv("TOKEN"),
    'cookie': os.getenv("COOKIES"),
    'accept': 'application/json',
    'content-type': 'application/json',
}

def generate_nonce():
    """Generates a unique nonce for API calls."""
    return str(uuid.uuid4()).replace('-', '')

def clean_html(raw_html):
    """Removes CSS and HTML tags to return plain text."""
    if not raw_html: return ""
    clean_text = re.sub(r'<style.*?>.*?</style>', '', raw_html, flags=re.DOTALL | re.IGNORECASE)
    clean_text = re.sub(r'<[^<]+?>', '', clean_text)
    clean_text = html.unescape(clean_text)
    clean_text = re.sub(r'\n\s*\n', '\n\n', clean_text)
    return clean_text.strip()

def resolve_author_name(msg, name_map, viewer_keys, audience, org_id):
    """Maps internal IDs back to readable names."""
    author_obj = msg.get("author", {})
    wpr_key = author_obj.get("wprKey") or author_obj.get("empKey") or ""
    
    if wpr_key in viewer_keys: return "Me (Patient)"
    if wpr_key in name_map: return name_map[wpr_key]

    if org_id and org_id in wpr_key:
        stripped_key = wpr_key.replace(f"{org_id}_", "")
        if stripped_key in name_map: return name_map[stripped_key]

    for person in audience:
        if wpr_key in [person.get("providerId"), person.get("empId")]:
            return person.get("name")
    return "Staff/System"

def get_full_text(hth_id, org_id, session):
    """Fetches full message history using a shared session."""
    all_msgs = []
    anchor = ""
    while True:
        nonce = generate_nonce()
        payload = {"id": hth_id, "organizationId": org_id or "", "startInstantISO": anchor, "PageNonce": nonce}
        try:
            url = f"{BASE_URL}/GetConversationMessages?cb={nonce}"
            resp = session.post(url, headers=HEADERS, json=payload, timeout=20)
            if resp.status_code != 200: break
            batch = resp.json().get("messages", [])
            if not batch: break
            all_msgs.extend(batch)
            new_anchor = batch[-1].get("deliveryInstantISO")
            if not new_anchor or new_anchor == anchor: break
            anchor = new_anchor
            time.sleep(0.2) 
        except: break
    return all_msgs

def process_conversation(conv, session):
    """Processes a single thread and returns (latest_date, formatted_block)."""
    hth_id = conv.get("hthId")
    org_id = conv.get("organizationId")
    subject = conv.get("subject", "No Subject")
    
    full_history = get_full_text(hth_id, org_id, session)
    active_messages = full_history if full_history else conv.get("messages", [])

    message_lines = []
    found_participants = set()
    processed_wmg_ids = set()
    latest_date = "0000-00-00T00:00:00Z" # Default for sorting

    for msg in active_messages:
        wmg_id = msg.get("wmgId")
        if wmg_id in processed_wmg_ids: continue
        processed_wmg_ids.add(wmg_id)

        author = resolve_author_name(msg, conv.get("userOverrideNames", {}), 
                                     conv.get("viewerKeys", []), conv.get("audience", []), org_id)
        
        found_participants.add(author)

        date = msg.get("deliveryInstantISO", "Unknown")
        # Track the latest message date in this conversation for sorting
        if date != "Unknown" and date > latest_date:
            latest_date = date

        body = clean_html(msg.get("body", ""))
        message_lines.append(f"FROM: {author}\nDATE: {date}\n\n{body}\n{'-'*40}")
    
    participant_header = " | ".join(sorted(list(found_participants))) if found_participants else "No Participants Found"

    block = [
        f"\n{'='*80}",
        f"SUBJECT:      {subject}",
        f"PARTICIPANTS: {participant_header}",
        f"{'='*80}"
    ]
    block.extend(message_lines)
        
    return (latest_date, "\n".join(block))

def hydrate(max_workers=5):
    """Main execution loop: Fetches, sorts, and saves transcripts."""
    input_file = "mychart_all_messages.json"
    if not os.path.exists(input_file):
        print("Error: run messages.py first.")
        return

    with open(input_file, "r") as f:
        conversations = json.load(f)

    print(f"Hydrating {len(conversations)} threads using {max_workers} parallel workers...")
    
    session = requests.Session()
    unsorted_results = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(process_conversation, c, session) for c in conversations]
        
        for i, future in enumerate(as_completed(futures)):
            try:
                result = future.result() # result is (latest_date, block_text)
                unsorted_results.append(result)
                print(f"[{i + 1}/{len(conversations)}] Processed: {conversations[i].get('subject')[:30]}...")
            except Exception as e:
                print(f"Error processing thread: {e}")

    # Sort all conversation blocks by their latest message date (Descending)
    print("Sorting transcript by date...")
    unsorted_results.sort(key=lambda x: x[0], reverse=True)

    with open("mychart_final_transcript.txt", "w") as f:
        # Extract just the block_text (index 1) from the sorted tuples
        f.write("\n".join(res[1] for res in unsorted_results))

    print(f"\nComplete! Transcript sorted by date and saved to 'mychart_final_transcript.txt'.")

if __name__ == "__main__":
    hydrate(max_workers=5)
