import zipfile, re
z = zipfile.ZipFile(r"D:\YZX\校园跑\lepao.apk")
names = z.namelist()
targets = [n for n in names if n == "classes.dex" or n.startswith("lib/")]
print("scan targets:", len(targets))
pat = re.compile(rb"[ -~]{4,}")
found_school = set()
found_api = set()
for n in targets:
    sz = z.getinfo(n).file_size
    if sz > 60_000_000:
        continue
    data = z.read(n)
    for m in pat.finditer(data):
        s = m.group()
        if b"school" in s.lower() or b"School" in s:
            found_school.add(s.decode("ascii", "replace"))
        if b"/v3/api.php" in s:
            found_api.add(s.decode("ascii", "replace"))
print("\n=== strings containing 'school' (", len(found_school), ") ===")
for s in sorted(found_school)[:80]:
    print("  ", s[:160])
print("\n=== strings containing /v3/api.php (", len(found_api), ") ===")
for s in sorted(found_api)[:80]:
    print("  ", s[:160])
