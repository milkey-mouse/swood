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

pyfftw.interfaces.cache.enable()


class ComplainToUser(Exception):
    pass


class DummyPbar:
    def update(i):
        pass


class FileSaveType(Enum):
    ARRAY_TO_DISK = 0
    ARRAY_IN_MEM = 1
    SMART_CACHING = 2


class Note:
    def __init__(self, length=None, pitch=None, volume=None, starttime=None):
        self.starttime = starttime
        self.length = length
        self.volume = volume
        self.pitch = pitch

    def __hash__(self):
        return hash((self.length, self.pitch))


class CachedNote:
    def __init__(self, length, rendered):
        self.used = 1
        self.length = length
        self.data = rendered

    def __len__(self):
        return len(self.data)


class UncachedWavFile:
    def __init__(self, length, filename, framerate, channels=1, dtype=np.int32):
        self.channels = np.zeros((channels, length), dtype=dtype)
        self.framerate = framerate
        self.filename = filename

    def add_data(self, start, data, channel=0):
        # cut it off at the end of the file in case of cache shenanigans
        length = min(self.channels.shape[1] - start, self.channels.shape[0])
        if channel == -1:
            for chan in range(self.channels.shape[0]):
                self.channels[chan][start:start + length] += data[chan][:length]
        else:
            self.channels[channel][start:start + length] += data[:length]

    def save(self):
        with wave.open(self.filename, "wb") as wavfile:
            wavfile.setparams((self.channels.shape[0], self.channels.dtype.itemsize, self.framerate, self.channels.shape[1], "NONE", "not compressed"))
            wavfile.writeframesraw(self.channels.reshape(self.channels.size, order="F"))


class CachedWavFile:  # Stores serialized data
    def __init__(self, length, dtype=np.int32, binsize=8192):
        self.binsize = binsize
        self.savedchunks = 0
        self.length = math.ceil(length / binsize) * binsize
        self.dtype = dtype
        self.chunks = collections.defaultdict(lambda: np.zeros((self.binsize, ), dtype=self.dtype))

    def __getitem__(self, key):
        if isinstance(key, int):
            if key < 0 or key >= self.length:
                raise IndexError()
            else:
                return self.chunks[key / self.binsize][key % self.binsize]
        elif isinstance(key, slice):
            startchunk = math.floor(slice.start / self.binsize)
            stopchunk = math.ceil(slice.stop / self.binsize)
            offset = slice.start - (startchunk * self.binsize)
            length = slice.stop - slice.start
            if startchunk == stopchunk:
                return self.chunks[startchunk][offset:offset + length]
            else:
                ret = []
                ret.extend(self.chunks[startchunk][offset])
            for i in range(startchunk, stopchunk + 1):
                if i in self.chunks:
                    for b in self.chunks[i][max(offset, self.binsize):]:
                        if offset > 0:
                            offset -= 1
                        elif length > 0:
                            length -= 1
                            yield b
                        else:
                            break
                else:
                    for _ in range(self.binsize):
                        if offset > 0:
                            offset -= 1
                        elif length > 0:
                            length -= 1
                            yield 0
                        else:
                            break

    def __setitem__(self, key, val):
        if isinstance(key, int):
            if key < 0 or key >= self.length:
                raise IndexError()
            else:
                self.chunks[int(key / self.binsize)][key % self.binsize] = val
        elif isinstance(key, slice):
            startchunk = math.floor(slice.start / self.binsize)
            stopchunk = math.ceil(slice.stop / self.binsize)
            offset = slice.start - (startchunk * self.binsize)
            length = slice.stop - slice.start
            if startchunk == stopchunk:
                self.chunks[startchunk][offset:length]
            else:
                #self.chunks[startchunk][offset:] =
                for idx, chunk in range(startchunk, stopchunk + 1):
                    if i in self.chunks:
                        for b in self.chunks[i]:
                            yield b
                    else:
                        for _ in range(self.binsize):
                            yield 0
    # note to self: http://rafekettler.com/magicmethods.html

    def add_data(self, idx, data):
        pass


class CalculatedFFT:
    def __init__(self, avgdata, spacing):
        self.avgdata = avgdata
        self.spacing = spacing


class Sample:
    def __init__(self, filename, binsize, volume=0.9, delete_raw_data=True):
        if binsize >= 512:
            self.binsize = binsize
        else:
            raise ComplainToUser("Bin size is too low. Absolute minimum is 512.")

        if volume > 0:
            self.volume = volume
        else:
            raise ComplainToUser("Volume canot be a negative number.")

        self.delete_raw = delete_raw_data  # delete raw data after FFT analysis

        self._maxfreq = None
        self._fft = None

        with wave.open(filename, "rb") as wavfile:
            self.sampwidth = wavfile.getsampwidth()
            self.framerate = wavfile.getframerate()
            self.channels = wavfile.getnchannels()
            self.length = wavfile.getnframes()

            if self.sampwidth == 1:
                self.size = np.int8
            elif self.sampwidth == 2:
                self.size = np.int16
            elif self.sampwidth == 3 or self.sampwidth == 4:
                self.size = np.int32
            else:
                raise ComplainToUser("WAV files higher than 32 bits are not supported.")

            self.wav = np.zeros((self.channels, self.length), dtype=self.size)
            for i in range(0, self.length):
                frame = wavfile.readframes(1)
                for chan in range(self.channels):
                    self.wav[chan][i] = int.from_bytes(frame[self.sampwidth*chan:self.sampwidth*(chan+1)], byteorder="little", signed=True)

            volume_mult = 256 ** (4 - self.sampwidth)
            self.img = Image.frombytes("I", (self.length, self.channels), (self.wav * (volume_mult * self.volume)).astype(np.int32).tobytes(), "raw", "I", 0, 1)

    def __len__(self):
        return self.length

    @property
    def fft(self):
        if not self._fft:
            if self.binsize % 2 != 0:
                print("Warning: Bin size must be a multiple of 2, correcting automatically")
                self.binsize += 1
            spacing = float(self.framerate) / self.binsize
            avgdata = np.zeros(self.binsize // 2, dtype=np.float64)
            for i in range(0, len(self.wav), self.binsize):
                data = np.array(self.wav[i:i + self.binsize], dtype=self.size)
                if len(data) != self.binsize:
                    continue
                fft = pyfftw.interfaces.numpy_fft.fft(data)
                fft = np.abs(fft[:self.binsize // 2])
                avgdata += fft
                del data
                del fft
            if max(avgdata) == 0:
                print("Warning: Bin size is too large to analyze sample; dividing by 2 and trying again")
                self.binsize = self.binsize // 2
                self._fft = self.fft
            else:
                if self.delete_raw:
                    del self.wav
                self._fft = CalculatedFFT(avgdata, spacing)
        return self._fft

    @property
    def maxfreq(self):
        if not self._maxfreq:
            self._maxfreq = (np.argmax(self.fft.avgdata[1:]) * self.fft.spacing) + (self.fft.spacing / 2)
        return self._maxfreq


class MIDIParser:
    def __init__(self, filename, wav, transpose=0, speed=1):  # TODO: convert the rest of the function to the new notes
        if speed <= 0:
            return ValueError("The speed must be a positive number.")
        results = collections.defaultdict(list)
        notes = collections.defaultdict(list)
        self.notecount = 0
        self.maxvolume = 0
        self.maxpitch = 0
        volume = 0

        with mido.MidiFile(filename, "r") as mid:
            time = 0
            for message in mid:
                time += message.time
                if "channel" in vars(message) and message.channel == 10:
                    continue  # channel 10 is reserved for percussion
                if message.type == "note_on":
                    note = Note()
                    note.starttime = int(round(time * wav.framerate / speed))
                    note.volume = 1 if message.velocity == 0 else message.velocity / 127
                    note.pitch = self.note_to_freq(message.note + transpose)

                    notes[message.note].append(note)
                    volume += note.volume
                    self.maxvolume = max(volume, self.maxvolume)
                elif message.type == "note_off":
                    note = notes[message.note].pop(0)
                    if len(notes[message.note]) == 0:
                        del notes[message.note]

                    try:
                        results[note.starttime].append(note)
                    except IndexError:
                        print("Warning: There was a note end event at {} seconds with no matching begin event".format(time))

                    self.notecount += 1
                    volume -= note.volume
                    self.maxpitch = max(self.maxpitch, note.pitch)
                    note.length = int(time * wav.framerate / speed) - note.starttime

            if len(notes) != 0:
                print("Warning: The MIDI ended with notes still playing, assuming they end when the MIDI does")
                for ntime, nlist in notes.items():
                    for note in nlist:
                        note.length = int(time * wav.framerate / speed) - note.starttime

                        self.notecount += 1
            self.notes = sorted(results.items(), key=operator.itemgetter(0))
            self.length = max(max(note.starttime + note.length for note in nlist) for _, nlist in self.notes)

    def note_to_freq(self, notenum):
        # see https://en.wikipedia.org/wiki/MIDI_Tuning_Standard
        return (2.0 ** ((notenum - 69) / 12.0)) * 440.0


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
        return np.asarray(img.resize((int(round(img.size[0] * multiplier)), self.sample.channels), resample=self.alg), dtype=np.int32).flatten()

    def render_note(self, note):
        scaled = self.zoom(self.sample.img, self.sample.maxfreq / note.pitch)
        if self.fullclip or len(scaled) < note.length + self.threshold:
            return scaled
        else:
            cutoffs = []
            for i in range(self.sample.channels):
                scaled[i] = scaled[i][:note.length + self.threshold]
                # find the nearest/closest zero crossing within the threshold and continue until that
                cutoffs.append(np.argmin([abs(i) + (d * 20) for d, i in enumerate(scaled[i][note.length:])]))
            merged_channels = np.zeros((self.sample.channels, note.length + max(cutoffs))
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
            raise ComplainToUser("Smart caching will be implemented in the future (possibly v. 1.0.1).")
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
            version = "?"
            try:
                version = pkg_resources.get_distribution("swood").version
            except:
                pass
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
            print(you_tried)
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
