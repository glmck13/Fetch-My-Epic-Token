#!/bin/bash

# 1. Grab the cURL command from the clipboard
# We use printf %b to handle any escaped characters, similar to your original logic
RAW_CLIPBOARD=$(wl-paste -t text/plain | xargs -0 printf '%b')

if [ -z "$RAW_CLIPBOARD" ]; then
    echo "Error: Clipboard is empty. Please copy the cURL command first."
    exit 1
fi

# 2. Prepare the POST data
# The CGI script uses cgi.FieldStorage(), which expects application/x-www-form-urlencoded
# We prefix the content with the key name the script looks for
POST_DATA="clipboard_content=$(python3 -c "import urllib.parse, sys; print(urllib.parse.quote(sys.stdin.read()))" <<< "$RAW_CLIPBOARD")"

# 3. Calculate Content Length
CONTENT_LENGTH=${#POST_DATA}

# 4. Invoke the CGI script with the simulated Web Server environment
# REQUEST_METHOD: Tells the script to look for POST data
# CONTENT_TYPE: Necessary for cgi.FieldStorage to parse the stream
# CONTENT_LENGTH: Necessary for the script to know how much to read from stdin
export REQUEST_METHOD="POST"
export CONTENT_TYPE="application/x-www-form-urlencoded"
export CONTENT_LENGTH=$CONTENT_LENGTH

echo "--- Starting MyChart Bundle Extraction ---" >&2

# Pipe the data into the script. 
# The script will output HTTP headers followed by the transcript.
echo -n "$POST_DATA" | ./mychart_bundle.py
