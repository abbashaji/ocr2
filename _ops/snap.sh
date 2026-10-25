#!/bin/sh
# Snapshot / diff-check / pack helper. Run from the project root (the folder that contains _ops).
#   sh _ops/snap.sh before           snapshot the tree exactly as received (do this before any edit)
#   sh _ops/snap.sh after            list what really changed + REVIEW items (from the diff, not from memory)
#   sh _ops/snap.sh pack <outdir> [label]
#                                    write <name>_vNNN.zip and CHANGES_vNNN.md into <outdir>.
#                                    With a label (letters/digits, starting with a letter, e.g. a) it marks a
#                                    parallel branch: <name>_vNNNa.zip and CHANGES_vNNNa.md.
#   sh _ops/snap.sh merge <branch.zip> <branch.zip> ...
#                                    merge chat only, right after 'before' on the BASE project: copies every
#                                    change no other branch also touched, lists the files that need a hand merge.
W=${FCB_WORK:-/tmp/fcb_work}
ORIG=$W/orig
CR=$(printf '\r'); TAB=$(printf '\t')
stop() { echo "STOPPED: $1"; echo "DO THIS: $2"; exit 2; }
[ -f _ops/STATE.md ] || stop "no _ops/STATE.md in $(pwd)" "run this from the project root, the folder that contains _ops"
NAME=$(basename "$PWD")
rx=$(grep -Ev '^[[:space:]]*(#|$)' _ops/EXCLUDE.txt 2>/dev/null | sed 's/[][\*^$|(){}+?.]/\\&/g' | paste -sd'|' -)
[ -n "$rx" ] || rx='^$x'
lst() { (cd "$1" && find . \( -type f -o -type l \) | sed 's|^\./||' | grep -Ev "(^|/)($rx)(/|\$)" | LC_ALL=C sort); }
getver() { sed -n 's/^Version:[[:space:]]*//p' _ops/STATE.md | head -n 1 | tr -d ' \r' | sed 's/^0*\([0-9]\)/\1/'; }
textual() { { grep -Iq . "$1" 2>/dev/null || [ ! -s "$1" ]; } && [ "$(wc -c < "$1")" -lt 2000000 ]; }
n() { wc -l < "$1" | tr -d ' '; }

before() {
  rm -rf "$W"; mkdir -p "$ORIG"
  lst . > "$W/old.lst"
  if [ -s "$W/old.lst" ]; then tar -cf - -T "$W/old.lst" | tar -xf - -C "$ORIG"; fi
  getver > "$W/ver"
  echo "SNAPSHOT: $(n "$W/old.lst") files, project $NAME, version $(cat "$W/ver"). Work dir: $W"
}

after_report() {
  [ -d "$ORIG" ] || stop "no snapshot found" "run  sh _ops/snap.sh before  at the start, before any edit"
  lst . > "$W/new.lst"; lst "$ORIG" > "$W/old.lst"
  LC_ALL=C comm -13 "$W/old.lst" "$W/new.lst" > "$W/added"
  LC_ALL=C comm -23 "$W/old.lst" "$W/new.lst" > "$W/deleted"
  LC_ALL=C comm -12 "$W/old.lst" "$W/new.lst" | while IFS= read -r f; do cmp -s "$ORIG/$f" "$f" || echo "$f"; done > "$W/modified"
  : > "$W/stream"
  AW='BEGIN{OFS="\t"} /^(\+\+\+|---)/{next} /^[+-]/{print f, $0}'
  while IFS= read -r f; do
    if textual "$ORIG/$f" && textual "$f"; then diff -U0 "$ORIG/$f" "$f" | awk -v f="$f" "$AW"; fi
  done < "$W/modified" >> "$W/stream"
  while IFS= read -r f; do
    if textual "$f"; then diff -U0 /dev/null "$f" | awk -v f="$f" "$AW"; fi
  done < "$W/added" >> "$W/stream"
  while IFS= read -r f; do
    if textual "$ORIG/$f"; then diff -U0 "$ORIG/$f" /dev/null | awk -v f="$f" "$AW"; fi
  done < "$W/deleted" >> "$W/stream"
  cat > "$W/skip.rx" <<'RX'
(#\[ignore\]|pytest\.mark\.skip|xfail|\.skip\(|xit\(|xdescribe|@Disabled|t\.Skip\(|\[Ignore\]|DISABLED_|GTEST_SKIP)
RX
  cat > "$W/stub.rx" <<'RX'
(TODO|FIXME|XXX|unimplemented!|todo!\(|NotImplemented)
RX
  cat > "$W/sec.rx" <<'RX'
(-----BEGIN [A-Z ]*PRIVATE KEY|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}|xox[baprs]-[A-Za-z0-9-]{10,}|sk-[A-Za-z0-9]{20,}|(api[_-]?key|secret|passw(or)?d|token)["' ]*[:=]["' ]*[A-Za-z0-9/+_-]{16,})
RX
  cat > "$W/dep.rx" <<'RX'
(^|/)(Cargo\.(toml|lock)|package(-lock)?\.json|yarn\.lock|pnpm-lock\.yaml|requirements[^/]*\.txt|pyproject\.toml|poetry\.lock|go\.(mod|sum)|Gemfile(\.lock)?|composer\.(json|lock)|pom\.xml|build\.gradle|[^/]*\.csproj|[^/]*\.Build\.cs|[^/]*\.uproject)$|^\.github/
RX
  {
    echo "== CHANGED FILES =="
    sed 's/^/A /' "$W/added"; sed 's/^/M /' "$W/modified"; sed 's/^/D /' "$W/deleted"
    echo "total: $(n "$W/added") added, $(n "$W/modified") modified, $(n "$W/deleted") deleted"
    echo "== REVIEW items: open the real file for each before accepting =="
    awk -F"$TAB" '$2 ~ /^-/ && $1 ~ /(^|\/)(tests?|__tests__|spec)\/|_test\.|\.test\.|\.spec\.|(^|\/)test_/ {print "REVIEW test-line-removed-or-changed: " $1 ": " substr($2,1,100)}' "$W/stream" | head -40
    awk -F"$TAB" '$2 ~ /^\+/' "$W/stream" > "$W/plus"
    grep -E -f "$W/skip.rx" "$W/plus" | sed 's/^/REVIEW test-skipped: /' | cut -c1-140 | head -20
    grep -E -f "$W/stub.rx" "$W/plus" | sed 's/^/REVIEW stub: /' | cut -c1-140 | head -20
    grep -E -f "$W/sec.rx" "$W/plus" | sed 's/^/REVIEW possible-secret: /' | cut -c1-60 | head -20
    cat "$W/added" "$W/modified" "$W/deleted" | grep -E -f "$W/dep.rx" | sed 's/^/REVIEW dependency-or-CI-file-changed (check it was asked for): /'
    cat "$W/added" "$W/modified" "$W/deleted" | grep '^_ops/' | grep -v '^_ops/STATE.md$' | sed 's/^/REVIEW ops-file-changed (rules must not be edited): /'
    cat "$W/added" "$W/modified" | while IFS= read -r f; do
      if ! { grep -Iq . "$f" 2>/dev/null || [ ! -s "$f" ]; }; then echo "REVIEW binary-file: $f ($(wc -c < "$f" | tr -d ' ') bytes)"; fi
    done
    while IFS= read -r f; do
      if textual "$ORIG/$f" && textual "$f"; then
        a=$(grep -c "$CR" "$ORIG/$f"); b=$(grep -c "$CR" "$f")
        if { [ "$a" -gt 0 ] && [ "$b" -eq 0 ]; } || { [ "$a" -eq 0 ] && [ "$b" -gt 0 ]; }; then
          echo "REVIEW line-endings: $f (CRLF lines: was $a, now $b)"; fi
      fi
    done < "$W/modified"
    echo "== end REVIEW items =="
  } > "$W/report.txt"
}

pack() {
  out=$1; lab=${2:-}
  [ -n "$out" ] && [ -d "$out" ] || stop "pack needs an existing output folder" "run: sh _ops/snap.sh pack <outdir> [label]"
  case "$lab" in *[!A-Za-z0-9]*|[0-9]*) stop "branch label '$lab' is not allowed" "use letters and digits only, starting with a letter (for example a)";; esac
  command -v zip >/dev/null 2>&1 && command -v unzip >/dev/null 2>&1 && command -v tar >/dev/null 2>&1 || stop "zip, unzip or tar is missing in this environment" "tell the human; nothing can be packed here"
  out=$(cd "$out" && pwd)
  [ -f "$W/summary.md" ] || stop "no summary yet" "write $W/summary.md (max 25 lines), then run pack again"
  v=$(getver); o=$(cat "$W/ver" 2>/dev/null)
  case "$v$o" in ''|*[!0-9]*) stop "Version in _ops/STATE.md or in the snapshot is not a plain number" "fix the Version: line in _ops/STATE.md";; esac
  [ "$v" -eq $((o+1)) ] || stop "Version in _ops/STATE.md is $v but must be $((o+1))" "set 'Version: $((o+1))' in _ops/STATE.md, then run pack again"
  after_report
  nn=$(printf '%03d' "$v")
  mode=$(sed -n 's/^Return:[[:space:]]*//p' _ops/STATE.md | head -n 1 | tr -d ' \r')
  S=$W/stage; rm -rf "$S"; mkdir -p "$S/$NAME"
  if [ "$mode" = changed ]; then
    cat "$W/added" "$W/modified" > "$W/pack.lst"; zn="${NAME}_v${nn}${lab}_changed.zip"
    if [ -s "$W/deleted" ]; then cp "$W/deleted" "$S/DELETE_THESE.txt"; fi
  else
    cp "$W/new.lst" "$W/pack.lst"; zn="${NAME}_v${nn}${lab}.zip"
  fi
  if [ -s "$W/pack.lst" ]; then tar -cf - -T "$W/pack.lst" | tar -xf - -C "$S/$NAME"; fi
  if [ -n "$lab" ]; then cp "$W/summary.md" "$S/BRANCH_SUMMARY.md"; fi
  rm -f "$out/$zn"; (cd "$S" && zip -qry "$out/$zn" .) || stop "zip failed" "tell the human the exact error"
  unzip -tq "$out/$zn" >/dev/null || stop "the zip it just wrote does not pass unzip -t" "tell the human"
  cn="CHANGES_v${nn}${lab}.md"
  { echo "# CHANGES v$nn$lab ($NAME)"; echo
    if [ -n "$lab" ]; then echo "PARALLEL BRANCH $lab (base version $o). Not a next project zip: keep it for the merge step."; echo; fi
    cat "$W/summary.md"; echo; echo "## Generated from the real diff, not from memory"; echo '```'; cat "$W/report.txt"; echo '```'; } > "$out/$cn"
  sz=$(wc -c < "$out/$zn" | tr -d ' ')
  echo "PACKED: $zn ($(unzip -Z1 "$out/$zn" | grep -vc '/$') files, $sz bytes) and $cn in $out"
  [ "$sz" -lt 25000000 ] || echo "WARNING: the zip is over 25 MB; the human may not be able to upload it next time. Say so in the reply."
}

merge() {
  [ -d "$ORIG" ] || stop "no snapshot found" "unzip the base project, go to its root and run  sh _ops/snap.sh before  first"
  [ "$#" -ge 2 ] || stop "merge needs at least two branch zips" "run: sh _ops/snap.sh merge <branch1.zip> <branch2.zip> ..."
  command -v unzip >/dev/null 2>&1 || stop "unzip is missing in this environment" "tell the human; nothing can be merged here"
  lst . > "$W/new.lst"; lst "$ORIG" > "$W/old.lst"
  cmp -s "$W/new.lst" "$W/old.lst" || stop "the project tree differs from the snapshot" "merge must run right after 'before' and before any edit: unzip the base project again, run  sh _ops/snap.sh before, then merge"
  while IFS= read -r f; do
    [ ! -L "$f" ] || stop "$f is a symbolic link" "merge does not handle symbolic links: remove it from the project or run the tasks one after another"
    cmp -s "$ORIG/$f" "$f" || stop "$f differs from the snapshot" "merge must run right after 'before' and before any edit: unzip the base project again, run  sh _ops/snap.sh before, then merge"
  done < "$W/old.lst"
  bv=$(cat "$W/ver"); B=$W/branches; rm -rf "$B"; mkdir -p "$B"
  hl=$(tr -d '\r' < _ops/STATE.md | awk '/^## History/{f=1;next} f&&NF{print;exit}')
  : > "$W/m_all"; : > "$W/m_opsnote"; labels=""
  for z in "$@"; do
    [ -f "$z" ] || stop "branch zip not found: $z" "attach it and pass its real path"
    lab=$(basename "$z" | sed -n 's/.*_v[0-9][0-9]*\([A-Za-z][A-Za-z0-9]*\)\(_changed\)\{0,1\}\.zip$/\1/p')
    [ -n "$lab" ] || stop "no branch label in the name of $(basename "$z")" "branch zips are named <project>_vNNN<label>.zip (written by: sh _ops/snap.sh pack <dir> <label>)"
    [ ! -d "$B/$lab" ] || stop "two branch zips use the label $lab" "each parallel branch needs its own label; rebuild one of them"
    mkdir -p "$B/$lab"; unzip -q "$z" -d "$B/$lab" || stop "cannot unzip $z" "tell the human the exact error"
    sf=$(find "$B/$lab" -maxdepth 3 -path '*/_ops/STATE.md')
    [ -n "$sf" ] || stop "no _ops/STATE.md inside branch $lab" "that zip is not a branch result; attach the right one"
    [ "$(echo "$sf" | wc -l | tr -d ' ')" -eq 1 ] || stop "branch $lab holds more than one _ops/STATE.md" "that zip is not a branch result; attach the right one"
    root=$(dirname "$(dirname "$sf")"); echo "$root" > "$W/m_root_$lab"
    bver=$(sed -n 's/^Version:[[:space:]]*//p' "$root/_ops/STATE.md" | head -n 1 | tr -d ' \r' | sed 's/^0*\([0-9]\)/\1/')
    case "$bver" in ''|*[!0-9]*) stop "branch $lab has no plain Version number" "rebuild that branch";; esac
    [ "$bver" -eq $((bv+1)) ] || stop "branch $lab has Version $bver but the base is $bv, so it must be $((bv+1))" "rebuild that branch from the same base zip as the other branches"
    if [ -n "$hl" ] && ! tr -d '\r' < "$root/_ops/STATE.md" | grep -Fqx -- "$hl"; then
      stop "branch $lab does not carry the base's newest history line ($hl)" "it was probably built from a different base zip, or its history was rewritten; rebuild it from the base zip"
    fi
    mode=$(sed -n 's/^Return:[[:space:]]*//p' "$root/_ops/STATE.md" | head -n 1 | tr -d ' \r')
    lst "$root" > "$B/$lab.lst"
    while IFS= read -r f; do
      [ ! -L "$root/$f" ] || stop "branch $lab contains the symbolic link $f" "merge does not handle symbolic links; run the tasks one after another instead"
    done < "$B/$lab.lst"
    : > "$B/$lab.ch"
    LC_ALL=C comm -13 "$W/old.lst" "$B/$lab.lst" | sed "s/^/A$TAB/" >> "$B/$lab.ch"
    LC_ALL=C comm -12 "$W/old.lst" "$B/$lab.lst" | while IFS= read -r f; do cmp -s "$ORIG/$f" "$root/$f" || echo "$f"; done | sed "s/^/M$TAB/" >> "$B/$lab.ch"
    if [ "$mode" = changed ]; then
      if [ -f "$B/$lab/DELETE_THESE.txt" ]; then
        sed 's/\r$//; s|^\./||' "$B/$lab/DELETE_THESE.txt" | grep -v '^$' | LC_ALL=C sort > "$B/$lab.del"
        LC_ALL=C comm -12 "$W/old.lst" "$B/$lab.del" | sed "s/^/D$TAB/" >> "$B/$lab.ch"
        LC_ALL=C comm -13 "$W/old.lst" "$B/$lab.del" | sed "s/^/REVIEW delete-list entry of branch $lab matches no file in the base (not applied): /" >> "$W/m_opsnote"
      fi
    else
      LC_ALL=C comm -23 "$W/old.lst" "$B/$lab.lst" | sed "s/^/D$TAB/" >> "$B/$lab.ch"
    fi
    awk -F"$TAB" -v l="$lab" 'BEGIN{OFS="\t"} $2 !~ /^_ops\// {print $2, l, $1}' "$B/$lab.ch" >> "$W/m_all"
    awk -F"$TAB" -v l="$lab" '$2 ~ /^_ops\// && $2 != "_ops/STATE.md" {print "REVIEW ops-file-changed in branch " l " (not applied): " $2}' "$B/$lab.ch" >> "$W/m_opsnote"
    labels="$labels $lab"
  done
  cut -f1 "$W/m_all" | LC_ALL=C sort -u > "$W/m_files"
  : > "$W/m_plan"; : > "$W/m_applied"; : > "$W/m_conf"
  while IFS= read -r f; do
    F=$f awk -F"$TAB" 'BEGIN{OFS="\t"} $1==ENVIRON["F"] {print $2, $3}' "$W/m_all" > "$W/m_rows"
    read -r l0 k0 < "$W/m_rows"
    agree=1
    while IFS="$TAB" read -r l k; do
      [ "$k" = "$k0" ] || agree=0
      if [ "$agree" = 1 ] && [ "$k" != D ]; then cmp -s "$(cat "$W/m_root_$l")/$f" "$(cat "$W/m_root_$l0")/$f" || agree=0; fi
    done < "$W/m_rows"
    if [ "$agree" = 1 ]; then
      printf '%s\t%s\t%s\n' "$k0" "$f" "$l0" >> "$W/m_plan"
    else
      { printf 'CONFLICT %s:' "$f"; while IFS="$TAB" read -r l k; do printf ' %s=%s' "$l" "$k"; done < "$W/m_rows"; echo; } >> "$W/m_conf"
    fi
  done < "$W/m_files"
  # deletions first (a folder may turn into a file), then additions and changes
  awk -F"$TAB" '$1=="D"' "$W/m_plan" | while IFS="$TAB" read -r k f l; do
    rm -f -- "$f"; rmdir -p "$(dirname "$f")" 2>/dev/null
    printf 'D %s\n' "$f" >> "$W/m_applied"
  done
  awk -F"$TAB" '$1!="D"' "$W/m_plan" | while IFS="$TAB" read -r k f l; do
    if [ -d "$f" ] || ! mkdir -p "$(dirname "$f")" 2>/dev/null || ! cp -p "$(cat "$W/m_root_$l")/$f" "$f" 2>/dev/null; then
      echo "CONFLICT $f: $l=$k (could not place it: a file and a folder want the same path)" >> "$W/m_conf"
    else
      printf '%s %s\n' "$k" "$f" >> "$W/m_applied"
    fi
  done
  {
    echo "== MERGE REPORT (base version $bv, branches:$labels) =="
    for l in $labels; do echo "branch $l: $(n "$B/$l.ch") changed files; its project folder: $(cat "$W/m_root_$l")"; done
    echo "== APPLIED without conflict (A added, M modified, D deleted): $(n "$W/m_applied") =="
    cat "$W/m_applied"
    echo "== CONFLICTS: base copy left in place; each branch's copy is in its project folder above =="
    cat "$W/m_conf"
    cat "$W/m_opsnote"
    for l in $labels; do
      echo "== Summary written by branch $l (its 'Needs merge' items and what it could not verify) =="
      if [ -f "$B/$l/BRANCH_SUMMARY.md" ]; then cat "$B/$l/BRANCH_SUMMARY.md"; else echo "(none: this zip was not made by pack with a label)"; fi
    done
    for l in $labels; do
      echo "== STATE.md lines that differ in branch $l (< base, > branch). STATE.md is yours to merge by hand =="
      diff "$ORIG/_ops/STATE.md" "$(cat "$W/m_root_$l")/_ops/STATE.md" | grep '^[<>]' | head -n 30
    done
    echo "MERGE: $(n "$W/m_conf") conflicts"
  } > "$W/merge_report.txt"
  cat "$W/merge_report.txt"
}

case "${1:-}" in
  before) before ;;
  after) after_report; cat "$W/report.txt" ;;
  pack) pack "${2:-}" "${3:-}" ;;
  merge) shift; merge "$@" ;;
  *) echo "usage: sh _ops/snap.sh before | after | pack <outdir> [label] | merge <branch.zip> <branch.zip> ..."; exit 2 ;;
esac
