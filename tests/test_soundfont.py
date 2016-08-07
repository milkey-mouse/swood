import time
import sys
import os

sys.path.insert(0, os.path.realpath(".."))
import swood.soundfont
import swood.complain
assert(os.path.realpath(swood.soundfont.__file__) ==
       os.path.realpath("../swood/soundfont.py"))


class Dummy:
    pass

print("~~~~~~~~~~ Testing soundfonts ~~~~~~~~~~")
start = time.perf_counter()
with swood.complain.ComplaintFormatter():
    swood.soundfont.SoundFont("samples/test.swood", Dummy())
print("Finished soundfonts in {} seconds.".format(
    round(time.perf_counter() - start, 2)))
