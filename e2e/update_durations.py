"""Write each e2e test class's seconds into e2e/durations.json, for CI's shards (load_tests).

CI's e2e step lists every test's seconds (--durations 0); take them from a passing run:

    gh run view <run id> --log > e2e-durations.log
    py313/bin/python e2e/update_durations.py e2e-durations.log

Use CI's, not a local run's: some classes are far slower there (WhiteCardRuleTest 2.5 times).
A class missing from the file counts as the median one; rerun this after adding or growing
classes.
"""

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

# CI's log puts the job name and a timestamp before each line.
LINE = re.compile(r"([\d.]+)s\s+\S+\s+\(e2e\.main_flow\.(\w+)\.\w+\)$")

seconds = defaultdict(float)
for line in Path(sys.argv[1]).read_text().splitlines():
    if match := LINE.search(line):
        seconds[match[2]] += float(match[1])
table = {name: round(total) for name, total in sorted(seconds.items())}
(Path(__file__).parent / "durations.json").write_text(json.dumps(table, indent=2) + "\n")
print(f"{len(table)} classes, {sum(table.values())} seconds")
