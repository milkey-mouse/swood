"""A wrapper around FFMPEG to output audio files."""
from os.path import expanduser, basename, isfile, isdir, join
from threading import Thread
from itertools import chain
from PIL import Image
from tqdm import tqdm
import http.client
import subprocess
import functools
import operator
import platform
import tempfile
import queue
import time
import sys
import ssl
import os
import io

from .__init__ import patch_tqdm
from . import complain

# licensing note: ffmpeg itself it under the GPL
# it is not technically distributed with swood though

patch_tqdm(tqdm)

FFMPEG_TIMEOUT = 2

# AsynchronousFileReader based on code from
# http://stefaanlippens.net/python-asynchronous-subprocess-pipe-reading/


class AsynchronousFileReader(Thread):
    '''
    Helper class to implement asynchronous reading of a file
    in a separate thread. Pushes read lines on a queue to
    be consumed in another thread.
    '''

    def __init__(self, fd, outqueue, chunksize=4096):
        assert(isinstance(outqueue, queue.Queue))
        assert(callable(fd.readline))
        super().__init__(daemon=True)
        self._fd = fd
        self._queue = outqueue
        self._chunksize = chunksize

    def run(self):
        '''The body of the tread: read lines and put them on the queue.'''
        buf = self._fd.read(self._chunksize)
        while buf != b"":
            self._queue.put(buf)
            buf = self._fd.read(self._chunksize)

    def eof(self):
        '''Check whether there is no more content to expect.'''
        return not self.is_alive() and self._queue.empty()


class StreamInfo:

    def __getitem__(self, key):
        return vars(self)[key]

    def __setitem__(self, key, val):
        vars(self)[key] = val

    def __delitem__(self, key):
        del vars(self)[key]

    def __str__(self):
        return str(self.index)


class FFmpegFile:

    def __init__(self):
        self.show_debug = (os.environ.get("SWOOD_SHOW_FFMPEG") == "1")
        self.binaries = ["ffmpeg", "ffprobe"]
        self._cached_paths = None
        if os.name == "nt":
            self.appdata = expanduser("~/AppData/Local/swood")
            self.binaries = [fp + ".exe" for fp in self.binaries]
        else:
            self.appdata = expanduser("~/.swood")

    @staticmethod
    def _safe_close(ffproc):
        try:
            ffproc.stdin.close()
        except:
            pass
        try:
            ffproc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass
        ffproc.terminate()

    @staticmethod
    def find_program(prog):
        for path in os.environ["PATH"].split(os.pathsep):
            prog_location = join(path.strip('"'), prog)
            if isfile(prog_location):
                return prog_location
        return None

    @staticmethod
    def stdout_pass(stdout, queue, chunksize=4096):
        buf = stdout.read(chunksize)
        while buf:
            queue.put(buf)
            buf = stdout.read(chunksize)
        stdout.close()

    @staticmethod
    def parse_duration(timestr):
        multipliers = (3600, 60, 1)
        times = map(float, timestr.split(":"))
        return sum(a * b for a, b in zip(multipliers, times))

    @classmethod
    def stderr_pbar(cls, stderr, desc):
        with tqdm(total=1.0, dynamic_ncols=True, desc=desc, bar_format="{l_bar}{bar}|") as pbar:
            duration = None
            last_progress = 0
            for line in iter(stderr.readline, b""):
                if duration is None:
                    stripped = line.decode("utf-8").lstrip()
                    if stripped.startswith("Duration: "):
                        duration = cls.parse_duration(
                            stripped.split(" ")[1].rstrip(","))
                elif line.startswith(b"out_time="):
                    cut_time = line.decode("utf-8").split("=")[1].rstrip("\n")
                    progress = int(
                        round(cls.parse_duration(cut_time) / duration))
                    pbar.update(progress - last_progress)
                    last_progress = progress
        stderr.close()

    @property
    def ffmpeg_path(self):
        return self.program_paths[0]

    @property
    def ffprobe_path(self):
        return self.program_paths[1]

    @property
    def program_paths(self):
        if self._cached_paths is not None:
            return self._cached_paths
        self._cached_paths = tuple(map(self.find_program, self.binaries))
        if None in self._cached_paths:
            self._cached_paths = tuple(
                map(lambda x: join(self.appdata, x), self.binaries))
            if not all(map(isfile, self._cached_paths)):
                self._cached_paths = self._download_ffmpeg()
        return self._cached_paths

    def run_ffmpeg(self, *args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=None, check=True, popen=False, desc=None, exe=None, **kwargs):
        cmd = list(args)
        if exe is None:
            cmd[0:0] = (self.ffmpeg_path, "-hide_banner", "-y")
        else:
            cmd.insert(0, exe)

        if stderr is not None:
            ff_stderr = stderr
        elif desc is not None and exe is None and not popen:
            cmd.extend(("-progress", "pipe:2"))
            ff_stderr = subprocess.PIPE
        elif self.show_debug:
            ff_stderr = sys.stderr
        else:
            ff_stderr = subprocess.DEVNULL

        if self.show_debug:
            print(" ".join(cmd), file=sys.stderr)

        if popen:
            return subprocess.Popen(cmd, stdin=stdin, stdout=stdout, stderr=ff_stderr, **kwargs)
        else:
            if ff_stderr != subprocess.PIPE:
                return subprocess.run(cmd, stdin=stdin, stdout=stdout, stderr=ff_stderr, check=check, **kwargs)
            else:
                with subprocess.Popen(cmd, stdin=stdin, stdout=stdout, stderr=ff_stderr, **kwargs) as ffproc:
                    out_bytes = None
                    if stdout != subprocess.PIPE:
                        self.stderr_pbar(ffproc.stderr, desc)
                    else:
                        stdout_queue = queue.Queue()
                        stderr_thread = Thread(target=self.stderr_pbar,
                                               args=(ffproc.stderr, desc),
                                               daemon=True)
                        stdout_thread = AsynchronousFileReader(ffproc.stdout,
                                                               stdout_queue)
                        stderr_thread.start()
                        stdout_thread.start()
                        with io.BytesIO() as out_buf:
                            while not stdout_thread.eof():
                                while not stdout_queue.empty():
                                    out_buf.write(stdout_queue.get())
                                time.sleep(0.1)
                            out_bytes = out_buf.getvalue()
                        stderr_thread.join()
                        stdout_thread.join()
                        ffproc.terminate()
                    if check == True and ffproc.returncode != 0:
                        return subprocess.CalledProcessError(ffproc.returncode, ffproc.args, out_bytes)
                    return subprocess.CompletedProcess(ffproc.args, ffproc.returncode, stdout=out_bytes)

    def _download_ffmpeg(self, check_certs=True):
        with tempfile.TemporaryFile() as ffmpeg_zip:
            while True:
                if check_certs:
                    ssl_context = ssl.create_default_context()
                else:
                    ssl_context = ssl._create_unverified_context()
                try:
                    if os.name == "nt":
                        conn = http.client.HTTPSConnection("ffmpeg.zeranoe.com",
                                                           context=ssl_context)
                        if platform.architecture()[0] == "64bit":
                            conn.request(
                                "GET", "/builds/win64/static/ffmpeg-latest-win64-static.zip")
                        elif platform.architecture()[0] == "32bit":
                            conn.request(
                                "GET", "/builds/win32/static/ffmpeg-latest-win32-static.zip")
                        else:
                            raise complain.ComplainToUser(
                                "Unsupported architecture for FFMPEG")
                    elif os.name == "posix":
                        conn = http.client.HTTPSConnection("johnvansickle.com",
                                                           context=ssl_context)
                        if platform.architecture()[0] == "64bit":
                            conn.request(
                                "GET", "/ffmpeg/builds/ffmpeg-git-64bit-static.tar.xz")
                        elif platform.architecture()[0] == "32bit":
                            conn.request(
                                "GET", "/ffmpeg/builds/ffmpeg-git-32bit-static.tar.xz")
                        else:
                            raise complain.ComplainToUser(
                                "Unsupported architecture for FFMPEG")
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
                    break
                except ssl.SSLError:
                    print("The SSL certificate for the server is invalid.",
                          file=sys.stderr)
                    print("Someone might be doing something malicious!",
                          file=sys.stderr)
                    download_insecurely = None
                    while download_insecurely is None:
                        print(
                            "Do you still want to download FFmpeg insecurely? (Y/N): ", file=sys.stderr)
                        r = input().lower()
                        if r in ("yes", "y", "true", "1"):
                            download_insecurely = True
                        elif r in ("no", "n", "false", "0"):
                            download_insecurely = False
                    if download_insecurely:
                        return self._download_ffmpeg(check_certs=False)
                    else:
                        raise complain.ComplainToUser(
                            "Canceled FFmpeg download")
                except ConnectionError:
                    raise complain.ComplainToUser(
                        "There was an error while connecting to the server. Try again later.")
                except http.client.HTTPException:
                    raise complain.ComplainToUser(
                        "An unknown error occurred while downloading ffmpeg.")
            ffmpeg_zip.seek(0)

            if not isdir(self.appdata):
                os.mkdir(self.appdata)

            if os.name == "nt":
                return self.extract_zip(ffmpeg_zip)
            elif os.name == "posix":
                return self.extract_tar(ffmpeg_zip)

    def extract_zip(self, ffmpeg_zip):
        import zipfile
        try:
            with tqdm(desc="Searching archive", dynamic_ncols=True, unit="B", unit_scale=True) as pbar:
                with zipfile.ZipFile(ffmpeg_zip) as zf:
                    zipped_binaries = [fn for fn in zf.infolist() if any(
                        map(fn.filename.endswith, self.binaries))]
                    if len(zipped_binaries) != len(self.binaries):
                        raise complain.ComplainToUser(
                            "Could not locate binaries in archive")
                    pbar.total = sum(fn.file_size for fn in zipped_binaries)
                    for fn in zipped_binaries:
                        out_name = basename(fn.filename)
                        pbar.desc = "Extracting '{}'".format(out_name)
                        out_name = join(self.appdata, out_name)
                        with zf.open(fn) as zipped, open(out_name, "wb") as unzipped:
                            while True:
                                buf = zipped.read(4096)
                                if buf:
                                    unzipped.write(buf)
                                    pbar.update(len(buf))
                                else:
                                    break
        except zipfile.BadZipFile:
            raise complain.ComplainToUser("Zip file is corrupted")
        return tuple(join(self.appdata, x) for x in self.binaries)

    def extract_tar(self, ffmpeg_zip):
        import tarfile
        try:
            with tqdm(desc="Searching archive", dynamic_ncols=True, unit="B", unit_scale=True) as pbar:
                with tarfile.open(fileobj=ffmpeg_zip, mode="r:xz") as tf:
                    zipped_binaries = [fn for fn in tf.getmembers() if any(
                        map(fn.name.endswith, self.binaries))]
                    if len(zipped_binaries) != len(self.binaries):
                        raise complain.ComplainToUser(
                            "Could not locate binaries in archive")
                    pbar.total = sum(fn.size for fn in zipped_binaries)
                    for fn in zipped_binaries:
                        out_name = basename(fn.filename)
                        pbar.desc = "Extracting '{}'".format(out_name)
                        out_name = join(self.appdata, out_name)
                        with tf.extractfile(fn) as zipped, open(out_name, "wb") as unzipped:
                            while True:
                                buf = zipped.read(4096)
                                if buf:
                                    unzipped.write(buf)
                                    pbar.update(len(buf))
                                else:
                                    break
                        # set execution bits
                        os.chmod(out_name, 0o700)
        except tarfile.ExtractError:
            raise complain.ComplainToUser("Tarball can't be extracted")
        return tuple(join(self.appdata, x) for x in self.binaries)


class MediaInfo(FFmpegFile):

    def __init__(self, filename):
        super().__init__()
        if isinstance(filename, str):
            ffprobe = self.run_ffmpeg("-show_streams", filename,
                                      stdout=subprocess.PIPE, exe=self.ffprobe_path)
        else:
            ffprobe = self.run_ffmpeg("-show_streams", "-", stdin=filename,
                                      stdout=subprocess.PIPE, exe=self.ffprobe_path)
        ai = None
        self.streams = []
        if self.show_debug:
            print(ffprobe.stdout.decode("utf-8"), file=sys.stderr)
        for line in ffprobe.stdout.decode("utf-8").replace("\r\n", "\n").split("\n"):
            if line == "[STREAM]":
                ai = StreamInfo()
            elif line == "[/STREAM]":
                self.streams.append(ai)
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


class AudioFile(FFmpegFile):

    def __init__(self, filename, mode="r", streams=None, channels=1, sample_rate=96000, in_format=None, out_format=None):
        super().__init__()
        self.sample_rate = sample_rate
        self.channels = channels
        self.name = filename

        self._is_buffer = not isinstance(filename, str)
        self._ffproc = None

        if self._is_buffer:
            if in_format is None:
                raise ValueError(
                    "Must specify in_format for a stream input")
            else:
                self.in_format = ("-f", in_format)
        else:
            if in_format is None:
                self.in_format = ()
            else:
                if self.show_debug:
                    print(
                        "Warning: Stream format specified for file input", file=sys.stderr)
                self.in_format = ("-f", in_format)

        if out_format is None:
            self.out_format = ()
        else:
            self.out_format = ("-f", out_format)

        if streams is None:
            self.map = ()
        elif isinstance(streams, (int, StreamInfo)):
            self.map = ("-map", "0:{}".format(streams))
        else:
            self.map = tuple(chain.from_iterable(
                ("-map", "0:" + str(x)) for x in streams))

        if mode in ("r", "rb"):
            self.mode = "r"
        elif mode in ("w", "wb"):
            self.mode = "w"
        else:
            raise ValueError("invalid mode: '{}'".format(self.mode))

    @property
    def ffproc(self):
        # Lazy-load the FFmpeg process so we can do a direct
        # transfer (via CLI args) if it's file-to-file or buffer-to-buffer
        if self._ffproc is not None:
            return self._ffproc
        elif self.mode == "r":
            if self._is_buffer:
                self._ffproc = self.run_ffmpeg(*self.in_format, "-i", "-",
                                               *self.out_format, *self.map, "-",
                                               stdin=self.name, stdout=subprocess.PIPE, popen=True)
            else:
                self._ffproc = self.run_ffmpeg(*self.in_format, "-i", self.name,
                                               *self.out_format, *self.map, "-",
                                               stdout=subprocess.PIPE, popen=True)
        else:
            if self._is_buffer:
                self._ffproc = self.run_ffmpeg(*self.in_format, "-i", "-",
                                               *self.out_format, *self.map, "-",
                                               stdin=subprocess.PIPE, stdout=self.name, popen=True)
            else:
                self._ffproc = self.run_ffmpeg(*self.in_format, "-i", "-",
                                               *self.out_format, *self.map, self.name,
                                               stdin=subprocess.PIPE, popen=True)
        return self._ffproc

    def read(self):
        if self.mode == "w":
            return io.UnsupportedOperation("not readable")
        else:
            self.ffproc.stdout.read()

    def write(self, buf):
        if self.mode == "r":
            return io.UnsupportedOperation("not writeable")
        else:
            self.ffproc.stdin.write(buf)

    def flush(self):
        try:
            if self._ffproc is not None and self.ffproc.poll() is None:
                self.ffproc.stdin.flush()
        except:
            pass

    def close(self):
        if self._ffproc is not None and self.ffproc.poll() is None:
            self._safe_close(self.ffproc)

    def tofile(self, filename, desc=None):
        if self.mode == "w":
            return io.UnsupportedOperation("not readable")
        if self._is_buffer:
            self.run_ffmpeg(*self.in_format, "-i", "-", *self.out_format,
                            *self.map, filename, stdin=self.name, desc=desc)
        else:
            self.run_ffmpeg(*self.in_format, "-i", self.name,
                            *self.out_format, *self.map, filename, desc=desc)

    def tobuffer(self, desc=None):
        if self.mode == "w":
            return io.UnsupportedOperation("not readable")
        if self.out_format is None:
            return ValueError("No format specified for stream output")
        if self._is_buffer:
            return self.run_ffmpeg(*self.in_format, "-i", "-",
                                   *self.out_format, *self.map, "-",
                                   stdin=self.name, stdout=subprocess.PIPE, desc=desc).stdout
        else:
            return self.run_ffmpeg(*self.in_format, "-i", self.name,
                                   *self.out_format, *self.map, "-",
                                   stdout=subprocess.PIPE, desc=desc).stdout

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False


class VideoFile(FFmpegFile):

    def __init__(self, filename, mode="r", streams=None, width=1920, height=1080, fps=30, format=None):
        super().__init__()
        self.fps = fps
        self.size = (width, height)
        self._bytes_per_frame = width * height * 3
        self._is_buffer = not isinstance(filename, str)
        self.format = format
        self._ffproc = None

        self.video_format = ("-f", "rawvideo", "-pix_fmt", "rgb24",
                             "-s:v", "{}x{}".format(*self.size), "-r", str(fps))

        if mode in ("r", "rb"):
            self.mode = "w"
        elif mode in ("w", "wb"):
            self.mode = "w"
        else:
            raise ValueError("invalid mode: '{}'".format(self.mode))

        if streams is None:
            self.map = ()
        elif isinstance(streams, (int, StreamInfo)):
            self.map = ("-map", "0:{}".format(streams))
        else:
            self.map = tuple(chain.from_iterable(
                ("-map", "0:" + str(x)) for x in streams))

    @property
    def ffproc(self):
        # Lazy-load the FFmpeg process so we can do a direct
        # transfer (via CLI args) if it's file-to-file or buffer-to-buffer

        # convert raw 24bpp RGB data to ffmpeg default format for file ext or vice versa
        # (raw because PIL has no encoders in the Windows precompiled installer)

        if self._ffproc is not None:
            return self._ffproc
        elif self.mode == "r":
            if self._is_buffer:
                if self.format is None:
                    raise ValueError("Must specify a format for buffer input")
                self._ffproc = self.run_ffmpeg("-f", self.format, "-i", "-", *self.video_format, *self.map,
                                               "-", stdin=self.name, stdout=subprocess.PIPE, popen=True)
            else:
                self._ffproc = self.run_ffmpeg("-i", self.name, *self.video_format,
                                               *self.map, "-", stdout=subprocess.PIPE, popen=True)
        else:
            if self._is_buffer:
                self._ffproc = run_ffmpeg(*self.video_format, "-i", "-", *self.map, "-",
                                          stdin=subprocess.PIPE, stdout=self.name, popen=True)
            else:
                self._ffproc = run_ffmpeg(*self.video_format, "-i", "-", *self.map,
                                          self.name, stdin=subprocess.PIPE, popen=True)
        return self._ffproc

    def write(self, im):
        if self.mode == "r":
            return io.UnsupportedOperation("not writeable")
        elif im.size != self.size:
            raise ValueError(
                "Wrong resolution for video ({}x{} needed)".format(*self.size))
        if im.mode == "RGB":
            self.ffproc.stdin.write(im.tobytes())
        else:
            self.ffproc.stdin.write(im.convert("RGB").tobytes())

    def read(self):
        if self.mode == "w":
            return io.UnsupportedOperation("not readable")
        else:
            buf = self.ffproc.stdout.read(self._bytes_per_frame)
            if buf is None or len(buf) != self._bytes_per_frame:
                return None
            else:
                return Image.frombuffer("RGB", self.size, buf, "raw", "RGB", 0, 1)

        self._safe_close(self.ffproc)
        self.ffproc = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False
