#!/usr/bin/env python3

import sys, os, requests

rsp = requests.get("https://open.epic.com/Endpoints/R4").json()

print('<select class="half" id="mychart">')
print('<option value="">-- Select Epic/MyChart Provider --</option>')

options = {}
for ep in rsp["entry"]:
	ep = ep["resource"]
	options[ep["address"]] = ep["name"]

for tup in sorted(options.items(), key=lambda kv: kv[1]):
	print('<option value="{}">{}</option>'.format(tup[0], tup[1]))
	
print('</select>')
