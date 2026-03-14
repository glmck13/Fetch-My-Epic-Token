#!/usr/bin/env python3

import os
import requests
import json
import time
import uuid
import re
import html

# --- Configuration ---
BASE_URL = os.getenv("BASE_URL")
HEADERS = {
    '__requestverificationtoken': os.getenv("TOKEN"),
    'cookie': os.getenv("COOKIES"),
    'accept': 'application/json',
    'content-type': 'application/json',
}

def generate_nonce():
    return str(uuid.uuid4()).replace('-', '')

def clean_html(raw_html):
    if not raw_html: return ""
    # Remove CSS <style> blocks
    clean_text = re.sub(r'<style.*?>.*?</style>', '', raw_html, flags=re.DOTALL | re.IGNORECASE)
    # Remove HTML tags
    clean_text = re.sub(r'<[^<]+?>', '', clean_text)
    # Decode entities (&#39; -> ')
    clean_text = html.unescape(clean_text)
    # Normalize whitespace
    clean_text = re.sub(r'\n\s*\n', '\n\n', clean_text)
    return clean_text.strip()

def build_participant_header(conv):
    """Creates a readable list of all doctors/staff involved in this thread."""
    participants = []
    
    # Check the audience list
    for person in conv.get("audience", []):
        name = person.get("name")
        if name and name not in participants:
            participants.append(name)
            
    # Check the users list (sometimes contains different entries)
    for user in conv.get("users", []):
        name = user.get("displayName")
        if name and name not in participants:
            participants.append(name)
            
    if not participants:
        return "PARTICIPANTS: Staff/System Only"
        
    return "PARTICIPANTS: " + " | ".join(participants)

def resolve_author_name(msg, name_map, viewer_keys, audience, org_id):
    author_obj = msg.get("author", {})
    wpr_key = author_obj.get("wprKey") or author_obj.get("empKey") or ""
    
    if wpr_key in viewer_keys: return "Me (Patient)"
    if wpr_key in name_map: return name_map[wpr_key]

    # Handle the 'OrgID_StaffID' naming convention
    if org_id and org_id in wpr_key:
        stripped_key = wpr_key.replace(f"{org_id}_", "")
        if stripped_key in name_map: return name_map[stripped_key]
        stripped_ser = stripped_key.replace("ser_", "")
        if stripped_ser in name_map: return name_map[stripped_ser]

    for person in audience:
        p_id = person.get("providerId")
        e_id = person.get("empId")
        if wpr_key in [p_id, e_id] or (p_id and p_id in wpr_key) or (e_id and e_id in wpr_key):
            return person.get("name")

    return "Staff/System"

def get_full_text(hth_id, org_id):
    all_msgs = []
    anchor = ""
    while True:
        nonce = generate_nonce()
        payload = {"id": hth_id, "organizationId": org_id or "", "startInstantISO": anchor, "PageNonce": nonce}
        try:
            url = f"{BASE_URL}/GetConversationMessages?cb={nonce}"
            resp = requests.post(url, headers=HEADERS, json=payload)
            if resp.status_code != 200: break
            batch = resp.json().get("messages", [])
            if not batch: break
            all_msgs.extend(batch)
            new_anchor = batch[-1].get("deliveryInstantISO")
            if not new_anchor or new_anchor == anchor: break
            anchor = new_anchor
            time.sleep(0.4)
        except: break
    return all_msgs

def hydrate():
    input_file = "mychart_all_messages.json"
    if not os.path.exists(input_file):
        print("Error: run messages.py first.")
        return

    with open(input_file, "r") as f:
        conversations = json.load(f)

    print(f"Hydrating {len(conversations)} threads...")
    transcript = []

    for i, conv in enumerate(conversations, 1):
        hth_id = conv.get("hthId")
        org_id = conv.get("organizationId")
        subject = conv.get("subject", "No Subject")
        
        # Build the new Metadata Header
        participant_header = build_participant_header(conv)

        print(f"[{i}/{len(conversations)}] Processing: {subject[:50]}...")
        
        full_history = get_full_text(hth_id, org_id)
        active_messages = full_history if full_history else conv.get("messages", [])

        # Start thread block in transcript
        transcript.append(f"\n{'='*80}")
        transcript.append(f"SUBJECT:      {subject}")
        transcript.append(f"{participant_header}")
        transcript.append(f"{'='*80}")
        
        processed_wmg_ids = set()
        for msg in active_messages:
            wmg_id = msg.get("wmgId")
            if wmg_id in processed_wmg_ids: continue
            processed_wmg_ids.add(wmg_id)

            author = resolve_author_name(msg, conv.get("userOverrideNames", {}), conv.get("viewerKeys", []), conv.get("audience", []), org_id)
            date = msg.get("deliveryInstantISO", "Unknown")
            body = clean_html(msg.get("body", ""))
            
            transcript.append(f"FROM: {author}\nDATE: {date}\n\n{body}\n{'-'*40}")

    with open("mychart_final_transcript.txt", "w") as f:
        f.write("\n".join(transcript))

    print("\nComplete! See 'mychart_final_transcript.txt' for the updated headers.")

if __name__ == "__main__":
    hydrate()
