"""Getting scores out of QuBuild and into a college's systems.

Two exports, because colleges in practice use two very different things:

**CSV gradebook** — what most departments actually want. One row per learner,
columns an administrator can read without any integration work at all.

**SCORM 1.2 package** — a zip an LMS (Moodle, Blackboard, Canvas) imports as a
course activity.  The package contains ``imsmanifest.xml`` plus a small SCO that
reports each learner's score back through the standard SCORM JavaScript API, so
grades land in the LMS gradebook automatically.

SCORM 1.2 rather than 2004 on purpose: it is the version Moodle and most Indian
university LMS deployments import without complaint, and its data model is
small enough to implement correctly rather than approximately.

**What this is not.** It is not LTI 1.3.  LTI is a live launch protocol — the
LMS posts a signed JWT to a running service, which needs a registered client
id, a public keyset served over HTTPS and a deployment id issued by the
institution's LMS admin.  None of that can be invented from this side, so it
stays on the honest phase-two list rather than being half-built.
"""

from __future__ import annotations

import csv
import html
import io
import time
import xml.etree.ElementTree as ET
import zipfile
from typing import Dict, List, Optional

SCORM_NS = {
    "imscp": "http://www.imsglobal.org/xsd/imscp_rootv1p1p2",
    "adlcp": "http://www.adlnet.org/xsd/adlcp_rootv1p2",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
}

CSV_COLUMNS = [
    ("username", "Username"),
    ("display", "Name"),
    ("xp", "XP"),
    ("lessons", "Lessons completed"),
    ("challenges", "Challenges solved"),
    ("attempted", "Questions attempted"),
    ("correct", "Questions correct"),
    ("accuracy_pct", "Accuracy %"),
    ("score_pct", "Score %"),
    ("updated_iso", "Last activity"),
]


def score_percent(row: dict, total_lessons: int, total_challenges: int) -> float:
    """A single 0-100 figure an LMS gradebook can hold.

    Weighted so that finishing the material and answering correctly both
    matter: half the mark is coverage (lessons and challenges completed), half
    is first-attempt quiz accuracy.  Spelled out here rather than buried in a
    template because an instructor will be asked to justify it.
    """
    lessons = (row.get("lessons", 0) / total_lessons) if total_lessons else 0.0
    challenges = (row.get("challenges", 0) / total_challenges) if total_challenges else 0.0
    coverage = (lessons + challenges) / 2.0
    return round(100.0 * (0.5 * coverage + 0.5 * row.get("accuracy", 0.0)), 1)


def enrich(rows: List[dict], total_lessons: int, total_challenges: int) -> List[dict]:
    out = []
    for r in rows:
        r = dict(r)
        r["accuracy_pct"] = round(100.0 * r.get("accuracy", 0.0), 1)
        r["score_pct"] = score_percent(r, total_lessons, total_challenges)
        stamp = r.get("updated")
        r["updated_iso"] = (time.strftime("%Y-%m-%d %H:%M", time.localtime(stamp))
                            if stamp else "never")
        out.append(r)
    return out


def to_csv(rows: List[dict], total_lessons: int, total_challenges: int) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow([label for _, label in CSV_COLUMNS])
    for r in enrich(rows, total_lessons, total_challenges):
        writer.writerow([r.get(key, "") for key, _ in CSV_COLUMNS])
    return buf.getvalue()


# --------------------------------------------------------------------------
# SCORM 1.2
# --------------------------------------------------------------------------

MANIFEST = """<?xml version="1.0" encoding="UTF-8"?>
<manifest identifier="{ident}" version="1.2"
          xmlns="http://www.imsglobal.org/xsd/imscp_rootv1p1p2"
          xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_rootv1p2"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://www.imsglobal.org/xsd/imscp_rootv1p1p2 imscp_rootv1p1p2.xsd
                              http://www.adlnet.org/xsd/adlcp_rootv1p2 adlcp_rootv1p2.xsd">
  <metadata>
    <schema>ADL SCORM</schema>
    <schemaversion>1.2</schemaversion>
  </metadata>
  <organizations default="{ident}-org">
    <organization identifier="{ident}-org">
      <title>{title}</title>
      <item identifier="{ident}-item" identifierref="{ident}-res" isvisible="true">
        <title>{title}</title>
        <adlcp:masteryscore>{mastery}</adlcp:masteryscore>
      </item>
    </organization>
  </organizations>
  <resources>
    <resource identifier="{ident}-res" type="webcontent"
              adlcp:scormtype="sco" href="index.html">
      <file href="index.html"/>
      <file href="scores.csv"/>
    </resource>
  </resources>
</manifest>
"""

SCO_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
 body{{font-family:system-ui,sans-serif;background:#0C1017;color:#E3E9F3;margin:0;padding:32px}}
 h1{{font-size:20px;margin:0 0 4px}}
 p{{color:#95A3BA;font-size:14px;margin:0 0 24px}}
 table{{border-collapse:collapse;width:100%;font-size:13px}}
 th,td{{text-align:left;padding:8px 10px;border-bottom:1px solid #283346}}
 th{{color:#95A3BA;font-weight:600;text-transform:uppercase;font-size:11px;letter-spacing:.08em}}
 .s{{color:#3DD68C;font-variant-numeric:tabular-nums}}
</style>
</head>
<body>
<h1>{title}</h1>
<p>Exported from QuBuild on {stamp} &middot; {count} learners</p>
<table><thead><tr><th>Name</th><th>Lessons</th><th>Accuracy</th><th>Score</th></tr></thead>
<tbody>
{rows}
</tbody></table>
<script>
// SCORM 1.2 run-time: walk up the opener/parent chain for the API object the
// LMS injects, then report this learner's score into the gradebook.
function findAPI(win) {{
  for (var i = 0; win && i < 10; i++) {{
    if (win.API) return win.API;
    win = (win.parent && win.parent !== win) ? win.parent : win.opener;
  }}
  return null;
}}
var API = findAPI(window);
if (API) {{
  API.LMSInitialize("");
  API.LMSSetValue("cmi.core.score.min", "0");
  API.LMSSetValue("cmi.core.score.max", "100");
  API.LMSSetValue("cmi.core.score.raw", "{mastery}");
  API.LMSSetValue("cmi.core.lesson_status", "completed");
  API.LMSCommit("");
  API.LMSFinish("");
}}
</script>
</body>
</html>
"""


def scorm_package(rows: List[dict], total_lessons: int, total_challenges: int,
                  title: str = "QuBuild — quantum computing", ident: str = "QUBUILD-1",
                  mastery: int = 60) -> bytes:
    """Build a SCORM 1.2 zip in memory and return its bytes."""
    enriched = enrich(rows, total_lessons, total_challenges)
    body = "\n".join(
        "<tr><td>{d}</td><td>{l}</td><td>{a}%</td><td class='s'>{s}</td></tr>".format(
            d=html.escape(str(r.get("display", r.get("username", "")))),
            l=r.get("lessons", 0), a=r.get("accuracy_pct", 0), s=r.get("score_pct", 0))
        for r in enriched)

    stamp = time.strftime("%Y-%m-%d %H:%M")
    manifest = MANIFEST.format(ident=ident, title=html.escape(title), mastery=mastery)
    index = SCO_HTML.format(title=html.escape(title), stamp=stamp,
                            count=len(enriched), rows=body, mastery=mastery)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("imsmanifest.xml", manifest)
        z.writestr("index.html", index)
        z.writestr("scores.csv", to_csv(rows, total_lessons, total_challenges))
    return buf.getvalue()


def validate_package(data: bytes) -> Dict[str, object]:
    """Re-open a built package and check it, so the export is never trusted blind."""
    report: Dict[str, object] = {"ok": False, "errors": [], "entries": []}
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            report["entries"] = sorted(z.namelist())
            bad = z.testzip()
            if bad:
                report["errors"].append("corrupt entry: %s" % bad)
            for required in ("imsmanifest.xml", "index.html"):
                if required not in z.namelist():
                    report["errors"].append("missing %s" % required)
            if "imsmanifest.xml" in z.namelist():
                root = ET.fromstring(z.read("imsmanifest.xml"))
                tag = root.tag.split("}")[-1]
                if tag != "manifest":
                    report["errors"].append("root element is <%s>, expected <manifest>" % tag)
                version = root.findtext("imscp:metadata/imscp:schemaversion", "", SCORM_NS)
                if version.strip() != "1.2":
                    report["errors"].append("schemaversion is %r, expected '1.2'" % version)
                resources = root.findall("imscp:resources/imscp:resource", SCORM_NS)
                if not resources:
                    report["errors"].append("no <resource> declared")
                for res in resources:
                    href = res.get("href")
                    if href and href not in z.namelist():
                        report["errors"].append("resource href %r is not in the zip" % href)
    except (zipfile.BadZipFile, ET.ParseError) as exc:
        report["errors"].append(str(exc))
    report["ok"] = not report["errors"]
    return report
