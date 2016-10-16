"""Parses .swood files."""

# See https://github.com/milkey-mouse/swood/issues/1

from os.path import normpath, abspath, dirname, join
from collections import defaultdict
from enum import Enum

from PIL.Image import BILINEAR
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
        return "Syntax error on line {}:\n".format(self.line + 1) + \
               self.line_text + "\n" + self.error_desc


class Instrument:
    """Holds information about a MIDI instrument or track."""

    def __init__(self, fullclip=False, noscale=False, sample=None, volume=0.9, pan=0.5, pitch=None):
        self.fullclip = fullclip
        self.noscale = noscale
        self.sample = sample
        self.volume = volume
        self.pitch = pitch
        self.pan = pan

    def __hash__(self):
        if isinstance(self.sample, Sample):
            return hash((self.noscale, self.sample.filename, self.volume, self.pan))
        else:
            return hash((self.noscale, None, self.volume, self.pan))

    def __eq__(self, other):
        return hash(self) == hash(other)

    def __repr__(self):
        return "Instrument(noscale={}, sample={}, volume={}, pan={})".format(self.noscale, self.sample, self.volume, self.pan)


class SoundFont:
    """Parses and holds information about .swood files."""

    def __init__(self, filename, arguments, binsize=8192, pbar=True):
        self.arguments = arguments
        self._binsize = binsize
        self.pbar = pbar
        self.load_instruments()
        self.samples = set()
        self.channels = {}

        if isinstance(filename, str):
            self.file = open(filename)
        elif filename is not None:
            self.file = filename

        if filename is not None:
            if zipfile.is_zipfile(self.file):
                self.file = zipfile.ZipFile(self.file)
                self.load_zip()
                self.load_samples_from_zip()
            else:
                self.load_ini()
                self.load_samples_from_txt()

    def load_instruments(self):
        self.instruments = defaultdict(list)
        self.percussion = defaultdict(list)
        for names in instruments:
            new_instrument = Instrument()
            for name in names:
                if isinstance(name, str):
                    name = name.lower()
                self.instruments[name].append(new_instrument)
                self.instruments["non-percussion"].append(new_instrument)
            self.instruments["all"].append(new_instrument)
        # percussion is a bit weird as it doesn't actually use MIDI instruments;
        # any event on channel 10 is percussion, and the actual instrument is
        # denoted by the note number (with valid #s ranging 35-81).
        for idx, *names in percussion:
            new_instrument = Instrument(fullclip=True, noscale=True)
            self.percussion[idx].append(new_instrument)
            for name in names:
                if isinstance(name, str):
                    name = name.lower()
                self.percussion[name].append(new_instrument)
                self.percussion["percussion"].append(new_instrument)
            self.instruments["all"].append(new_instrument)

    def load_ini(self):
        self.file.seek(0)
        if "b" in self.file.mode:
            self.parse(self.file.read().decode("utf-8"))
        else:
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
        self.parse(config_txt.decode("utf-8"))

    def strip_comments(self, line):
        hash_index = line.find("#")
        if hash_index == -1:
            return line.strip(string.whitespace + "\n")
        else:
            return line[:hash_index].strip(string.whitespace + "\n")

    def parse(self, config):
        affected_instruments = []
        parse_arguments = None
        for linenum, raw_text in enumerate(config.replace("\r\n", "\n").split("\n")):
            text = self.strip_comments(raw_text)
            if text == "":
                continue
            elif text.startswith("[") and text.endswith("]"):
                header_name = text[1:-1].lower()
                if header_name in ("arguments", "args", "options"):
                    affected_instruments = []
                    parse_arguments = True
                elif header_name in ("default", "all"):
                    affected_instruments = self.instruments["all"]
                    parse_arguments = False
                elif header_name in self.instruments:
                    affected_instruments = self.instruments[header_name]
                    parse_arguments = False
                elif header_name in self.percussion:
                    affected_instruments = self.percussion[header_name]
                    parse_arguments = False
                elif header_name in ("non percussion", "nonpercussion"):
                    affected_instruments = self.percussion["non-percussion"]
                    parse_arguments = False
                elif len(header_name) == 3 and header_name.startswith("p"):
                    try:
                        affected_instruments = \
                            self.percussion[int(header_name[1:])]
                        parse_arguments = False
                    except (ValueError, KeyError):
                        raise SoundFontSyntaxError(
                            linenum, raw_text, "Header not recognized.")
                else:
                    raise SoundFontSyntaxError(
                        linenum, raw_text, "Header not recognized.")
            elif "=" in text:
                parts = text.split("=")
                name = parts[0].strip()
                value = parts[1]
                if parse_arguments is None:
                    raise SoundFontSyntaxError(
                        linenum, raw_text,
                        "No header specified. For defaults, specify '[default]' on the line before."
                    )
                elif parse_arguments:
                    possible_args = {
                        "transpose": int,
                        "speed": float,
                        "cachesize": float,
                        "binsize": int,
                    }
                    if name in possible_args:
                        try:
                            self.arguments[name] = possible_args[name](value)
                        except ValueError:
                            raise SoundFontSyntaxError(
                                linenum, raw_text, "'{}' is not a valid value for '{}'".format(value, name))
                elif name in ("file", "sample"):
                    for instrument in affected_instruments:
                        if value.lower() in ("", "none", "null"):
                            instrument.sample = None
                        else:
                            instrument.sample = value
                            self.samples.add(value)
                elif name in ("volume", "vol"):
                    for instrument in affected_instruments:
                        try:
                            instrument.volume = int(value) / 100
                            if instrument.volume > 0.95:
                                print(
                                    "Warning: Volumes higher than 95 may cause clipping or other glitches")
                        except ValueError:
                            raise SoundFontSyntaxError(
                                linenum, raw_text, "'{}' is not a valid number".format(value))
                elif name == "pan":
                    for instrument in affected_instruments:
                        try:
                            pan = float(value)
                            if pan < 0 or pan > 1:
                                raise SoundFontSyntaxError(
                                    linenum, raw_text, "'{}' is outside of the allowed 0.0-1.0 range".format(value))
                            else:
                                instrument.pan = pan
                        except ValueError:
                            raise SoundFontSyntaxError(
                                linenum, raw_text, "'{}' is not a valid number".format(value))
                elif name == "pitch":
                    for instrument in affected_instruments:
                        try:
                            pitch = float(value)
                            if pan < 0:
                                raise SoundFontSyntaxError(
                                    linenum, raw_text, "'{}' is below 0".format(value))
                            else:
                                instrument.pitch = pitch
                        except ValueError:
                            raise SoundFontSyntaxError(
                                linenum, raw_text, "'{}' is not a valid number".format(value))
                elif name == "fullclip":
                    for instrument in affected_instruments:
                        if value.lower() in ("true", "1"):
                            instrument.fullclip = True
                        elif value.lower() in ("false", "0"):
                            instrument.fullclip = False
                        else:
                            raise SoundFontSyntaxError(linenum, raw_text,
                                                       "fullclip must be 'True' or 'False'; '{}' is invalid".format(value))
                elif name == "noscale":
                    for instrument in affected_instruments:
                        if value.lower() in ("true", "1"):
                            instrument.noscale = True
                        elif value.lower() in ("false", "0"):
                            instrument.noscale = False
                        else:
                            raise SoundFontSyntaxError(linenum, raw_text,
                                                       "noscale must be 'True' or 'False'; '{}' is invalid".format(value))
                else:
                    raise SoundFontSyntaxError(
                        linenum, raw_text, "'{}' is not a valid property".format(name))

    def wavpath(self, relpath):
        # only works on non-zip files
        return normpath(join(dirname(abspath(self.file.name)), relpath))

    def load_samples_from_txt(self):
        loaded_samples = {}
        for fn in self.samples:
            loaded_samples[fn] = Sample(
                self.wavpath(fn),
                self._binsize,
                pbar=self.pbar
            )
        self.add_samples(loaded_samples)

    def load_samples_from_zip(self):
        loaded_samples = {}
        for fn in self.samples:
            try:
                with self.file.open(fn) as zipped_wav:
                    loaded_samples[fn] = Sample(
                        zipped_wav, self._binsize, pbar=self.pbar)
            except KeyError:  # file not found in zip
                raise complain.ComplainToUser(
                    "Sample '{}' not found in config ZIP")
        self.add_samples(loaded_samples)

    def add_samples(self, loaded_samples):
        for instruments in self.instruments.values():
            for instrument in instruments:
                if isinstance(instrument.sample, str):
                    real_instrument = loaded_samples[instrument.sample]
                    real_instrument.fundamental_freq = instrument.pitch
                    instrument.sample = real_instrument
        self.framerate = max(s.framerate for s in loaded_samples.values())
        self.channels = max(s.channels for s in loaded_samples.values())
        self.length = max(len(s) for s in loaded_samples.values())
        for samp in loaded_samples.values():
            multiplier = self.framerate / samp.framerate
            samp._img = samp.img.resize(
                (int(round(samp.img.size[0] * multiplier)), samp.channels),
                resample=BILINEAR)
            samp.framerate = self.framerate
        for instruments in self.instruments.values():
            for instrument in instruments:
                if isinstance(instrument.sample, str):
                    instrument.sample = loaded_samples[instrument.sample]
        if self.channels != 2:
            warned_pan = False
            for instruments in self.instruments.values():
                for instrument in instruments:
                    if instrument.pan != 0.5:
                        instrument.pan = 0.5
                        if not warned_pan:
                            print("Warning: Audio has >2 channels; pan ignored")
                            warned_pan = True

    def __len__(self):
        return self.length


def DefaultFont(samp):
    sf = SoundFont(None, None, pbar=samp.pbar)
    sf.framerate = samp.framerate
    sf.channels = samp.channels
    sf.length = samp.length
    for instruments in sf.instruments.values():
        for instrument in instruments:
            instrument.sample = samp
    return sf
