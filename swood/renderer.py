from enum import Enum
import math

from PIL import Image
import progressbar
from numpy import empty, zeros, asarray, argmin, resize, int32, full, iinfo

from . import wavout


class CachedNote:
    def __init__(self, length, rendered, cutoffs):
        self.used = 1
        self.length = length
        self.data = rendered
        self.cutoffs = cutoffs

    def __len__(self):
        return len(self.data)


class FileSaveType(Enum):
    ARRAY_TO_DISK = 0
    ARRAY_IN_MEM = 1
    SMART_CACHING = 2


class NoteRenderer:
    def __init__(self, sample, fullclip=False, cachesize=7.5, threshold=0.05):
        if threshold < 0:
            return ValueError("The threshold must be a positive number.")
        self.sample = sample
        self.fullclip = fullclip

        self.cachesize = cachesize * sample.framerate
        self.threshold = int(threshold * sample.framerate)

        self.maxint32 = iinfo(int32).max
        self.intrange = self.maxint32 - iinfo(int32).min
        self.distance_multiplier = self.intrange / self.threshold * 0

        self.notecache = {}

    def zoom(self, img, multiplier):
        return asarray(img.resize((int(round(img.size[0] * multiplier)), self.sample.channels), resample=Image.BICUBIC), dtype=int32)

    def render_note(self, note):
        scaled = self.zoom(self.sample.img, self.sample.fundamental_freq / note.pitch)
        if note.bend:
            return scaled[note.samplestart:note.samplestart+note.length], full(self.sample.channels, scaled.shape[1], dtype=int32)
        else:
            print("wat")
            # find the closest zero crossing within the threshold and continue until that
            # this removes most "clicking" sounds from the audio suddenly cutting out
            cutoffs = zeros(self.sample.channels, dtype=int32)
            cutoff_scores = full(self.sample.channels, self.maxint32, dtype=int32)
            print("dist")
            if scaled.shape[1] > note.length:
                note_ending = scaled[note.length:note.length + self.threshold]
                distance_multiplier = self.distance_multiplier
            else:
                note_ending = scaled[]
                distance_multiplier = -self.distance_multiplier
            for distance, sample in enumerate(note_ending):
                print("meme")
                for channel, val in enumerate(sample):
                    score = abs(val) + (distance * distance_multiplier)
                    if score < cutoff_scores[channel]:
                        cutoff_scores[channel] = score
                        cutoffs[channel] = distance
                        print(self.threshold / distance)
                    else:
                        print(score, cutoff_scores[channel])
            cutoffs += note.length
            print("end", cutoffs)
            return scaled, cutoffs

    def render(self, midi, filename, pbar=True, savetype=FileSaveType.ARRAY_TO_DISK, clear_cache=True):
        if self.fullclip:
            # leave a small buffer at the end with space for one more sample
            output_length = midi.length + int(math.ceil(midi.maxpitch * len(self.sample)))
        else:
            output_length = midi.length + self.threshold  # it has to cut off sounds at the threshold anyway

        if savetype == FileSaveType.SMART_CACHING:
            #output = CachedWavFile(output_length, filename, self.sample.framerate)
            raise complain.ComplainToUser("Smart caching will be implemented in the future.")
        else:
            output = wavout.UncachedWavFile(output_length, filename, self.sample.framerate, self.sample.channels)

        if pbar:
            bar = progressbar.ProgressBar(widgets=[progressbar.Percentage(), " ", progressbar.Bar(), " ", progressbar.ETA()], max_value=midi.notecount)
            update = bar.update
            progress = 0

        # "inlining" these variables can speed up the lookup, making it faster
        # see https://stackoverflow.com/questions/37202463
        caching = self.cachesize > 0
        add_data = output.add_data
        maxvolume = midi.maxvolume
        cachesize = self.cachesize

        if caching:
            tick = 8
            notecache = self.notecache

        for time, notes in midi.notes:
            for note in notes:
                if hash(note) in notecache:
                    rendered_note = notecache[hash(note)]
                    rendered_note.used += 1  # increment the used counter each time for the "GC" below
                else:
                    rendered_note = CachedNote(time, *self.render_note(note))
                    notecache[hash(note)] = rendered_note
                if rendered_note.data.shape[0] != 0:
                    add_data(time, (rendered_note.data * (note.volume / midi.maxvolume)), rendered_note.cutoffs)

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
