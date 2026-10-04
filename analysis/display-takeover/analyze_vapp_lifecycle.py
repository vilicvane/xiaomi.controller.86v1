"""Offline bounded lifecycle audit of original vapp; never calls target code."""
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'analysis' / 'pinout'))
import analyze_a7_peripherals as a

def main():
    data = a.FILE.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    assert sha == '777de42c53a1c95495c55b3a9a0c27f907f68ab87a9512bee6b5f4356acb695b'
    word = lambda va: struct.unpack_from('<I', data, a.address_to_offset(va))[0]
    assert word(0x383a92e8) == 0x3846db18
    methods = struct.unpack_from('<7I', data, a.address_to_offset(0x3846db18))
    assert methods[2:6] == (0x381a5191, 0x381aa7d5, 0x381a93a1, 0x381a5035)
    assert word(0x381a8304) == 0x3846da58
    assert word(0x3846da58 + 0x10) == 0x381a89d9
    windows = [
        ('original_vapp_main_complete', 0x3818f9fc, 0x170),
        ('main_framework_event_stop_callback', 0x3818f8a0, 0x9e),
        ('main_signal2_callback', 0x3818f948, 0xac),
        ('framework_constructor', 0x383a9240, 0xa6),
        ('framework_run_select_mode', 0x381aa7d4, 0x1ba),
        ('framework_run_async_thread_and_render', 0x381aaa64, 0x170),
        ('framework_run_cleanup_and_return', 0x381aa9de, 0x80),
        ('framework_stop', 0x381a93a0, 0xe2),
        ('framework_destroy', 0x381a5034, 0x154),
        ('application_constructor', 0x381a810c, 0x70),
        ('application_stop_async_request', 0x381a89d8, 0x3a),
        ('runtime_uv_stop_registration', 0x3819c588, 0xde),
        ('runtime_uv_stop_callback', 0x3819bb9c, 0x2c),
        ('native_async_send', 0x3805a368, 0x8a),
        ('render_stop_fd_cleanup', 0x381aefb0, 0x9a),
        ('application_thread_entry', 0x381a9488, 0x160),
        ('pthread_create_implementation', 0x383acc04, 0x12e),
        ('framework_event_registration', 0x381af158, 0x60),
    ]
    report = {
        'scope': 'Offline saved exact 1.50.10 NOR only; no target actions or payload changes. APIs below are evidence, not instructions to call them from an arbitrary task.',
        'firmware_file': str(a.FILE.relative_to(ROOT)), 'firmware_sha256': sha,
        'original_command': 'vapp app/com.xiaomi.smartpanel &',
        'original_main_Thumb': '0x3818f9fd', 'original_main_code_range': '0x3818f9fc..0x3818fb66',
        'registry_patch': 'Current counter changes builtin vapp entry word at383edcc4 only; original vapp main body remains available.',
        'main_behavior': [
            'Stores argc/argv globals38502550/38502554, parses CLI through3819b3c0.',
            'Manages Framework object at global3850260c; allocates8B object and constructs through383a9240.',
            'Invokes object vtable+8 init with CLIParsedArgument, registers framework events3/4 callback3818f8a1 and native signal2 handler3818f949, then invokes vtable+0c run.',
            'After run returns, tests impl+144 continuation/exit byte. Can reenter run while continuing, otherwise destroy(vtable+14), destructor(vtable+4), clear global pointer, and return exit status.',
        ],
        'framework_vtable': {'VA': '0x3846db18', 'constructor_pointer_literal': '0x383a92e8',
                            'init_Thumb': hex(methods[2]), 'run_Thumb': hex(methods[3]),
                            'stop_Thumb': hex(methods[4]), 'destroy_Thumb': hex(methods[5])},
        'thread_ownership': {
            'default_async_mode': 'Constructor383a92c4 storeshalfword0101 at impl+0, so async flag impl+1 starts1. Inspected init381a5190..381a6220 contains no byte store to+1; caller can have other modes but default original path is async.',
            'vapp_task': 'Runs original main and GUI render loop; builds two UV async handles, __uiloop_stop381a9319 and __uiloop_event381aaf89. Render loop pointer is impl+4.',
            'child_application_thread': '381aab10 calls native pthread_create implementation383acc04 with pthread ID output activeApp+120, attr copy whose stack size is overwritten0x20000, and start381a9489. This child runs application/JS runtime event loop.',
            'synchronization': 'Parent waits on render semaphore impl+ec at381aab64; child posts it while starting at3819d6c2 in related FrameworkExt path. Actual observed default Framework child launch is381a9489. Full child-join/all auxiliary worker closure is not audited here.',
            'SIGSTOP_limit': 'Pausing only the command task does not establish that the application/JS thread, LVGL callbacks, libuv worker threads or shared panel services stop. No SIGSTOP technique is recommended.'},
        'cooperative_stop': {
            'method': 'Framework::stop Thumb381a93a1 takes r0=valid framework object; assumes active app exists and valid runtime context.',
            'actual_chain': '381a93a0 checks impl+fc activeApp. Async mode calls App vtable+10=381a89d9; synchronous mode first invokes render-stop381aefb0 and then App stop.',
            'app_stop': 'App381a89d8 obtains RuntimeContext from app+128, checks context+2e0, then sends async notification to context+2a4 via3805a368.',
            'runtime_stop_handle': 'initialize_runtime_uv_internal3819c588 initializes UV loop atcontext+18 and async handlecontext+2a4 with callback3819bb9d; callback setscontext+30 (UVloop stop flag) to1.',
            'screen_input_cleanup': 'render-stop381aefb0 closes async handles in global384fce20 and closes associated FD. Framework destroy381a5034 invokesgui_context_uninit381b7988 and frees callback/container resources.',
            'method_limit': 'This is destruction/recreation, not a proven pause/resume that preserves current page/JS heap. Sending stop successfully is not by itself proof that run returned, all workers joined, frame ownership released or input callbacks stopped.'},
        'event_vs_signal': 'Framework events3/4 are registered through381af158, a framework listener/container routine, not OSsignal registration. Main also separately installs signal2 throughsignal wrapper3823e350. No signal numbers for SIGSTOP/SIGCONT are assumed or tested.',
        'lifecycle_strings': ['Start App loop...', 'Stop App loop...', 'virtual void ferry::Framework::stop()',
                              'gui_context_uninit', 'gui_release_context_resource', 'hidePage', 'destroyPage', 'terminate'],
        'JS_lifecycle_limit': 'Embedded strings demonstrate JS page/application lifecycle facilities, but hidePage/onHide/terminate are not independently proven to suspend every native renderer/input/async worker. No direct stable pause/resume ABI was closed.',
        'switching_assessment': 'A switchable launcher is plausible because original body and coherent stop/destroy paths remain. The evidenced route is controlled stop followed by rebuilding the selected UI; seamless state-preserving toggling needs an explicit display/input owner broker or a separately proved lifecycle handshake.',
        'resources_for_parent_broker_review': ['Serialize framebuffer PAN submissions and wait for previous owner/vblank references before freeing canvas.',
                                               'Ensure touch goes to selected UI only; independent subscriber rings can deliver the same touch toboth applications.',
                                               'Keep panel_apps/brightness/idle/network services running; these are independent of vapp UI ownership.'],
        'not_performed': 'No pause, exit, restart, signal, function injection, hardware access or patch change.',
        'code_evidence': {name: a.disassemble(data, a.address_to_offset(va), size, 'Thumb')
                          for name, va, size in windows},
    }
    out = ROOT / 'analysis' / 'display-takeover' / 'vapp-lifecycle-switch-review-1.50.10.json'
    out.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'report': str(out.relative_to(ROOT)), 'sha256': hashlib.sha256(out.read_bytes()).hexdigest(),
                      'hardware_access': False, 'native_stop_path': True, 'verified_state_preserving_pause_resume': False}))

if __name__ == '__main__':
    main()
