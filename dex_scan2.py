import zipfile, re
z = zipfile.ZipFile(r"D:\YZX\校园跑\lepao.apk")
targets = [n for n in z.namelist() if n == "classes.dex" or n.startswith("lib/")]
blob = b""
for n in targets:
    if z.getinfo(n).file_size < 60_000_000:
        blob += z.read(n)
print("scanned bytes:", len(blob))
for kw in ["首都经济贸易", "经济贸易大学", "首经贸"]:
    b = kw.encode("utf-8")
    print(f"  {kw}: {blob.count(b)} hits")
# look for school-list-ish identifiers
for kw in [b"getSchoolList", b"schoolList", b"SchoolListInfo", b"nearbySchool", b"getSchool"]:
    print(f"  {kw.decode()}: {blob.count(kw)} hits")
# how many distinct 'School/xxx' routes
routes = set(re.findall(rb"School/[A-Za-z]{3,30}", blob))
print("\nSchool/* routes:", sorted(x.decode() for x in routes))
