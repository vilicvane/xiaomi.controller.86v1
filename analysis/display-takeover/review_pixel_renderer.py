"""Offline-only validation of the assembled scanout-strip renderer."""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'analysis/wifi/python-packages'))
import capstone

code = (HERE / 'pixel-renderer.bin').read_bytes()
base = 0x10100000  # Disassembly-only address; actual scratch is fresh runtime state.
cs = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)
insns = list(cs.disasm(code, base))
expected = ['dsb', 'isb', 'cbz', 'str', 'adds', 'subs', 'bne',
            'dsb', 'str', 'dsb', 'isb', 'bkpt', 'b']
assert len(code) == 36 and sum(i.size for i in insns) == len(code)
assert [i.mnemonic for i in insns] == expected
assert insns[2].op_str == 'r1, #0x10100012'
assert insns[3].op_str == 'r2, [r0]'
assert insns[6].op_str == '#0x1010000a'
assert insns[8].op_str == 'r3, [r4]'
assert insns[11].op_str == '#0x55'
assert insns[12].op_str == '#0x10100022'
original_rbar, temporary_rbar, rlar = 0x38000007, 0x38000001, 0x39efffe9
assert original_rbar ^ temporary_rbar == 6
pixel_count, byte_count = 320 * 32, 320 * 32 * 4
bounds = []
for start in (0x38515040, 0x385ab140):
    end = start + byte_count
    assert start % 4 == 0 and 0x38000000 <= start < end <= 0x39f00000
    bounds.append({'base': hex(start), 'end_exclusive': hex(end),
                   'last_word_store': hex(end - 4), 'bytes': byte_count})

report = {
  'task': 'Offline assembled MCU pixel renderer for a reversible actual scanout strip',
  'target_hardware_access': False,
  'firmware_context': '1.50.10; roots independently observed scanout pointers',
  'source': 'analysis/display-takeover/pixel-renderer.S',
  'binary': 'analysis/display-takeover/pixel-renderer.bin',
  'bytes': len(code), 'hex': code.hex(),
  'sha256': hashlib.sha256(code).hexdigest(),
  'assembler': 'LLVM MC thumbv8m.main-none-eabi; object has no relocations',
  'inputs': {'r0': 'fresh exact active NC scanout base',
             'r1': hex(pixel_count), 'r2': '0xffff00ff candidate opaque magenta',
             'r3': hex(original_rbar), 'r4': '0xe000ed9c (secure MPU RBAR)'},
  'offsets': {'fill': '0xa', 'restore_only': '0x12', 'bkpt_55': '0x20',
              'terminal_loop': '0x22'},
  'clobbers': ['r0', 'r1', 'APSR arithmetic flags', 'PC'],
  'preserved_by_program': ['r2', 'r3', 'r4', 'other general registers',
                           'SP', 'LR', 'no FPU state or stack access'],
  'disassembly': [{'offset': hex(i.address - base), 'size': i.size,
                    'instruction': i.mnemonic + ' ' + i.op_str} for i in insns],
  'loop_proof': 'For N>0, one 32-bit store per decrement; consecutive aligned '
                'addresses start+4*k for k=0..N-1. N=0 skips all pixel writes '
                'and still restores RBAR. Caller must constrain N and r0.',
  'strip': {'physical_width': 320, 'rows': 32, 'pixel_count': pixel_count,
            'word_bytes': 4, 'bytes': byte_count,
            'actual_scanout_buffer_size': '0x96000', 'bounds': bounds},
  'mpu': {'bank': 'secure current execution context; RNR must be 5',
          'rnr_address': '0xe000ed98', 'rbar_address': '0xe000ed9c',
          'rlar_address': '0xe000eda0', 'original_rbar': hex(original_rbar),
          'temporary_rbar': hex(temporary_rbar), 'changed_mask': '0x6',
          'unchanged_rlar': hex(rlar), 'base': '0x38000000',
          'limit_inclusive': '0x39efffff', 'attribute_index': 4,
          'enabled': True, 'execute_never': True, 'shareability': 0,
          'original_AP': '3: privileged and unprivileged read-only',
          'temporary_AP': '0: privileged read-write; unprivileged no access',
          'MAIR_semantics': 'Attribute index 4 is unchanged; MAIR value not inferred.',
          'entry': 'DSB; ISB before any pixel stores',
          'exit': 'DSB after pixels; STR original RBAR; DSB; ISB; BKPT #0x55'},
  'integration_requirements': [
      'Root alone handles fresh halt, original CPU context, MASKINTS, secure-bank '
      'selection, scratch ownership and backup, A7 pause, framebuffer backup.',
      'Preflight actual RNR/region5 RBAR/RLAR, privilege, scanout base and DMA '
      'producer state. Preserve RNR, change only region5 RBAR AP bits.',
      'Keep RNR=5 while executing. Program restores original RBAR on both '
      'normal and zero-count completion before the expected BKPT.',
      'Read back original MPU RBAR; restore saved RNR, scanout bytes, scratch '
      'and complete CPU state before normal continuation.',
      'A failed run before MPU restoration needs explicit restoration and '
      'CPU DSB/ISB; restore-only entry+0x12 does no framebuffer stores.',
      'A7 cached producer aliases can overwrite physical pixels on resume; '
      'producer halt and physical framebuffer restoration are independent.'
  ],
  'limits': ['Not a full framebuffer driver replacement or persistent firmware.',
             'No target execution performed by this artifact builder.',
             'RGB32 channel/alpha interpretation remains a display observation '
             'question; candidate magenta is invariant under R/B channel swap.',
             'Payload has no upper bound guard; root must pass exact approved inputs.'],
  'primary_sources': [
      {'path': 'analysis/display-takeover/reference/cmsis5-mpu_armv8.h',
       'url': 'https://github.com/ARM-software/CMSIS_5/blob/5.9.0/CMSIS/Core/Include/mpu_armv8.h',
       'lines': [80, 89, 93, 137, 138],
       'supports': 'RO/NP AP encoding, RBAR composition, DSB/ISB after MPU update'},
      {'path': 'analysis/display-takeover/reference/cmsis5-core_cm33.h',
       'url': 'https://github.com/ARM-software/CMSIS_5/blob/5.9.0/CMSIS/Core/Include/core_cm33.h',
       'lines': [1481, 1530, 1537, 1543, 1547],
       'supports': 'MPU register layout, AP/XN/SH/AttrIndx/enable bit positions'},
      {'path': 'analysis/pinout/reference/plat_addr_map_best2003.h',
       'lines': [199, 200],
       'supports': 'PSRAMUHS cached 0x3c000000 and NC 0x38000000 aliases'}
  ]
}
(HERE / 'pixel-renderer-review.json').write_text(
    json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
print(json.dumps({'bytes': len(code), 'bkpt_offset': '0x20',
                  'restore_only_offset': '0x12', 'strip_bytes': byte_count,
                  'report': str(HERE / 'pixel-renderer-review.json')}))
