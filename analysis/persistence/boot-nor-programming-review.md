# Boot 自有 NOR HAL 的恢复闭包

仅离线读取 `mi-panel-flash-16m-1.50.10-20261004.bin`；本复核没有硬件操作或设备写入。

2026-10-04 地址纠正：此前版本错误地把公开默认controller名字当作本镜像logical id0，标成40140000。实际BOOT table20003300/file5378和main table20003948/file155858的raw2words均为 {40148000,40140000}，HAL按table[id]索引，所以id0为40148000。根代理也捕获main live同序。旧标注不是已验证硬件证据；所有后续SPI寄存器访问必须先读并核对live SRAM指针表。

保留的 boot 在进入主固件之前复制 `file0x2220..0x5b58` 到 `SRAM0x200001a8..0x20003ae0`、清零 `0x20003ae0..0x20003c20` 并执行 NOR 初始化。其原生读取、写入、擦除、保护设置和缓存失效的正常调用链完全在这套 SRAM 中；栈保护常量 `0x20003a58` 也在该复制块内（镜像初值 `0xdeadbeef`），没有主固件的 Flash guard 依赖。

该结论有条件：使用 boot 自己已经初始化的代码与上下文；实际 active chip 必须与 85-65-18 配置一致；HAL wrapper 使用 suspend=0；IRQ 屏蔽、A7/其他总线主设备暂停、controller 空闲；异常 assert/stack-failure 仍会调用 boot Flash 日志/断言代码。尚未执行 cold boot 写入/恢复测试。

## 精确入口

地址列是物理 SRAM 指令地址。Thumb 指针为地址+1；也可使用 RAMX alias（物理地址减 `0x1fe00000` 后+1），前提是运行字节、上下文和 MPU/调试状态已经验证。

| 入口 | 地址 | ABI | 最大内部栈 |
| --- | --- | --- | --- |
| 原生 JEDEC | `0x20001cf8` | r0=id, r1=RAM output, r2=len；pre/9f(min3)/post | 64 B |
| pre | `0x200018a8` | r0=id | 48 B |
| 通用 read_reg | `0x20001900` | r0=id, r1=cmd, r2=RAM output, r3=len；需外部 pre/post | 48 B |
| post | `0x200018f8` | r0=id | 48 B |
| HAL write | `0x20001248` | r0=id, r1=address, r2=RAM source, r3=len；suspend=0 | 200 B |
| HAL erase | `0x20001104` | r0=id, r1=address, r2=len；suspend=0 | 232 B |
| HAL BP 设置 | `0x20000fe8` | r0=id, r1=BP；保存 IRQ、pre/type4/post | 200 B |
| cache invalidate | `0x20002fb4` | r0=0I/1D, r1=start, r2=len；32 B line | 8 B |
| get_size | `0x20000f20` | r0=id, r1=total*, r2=block*, r3=sector*, [sp]=page* | 32 B |

专用 low/high status 函数 `0x2000193c/0x20001c2c` 的 guard 也只读 SRAM；首次验证仍可统一使用通用 read_reg 发 05/35。原生 SPI 读取返回 0 只是驱动完成，不足以证明读值正确；ID、状态和 post 后 uncached 映射页必须与备份核对。

## Boot 上下文与软件恢复

可保存 boot 自有 live 区域 `0x200001a8..0x20003c20`，结束地址不含，共 14968 B（14648 B 初始化块+320 B BSS）。这与 main 的 SRAM 重叠；不能在运行主固件中覆盖它，再不经完整原内容/上下文恢复就继续主固件原 PC。

| 节点 | 用途 |
| --- | --- |
| `0x20003ae0` | id0 ctx，opened byte0，cached ID byte1..3；stride0x24 |
| `0x20003af8/0x20003afc` | total/page；实际预计16 MiB/256 B，需 boot live 确认 |
| `0x20003b7a` | active cfg index；预计0x0f，需 boot live 确认 |
| `0x200036d0` | table[15]；镜像为0x2000382c |
| `0x20003844` | cfg callback；镜像为RAMX Thumb0x002024f5 |
| `0x20003b74/76/78` | pre/标准/alternate read divider bytes |
| `0x20003b88` | mode bitmap，调用读取，不改此字 |
| `0x20003b80` | id0 saved bus-lock；只读 SPI 的唯一软件全局写入（另有out/stack） |
| `0x20003b5a` | id0 suspend state；入口必须0，正常无 suspend 写/擦结束也设置0 |
| `0x20003b28/30/38` | resume address/source/length；仅操作暂停返回1时写入 |
| `0x20003a58` | SRAM stack guard；保存当前 live 值 |
| `0x20003adc` | timer 标定值；保存当前 live 值，不能只按源镜像初值假定 |

只读 stub 结束后核对/恢复 saved-lock word、scratch RAM 和全部核心寄存器；正常 no-suspend 写/擦还核对 state0、pending 字段未变化。固定 cfg/table/code 不会被这些正常操作修改。实际 BP 位属于芯片状态，需单独恢复，而不是恢复 ctx 文件就算完成。

boot 启动设置 MSP=`0x200d5e00`、MSPLIM=`0x200d3e00`。专用 MSP 栈必须满足已启用的下限，或者明确保存、临时调整并恢复 MSPLIM/PSPLIM。不能仅改 MSP 到 `0x200cxxxx`。内部峰值232 B之外另有 caller/保存区，建议擦写 stub 至少512 B专用栈且8 B对齐。IRQ 屏蔽并不屏蔽 HardFault/NMI。

## Controller、保护与缓存

boot controller table 在 `0x20003300`，raw源字节证明id0硬件为 `0x40148000`、id1为 `0x40140000`。调用前检查 `+0x0c busy bit0=0` 与 `+0x34 lock bit0x100=0`，保存并核对 `+04/+14/+34/+3c`；post应恢复 divider 和稳定 read-mode/lock 配置。交易 command/address、长度字段可以变化。禁止批量读取 FIFO `+08/+10`，特别是 RX `+10` 读取会消耗数据。

保护支持 mask=`0x407c`，来源 cfg 字段，不是当前保护值。保存 `orig_bp=(SR1|(SR2<<8))&0x407c`；`0x20000fe8` 按 active callback type4 仅替换支持的 BP 位，使用 volatile WREN50 写 low01/high31。再次读取05/35确认BP与其他稳定状态（含QE）；底层 dispatcher 会忽略 callback 的细部结果，HAL返回0不能代替读回。不要固定恢复为7c。

Puya 擦写的400/450 us延时由 `0x20002d78` 读取计数器 `0x40003004`，频率 getter `0x20003008` 返回 `word[0x20003adc]>>2`。镜像初值24000000（getter6000000）不是 cold live测量：恢复时必须确认计数器在跑、标定和当前clock一致。WIP轮询没有有界软件超时。

HAL本身不会替调用者失效I/D cache。写入/恢复后先从 uncached `0x28000000+offset` 逐字读回，再对变化Flash范围失效I/D cache，才恢复从相关Flash的执行。当前main正常wrapper用 `0x2c000000+offset` 地址调用这两个cache IDs，可作为地址别名参考。boot直接函数仍位于同一SRAM块，控制节点是 `0x27ffc000/0x27ffa000`。长度>=0x4000会全cache失效，应考虑无关cached data的所有权，不能随意扩大到全缓存。

## 尚需现场验证

应使用确定性的 reset/调试停点，在保留boot已经打开NOR、且main还没覆盖SRAM的阶段（另代理已定位 `0x0c0104c6`）暂停。先抓 boot live上下文并执行原生9f/05/35，只读核对post后映射页，恢复原boot核心/调试状态，再确认原main正常启动。之后才有依据开展已核对扇区的最小program/读回/erase/完整restore测试。当前静态结论证明 boot 存在独立恢复驱动候选，没有把 warm main HAL 误作 cold恢复证据。

机器可读证据：`boot-nor-programming-review.json`（ABI、hash、所有非代码全局、恢复条件），`boot-nor-functions-disassembly.json`（逐入口指令/字面量），`boot-sram-call-closure-no-suspend.json`（完整CFG与栈上界）。
