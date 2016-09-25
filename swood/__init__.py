import argparse
import os.path
import string
import mido
import sys


def patch_tqdm(tqdm):
    # monkey-patch tqdm to not do fractional chars with 0-9; it looks ugly
    if "patched" not in vars(tqdm) or tqdm.patched == False:
        old_format_meter = tqdm.format_meter
        fm_translation_table = dict.fromkeys(map(ord, string.digits), ord("#"))


        @staticmethod
        def patched_format_meter(*args, **kwargs):
            formatted_bar = old_format_meter(*args, **kwargs)
            try:
                parts = formatted_bar.split("|")
                parts[1] = parts[1].translate(fm_translation_table)
                return "|".join(parts)
            except:
                return formatted_bar

        tqdm.format_meter = patched_format_meter
        tqdm.patched = True


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
        return "swood ??? (dependencies unknown)"


def swoodlive_installed():
    import importlib.util
    return importlib.util.find_spec("swoodlive") is not None


def is_wav(filename):
    with open(filename, "rb") as f:
        riff = f.read(4) == b"RIFF"
        f.read(4)
        wave = f.read(4) == b"WAVE"
        f.seek(0)
        return riff and wave


def run_cmd(argv=sys.argv[1:]):
    basename = os.path.basename(sys.argv[0])
    parser = argparse.ArgumentParser(prog="swood" if basename == "swood-script.py" else basename,
                                     description="swood.exe: the automatic ytpmv generator",
                                     formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument("infile", type=str,
                        help="a short wav file to sample as the instrument, or a swood config file")
    # type=mido.MidiFile works too, but throws more obscure errors
    parser.add_argument("midi", type=str,
                        help="the MIDI to play with the wav sample")
    parser.add_argument("output", type=str,
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
            try:
                config_options = {}
                sample = soundfont.SoundFont(
                    args.infile, config_options, binsize=args.binsize)
                # ensure cli args take precedence over config by
                # only changing arguments currently at their default
                for name, value in config_options.items():
                    for option in parser._actions:
                        if option.dest == name:
                            if option.default == vars(args)[name]:
                                vars(args)[name] = value
                            break
            except:
                sample = soundfont.DefaultFont(
                    sample.Sample(args.infile, args.binsize))
        midi = midiparse.MIDIParser(
            args.midi, sample, args.transpose, args.speed)
        renderer = render.NoteRenderer(sample, args.fullclip, args.cachesize)
        renderer.render(midi, args.output, pbar=args.no_pbar)


if __name__ == "__main__":
    run_cmd()
