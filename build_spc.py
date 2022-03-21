import os
import sys

from mml2mfvi import byte_insert, int_insert

SPC_WORK_RAM_FILE = "experimental/spc_work_ram.bin"
SPC_AUX_RAM_FILE = "experimental/spc_aux_ram.bin"

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

def end_with_message(message, pause=True):
    print(message)
    if pause:
        print("Press enter to close.")
        input()
    exit()

def load_binary_file(fn, expected_size=0):
    try:
        with open(fn, "rb") as f:
            data = f.read()
    except OSError:
        end_with_message(f"Could not open {fn}, aborting")
    if len(data) < expected_size:
        end_with_message(f"File {fn} is invalid or corrupt -- expected ${expected_size:0X} bytes, found ${len(data):0X} bytes")
    return data
    
# AKAO's data transfer from ROM to SPC uses a 2-byte header to determine
# how much data to read given only an offset. This function simulates
# that process.

def load_data_from_rom(rom, offset, seq=False):
    length = int.from_bytes(rom[offset:offset+2], "little")
    data = rom[offset+2 : offset+2+length+(1 if seq else 0)]
    return data
    
def read_pointer(rom, offset, length=3):
    pointer = int.from_bytes(rom[offset:offset+length], "little")
    if pointer >= 0xC00000:
        pointer -= 0xC00000
    return pointer
    
def print_bytes(bin, group=2):
    s = ""
    count = 0
    for i in bin:
        #i = int.from_bytes(char, "little")
        s += f"{i:02X} "
        count += 1
        if count >= group:
            s += " "
            count = 0
    return s.strip()
    
def build_samples(rom, song_idx):
    
    static_brr_data = load_data_from_rom(rom, STATIC_BRR_OFFSET)
    static_brr_ptr = load_data_from_rom(rom, STATIC_PTR_OFFSET)
    static_brr_env = load_data_from_rom(rom, STATIC_ENV_OFFSET)
    static_brr_pitch = load_data_from_rom(rom, STATIC_PITCH_OFFSET)

    brr_pointer_offset = read_pointer(rom, POINTER_TO_BRR_POINTERS)
    brr_loop_offset = read_pointer(rom, POINTER_TO_BRR_LOOPS)
    brr_env_offset = read_pointer(rom, POINTER_TO_BRR_ENV)
    brr_pitch_offset = read_pointer(rom, POINTER_TO_BRR_PITCH)
    inst_table_offset = read_pointer(rom, POINTER_TO_INST_TABLE)
    
    print(f"BRR pointers at {brr_pointer_offset:06X}")
    print(f"loop, ADSR, tuning at {brr_loop_offset:06X}, {brr_env_offset:06X}, {brr_pitch_offset:06X}")
    
    free_brr_offset = 0x4800 + len(static_brr_data)
    
    all_brr_data = bytearray(static_brr_data)
    dyn_brr_ptr = bytearray(0x40)
    dyn_brr_env = bytearray(0x20)
    dyn_brr_pitch = bytearray(0x20)
    
    loc = song_idx * 0x20 + inst_table_offset
    inst_table = rom[loc:loc+0x20]
    print(f"instrument table at {inst_table_offset:06X} + {song_idx * 0x20:X} = {loc:06X}")
    for i in range(16):
        inst_id = int.from_bytes(inst_table[i*2:i*2+2], "little")
        
        if inst_id:
            print(f"Loading sample id {inst_id:02X}...")
            # Offset the sample index because there is no entry for zero
            inst_idx = inst_id - 1
            brr_loop = read_pointer(rom, brr_loop_offset + 2 * inst_idx, 2)
            dyn_brr_ptr = int_insert(dyn_brr_ptr, 4 * i, free_brr_offset, 2)
            dyn_brr_ptr = int_insert(dyn_brr_ptr, 4 * i + 2, free_brr_offset + brr_loop, 2)
            
            loc = brr_env_offset + 2 * inst_idx
            brr_env = rom[loc:loc+2]
            dyn_brr_env = byte_insert(dyn_brr_env, 2 * i, brr_env)
            
            loc = brr_pitch_offset + 2 * inst_idx
            brr_pitch = rom[loc:loc+2]
            dyn_brr_pitch = byte_insert(dyn_brr_pitch, 2 * i, brr_pitch)
            
            brr_pointer = read_pointer(rom, brr_pointer_offset + 3 * inst_idx)
            inst_brr_data = load_data_from_rom(rom, brr_pointer)
            all_brr_data += inst_brr_data
            free_brr_offset = 0x4800 + len(all_brr_data)
            print(f"    ROM location {brr_pointer:06X}, size {len(inst_brr_data)//9} blocks.")
        
    meta = bytearray(0x200)
    meta = byte_insert(meta, 0x000, static_brr_pitch)
    meta = byte_insert(meta, 0x040, dyn_brr_pitch)
    meta = byte_insert(meta, 0x080, static_brr_env)
    meta = byte_insert(meta, 0x0C0, dyn_brr_env)
    meta = byte_insert(meta, 0x100, static_brr_ptr)
    meta = byte_insert(meta, 0x180, dyn_brr_ptr)
    
    return meta, all_brr_data
    
def build_spc(rom, song_idx):
    
    # SPC format - 64KB memory + $100 bytes for DSP registers etc. at end
    spc = bytearray(0x10100)
    
    spc_work_ram = load_binary_file(SPC_WORK_RAM_FILE, expected_size = 0x300)
    spc_aux_ram = load_binary_file(SPC_AUX_RAM_FILE, expected_size = 0xB00)
    
    # $100 byte SPC header - keep separate for now
    header = spc_work_ram[:0x100]
    
    # $0000 to $0200 - SPC work RAM
    spc = byte_insert(spc, 0, spc_work_ram[0x100:0x300])
    
    # $0200 to $1A00 - SPC engine code
    spc = byte_insert(spc, 0x200, load_data_from_rom(rom, SPC_ENGINE_OFFSET))
    
    # $1A00 to $1C00 - patch metadata/pointer tables
    # $4800 up to $F600 - BRR sample data
    meta, samples = build_samples(rom, song_idx)
    spc = byte_insert(spc, 0x1A00, meta)
    spc = byte_insert(spc, 0x4800, samples)
    
    # $1C00 to $2C00 - sequence data
    # $2C00 to $4800 - SFX pointers and data (not implemented in this program)
    loc = read_pointer(rom, POINTER_TO_SEQ_POINTERS)
    loc += song_idx * 3
    loc = read_pointer(rom, loc)
    seq = load_data_from_rom(rom, loc, seq=True)
    print(f"Sequence {song_idx:X} at {loc:06X} -- {len(seq):0X} bytes")
    
    # Append "end track" to keep unused channels from going rogue
    seq += b"\xEB"
    spc = byte_insert(spc, 0x1C00, seq)
    
    # Set track read heads to start of tracks
    address_base = int.from_bytes(seq[0:2], "little")
    script_offset = 0x11C24 - address_base
    while script_offset >= 0x10000:
        script_offset -= 0x10000
    print(f"ROM address base for sequence: {address_base:04X} / Script offset: {script_offset:04X}")
    spc = int_insert(spc, 0, script_offset, 2)
    for i in range(8):
        loc = 4 + i * 2
        track_start = int.from_bytes(seq[loc:loc+2], "little")
        track_start -= address_base
        track_start += 0x1C24
        print(f"track {i} start: ${track_start:04X}")
        loc = 2 + i * 2
        spc = int_insert(spc, loc, track_start, 2)
    
    # $F600 to $FFFF - additional RAM used for track state
    # $10000 to end - DSP registers, etc.
    spc = byte_insert(spc, 0xF600, spc_aux_ram)
    
    return header + spc
    
if __name__ == "__main__":
    print("mfvitools Build SPC tool")
    print("Extracts a sequence from ROM into an SPC file")
    print()
    print("This is EXPERIMENTAL and may not work flawlessly!")
    print()
    
    syntax_error_message = (f"syntax: {sys.argv[0]} ROMFILE SONGID [OUTFILE]" + "\n"
                         + "Song ID should be in hex with no prefix, e.g. 4C")
    
    if len(sys.argv) < 3:
        end_with_message(syntax_error_message)
    
    try:
        id = int(sys.argv[2], 16)
    except ValueError:
        end_with_message(syntax_error_message)
        
    romfile = sys.argv[1]
    
    rom = load_binary_file(romfile, 0x300000)
    if len(rom) % 0x10000 == 0x200:
        rom = rom[0x200:]
        print("Loaded ROM with header.")
    elif len(rom) % 0x10000 == 0:
        print("Loaded ROM without header.")
    else:
        print("Loaded ROM, assuming no header.")
        
    spc = build_spc(rom, id)
    
    if len(sys.argv) >= 4:
        outfile = sys.argv[3]
    else:
        outfile = os.path.splitext(os.path.basename(romfile))[0] + f"-{id:02X}.spc"
        
    with open(outfile, "wb") as f:
        f.write(spc)
    end_with_message(f"wrote to {outfile}", pause=False)