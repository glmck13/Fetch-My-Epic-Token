#!/bin/bash

echo "Copy 'GetOrganizations' cURL API call, then hit enter when ready..."
read x

wl-paste -t text/plain | xargs -0 printf '%b' >curl.sh
BASE_URL=$(grep '^curl' curl.sh) BASE_URL=${BASE_URL#*\'} BASE_URL=${BASE_URL%/*}
export BASE_URL
COOKIES=$(grep '^ *-b ' curl.sh) COOKIES=${COOKIES#*\'} COOKIES=${COOKIES%? *}
export COOKIES
TOKEN=$(grep -i '__RequestVerificationToken:' curl.sh) TOKEN=${TOKEN#*: } TOKEN=${TOKEN%? *}
export TOKEN

./messages.py
./hydrate.py
