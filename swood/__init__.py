from __future__ import print_function
import sys

if sys.version_info.major < 3 or (sys.version_info.major == 3 and sys.version_info.minor < 4):
    print("Sorry, swood.exe requires at least Python 3.4 to run correctly.")
    sys.exit(1)

import complain


def run_cmd():
    with complain.ComplaintFormatter():
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
            print("  --fullclip         no matter how short the note, always use the full sample without cropping")
            print("  --optout           opt out of automatic bug reporting (or you can set the env variable SWOOD_OPTOUT)")
            if importlib.util.find_spec("swoodlive"):
                print("  --live             listen on a midi input and generate the output in realtime")
            return

        import midiparse
        import renderer
        import sample
        

        transpose = 0
        speed = 1.0
        threshold = 0.075
        binsize = 8192
        cachesize = 7.5
        fullclip = False

        for arg in sys.argv[4:]:
            try:
                if arg == "--fullclip":
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

        sample = sample.Sample(sys.argv[1], binsize)
        midi = midiparse.MIDIParser(sys.argv[2], sample, transpose, speed)
        renderer = renderer.NoteRenderer(sample, fullclip, threshold, cachesize)
        renderer.render(midi, sys.argv[3])



if __name__ == "__main__":
    run_cmd()
