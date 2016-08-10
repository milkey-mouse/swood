"""Parses MIDI files into a list of notes in chronological order."""

from copy import copy
import collections
import operator

import mido

from . import complain


def note_to_freq(notenum):
    """Converts a MIDI note number to a frequency.

    See https://en.wikipedia.org/wiki/MIDI_Tuning_Standard
    """
    return (2.0 ** ((notenum - 69) / 12.0)) * 440.0


class Note:
    """Holds information about each MIDI note."""

    def __init__(self, samplestart=0, length=0, volume=127, starttime=0, pitch=0, bend=0):
        self.samplestart = samplestart
        self.starttime = starttime
        self.length = length
        self.volume = volume
        self.pitch = pitch
        self.bend = bend

    def __hash__(self):
        return hash((self.length, self.pitch, self.samplestart))

    def __eq__(self, other):
        return self.length == other.length and self.pitch == other.pitch

    def __len__(self):
        return len(self.data)

    def __repr__(self):
        return "Note(length={}, pitch={}, starttime={}, samplestart={}, bend={})".format(
            self.length, self.pitch, self.starttime, self.samplestart, self.bend)

    def finalize(self, time):
        self.pitch = note_to_freq(self.pitch + self.bend)
        self.length = time - self.starttime
        return self


class MIDIParser:
    """Parses a MIDI file into a chronological list of notes."""

    def __init__(self, filename, sample, transpose=0, speed=1):
        playing = collections.defaultdict(list)
        notes = collections.defaultdict(list)
        self.notecount = 0
        self.maxvolume = 0
        self.maxpitch = 0
        volume = 0
        bend = 0

        try:
            with (mido.MidiFile(filename, "r") if isinstance(filename, str) else filename) as mid:
                if mid.type == 2:
                    raise complain.ComplainToUser(
                        "Type 2 (asynchronous) MIDI files are not supported.")
                time = 0
                # label messages from each track
                for track_idx, track in enumerate(mid.tracks):
                    for message in track:
                        # mido hooks __setattr__ so can't set stuff directly
                        vars(message)["track_idx"] = track_idx
                for message in mid:
                    time += message.time / speed
                    if "channel" in vars(message) and message.channel == 10:
                        continue  # channel 10 is reserved for percussion
                    time_samples = int(round(time * sample.framerate))
                    # ugh, string-typing
                    if message.type == "note_on":
                        playing[message.note].append(
                            Note(starttime=time_samples,
                                 volume=message.velocity,
                                 pitch=message.note + transpose,
                                 bend=bend))
                        volume += message.velocity
                        self.maxvolume = max(volume, self.maxvolume)
                        self.maxpitch = max(
                            self.maxpitch, message.note + transpose + bend)
                    elif message.type == "note_off":
                        try:
                            note = playing[message.note].pop()
                        except IndexError:  # the pop will fail if there aren't any matching notes playing
                            print(
                                "Warning: Note end event with no matching begin event @ {}".format(time))
                        if len(playing[message.note]) == 0:
                            del playing[message.note]
                        note.finalize(time_samples)
                        note.bend = False
                        notes[note.starttime].append(note)
                        self.notecount += 1
                        volume -= note.volume
                    elif message.type == "pitchwheel":
                        # stop the note and start a new one at that time
                        newbend = message.pitch / 8192 * 12
                        if newbend != bend:
                            bend = newbend
                            for notelist in playing.values():
                                for note in notelist:
                                    oldnote = copy(note)
                                    oldnote.finalize(time_samples)
                                    oldnote.bend = True
                                    notes[note.starttime].append(oldnote)

                                    note.samplestart = int(
                                        round(oldnote.length / oldnote.pitch))
                                    note.start = oldnote.length
                                    self.notecount += 1
                                    note.length = None
                                    note.bend = bend
                if len(playing) != 0:
                    print("Warning: The MIDI ended with notes still playing.")
                    for notelist in playing.values():
                        for note in notelist:
                            note.length = int(
                                time * sample.framerate) - note.start
                            self.notecount += 1
                self.notes = sorted(notes.items(), key=operator.itemgetter(0))
                self.length = max(
                    max(note.starttime + note.length for note in nlist) for _, nlist in self.notes)
                self.maxpitch = note_to_freq(self.maxpitch)
        except IOError:
            raise complain.ComplainToUser(
                "Error opening MIDI file '{}'.".format(filename))
        except IndexError:
            raise complain.ComplainToUser(
                "This MIDI file is broken. Try opening it in MidiEditor (https://meme.institute/midieditor) and saving it back out again.")
