#!/bin/bash

echo "Copy 'GetOrganizations' cURL API call, then hit enter when ready..."
read x

wl-paste -t text/plain | xargs -0 printf '%b' >curl.sh
COOKIES=$(grep '^  *-b ' curl.sh) COOKIES=${COOKIES#*-b $\'} COOKIES=${COOKIES%? *}
export COOKIES
TOKEN=$(grep '^  -H .__requestverificationtoken' curl.sh) TOKEN=${TOKEN#*-H *: } TOKEN=${TOKEN%? *}
export TOKEN

./${0%.*}.py
./msgcsv.py
