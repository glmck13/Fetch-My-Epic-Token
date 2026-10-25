#!/usr/bin/env python3

import sys
import os
import json
import zipfile
import shutil
import asyncio
import httpx
import re
import base64
import tempfile
import logging
import csv
from urllib.parse import parse_qs

# Configure logging to stderr so it doesn't pollute stdout binary streams
logging.basicConfig(level=logging.WARNING, stream=sys.stderr, format="%(levelname)s: %(message)s")

# --- CONFIGURATION & ENVIRONMENT ---
MAX_CONCURRENT_REQUESTS = 10
semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

Method = os.getenv("REQUEST_METHOD", "")
if Method == "GET":
    QueryString = os.getenv("QUERY_STRING", "")
elif Method == "POST":
    QueryString = sys.stdin.read()
else:
    QueryString = ""

if QueryString:
    Fields = parse_qs(QueryString)
    ApiBase = Fields.get("ApiBase", [""])[0]
    Patient = Fields.get("Patient", [""])[0]
    Token = Fields.get("Token", [""])[0]
    Organization = Fields.get("Organization", ["None"])[0]
else:
    ApiBase = os.getenv("APIBASE", "")
    Patient = os.getenv("PATIENT", "")
    Token = os.getenv("OAUTH_TOKEN", "")
    Organization = "None"

# --- HELPER FUNCTIONS ---

async def fetch_json(client, url, headers):
    async with semaphore:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logging.warning(f"Failed to fetch {url}: {e}")
            return {}

async def fetch_resource_list(client, path, headers):
    url = f"{ApiBase}/{path}" if not path.startswith("http") else path
    data = await fetch_json(client, url, headers)
    return data.get("entry", [])

def clean_filename(name):
    # Sanitize string to safe filename characters to prevent path traversal
    clean_name = re.sub(r'[^\w\.-]', '_', str(name))
    return os.path.basename(clean_name) or "unnamed_file"

# --- MAIN ASYNC LOGIC ---

async def main():
    Headers = {"Authorization": f"Bearer {Token}", "Accept": "application/json+fhir"}

    # Use TemporaryDirectory context manager for guaranteed disk cleanup
    with tempfile.TemporaryDirectory() as TmpDir:
        OldDir = os.getcwd()
        os.chdir(TmpDir)
        ZIPFILE = "EHR.zip"
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                # 1. Parallel Initial Fetches
                endpoints = [
                    f"Encounter?patient={Patient}",
                    f"Immunization?patient={Patient}",
                    f"Observation?patient={Patient}&category=vital-signs",
                    f"Observation?patient={Patient}&category=laboratory",
                    f"DiagnosticReport?patient={Patient}",
                    f"DocumentReference?patient={Patient}&category=clinical-note"
                ]
                
                tasks = [fetch_resource_list(client, ep, Headers) for ep in endpoints]
                results = await asyncio.gather(*tasks)
                Encntr, Shots, VitalOb, LabOb, DiagRpt, RefDoc = results

                # 2. Process Immunizations (using csv.writer)
                if Shots:
                    with open("Immunizations.csv", "w", newline="", encoding="utf-8") as f:
                        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
                        writer.writerow(["When", "What"])
                        for s in Shots:
                            r = s.get("resource", {})
                            if r.get("resourceType") == "Immunization":
                                when = r.get("occurrenceDateTime", "")
                                what = r.get("vaccineCode", {}).get("text", "")
                                if when:
                                    writer.writerow([when, what])

                # 3. Process Encounters (using csv.writer)
                if Encntr:
                    with open("Visits.csv", "w", newline="", encoding="utf-8") as f:
                        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
                        writer.writerow(["When", "What", "Why", "How", "Who", "Where"])
                        for e in Encntr:
                            r = e.get("resource", {})
                            when = r.get("period", {}).get("start", "")
                            what = r.get("class", {}).get("display", "")
                            why = ",".join([x.get("text", "") for x in r.get("reasonCode", []) if x.get("text")])
                            how = ",".join([x.get("text", "") for x in r.get("type", []) if x.get("text")])
                            who = ",".join([x.get("individual", {}).get("display", "") for x in r.get("participant", []) if x.get("individual")])
                            where = ",".join([x.get("location", {}).get("display", "") for x in r.get("location", []) if x.get("location")])
                            if when:
                                writer.writerow([when, what, why, how, who, where])

                # 4. Handle Lab and Diagnostic Reports
                LabObId = set()
                LabObRec = []
                for x in LabOb:
                    r = x.get("resource", {})
                    if r.get("resourceType") == "Observation":
                        res_id = r.get("id")
                        if res_id:
                            LabObId.add(f"Observation/{res_id}")
                        LabObRec.append(r)

                DiagObId = []
                for x in DiagRpt:
                    r = x.get("resource", {})
                    if r.get("resourceType") == "DiagnosticReport":
                        for res_ref in r.get("result", []):
                            ref = res_ref.get("reference", "")
                            if '/' in ref and ref not in LabObId:
                                DiagObId.append(ref)

                diag_tasks = [fetch_json(client, f"{ApiBase}/{ref}", Headers) for ref in DiagObId]
                diag_responses = await asyncio.gather(*diag_tasks)
                
                DiagObRec = []
                for y in diag_responses:
                    if not y:
                        continue
                    toss = any(w.get("code") == "Lab" for z in y.get("category", []) for w in z.get("coding", []))
                    if not toss:
                        DiagObRec.append(y)

                NewLabObRec = []
                for x in LabObRec:
                    y = x.get("code", {}).get("text", "").lower()
                    if "report" in y or "path" in y:
                        DiagObRec.append(x)
                    elif y:
                        NewLabObRec.append(x)
                LabObRec = NewLabObRec

                # 5. Write Labs.csv (using csv.writer)
                if LabObRec or VitalOb:
                    with open("Labs.csv", "w", newline="", encoding="utf-8") as f:
                        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
                        writer.writerow(["Order", "DateTime", "Test", "Value"])
                        
                        for x in LabObRec:
                            based_on = x.get("basedOn", [{}])
                            order = based_on[0].get("display", "") if based_on else ""
                            dt = x.get("effectiveDateTime", "")
                            test = x.get("code", {}).get("text", "")
                            
                            if "valueQuantity" in x and x["valueQuantity"]:
                                val = x["valueQuantity"].get("value", "")
                            elif "valueRatio" in x and x["valueRatio"]:
                                ratio = x["valueRatio"]
                                num = ratio.get("numerator", {}).get("value", "")
                                den = ratio.get("denominator", {}).get("value", "")
                                val = f"{num}/{den}" if num != "" or den != "" else ""
                            elif "valueRange" in x and x["valueRange"]:
                                v_range = x["valueRange"]
                                low = v_range.get("low", {}).get("value", "")
                                high = v_range.get("high", {}).get("value", "")
                                val = f"{low}-{high}" if low != "" or high != "" else ""
                            elif "valueString" in x and x["valueString"] is not None:
                                val = str(x["valueString"])
                            else:
                                val = ""
                            
                            writer.writerow([order, dt, test, val])

                        for x in VitalOb:
                            r = x.get("resource", {})
                            if r.get("resourceType") != "Observation":
                                continue
                            
                            categories = r.get("category", [{}])
                            order = categories[0].get("text", "") if categories else ""
                            dt = r.get("effectiveDateTime", "")
                            test = r.get("code", {}).get("text", "")
                            
                            if r.get("valueQuantity"):
                                val = r["valueQuantity"].get("value", "")
                            elif r.get("component"):
                                val = ' / '.join([str(y.get("valueQuantity", {}).get("value", "")) for y in r["component"] if "valueQuantity" in y])
                            else:
                                val = ""
                            writer.writerow([order, dt, test, val])

                # 6. Write Diagnostic Report Text Files
                for x in DiagObRec:
                    order_list = x.get("basedOn", [])
                    order = order_list[0].get("display", "None") if order_list else "None"
                    dt = x.get('effectiveDateTime', "NoDate")
                    test = x.get('code', {}).get('text', "NoTest")
                    fname = clean_filename(f"{order}-{dt}-{test}.txt")
                    with open(fname, "w", encoding="utf-8") as f:
                        f.write(x.get("valueString", ""))

                # 7. Fetch and Write Document Notes
                async def download_note(doc_ref):
                    r = doc_ref.get("resource", {})
                    if r.get("resourceType") != "DocumentReference" or "author" not in r:
                        return
                    
                    authors = r.get("author", [])
                    author = authors[0].get("display", "Unknown") if authors else "Unknown"
                    
                    for content in r.get("content", []):
                        att = content.get("attachment", {})
                        c_type = att.get("contentType", "")
                        
                        if "html" in c_type.lower():
                            continue

                        fname = clean_filename(f"Note-{author}-{r.get('date', '')}.{c_type.split('/')[-1]}")

                        if "url" in att:
                            url = att["url"]
                            if not url.startswith("http"):
                                url = f"{ApiBase}/{url}"
                            
                            async with semaphore:
                                try:
                                    note_resp = await client.get(
                                        url,
                                        headers={"Authorization": f"Bearer {Token}", "Accept": c_type}
                                    )
                                    note_resp.raise_for_status()
                                    with open(fname, "wb") as f:
                                        f.write(note_resp.content)
                                except Exception as e:
                                    logging.warning(f"Failed to download note from {url}: {e}")

                        elif "data" in att:
                            try:
                                decoded_data = base64.b64decode(att["data"])
                                with open(fname, "wb") as f:
                                    f.write(decoded_data)
                            except Exception as e:
                                logging.warning(f"Failed to decode inline attachment data: {e}")

                await asyncio.gather(*[download_note(d) for d in RefDoc])

                # 8. Create ZIP File
                with zipfile.ZipFile(ZIPFILE, "w") as zf:
                    for folder, _, files in os.walk(TmpDir):
                        for f in files:
                            if f != ZIPFILE:
                                zf.write(os.path.join(folder, f), f, compress_type=zipfile.ZIP_DEFLATED)

            # Output CGI headers if executing as a web gateway
            if os.getenv("SCRIPT_FILENAME"):
                fname = clean_filename(f"{Organization}.zip")
                cgi_headers = (
                    f"Content-type: application/octet-stream\r\n"
                    f"Content-Disposition: attachment; filename={fname}\r\n\r\n"
                )
                sys.stdout.buffer.write(cgi_headers.encode("utf-8"))

            # Stream binary ZIP contents directly to stdout in 64KB chunks
            with open(ZIPFILE, "rb") as f:
                while chunk := f.read(65536):
                    sys.stdout.buffer.write(chunk)
            
            sys.stdout.buffer.flush()

        finally:
            os.chdir(OldDir)

if __name__ == "__main__":
    asyncio.run(main())
