import os
import sys
from collections import defaultdict
from pathlib import Path

# Add project root to sys path to import jobclaw modules
PROJECT_ROOT = Path(r"c:\Users\kanap\OneDrive\Documents\job_agent")
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from scripts.ingestion.scrape_ats import load_registry
    registry = load_registry() or []
except Exception as e:
    registry = []
    print(f"Error loading registry: {e}")

ats_groups = defaultdict(list)
for r in registry:
    ats = r.get("ats", "unknown")
    company = r.get("company", "Unknown Company")
    ats_groups[ats].append(company)

# Sort ATS by number of companies descending
sorted_ats = sorted(ats_groups.items(), key=lambda x: len(x[1]), reverse=True)

md_content = "# ATS Company Breakdown\n\n"
md_content += f"**Total Companies in Registry:** {len(registry)}\n\n"

for ats, companies in sorted_ats:
    companies_sorted = sorted(companies)
    md_content += f"## {ats.title()} ({len(companies)} companies)\n"
    
    # We use a details block to prevent the markdown file from being too overwhelmingly long
    md_content += "<details>\n<summary>Click to view all companies</summary>\n\n"
    
    # Create a comma-separated list of companies for dense but readable formatting
    md_content += ", ".join(companies_sorted) + "\n"
    
    md_content += "\n</details>\n\n"

out_path = Path(r"C:\Users\kanap\.gemini\antigravity\brain\0645d642-db97-46a3-adc9-0b24369605a4\ats_companies_list.md")
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(md_content, encoding="utf-8")
print(f"Artifact written to {out_path} with {len(registry)} companies.")
