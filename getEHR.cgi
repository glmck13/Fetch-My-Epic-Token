#!/usr/bin/env python3

import sys, os, json
import requests
from urllib.parse import parse_qs
from tempfile import mkdtemp
import zipfile
import shutil

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
	for c in ":',/ ":
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
	Encntr = requests.get(ApiBase + "/Encounter?patient=" + Patient, headers=Headers).json()["entry"]
	Shots = requests.get(ApiBase + "/Immunization?patient=" + Patient, headers=Headers).json()["entry"]
	VitalOb = requests.get(ApiBase + "/Observation?patient=" + Patient + "&category=vital-signs", headers=Headers).json()["entry"]
	LabOb = requests.get(ApiBase + "/Observation?patient=" + Patient + "&category=laboratory", headers=Headers).json()["entry"]
	DiagRpt = requests.get(ApiBase + "/DiagnosticReport?patient=" + Patient, headers=Headers).json()["entry"]
	RefDoc = requests.get(ApiBase + "/DocumentReference?patient=" + Patient + "&category=clinical-note", headers=Headers).json()["entry"]
except:
	exit()

def fmt_set (s):
	if s:
		return '"' + '","'.join(s) + '"'
	else:
		return ''

if len(Shots) > 0:
	with open("Immunizations.csv", "w") as f:
		f.write("When|What\n")
		for s in Shots:
			r = s["resource"]
			if r["resourceType"] != "Immunization":
				continue
			when = r.get("occurrenceDateTime", "")
			what = r.get("vaccineCode", {}).get("text", "")
			if when:
				f.write('{}|{}\n'.format(when, what))

if len(Encntr) > 0:
	with open("Visits.csv", "w") as f:
		f.write("When|What|Why|How|Who|Where\n")
		for e in Encntr:
			r = e["resource"]
			when = r.get("period", {}).get("start", "")
			what = r.get("class", {}).get("display", "")
			why = set()
			for x in r.get("reasonCode", []):
				y = x.get("text")
				if y:
					why.add(y)
			how = set()
			for x in r.get("type", []):
				y = x.get("text")
				if y:
					how.add(y)
			who = set()
			for x in r.get("participant", [{}]):
				y = x.get("individual", {}).get("display")
				if y:
					who.add(y)
			where = set()
			for x in r.get("location", [{}]):
				y = x.get("location", {}).get("display")
				if y:
					where.add(y)
			if when:
				f.write('{}|{}|{}|{}|{}|{}\n'.format(when, what, fmt_set(why), fmt_set(how), fmt_set(who), fmt_set(where)))

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
		if '/' in z and z not in LabObId:
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
	y = x["code"].get("text", "").lower()
	if "report" in y or "path" in y:
		DiagObRec.append(x)
	elif y:
		NewLabObRec.append(x)
LabObRec = NewLabObRec

if len(LabObRec) > 0 or len(VitalOb) > 0:
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
		for x in VitalOb:
			x = x["resource"]
			if x["resourceType"] != "Observation":
				continue
			order = x["category"][0]["text"]
			dt = x["effectiveDateTime"]
			test = x["code"]["text"]
			if x.get("valueQuantity"):
				value = x["valueQuantity"]["value"]
			elif x.get("component"):
				value = []
				for y in x.get("component"):
					if y.get("valueQuantity"):
						value.append(str(y["valueQuantity"]["value"]))
				value = ' / '.join(value)
			else:
				value = ""

			f.write('"{}","{}","{}","{}"\n'.format(order, dt, test, value))

for x in DiagObRec:
	for y in x["basedOn"]:
		order = y["display"]
	dt = x["effectiveDateTime"]
	test = x["code"]["text"]

	fname = "{}-{}-{}.txt".format(order, dt, test)
	for c in ":',/ ":
		fname = fname.replace(c, '_')
	with open(fname, "w") as f:
		f.write(x.get("valueString", ""))

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
	for c in ":',/ ":
		fname = fname.replace(c, '_')
	with open(fname, "wb") as f:
		f.write(Note)

#zip = subprocess.run(["zip", "-r", "-", "." ], capture_output=True)
ZIPFILE = "EHR.zip"
with zipfile.ZipFile(ZIPFILE, "w") as zf:
	for folder, sub_folders, files in os.walk(TmpDir):
		for fname in files:
			if fname == ZIPFILE:
				continue
			file_path = os.path.join(folder, fname)
			zf.write(file_path, os.path.basename(file_path), compress_type=zipfile.ZIP_DEFLATED)
with open(ZIPFILE, "rb") as f:
	zip_raw = f.read()

os.chdir(OldDir)
#subprocess.run(["rm", "-fr", TmpDir])
shutil.rmtree(TmpDir)

sys.stdout.buffer.write(zip_raw)
