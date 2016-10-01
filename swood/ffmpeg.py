"""A wrapper around FFMPEG to stitch frames into a video."""
from tqdm import tqdm
import http.client
import subprocess
import platform
import tempfile
import sys
import ssl
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
        try:
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
        except ssl.SSLError:
            raise complain.ComplainToUser("The SSL certificate for the ffmpeg server is invalid. Someone might be doing something nasty!")
        except ConnectionError:
            raise complain.ComplainToUser("There was an error while connecting to the server. Try again later.")
        except http.client.HTTPException:
            raise complain.ComplainToUser("An unknown error occurred while downloading ffmpeg.")
        ffmpeg_zip.seek(0)

        files_to_extract = ("ffmpeg", "ffprobe")

        nt = (os.name == "nt")
        if nt: files_to_extract = tuple(map(lambda x: x + ".exe", files_to_extract))
        swood_appdata = os.path.expanduser("~/AppData/Local/swood" if nt else "~/.swood")
        if not os.path.isdir(swood_appdata):
            os.mkdir(swood_appdata)
        if os.name == "nt":
            import zipfile
            try:
                with tqdm(desc="Searching archive", dynamic_ncols=True, unit="B", unit_scale=True) as pbar:
                    with zipfile.ZipFile(ffmpeg_zip) as zf:
                        binaries = tuple(fn for fn in zf.infolist() if any(map(fn.filename.endswith, files_to_extract)))
                        if len(binaries) < 2:
                            raise complain.ComplainToUser("Could not find ffmpeg/ffprobe in archive")
                        pbar.total = sum(fn.file_size for fn in binaries)
                        for fn in binaries:
                            extracted_name = os.path.basename(fn.filename)
                            pbar.desc = "Extracting '{}'".format(extracted_name)
                            with zf.open(fn) as zipped, open(os.path.join(swood_appdata, extracted_name), "wb") as unzipped:
                                while True:
                                    buf = zipped.read(4096)
                                    if buf:
                                        unzipped.write(buf)
                                        pbar.update(len(buf))
                                    else:
                                        break
            except zipfile.BadZipFile:
                raise complain.ComplainToUser("Zip file is corrupted")
            
            return os.path.join(swood_appdata, "ffmpeg.exe"), os.path.join(swood_appdata, "ffprobe.exe")
        elif os.name == "posix":
            import tarfile
            try:
                with tqdm(desc="Searching archive", dynamic_ncols=True, unit="B", unit_scale=True) as pbar:
                    with tarfile.open(fileobj=ffmpeg_zip, mode="r:xz") as tf:
                        binaries = tuple(fn for fn in tf.getmembers() if any(map(fn.name.endswith, files_to_extract)))
                        if len(binaries) < 2:
                            raise complain.ComplainToUser("Could not find ffmpeg/ffprobe in archive")
                        pbar.total = sum(fn.size for fn in binaries)
                        for fn in binaries:
                            extracted_name = os.path.basename(fn.name)
                            pbar.desc = "Extracting '{}'".format(extracted_name)
                            with tf.extractfile(fn) as zipped, open(os.path.join(swood_appdata, extracted_name), "wb") as unzipped:
                                while True:
                                    buf = zipped.read(4096)
                                    if buf:
                                        unzipped.write(buf)
                                        pbar.update(len(buf))
                                    else:
                                        break
                            # set execution bits
                            os.chmod(os.path.join(swood_appdata, extracted_name), 0o700)
            except tarfile.ExtractError:
                raise complain.ComplainToUser("Tarball can't be extracted")
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

class StreamInfo:
    def __getitem__(self, key):
        return vars(self)[key]

    def __setitem__(self, key, val):
        vars(self)[key] = val
    
    def __delitem__(self, key):
        del vars(self)[key]

def ffprobe(filename):
    if isinstance(filename, str):
        cmd = [ffprobe_path, "-show_streams", filename]
        ffp_stdin = subprocess.DEVNULL
    else:
        cmd = [ffprobe_path, "-show_streams", "-"]
        ffp_stdin = filename
    ffprobe = subprocess.run(cmd, stdin=ffp_stdin, stdout=subprocess.PIPE, check=True)

    ai = None
    streams = []
    for line in ffprobe.stdout.decode("utf-8").replace("\r\n", "\n").split("\n"):
        if line == "[STREAM]":
            ai = StreamInfo()
        elif line == "[/STREAM]":
            streams.append(ai)
            ai = None
        elif ai is not None:
            k, v = line.split("=")
            try:
                ai[k] = int(v)
            except ValueError:
                try:
                    ai[k] = float(v)
                except ValueError:
                    ai[k] = v
    return streams

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
        return subprocess.Popen(cmd, stdin=stdin, stdout=stdout, stderr=ff_stderr, **kwargs)
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

class VideoFile:
    def __init__(self, filename, width=1920, height=1080, fps=30):
        self.size = (width, height)
        resolution = "{}x{}".format(*self.size)
        # take in raw 24bpp RGB data (PIL has no encoders)
        # and output the default format for <filename>
        self.ffproc = run_ffmpeg("-f", "rawvideo", "-pix_fmt", "rgb24",
                                 "-s:v", resolution, "-r", str(fps), "-i", "-",
                                 filename, stdin=subprocess.PIPE, popen=True)

    def write(self, im):
        if im.size != self.size:
            raise ValueError("Wrong resolution for video ({}x{} needed)".format(*self.size))
        if im.mode == "RGB":
            self.ffproc.stdin.write(im.tobytes())
        else:
            self.ffproc.stdin.write(im.convert("RGB").tobytes())            

    def close(self):
        if self.ffproc is not None and self.ffproc.poll() is None:
            try:
                self.ffproc.stdin.close()
            except:
                pass
            try:
                self.ffproc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
            self.ffproc.terminate()
            self.ffproc = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return True