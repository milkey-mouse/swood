import collections
import operator

import mido

import complain

class Note:
    def __init__(self, length=None, pitch=None, volume=None, starttime=None):
        self.starttime = starttime
        self.length = length
        self.volume = volume
        self.pitch = pitch

    def __hash__(self):
        return hash((self.length, self.pitch))

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
    def __init__(self, filename, wav, transpose=0, speed=1):  # TODO: convert the rest of the function to the new notes
        if speed <= 0:
            return ValueError("The speed must be a positive number.")
        results = collections.defaultdict(list)
        notes = collections.defaultdict(list)
        self.notecount = 0
        self.maxvolume = 0
        self.maxpitch = 0
        volume = 0

        try:
            with mido.MidiFile(filename, "r") as mid:
                time = 0
                for message in mid:
                    time += message.time
                    if "channel" in vars(message) and message.channel == 10:
                        continue  # channel 10 is reserved for percussion
                    if message.type == "note_on":
                        note = Note()
                        note.starttime = int(round(time * wav.framerate / speed))
                        note.volume = 127 if message.velocity == 0 else message.velocity
                        note.pitch = self.note_to_freq(message.note + transpose)

                        notes[message.note].append(note)
                        volume += note.volume
                        self.maxvolume = max(volume, self.maxvolume)
                    elif message.type == "note_off":
                        note = notes[message.note].pop(0)
                        if len(notes[message.note]) == 0:
                            del notes[message.note]

                        try:
                            results[note.starttime].append(note)
                        except IndexError:
                            print("Warning: There was a note end event at {} seconds with no matching begin event".format(time))

                        self.notecount += 1
                        volume -= note.volume
                        self.maxpitch = max(self.maxpitch, note.pitch)
                        note.length = int(time * wav.framerate / speed) - note.starttime

                if len(notes) != 0:
                    print("Warning: The MIDI ended with notes still playing, assuming they end when the MIDI does")
                    for ntime, nlist in notes.items():
                        for note in nlist:
                            note.length = int(time * wav.framerate / speed) - note.starttime
                            self.notecount += 1

                if self.notecount == 0:
                    raise complain.ComplainToUser("This MIDI file doesn't have any notes in it!")

                self.notes = sorted(results.items(), key=operator.itemgetter(0))
                self.length = max(max(note.starttime + note.length for note in nlist) for _, nlist in self.notes)
        except (IOError, IndexError):
            raise complain.ComplainToUser("This MIDI file is broken. Try opening it in MidiEditor (https://meme.institute/midieditor) and saving it back out again.")

    def note_to_freq(self, notenum):
        # see https://en.wikipedia.org/wiki/MIDI_Tuning_Standard
        return (2.0 ** ((notenum - 69) / 12.0)) * 440.0
