import subprocess
import twine.cli
import shutil
import sys
import os

version = None

with open("../setup.py") as swood_setup:
    for line in swood_setup:
        if "version=" in line:
            version = line.rstrip("\r\n")[line.index("version=") + 9:-2]

assert(version is not None)

old_version = version

try:
    version_ints = list(map(int, version.split(".")))
    version_ints[-1] += 1
    version = ".".join(map(str, version_ints))
except ValueError:
    pass

inp = input("Type a version number for the new version [{}]: ".format(version))
version = inp if len(inp) > 0 else version

with open("../setup.py") as oldsetup, open("../setup.py.tmp", "w") as newsetup:
    for line in oldsetup:
        if "version=" in line:
            newsetup.write(line.replace(old_version, version))
        else:
            newsetup.write(line)
shutil.move("../setup.py.tmp", "../setup.py")
print("Updated setup.py")

if os.path.isfile("../swood.egg-info/PKG-INFO"):
    with open("../swood.egg-info/PKG-INFO") as old_pkginfo, open("../swood.egg-info/PKG-INFO.tmp", "w") as new_pkginfo:
        for line in old_pkginfo:
            if line.startswith("Version:"):
                new_pkginfo.write(line.replace(old_version, version))
            else:
                new_pkginfo.write(line)
    shutil.move("../swood.egg-info/PKG-INFO.tmp", "../swood.egg-info/PKG-INFO")
    print("Updated PKG-INFO")

while True:
    inp = input("Publish to PyPI? (Y/n): ").lower()
    if inp in ("yes", "y"):
        os.chdir("..")
        subprocess.run([sys.executable, "setup.py", "sdist",
                        "--formats=gztar,bztar,zip"], check=True)
        os.chdir("dist")
        twine.cli.dispatch(["upload", *os.listdir()])
        os.chdir("..")
        shutil.rmdir("dist")
        break
    elif inp in ("no", "n", ""):
        break
