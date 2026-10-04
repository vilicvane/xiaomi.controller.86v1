# 1.50.10 NOR 编程与回滚离线复核

本目录只读原始备份并生成证据；未访问 HID、未执行目标函数、未写设备 RAM 或 NOR。

输入：`backups/mi-panel-flash-16m-1.50.10-20261004.bin`，16 MiB，SHA-256 `777de42c53a1c95495c55b3a9a0c27f907f68ab87a9512bee6b5f4356acb695b`。精确地址来自该镜像的指令、启动复制表和常量；公开 SDK 只帮助命名与比对 ABI，不能替代当前二进制证据。

2026-10-04 地址纠正：此前版本错误地把公开默认controller名字当作本镜像logical id0，标成40140000。实际BOOT table20003300/file5378和main table20003948/file155858的raw2words均为 {40148000,40140000}，HAL按table[id]索引，所以id0为40148000。根代理也捕获main live同序。旧标注不是已验证硬件证据；所有后续SPI寄存器访问必须先读并核对live SRAM指针表。

## 已确认的硬件上下文

根代理提供的当前只读捕获 `backups/display-takeover/norflash-context.bin` 对应 `0x2000417c`，记录长 `0x24`：opened=1，缓存 JEDEC=85-65-18，total size=`0x01000000`，page size=`0x100`。驱动固定 sector=`0x1000`、block=`0x8000`。

根代理后续直接读取确认 active index byte `0x20004216=0x0f`，table slot `0x20003db8=0x20003f14`，cfg callback slot `0x20003f2c=0x00202901`。这与镜像中唯一 85-65-18 的 chip cfg（table index 15）一致。cfg BP 支持掩码是 `0x407c`；这不是当前实际保护状态。

85 是 Puya 的厂商 ID，但所查 P25Q128H/L 厂商资料均列 85-60-18，与实际 85-65-18 不同。因此不据这些资料判定具体型号、电压或最长擦写时间。

## 可复用入口与闭包

以下地址是偶数指令地址，Thumb 函数指针需加 1。A7 必须暂停、MCU 调用 stub 必须屏蔽 IRQ；SRAM 代码与相关上下文在调用前仍需与该镜像/捕获比对。

| 入口 | 地址 | ABI | 静态最大内部栈 |
| --- | --- | --- | --- |
| 原生 JEDEC | `0x20002084` | r0=id, r1=RAM output, r2=len；内部 pre/read 9f/post，读取 min(len,3) | 64 B |
| pre_operation | `0x20001c34` | r0=id | 48 B |
| 通用 read_reg | `0x20001c8c` | r0=id, r1=cmd, r2=RAM output, r3=len；必须在 pre/post 中使用 | 48 B |
| post_operation | `0x20001c84` | r0=id | 48 B |
| HAL write | `0x20001590` | r0=id, r1=address, r2=RAM source, r3=len；suspend=0 | 200 B |
| HAL erase | `0x2000144c` | r0=id, r1=address, r2=len；suspend=0 | 232 B |
| HAL set protection | `0x2000135c` | r0=id, r1=BP composite value | 200 B |

`sram-call-closure.json` 给出了逐指令 CFG、所有分支、调用点、局部栈用量、字面量目标及异常出口。最大栈不含 stub 自身、寄存器保存区、异常帧或 FPU 自动保存；它们是有条件的静态上界，不是运行期测量。

原生 JEDEC 正常闭包 23 个函数；它及通用 pre/read/post 没有 Flash 字面量或未解析间接分支。专用 `read_status_low=0x20001cc8` / `read_status_high=0x20001fb8` 含 Flash 栈保护引用，首次只读验证应使用通用 read_reg 分别发 05 和 35。

只有当前匹配的 callback 才能支持这份擦写闭包结论：间接 tail `0x200019ae` 与 BLX `0x200027b4` 被解析到 RAMX 指针 `0x00202901`（物理 SRAM 指令 `0x20002900`）。所有正常指令均在 SRAM；仍有 assert/stack failure veneers 通向 Flash，不能把异常路径视为独立可恢复的 RAM loader。

## 首次只读 SPI 验证

单个 SRAM stub 可以依次调用：

1. `native_get_id(0, out, 3)`；与缓存 85-65-18 比较。
2. `pre_operation(0)`。
3. `read_reg(0, 0x05, out+3, 1)`。
4. `read_reg(0, 0x35, out+4, 1)`。
5. `post_operation(0)`。
6. 保存返回值和完成标志，在 IRQ 仍屏蔽时 BKPT，交由宿主验证并恢复调用前状态。

这条链暂时改变 Flash controller 的命令、FIFO、read-bus lock、divider 和 continuous-read 配置；它只发 JEDEC、状态读取及 continuous-read 读命令，没有 WREN/status-write/program/erase 命令。函数返回 0 不是 SPI 总线正确的充分条件，必须看实际 ID、状态及恢复证据。等待 controller busy 的轮询没有软件超时；宿主仍需自己的超时/停止/恢复路径。

建议独立 scratch stack 至少 256 B 且 8 B 对齐，保存原 CONTROL/MSP/PSP/PRIMASK 与通用寄存器，不借用正在暂停的任务栈。64 B 是被调用函数最大值，不能作为整个 stub 的栈容量。

logical id0 controller 基址 `0x40148000`（先验证 live20003948 指针表）；正常 pre/post 只写软件 saved-bus-lock word `0x2000421c`，不改 chip index、mode `0x20004224` 或 divider bytes `0x20004210/12/14`。

| 节点 | 检查用途 |
| --- | --- |
| `0x4014800c` | 起始 busy bit0 必须为 0；只读 status |
| `0x40148034` | 起始 lock bit0x100 必须为 0；比较恢复后的稳定 lock/reset bits0x300 |
| `0x40148004` | read/command 配置；稳定 bits 应恢复，地址长度 bits12..24 可能被读命令归一化为 0 |
| `0x40148014` | divider 配置；尤其 bits16..23 应恢复 |
| `0x4014803c` | status flags，仅观察；不把动态状态要求逐字相等 |
| `0x2000421c` | 软件 saved lock，保存原值并在停止状态下检查恢复 |

不要把 controller 当普通 RAM 批量读：`+0x10` 是 RX FIFO，读取会取走数据；`+0x08` 是 TX FIFO。`+0x00` 是交易命令/地址，不要求原生读取之后与起始值一致，也不应直接回写旧命令来“恢复”。先确认正常 post 已完成，再恢复 CPU/IRQ/A7；无法完成 post 时需要单独的 controller 恢复程序，不能盲目清 lock 并继续从 Flash 执行。

## 擦写前必须处理的 Flash 依赖

三处 SRAM 字面量池都指向 cached Flash `0x2c7f8934` 的栈保护值：

| SRAM 池 | 使用者 |
| --- | --- |
| `0x20001cfc` | 低状态读取，所有 WIP 等待都会经过 |
| `0x20001fec` | 高状态读取 |
| `0x20002a60` | chip status callback：QE/BP 等 |

不能假定这些 Flash 读取会命中缓存。候选措施是：保存三个原池，另在独立 SRAM 保存当前 guard 值，再把三个池临时重定向到该 RAM 值；验证整个正常调用闭包和运行 SRAM 一致后才擦写；结束后恢复三个原池。独立且没有 Flash 依赖的 RAM loader 是另一条路线。这两条都尚未由本代理执行或证明冷启动恢复。

当前 HAL 不自带 RTOS mutex；memory-read bus lock 是 controller 锁，不会停止 A7、DMA 或其他总线主设备。外围 norflash_api 使用 PRIMASK 保存/恢复、保护范围选择、缓存失效，且其 A7 前后 callback 在当前镜像只是两个 `bx lr`，不能依靠它暂停 A7。注入时需要两核已停、controller 没有现存交易、HAL suspend state `0x200041f6=0`，并避免暂停在某个尚未结束的 NOR 操作中。

保护复原必须使用真实读出的 `orig_bp=(SR1|(SR2<<8))&0x407c`。type4 callback 读当前状态后仅替换支持的 BP 位，并使用 volatile WREN 50 写状态。返回值包装函数会忽略 callback 的细部错误，必须再读状态验证；不能用外围 API 的固定 `0x7c` 替代原保护设置，也不能把 config mask 当实际状态。QE 等其他状态位必须与基线相容。

HAL erase 会把地址向下、长度向上按 4 KiB 扩展；仅使用预先核对的对齐扇区和精确 `0x1000` 长度，避免意外扩区或 whole-chip erase 分支。HAL write 按 256 B 页拆分，输入源必须完全在 SRAM/安全的已驻留 RAM。写后先用 uncached `0x28000000+offset` 读回，再使 I/D cache 失效后恢复从相关 Flash 的读取/取指。外围 API 的失效 helper 仅对 cached `0x2c` 别名地址生效，使用其他地址不能假定它已经刷新缓存。

## 最小测试、入口 hook 与回滚边界

已离线保存主镜像入口扇区：`original-main-entry-sector-150000.bin`，4 KiB，源 offset `0x150000`；其 SHA-256 在 JSON 中。真正写之前仍需新读目标扇区并逐字节与备份核对。测试只有在扇区所有权/用途已明确后才能选点：可在原本 FF 的一个字节把 1 清成 0，读回，再擦除该 4 KiB 并完整恢复原扇区，最后再次逐字比较。单字节 program 的恢复也可能需要整个扇区 erase，所以没有“只影响一个字节”的回滚承诺。

主镜像 `0x150056` 的四字节 BL `86f06ff2` 调用 `0x0c5d6538`，时序在早期 SRAM/PSRAM 初始化之后、主入口之前，是入口 hook 候选。改这四字节仍通常要擦写整个 `0x150000` 扇区。它的 boot header、原指令和全扇区必须按备份完整保留；还需证明 boot/recovery 的完整性检查范围、hook 的原调用/返回语义、代码存放区域及 MCU/A7 上电时序。

`0x825000..0x8e0000` 在备份中全 FF，只证明内容空白，没有证明分区所有权、OTA 预留范围或校验覆盖，不能据此称“安全空闲扇区”。boot/recovery/A7/factory 不在本候选修改范围内。security 字段 0、build info 的 CRC32_OF_IMAGE=0 也不足以排除其他启动完整性检查。

现有 `0x2000xxxx` HAL 来自 main 启动复制/初始化；本次不停电时可复用不等于损坏 main 或断电之后仍可复用。主入口扇区擦写期间的断电会留下启动缺口。因此，持久化之前要么准备自带代码/上下文/controller 初始化的独立 RAM loader，要么在 boot/recovery 路径下验证可重新获取并调用备用 HAL 的原生 JEDEC、状态读取及 raw restore。仅保存 NOR 文件不足以证明冷启动可回滚。

## RAM 快照移植候选

`hal-transplant-manifest.json` 完整列出正常闭包中的非代码数据读取节点。限定所有 HAL wrapper 的 suspend=0 后，WIP wait 在 `0x20001d26` 直接回到忙状态轮询，NVIC 检查的 `0x20028d0c/20028d24` 不会执行。因此无需复制第二个大 SRAM 段。`sram-call-closure-no-suspend.json` 记录这个有证据的剪枝；含直接 cache-invalidate 的合并闭包共 1158 条指令，地址范围 `0x200006dc..0x20003440`。

未来 live 快照范围候选是 `0x200001a8..0x20004240`（结束地址不含，16536 B）：代码、字面量池、chip cfg 表全在 `0x200001a8..0x2000417c` 的初始化块内；BSS/context 数据直到 `0x2000423a`。特别要保存运行中的 `0x20004174` 定时器频率标定值；不能用 NOR 启动初值覆盖它或 HAL BSS。三处 guard 仍需另外重定向到独立 SRAM。

这个快照是移植候选，不是已证明的独立 loader。cold boot/recovery 必须仍能进入调试、初始化兼容的 SPI clock/controller；定时器 `0x40003004` 必须持续计数，频率与保存的标定值相符；当前 divider/mode 必须相容。原生 9f/05/35 成功以后，还应检查 post 后从 uncached NOR 映射读出的既有页与备份一致，才能验证 quad/XIP read-route。不同 boot/recovery PLL 状态下盲目覆盖 warm ctx 不成立。直接 cache-invalidate `0x20003348` 位于同一复制块，无 Flash 依赖、内部最大栈 8 B，控制节点为 `0x27ffc000`（I）/`0x27ffa000`（D）。

## 公开资料与适用限制

- [OpenHarmony BEST SDK，固定 commit](https://github.com/openharmony/device_soc_bestechnic/tree/17f61a22388e6f2fbd8fe855b0ccb298b9a3bd45)：BEST2003 地址别名、公开 HAL/NOR 头文件以及预编译 SDK archive；当前实机 HAL 的 ctx stride 与 return enum 与此版本有差异。
- [Puya P25Q128L 官方产品页](https://www.puyasemi.com/en/flash719/3156.html) 与 [P25Q128H 官方产品页](https://www.puyasemi.com/en/h_series653/3180.html)：用于核对厂商和 ID 表；不能据与实际 ID 不同的型号推出本机电压/时序。

精确入口、源码字节 hash、实际启动 RAM 复制段、guard 池及原入口扇区 hash 见 `nor-programming-review.json`；逐函数反汇编见 `identified-functions-disassembly.txt`；闭包与栈证据见 `sram-call-closure.json`。本报告所有实际地址均按 1.50.10 镜像重新验证，没有沿用 1.48.5 地址。
