#!/usr/bin/env python3

import sys, os, json
import requests
from urllib.parse import parse_qs
from tempfile import mkdtemp
import subprocess

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

if os.getenv("SCRIPT_FILENAME"):
	fname = "{}.zip".format(Organization)
	for c in "',/ ":
		fname = fname.replace(c, '_')
	print("Content-type: application/octet-stream")
	print("Content-Disposition: attachment; filename={}".format(fname))
	print()
	sys.stdout.flush()

TmpDir = mkdtemp()
OldDir = os.getcwd()
os.chdir(TmpDir)

Headers = {"Authorization" : "Bearer " + Token, "Accept" : "application/json+fhir"}

try:
    LabOb = requests.get(ApiBase + "/Observation?patient=" + Patient + "&category=laboratory", headers=Headers).json()["entry"]
    DiagRpt = requests.get(ApiBase + "/DiagnosticReport?patient=" + Patient, headers=Headers).json()["entry"]
    RefDoc = requests.get(ApiBase + "/DocumentReference?patient=" + Patient + "&category=clinical-note", headers=Headers).json()["entry"]
except:
    exit()

LabObRec = []
LabObId = set()
for x in LabOb:
	x = x["resource"]
	y = x["resourceType"]
	if y != "Observation":
		continue
	LabObId.add(y + '/' + x["id"])
	LabObRec.append(x)
del(LabOb)

DiagObId = []
for x in DiagRpt:
	x = x["resource"]
	y = x["resourceType"]
	if y != "DiagnosticReport":
		continue
	for y in x.get("result", []):
		z = y["reference"]
		if z not in LabObId:
			DiagObId.append(z)
del(DiagRpt)

DiagObRec = []
for x in DiagObId:
	y = requests.get(ApiBase + '/' + x, headers=Headers).json()
	toss = False
	for z in y["category"]:
		for w in z["coding"]:
			if w["code"] == "Lab":
				toss = True
	if not toss:
		DiagObRec.append(y)
del(LabObId)
del(DiagObId)

NewLabObRec = []
for x in LabObRec:
	y = x["code"]["text"].lower()
	if "report" in y or "path" in y:
		DiagObRec.append(x)
	else:
		NewLabObRec.append(x)
LabObRec = NewLabObRec

if len(LabObRec) > 0:
    with open("Labs.csv", "w") as f:
    	f.write('"Order","DateTime","Test","Value"\n')
    	for x in LabObRec:
    		order = x["basedOn"][0]["display"]
    		dt = x["effectiveDateTime"]
    		test = x["code"]["text"]
    		if x.get("valueQuantity"):
    			value = x["valueQuantity"]["value"]
    		elif x.get("valueString"):
    			value = x["valueString"].replace('"', "'")
    		else:
    			value = ""
    		f.write('"{}","{}","{}","{}"\n'.format(order, dt, test, value))

for x in DiagObRec:
	for y in x["basedOn"]:
		order = y["display"]
	dt = x["effectiveDateTime"]
	test = x["code"]["text"]

	fname = "{}-{}-{}.txt".format(order, dt, test)
	for c in "',/ ":
		fname = fname.replace(c, '_')
	with open(fname, "w") as f:
		f.write(x.get("valueString"))

for x in RefDoc:
	x = x["resource"]
	y = x["resourceType"]
	if y != "DocumentReference":
		continue
	if "author" not in x:
		continue

	for y in x["author"]:
		author = y["display"]

	url = ""
	for y in x["content"]:
		y = y["attachment"]
		contentType = y["contentType"].lower()
		if "html" not in contentType:
			url = y["url"]
	if not url:
		continue

	dt = x["date"]

	Headers["Accept"] = contentType

	Note = requests.get(ApiBase + "/" + url, headers=Headers).content

	fname = "Note-{}-{}.{}".format(author, dt, contentType.split('/')[1])
	for c in "',/ ":
		fname = fname.replace(c, '_')
	with open(fname, "wb") as f:
		f.write(Note)

zip = subprocess.run(["zip", "-r", "-", "." ], capture_output=True)

os.chdir(OldDir)
subprocess.run(["rm", "-fr", TmpDir])
sys.stdout.buffer.write(zip.stdout)
