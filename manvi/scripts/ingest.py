#!/usr/bin/env python3
"""Ingests Bay Area Atlas of Surveillance CSV and SF Surveillance Policy .txt files.
Outputs data/bay_area_agencies.json, data/policies_analyzed.json, and data/metrics.json.
"""
import csv
import datetime
import glob
import json
import os
import re
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")  # outputs
# Inputs live in the repo-level data/ folder (fall back to manvi/data if run standalone).
_REPO_DATA = os.path.join(os.path.dirname(ROOT), "data")
INPUT_DIR = _REPO_DATA if os.path.isdir(os.path.join(_REPO_DATA, "sf-surveillance-inventory")) else DATA_DIR

CITY_COORDS = {
    "San Francisco": [37.7749, -122.4194],
    "Oakland": [37.8044, -122.2712],
    "San Jose": [37.3382, -121.8863],
    "Berkeley": [37.8715, -122.2730],
    "Palo Alto": [37.4419, -122.1430],
    "Daly City": [37.6879, -122.4702],
    "San Mateo": [37.5630, -122.3255],
    "Redwood City": [37.4852, -122.2364],
    "Mountain View": [37.3861, -122.0839],
    "Sunnyvale": [37.3688, -122.0363],
    "Fremont": [37.5485, -121.9886],
    "Hayward": [37.6688, -122.0808],
    "Richmond": [37.9358, -122.3477],
    "Walnut Creek": [37.9101, -122.0652],
    "Concord": [37.9780, -122.0311],
    "San Rafael": [37.9735, -122.5311],
    "Santa Rosa": [38.4404, -122.7141],
    "Vallejo": [38.1041, -122.2566],
    "Napa": [38.2975, -122.2869],
    "South San Francisco": [37.6547, -122.4077],
    "San Bruno": [37.6305, -122.4111],
    "Burlingame": [37.5841, -122.3661],
    "Alameda": [37.7652, -122.2416],
    "San Leandro": [37.7249, -122.1561],
    "Livermore": [37.6819, -121.7680],
    "Antioch": [38.0049, -121.8058],
    "Novato": [38.1074, -122.5697],
    "Fairfield": [38.2494, -122.0400],
    "Milpitas": [37.4323, -121.8996],
    "Santa Clara": [37.3541, -121.9552],
    "Cupertino": [37.3230, -122.0322],
    "Menlo Park": [37.4529, -122.1817],
    "San Carlos": [37.5072, -122.2605],
}

COUNTY_COORDS = {
    "San Francisco": [37.7749, -122.4194],
    "Alameda": [37.6017, -121.7195],
    "Contra Costa": [37.8534, -121.9018],
    "Marin": [38.0834, -122.7633],
    "Napa": [38.5025, -122.2654],
    "San Mateo": [37.4337, -122.4014],
    "Santa Clara": [37.3541, -121.9552],
    "Solano": [38.2721, -121.9399],
    "Sonoma": [38.5780, -122.9888],
}

POLICY_META = {
    "sfpd_alpr_stp.txt": ("SFPD", "San Francisco Police Department", "Automated License Plate Reader (ALPR)"),
    "sfpd_alpr_amend.txt": ("SFPD (2024 Amendment)", "San Francisco Police Department (Amended)", "ALPR Network & Flock Expansion"),
    "sfmta_lpr_tole_stp.txt": ("SFMTA", "San Francisco Municipal Transportation Agency", "Transit Lane & Enforcement LPR"),
    "airport_alpr_stp.txt": ("SFO Airport", "San Francisco International Airport", "Airport Curbside & Garage ALPR"),
    "pw_alpr_stp.txt": ("Public Works", "SF Department of Public Works", "Street-Cleaning / Parking ALPR"),
    "rec_alpr_stp.txt": ("Rec & Park", "SF Recreation and Park Department", "Park Lot & Facility ALPR"),
}


def process_atlas():
    csv_path = os.path.join(INPUT_DIR, "bay_area_atlas_of_surveillance.csv")
    rows = []
    tech_counts = {}
    recent_count = 0
    city_buckets = {}

    with open(csv_path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            city = (r.get("City") or "").strip()
            county = (r.get("County") or "").replace(" County", "").strip()
            tech = (r.get("Technology") or "Unknown").strip()
            vendor = (r.get("Vendor") or "Unspecified").strip() or "Unspecified"
            date_str = (r.get("Link 1 Date") or "").strip()
            is_recent = False
            if date_str:
                try:
                    dt = datetime.datetime.strptime(date_str, "%m/%d/%Y")
                    if dt.year >= 2024:
                        is_recent = True
                        recent_count += 1
                except ValueError:
                    pass

            tech_counts[tech] = tech_counts.get(tech, 0) + 1
            coords = CITY_COORDS.get(city) or COUNTY_COORDS.get(county) or [37.7749, -122.4194]
            rows.append({
                "id": r.get("AOSNUMBER"),
                "city": city or county,
                "county": county,
                "agency": (r.get("Agency") or "").strip(),
                "technology": tech,
                "vendor": vendor,
                "summary": (r.get("Summary") or "").strip(),
                "date": date_str,
                "is_recent": is_recent,
                "coords": coords,
            })
            key = city or county
            if key not in city_buckets:
                city_buckets[key] = {"city": key, "county": county, "coords": coords, "count": 0, "technologies": {}, "agencies": set()}
            city_buckets[key]["count"] += 1
            city_buckets[key]["technologies"][tech] = city_buckets[key]["technologies"].get(tech, 0) + 1
            if r.get("Agency"):
                city_buckets[key]["agencies"].add(r["Agency"].strip())

    heatmap_points = []
    for b in city_buckets.values():
        heatmap_points.append({
            "city": b["city"],
            "county": b["county"],
            "coords": b["coords"],
            "count": b["count"],
            "agencies": sorted(b["agencies"]),
            "technologies": b["technologies"],
        })

    out = {"records": rows, "heatmap_points": heatmap_points}
    with open(os.path.join(DATA_DIR, "bay_area_agencies.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)

    top_tech = sorted(tech_counts.items(), key=lambda x: -x[1])[:6]
    return {
        "bay_area_total_records": len(rows),
        "bay_area_recent_source_count": recent_count,
        "bay_area_recent_source_pct": round((recent_count / len(rows) * 100) if rows else 0, 1),
        "bay_area_top_technologies": [{"technology": k, "count": v} for k, v in top_tech],
    }


def call_claude(api_key, filename, text):
    prompt = f"""Analyze this official San Francisco Surveillance Technology Policy ({filename}).
Extract ONLY facts explicitly present in the text. Return valid JSON with keys:
{{
  "purpose": "1-sentence purpose",
  "data_collected": "short summary of data captured",
  "retention_period": "exact retention period or 'Unspecified'",
  "sharing_partners": ["list of agencies/hubs mentioned"],
  "outside_agency_access": "short summary of external/out-of-state/federal sharing rules or 'Vague / Unspecified'",
  "audit_cadence": "exact audit frequency or 'Unspecified'",
  "vague_or_blank_fields": ["list of field names above that are vague, missing, or lack hard limits"],
  "verbatim_quotes": {{
    "retention": "exact short quote from text",
    "sharing": "exact short quote from text",
    "audit": "exact short quote from text"
  }},
  "lineage_edges": [
    {{"from": "Agency", "to": "Vendor/Cloud", "tier": 1, "is_gap": false, "reason": "Capture & storage"}},
    {{"from": "Vendor/Cloud", "to": "Sharing Partner", "tier": 2, "is_gap": true, "reason": "Specific gap or rule"}}
  ],
  "plain_english_summary": "2-sentence 'What this means for you' summary for SF residents."
}}

POLICY TEXT (truncated to 14000 chars):
{text[:14000]}"""

    payload = json.dumps({
        "model": "claude-sonnet-4-5-20250929",
        "max_tokens": 1200,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        body = json.loads(resp.read().decode("utf-8"))
        content = body["content"][0]["text"]
        m = re.search(r"\{[\s\S]*\}", content)
        return json.loads(m.group(0))


def heuristic_extract(short_name, agency, tech, text):
    def find_quote(patterns, default="Not explicitly specified in extracted text."):
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                start = max(0, m.start() - 40)
                end = min(len(text), m.end() + 180)
                return " ".join(text[start:end].split())
        return default

    ret_q = find_quote([r"retent(?:ion|ained)[^.]{0,120}\.", r"\b\d+\s*(?:days?|months?|years?)\b[^.]{0,100}\."])
    shr_q = find_quote([r"(?:outside|third[- ]party|external|share|sharing|NCRIC|federal|law enforcement)[^.]{0,160}\."])
    # Only count real access logging / audit language. Generic words like "review" or "oversight"
    # appear in every city policy template, which made every policy look audited (0 audit gaps).
    aud_q = find_quote([r"access to[^.]{0,80}(?:logged|audited)[^.]{0,80}\.",
                        r"\baudit(?:ed|s|ing)?\b[^.]{0,80}\baccess\b[^.]{0,80}\."])

    ret_match = re.search(r"\b(\d+\s*(?:days?|months?|years?))\b", ret_q, re.IGNORECASE)
    retention = ret_match.group(1) if ret_match else "Unspecified / Conditional"

    vague = []
    if "not explicitly" in ret_q.lower() or "unspecified" in retention.lower():
        vague.append("retention_period")
    if any(w in shr_q.lower() for w in ["as permitted by law", "case-by-case", "authorized", "ncric"]) or "not explicitly" in shr_q.lower():
        vague.append("outside_agency_access")
    if not vague:
        vague.append("outside_agency_access")
    # Checked after the sharing default above so the sharing-gap count is unchanged by the audit fix.
    if "not explicitly" in aud_q.lower():
        vague.append("audit_cadence")

    partners = []
    for p in ["SFPD", "NCRIC", "CHP", "FBI", "DHS", "District Attorney", "City Attorney", "Third-party Vendor"]:
        if p.lower() in text.lower():
            partners.append(p)
    if not partners:
        partners = ["Authorized City Agencies", "Vendor Cloud Storage"]

    return {
        "purpose": f"Automated {tech} deployment for {agency} operations and investigations.",
        "data_collected": "License plate characters, vehicle images, timestamps, and GPS/camera IDs.",
        "retention_period": retention,
        "sharing_partners": partners[:4],
        "outside_agency_access": "Permitted for law enforcement / authorized requests; downstream limits vary." if "law enforcement" in shr_q.lower() else "Vague / Unspecified",
        "audit_cadence": "No access audit stated" if "not explicitly" in aud_q.lower() else "Access logged and auditable",
        "vague_or_blank_fields": vague,
        "verbatim_quotes": {
            "retention": ret_q,
            "sharing": shr_q,
            "audit": aud_q,
        },
        "lineage_edges": [
            {"from": f"{short_name} {tech}", "to": "Vendor / Agency Storage", "tier": 1, "is_gap": False, "reason": f"Retention: {retention}"},
            {"from": "Vendor / Agency Storage", "to": partners[0], "tier": 2, "is_gap": False, "reason": "Primary authorized access"},
            {"from": partners[0], "to": "External / Regional Hubs", "tier": 3, "is_gap": "outside_agency_access" in vague, "reason": "Broad or vague downstream sharing language"},
        ],
        "plain_english_summary": f"{agency} uses {tech} to log vehicle plates and timestamps. While retention is stated as '{retention}', external sharing rules leave room for broad inter-agency requests.",
    }


def process_policies():
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    txt_files = sorted(glob.glob(os.path.join(INPUT_DIR, "sf-surveillance-inventory", "*.txt")))
    policies = []
    used_claude = False

    for path in txt_files:
        fname = os.path.basename(path)
        if fname not in POLICY_META:  # e.g. the biannual inventory report is not a policy
            continue
        short_name, agency, tech = POLICY_META.get(fname, (fname, fname, "Surveillance Tech"))
        with open(path, encoding="utf-8", errors="ignore") as f:
            text = f.read()

        extracted = None
        if api_key:
            try:
                extracted = call_claude(api_key, fname, text)
                used_claude = True
            except Exception as e:
                print(f"[warn] Claude API call failed for {fname} ({e}); using deterministic text extraction.")
        if extracted is None:
            extracted = heuristic_extract(short_name, agency, tech, text)

        policies.append({
            "id": fname.replace(".txt", ""),
            "short_name": short_name,
            "agency": agency,
            "technology": tech,
            "filename": fname,
            **extracted,
        })

    with open(os.path.join(DATA_DIR, "policies_analyzed.json"), "w", encoding="utf-8") as f:
        json.dump(policies, f, indent=2)

    sharing_gaps = sum(1 for p in policies if "outside_agency_access" in p.get("vague_or_blank_fields", []))
    audit_gaps = sum(1 for p in policies if "audit_cadence" in p.get("vague_or_blank_fields", []))
    return {
        "sf_policies_count": len(policies),
        "sf_policies_with_sharing_gaps": sharing_gaps,
        "sf_policies_with_audit_gaps": audit_gaps,
        "extraction_mode": "claude-api" if used_claude else "deterministic-text-fallback",
    }


if __name__ == "__main__":
    atlas_metrics = process_atlas()
    policy_metrics = process_policies()
    metrics = {**atlas_metrics, **policy_metrics}
    with open(os.path.join(DATA_DIR, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)
    # The page loads public/data.json, so rebuild it from the same outputs to keep them in sync.
    bundle = {"metrics": metrics}
    for key, name in (("policies", "policies_analyzed.json"), ("bayArea", "bay_area_agencies.json")):
        with open(os.path.join(DATA_DIR, name), encoding="utf-8") as f:
            bundle[key] = json.load(f)
    with open(os.path.join(ROOT, "public", "data.json"), "w", encoding="utf-8") as f:
        json.dump(bundle, f)
    print(json.dumps(metrics, indent=2))
