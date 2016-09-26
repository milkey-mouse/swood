"""A wrapper around FFMPEG to stitch frames into a video."""
from tqdm import tqdm
import http.client
import subprocess
import platform
import tempfile
import sys
import os

from .__init__ import patch_tqdm
from . import complain

# licensing note: ffmpeg itself it under the GPL
# it is not technically distributed with swood though

patch_tqdm(tqdm)

def find_program(prog):
    for path in os.environ["PATH"].split(os.pathsep):
        prog_location = os.path.join(path.strip('"'), prog)
        if os.path.isfile(prog_location):
            return prog_location
        elif os.name == "nt" and os.path.isfile(prog_location + ".exe"):
            return prog_location + ".exe"
    return None

def download_ffmpeg():
    with tempfile.TemporaryFile() as ffmpeg_zip:
        if os.name == "nt":
            conn = http.client.HTTPSConnection("ffmpeg.zeranoe.com")
            if platform.architecture()[0] == "64bit":
                conn.request("GET", "/builds/win64/static/ffmpeg-latest-win64-static.zip")
            elif platform.architecture()[0] == "32bit":
                conn.request("GET", "/builds/win64/static/ffmpeg-latest-win32-static.zip")
            else:
                raise complain.ComplainToUser("Can't detect architecture")
        elif os.name == "posix":
            conn = http.client.HTTPSConnection("johnvansickle.com")
            if platform.architecture()[0] == "64bit":
                conn.request("GET", "/ffmpeg/builds/ffmpeg-git-64bit-static.tar.xz")
            elif platform.architecture()[0] == "32bit":
                conn.request("GET", "/ffmpeg/builds/ffmpeg-git-32bit-static.tar.xz")
            else:
                raise complain.ComplainToUser("Can't detect architecture")
        else:
            raise complain.ComplainToUser("Can't detect OS")
        resp = conn.getresponse()
        zip_len = int(resp.getheader("content-length"))
        with tqdm(desc="Downloading ffmpeg", total=zip_len, dynamic_ncols=True, unit="B", unit_scale=True) as pbar:
            while True:
                buf = resp.read(4096)
                if buf:
                    ffmpeg_zip.write(buf)
                    pbar.update(4096)
                else:
                    break
        ffmpeg_zip.seek(0)
        if os.name == "nt":
            import zipfile
            with zipfile.ZipFile(ffmpeg_zip) as zf:
                swood_appdata = os.path.expanduser("~/AppData/Local/swood")
                if not os.path.isdir(swood_appdata):
                    os.mkdir(swood_appdata)
                try:
                    ffmpeg_exe = next(fn for fn in zf.infolist() if fn.filename.endswith("ffmpeg.exe"))
                    ffprobe_exe = next(fn for fn in zf.infolist() if fn.filename.endswith("ffprobe.exe"))
                except StopIteration:
                    raise complain.ComplainToUser("Could not find ffmpeg binary in zip file")
                with tqdm(desc="Extracting ffmpeg", total=ffmpeg_exe.file_size + ffprobe.file_size, dynamic_ncols=True, unit="B", unit_scale=True) as pbar:
                    with zf.open(ffmpeg_exe) as zipped_exe, open(os.path.join(swood_appdata, "ffmpeg.exe"), "wb") as unzipped_exe:
                        while True:
                            buf = zipped_exe.read(4096)
                            if buf:
                                unzipped_exe.write(buf)
                                pbar.update(len(buf))
                            else:
                                break
                    with zf.open(ffprobe_exe) as zipped_exe, open(os.path.join(swood_appdata, "ffprobe.exe"), "wb") as unzipped_exe:
                        while True:
                            buf = zipped_exe.read(4096)
                            if buf:
                                unzipped_exe.write(buf)
                                pbar.update(len(buf))
                            else:
                                break
            return os.path.join(swood_appdata, "ffmpeg.exe"), os.path.join(swood_appdata, "ffprobe.exe")
        elif os.name == "posix":
            import tarfile
            if not os.path.isdir(os.path.expanduser("~/.swood")):
                os.mkdir(os.path.expanduser("~/.swood"))
            with tarfile.open(mode="r:xz", fileobj=ffmpeg_zip) as tf:
                try:
                    ffmpeg_bin = next(fn for fn in tf.getmembers() if fn.name.endswith("ffmpeg"))
                    ffprobe_bin = next(fn for fn in tf.getmembers() if fn.name.endswith("ffprobe"))
                except StopIteration:
                    raise complain.ComplainToUser("Could not find ffmpeg/ffprobe binary in tarball")
                with tqdm(desc="Extracting ffmpeg", total=ffmpeg_bin.size + ffprobe_bin.size, dynamic_ncols=True, unit="B", unit_scale=True) as pbar:
                    with tf.extractfile(ffmpeg_bin) as zipped_exe, open(os.path.expanduser("~/.swood/ffmpeg"), "wb") as unzipped_exe:
                        while True:
                            buf = zipped_exe.read(4096)
                            if buf:
                                unzipped_exe.write(buf)
                                pbar.update(len(buf))
                            else:
                                break
                    with tf.extractfile(ffprobe_bin) as zipped_exe, open(os.path.expanduser("~/.swood/ffprobe"), "wb") as unzipped_exe:
                        while True:
                            buf = zipped_exe.read(4096)
                            if buf:
                                unzipped_exe.write(buf)
                                pbar.update(len(buf))
                            else:
                                break
                    # set execution bits
                    os.chmod(os.path.expanduser("~/.swood/ffmpeg"), 0o700)
                    os.chmod(os.path.expanduser("~/.swood/ffprobe"), 0o700)
            return os.path.expanduser("~/.swood/ffmpeg"), os.path.expanduser("~/.swood/ffprobe")

ffmpeg_path = find_program("ffmpeg")
ffprobe_path = find_program("ffprobe")
if ffmpeg_path is None or ffprobe_path is None:
    if os.path.isfile(os.path.expanduser("~/AppData/Local/swood/ffmpeg.exe")) and os.path.isfile(os.path.expanduser("~/AppData/Local/swood/ffprobe.exe")):
        ffmpeg_path = os.path.expanduser("~/AppData/Local/swood/ffmpeg.exe")
        ffprobe_path = os.path.expanduser("~/AppData/Local/swood/ffprobe.exe")
    elif os.path.isfile(os.path.expanduser("~/.swood/ffmpeg")) and os.path.isfile(os.path.expanduser("~/.swood/ffprobe")):
        ffmpeg_path = os.path.expanduser("~/.swood/ffmpeg")
        ffprobe_path = os.path.expanduser("~/.swood/ffprobe")
    else:
        ffmpeg_path, ffprobe_path = download_ffmpeg()
else:
    if os.environ.get("SWOOD_SHOW_FFMPEG") is not None:
        print("Using ffmpeg from PATH ({})".format(ffmpeg_path))
        print("Using ffprobe from PATH ({})".format(ffprobe_path))

class AudioInfo:
    pass

def ffprobe(filename):
    if isinstance(filename, str):
        cmd = [ffprobe_path, "-show_streams", filename]
        ffp_stdin = subprocess.DEVNULL
    else:
        cmd = [ffprobe_path, "-show_streams", "-"]
        ffp_stdin = filename
    ffprobe = subprocess.run(cmd, stdin=ffp_stdin, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True)
    ai = AudioInfo()
    stream = False
    for line in ffprobe.stdout.decode("utf-8").replace("\r\n", "\n").split("\n"):
        if line == "[STREAM]":
            stream = True
        elif line == "[/STREAM]":
            break
        elif stream:
            k, v = line.split("=")
            try:
                vars(ai)[k] = int(v)
            except ValueError:
                try:
                    vars(ai)[k] = float(v)
                except ValueError:
                    vars(ai)[k] = v
    return ai

def run_ffmpeg(*args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=None, check=True, popen=False, **kwargs):
    cmd = list(args)
    cmd.insert(0, ffmpeg_path)
    cmd.append("-y")
    if os.environ.get("SWOOD_SHOW_FFMPEG") is not None:
        print(" ".join(cmd))
        ff_stderr = sys.stderr
    else:
        ff_stderr = subprocess.DEVNULL
    if popen:
        return subprocess.Popen(cmd, stdin=stdin, stdout=stdout, stderr=ff_stderr, check=check, **kwargs)
    else:
        return subprocess.run(cmd, stdin=stdin, stdout=stdout, stderr=ff_stderr, check=check, **kwargs)
        
def buffer_to_buffer(infile, format="s32le"):
    return run_ffmpeg("-i", "-", "-f", format, "-", stdin=infile, stdout=subprocess.PIPE).stdout

def buffer_to_file(infile, outfile):
    run_ffmpeg("-i", "-", outfile, stdin=infile)

def file_to_buffer(infile, format="s32le"):
    return run_ffmpeg("-i", infile, "-f", format, "-", stdout=subprocess.PIPE).stdout

def file_to_file(infile, outfile):
    run_ffmpeg("-i", infile, outfile)
