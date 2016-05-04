from __future__ import print_function
import sys
if sys.version_info.major < 3:
    print("WARNING: swood.exe requires at least Python 3.4 to run correctly.")
elif sys.version_info.major == 3 and sys.version_info.minor < 4:
    print("WARNING: swood.exe requires at least Python 3.4 to run correctly.")

from enum import Enum
import pkg_resources
import collections
import importlib
import math
import wave

from PIL import Image
import progressbar
import numpy as np
import pyfftw
import mido

pyfftw.interfaces.cache.enable()


class DummyPbar:
    def update(i):
        pass


class FileSaveType(Enum):
    ARRAY_TO_DISK = 0
    ARRAY_IN_MEM  = 1
    SMART_CACHING = 2


class Note:
    def __init__(self, time, frequency, volume):
        self.time = time
        self.frequency = frequency
        self.volume = volume

    def __hash__(self):
        return hash((self.time, self.frequency))


class CachedNote:
    def __init__(self, time, rendered):
        self.used = 1
        self.time = time
        self.data = rendered
        
    def __len__(self):
        return len(self.data)


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
        if binsize < 2:
            print("Error: Your suggested bin size is too low. It should be somewhere around 8192 (but higher is better).")
            sys.exit(1)
        self.delete_raw = delete_raw_data
        with wave.open(filename, "r") as wavfile:
            print(wavfile.getparams())
            self.sampwidth = wavfile.getsampwidth()
            self.framerate = wavfile.getframerate()
            self.length = wavfile.getnframes()
            self.binsize = binsize
            self.size = np.int32
            self._maxfreq = None
            self._fft = None
            dither = False
            if self.sampwidth == 1:
                self.size = np.int8
            elif self.sampwidth == 2:
                self.size = np.int16
            self.wav = np.zeros(self.length, dtype=self.size)
            if self.sampwidth > 4:
                self.sampwidth = 4
                for i in range(0, self.length):
                    self.wav[i] = int.from_bytes(wavfile.readframes(1)[:self.sampwidth], byteorder="little", signed=True) / 2 ** 32  # 64-bit int to 32-bit
            else:
                for i in range(0, self.length):
                    self.wav[i] = int.from_bytes(wavfile.readframes(1)[:self.sampwidth], byteorder="little", signed=True)
            self.volume = 256 ** self.sampwidth / (max(self.wav) - min(self.wav))
            data_mult = 256 ** 4 / 256 ** self.sampwidth * 0.9
            self.img = Image.frombytes("I", (self.length, 1), (self.wav.astype(np.float64) * data_mult).astype(np.int32).tobytes(), "raw", "I", 0, 1)
            
    def __len__(self):
        return self.length

    @property
    def fft(self):
        if self.binsize % 2 != 0:
            print("Warning: bin size must be a multiple of 2, correcting automatically")
            self.binsize += 1
        if not self._fft:
            spacing = float(self.framerate) / self.binsize
            avgdata = np.zeros(self.binsize // 2, dtype=np.float64)
            c = None
            offset = None
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
                print("Warning: bin size is too large to analyze sample. Dividing by 2 and trying again.")
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
    def __init__(self, path, wav, transpose=0, speed=1):  # TODO: convert the rest of the function to the new notes
        if speed <= 0:
            print("Error: The speed must be a positive number.")
            sys.exit(1)
        results = collections.defaultdict(lambda: [])
        notes = collections.defaultdict(lambda: [])
        self.notecount = 0
        self.maxnotes = 0
        self.maxvolume = 0
        self.maxpitch = 0
        volume = 0
        with mido.MidiFile(path, "r") as mid:
            time = 0
            for message in mid:
                time += message.time
                if "channel" in vars(message) and message.channel == 10:
                    continue  # channel 10 is reserved for percussion
                if message.type == "note_on":
                    note_volume = 1 if message.velocity == 0 else message.velocity / 127
                    notes[message.note].append((note_volume, time))
                    volume += note_volume
                    self.maxvolume = max(volume, self.maxvolume)
                    self.maxnotes = max(sum(len(i) for i in notes.values()), self.maxnotes)
                elif message.type == "note_off":
                    note_from_cache = notes[message.note][0]
                    note_time = int(round(note_from_cache[1] * wav.framerate / speed))
                    note_length = int((time - note_from_cache[1]) * wav.framerate)
                    note_pitch = wav.maxfreq / self.note_to_freq(message.note + transpose)
                    note_volume = note_from_cache[0]
                    try:
                        results[note_time].append((note_length, note_pitch, note_volume))
                    except IndexError:
                        print("Warning: There was a note end event at {} seconds with no matching begin event.".format(time))
                    self.maxpitch = max(self.maxpitch, note_pitch)
                    volume -= note_volume
                    notes[message.note].pop(0)
                    self.notecount += 1
            if len(notes) != 0:
                print("Warning: MIDI ended with notes still playing, assuming they end when the MIDI does")
                for ntime, nlist in notes.items():
                    for note in nlist:
                        results[int(round(notes[note][0][1] * wav.framerate / speed))].append((int((ntime - time) * wav.framerate), wav.get_max_freq() / self.note_to_freq(note + transpose), 1))
                        self.notecount += 1
            self.notes = sorted(results.items())
            self.length = self.notes[-1][0] + max(self.notes[-1][1])[0]
            for time, nlist in self.notes:
                for i in range(len(nlist)):  # convert all the notes to the class kind
                    oldnote = nlist[i]
                    nlist[i] = Note(oldnote[0], oldnote[1], oldnote[2])

    def note_to_freq(self, notenum):
        # https://en.wikipedia.org/wiki/MIDI_Tuning_Standard
        return (2.0 ** ((notenum - 69) / 12.0)) * 440.0


class NoteRenderer:
    def __init__(self, sample, volume=0.9, alg=Image.BICUBIC, fullclip=False, threshold=0.075, cachesize=7.5):
        if threshold < 0:
            print("Error: The threshold must be a positive number.")
            sys.exit(1)
        if volume < 0 or volume > 1:
            print("Error: Volume must be between 0 and 1 (inclusive)")
            sys.exit(1)
        self.alg = alg
        self.sample = sample
        self.volume = volume
        self.fullclip = fullclip
        self.img = self.sample.img
        
        self.cachesize = cachesize * sample.framerate
        self.threshold = int(threshold * sample.framerate)

        self.notecache = {}

    def zoom(self, multiplier):
        return np.asarray(self.img.resize((int(round(self.img.size[0] * multiplier)), 1), resample=self.alg), dtype=np.int32).flatten()

    def render_note(self, note):
        scaled = self.zoom(note.frequency)
        if self.fullclip or len(scaled) < note.time + self.threshold:
            return scaled
        else:
            scaled = scaled[:note.time + self.threshold]
            # find the nearest/closest zero crossing within the threshold and continue until that
            cutoff = np.argmin([abs(i) + (d * 20) for d, i in enumerate(scaled[note.time:])])
            return scaled[:note.time + cutoff]

    def hash_array(self, arr):
        arr.flags.writeable = False
        result = hash(arr.data)
        arr.flags.writeable = True
        return result

    def render(self, midi, filename, pbar=True, all_in_memory=False, clear_cache=True):
        tick = 15
        bar = None
        c = 0
        output_length = midi.length + (len(self.sample) * int(math.ceil(midi.maxpitch * len(self.sample))) if self.fullclip else self.threshold) + 1
        output = CachedWavFile(output_length) if all_in_memory else np.zeros(output_length, dtype=np.int32)
        bar = progressbar.ProgressBar(widgets=[progressbar.Percentage(), " ", progressbar.Bar(), " ", progressbar.ETA()], max_value=midi.notecount) if pbar else DummyPbar()
        for time, notes in midi.notes:
            for note in notes:
                rendered_note = None
                if hash(note) in self.notecache:
                    rendered_note = self.notecache[hash(note)]
                    rendered_note.used += 1  # increment the used counter each time for the "GC" below
                else:
                    rendered_note = CachedNote(time, self.render_note(note))
                    self.notecache[hash(note)] = rendered_note
                note_volume = ((note.volume / midi.maxvolume) * self.sample.volume)
                out_length = min(len(rendered_note), len(output) - time)  # cut it off at the end of the file in case of cache shenanigans
                output[time:time + out_length] += (rendered_note.data[:out_length] * note_volume).astype(np.int32)
                #increment progress bar
                c += 1
                bar.update(c)

            # cache "garbage collection":
            # if a CachedNote is more than 7.5 (default) seconds old it removes it from the cache to save mem(e)ory
            if self.cachesize > 0:
                tick += 1
                if tick == 15:
                    tick = 0
                    for k in list(notecache.keys()):
                        if time - self.notecache[k].time > self.cachesize and self.notecache[k].used < 3:
                            del self.notecache[k]

        if clear_cache:
            self.notecache.clear()

        with wave.open(filename, "wb") as outfile:
            outfile.setparams((1, 4, self.sample.framerate, len(output), "NONE", "not compressed"))
            print(outfile.getparams())
            outfile.writeframes(output)


def run(sample, outfile, midi, renderer):
    print("Loading sample into memory")
    sample = Sample(inwav, binsize)
    print("Analyzing sample")
    print("Fundamental Frequency: {} Hz".format(sample.maxfreq))
    print("Parsing MIDI")
    midi = MIDIParser(inmid, sample, transpose=transpose, speed=speed)
    print("Creating output buffer")

    print("Rendering audio")

    renderer = NoteRenderer(sample, threshold, Image.BILINEAR if linear else Image.BICUBIC, fullclip, cachesize)

    print("Saving audio")

    print("Saved to {}".format(outpath))


def run_cmd():
    transpose = 0
    speed = 1.0
    threshold = 0.075
    binsize = 8192
    cachesize = 7.5
    volume = 0.9
    fullclip = False
    alg = Image.BICUBIC
    if len(sys.argv) <= 3:
        version = "?"
        try:
            version = pkg_resources.get_distribution("swood").version
        except:
            pass
        print("""swood - the automatic ytpmv generator (v. {})

usage: swood in_wav in_midi out_wav
  in_wav: a short wav file to use as the instrument for the midi
  in_midi: a midi to output with the wav sample as the instrument
  out_wav: location for the finished song as a wav

options:
  --transpose=0      transpose the midi by n semitones
  --speed=1.0        speed up the midi by this multiplier
  --threshold=0.075  maximum amount of time after a note ends that it can go on for a smoother ending
  --binsize=8192     FFT bin size for the sample analysis; lower numbers make it faster but more off-pitch
  --cachesize=7.5    note cache size (seconds); lower could speed up repetitive songs, using more memory
  --volume=0.9       
  --linear           use a lower quality scaling algorithm that will be a little bit faster
  --fullclip         no matter how short the note, always use the full sample without cropping""".format(version))
        if importlib.util.find_spec("swoodlive"):
            print("  --live             listen on a midi input and generate the output in realtime")
        sys.exit(1)
    for arg in sys.argv[4:]:
        try:
            if arg == "--linear":
                alg = Image.BILINEAR
            elif arg == "--fullclip":
                fullclip = True
            elif arg.startswith("--transpose="):
                transpose = int(float(arg[len("--transpose="):]))
            elif arg.startswith("--speed="):
                speed = float(arg[len("--speed="):])
            elif arg.startswith("--threshold="):
                threshold = float(arg[len("--threshold="):])
            elif arg.startswith("--binsize="):
                binsize = int(float(arg[len("--binsize="):]))
            elif arg.startswith("--volume="):
                volume = float(arg[len("--volume="):])
            else:
                print("Unrecognized command-line option '{}'.".format(arg))
                sys.exit(1)
        except ValueError:
            print("Error parsing command-line option '{}'.".format(arg))
            sys.exit(1)
    sample = Sample(sys.argv[1], binsize)
    print(sample.maxfreq)
    midi = MIDIParser(sys.argv[2], sample, transpose, speed)
    renderer = NoteRenderer(sample, volume, alg, fullclip, threshold, cachesize)
    renderer.render(midi, sys.argv[3])
    #run(sys.argv[1], sys.argv[2], sys.argv[3], transpose, speed, threshold, binsize, linear, cachesize, fullclip)

if __name__ == "__main__":
    run_cmd()
