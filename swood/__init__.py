from . import complain
import sys

def print_version_info():
    import pkg_resources
    for pkg in ("swood", "pillow-simd", "pillow", "PIL", "pyFFTW"):
        try:
            print(pkg_resources.get_distribution(pkg))
        except pkg_resources.DistributionNotFound:
            pass

def swoodlive_installed():
    import importlib.util
    return importlib.util.find_spec("swoodlive") is not None

def run_cmd():
    with complain.ComplaintFormatter():
        parser = argparse.ArgumentParser(description="swood.exe: the automatic ytpmv generator")
        
        parser.add_argument("in_wav", type=argparse.FileType("rb"), help="a short wav file to sample as the instrument for the midi")
        parser.add_argument("in_midi", type=argparse.FileType("rb"), help="a midi to output with the wav sample as the instrument")
        parser.add_argument("out_wav", type=argparse.FileType("wb"), help="path for the wav file of the finished song")
        
        parser.add_argument("--fullclip")
        
        print("swood - the automatic ytpmv generator " + version)
        print("")
        print("usage: swood in_midi out_wav")
        print("  in_wav: ")
        print("  in_midi: ")
        print("  out_wav: ")
        print("")
        print("options:")
        print("  --transpose=0      transpose the midi by n semitones")
        print("  --speed=1.0        speed up the midi by this multiplier")
        print("  --threshold=0.075  maximum amount of time after a note ends that it can go on for a smoother ending")
        print("  --binsize=8192     FFT bin size for the sample analysis; lower numbers make it faster but more off-pitch")
        print("  --cachesize=7.5    note cache size (seconds); lower could speed up repetitive songs, using more memory")
        print("  --fullclip         no matter how short the note, always use the full sample without cropping")
        print("  --optout           opt out of automatic bug reporting (or you can set the env variable SWOOD_OPTOUT)")
        if swoodlive_installed():
            print("  --live             listen on a midi input and generate the output in realtime")
        return

    from . import midiparse
    from . import renderer
    from . import sample
    

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
