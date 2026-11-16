#!/bin/bash
# QC only (never committed): switch on the mocks the coding step left for APIs the backend has not shipped yet.
# Convention (prompts/ticket.md, docs/ai/mock-data.md): `const USE_MOCK = __DEV__; // MOCK(US-xxxx) ...`
# The QC app is a staging Release build (__DEV__ false), so flip those lines to `true` before bundling.
# Usage: qc-mock.sh   (cwd = app checkout)
files=$(git grep -l -E 'USE_MOCK[A-Z_]* = __DEV__;.*MOCK\((US|UTD|UOB)-[0-9]+' -- src 2>/dev/null)
[ -z "$files" ] && exit 0
for f in $files; do sed -i.bak -E 's/(USE_MOCK[A-Z_]* = )__DEV__;(.*MOCK\((US|UTD|UOB)-[0-9]+)/\1true;\2/' "$f" && rm -f "$f.bak"; done
echo "qc mock: on in $(wc -w <<<"$files" | tr -d ' ') file(s)" | tee -a ../ctx/mock.txt
