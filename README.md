# mfvitools
some things i wrote to make ff6 music importing/editing easier  
* [windows binaries](https://github.com/emberling/mfvitools/releases)

Currently these are focused on manipulating song data through the MML (Music Macro Language) text format. Legacy hex based tools are provided in a subfolder, but these have little to no utility anymore.

## MFVI2MML

Converts binary FF6 format music sequence data into mfvitools MML format. The sequence will be represented as accurately as possible -- every byte translated into its equivalent. This MML format is designed to represent any valid FF6 sequence without loss, except for some extreme edge cases involving pointers that point to the middle of a command. If you have a _data.bin and _inst.bin file, it will import from both.

## MML2MFVI

Converts mfvitools MML format into binary FF6 format. Outputs a data file with 38-byte header (ready to insert into ROM) and a 32-byte inst file.

Format is based on rs3extool MML but extended and altered. Documentation [on github wiki](https://github.com/emberling/mfvitools/wiki/).

## SQSPCMML

Converts binary music sequence data from various Square SPC sequence formats into mfvitools MML format (i.e., into FF6 format). This tool does not prioritize wholly accurate representation; instead, its design is focused on convenience and utility. Program, volume, and octave commands are replaced with macros, allowing these to be tweaked globally. Features not supported by FF6 are either converted to a close equivalent or rendered as comments.

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
* Treasure of the Rudras / Rudra no Hihou (KAWAKAMI)
* Bandai Satellaview games by Square (AKAO4):
  * Treasure Conflix
  * DynamiTracer
  * Radical Dreamers
  * Koi ha Balance

## "How do I get these data files into my ROM?"

* The [Beyond Chaos EX](https://github.com/subtractionsoup/beyondchaos/releases) randomizer and its cosmetic-only little sister [nascentorder](https://github.com/emberling/nascentorder) use the mfvitools MML parser for their randomized music mode.
* [This tutorial](https://www.ff6hacking.com/forums/thread-2584.html) covers inserting data and inst files into FF6 with a hex editor.
* The archive for [this tutorial](https://www.ff6hacking.com/forums/thread-3922.html), on translating music from binary FF6 hacks to Beyond Chaos mfvitools format MML files, contains a small python script that automatically inserts songs into a ROM with a fixed location and ID. It's not configurable enough for serious hacking, but it's convenient for testing.
