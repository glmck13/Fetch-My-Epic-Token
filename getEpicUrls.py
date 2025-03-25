#!/usr/bin/env python3

import sys, os, json, requests

#rsp = json.loads(sys.stdin.read())
rsp = requests.get("https://open.epic.com/Endpoints/Brands").json()

print('<select class="half" id="mychart">')
print('<option value="">-- Select Epic/MyChart Provider --</option>')
print('<option value="https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4/">Epic Sandbox</option>')

options = {}
for ep in rsp["entry"]:
	ep = ep["resource"]
	if ep["resourceType"] == "Endpoint":
		options[ep["address"]] = ep["name"]

for tup in sorted(options.items(), key=lambda kv: kv[1]):
	print('<option value="{}">{}</option>'.format(tup[0], tup[1]))
	
print('</select>')
