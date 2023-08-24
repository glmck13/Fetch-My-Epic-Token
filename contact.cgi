#!/bin/ksh

MAILTO="fetchmyepictoken@yahoo.com"
QUERY_STRING=$(cat -)

print "Content-Type: text/html\n"

for x in ${QUERY_STRING//\&/ }
do
    key=${x%%=*} val=${x#*=}
    val=$(urlencode -d "$val" | sed -e 's/\$/\\\\\\&/g')
    eval $key=\"$val\"
done

sendaway.sh "${MAILTO}" "User contact from Fetch My Epic Token" "Contact: ${Contact}\rEmail: ${Email}\r\r${Note}"

cat header.html
cat - <<EOF
<p>I'll review your message and get back to you shortly.  Thanks for using Fetch My Epic Token!</p>
EOF
cat footer.html
