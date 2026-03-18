#!/usr/bin/env python3

import os
import requests
import json
import time
import uuid
import re
import html
import sys
import shlex
import codecs
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- LOGGING HELPER ---
def log(msg):
    """Writes progress to stderr for web server or terminal log tracking."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [MyChart-CGI] {msg}", file=sys.stderr)
    sys.stderr.flush()

# --- ROBUST PARSING ---
def parse_curl(curl_str):
    log("Starting robust cURL parse...")
    try:
        curl_str = curl_str.replace('\\\n', ' ').replace('\\ ', ' ')
        parts = shlex.split(curl_str, posix=True)
        url, token, cookies = "", "", ""
        
        for i, part in enumerate(parts):
            if part.startswith('http') and not url:
                url = part.rsplit('/', 1)[0]
            if part.lower() in ['-h', '--header']:
                h_parts = parts[i+1].split(':', 1)
                if len(h_parts) == 2 and h_parts[0].strip().lower() == '__requestverificationtoken':
                    token = h_parts[1].strip()
            if part.lower() in ['-b', '--cookie']:
                raw_cookies = parts[i+1].strip()
                if raw_cookies.startswith('$'):
                    cookies = codecs.decode(raw_cookies[1:], 'unicode_escape')
                else:
                    cookies = raw_cookies
        
        log(f"Parsed URL: {url} | Token: {len(token)} chars | Cookies: {len(cookies)} chars")
        return url, token, cookies
    except Exception as e:
        log(f"Parse error: {str(e)}")
        return None, None, None

# --- CORE LOGIC (STRICT PRESERVATION) ---

def clean_html(raw_html):
    if not raw_html: return ""
    clean_text = re.sub(r'<style.*?>.*?</style>', '', raw_html, flags=re.DOTALL | re.IGNORECASE)
    clean_text = re.sub(r'<[^<]+?>', '', clean_text)
    clean_text = html.unescape(clean_text)
    clean_text = re.sub(r'\n\s*\n', '\n\n', clean_text)
    return clean_text.strip()

def resolve_author_name(msg, name_map, viewer_keys, audience, org_id):
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

def get_full_text(hth_id, org_id, session, config):
    all_msgs, anchor = [], ""
    while True:
        nonce = str(uuid.uuid4()).replace('-', '')
        payload = {"id": hth_id, "organizationId": org_id or "", "startInstantISO": anchor, "PageNonce": nonce}
        try:
            url = f"{config['BASE_URL']}/GetConversationMessages?cb={nonce}"
            resp = session.post(url, headers=config['HEADERS'], json=payload, timeout=20)
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

def process_conversation(conv, session, config):
    hth_id, org_id = conv.get("hthId"), conv.get("organizationId")
    subject = conv.get("subject", "No Subject")
    full_history = get_full_text(hth_id, org_id, session, config)
    active_messages = full_history if full_history else conv.get("messages", [])
    
    message_lines, found_participants, processed_wmg_ids = [], set(), set()
    latest_date = "0000-00-00T00:00:00Z"
    
    for msg in active_messages:
        wmg_id = msg.get("wmgId")
        if wmg_id and wmg_id in processed_wmg_ids: continue
        if wmg_id: processed_wmg_ids.add(wmg_id)

        author = resolve_author_name(msg, conv.get("userOverrideNames", {}), conv.get("viewerKeys", []), conv.get("audience", []), org_id)
        found_participants.add(author)
        date = msg.get("deliveryInstantISO", "Unknown")
        if date != "Unknown" and date > latest_date: latest_date = date
        body = clean_html(msg.get("body", ""))
        message_lines.append(f"FROM: {author}\nDATE: {date}\n\n{body}\n{'-'*40}")
    
    participant_header = " | ".join(sorted(list(found_participants)))
    block = [f"\n{'='*80}", f"SUBJECT:      {subject}", f"PARTICIPANTS: {participant_header}", f"{'='*80}", "\n".join(message_lines)]
    return (latest_date, "\n".join(block))

def download_messages(config, json_path):
    session = requests.Session()
    log("Fetching organizations...")
    try:
        resp = session.post(f"{config['BASE_URL']}/GetOrganizations", headers=config['HEADERS'], json={})
        org_keys = list(resp.json().get("organizations", {}).keys())
        log(f"Connected to {len(org_keys)} organizations.")
    except Exception as e:
        log(f"Connection error: {e}")
        return False

    all_conversations, master_address_book = {}, {}
    for tag in [1, 2]:
        tag_label = "INBOX" if tag == 1 else "ARCHIVE"
        anchors = {k: "" for k in org_keys}
        local_anchor, page_num, empty_page_retries = "", 1, 0
        
        while True:
            nonce = str(uuid.uuid4()).replace('-', '')
            payload = {
                "tag": tag,
                "localLoadParams": {"loadStartInstantISO": local_anchor, "loadEndInstantISO": "", "pagingInfo": 1},
                "externalLoadParams": {
                    k: {"communicationCenter": {"loadStartInstantISO": anchors[k], "loadEndInstantISO": "", "pagingInfo": 1}} 
                    for k in org_keys
                },
                "searchQuery": "",
                "PageNonce": nonce
            }
            
            url = f"{config['BASE_URL']}/GetConversationList?cb={nonce}"
            response = session.post(url, headers=config['HEADERS'], json=payload, timeout=30)
            
            if response.status_code != 200:
                log(f"Error on {tag_label} page {page_num}: Status {response.status_code}")
                break
                
            data = response.json()
            batch = data.get("conversations", [])
            master_address_book.update(data.get("userOverrideNames", {}))
            
            if not batch:
                if empty_page_retries < 1:
                    empty_page_retries += 1
                    log(f"{tag_label} page {page_num} empty, retrying once...")
                    time.sleep(2)
                    continue
                break
            
            empty_page_retries = 0
            new_count = 0
            for conv in batch:
                cid = conv.get("hthId")
                if cid not in all_conversations:
                    all_conversations[cid] = conv
                    new_count += 1
            
            log(f"{tag_label} Page {page_num}: Received {len(batch)} items ({new_count} new).")
            if new_count == 0 and page_num > 1: break
            
            last_ts = batch[-1]["messages"][-1].get("deliveryInstantISO")
            local_anchor = last_ts
            for k in org_keys: anchors[k] = last_ts
            page_num += 1
            time.sleep(1.0)

    final_list = list(all_conversations.values())
    for conv in final_list:
        conv.setdefault("userOverrideNames", {}).update(master_address_book)
    with open(json_path, "w") as f:
        json.dump(final_list, f)
    log(f"Success! Total unique threads found: {len(all_conversations)}")
    return True

def hydrate(config, json_path):
    with open(json_path, "r") as f:
        conversations = json.load(f)
    log(f"Hydrating {len(conversations)} threads...")
    session = requests.Session()
    unsorted_results = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(process_conversation, c, session, config) for c in conversations]
        for i, future in enumerate(as_completed(futures)):
            try:
                result = future.result()
                unsorted_results.append(result)
                if (i + 1) % 5 == 0 or (i + 1) == len(conversations):
                    log(f"Processed {i + 1}/{len(conversations)} threads...")
            except Exception as e:
                log(f"Error processing thread: {e}")
                
    log("Sorting transcript by date...")
    unsorted_results.sort(key=lambda x: x[0], reverse=True)
    return "\n".join(res[1] for res in unsorted_results)

# --- REFACTORED CGI ENTRY ---

if __name__ == "__main__":
    raw_curl = None
    if os.environ.get("REQUEST_METHOD") == "POST":
        try:
            length = int(os.environ.get("CONTENT_LENGTH", 0))
            body = sys.stdin.read(length)
            params = urllib.parse.parse_qs(body)
            raw_curl = params.get("clipboard_content", [None])[0]
        except Exception as e:
            log(f"POST parse error: {e}")

    if not raw_curl:
        print("Content-Type: text/html\n")
        print("<html><body><form method='POST'>Paste cURL Command:<br><textarea name='clipboard_content' rows='12' cols='100'></textarea><br><input type='submit' value='Process'></form></body></html>")
        sys.exit(0)

    base, token, cookies = parse_curl(raw_curl)
    if not (base and token and cookies):
        print("Content-Type: text/html\n\n<h1>Parse Error</h1><p>Check stderr logs.</p>")
        sys.exit(1)

    config = {
        'BASE_URL': base,
        'HEADERS': {
            '__requestverificationtoken': token,
            'cookie': cookies,
            'accept': 'application/json',
            'content-type': 'application/json',
        }
    }

    run_id = str(uuid.uuid4())[:8]
    tmp_json = f"/tmp/mychart_{run_id}.json"
    
    try:
        if download_messages(config, tmp_json):
            final_text = hydrate(config, tmp_json)
            print("Content-Type: text/plain")
            print(f"Content-Disposition: attachment; filename=\"mychart_transcript_{run_id}.txt\"")
            print()
            print(final_text)
            log("Process complete. File sent.")
    finally:
        if os.path.exists(tmp_json):
            os.remove(tmp_json)
