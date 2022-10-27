## mfvitools mass extractor tool
## extract mml, samples, and SPC from multiple tracks all at once, with tags
## set up what to extract in a config file, then run mass_extract.py [CONFIGFILE]

import sys, os, configparser
from build_spc import build_spc, load_data_from_rom, read_pointer
from mfvi2mml import akao_to_mml, byte_insert

SPC_ENGINE_OFFSET = 0x5070E
STATIC_BRR_OFFSET = 0x51EC7
STATIC_PTR_OFFSET = 0x52016
STATIC_ENV_OFFSET = 0x52038
STATIC_PITCH_OFFSET = 0x5204A

POINTER_TO_BRR_POINTERS = 0x50222
POINTER_TO_BRR_LOOPS = 0x5041C
POINTER_TO_BRR_ENV = 0x504DE
POINTER_TO_BRR_PITCH = 0x5049C
POINTER_TO_INST_TABLE = 0x501E3
POINTER_TO_SEQ_POINTERS = 0x50539

def text_insert(data, position, text, length):
    new_data = bytearray(length)
    new_data = byte_insert(new_data, 0, bytes(text, "utf-8"), maxlength = length)
    return bytearray(byte_insert(data, position, new_data))
    
if __name__ == "__main__":
    print(f"mfvitools mass extractor tool")
    print(f"                    created by emberling")
    print()
    
    if len(sys.argv) >= 2:
        fn = sys.argv[1]
    else:
        print("HOW TO USE:")
        print("Make a config file to set up the files you want to extract.     ")
        print("Example txt file:                                               ")
        print("................................................................")
        print("[ff6.smc]                                                       ")
        print("01: prelude; The Prelude; Final Fantasy VI; Nobuo Uematsu; M.Akao")
        print("09: gau; Gau's Theme; Final Fantasy VI; Nobuo Uematsu; M.Akao   ")
        print("                                                                ")
        print("[rotds.smc]                                                     ")
        print("19: xb_gaur; Gaur Plains; Xenoblade; ACE+; Jackimus             ")
        print("1A: lal_boss; Megalomania; Live A Live; Yoko Shimomura; Gi Nattak")
        print("................................................................")
        print("Format is [id]: file; title; game; composer; arranger/converter ")
        print("You can process more than one game at the same time.            ")
        print("Files will include the ROM name, e.g. ff6_gau.mml, rotds_xb_gaur.mml")
        print("Rename your ROM as appropriate to keep filenames manageable.    ")
        print("                                                                ")
        print("You can also just enter a ROM directly instead of a config file ")
        print("to extract all music with no titles or metadata.                ")

        
        print("Enter config filename..")
        fn = input(" > ").replace('"','').strip()

    config = configparser.ConfigParser()
        
    # is this a rom or a config file?
    cfg_size = os.path.getsize(fn)
    if cfg_size >= 0x300000:
        try:
            with open(fn, 'rb') as f:
                rom = f.read()
        except IOError:
            print(f"ERROR: Couldn't load ROM file {fn}")
            os.exit()
        if len(rom) % 0x10000 == 0x200:
            rom = rom[0x200:]
        number_of_songs = rom[0x53C5E]
        
        virt_config = {fn: {f"{n:02X}": f"{n:02X}" for n in range(number_of_songs)}}
        config.read_dict(virt_config)
    else:
        config.read(fn)
    
    for romfile in config.sections():
        
        romid = os.path.basename(romfile).split('.')[0].strip().replace(' ', '_')
        
        try:
            with open(romfile, 'rb') as f:
                rom = f.read()
        except IOError:
            print(f"ERROR: Couldn't load ROM file {romfile}")
            continue
        if len(rom) % 0x10000 == 0x200:
            rom = rom[0x200:]
            print(f"Loaded {romfile} with header.")
        else:
            print(f"Loaded {romfile} without header.")
            
        for song_idx_string in config[romfile]:
            try:
                song_idx = int(song_idx_string.strip(), 16)
            except ValueError:
                print(f"ERROR: invalid index {song_idx_string}")
                continue
                
            spc = build_spc(rom, song_idx)
            
            ## Build MML
            brr_pointer_offset = read_pointer(rom, POINTER_TO_BRR_POINTERS)
            brr_loop_offset = read_pointer(rom, POINTER_TO_BRR_LOOPS)
            brr_env_offset = read_pointer(rom, POINTER_TO_BRR_ENV)
            brr_pitch_offset = read_pointer(rom, POINTER_TO_BRR_PITCH)
            inst_table_offset = read_pointer(rom, POINTER_TO_INST_TABLE)
            
            # Extract sequence from ROM and convert to MML
            loc = read_pointer(rom, POINTER_TO_SEQ_POINTERS)
            loc += song_idx * 3
            loc = read_pointer(rom, loc)
            seq = load_data_from_rom(rom, loc)
            try:
                mml = akao_to_mml(seq)
            except IndexError:
                print(f"Failed to convert sequence {romid}:{song_idx:02X} (sequence too short?)")
                continue
                
            # Extract samples from ROM
            #brr_loop, brr_env, brr_pitch, brr_ident = {}, {}, {}, {}
            sample_defs = []
            loc = song_idx * 0x20 + inst_table_offset
            inst_table = rom[loc:loc+0x20]
            for i in range(16):
                inst_id = int.from_bytes(inst_table[i*2:i*2+2], "little")
                if inst_id:
                    inst_idx = inst_id - 1
                    loc = brr_loop_offset + 2 * inst_idx
                    brr_loop = int.from_bytes(rom[loc:loc+2], "big")
                    
                    loc = brr_env_offset + 2 * inst_idx
                    brr_env = int.from_bytes(rom[loc:loc+2], "big")
                    
                    loc = brr_pitch_offset + 2 * inst_idx
                    brr_pitch = int.from_bytes(rom[loc:loc+2], "big")
                    
                    brr_pointer = read_pointer(rom, brr_pointer_offset + 3 * inst_idx)
                    brr_data = load_data_from_rom(rom, brr_pointer)
                    
                    brr_ident = f"{len(brr_data) // 9:04}_{sum(brr_data) % pow(16,6):06X}"
                    
                    os.makedirs(os.path.join("brr", romid), exist_ok = True)
                    bfn = f"brr/{romid}/{brr_ident}.brr"
                    try:
                        with open(bfn, "wb") as f:
                            f.write(brr_data)
                    except IOError:
                        print(f"ERROR: Couldn't write sample {romid}:{song_idx:02X}:{i + 0x20:02X} as {bfn}")
                        continue
                    
                    # Build definition
                    prg = i + 0x20
                    sample_defs.append(f"#BRR 0x{prg:02X} 0x{inst_id:02X}; {bfn}, {brr_loop:04X}, {brr_pitch:04X}, {brr_env:04X}")
                    
            out_mml = []
            
            ## Deal with metadata
            meta_cfg = config[romfile][song_idx_string].split(';')
            while len(meta_cfg) < 5:
                meta_cfg.append("")
            for i in range(len(meta_cfg)):
                meta_cfg[i] = meta_cfg[i].strip()
                
            songfn = romid + '_' + meta_cfg[0]
            
            if meta_cfg[1]:
                out_mml.append(f"#TITLE {meta_cfg[1]}")
                spc = text_insert(spc, 0x2E, meta_cfg[1], 0x20)
                spc[0x23] = 0x1A
            if meta_cfg[2]:
                out_mml.append(f"#ALBUM {meta_cfg[2]}")
                spc = text_insert(spc, 0x4E, meta_cfg[2], 0x20)
                spc[0x23] = 0x1A
            if meta_cfg[3]:
                out_mml.append(f"#COMPOSER {meta_cfg[3]}")
                spc = text_insert(spc, 0xB1, meta_cfg[3], 0x20)
                spc[0x23] = 0x1A
            if meta_cfg[4]:
                out_mml.append(f"#ARRANGED {meta_cfg[4]}")
                spc = text_insert(spc, 0x6E, meta_cfg[4], 0x10)
                spc[0x23] = 0x1A
            spc = byte_insert(spc, 0xAC, b"\x35\x30\x30\x30")
            
            ## MML surgery
            out_mml.append("")
            for line in sample_defs:
                out_mml.append(line)
            out_mml.append("")
            
            mml = [line for line in mml if not line.startswith("#WAVE")]
            out_mml = out_mml + mml
            out_mml = "\n".join(out_mml)
            
            ## file output
            
            this_fn = songfn + ".spc"
            try:
                with open(this_fn, "wb") as f:
                    f.write(spc)
            except IOError:
                print("ERROR: failed to write {this_fn}")
                
            this_fn = songfn + ".mml"
            try:
                with open(this_fn, "w") as f:
                    f.write(out_mml)
            except IOError:
                print("ERROR: failed to write {this_fn}")
                
            