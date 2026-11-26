import zipfile, re, json, os
z = zipfile.ZipFile(r"D:\YZX\校园跑\lepao.apk")
names = z.namelist()

# 1) top-level dirs
tops = {}
for n in names:
    top = n.split("/")[0]
    tops[top] = tops.get(top, 0) + 1
print("=== top-level ===")
for k, v in sorted(tops.items(), key=lambda x: -x[1])[:20]:
    print(f"  {v:5d}  {k}")

# 2) assets tree
print("\n=== assets (first 60) ===")
assets = [n for n in names if n.startswith("assets/")]
print("assets count:", len(assets))
for n in assets[:60]:
    print("  ", n, z.getinfo(n).file_size)

# 3) db / json / bin under assets with size
print("\n=== candidate data files (json/db/sqlite/txt/bin/dat) ===")
cand = [n for n in assets if re.search(r"\.(json|db|sqlite|txt|dat|bin|xml|js)$", n, re.I)]
for n in sorted(cand, key=lambda x: -z.getinfo(x).file_size)[:40]:
    print(f"  {z.getinfo(n).file_size:9d}  {n}")
