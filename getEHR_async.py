#!/usr/bin/env python3

import sys, os, json, zipfile, shutil, asyncio, httpx
from urllib.parse import parse_qs
from tempfile import mkdtemp

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
            return response.json()
        except Exception:
            return {}

async def fetch_resource_list(client, path, headers):
    url = f"{ApiBase}/{path}" if not path.startswith("http") else path
    data = await fetch_json(client, url, headers)
    return data.get("entry", [])

def clean_filename(name):
    for c in ":',/ ":
        name = name.replace(c, '_')
    return name

# --- MAIN ASYNC LOGIC ---

async def main():
    if os.getenv("SCRIPT_FILENAME"):
        fname = clean_filename(f"{Organization}.zip")
        print("Content-type: application/octet-stream")
        print(f"Content-Disposition: attachment; filename={fname}")
        print()
        sys.stdout.flush()

    TmpDir = mkdtemp()
    OldDir = os.getcwd()
    os.chdir(TmpDir)

    Headers = {"Authorization": f"Bearer {Token}", "Accept": "application/json+fhir"}

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

        # 2. Process Immunizations
        if Shots:
            with open("Immunizations.csv", "w") as f:
                f.write('"When","What"\n')
                for s in Shots:
                    r = s["resource"]
                    if r.get("resourceType") == "Immunization":
                        when = r.get("occurrenceDateTime", "")
                        what = r.get("vaccineCode", {}).get("text", "")
                        if when: f.write(f'"{when}","{what}"\n')

        # 3. Process Encounters
        if Encntr:
            with open("Visits.csv", "w") as f:
                f.write('"When","What","Why","How","Who","Where"\n')
                for e in Encntr:
                    r = e["resource"]
                    when = r.get("period", {}).get("start", "")
                    what = r.get("class", {}).get("display", "")
                    why = ",".join([x.get("text", "") for x in r.get("reasonCode", []) if x.get("text")])
                    how = ",".join([x.get("text", "") for x in r.get("type", []) if x.get("text")])
                    who = ",".join([x.get("individual", {}).get("display", "") for x in r.get("participant", []) if x.get("individual")])
                    where = ",".join([x.get("location", {}).get("display", "") for x in r.get("location", []) if x.get("location")])
                    if when: f.write(f'"{when}","{what}","{why}","{how}","{who}","{where}"\n')

        # 4. Handle Lab and Diagnostic Reports
        LabObId = {f"{x['resource']['resourceType']}/{x['resource']['id']}" for x in LabOb if x['resource']['resourceType'] == "Observation"}
        LabObRec = [x['resource'] for x in LabOb if x['resource']['resourceType'] == "Observation"]

        DiagObId = []
        for x in DiagRpt:
            r = x["resource"]
            if r.get("resourceType") == "DiagnosticReport":
                for res_ref in r.get("result", []):
                    ref = res_ref["reference"]
                    if '/' in ref and ref not in LabObId:
                        DiagObId.append(ref)

        diag_tasks = [fetch_json(client, f"{ApiBase}/{ref}", Headers) for ref in DiagObId]
        diag_responses = await asyncio.gather(*diag_tasks)
        
        DiagObRec = []
        for y in diag_responses:
            if not y: continue
            toss = any(w.get("code") == "Lab" for z in y.get("category", []) for w in z.get("coding", []))
            if not toss: DiagObRec.append(y)

        NewLabObRec = []
        for x in LabObRec:
            y = x["code"].get("text", "").lower()
            if "report" in y or "path" in y: DiagObRec.append(x)
            elif y: NewLabObRec.append(x)
        LabObRec = NewLabObRec

        # 5. Write Labs.csv (FIXED TYPE HANDLING)
        if LabObRec or VitalOb:
            with open("Labs.csv", "w") as f:
                f.write('"Order","DateTime","Test","Value"\n')
                for x in LabObRec:
                    order = x.get("basedOn", [{}])[0].get("display", "")
                    dt, test = x.get("effectiveDateTime", ""), x["code"].get("text", "")
                    
                    # Restored original logic to avoid .replace() on non-strings
                    if x.get("valueQuantity"):
                        val = x["valueQuantity"]["value"]
                    elif x.get("valueString"):
                        val = x["valueString"].replace('"', "'")
                    else:
                        val = ""
                    
                    f.write(f'"{order}","{dt}","{test}","{val}"\n')

                for x in VitalOb:
                    r = x["resource"]
                    if r.get("resourceType") != "Observation": continue
                    order, dt, test = r["category"][0].get("text", ""), r.get("effectiveDateTime", ""), r["code"].get("text", "")
                    if r.get("valueQuantity"): val = r["valueQuantity"]["value"]
                    elif r.get("component"):
                        val = ' / '.join([str(y["valueQuantity"]["value"]) for y in r["component"] if "valueQuantity" in y])
                    else: val = ""
                    f.write(f'"{order}","{dt}","{test}","{val}"\n')

        # 6. Write Diagnostic Report Text Files
        for x in DiagObRec:
            order_list = x.get("basedOn", [])
            order = order_list[0].get("display", "None") if order_list else "None"
            dt = x.get('effectiveDateTime', "NoDate")
            test = x['code'].get('text', "NoTest")
            fname = clean_filename(f"{order}-{dt}-{test}.txt")
            with open(fname, "w") as f:
                f.write(x.get("valueString", ""))

        # 7. Fetch and Write Document Notes
        async def download_note(doc_ref):
            r = doc_ref["resource"]
            if r.get("resourceType") != "DocumentReference" or "author" not in r: return
            author = r["author"][0].get("display", "Unknown")
            
            for content in r.get("content", []):
                att = content["attachment"]
                if "html" not in att.get("contentType", "").lower():
                    c_type = att["contentType"]
                    async with semaphore:
                        note_resp = await client.get(f"{ApiBase}/{att['url']}", headers={"Authorization": f"Bearer {Token}", "Accept": c_type})
                        fname = clean_filename(f"Note-{author}-{r.get('date')}.{c_type.split('/')[-1]}")
                        with open(fname, "wb") as f:
                            f.write(note_resp.content)

        await asyncio.gather(*[download_note(d) for d in RefDoc])

    # 8. Zip and Send
    ZIPFILE = "EHR.zip"
    with zipfile.ZipFile(ZIPFILE, "w") as zf:
        for folder, _, files in os.walk(TmpDir):
            for f in files:
                if f != ZIPFILE:
                    zf.write(os.path.join(folder, f), f, compress_type=zipfile.ZIP_DEFLATED)
    
    with open(ZIPFILE, "rb") as f:
        zip_raw = f.read()

    os.chdir(OldDir)
    shutil.rmtree(TmpDir)
    sys.stdout.buffer.write(zip_raw)

if __name__ == "__main__":
    asyncio.run(main())
