"""Parses .swood files."""

# See https://github.com/milkey-mouse/swood/issues/1

from . import complain, sample
from .instruments import *
import zipfile

class Instrument:
    """Holds information about a MIDI instrument."""
    def __init__(self, sample=None, volume=100, pan=0.5):
        self.sample = sample
        self.volume = volume
        self.pan = pan

class SoundFont:
    """Parses and holds information about .swood files."""

    def __init__(self, filename):
        self.instrument_names
        self.instruments = []
        self.percussion = {}
        self.options = {}
        if isinstance(filename, str):
            self.file = open(filename)
        else:
            self.file = filename

        try:
            try:
                self.file = zipfile.ZipFile(
                    self.file, compression=zipfile.ZIP_DEFLATED)
            except RuntimeError:
                self.file = zipfile.ZipFile(self.file)
            self.parse_zip()
        except zipfile.BadZipFile:
            self.parse_ini()

    def parse_zip(self):
        """Parses a ZIP of a .swood INI file and its samples without extracting."""
        try:
            valid_extensions = {"swood", "ini", "txt"}
            ini_path = next(fn for fn in self.file.namelist()
                            if fn.split(".")[-1] in valid_extensions)
        except StopIteration:
            raise complain.ComplainToUser(
                "Couldn't find config file in ZIP. Be sure it ends in .ini, .swood, or .txt.'")
        config_txt = self.file.read(ini_path).replace("\r\n", "\n")
        tokenize(config_txt)

    def strip_comments(self, line):
        hash_index = line.find("#")
        if hash_index == -1:
            return line.strip()
        else:
            return line[:hash_index].strip()

    def tokenize(self, config):
        section = None
        for linenum, text in enumerate(config_txt.split("\n")):
            text = strip_comments(text)
            if line == "":
                continue
            elif text.startswith("[") and text.endswith("]"):
                section = text[1:-1]
            elif "=" in text:
                parts = text.split("=")
                name = parts[0]
                if name not in ("file", "volume", "vol", "pan")
                value = self.get_value(parts[1])
                if section in ("default", "all"):
                    for instrument in instruments:
