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

def build_participant_header(conv):
    """Lists all medical staff involved in the thread."""
    participants = []
    for person in conv.get("audience", []):
        name = person.get("name")
        if name and name not in participants:
            participants.append(name)
    for user in conv.get("users", []):
        name = user.get("displayName")
        if name and name not in participants:
            participants.append(name)
    return "PARTICIPANTS: " + (" | ".join(participants) if participants else "Staff/System Only")

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
            time.sleep(0.2) # Slight pause to be polite to the server
        except: break
    return all_msgs

def process_conversation(conv, session):
    """Worker function to process a single thread block."""
    hth_id = conv.get("hthId")
    org_id = conv.get("organizationId")
    subject = conv.get("subject", "No Subject")
    
    full_history = get_full_text(hth_id, org_id, session)
    active_messages = full_history if full_history else conv.get("messages", [])

    block = [
        f"\n{'='*80}",
        f"SUBJECT:      {subject}",
        f"{build_participant_header(conv)}",
        f"{'='*80}"
    ]
    
    processed_wmg_ids = set()
    for msg in active_messages:
        wmg_id = msg.get("wmgId")
        if wmg_id in processed_wmg_ids: continue
        processed_wmg_ids.add(wmg_id)

        author = resolve_author_name(msg, conv.get("userOverrideNames", {}), 
                                     conv.get("viewerKeys", []), conv.get("audience", []), org_id)
        date = msg.get("deliveryInstantISO", "Unknown")
        body = clean_html(msg.get("body", ""))
        block.append(f"FROM: {author}\nDATE: {date}\n\n{body}\n{'-'*40}")
        
    return "\n".join(block)

def hydrate(max_workers=5):
    """Main execution loop using multi-threading."""
    input_file = "mychart_all_messages.json"
    if not os.path.exists(input_file):
        print("Error: run messages.py first.")
        return

    with open(input_file, "r") as f:
        conversations = json.load(f)

    print(f"Hydrating {len(conversations)} threads using {max_workers} parallel workers...")
    
    session = requests.Session()
    final_results = [None] * len(conversations)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit tasks and track their original index to keep order
        future_to_idx = {executor.submit(process_conversation, c, session): i 
                         for i, c in enumerate(conversations)}
        
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                final_results[idx] = future.result()
                print(f"[{idx + 1}/{len(conversations)}] Processed: {conversations[idx].get('subject')[:30]}...")
            except Exception as e:
                print(f"Error on thread {idx}: {e}")

    with open("mychart_final_transcript.txt", "w") as f:
        f.write("\n".join(filter(None, final_results)))

    print(f"\nComplete! Transcript saved to 'mychart_final_transcript.txt'.")

if __name__ == "__main__":
    # Suggested: 5 workers is usually safe. 10 is faster but may trigger rate limits.
    hydrate(max_workers=5)
