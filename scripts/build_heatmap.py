#!/usr/bin/env python3
"""Build heatmap.html: SF license-plate-reader policies, policy vs promise.

Cells were filled by reading each policy's extracted text. This script refuses
to publish a cell whose quote is not found verbatim (whitespace-normalized) in
the source file, and reports the page it was found on.

Run:  python3 scripts/build_heatmap.py   then open heatmap.html
"""
import html, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "sf-surveillance-inventory"

POLICIES = [
    ("SFPD", "Police Department", "sfpd_alpr_amend", "pdf"),
    ("Airport", "SFO Airport", "airport_alpr_stp", "html"),
    ("SFMTA", "Municipal Transportation Agency", "sfmta_lpr_tole_stp", "pdf"),
    ("Public Works", "Department of Public Works", "pw_alpr_stp", "pdf"),
    ("Rec & Park", "Recreation and Park Department", "rec_alpr_stp", "pdf"),
]

COLUMNS = [
    ("retention", "Retention period", "Does it state how long plate data is kept?"),
    ("justification", "Retention tied to purpose", "The promise: keep PII only as long as strictly necessary for the purpose. Is the stated reason about the purpose?"),
    ("recipients", "Names who gets the data", "Does it name the outside recipients, or use open-ended categories?"),
    ("federal", "Federal / out-of-state ban written in", "Does the policy itself say plate data won't go to federal or out-of-state agencies?"),
    ("statelaw", "Cites CA plate-reader law", "Does it reference Civil Code 1798.90.5 et seq. (California's ALPR law)?"),
    ("audit", "Access logging / audit", "Does it say access is logged or audited?"),
]

# level: ok | vague | missing.  quote must appear verbatim in the source text.
# For "missing", quote is None and note says what was searched.
CELLS = {
    "SFPD": {
        "retention": ("ok", "12 months; 5 years if tied to an investigation",
                      "SFPD defers to the NCRIC retention standard: ALPR records are maintained for 12 months from capture."),
        "justification": ("vague", "Defers to NCRIC (regional intelligence center) standard; no purpose-based reason of its own",
                          "SFPD defers to the NCRIC retention standard"),
        "recipients": ("vague", "DA, Public Defender, and “NCRIC law enforcement partners” (open-ended)",
                       "Parties to civil litigation, or other third parties, in response to a valid Court Order."),
        "federal": ("ok", "Yes, explicit ban without a California court order",
                    "ALPR information shall not be sold, shared, or transferred to out-of-state or federal agencies without a court order or warrant issued by a California court."),
        "statelaw": ("ok", "Yes", "SFPD shall not sell, share, or transfer ALPR information, except to another public agency, and only as otherwise permitted by California state law."),
        "audit": ("missing", "No mention of logging or audit found", None),
    },
    "Airport": {
        "retention": ("ok", "18 months on server, then 4.5 years in cloud (~6 years total)",
                      "Data is active for 18 months in the production server, then 4.5 years in cloud storage."),
        "justification": ("missing", "Justified by a records schedule and server size, not by the purpose",
                          "Airport server storage size limits retention on production server. Airport Data Retention Policy requires 4.5 years."),
        "recipients": ("vague", "Includes “law enforcement agencies” and “other third parties when required under law”",
                       "law enforcement agencies as part of a criminal or administrative investigation; Parties to civil litigation, or other third parties when required under law."),
        "federal": ("missing", "Not found; purpose statement mentions supporting federal departments", None),
        "statelaw": ("ok", "Yes (public-notice requirement)",
                     "in compliance with California Civil Code § 1798.90.5, the Airport shall notify the public"),
        "audit": ("missing", "No mention of logging or audit found", None),
    },
    "SFMTA": {
        "retention": ("ok", "Varies by use: 14 days citations, 60 days garage images, 2 years garage data",
                      "Parking garage data is stored 2 years for auditing"),
        "justification": ("ok", "Each period tied to a use (e.g. 72-hour parking rule, CHP state limit)",
                          "consistent with maximum period the California"),
        "recipients": ("vague", "“other government entities, contractors, vendors” (examples, not a list)",
                       "with entities outside the City (e.g., other government entities, contractors, vendors)."),
        "federal": ("missing", "Not found", None),
        "statelaw": ("ok", "Yes", "This Policy complies with the requirements for the collection of license plate information set forth in Civil Code section 1798.90.5 et seq)"),
        "audit": ("ok", "Yes, all access logged",
                  "All access to and activity in the ALPR system is logged and can be audited."),
    },
    "Public Works": {
        "retention": ("ok", "Maximum 30 days, automatic overwrite",
                      "Automatic overwrite after 30 days"),
        "justification": ("ok", "Tied to purpose: identify illegal dumpers",
                          "Only need it long enough to confirm responsible parties"),
        "recipients": ("ok", "SFPD and the District Attorney",
                       "Public Works may share data with SFPD and the District Attorney to pursue criminal charges."),
        "federal": ("missing", "Not found", None),
        "statelaw": ("missing", "Not found", None),
        "audit": ("missing", "No mention of logging or audit found", None),
    },
    "Rec & Park": {
        "retention": ("vague", "30–60 days, depending on hardware capacity",
                      "ALPR video files will be retained for 30-60 days (depending upon the hardware capacity)."),
        "justification": ("missing", "Set by disk capacity, not by purpose",
                          "(depending upon the hardware capacity)"),
        "recipients": ("vague", "Says no sharing inside the City; silent on outside entities, yet frequency is “upon request”",
                       "The department does not share surveillance technology data with other departments or entities inside the City and County of San Francisco."),
        "federal": ("missing", "Not found", None),
        "statelaw": ("missing", "Not found", None),
        "audit": ("missing", "No mention of logging or audit found", None),
    },
}

SOURCE_URLS = {
    "sfpd_alpr_amend": "https://www.sf.gov/documents/55994/Surveillance_Tech_Policy_Amend.pdf",
    "airport_alpr_stp": "https://www.sf.gov/airport-automated-license-plate-readers-surveillance-technology-policy",
    "sfmta_lpr_tole_stp": "https://sfgov.legistar.com/View.ashx?M=F&ID=11065541&GUID=A886AD5F-639A-48C9-9D6D-DE2B9D50E6C1",
    "pw_alpr_stp": "https://www.sf.gov/sites/default/files/2021-02/PW_Surveillance%20Technology%20Policy_ALPR_FINAL_0.pdf",
    "rec_alpr_stp": "https://www.sf.gov/sites/default/files/2022-03/REC_Surveillance%20Technology%20Ordinance_ALPR_Policy_COIT.pdf",
}

# ---- Practice layer: what each department told the city it actually did in 2024 ----
# Source: each department's ALPR Annual Surveillance Report 2024 (filed Oct 2024), in data/annual-reports/.
REPORTS = Path(ROOT / "data" / "annual-reports")
PRACTICE_SOURCES = {
    "SFPD": ("sfpd_alpr_annual_2024", "https://api.sf.gov/documents/33376/POL_Automated_License_Plate_Reader_ALPR_Annual_Surveillance_Report_2024.pdf"),
    "Airport": ("airport_alpr_annual_2024", "https://sf.gov/sites/default/files/2024-10/AIR%20ALPR%20Annual%20Surveillance%20Report%202024.pdf"),
    "SFMTA": ("sfmta_alpr_annual_2024", "https://sf.gov/sites/default/files/2024-10/MTA%20Automated%20License%20Plate%20Reader%20%28ALPR%29%20Annual%20Surveillance%20Report%202024.pdf"),
    "Public Works": ("pw_alpr_annual_2024", "https://sf.gov/sites/default/files/2024-10/DPW%20Automated%20License%20Plate%20Reader%20%28ALPR%29%20Annual%20Surveillance%20Report%202024.pdf"),
    "Rec & Park": ("rec_alpr_annual_2024", "https://sf.gov/sites/default/files/2024-10/REC%20Automated%20License%20Plate%20Reader%20%28ALPR%29%20Annual%20Surveillance%20Report%202024.pdf"),
}

PRACTICE_COLUMNS = [
    ("shared", "Shared outside the department", "Did plate data go to anyone outside the department in 2024?"),
    ("audit", "Internal audit in 2024", "Did the department check its own use of the system?"),
    ("violations", "Violations found", "Did the department report any broken rules?"),
    ("works", "Says it worked", "Did the department say the cameras did their job?"),
]

Q_SHARED_NO = "Has data acquired through the surveillance technology been shared with entities outside of the department? No"
Q_AUDIT_NO = "Has your department conducted any internal audits of the technology? No"
Q_VIOL_NO = ("Were there any violations of the Surveillance Technology Policy or Surveillance Impact Report, reported through "
             "community members, non-privileged internal audits, or through other means in the last year? No")
VIOL_UNCHECKED = "None reported, but no internal audit was done to find any"

PRACTICE = {
    "SFPD": {
        "shared": ("vague", "Yes: the District Attorney plus about 200 law enforcement agencies across California",
                   "the department shared digital images of vehicle license plates and their associated vehicles and the date and time the license plate passed a digital image site where an ALPR is located with the following law enforcement agencies"),
        "audit": ("missing", "No internal audit", Q_AUDIT_NO),
        "violations": ("vague", VIOL_UNCHECKED, Q_VIOL_NO),
        "works": ("ok", "Yes: credits the cameras with arrests", "The department’s ALRP cameras are already delivering significant results"),
    },
    "Airport": {
        "shared": ("vague", "Yes: SFPD Airport Bureau, San Mateo County Sheriff, and the state utilities regulator (CPUC). The policy names neither of the last two.",
                   "The California Public Utilities Commission (CPUC) receives surveillance technology data from the Airport."),
        "audit": ("missing", "No internal audit", Q_AUDIT_NO),
        "violations": ("vague", VIOL_UNCHECKED, Q_VIOL_NO),
        "works": ("ok", "Yes", "Has the surveillance technology been eﬀective at achieving its identified purpose? Yes"),
    },
    "SFMTA": {
        "shared": ("ok", "No", Q_SHARED_NO),
        "audit": ("ok", "Yes, internal audits done", "Has your department conducted any internal audits of the technology? Yes"),
        "violations": ("ok", "None, after an internal audit", "No violations of data were found as a result of our department's internal audits."),
        "works": ("ok", "Yes", "Has the surveillance technology been effective at achieving its identified purpose? Yes"),
    },
    "Public Works": {
        "shared": ("ok", "No", Q_SHARED_NO),
        "audit": ("missing", "No internal audit", Q_AUDIT_NO),
        "violations": ("vague", VIOL_UNCHECKED, Q_VIOL_NO),
        "works": ("vague", "Can't say yet: the first cameras went up on October 29, 2024",
                  "Public Works cannot make a determination regarding the success of this program or not, since we have been delayed in the implementation of cameras outlined in this policy"),
    },
    "Rec & Park": {
        "shared": ("ok", "No", Q_SHARED_NO),
        "audit": ("missing", "No internal audit", Q_AUDIT_NO),
        "violations": ("vague", VIOL_UNCHECKED, Q_VIOL_NO),
        "works": ("ok", "Yes", "Has the surveillance technology been effective at achieving its identified purpose? Yes"),
    },
}

MISSING_SEARCH = {
    "federal": "searched for “federal agenc”, “out-of-state”",
    "statelaw": "searched for “1798.90”",
    "audit": "searched for “audit”",
}

# Appendix D of COIT Biannual Inventory Report, Sept 1 2026 (p. 9-10).
NO_POLICY = {
    "Police Department": ["Audio Recorders on Surveillance Van", "Hostage Negotiation Throw Phone", "Cogent ABIS (biometric ID)",
        "DataWorksPlus Digital Crime Scene", "DataWorksPlus Digital Photo Manager", "Microblink Software",
        "CommPort Tech (Under Vehicle Camera)", "Fiber Optic Camera", "IP Cameras", "Pole Camera",
        "Security Cameras (City Dept)", "SWAT Camera", "Tactical Electronics Fiber Scope", "Under Door Camera",
        "Under Vehicle Camera", "Vertmax Camera", "DVR Recorder", "Magnetic Forensics", "CellHawk", "Penlink"],
    "Municipal Transportation Agency": ["Data Feeds for Stationless Bicycles", "Electronic Taxi Access System"],
    "Multi-departmental (8 depts)": ["Public Wi-Fi Network"],
}


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


def pages_of(stem, kind, folder=DATA):
    raw = (folder / f"{stem}.txt").read_text(errors="replace")
    return [norm(p) for p in raw.split("\f")] if kind == "pdf" else [norm(raw)]


def locate(pages, quote):
    q = norm(quote)
    for i, p in enumerate(pages):
        if q in p:
            return f"p. {i + 1}"
    joined, starts, pos = "", [], 0
    for p in pages:
        starts.append(pos); joined += p + " "; pos = len(joined)
    j = joined.find(q)
    if j < 0:
        return None
    a = max(k for k, s in enumerate(starts) if s <= j)
    b = max(k for k, s in enumerate(starts) if s <= j + len(q))
    return f"pp. {a + 1}–{b + 1}"


def main():
    rows, failures, checked = [], [], 0
    for short, full, stem, kind in POLICIES:
        pages = pages_of(stem, kind)
        cells = []
        for key, _, _ in COLUMNS:
            level, summary, quote = CELLS[short][key]
            where = None
            if quote:
                checked += 1
                where = locate(pages, quote)
                if where is None:
                    failures.append(f"{short}/{key}: {quote[:70]}")
            if kind == "html" and where:
                where = "web page"
            cells.append({"key": key, "level": level, "summary": summary, "quote": quote,
                          "where": where, "searched": MISSING_SEARCH.get(key) if level == "missing" else None})
        rows.append({"short": short, "full": full, "file": SOURCE_URLS[stem], "fname": f"{stem}.{kind}", "cells": cells})

    prows = []
    for short, full, _, _ in POLICIES:
        stem, url = PRACTICE_SOURCES[short]
        pages = pages_of(stem, "pdf", REPORTS)
        cells = []
        for key, _, _ in PRACTICE_COLUMNS:
            level, summary, quote = PRACTICE[short][key]
            checked += 1
            where = locate(pages, quote)
            if where is None:
                failures.append(f"practice {short}/{key}: {quote[:70]}")
            cells.append({"key": key, "level": level, "summary": summary, "quote": quote, "where": where, "searched": None})
        prows.append({"short": short, "full": full, "file": url, "fname": f"{stem}.pdf", "cells": cells})

    if failures:
        print("QUOTE CHECK FAILED, not publishing:\n  " + "\n  ".join(failures)); sys.exit(1)

    n = len(rows)
    count = lambda key, lvl: sum(1 for r in rows for c in r["cells"] if c["key"] == key and c["level"] == lvl)
    pcount = lambda key, lvl: sum(1 for r in prows for c in r["cells"] if c["key"] == key and c["level"] == lvl)
    metrics = {
        "policies": n,
        "concrete_retention": count("retention", "ok"),
        "purpose_justified": count("justification", "ok"),
        "federal_ban": count("federal", "ok"),
        "audit": count("audit", "ok"),
        "quotes_verified": checked,
        "no_policy_total": sum(len(v) for v in NO_POLICY.values()),
        "no_policy_sfpd": len(NO_POLICY["Police Department"]),
        "audited_2024": pcount("audit", "ok"),
        "unchecked_no_violations": pcount("violations", "vague"),
    }
    for k, v in metrics.items():
        print(f"{k:24s} {v}")

    body = TEMPLATE.replace("__DATA__", json.dumps({"columns": COLUMNS, "rows": rows, "pcolumns": PRACTICE_COLUMNS,
                                                     "prows": prows, "metrics": metrics, "noPolicy": NO_POLICY}))
    (ROOT / "heatmap.html").write_text('<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">\n' + body + "\n</html>")
    pub = ROOT / "_publish"; pub.mkdir(exist_ok=True)
    (pub / "policy-vs-promise.html").write_text(body)
    print(f"\nwrote {ROOT / 'heatmap.html'}  ({checked}/{checked} quotes found verbatim in source)")


TEMPLATE = r"""<title>Policy vs Promise</title>
<meta name="claude:viewport-fit-sides" content="cover">
<style>
:root{--bg:#f7f6f2;--fg:#1c1b19;--muted:#6b6862;--card:#fff;--line:#e2dfd8;--ok:#2f7d4f;--okbg:#dcefe2;--vague:#9a6500;--vaguebg:#f8e9c6;--miss:#b3261e;--missbg:#f7d9d6}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#141413;--fg:#ecebe7;--muted:#9b978f;--card:#1e1e1c;--line:#33322f;--ok:#7fd19d;--okbg:#1f3a2a;--vague:#f0c060;--vaguebg:#3d3118;--miss:#f19a92;--missbg:#45201d;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#141413;--fg:#ecebe7;--muted:#9b978f;--card:#1e1e1c;--line:#33322f;--ok:#7fd19d;--okbg:#1f3a2a;--vague:#f0c060;--vaguebg:#3d3118;--miss:#f19a92;--missbg:#45201d;color-scheme:dark}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,sans-serif}
main{max-width:1180px;margin:0 auto;padding-block:28px 60px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
h1{font-size:26px;margin:0 0 4px}h2{font-size:17px;margin:34px 0 10px}.sub{color:var(--muted);margin:0 0 22px;max-width:760px}
.promise{border-left:3px solid var(--fg);padding:8px 14px;margin:0 0 22px;background:var(--card);max-width:820px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin-bottom:26px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px 14px}.stat b{font-size:24px;display:block}.stat span{color:var(--muted);font-size:13px}
.wrap{overflow-x:auto;border:1px solid var(--line);border-radius:8px;background:var(--card)}
table{border-collapse:collapse;width:100%;min-width:900px}th,td{padding:10px;border-bottom:1px solid var(--line);vertical-align:top;text-align:left}
th{font-size:13px;color:var(--muted);font-weight:600}th small{display:block;font-weight:400;font-size:11.5px;line-height:1.35}
td.dept{font-weight:600;white-space:nowrap}td.dept a{color:var(--muted);font-weight:400;font-size:12px;display:block}
.cell{cursor:pointer;border-radius:6px;padding:7px 9px;font-size:13px;border:2px solid transparent;width:100%;text-align:left;font:inherit;font-size:13px;color:inherit}
.cell:focus-visible,.cell.sel{border-color:var(--fg)}
.ok{background:var(--okbg)}.ok .tag{color:var(--ok)}.vague{background:var(--vaguebg)}.vague .tag{color:var(--vague)}.missing{background:var(--missbg)}.missing .tag{color:var(--miss)}
.tag{font-weight:700;font-size:11px;text-transform:uppercase;letter-spacing:.04em;display:block}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:13px;color:var(--muted);margin:10px 0}.legend i{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:5px;vertical-align:-1px}
.drawer{margin-top:14px;background:var(--card);border:1px solid var(--line);border-radius:8px;padding:14px 16px;min-height:90px}
.drawer blockquote{margin:8px 0;padding-left:12px;border-left:3px solid var(--line);font-family:Georgia,serif;font-size:15px}
.drawer .meta{color:var(--muted);font-size:13px}
.nopol{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:6px}.nopol div{background:var(--missbg);border-radius:6px;padding:6px 9px;font-size:13px}
.foot{color:var(--muted);font-size:13px;margin-top:30px;max-width:820px}
</style><main>
<h1>Policy vs Promise: SF license plate readers</h1>
<p class="sub">Five San Francisco departments run plate readers. Each signed the same promise, then filled in its own rules. Click any cell to see the exact sentence from the policy.</p>
<div class="promise"><b>The promise, word for word in the city template:</b> &ldquo;Departments shall minimize the use, collection, and retention of Personally Identifiable Information (PII) to what is strictly necessary to accomplish the intended purpose of the surveillance technology.&rdquo;</div>
<div class="stats" id="stats"></div>
<div class="legend"><span><i style="background:var(--okbg)"></i>Concrete</span><span><i style="background:var(--vaguebg)"></i>Vague / open-ended</span><span><i style="background:var(--missbg)"></i>Missing or not purpose-based</span></div>
<div class="wrap"><table id="t"></table></div>
<div class="drawer" id="drawer" aria-live="polite"><span class="meta">Click a cell to see its source quote.</span></div>
<h2>Practice: what each department told the city about 2024</h2>
<p class="sub">Every department files a yearly surveillance report with the city. These are their own answers for 2024, in their own words. Click any cell to see the exact answer.</p>
<div class="stats" id="pstats"></div>
<div class="legend"><span><i style="background:var(--okbg)"></i>Matches the promise</span><span><i style="background:var(--vaguebg)"></i>Worth a question</span><span><i style="background:var(--missbg)"></i>Gap</span></div>
<div class="wrap"><table id="p"></table></div>
<div class="drawer" id="pdrawer" aria-live="polite"><span class="meta">Click a cell to see the department's own answer.</span></div>
<h2 id="np"></h2>
<p class="sub">From the city's own Biannual Surveillance Technology Inventory Report (COIT, Sept 1 2026, Appendix D). The city counts 28 technologies from nine departments; the list has 23 entries because public Wi-Fi is shared by 8 departments. The city notes all were in use before the 2019 ordinance.</p>
<div class="nopol" id="nopol"></div>
<p class="foot"><b>Limits.</b> The practice table is each department's own answers on its 2024 yearly report, not an independent check: we have no access or sharing logs. &ldquo;About 200 agencies&rdquo; is our count of SFPD's listed recipients. &ldquo;Missing&rdquo; means a keyword search of the extracted text found nothing; a rule may exist elsewhere (state law applies whether or not a policy repeats it). Whether a justification is &ldquo;purpose-based&rdquo; is our team's judgment, shown with the quote so you can disagree. SFPD row uses the amended policy. Cells were filled by reading the text; every quote is machine-checked to appear verbatim in the source.</p>
</main>
<script>
const D=__DATA__,M=D.metrics,esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
document.getElementById('stats').innerHTML=[
 [M.concrete_retention+'/'+M.policies,'state a concrete retention period'],
 [M.purpose_justified+'/'+M.policies,'tie retention to the purpose'],
 [M.federal_ban+'/'+M.policies,'write in the federal / out-of-state ban'],
 [M.audit+'/'+M.policies,'mention access logging or audit'],
 ['28','technologies in use with no policy, per the city ('+M.no_policy_sfpd+' are SFPD)'],
 [M.quotes_verified+'/'+M.quotes_verified,'quotes verified verbatim against source']
].map(([b,s])=>`<div class="stat"><b>${b}</b><span>${s}</span></div>`).join('');
document.getElementById('pstats').innerHTML=[
 [M.audited_2024+'/'+M.policies,'checked their own use with an internal audit'],
 ['~200','outside agencies received SFPD plate data in 2024'],
 [M.unchecked_no_violations+'/'+M.policies,'reported zero violations without auditing'],
].map(([b,s])=>`<div class="stat"><b>${b}</b><span>${s}</span></div>`).join('');
function grid(id,drawerId,columns,rows,tags){
 const t=document.getElementById(id),dr=document.getElementById(drawerId);
 t.innerHTML='<tr><th>Department</th>'+columns.map(c=>`<th>${esc(c[1])}<small>${esc(c[2])}</small></th>`).join('')+'</tr>'+
  rows.map((r,ri)=>`<tr><td class="dept">${esc(r.short)}<a href="${esc(r.file)}" target="_blank" rel="noopener">source</a></td>`+
  r.cells.map((c,ci)=>`<td><button class="cell ${c.level}" data-r="${ri}" data-c="${ci}"><span class="tag">${tags[c.level]}</span>${esc(c.summary)}</button></td>`).join('')+'</tr>').join('');
 t.addEventListener('click',e=>{const b=e.target.closest('.cell');if(!b)return;
  document.querySelectorAll('.cell.sel').forEach(x=>x.classList.remove('sel'));b.classList.add('sel');
  const r=rows[b.dataset.r],c=r.cells[b.dataset.c],col=columns[b.dataset.c];
  dr.innerHTML=`<b>${esc(r.full)}</b> &middot; ${esc(col[1])}<br>`+(c.quote?`<blockquote>&ldquo;${esc(c.quote)}&rdquo;</blockquote><span class="meta">${esc(c.where)} of <a href="${esc(r.file)}" target="_blank" rel="noopener">${esc(r.fname)}</a></span>`:
  `<p>${esc(c.summary)}.</p><span class="meta">No quote: ${esc(c.searched||'not found')} in <a href="${esc(r.file)}" target="_blank" rel="noopener">${esc(r.fname)}</a>.</span>`);});
}
grid('t','drawer',D.columns,D.rows,{ok:'concrete',vague:'vague',missing:'missing'});
grid('p','pdrawer',D.pcolumns,D.prows,{ok:'matches',vague:'question',missing:'gap'});
document.getElementById('np').textContent='28 surveillance technologies in use with no approved policy';
document.getElementById('nopol').innerHTML=Object.entries(D.noPolicy).flatMap(([d,ts])=>ts.map(x=>`<div><b>${esc(x)}</b><br><span style="opacity:.75">${esc(d)}</span></div>`)).join('');
</script>"""

if __name__ == "__main__":
    main()
