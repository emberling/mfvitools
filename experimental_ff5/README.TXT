experimental MML interpreter for FF5 -- emberling

- This program will give you two files, a data (up to $1000 bytes, generally) and inst ($20 bytes).
- For basic testing, insert the inst at $43DAA. This will replace the program selections for song id 00 (Main Theme)
- Put the data.bin anywhere there's room, e.g. $200000. Then change a song data pointer to point to this location, e.g. changing $43B97 to 00 00 E0 will load the data at $200000 for id 00 (Main Theme)

I'll work on better documenting the MML format if there's interest; the core of it is based on the RS3ExTool format documented on ff6hacking.com wiki, but there are a lot of extra features

Beyond Chaos has a large repository of works in the FF6 version of this format:
https://github.com/emberling/beyondchaos/tree/master/custom/music
SPCs: https://www.dropbox.com/sh/jtjl6g75n8gwipo/AABiN0mZ0JNsK49XiduxqRzha?dl=0

You can also use mfvi2mml from the root of this repository to attempt to auto convert AKAO4 to MML, in order to extract music from FF6 hacks or (with some hex editing preparation - refer to vgmtrans source for bytecode differences) other AKAO4 games like chrono trigger, radical dreamers, rs2/3, live-a-live, front missions.

Here's the basics of getting these going in FF5:

- Obviously there are different samples available, so the sample table needs to be changed.
    VGMTrans' SF2 export is helpful for figuring out the existing sample table in an SPC.
    Samples available in unmodified FF5:
        id  block size  octave  instrument
        01  300         -       kick drum
        02  337         -       snare drum
        03  500         -       hard snare drum
        04  407         -       crash cymbal
        05  625         +1      tom
        06  125         -       closed hi-hat
        07  500         -       open hi-hat
        08  500         +2      timpani
        09  297         +1      glockenspiel
        0A  78          -       marimba
        0B  896         -       strings
        0C  394         +1      choir
        0D  97          +1      harp
        0E  215         -       trumpet
        0F  70          -       oboe
        10  165         +1      flute
        11  316         -       rock organ
        12  485         +1      like a cross between a honky-tonk and a music box?
        13  54          -       bagpipe drone
        14  158         -2?     bass guitar
        15  199         -2?     low piano
        16  332         +1      music box
        17  500                 shout
        18  923                 deep synth
        19  646                 pad chord A+maj7
        1A  316                 dist guitar power chord
        1B  460                 clavinet
        1C  629         -       horn
        1D  97                  mandolin
        1E  217                 steel drum
        1F  334                 conga
        20  243                 shaker
        21  281                 wood block
        22  412                 guiro
        23  325                 clap
        
The sample table is built using these directives:
->   #WAVE 0xXX 0xYY
    this loads sample id YY into program XX.
    AKAO uses programs 0x20 - 0x2F for dynamic samples; all others are either unused or set to fixed samples used by sound effects.
    Using all 16 slots seems to crash the game, however, and FF5 seems to have issues if there are gaps.
    There are also memory limits; I believe FF5 is a constant 3895 blocks for dynamic samples, though some AKAO games (chrono trigger, secret of mana) do have adjustable limits (this is a factor of echo delay length)

You may also see something like this:
->  #WAVE 0xXX ~0xYY~ /0xZZ/
This comes from a method of storing two variant arrangements in one file for different instrument sets. The easiest ways to deal with this are:
        - set both YY and ZZ to the desired instrument, or
        - use regex search and replace to eliminate everything between two / or two ~ in the entire file.
        
- FF5 uses 8-bit numbers for panning, while FF6 uses 7-bit. I've added a directive to scale all pan values in an MML:
-> #scale pan X

    So add -> #scale pan 2 <- to use an FF6 MML in FF5.
    
- FF5 and FF6 use different styles of setting echo settings. I've just rendered these as different commands.
    FF6: %vXX %b0,YY %f0,Z
    FF5: %vXX %zYY,Z
    XX - echo volume, YY - echo feedback, Z - echo FIR filter mode (0-3).
    values of Z other than 0 can be extremely glitchy, so stick with 0.
    
    Due to different global SPC volume settings between the games, the same echo settings on FF5 and FF6 won't sound the same - not currently sure of a conversion rate. Experiment or whatever.
    
- Tempo clocks aren't the same. FF6 is very close to real BPM, FF5 is a bit off. don't remember offhand in which direction. This can mostly be ignored for ok results

- There are a good handful of commands available in AKAO4 (FF6, etc) that are not in AKAO3 (FF5). Some just make things sound a little nicer, but others could screw up the whole track.

Mostly, the &xx command (set length of next note) is not present in FF5, has no equivalents, and is vital to track synchronization. Anything using this has to be rewritten.
Also, the jxx / jxx,yy command (jump on certain number of loop iterations) works differently in AKAO3. I've tried to compensate for this but I haven't really done any testing, and jxx,yy needs manual correction

Also not present are %l and %g (legato with and without slur). These won't break anything for missing them but some stuff will sound pretty odd. Legato with slur can be faked in FF5 using instant pitch bends (m0,xx) but at the cost of effort and a lot of data bytes.
    