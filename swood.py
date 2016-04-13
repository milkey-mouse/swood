import pkg_resources
import collections
import math
import wave
import sys

from PIL import Image
import progressbar
import numpy as np
import pyfftw
import mido
pyfftw.interfaces.cache.enable()


class WavFFT:
    def __init__(self, filename, chunksize):
        with wave.open(filename, "r") as wavfile:
            self.sampwidth = wavfile.getsampwidth()
            self.framerate = wavfile.getframerate()
            self.chunksize = chunksize
            self.offset = 2 ** (8 * max(self.sampwidth, 4))  # max 32-bit
            self.size = np.int32
            self.fft = None
            self.maxfreq = None
            dither = False
            if self.sampwidth == 1:
                self.size = np.int8
            elif self.sampwidth == 2:
                self.size = np.int16
            self.wav = np.zeros(wavfile.getnframes(), dtype=self.size)
            if self.sampwidth > 4:
                for i in range(0, wavfile.getnframes()):
                    self.wav[i] = int.from_bytes(wavfile.readframes(1)[:self.sampwidth], byteorder="little", signed=True) / 2 ** 32  # 64-bit int to 32-bit
            else:
                for i in range(0, wavfile.getnframes()):
                    self.wav[i] = int.from_bytes(wavfile.readframes(1)[:self.sampwidth], byteorder="little", signed=True)
            #self.wav -= int(np.average(self.wav))
            self.wav.flags.writeable = False
            self.img = Image.frombytes("I", (len(self.wav), 1), (self.wav.astype(np.float64) * ((2 ** 32) / (2 ** (8 * self.sampwidth)))).astype(np.int32).tobytes(), "raw", "I", 0, 1)

    def get_fft(self):
        if self.chunksize % 2 != 0:
            print("Error: bin size must be a multiple of 2")
        if not self.fft:
            spacing = float(self.framerate) / self.chunksize
            avgdata = np.zeros(self.chunksize // 2, dtype=np.float64)
            c = None
            offset = None
            for i in range(0, len(self.wav), self.chunksize):
                data = np.array(self.wav[i:i + self.chunksize], dtype=self.size)
                if len(data) != self.chunksize:
                    continue
                fft = pyfftw.interfaces.numpy_fft.fft(data)
                fft = np.abs(fft[:self.chunksize // 2])
                avgdata += fft
                del data
                del fft
            if max(avgdata) == 0:
                self.chunksize = self.chunksize // 2
                self.fft = self.get_fft()
            else:
                self.fft = (avgdata, spacing)
        return self.fft

    def get_max_freq(self):
        if not self.maxfreq:
            fft = self.get_fft()
            self.maxfreq = (np.argmax(fft[0][1:]) * fft[1]) + (fft[1] / 2)
        return self.maxfreq

class Note:
    def __init__(self, time, frequency, volume):
        self.time = time
        self.frequency = frequency
        self.volume = volume
        
class CachedNote:
    def __init__(self, time, rendered):
        self.used = 1
        self.time = time
        self.rendered = rendered
        self.length = len(rendered)

class MIDIParser:
    def __init__(self, path, wav, transpose=0, speed=1):  # TODO: convert the rest of the function to the new notes
        results = collections.defaultdict(lambda: [])
        notes = collections.defaultdict(lambda: [])
        self.notecount = 0
        self.maxnotes = 0
        self.maxvolume = 0
        volume = 0
        with mido.MidiFile(path, "r") as mid:
            time = 0
            for message in mid:
                time += message.time
                if "channel" in message.__dict__ and message.channel == 10:
                    continue  # channel 10 is reserved for percussion
                if message.type == "note_on":
                    note_volume = 1 if message.velocity == 0 else message.velocity / 127
                    notes[message.note].append((note_volume, time))
                    volume += note_volume
                    self.maxvolume = max(volume, self.maxvolume)
                    self.maxnotes = max(sum(len(i) for i in notes.values()), self.maxnotes)
                elif message.type == "note_off":
                    onote = notes[message.note][0][1]
                    results[int(round(onote * wav.framerate / speed))].append((int((time - onote) * wav.framerate), wav.get_max_freq() / self.note_to_freq(message.note + transpose), 1 if message.velocity == 0 else message.velocity / 127))
                    volume -= notes[message.note][0][0]
                    notes[message.note].pop(0)
                    self.notecount += 1
            if len(notes) != 0:
                print("Warning: MIDI ended with notes still playing, assuming they end when the MIDI does")
                for ntime, nlist in notes.items():
                    for note in nlist:
                        results[int(round(notes[note][0] * wav.framerate / speed))].append((int((ntime - time) * wav.framerate), wav.get_max_freq() / self.note_to_freq(note + transpose), 1))
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

class CachedWavFile:
    def __init__(self, length, dtype=np.int32, chunksize=8192):
        self.chunksize = chunksize
        self.dtype = dtype
        self.chunks = collections.defaultdict(lambda: np.zeros((self.chunksize,), dtype=self.dtype))
        self.__getitem__ = self.chunks.__getitem__
        
    # note to self: http://rafekettler.com/magicmethods.html
        
    def add_data(self, idx, data):
        pass

def zoom(img, multiplier, alg):
    return np.asarray(img.resize((int(round(img.size[0] * multiplier)), 1), resample=alg), dtype=np.int32).flatten()


def render_note(note, sample, threshold, alg):
    scaled = zoom(sample.img, note.frequency, alg)
    if len(scaled) < note.time + threshold:
        return scaled
    else:
        scaled = scaled[:note.time + threshold]
        # find the nearest/closest zero crossing within the threshold and continue until that
        cutoff = np.argmin([abs(i) + (d * 20) for d, i in enumerate(scaled[note.time:])])
        return scaled[:note.time + cutoff]


def hash_array(arr):
    arr.flags.writeable = False
    result = hash(arr.data)
    arr.flags.writeable = True
    return result

def run(inwav, inmid, outpath, transpose=0, speed=1, binsize=8192, threshold_mult=0.075, linear=False, cachesize=None):
    c = 0
    tick = 15
    notecache = {}
    if not cachesize:
        cachesize = 7.5
    alg = Image.BILINEAR if linear else Image.BICUBIC
    print("Loading sample into memory")
    sample = WavFFT(inwav, binsize)
    print("Analyzing sample")
    ffreq = sample.get_max_freq()
    threshold = int(float(sample.framerate) * threshold_mult)
    cachesize *= sample.framerate
    print("Fundamental Frequency: {} Hz".format(ffreq))
    print("Parsing MIDI")
    midi = MIDIParser(inmid, sample, transpose=transpose, speed=speed)
    print("Creating output buffer")
    outlen = midi.length + 1 + threshold
    output = np.zeros(outlen, dtype=np.int32)
    print("Rendering audio")
    bar = progressbar.ProgressBar(widgets=[progressbar.Percentage(), " ", progressbar.Bar(), " ", progressbar.ETA()], max_value=midi.notecount)
    for time, notes in midi.notes:
        for note in notes:
            if (note.time, note.frequency) in notecache:
                cachednote = notecache[(note.time, note.frequency)]
                output[time:time + cachednote.length] += (cachednote.rendered * (note.volume / midi.maxvolume)).astype(np.int32)
                notecache[(note.time, note.frequency)].used += 1
            else:
                rendered = render_note(note, sample, threshold, alg)
                out_length = min(len(rendered), outlen - time)
                output[time:time + out_length] += (rendered[:out_length] * (note.volume / midi.maxvolume)).astype(np.int32)
                notecache[(note.time, note.frequency)] = CachedNote(time, rendered)
            c += 1
            bar.update(c)
        
        # cache "garbage collection"
        tick -= 1
        if tick == 0:
            tick = 15
            for k in list(notecache.keys()):
                if (time - notecache[k].time) > cachesize and notecache[k].used < 3:
                    del notecache[k]

    print("Saving audio")

    with wave.open(outpath, "w") as outwav:
        outwav.setframerate(sample.framerate)
        outwav.setnchannels(1)
        outwav.setsampwidth(4)
        outwav.setnframes(outlen)
        outwav.writeframesraw(output)

    print("Saved to {}".format(outpath))


def run_cmd():
    transpose = 0
    speed = 1.0
    threshold = 0.075
    binsize = 8192
    cachesize = 7.5
    linear=False
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
  --linear           use a lower quality scaling algorithm that will be a little bit faster
  --threshold=0.075  maximum amount of time after a note ends that it can go on for a smoother ending
  --binsize=8192     FFT bin size for the sample analysis; lower numbers make it faster but more off-pitch
  --cachesize=7.5    note cache size (seconds); lower could speed up repetitive songs, using more memory""".format(version))
        sys.exit(1)
    for arg in sys.argv[4:]:
        try:
            if arg == "--linear":
                linear = True
            elif arg.startswith("--transpose="):
                transpose = int(float(arg[len("--transpose="):]))
            elif arg.startswith("--speed="):
                speed = float(arg[len("--speed="):])
            elif arg.startswith("--threshold="):
                threshold = float(arg[len("--threshold="):])
            elif arg.startswith("--binsize="):
                binsize = int(float(arg[len("--binsize="):]))
            else:
                print("Unrecognized command-line option '{}'.".format(arg))
                sys.exit(1)
        except ValueError:
            print("Error parsing command-line option '{}'.".format(arg))
            sys.exit(1)
    run(sys.argv[1], sys.argv[2], sys.argv[3], transpose=transpose, speed=speed, threshold_mult=threshold, binsize=binsize, linear=linear, cachesize=cachesize)

if __name__ == "__main__":
    run_cmd()
