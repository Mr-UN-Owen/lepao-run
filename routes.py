import zipfile, re
z = zipfile.ZipFile(r"D:\YZX\校园跑\lepao.apk")
targets = [n for n in z.namelist() if n == "classes.dex" or n.startswith("lib/")]
pat = re.compile(rb"[ -~]{5,}")
route = re.compile(r"^(?:[A-Z][A-Za-z0-9]{1,24}/)+[A-Za-z][A-Za-z0-9_]{1,40}$")
hits = set()
for n in targets:
    if z.getinfo(n).file_size > 60_000_000: continue
    for m in pat.finditer(z.read(n)):
        s = m.group().decode("ascii","replace")
        if route.match(s) and ("chool" in s or "ogin" in s or "Run" in s):
            hits.add(s)
print("=== route-like strings (", len(hits), ") ===")
for s in sorted(hits): print("  ", s)
