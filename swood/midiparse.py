"""Parses MIDI files into a list of notes in chronological order."""

from copy import copy
import collections
import operator

import mido

from . import complain, soundfont
from .sample import Sample


def note_to_freq(notenum):
    """Converts a MIDI note number to a frequency.

    See https://en.wikipedia.org/wiki/MIDI_Tuning_Standard
    """
    return (2.0 ** ((notenum - 69) / 12.0)) * 440.0


class Note:
    """Holds information about each MIDI note."""

    def __init__(self, volume=127, start=0, pitch=0, instrument=1, percussion=False):
        self.instrument = instrument
        self.percussion = percussion

        self.volume = volume
        self.start = start
        self.pitch = pitch
        self.length = 0

    def __hash__(self):
        return hash((self.length, self.pitch, self.start, hash(self.instrument), self.percussion))

    def __eq__(self, other):
        return hash(self) == hash(other)

    def __len__(self):
        return len(self.data)

    def __repr__(self):
        return "Note(length={}, volume={}, start={}, pitch={})".format(self.length, self.volume, self.start, self.pitch)

    def finalize(self, time):
        if not self.percussion:
            self.pitch = note_to_freq(self.pitch)
        self.length = time - self.start
        return self


class MIDIParser:
    """Parses a MIDI file into a chronological list of notes."""

    def __init__(self, filename, sample, transpose=0, speed=1):
        playing = collections.defaultdict(list)
        notes = collections.defaultdict(list)
        # default to acoustic piano
        self.channel_instruments = [sample.instruments[1][0], ] * 16
        self.notecount = 0
        self.maxvolume = 0
        self.maxpitch = 0
        volume = 0

        try:
            with (mido.MidiFile(filename, "r") if isinstance(filename, str) else filename) as mid:
                if mid.type == 2:
                    raise complain.ComplainToUser(
                        "Type 2 (asynchronous) MIDI files are not supported.")

                # label messages from each track
                for track_idx, track in enumerate(mid.tracks):
                    for message in track:
                        # mido hooks __setattr__ so we can't set stuff directly
                        vars(message)["track_idx"] = track_idx

                time = 0
                for message in mid:
                    time += message.time / speed
                    time_samples = int(round(time * sample.framerate))

                    if message.type == "note_on":  # ugh, string-typing
                        if message.channel == 10:
                            try:
                                instrument = sample.percussion[message.note]
                                playing[message.note].append(
                                    Note(start=time_samples,
                                         volume=message.velocity * instrument.volume,
                                         instrument=instrument,
                                         percussion=True))
                            except KeyError:
                                print(
                                    "Warning: Percussion note number outside typical 35-81 range: {}".format(message.note))
                        else:
                            instrument = self.channel_instruments[
                                message.channel]
                            playing[message.note].append(
                                Note(start=time_samples,
                                     volume=message.velocity * instrument.volume,
                                     pitch=message.note + transpose,
                                     instrument=instrument))
                        volume += message.velocity * instrument.volume
                        self.maxvolume = max(volume, self.maxvolume)
                        self.maxpitch = max(message.note + transpose,
                                            self.maxpitch)
                    elif message.type == "note_off":
                        try:
                            note = playing[message.note].pop()
                        except IndexError:  # the pop will fail if there aren't any matching notes playing
                            print(
                                "Warning: Note end event with no matching begin event @ {}".format(time))
                        if len(playing[message.note]) == 0:
                            del playing[message.note]
                        note.finalize(time_samples)
                        notes[note.start].append(note)
                        self.notecount += 1
                        volume -= note.volume
                    elif message.type == "program_change":
                        self.channel_instruments[message.channel] = \
                            sample.instruments[message.program + 1][0]
                if len(playing) != 0:
                    print("Warning: The MIDI ended with notes still playing.")
                    for notelist in playing.values():
                        for note in notelist:
                            note.length = int(
                                time * sample.framerate) - note.start
                            self.notecount += 1
                self.notes = sorted(notes.items(), key=operator.itemgetter(0))
                self.length = max(
                    max(note.start + note.length for note in nlist) for _, nlist in self.notes)
                self.maxpitch = note_to_freq(self.maxpitch)
        except IOError:
            raise complain.ComplainToUser(
                "Error opening MIDI file '{}'.".format(filename))
        except IndexError:
            raise complain.ComplainToUser(
                "This MIDI file is broken. Try opening it in MidiEditor (https://meme.institute/midieditor) and saving it back out again.")
