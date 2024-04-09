#!/usr/bin/env python3

import urllib.request
import json

request = urllib.request.Request("https://github.com/mongodb/snooty-parser/releases/latest", headers={"Accept": "application/json"})
with urllib.request.urlopen(request) as f:
    tag_name = json.loads(f.read())["tag_name"]

print(f"https://github.com/mongodb/snooty-parser/releases/download/{tag_name}/snooty-{tag_name}-linux_x86_64.zip")
