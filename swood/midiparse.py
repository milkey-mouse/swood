import collections
import operator

import mido

from . import complain


class Note:
    def __init__(self, length=None, pitch=1, volume=127, starttime=None, bend=0, samplestart=0):
        self.samplestart = samplestart
        self.starttime = starttime
        self.length = length
        self.volume = volume
        self.pitch = pitch
        self.bend = bend

    def __hash__(self):
        return hash((self.length, self.pitch))

    def __eq__(self, other):
        return self.length == other.length and self.pitch == other.pitch and self.bend == other.bend

    def __len__(self):
        return len(self.data)


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
                    time_samples = int(round(time * sample.framerate)
                    if message.type == "note_on":
                        note = Note()
                        note.starttime = time_samples
                        note.volume = 127 if message.velocity == 0 else message.velocity
                        note.pitch = message.note + transpose
                        note.bend = bend
                        playing[message.note].append(note)

                        volume += note.volume
                        self.maxvolume = max(volume, self.maxvolume)
                        self.maxpitch = max(self.maxpitch, note.pitch + note.bend)
                    elif message.type == "note_off":
                        note = playing[message.note].pop(0)
                        if len(playing[message.note]) == 0:
                            del playing[message.note]
                        try:
                            notes[note.starttime].append(note)
                        except IndexError:
                            print("Warning: There was a note end event at {} seconds with no matching begin event".format(time))

                        self.notecount += 1
                        volume -= note.volume
                        note.pitch = self.note_to_freq(note.pitch + note.bend)
                        note.length = time_samples - note.starttime
                        del note.bend
                    elif message.type == "pitchwheel":
                        #stop the note and start a new one at that time
                        bend = message.pitches / 8192 * 12
                        for notelist in playing:
                            for note in notelist:
                                note.samplestart = note.length * sample.length * self.sample.fundamental_freq / note.pitch
                                note.length = time_samples - note.starttime
                                notes[note.starttime].append(note)
                                note.starttime = time_samples
                                self.notecount += 1
                                note.length = None
                                note.bend = bend
                if len(playing) != 0:
                    print("Warning: The MIDI ended with notes still playing, assuming they end when the MIDI does")
                    for ntime, nlist in playing.items():
                        for note in nlist:
                            note.length = int(time * sample.framerate) - note.starttime
                            self.notecount += 1
                self.playing = sorted(notes.items(), key=operator.itemgetter(0))
                self.length = max(max(note.starttime + note.length for note in nlist) for _, nlist in self.playing)
                self.maxpitch = self.note_to_freq(self.maxpitch)
        except IOError:
            raise complain.ComplainToUser("Error opening MIDI file '{}'.".format(filename))
        except IndexError:
            raise complain.ComplainToUser("This MIDI file is broken. Try opening it in MidiEditor (https://meme.institute/midieditor) and saving it back out again.")   

    def note_to_freq(self, notenum):
        # see https://en.wikipedia.org/wiki/MIDI_Tuning_Standard
        return (2.0 ** ((notenum - 69) / 12.0)) * 440.0