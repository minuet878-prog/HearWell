"""Write each e2e test class's seconds into e2e/durations.json, for CI's shards (load_tests).

    py313/bin/python manage.py test --settings=config.test_settings e2e.main_flow \\
        --parallel 4 --durations 0 > e2e-durations.log
    py313/bin/python e2e/update_durations.py e2e-durations.log

Only how long the classes take next to each other matters, so a local run serves CI too. A class
missing from the file counts as the median one; rerun this after adding or growing classes.
"""

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

LINE = re.compile(r"^([\d.]+)s\s+\S+\s+\(e2e\.main_flow\.(\w+)\.\w+\)$")

seconds = defaultdict(float)
for line in Path(sys.argv[1]).read_text().splitlines():
    if match := LINE.match(line):
        seconds[match[2]] += float(match[1])
table = {name: round(total) for name, total in sorted(seconds.items())}
(Path(__file__).parent / "durations.json").write_text(json.dumps(table, indent=2) + "\n")
print(f"{len(table)} classes, {sum(table.values())} seconds")
