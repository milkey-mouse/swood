"""Parses .swood files."""

# See https://github.com/milkey-mouse/swood/issues/1

from os.path import normpath, abspath, dirname, join
from collections import defaultdict
from .sample import Sample
from .instruments import *
from . import complain
import zipfile
import string

# user-friendly repr for zip-loaded samples
zipfile.ZipExtFile.__repr__ = (
    lambda self: "<zipped WAV file '{}'>".format(self.name))


class SoundFontSyntaxError(complain.ComplainToUser, SyntaxError):
    """Tells the user when something is wrong with the config file."""

    def __init__(self, line, line_text, error_desc):
        self.line = line
        self.line_text = line_text
        self.error_desc = error_desc

    def __str__(self):
        return "Syntax error on line {}:\n".format(self.line) + \
               self.line_text + "\n" + self.error_desc


class Instrument:
    """Holds information about a MIDI instrument (or channel)."""

    def __init__(self, sample=None, volume=100, pan=0.5):
        self.sample = sample
        self.volume = volume
        self.pan = pan

    def __repr__(self):
        return "Instrument(sample={}, volume={}, pan={})".format(self.sample, self.volume, self.pan)


class SoundFont:
    """Parses and holds information about .swood files."""

    def __init__(self, filename):
        self.load_instruments()
        self.channels = {}
        self.options = {}
        self.samples = set()

        if isinstance(filename, str):
            self.file = open(filename)
        else:
            self.file = filename

        if zipfile.is_zipfile(self.file):
            self.file = zipfile.ZipFile(self.file)
            self.load_zip()
        else:
            self.load_ini()

        self.load_samples()

    def load_instruments(self):
        self.instruments = defaultdict(set)
        for names in instruments:
            new_instrument = Instrument()
            for name in names:
                self.instruments[name].add(new_instrument)
            self.instruments["default"].add(new_instrument)
            self.instruments["all"].add(new_instrument)
        # percussion is a bit weird as it doesn't actually use MIDI instruments;
        # any event on channel 10 is percussion, and the actual instrument is
        # denoted by the note number (with valid #s ranging 35-81).
        for idx, *names in percussion:
            new_instrument = Instrument()
            self.instruments["p" + str(idx)].add(new_instrument)
            for name in names:
                self.instruments[name].add(new_instrument)
            self.instruments["default"].add(new_instrument)
            self.instruments["all"].add(new_instrument)

    def load_ini(self):
        self.file.seek(0)
        self.parse(self.file.read())

    def load_zip(self):
        """Parses a ZIP of a .swood INI file and its samples without extracting."""
        try:
            valid_extensions = {"swood", "ini", "txt"}
            ini_path = next(fn for fn in self.file.namelist()
                            if fn.split(".")[-1] in valid_extensions)
        except StopIteration:
            raise complain.ComplainToUser(
                "Couldn't find config file in ZIP. Be sure it ends in .ini, .swood, or .txt.'")
        config_txt = self.file.read(ini_path)
        tokenize(config_txt)

    def strip_comments(self, line):
        hash_index = line.find("#")
        if hash_index == -1:
            return line.strip(string.whitespace + "\n")
        else:
            return line[:hash_index].strip(string.whitespace + "\n")

    def parse(self, config):
        affected_instruments = []
        for linenum, raw_text in enumerate(config.replace("\r\n", "\n").split("\n")):
            text = self.strip_comments(raw_text)
            if text == "":
                continue
            elif text.startswith("[") and text.endswith("]"):
                affected_instruments = self.instruments[text[1:-1]]
            elif "=" in text:
                parts = text.split("=")
                name = parts[0].strip()
                if name in ("file", "sample"):
                    for instrument in affected_instruments:
                        if parts[1].lower() not in ("", "none", "null"):
                            instrument.sample = parts[1]
                            self.samples.add(parts[1])
                elif name in ("volume", "vol"):
                    for instrument in affected_instruments:
                        if parts[1] != "0":
                            try:
                                instrument.volume = int(parts[1])
                            except ValueError:
                                raise SoundFontSyntaxError(
                                    linenum, raw_text, "'{}' is not a valid number".format(parts[1]))
                elif name == "pan":
                    for instrument in affected_instruments:
                        try:
                            pan = float(parts[1])
                        except ValueError:
                            raise SoundFontSyntaxError(
                                linenum, raw_text, "'{}' is not a valid number".format(parts[1]))
                            if pan < 0 or pan > 1:
                                raise SoundFontSyntaxError(
                                    linenum, raw_text, "'{}' is outside of the allowed 0.0-1.0 range".format(parts[1]))
                            else:
                                instrument.pan = pan
                        instrument.pan = float(parts[1])
                else:
                    raise SoundFontSyntaxError(
                        linenum, raw_text, "'{}' is not a valid property".format(name))

    def wavpath(self, relpath):
        # only works on non-zip files
        return normpath(join(dirname(abspath(self.file.name)), relpath))

    def load_samples(self):
        loaded_samples = {fn: Sample(self.wavpath(fn)) for fn in self.samples}
        for instruments in self.instruments.values():
            for instrument in instruments:
                if isinstance(instrument.sample, str):
                    instrument.sample = loaded_samples[instrument.sample]

    def load_samples_from_zip(self):
        loaded_samples = {}
        for fn in self.samples:
            filepath = normpath(join(dirname(abspath(self.file.fp.name)), fn))
            with self.file.open(filepath) as zipped_wav:
                loaded_samples[fn] = Sample(zipped_wav)
        for instruments in self.instruments.values():
            for instrument in instruments:
                if isinstance(instrument.sample, str):
                    instrument.sample = loaded_samples[instrument.sample]
