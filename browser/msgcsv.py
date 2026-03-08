#!/usr/bin/env python3

import json
import pandas as pd
import re
import html  # Added to handle entity conversion

def clean_html(raw_html):
    """Removes HTML tags and converts entities to ASCII/Unicode."""
    if not raw_html:
        return ""
    
    # 1. Remove style tags and everything inside them
    cleanr = re.compile(r'<style.*?>.*?</style>', re.DOTALL)
    cleantext = re.sub(cleanr, '', raw_html)
    
    # 2. Remove all other HTML tags
    cleanr = re.compile(r'<.*?>')
    cleantext = re.sub(cleanr, ' ', cleantext)
    
    # 3. Convert HTML entities like &#dd; or &nbsp; to actual characters
    cleantext = html.unescape(cleantext)
    
    # 4. Clean up whitespace and line breaks
    cleantext = re.sub(r'\s+', ' ', cleantext).strip()
    
    return cleantext

def convert_mychart(input_file, output_file):
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: {input_file} not found.")
        return

    conversations = data.get("conversations", []) if isinstance(data, dict) else data

    rows = []
    for conv in conversations:
        subject = conv.get("subject", "No Subject")
        names = conv.get("userOverrideNames", {})
        
        for msg in conv.get("messages", []):
            author_info = msg.get("author", {})
            emp_key = author_info.get("empKey", "")
            author = author_info.get("displayName") or names.get(emp_key) or emp_key
            
            rows.append({
                "Date": msg.get("deliveryInstantISO", ""),
                "From": author,
                "Subject": subject,
                "Message": clean_html(msg.get("body", ""))
            })
            
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(by="Date")
        df.to_csv(output_file, index=False, encoding='utf-8-sig')
        print(f"Success! Created {output_file} with {len(rows)} messages.")
    else:
        print("No messages found to convert.")

if __name__ == "__main__":
    convert_mychart('mychart_all_messages.json', 'mychart_all_messages.csv')
