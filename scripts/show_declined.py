import json
from pathlib import Path

output_dir = Path("output")
for json_path in sorted(output_dir.glob("*.json")):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not data.get("payables"):
        reason = data.get("declined", [{}])[0].get("reason", "N/A")
        print(f"{json_path.name:20} | {reason}")
