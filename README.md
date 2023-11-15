# FetchMyEpicToken
I’m guessing many of you have logins to an EHR (Electronic Health Record) platform developed by Epic called “MyChart”.  Although  MyChart has tons of features, there may be times when you’d like to access your data directly from a script without having to go through a web portal (at least I would!)  It just so happens that EHR providers are required by law to provide API access to their platforms using a standard called FHIR, and do so free-of-charge, at least for a subset of the calls.  
  
This app enables patients to login to any Epic/MyChart production system in order to obtain access tokens for making FHIR API calls. The tokens can then be used within scripts to process Epic health data using the FHIR API. Scripts can be authored in a variety of languages, including bash/curl, Python, Javascript, etc. – essentially any language that provides methods for making REST-based API calls. A live version of the app is running here: [https://fetch-my-epic-token.org](https://fetch-my-epic-token.org).  You can find basic instructions for writing scripts as well as simple script examples on the HowTo page.

## References
+ https://github.com/pftechsln/pftechsln.github.io
