from copy import copy
import collections
import operator

import mido

from . import complain

def note_to_freq(notenum):
        # see https://en.wikipedia.org/wiki/MIDI_Tuning_Standard
        return (2.0 ** ((min(notenum, 0) - 69) / 12.0)) * 440.0

class Note:
    def __init__(self, samplestart=0, length=0, volume=127, start=0, pitch=0, bend=0):
        self.samplestart = samplestart
        self.length = length
        self.volume = volume
        self.start = start
        self.pitch = pitch
        self.bend = bend

    def __hash__(self):
        return hash((self.length, self.pitch))

    def __eq__(self, other):
        return self.length == other.length and self.pitch == other.pitch

    def __len__(self):
        return len(self.data)

    def __repr__(self):
        return "Note(length={}, pitch={}, start={}, samplestart={}, bend={})".format(self.length, self.pitch, self.start, self.samplestart, self.bend)

    def finalize(self, time):
        self.pitch = note_to_freq(self.pitch + self.bend)
        self.length = time - self.start
        return self

class CachedNote:
    def __init__(self, length, rendered):
        self.used = 1
        self.length = length
        self.data = rendered

    def __len__(self):
        return len(self.data)


class MIDIParser:
    def __init__(self, filename, sample, transpose=0, speed=1):  # TODO: convert the rest of the function to the new notes
        playing = collections.defaultdict(list)
        notes = collections.defaultdict(list)
        self.notecount = 0
        self.maxvolume = 0
        self.maxpitch = 0
        volume = 0
        bend = 0

        try:
            with (mido.MidiFile(filename, "r") if isinstance(filename, str) else filename) as mid:
                time = 0
                for message in mid:
                    time += message.time / speed
                    if "channel" in vars(message) and message.channel == 10:
                        continue  # channel 10 is reserved for percussion
                    time_samples = int(round(time * sample.framerate))
                    # ugh, string-typing
                    if message.type == "note_on":
                        playing[message.note].append(
                            Note(start=time_samples,
                            volume=message.velocity,
                            pitch=message.note+transpose,
                            bend=bend))
                        volume += message.velocity
                        self.maxvolume = max(volume, self.maxvolume)
                        self.maxpitch = max(self.maxpitch, message.note + transpose + bend)
                    elif message.type == "note_off":
                        try:
                            note = playing[message.note].pop()
                        except IndexError:  # the pop will fail if there aren't any matching notes playing
                            print("Warning: There was a note end event at {} seconds with no matching begin event".format(time))
                        if len(playing[message.note]) == 0:
                            del playing[message.note]
                        note.finalize(time_samples)
                        note.bend = False
                        notes[note.start].append(note)
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
                                    notes[note.start].append(oldnote)

                                    note.samplestart = int(round(note.length * sample.fundamental_freq / note.pitch))
                                    note.start = note.length
                                    self.notecount += 1
                                    note.length = None
                                    note.bend = bend
                if len(playing) != 0:
                    print("Warning: The MIDI ended with notes still playing, assuming they end when the MIDI does")
                    for notelist in playing.values():
                        for note in notelist:
                            note.length = int(time * sample.framerate) - note.start
                            self.notecount += 1
                self.notes = sorted(notes.items(), key=operator.itemgetter(0))
                self.length = max(max(note.start + note.length for note in nlist) for _, nlist in self.notes)
                self.maxpitch = note_to_freq(self.maxpitch)
                import pprint
                pprint.pprint(self.notes)
        except IOError:
            raise complain.ComplainToUser("Error opening MIDI file '{}'.".format(filename))
        except IndexError:
            raise complain.ComplainToUser("This MIDI file is broken. Try opening it in MidiEditor (https://meme.institute/midieditor) and saving it back out again.")