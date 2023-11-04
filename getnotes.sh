#!/bin/ksh

TMPFILE=clinnotes.json

curl -s -H "Authorization: Bearer ${OAUTH_TOKEN}" -H "Accept: application/json+fhir" "$APIBASE/DocumentReference?patient=$PATIENT&category=clinical-note" >$TMPFILE

python3 <<EOF | while IFS='|' read when who where what
import sys, os, json

docref = json.loads(open("$TMPFILE").read())

for x in docref["entry"]:
	x = x["resource"]
	if x["resourceType"] != "DocumentReference":
		continue
	when = x["date"]
	if "author" not in x:
		continue
	who = x["author"][0]["display"]
	for y in x["content"]:
		y = y["attachment"]
		where = y["url"]
		what = y["contentType"]
		if "html" in what:
			continue
		print('{}|{}|{}|{}'.format(when, who, where, what))
EOF
do
echo $when $who
when=${when//:/-} who=${who//,/} who=${who// /_}
curl -s -H "Authorization: Bearer ${OAUTH_TOKEN}" -H "Accept: ${what}" "${APIBASE}/${where}" >${who}-${when}.bin
done

rm -f $TMPFILE
