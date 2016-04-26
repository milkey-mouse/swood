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
            self._maxfreq = None
            self._fft = None
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
            self.img = Image.frombytes("I", (len(self.wav), 1), (self.wav.astype(np.float64) * ((2 ** 32) / (2 ** (8 * self.sampwidth)) * 0.9)).astype(np.int32).tobytes(), "raw", "I", 0, 1)
            
    @property
    def fft(self):
        if self.chunksize % 2 != 0:
            print("Warning: bin size must be a multiple of 2, correcting automatically")
            self.chunksize += 1
        if not self._fft:
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
                print("Warning: Chunk size too large for sound file. Dividing by 2 and trying again.")
                self.chunksize = self.chunksize // 2
                self._fft = self.fft
            else:
                self._fft = (avgdata, spacing)
        return self._fft

    def get_max_freq(self):
        if not self._maxfreq:
            fft = self.get_fft()
            self._maxfreq = (np.argmax(fft[0][1:]) * fft[1]) + (fft[1] / 2)
        return self._maxfreq
        
   def __getitem__(self, key):
       setattr(vars(self), 

class Note:
    def __init__(self, time, frequency, volume):
        self.time = time
        self.frequency = frequency
        self.volume = volume
        
    def __hash__(self):
        return hash((note.time, note.frequency))
        
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
        self.maxmult = 0
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
                    onote = notes[message.note][0][1]
                    multiplier = wav.get_max_freq() / self.note_to_freq(message.note + transpose)
                    self.maxmult = max(self.maxmult, multiplier)
                    try:
                        results[int(round(onote * wav.framerate / speed))].append((int((time - onote) * wav.framerate), multiplier, 1 if message.velocity == 0 else message.velocity / 127))
                    except IndexError:
                        print("Warning: There was a note end event at {} seconds with no matching begin event.".format(time))
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

class CachedWavFile:  # Stores serialized data

    def __init__(self, length, dtype=np.int32, chunksize=8192):
        self.chunksize = chunksize
        self.savedchunks = 0
        self.length = math.ceil(length / chunksize) * chunksize
        self.dtype = dtype
        self.chunks = collections.defaultdict(lambda: np.zeros((self.chunksize,), dtype=self.dtype))
        
    def __getitem__(self, key):
        if isinstance(key, int):
            if key < 0 or key >= self.length:
                raise IndexError()
            else:
                return self.chunks[key / self.chunksize][key % self.chunksize]
        elif isinstance(key, slice):
            startchunk = math.floor(slice.start / self.chunksize)
            stopchunk = math.ceil(slice.stop / self.chunksize)
            offset = slice.start - (startchunk * self.chunksize)
            length = slice.stop - slice.start
            if startchunk == stopchunk:
                return self.chunks[startchunk][offset:offset + length]
            else:
                ret = []
                ret.extend(self.chunks[startchunk][offset])
            for i in range(startchunk, stopchunk+1):
                if i in self.chunks:
                    for b in self.chunks[i][max(offset, self.chunksize):]:
                        if offset > 0:
                            offset -= 1
                        elif length > 0:
                            length -= 1
                            yield b
                        else:
                            break
                else:
                    for _ in range(self.chunksize):
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
                self.chunks[int(key / self.chunksize)][key % self.chunksize] = val
        elif isinstance(key, slice):
            startchunk = math.floor(slice.start / self.chunksize)
            stopchunk = math.ceil(slice.stop / self.chunksize)
            offset = slice.start - (startchunk * self.chunksize)
            length = slice.stop - slice.start
            if startchunk == stopchunk:
                self.chunks[startchunk][offset:length]
            else:
                #self.chunks[startchunk][offset:] = 
                for idx, chunk in range(startchunk, stopchunk+1):
                    if i in self.chunks:
                        for b in self.chunks[i]:
                            yield b
                    else:
                        for _ in range(self.chunksize):
                            yield 0
        
    # note to self: http://rafekettler.com/magicmethods.html
        
    def add_data(self, idx, data):
        pass


class NoteRenderer:
    def __init__(self, sample, threshold=0.075, alg=Image.BICUBIC, fullclip=False, cachesize=7.5):
        self.sample = sample
        self.img = self.sample.img
        self.threshold = int(threshold * sample.framerate)
        self.fullclip = fullclip
        self.cachesize = cachesize * sample.framerate
        self.alg = alg
        
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
        
    def render(self, midi, pbar=True, clear_cache=True):
        tick = 15
        bar = None
        c = 0
        if pbar:
            bar = progressbar.ProgressBar(widgets=[progressbar.Percentage(), " ", progressbar.Bar(), " ", progressbar.ETA()], max_value=midi.notecount)
        for time, notes in midi.notes:
            for note in notes:
                if hash(note) in self.notecache:
                    cachednote = self.notecache[hash(note)]
                    cachednote.used += 1
                    out_length = min(cachednote.length, outlen - time)
                    
                    output[time:time + cachednote.length] += (cachednote.rendered * ((note.volume / midi.maxvolume) * self.sample.volume_mult)).astype(np.int32)
                    
                else:
                    rendered = render_note(note, sample, threshold, alg, fullclip)
                    out_length = min(len(rendered), outlen - time)
                    
                    output[time:time + out_length] += (rendered[:out_length] * (note.volume / midi.maxvolume) * self.sample.volume_mult).astype(np.int32)
                    self.notecache[hash(note)] = CachedNote(time, rendered)
                if bar is not None:
                    c += 1
                    bar.update(c)
            
            # cache "garbage collection":
            # if a CachedNote is more than 7.5 (default) seconds old it removes it from the cache to save mem(e)ory
            tick += 1
            if tick == 15:
                tick = 0
                for k in list(notecache.keys()):
                    if (time - self.notecache[k].time) > self.cachesize and self.notecache[k].used < 3:
                        del self.notecache[k]
                        
        if clear_cache:
            self.notecache.clear()

def run(inwav, inmid, outpath, transpose=0, speed=1, binsize=8192, threshold=0.075, linear=False, cachesize=7.5, fullclip=False):
    if binsize < 2:
        print("Error: Your suggested bin size is too low.")
    if speed == 0.0:
        print("Error: The speed must be a positive number.")
    if threshold < 0:
        print("Error: The threshold must be ")
    print("Loading sample into memory")
    sample = WavFFT(inwav, binsize)
    print("Analyzing sample")
    print("Fundamental Frequency: {} Hz".format(sample.maxfreq))
    print("Parsing MIDI")
    midi = MIDIParser(inmid, sample, transpose=transpose, speed=speed)
    print("Creating output buffer")
    outlen = midi.length + (len(sample.wav) * int(math.ceil(midi.maxmult)) if fullclip else threshold) + 1
    output = np.zeros(outlen, dtype=np.int32)
    print("Rendering audio")
    
    renderer = NoteRenderer(sample, threshold, Image.BILINEAR if linear else Image.BICUBIC, fullclip, cachesize)

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
    fullclip = False
    linear = False
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
  --linear           use a lower quality scaling algorithm that will be a little bit faster
  --fullclip         no matter how short the note, always use the full sample without cropping""".format(version))
        import importlib   
        if importlib.util.find_spec("swoodlive"):
            print("  --live             listen on a midi input and generate the output in realtime")
        sys.exit(1)
    for arg in sys.argv[4:]:
        try:
            if arg == "--linear":
                linear = True
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
            else:
                print("Unrecognized command-line option '{}'.".format(arg))
                sys.exit(1)
        except ValueError:
            print("Error parsing command-line option '{}'.".format(arg))
            sys.exit(1)
    run(sys.argv[1], sys.argv[2], sys.argv[3], transpose, speed, threshold, binsize, linear, cachesize, fullclip)

if __name__ == "__main__":
    run_cmd()
