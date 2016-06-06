from enum import Enum
import math

from PIL import Image
import progressbar
import numpy as np
from numpy import zeros, asarray, argmin, resize, int32

from . import midiparse
from . import wavout

CachedNote = midiparse.CachedNote


class FileSaveType(Enum):
    ARRAY_TO_DISK = 0
    ARRAY_IN_MEM = 1
    SMART_CACHING = 2


class NoteRenderer:
    def __init__(self, sample, fullclip=False, cachesize=7.5, threshold=0.075):
        if threshold < 0:
            return ValueError("The threshold must be a positive number.")
        self.sample = sample
        self.fullclip = fullclip

        self.cachesize = cachesize * sample.framerate
        self.threshold = int(threshold * sample.framerate)

        self.notecache = {}

    def zoom(self, img, multiplier):
        return asarray(img.resize((int(round(img.size[0] * multiplier)), self.sample.channels), resample=Image.BICUBIC), dtype=np.int32)

    def render_note(self, note):
        scaled = self.zoom(self.sample.img, self.sample.fundamental_freq / note.pitch)
        if self.fullclip or len(scaled) < note.length + self.threshold:
            return scaled
        channels = self.sample.channels.shape[0]
        if channels == 1:
            cutoff = argmin(v + (d * 20) for d, v in enumerate(scaled[0][note.length:note.length + self.threshold]))
            return np.resize(scaled, (1, note.length + cutoff))
        else:
            cutoffs = [None] * channels
            for chan in range(channels):
                # find the nearest/closest zero crossing within the threshold and continue until that
                sample_end = np.empty(self.threshold)
                for distance, val in enumerate(scaled[chan][note.length:note.length + self.threshold]):
                    sample_end[distance] = (val) + (distance * 20)
                cutoffs[chan] = argmin(sample_end)
            merged_channels = zeros((channels, note.length + max(cutoffs)), dtype=int32)
            for chan in range(channels):
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
            raise complain.ComplainToUser("Smart caching will be implemented in the future.")
        else:
            output = wavout.UncachedWavFile(output_length, filename, self.sample.framerate, self.sample.channels)

        if pbar:
            bar = progressbar.ProgressBar(widgets=[progressbar.Percentage(), " ", progressbar.Bar(), " ", progressbar.ETA()], max_value=midi.notecount)
            progress = 0

        # "inlining" these variables can speed up the lookup, making it faster
        # see https://stackoverflow.com/questions/37202463
        caching = self.cachesize > 0
        add_data = output.add_data
        maxvolume = midi.maxvolume
        cachesize = self.cachesize

        if caching:
            tick = 8
            update = bar.update
            notecache = self.notecache

        for time, notes in midi.notes:
            for note in notes:
                if hash(note) in notecache:
                    rendered_note = notecache[hash(note)]
                    rendered_note.used += 1  # increment the used counter each time for the "GC" below
                else:
                    rendered_note = CachedNote(time, self.render_note(note))
                    notecache[hash(note)] = rendered_note
                note_volume = (note.volume / midi.maxvolume) * self.sample.volume
                add_data(time, (rendered_note.data * note_volume).astype(int32))

                if pbar:
                    # increment progress bar
                    progress += 1
                    update(progress)

            
            if caching:
                # cache "garbage collection":
                # if a CachedNote is more than <cachesize> seconds old and not
                # used >2 times it removes it from the cache to save mem(e)ory
                tick += 1
                if tick == 15:
                    tick = 0
                    for k in list(notecache.keys()):
                        if time - notecache[k].length > cachesize and notecache[k].used < 3:
                            del notecache[k]

        if caching and clear_cache:
            notecache.clear()

        if savetype == FileSaveType.ARRAY_IN_MEM:
            return output.channels
        else:
            output.save()
