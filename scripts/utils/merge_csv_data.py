import csv
import json
import os
from pathlib import Path

def merge_csvs():
    # Setup paths
    base_dir = Path(r"c:\Users\kanap\OneDrive\Documents\job_agent")
    data_dir = base_dir / "data"
    registry_path = base_dir / "config" / "company_registry.json"
    
    # Load existing registry
    with open(registry_path, "r", encoding="utf-8") as f:
        registry = json.load(f)
        
    csv_mappings = {
        "greenhouse_companies.csv": "greenhouse",
        "lever_companies.csv": "lever",
        "workday_companies.csv": "workday",
        "workable_companies.csv": "workable",
        "rippling_companies.csv": "rippling"
    }
    
    total_added = 0
    
    for filename, platform in csv_mappings.items():
        csv_path = data_dir / filename
        if not csv_path.exists():
            continue
            
        added_for_platform = 0
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                url = row.get("url", "").strip()
                name = row.get("name", "").strip()
                
                if not url or not name:
                    continue
                    
                # Extract slug from URL depending on platform
                slug = None
                if platform == "greenhouse":
                    # e.g https://job-boards.greenhouse.io/adobe -> adobe
                    parts = url.rstrip("/").split("/")
                    if parts:
                        slug = parts[-1]
                elif platform == "lever":
                    # e.g https://jobs.lever.co/kopi -> kopi
                    parts = url.rstrip("/").split("/")
                    if parts:
                        slug = parts[-1]
                elif platform == "workday":
                    # Keep full URL for Workday as per our ATS schema
                    slug = url
                elif platform == "workable":
                    # Keep full URL or piece it depending on our setup? 
                    # Right now we aren't officially tracking Workable, but we can add it as a new platform!
                    parts = url.rstrip("/").split("/")
                    if parts:
                        slug = parts[-1]
                elif platform == "rippling":
                    # https://ats.rippling.com/{slug}/jobs
                    try:
                        slug = url.split("ats.rippling.com/")[1].split("/jobs")[0]
                    except IndexError:
                        pass
                
                if not slug:
                    continue
                    
                # Ensure the platform list exists
                if platform not in registry:
                    registry[platform] = []
                    
                # Check if it already exists to avoid duplicates
                exists = any(c.get("name") == name or c.get("url", c.get("slug")) == slug for c in registry[platform])
                
                if not exists:
                    if platform == "workday":
                        registry[platform].append({"name": name, "url": slug})
                    else:
                        registry[platform].append({"name": name, "slug": slug})
                    added_for_platform += 1
                    total_added += 1
                    
        print(f"Added {added_for_platform} new companies for {platform}")
        
    print(f"Total new companies added across all platforms: {total_added}")
    
    # Save back
    with open(registry_path, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=4)
        print("Updated company_registry.json")

if __name__ == "__main__":
    merge_csvs()
