import subprocess
import requests
import tempfile
import tarfile
import shutil
import sys
import os

if os.name != "nt":
    print("Error: Can only build pillow-simd on a Windows system")

repo_url = "https://api.github.com/repos/uploadcare/pillow-simd/tags"
tarball_url = requests.get(repo_url).json()[0]["tarball_url"]
r = requests.head(tarball_url, allow_redirects=True)
for x in r.headers["content-disposition"].split(";"):
    if "filename=" in x:
        tarball_fn = os.path.join(tempfile.gettempdir(), x.strip()[9:])

if not os.path.isfile(tarball_fn):
    for fp in os.scandir():
        if "pillow-simd" in fp.name and fp.name.endswith(".tar.gz"):
            print("Removing outdated tarball {}".format(fp.name))
            os.remove(fp.path)
    print("Downloading tarball {}...".format(tarball_fn))
    r = requests.get(tarball_url, stream=True)
    with open(tarball_fn, 'wb') as f:
        for chunk in r.iter_content(chunk_size=1024):
            if chunk:  # filter out keep-alive new chunks
                f.write(chunk)
else:
    print("Using cached tarball {}".format(tarball_fn))

if os.path.isdir("pillow-simd"):
    shutil.rmtree("pillow-simd")

with tarfile.open(tarball_fn) as pkg_tar:
    for fp in pkg_tar:
        if fp.isfile():
            outp = os.path.join("pillow-simd", *fp.name.split("/")[1:])
            print("{} -> {}".format(fp.name, outp))
            os.makedirs(os.path.dirname(outp), exist_ok=True)
            with open(outp, "wb") as out:
                out.write(pkg_tar.extractfile(fp).read())

# no easy way to specify on the command line to not build default libs
with open("pillow-simd/setup.py") as infile, open("pillow-simd/setup.py.tmp", "w") as outfile:
    for line in infile:
        if line.startswith("        required ="):
            outfile.write("        required = set()\n")
        else:
            outfile.write(line)
shutil.move("pillow-simd/setup.py.tmp", "pillow-simd/setup.py")

owd = os.getcwd()
os.chdir("pillow-simd")
subprocess.run([sys.executable, "setup.py", "build"], check=True)
os.chdir(owd)

for fp in os.scandir("pillow-simd/build"):
    if fp.is_dir() and fp.name.startswith("lib."):
        build_dir = fp.path
        break

bitness = 64 if "amd64" in os.path.basename(build_dir) else 32

with tarfile.open("pillow-simd-{}bit.tar.gz".format(bitness), "w") as out_tar:
    for root, dirs, files in os.walk(build_dir):
        for fp in (os.path.join(root, p) for p in files):
            outp = os.path.relpath(fp, build_dir)
            print("{} -> {}".format(fp, outp))
            out_tar.add(fp, outp)

shutil.rmtree("pillow-simd")
# os.remove(tarball_fn)
