# mfvitools
some things i wrote to make ff6 music importing/editing easier  
* [windows binaries](https://github.com/emberling/mfvitools/releases)

Currently these are focused on manipulating song data through the MML (Music Macro Language) text format. Legacy hex based tools are provided in a subfolder, but these have little to no utility anymore.

## MFVI2MML

Converts binary FF6 format music sequence data into mfvitools MML format. The sequence will be represented as accurately as possible -- every byte translated into its equivalent. This MML format is designed to represent any valid FF6 sequence without loss, except for some extreme edge cases involving pointers that point to the middle of a command. If you have a _data.bin and _inst.bin file, it will import from both.

## MML2MFVI

Converts mfvitools MML format into binary FF6 format. Outputs a data file with 38-byte header (ready to insert into ROM) and a 32-byte inst file.

Format is based on rs3extool MML but extended and altered. Documentation [on github wiki](https://github.com/emberling/mfvitools/wiki/).

## INSERTMFVI

General music insertion tool for FF6. Supports raw data and MML import for sequences. Can also import custom BRR samples defined either in imported MMLs or in independent sample list files. Handles song, sample, and ROM expansion automatically. More detailed documentation [here](https://github.com/emberling/mfvitools/wiki/insertmfvi)

## SQSPCMML

Converts binary music sequence data from various Square SPC sequence formats into mfvitools MML format (i.e., into FF6 format). This tool does not prioritize wholly accurate representation; instead, its design is focused on convenience and utility. Program, volume, and octave commands are replaced with macros, allowing these to be tweaked globally. Features not supported by FF6 are either converted to a close equivalent or rendered as comments. Samples may optionally also be ripped.

Supports:
* Bahamut Lagoon (SUZUKI)
* Chrono Trigger (AKAO4)
* Final Fantasy IV (AKAO1)
* Final Fantasy V (AKAO3)
* Final Fantasy VI (AKAO4)
* Final Fantasy Mystic Quest (AKAO3)
* Front Mission (AKAO4)
* Front Mission: Gun Hazard (AKAO4)
* Live A Live (AKAO4)
* Romancing SaGa (AKAO2)
* Romancing SaGa 2 (AKAO4)
* Romancing SaGa 3 (AKAO4)
* Secret of Mana / Seiken Densetsu 2 (AKAO3)
* Trials of Mana / Seiken Densetsu 3 (SUZUKI)
* Super Mario RPG: Legend of the Seven Stars (SUZUKI)
* Treasure of the Rudras / Rudra no Hihou
* Bandai Satellaview games by Square (AKAO4):
  * Treasure Conflix
  * DynamiTracer
  * Radical Dreamers
  * Koi ha Balance

## BRR2SF2

Converts multiple BRR files into a SoundFont2 file for auditioning and testing. Designed to imitate some of BRR's quirks somewhat better than the raw waveform output other programs provide. Semi-accurately imitates SPC700 ADSR envelopes and allows for non-identical loop iterations as occur in some BRRs. All samples receive a vibrato delay of 1 quarter note at 120bpm. Minimum and maximum ranges are defined for each sample based on SPC and engine limits, so you can see which notes are playable and which are not.

Input format is the same as `insertmfvi` sample listfiles, with some additions (which `insertmfvi` will happily ignore): After the ADSR value, put another comma, and the subsequent text will be processed by `brr2sf2`. From here, any text in `{`braces`}` will be ignored; by convention, the size of the sample in blocks is placed in braces here first, though it has no effect on the resulting sf2 file. Any text in `[`brackets`]` will be stripped out and used as an inverse transpose value. In other words: if a sample with the given tuning sounds one octave higher than the actual note played, you may represent this in the listfile as `[+12]`. The sample in the resulting soundfont will then be transposed one octave *down*, so that the note you play now matches the note you hear. After all text in brackets and braces is trimmed out, the remaining text, if any (with leading and trailing whitespace removed), is used as the sample's display name.

On the command line, append `sort` if you want the soundfont to be sorted by size within each bank. Append `id` to add the hex ID of the instrument to its display name.

## SPC2BRRS

Extracts multiple BRR files from an arbitrary SPC file. Should work on more or less any game. Sets up an `insertmfvi` listfile for the samples, with accurate loop points, which can be fed immediately into `brr2sf2`. DOES NOT attempt to tune the samples or apply ADSR other than default; you may wish to tune manually by editing the listfile, re-running `brr2sf2`, and repeating until successful.

## SXC2MML (experimental folder)

Converts Neverland SFC/S2C format to mfvitools MML format. The conversion is rudimentary and not designed to directly create good-sounding or listenable output. The intended purpose is to use this output - both the MML file itself and a MIDI conversion of it via [vgmtrans](https://github.com/vgmtrans/vgmtrans) - as a reference for manually building a rendition of the song.

There may currently be some issues where notes retrigger where they should hold, or hold where they should retrigger.

Percussion isn't simulated (no samples are set), but seems to follow General MIDI key layout, so it should work once converted to MIDI.

## "How do I get these data files into my ROM?"

* INSERTMFVI should cover most use cases.
* The [Beyond Chaos EX](https://github.com/subtractionsoup/beyondchaos/releases) randomizer and its cosmetic-only little sister [nascentorder](https://github.com/emberling/nascentorder) use the mfvitools MML parser for their randomized music mode.
* [This tutorial](https://www.ff6hacking.com/forums/thread-2584.html) covers inserting data and inst files into FF6 with a hex editor.
* The archive for [this tutorial](https://www.ff6hacking.com/forums/thread-3922.html), on translating music from binary FF6 hacks to Beyond Chaos mfvitools format MML files, contains a small python script that automatically inserts songs into a ROM with a fixed location and ID. It's not configurable enough for serious hacking, but it's convenient for testing.

## contact info
* [FF6hacking Discord](https://discord.gg/FFAHavK)
* [Twitter](https://twitter.com/jen_imago)
