from __future__ import print_function
import sys

if sys.version_info.major < 3 or (sys.version_info.major == 3 and sys.version_info.minor < 4):
    print("Sorry, swood.exe requires at least Python 3.4 to run correctly.")
    sys.exit(1)

from PIL import Image

import traceback
import os


class ComplainToUser(Exception):
    pass


def run_cmd():
    try:
        transpose = 0
        speed = 1.0
        threshold = 0.075
        binsize = 8192
        cachesize = 7.5
        fullclip = False
        alg = Image.BICUBIC
        if len(sys.argv) <= 3:
            import pkg_resources
            import importlib
            try:
                version = pkg_resources.get_distribution("swood").version
            except pkg_resources.DistributionNotFound:
                version = "?"
            print("swood - the automatic ytpmv generator (v. {})".format(version))
            print("")
            print("usage: swood in_wav in_midi out_wav")
            print("  in_wav: a short wav file to use as the instrument for the midi")
            print("  in_midi: a midi to output with the wav sample as the instrument")
            print("  out_wav: location for the finished song as a wav")
            print("")
            print("options:")
            print("  --transpose=0      transpose the midi by n semitones")
            print("  --speed=1.0        speed up the midi by this multiplier")
            print("  --threshold=0.075  maximum amount of time after a note ends that it can go on for a smoother ending")
            print("  --binsize=8192     FFT bin size for the sample analysis; lower numbers make it faster but more off-pitch")
            print("  --cachesize=7.5    note cache size (seconds); lower could speed up repetitive songs, using more memory")
            print("  --linear           use a lower quality scaling algorithm that will be a little bit faster")
            print("  --fullclip         no matter how short the note, always use the full sample without cropping")
            print("  --optout           opt out of automatic bug reporting (or you can set the env variable SWOOD_OPTOUT)")
            if importlib.util.find_spec("swoodlive"):
                print("  --live             listen on a midi input and generate the output in realtime")
            return
        for arg in sys.argv[4:]:
            try:
                if arg == "--linear":
                    alg = Image.BILINEAR
                elif arg == "--fullclip":
                    fullclip = True
                elif arg == "--optout":
                    pass
                elif arg.startswith("--transpose="):
                    transpose = int(arg[len("--transpose="):])
                elif arg.startswith("--speed="):
                    speed = float(arg[len("--speed="):])
                elif arg.startswith("--threshold="):
                    threshold = float(arg[len("--threshold="):])
                elif arg.startswith("--binsize="):
                    binsize = int(arg[len("--binsize="):])
                else:
                    raise ComplainToUser("Unrecognized command-line option '{}'.".format(arg))
            except ValueError:
                raise ComplainToUser("Error parsing command-line option '{}'.".format(arg))

        for i in (1, 2):
            if not os.path.isfile(sys.argv[i]):
                ext = ".mid" if i == 2 else ".wav"
                if os.path.isfile(sys.argv[i] + ext):
                    sys.argv[i] += ext
                else:
                    raise ComplainToUser("No file found at path '{}'.".format(sys.argv[i]))
        if not sys.argv[3].endswith(".wav"):
            sys.argv[3] += ".wav"

        sample = Sample(sys.argv[1], binsize)
        midi = MIDIParser(sys.argv[2], sample, transpose, speed)
        renderer = NoteRenderer(sample, alg, fullclip, threshold, cachesize)
        renderer.render(midi, sys.argv[3])
    except Exception as you_tried:
        if isinstance(you_tried, ComplainToUser):
            print("Error: {}".format(you_tried))
        else:
            tb = traceback.format_exc()
            if "--optout" in sys.argv or os.environ.get("SWOOD_OPTOUT") is not None:
                print("Something went wrong. A bug report will not be sent because of your environment variable/CLI option.")
                print(tb)
            else:
                print("Something went wrong. A bug report will be sent to help figure it out. (see --optout)")
                try:
                    import http.client
                    conn = http.client.HTTPSConnection("meme.institute")
                    conn.request("POST", "/swood/bugs/submit", tb)
                    resp = conn.getresponse().read().decode("utf-8")
                    if resp == "done":
                        print("New bug submitted!")
                    elif resp == "dupe":
                        print("This bug is already in the queue to be fixed.")
                    else:
                        raise Exception
                except Exception:
                    traceback.print_exc()
                    print("Well apparently we can't even send a bug report right. Sorry about that.")


if __name__ == "__main__":
    run_cmd()
