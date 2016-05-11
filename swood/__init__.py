from __future__ import print_function
import sys

if sys.version_info.major < 3 or (sys.version_info.major == 3 and sys.version_info.minor < 4):
    print("Sorry, swood.exe requires at least Python 3.4 to run correctly.")
    sys.exit(1)

from enum import Enum
import pkg_resources
import http.client
import collections
import importlib
import traceback
import operator
import math
import wave
import os

from PIL import Image
import progressbar
import numpy as np
import pyfftw
import mido


class ComplainToUser(Exception):
    pass


class FileSaveType(Enum):
    ARRAY_TO_DISK = 0
    ARRAY_IN_MEM = 1
    SMART_CACHING = 2


class NoteRenderer:
    def __init__(self, sample, alg=Image.BICUBIC, fullclip=False, threshold=0.075, cachesize=7.5):
        if threshold < 0:
            return ValueError("The threshold must be a positive number.")
        self.alg = alg
        self.sample = sample
        self.fullclip = fullclip

        self.cachesize = cachesize * sample.framerate
        self.threshold = int(threshold * sample.framerate)

        self.notecache = {}

    def zoom(self, img, multiplier):
        return np.asarray(img.resize((int(round(img.size[0] * multiplier)), self.sample.channels), resample=self.alg), dtype=np.int32)

    def render_note(self, note):
        scaled = self.zoom(self.sample.img, self.sample.maxfreq / note.pitch)
        if self.fullclip or len(scaled) < note.length + self.threshold:
            return scaled
        else:
            cutoffs = []
            for chan in range(self.sample.channels):
                # find the nearest/closest zero crossing within the threshold and continue until that
                sample_end = np.empty(self.threshold)
                for distance, val in enumerate(scaled[chan][note.length:note.length + self.threshold]):
                    sample_end[distance] = (val) + (distance * 30)
                cutoffs.append(np.argmin(sample_end))
            merged_channels = np.zeros((self.sample.channels, note.length + max(cutoffs)), dtype=np.int32)
            for chan in range(self.sample.channels):
                cutoff = note.length + cutoffs[chan]
                merged_channels[chan][:cutoff] = scaled[chan][:cutoff]
            return merged_channels

    def render(self, midi, filename, pbar=True, savetype=FileSaveType.ARRAY_TO_DISK, clear_cache=True):
        if self.fullclip:
            # leave a small buffer at the end with space for one more sample
            end_buffer = int(math.ceil(midi.maxpitch * len(self.sample)))
        else:
            end_buffer = self.threshold  # it has to cut off sounds at the threshold anyway
        output_length = midi.length + end_buffer

        if savetype == FileSaveType.SMART_CACHING:
            #output = CachedWavFile(output_length, filename, self.sample.framerate)
            raise ComplainToUser("Smart caching will be implemented in the future.")
        else:
            output = UncachedWavFile(output_length, filename, self.sample.framerate, self.sample.channels)

        if pbar:
            bar = progressbar.ProgressBar(widgets=[progressbar.Percentage(), " ", progressbar.Bar(), " ", progressbar.ETA()], max_value=midi.notecount)
            progress = 0

        caching = self.cachesize > 0

        if caching:
            tick = 8

        for time, notes in midi.notes:
            for note in notes:
                if hash(note) in self.notecache:
                    rendered_note = self.notecache[hash(note)]
                    rendered_note.used += 1  # increment the used counter each time for the "GC" below
                else:
                    rendered_note = CachedNote(time, self.render_note(note))
                    self.notecache[hash(note)] = rendered_note
                note_volume = note.volume / midi.maxvolume
                output.add_data(time, (rendered_note.data * note_volume).astype(np.int32), channel=-1)

                if pbar:
                    # increment progress bar
                    progress += 1
                    bar.update(progress)

            
            if caching:
                # cache "garbage collection":
                # if a CachedNote is more than 7.5 (default) seconds old it removes it from the cache to save mem(e)ory
                tick += 1
                if tick == 8:
                    tick = 0
                    for k in list(notecache.keys()):
                        if time - self.notecache[k].length > self.cachesize and self.notecache[k].used < 3:
                            del self.notecache[k]

        if clear_cache:
            self.notecache.clear()

        if savetype == FileSaveType.ARRAY_IN_MEM:
            return output.channels
        else:
            output.save()


def run_cmd():
    try:
        transpose = 0
        speed = 1.0
        threshold = 0.075
        binsize = 8192
        cachesize = 7.5
        fullclip = False
        alg = Image.BICUBIC
        if len(sys.argv) <= 3:

            try:
                version = pkg_resources.get_distribution("swood").version
            except pkg_resources.DistributionNotFound:
                version = "?"
            print("swood - the automatic ytpmv generator (v. {})".format(version))
            print("")
            print("usage: swood in_wav in_midi out_wav")
            print("  in_wav: a short wav file to use as the instrument for the midi")
            print("  in_midi: a midi to output with the wav sample as the instrument")
            print("  out_wav: location for the finished song as a wav")
            print("")
            print("options:")
            print("  --transpose=0      transpose the midi by n semitones")
            print("  --speed=1.0        speed up the midi by this multiplier")
            print("  --threshold=0.075  maximum amount of time after a note ends that it can go on for a smoother ending")
            print("  --binsize=8192     FFT bin size for the sample analysis; lower numbers make it faster but more off-pitch")
            print("  --cachesize=7.5    note cache size (seconds); lower could speed up repetitive songs, using more memory")
            print("  --linear           use a lower quality scaling algorithm that will be a little bit faster")
            print("  --fullclip         no matter how short the note, always use the full sample without cropping")
            print("  --optout           opt out of automatic bug reporting (or you can set the env variable SWOOD_OPTOUT)")
            if importlib.util.find_spec("swoodlive"):
                print("  --live             listen on a midi input and generate the output in realtime")
            return
        for arg in sys.argv[4:]:
            try:
                if arg == "--linear":
                    alg = Image.BILINEAR
                elif arg == "--fullclip":
                    fullclip = True
                elif arg == "--optout":
                    pass
                elif arg.startswith("--transpose="):
                    transpose = int(arg[len("--transpose="):])
                elif arg.startswith("--speed="):
                    speed = float(arg[len("--speed="):])
                elif arg.startswith("--threshold="):
                    threshold = float(arg[len("--threshold="):])
                elif arg.startswith("--binsize="):
                    binsize = int(arg[len("--binsize="):])
                else:
                    raise ComplainToUser("Unrecognized command-line option '{}'.".format(arg))
            except ValueError:
                raise ComplainToUser("Error parsing command-line option '{}'.".format(arg))

        for i in (1, 2):
            if not os.path.isfile(sys.argv[i]):
                ext = ".mid" if i == 2 else ".wav"
                if os.path.isfile(sys.argv[i] + ext):
                    sys.argv[i] += ext
                else:
                    raise ComplainToUser("No file found at path '{}'.".format(sys.argv[i]))
        if not sys.argv[3].endswith(".wav"):
            sys.argv[3] += ".wav"

        sample = Sample(sys.argv[1], binsize)
        midi = MIDIParser(sys.argv[2], sample, transpose, speed)
        renderer = NoteRenderer(sample, alg, fullclip, threshold, cachesize)
        renderer.render(midi, sys.argv[3])
    except Exception as you_tried:
        if isinstance(you_tried, ComplainToUser):
            print("Error: {}".format(you_tried))
        else:
            tb = traceback.format_exc()
            if "--optout" in sys.argv or os.environ.get("SWOOD_OPTOUT") is not None:
                print("Something went wrong. A bug report will not be sent because of your environment variable/CLI option.")
                print(tb)
            else:
                print("Something went wrong. A bug report will be sent to help figure it out. (see --optout)")
                try:
                    conn = http.client.HTTPSConnection("meme.institute")
                    conn.request("POST", "/swood/bugs/submit", tb)
                    resp = conn.getresponse().read().decode("utf-8")
                    if resp == "done":
                        print("New bug submitted!")
                    elif resp == "dupe":
                        print("This bug is already in the queue to be fixed.")
                    else:
                        raise Exception
                except Exception:
                    traceback.print_exc()
                    print("Well apparently we can't even send a bug report right. Sorry about that.")


if __name__ == "__main__":
    run_cmd()
