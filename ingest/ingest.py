#!/usr/bin/env python3
"""
Citibike raw ingest: stage zips from the public S3 archive into GCS, then load
into two raw-faithful BigQuery tables (legacy 15-col, new 13-col), per the
decisions in DECISIONS.md. No normalization on load.

Pipeline (file-by-file): download zip -> recursively extract CSV members ->
restage (CSV-aware): strip header if present, append provenance (system,
source_file), HARD field-count gate, gzip -> upload to gs://.../staging/{era}/
-> two `bq load --replace` wildcard jobs (free; no query bytes billed).

Usage:
  python ingest.py --list                       # print manifest, do nothing
  python ingest.py --files A.zip,B.zip          # stage only these (no load)
  python ingest.py --files A.zip --load         # stage these, then load
  python ingest.py                              # FULL: clean staging + all 169 + load
"""
import argparse, csv, gzip, hashlib, io, os, re, shutil, subprocess, sys, tempfile, urllib.request, zipfile

PROJECT  = os.environ.get("GCP_PROJECT", "YOUR_GCP_PROJECT")
DATASET  = "citibike_raw"
BUCKET   = os.environ.get("GCS_BUCKET", PROJECT + "-citibike-raw")
LOCATION = "US"
BASE_URL = "https://s3.amazonaws.com/tripdata/"
STAGING  = "staging"   # gs://BUCKET/staging/{legacy|new}/...

LEGACY_COLS = ["tripduration","starttime","stoptime","start_station_id","start_station_name",
    "start_station_latitude","start_station_longitude","end_station_id","end_station_name",
    "end_station_latitude","end_station_longitude","bikeid","usertype","birth_year","gender"]
NEW_COLS = ["ride_id","rideable_type","started_at","ended_at","start_station_name",
    "start_station_id","end_station_name","end_station_id","start_lat","start_lng",
    "end_lat","end_lng","member_casual"]
PROV = ["system","source_file"]
SRC_FIELDS = {"legacy": len(LEGACY_COLS), "new": len(NEW_COLS)}       # 15 / 13
OUT_FIELDS = {"legacy": len(LEGACY_COLS)+2, "new": len(NEW_COLS)+2}   # 17 / 15
csv.field_size_limit(10**7)

# ---- manifest / categorization -------------------------------------------------
def list_keys():
    xml = urllib.request.urlopen(BASE_URL).read().decode()
    return [k for k in re.findall(r"<Key>([^<]+)</Key>", xml) if k.endswith(".zip")]

def classify(key):
    """Return (system, era) for a top-level zip key. era is uniform within a file."""
    if key.startswith("JC-"):
        ym = re.search(r"(\d{6})", key).group(1)
        return "JC", ("legacy" if ym <= "202101" else "new")
    m6, m4 = re.match(r"^(\d{6})-", key), re.match(r"^(\d{4})-", key)
    if m6:  return "NYC", "new"                                  # monthly NYC are all 2024-01+
    if m4:  return "NYC", ("legacy" if int(m4.group(1)) <= 2019 else "new")
    raise ValueError(f"uncategorizable key: {key}")

def manifest(keys):
    out = {}
    for k in keys:
        out.setdefault(classify(k), []).append(k)
    return out

# ---- extraction ----------------------------------------------------------------
def iter_csv_members(zf, prefix=""):
    """Yield (member_path, binary_stream) for every .csv, recursing into nested zips."""
    for info in zf.infolist():
        name = info.filename
        base = name.rsplit("/", 1)[-1]
        if name.endswith("/") or "__MACOSX" in name or base.startswith("._") or base == ".DS_Store":
            continue
        low = name.lower()
        if low.endswith(".csv"):
            if info.file_size == 0:    # skip zero-byte members
                continue
            yield prefix + name, zf.open(info)
        elif low.endswith(".zip"):
            data = zf.read(info)
            with zipfile.ZipFile(io.BytesIO(data)) as zf2:
                yield from iter_csv_members(zf2, prefix + name + "::")

def is_header(row, era):
    if not row:
        return False
    f = row[0].lstrip("﻿").strip().strip('"').strip().lower().replace(" ", "")
    return f == "tripduration" if era == "legacy" else f == "ride_id"

def sanitize(s):
    return re.sub(r"[^A-Za-z0-9._-]", "_", s)

# ---- per-file processing -------------------------------------------------------
def download(key, dest):
    url = BASE_URL + urllib.request.quote(key)
    with urllib.request.urlopen(url) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f, length=1 << 20)

def stage_file(key, workdir, rej, rej_counts, dup_counts, dry=False):
    """Download, extract, restage every CSV member; upload gzipped to GCS.
    Bad-width rows are quarantined to the rejects log and skipped (run proceeds).
    Same-basename members within one archive are content-hashed: an identical
    duplicate is skipped (logged); a DIVERGENT one aborts the run for review,
    since the flat staging name cannot represent both. Returns rows staged."""
    system, era = classify(key)
    exp_src, exp_out = SRC_FIELDS[era], OUT_FIELDS[era]
    zpath = os.path.join(workdir, sanitize(key))
    print(f"  ↓ download {key}  ({system}/{era})")
    download(key, zpath)
    total = 0
    seen = {}   # member basename -> (sha1, member_path)  [first occurrence]
    with zipfile.ZipFile(zpath) as zf:
        # Some annual archives (2013, 2018) store each month BOTH as a flat
        # whole-month CSV and as size-split parts (top-level and/or in a
        # month subfolder) — i.e. the same data twice. When a month has a
        # whole-month file, keep only the whole and drop that month's parts.
        whole_months = {m.group(1) for nm in zf.namelist()
                        for m in [re.search(r"(?:^|/)(\d{6})-citibike-tripdata\.csv$", nm)] if m}
        for member, stream in iter_csv_members(zf):
            base = re.split(r"[/:]", member)[-1]
            mo = re.search(r"(\d{6})", base)
            if re.search(r"_\d+\.csv$", base) and mo and mo.group(1) in whole_months:
                dup_counts[era] = dup_counts.get(era, 0) + 1   # redundant split of a whole month
                print(f"    ⤷ redundant split skipped (month {mo.group(1)} kept as whole): {member}")
                continue
            raw = stream.read()
            h = hashlib.sha1(raw).hexdigest()
            if base in seen:
                prev_h, prev_member = seen[base]
                if h == prev_h:                             # identical duplicate -> skip
                    dup_counts[era] = dup_counts.get(era, 0) + 1
                    print(f"    ⤷ duplicate skipped (identical to "
                          f"{prev_member.split('::')[-1]}): {member}")
                    continue
                raise SystemExit(                           # divergent -> hard stop
                    f"DIVERGENT COLLISION in {key}: members '{member}' and "
                    f"'{prev_member}' share basename '{base}' but content differs "
                    f"(sha1 {h[:12]} vs {prev_h[:12]}). Staging naming cannot "
                    f"represent both — aborting for human review.")
            seen[base] = (h, member)
            out_name = f"{sanitize(key)[:-4]}__{sanitize(base)}"
            if not out_name.endswith(".csv"):
                out_name += ".csv"
            local_gz = os.path.join(workdir, out_name + ".gz")
            n = 0
            text = io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8", errors="replace", newline="")
            with gzip.open(local_gz, "wt", encoding="utf-8", newline="") as gzf:
                w = csv.writer(gzf)
                for i, row in enumerate(csv.reader(text)):
                    if i == 0 and is_header(row, era):
                        continue
                    if len(row) == 0:                       # skip blank lines
                        continue
                    if len(row) != exp_src:                 # <-- GATE: quarantine & continue
                        rej.write(f"{era}\t{key}\t{member}\tline {i+1}\t"
                                  f"got={len(row)}\texpected={exp_src}\n")
                        rej_counts[era] = rej_counts.get(era, 0) + 1
                        continue
                    w.writerow(row + [system, key])
                    n += 1
            if dry:
                os.remove(local_gz)
                dest = "(dry-run: not uploaded)"
            else:
                gs = f"gs://{BUCKET}/{STAGING}/{era}/{out_name}.gz"
                subprocess.run(["gcloud", "storage", "cp", "-q", local_gz, gs], check=True)
                os.remove(local_gz)
                dest = gs.split("/")[-1]
            total += n
            print(f"    ✓ {member.split('::')[-1]:<46} {n:>10,} rows -> {dest}")
    os.remove(zpath)
    return total

# ---- load ----------------------------------------------------------------------
def schema_str(cols):
    return ",".join(f"{c}:STRING" for c in cols + PROV)

def load_table(era, table):
    cols = LEGACY_COLS if era == "legacy" else NEW_COLS
    uri = f"gs://{BUCKET}/{STAGING}/{era}/*.csv.gz"
    print(f"\n== bq load --replace {DATASET}.{table}  <-  {uri}")
    subprocess.run(["bq", f"--location={LOCATION}", "load", "--replace",
        "--source_format=CSV", "--skip_leading_rows=0", "--allow_quoted_newlines",
        "--max_bad_records=0", f"--schema={schema_str(cols)}",
        f"{PROJECT}:{DATASET}.{table}", uri], check=True)
    out = subprocess.run(["bq", "show", "--format=prettyjson", f"{PROJECT}:{DATASET}.{table}"],
        capture_output=True, text=True, check=True).stdout
    rows = re.search(r'"numRows":\s*"(\d+)"', out)
    print(f"   -> {DATASET}.{table} numRows = {rows.group(1) if rows else '?'}")

def clean_staging():
    print(f"× clearing gs://{BUCKET}/{STAGING}/ for an idempotent run")
    subprocess.run(["gcloud", "storage", "rm", "--recursive", "-q",
        f"gs://{BUCKET}/{STAGING}/"], check=False)

# ---- main ----------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--files", help="comma-separated source keys to stage")
    ap.add_argument("--load", action="store_true", help="run the two load jobs after staging")
    ap.add_argument("--clean-staging", action="store_true")
    ap.add_argument("--dry-run", dest="dry_run", action="store_true",
                    help="process + gate + dedup only; no GCS upload, no clean, no load")
    args = ap.parse_args()

    keys = list_keys()
    mani = manifest(keys)
    if args.list:
        for (sys_, era), v in sorted(mani.items()):
            print(f"{sys_:<3} {era:<7} {len(v):>3}  [{sorted(v)[0]} … {sorted(v)[-1]}]")
        print(f"TOTAL {len(keys)} files -> legacy {SRC_FIELDS['legacy']}+2, new {SRC_FIELDS['new']}+2")
        return

    full = not args.files
    todo = keys if full else [k.strip() for k in args.files.split(",")]
    bad = [k for k in todo if k not in keys]
    if bad:
        raise SystemExit(f"unknown source keys: {bad}")

    if (args.clean_staging or full) and not args.dry_run:
        clean_staging()

    print(f"staging {len(todo)} file(s)…" + (" [DRY RUN]" if args.dry_run else ""))
    grand = 0
    rej_counts, dup_counts = {}, {}
    rej_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rejects.log")
    with open(rej_path, "w", encoding="utf-8") as rej, \
         tempfile.TemporaryDirectory(prefix="citibike_") as wd:
        for k in todo:
            grand += stage_file(k, wd, rej, rej_counts, dup_counts, args.dry_run)
    print(f"\nstaged {grand:,} total rows from {len(todo)} file(s)")
    print("reject summary (bad-width rows quarantined & skipped):")
    for era, table in [("legacy", "trips_legacy"), ("new", "trips_new")]:
        print(f"  {table:<14} {rej_counts.get(era, 0):>10,} rejects   "
              f"{dup_counts.get(era, 0):>4} identical-duplicate members skipped")
    print(f"  reject details: {rej_path}" if sum(rej_counts.values()) else "  (no rejects)")

    if args.dry_run:
        print("(dry run — no upload, no load)")
    elif args.load or full:
        load_table("legacy", "trips_legacy")
        load_table("new",    "trips_new")
    else:
        print("(staging only — pass --load to run the bq load jobs)")

if __name__ == "__main__":
    main()
