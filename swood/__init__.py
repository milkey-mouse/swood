import argparse
import mido
import sys


def version_info():
    try:
        import pkg_resources
        versions = []
        for pkg in ("swood", "pillow-simd", "pillow", "PIL", "pyFFTW", "mido"):
            try:
                versions.append(str(pkg_resources.get_distribution(pkg)))
            except pkg_resources.DistributionNotFound:
                pass
        return " ".join(versions)
    except:
        return "???"


def swoodlive_installed():
    import importlib.util
    return importlib.util.find_spec("swoodlive") is not None


def is_wav(f):
    riff = f.read(4) == b"RIFF"
    f.read(4)
    wave = f.read(4) == b"WAVE"
    f.seek(0)
    return riff and wave


def run_cmd(argv=sys.argv):
    parser = argparse.ArgumentParser(
        description="swood.exe: the automatic ytpmv generator", formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument("infile", type=argparse.FileType("rb"),
                        help="a short wav file to sample as the instrument, or a swood config file")
    parser.add_argument("midi", type=mido.MidiFile,
                        help="the MIDI to play with the wav sample")
    parser.add_argument("output", type=argparse.FileType("wb"),
                        help="path for the output wav file")

    parser.add_argument("--transpose", "-t", type=int,
                        default=0, help="amount to transpose (semitones)")
    parser.add_argument("--speed", "-s", type=float,
                        default=1.0, help="speed multiplier for the MIDI")
    parser.add_argument("--cachesize", "-c", type=float,
                        default=7.5, help="how long to save cached notes")
    parser.add_argument("--binsize", "-b", type=int, default=8192,
                        help="FFT bin size; lower numbers make it faster but more off-pitch")
    parser.add_argument("--fullclip", "-f", action="store_true",
                        help="always use the full sample without cropping")
    parser.add_argument("--no-pbar", "-p", action="store_false",
                        help=argparse.SUPPRESS)

    if swoodlive_installed():
        parser.add_argument("--live",
                            help="listen on a midi input and generate the output in realtime")

    parser.add_argument("--optout", "-o", action="store_true",
                        help="opt out of automatic bug reporting (or set the env variable SWOOD_OPTOUT)")
    parser.add_argument("--version", "-v", action="version", version=version_info(),
                        help="get the versions of swood and its dependencies")

    args = parser.parse_args(argv)

    from . import complain, midiparse, render, sample, soundfont

    with complain.ComplaintFormatter():
        if is_wav(args.infile):
            sample = soundfont.DefaultFont(
                sample.Sample(args.infile, args.binsize))
        else:
            sample = soundfont.SoundFont(args.infile, args)
            # reparse to ensure cli args take precedence over config
            parser.parse_args(argv, args)
        midi = midiparse.MIDIParser(
            args.midi, sample, args.transpose, args.speed)
        renderer = render.NoteRenderer(sample, args.fullclip, args.cachesize)
        renderer.render(midi, args.output, pbar=args.no_pbar)


if __name__ == "__main__":
    run_cmd()
