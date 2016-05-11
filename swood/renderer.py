import math
from PIL import Image
import progressbar
import numpy as np


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
