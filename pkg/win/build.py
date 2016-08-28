import subprocess
import requests
import tarfile
import shutil
import nsist
import yarg
import glob
import sys
import os

# patch pyNSIST bug with wheel filename parsing

# nsist.pypi.WheelDownloader.score_platform


def pbw_patched(self, release_list):
    best_score = (0, 0, 0)
    best = None
    for release in release_list:
        if release.package_type != 'wheel':
            continue

        *_, interpreter, abi, platform = release.filename[:-4].split("-")

        if abi.startswith(interpreter):  # e.g. cp35m
            abi = "abi3"

        score = (self.score_platform(platform),
                 self.score_abi(abi),
                 self.score_interpreter(interpreter)
                 )
        if any(s == 0 for s in score):
            continue

        if score > best_score:
            best = release
            best_score = score

    print("Using wheel {}".format(best.filename))
    return best

nsist.pypi.WheelDownloader.pick_best_wheel = pbw_patched

latest_python = 0
while requests.head("https://www.python.org/ftp/python/3.5.{0}/python-3.5.{0}-embed-win32.zip".format(latest_python + 1)).status_code == 200:
    latest_python += 1

latest_python = "3.5.{}".format(latest_python)

print("python version: {}".format(latest_python))

latest_commit = None

if "--stable" in sys.argv:
    releases = yarg.get("swood").latest_release
    version = releases[0].release_id
else:
    try:
        old_dir = os.getcwd()
        os.chdir("../..")
        latest_commit = subprocess.run(["git", "rev-parse", "--short=6", "HEAD", "-n=1"],
                                       stdout=subprocess.PIPE,
                                       check=True).stdout.decode("utf-8").rstrip("\n").rstrip("\r")
        branch_name = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                                     stdout=subprocess.PIPE,
                                     check=True).stdout.decode("utf-8").rstrip("\n").rstrip("\r")
        os.chdir(old_dir)
        version = "experimental ({}-{})".format(branch_name, latest_commit)
    except subprocess.CalledProcessError:
        version = "???"

print("swood version: {}".format(version))

# copy swood into pkgs folder
print("Copying source files")

if os.path.isdir("pynsist_pkgs"):
    shutil.rmtree("pynsist_pkgs")
os.mkdir("pynsist_pkgs")
os.mkdir("pynsist_pkgs/swood")
printed_ver = version + " (windows installer)"

if "--stable" in sys.argv:
    pkg_url = next(r.url for r in releases if r.url.endswith(".tar.gz"))
    r = requests.get(pkg_url, stream=True)
    with open("swood.tar.gz", 'wb') as f:
        for chunk in r.iter_content(chunk_size=1024):
            if chunk:  # filter out keep-alive new chunks
                f.write(chunk)
    with tarfile.open("swood.tar.gz") as pkg_tar:
        for fp in pkg_tar:
            if fp.isfile() and "/swood/" in fp.name and fp.name.endswith(".py"):
                outp = os.path.join("pynsist_pkgs/swood",
                                    os.path.basename(fp.name))
                print("{} -> {}".format(fp.name, outp))
                with open(outp, "w") as out:
                    extracted = pkg_tar.extractfile(fp).read().decode("utf-8")
                    out.write(extracted.replace(
                        "???", printed_ver).replace("\r\n", "\n"))
    os.remove("swood.tar.gz")
else:
    for fp in glob.iglob("../../swood/*.*"):
        outp = os.path.join("pynsist_pkgs/swood", os.path.basename(fp))
        print("{} -> {}".format(fp, outp))
        with open(fp) as infile, open(outp, "w") as outfile:
            for line in infile:
                outfile.write(line.replace("???", printed_ver))

print("Adding _user_path patch")
try:
    from nsist import _system_path
    spf = nsist._system_path.__file__
except:
    spf = os.path.join(os.path.dirname(nsist.__file__), "_system_path.py")
with open(spf) as syspath, open("pynsist_pkgs/_user_path.py", "w") as usrpath:
    for line in syspath:
        usrpath.write(syspath.read().replace(
            "allusers=True", "allusers=False"))

if not os.path.isdir("../build"):
    os.mkdir("../build")

for bitness in (32, 64):
    print("Building {}-bit version".format(bitness))
    if os.path.isdir("build"):
        shutil.rmtree("build")
    os.mkdir("build")
    shutil.copy("swood.ico", "build/swood.ico")
    shutil.copy("template.nsi", "build/template.nsi")
    nsist.InstallerBuilder(
        appname="swood",
        version=version,
        icon="swood.ico",
        shortcuts={},
        commands={"swood": {"entry_point": "swood:run_cmd"}},
        packages=["progressbar"],
        pypi_wheel_reqs=["numpy==1.11.1", "Pillow==3.3.1", "mido==1.1.15",
                         "python-utils==2.0.0", "six==1.10.0", "pyFFTW==0.10.4"],
        extra_files=[],
        py_version=latest_python,
        py_bitness=bitness,
        py_format="bundled",
        build_dir="./build",
        nsi_template="template.nsi",
        installer_name=os.path.abspath(
            "../build/swood-{}-{}bit.exe".format(latest_commit if latest_commit is not None else version, bitness)),
        exclude=[]).run(makensis=True)
    print("Cleaning up")
    shutil.rmtree("build")
shutil.rmtree("pynsist_pkgs")