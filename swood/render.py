"""Renders music by pitch bending samples according to a MIDI."""

from enum import Enum
import math

from PIL import Image
import progressbar
from numpy import zeros, full, asarray, resize, int32, int64

from . import wavout


class CachedNote:
    """Holds pre-rendered versions of notes, tracking # of uses."""

    def __init__(self, length, rendered, cutoffs):
        self.used = 1
        self.length = length
        self.data = rendered
        self.cutoffs = cutoffs

    def __len__(self):
        return len(self.data)


class FileSaveType(Enum):
    """Enum for selecting where to render to.

    ARRAY_TO_DISK will create a single array and write the contents out when done.
    ARRAY_IN_MEM will render to a single array and return the contents.
    SMART_CACHING will render out to many chunks, flushing them to disk to save memory.
    (If the platform supports it, SMART_CACHING will attempt to memory-map the file instead.)
    It's recommended to use SMART_CACHING (the default from the CLI) over ARRAY_TO_DISK
    as ARRAY_TO_DISK uses lots of memory on any file longer than a few seconds.
    """
    ARRAY_TO_DISK = 0
    ARRAY_IN_MEM = 1
    SMART_CACHING = 2


class NoteRenderer:
    """Renders a WAV file from a MIDI by pitch bending the samples."""

    def __init__(self, sample, fullclip=False, cachesize=7.5, threshold=0.075):
        if threshold < 0:
            return ValueError("The threshold must be a positive number.")
        self.sample = sample
        self.fullclip = fullclip

        self.cachesize = cachesize * sample.framerate
        self.threshold = int(threshold * sample.framerate)

        self.distance_multiplier = (2**32 - 1) / self.threshold * 0.5

        self.notecache = {}

    def zoom(self, img, multiplier):
        """Scales the sound clip (in PIL Image form) by the given multiplier."""
        if multiplier == 1.0:
            return asarray(img, dtype=int32)
        else:
            return asarray(img.resize((int(round(img.size[0] * multiplier)),
                                       self.sample.channels),
                                      resample=Image.BICUBIC), dtype=int32)

    def render_note(self, note):
        """Render a single note and return an array (with optional cutoffs)."""
        instrument = note.instrument

        if instrument.sample is None:
            return None, None

        if instrument.noscale:
            scaled = self.zoom(instrument.sample.img, 1.0)
        else:
            scaled = self.zoom(instrument.sample.img,
                               instrument.sample.fundamental_freq / note.pitch)
        if self.fullclip or instrument.fullclip:
            return scaled, full(instrument.sample.channels, scaled.shape[1], dtype=int32)

        # cache variables for faster lookups
        # see https://stackoverflow.com/q/37202463
        length = note.length
        channels = instrument.sample.channels

        # get the area on the end of the clip that it's ok to cut off at
        if scaled.shape[1] > length:
            distance_multiplier = self.distance_multiplier
            note_ending = scaled[:, length:length + self.threshold]
        else:
            distance_multiplier = -self.distance_multiplier
            start = min(0, length - self.threshold)
            note_ending = scaled[start:]

        # find the closest zero crossing within the threshold & cut off there
        # removes "clicking" sounds from the audio suddenly cutting out
        cutoffs = zeros(channels, dtype=int32)
        cutoff_scores = full(channels, 2**63 - 1, dtype=int64)
        for channel, audio in enumerate(note_ending):
            for distance, val in enumerate(audio):
                score = abs(val) + (distance * distance_multiplier)
                if score < cutoff_scores[channel]:
                    cutoff_scores[channel] = score
                    cutoffs[channel] = distance
        cutoffs += length
        return scaled, cutoffs

    def render(self, midi, filename=None, pbar=False, savetype=FileSaveType.SMART_CACHING, clear_cache=True):
        """Renders from a MIDIParser to an array or WAV file using Samples.

        Args:
            midi: The (pre-parsed) MIDI file to render.
            filename: A file or file path to save the WAV file to. Not needed with
            FileSaveType.ARRAY_IN_MEM.
            pbar: Show a progress bar on STDOUT while rendering. Defaults to False.
            savetype: The FileSaveType to use when writing the sound data. Defaults
            to FileSaveType.SMART_CACHING.
            clear_cache: Remove all notes from the temporary cache after rendering
            the MIDI. It's recommended to disable this if you're rendering many MIDIs
            and have memory to spare. Defaults to True.
        """

        if savetype != FileSaveType.ARRAY_IN_MEM and filename is None:
            return ValueError("When not outputting to an array in memory, you need to specify a filename.")
        if self.fullclip:
            # leave a small buffer at the end with space for one more sample
            output_length = midi.length + \
                int(math.ceil(midi.maxpitch * len(self.sample)))
        else:
            # it has to cut off sounds at the threshold anyway
            output_length = midi.length + self.threshold

        if savetype == FileSaveType.SMART_CACHING:
            output = wavout.CachedWavFile(
                output_length, filename, self.sample.framerate, self.sample.channels)
        else:
            output = wavout.UncachedWavFile(
                output_length, filename, self.sample.framerate, self.sample.channels)

        if pbar:
            bar = progressbar.ProgressBar(widgets=[progressbar.Percentage(
            ), " ", progressbar.Bar(), " ", progressbar.ETA()], max_value=midi.notecount)
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
                if note in notecache:
                    rendered_note = notecache[note]
                    rendered_note.used += 1  # increment the used counter each time for the "GC" below
                else:
                    rendered_note = CachedNote(time, *self.render_note(note))
                    notecache[note] = rendered_note
                if rendered_note.data is not None and rendered_note.data.shape[0] != 0:
                    add_data(time, rendered_note.data *
                             (note.volume / midi.maxvolume *
                              note.instrument.volume),
                             rendered_note.cutoffs)

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
