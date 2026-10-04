# BOOT 独立的可逆 NOR padding 测试准备

本材料全部离线生成，没有设备执行、NOR 写入或自动执行脚本。实际运行前必须先通过真实 BOOT 只读 ID/05/35、控制器 post、核心/栈恢复，以及已证明的独立 reset/恢复路径；当前 JSON 的条件不能当成已完成的硬件证据。

唯一候选改动范围是现有 AP 分区内的 `0x825000..0x825fff` 扇区：实时重新读回并证明4096字节全FF后，在 `0x825100` 编程一页256字节 `NORTEST1`+248FF；主机从 uncached `0x28825000` 读取整4K，与预先生成的 `nor-test-sector-programmed-825000.bin` 精确比较。随后擦除恰好此4K，并再次逐字证明等于原始全FF。此测试不改 boot/recovery/A7/factory/main入口，也不安装持久化 hook。未来 OTA 可占用此 padding，测试标记应立即恢复。

`boot-nor-one-call.bin` 是168字节、无 relocation 的 position-independent SRAM caller。主机把它放到 `base=oldSP-1024`，I/O在base+128，payload256字节在base+256..base+512，结束oldSP-512；HAL栈最多232字节位于oldSP-232..oldSP。oldSP及limits不改变，且base必须不低于实际保存的MSPLIM。函数指针和r0..3由主机放到I/O前5个字；输出为原PRIMASK、已屏蔽PRIMASK、HAL返回、完成标志43414c4c。BKPT在exec_base+46，guards位于base+124/base+164。caller停下时PRIMASK仍为1，必须由主机完整恢复。

独立审查确认 write `00201249(0,28825100,base+100,100)`、erase `00201105(0,28825000,1000,0)`、setBP `00200fe9(0,BP,0,0)` 的ABI和强制suspend=0调用闭包；正常代码、literal和guard全部在BOOT的SRAM，callee保留r4/r5/r7，无FPU。参数断言或stack guard失败仍会走Flash错误路径，不能忽略它们的前置条件。

原BP必须从真实SR1/SR2计算：`(SR1 | SR2<<8)&0x407c`。原BP=0时省去全部保护状态写；否则先 setBP0、立即重新原生读取05/35，确认仅407c掩码清零且QE和其他稳定位保持原值，再program/整4K读回/erase/整4K恢复，然后恢复实际原BP并重复状态核对。HAL BP dispatcher忽略callback细部返回，返回0不足以代替状态读回。每个完成阶段都要求WIP/WEL=0；比较状态时仅忽略这两个动态位，不忽略QE或其他保护位。

`diagnostics/boot-nor-padding-stage-inputs.cfg` 只提供纯计算函数 `bnt_stage_inputs(stage,oldSP,originalBP)`、`bnt_verify_sector(phase,words1024)`、`bnt_verify_status(phase,originalSR1,originalSR2,currentSR1,currentSR2)`，不含任何设备I/O。stage只接受unprotect/program/erase_restore/reprotect/invalidate_i/invalidate_d，精确目标地址固定，不能指定任意callee/地址。主机执行器需在每次调用前保存完整1KiB scratch、所有整数/核心/调试状态、BOOT HAL全局及控制器状态；每个正常阶段后恢复调用者RAM/核心到原BOOT停点，继续保持halt，直到整笔交易验证与恢复结束。

恢复后可用 `00202fb5(0或1,2c825000,1000,0)` 分别失效I/D cache的128条32B line；闭包仅自身、栈8字节，所有出口明确返回0，但非法cacheID也返回0，因此不能省略精确参数校验。它不转换alias，应使用2c缓存地址；28用于uncached物理读回。长度1000低于4000的whole-cache分支阈值，不扩大失效范围。

任何reset/fault/security变化、guard不符、未到BKPT、HAL出错或无法确认控制器post结束都停止后续阶段并保持暂停，保存真实状态和既有备份，不自动resume，也不盲目用旧PC/RAM覆盖新状态。根代理只有在重新确认BOOT/controller有效后才可执行精确扇区与保护恢复。只验证此4K不意味着已证明其余16MiB都无变化；完整NOR差异审计由根代理按需要另行完成。

精确字段、hash和阶段流程见 `boot-nor-padding-test-plan.json`；代码/二进制仍未实机运行。
