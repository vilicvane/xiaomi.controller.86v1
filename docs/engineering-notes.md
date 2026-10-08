# 工程约束与稳定知识

整理日期：2026-10-08。适用设备：本机 `xiaomi.controller.86v1`，官方映像 **1.50.10**。
本页收敛跨实验仍有效的约束；当前版本、运行布局与证据见 [架构](architecture.md)。
旧逐轮记录原文保留在 [研究归档](research/engineering-log-through-image-drawer.md)。

## 固件及证据边界

- 函数地址、结构体 ABI、代码容器和冻结输入属于这台设备的精确映像。
  不把版本号相同当作字节相同，也不向未知或部分写入基线套用历史安装器。
- 将静态分析、实际 ARM 模型、写入器 mock、暖启动读回、用户观察和完整断电分别记录。
  一个层次通过不能替代另一个层次，旧版本结果不自动继承给新版本。
- 完整 NOR 备份不包含通过 MMC/RPMsgFS 提供的 `/data`。当前六页版将图片另存 MMC，
  旧五页及更早版本仍为 RAM-only；备份固件不表示已经备份图片或全部配置。
- a 版的自动返回设置单独保存在 `/data/86v1-return.0`、`.1`，不是原厂身份配置。
  NOR 安装/恢复不删除这些文件；224B context 新增 +212/+216/+220 三个计时字段，
  旧 212B context 解释只属于旧版本。a 实机保存的 5 秒设置在独立 AON GLOBAL 暖复位后
  由新 context 与 GET 重新读到；这不代替完整断电验收。
- 保留本地备份、原始 capture 和冻结输入；Git 只收第一方代码及明确审查的证据。

## 硬件、供电与调试

- 主芯片丝印 BES2600WM，代码和寄存器对应 BEST2003/BES2003 家族；应用和显示运行在
  Cortex-A7，另有 STAR-MC1 MCU 及其他服务核。
- 主板原供电连接点输入 3.3V 未启动，输入 5V 正常启动。这只确认主板供电入口，
  不表示芯片或调试引脚允许 5V。
- 成功路径为 nanoDAP **SWD**、通用 MEM-AP：GND、JTMS/SWDIO、JTCK/SWCLK。
  最初虽接过 JTDI/JTDO，项目没有建立已验证 JTAG 链。
- DPIDR=`0x1be12aeb`，AP0 IDR=`0x1aeb0015`，MCU CPUID=`0x630f1321`。
  `swd-memory.cfg` 使用 MEM-AP，避免未经审查的 CPU 自动探测和 Flash 驱动操作。
- 使用隔离于市电的低压供电进行裸板调试；已授权的完整断电包括断开 nanoDAP USB，
  避免调试器残余供电。当前维护阶段沿用用户跳过完整断电的决定，不重复要求或借用旧结果。
- [针脚映射](../analysis/pinout/panel-pinmap-1.50.10.json)区分 GPIO 功能候选、驱动家族名
  与实体连线；未确认的物理器件仍标为待验证。

## 显示及触摸 ABI

| 项目 | 本映像的已确认值 |
| --- | --- |
| 逻辑画面 | 480×320，RGB32 格式 13，stride 1920，单帧 614400B |
| framebuffer ioctl | GETVIDEO=`0x2801`，GETPLANE=`0x2802`，PAN=`0x2816` |
| vendor PAN 源指针 | plane **+24 字节**，不能用 `fbmem` 的 +0 代替 |
| 原界面持久 mmap | `0x50000000`，须在 live 对象和启动 guard 中核对 |
| `/dev/input0` 打开标志 | `0x41`：read-only 1 加 nonblocking `0x40` |
| raw touch 样本 | 32B；npoints u32@0，flags byte@9，x/y i16@10/12，timestamp u64@24 |
| raw touch flags | DOWN=1、MOVE=2、UP=4；实机证据为单点输入 |
| LVGL callback 坐标 | int32 @+0/+4，与 raw sample 的 i16 坐标布局不同 |
| LVGL state/continue | **+0x12/+0x13**（18/19 字节） |
| list node prev/next | **+0x80/+0x84** |

PAN 同步旋转到 staging 缓冲区，但双槽队列仍保留源 token；切换或释放画布前要确认
旧源不再被引用。提交成功不等于 LCD 已完成扫描，非原子 MEM-AP 样本也不是帧率测量。
最初改 LCDC 背景和 DSI 图案没有可见变化，真正像素源提交才成功。

原 UI 的 PAN 和 UPDATEAREA 都必须拦截，后者内部直接调用原 PAN。物理和虚拟输入继续
读取并排空，隐藏方得到 release 状态；阻断读取会留下旧事件。owner 交接由 GUI 线程
完成，不能从 watcher 线程追半初始化节点。订阅 mutex 不阻止发布；最终提交须锁两个
touch upper publisher，核对 ring、释放状态和帧队列。直接调用原 PAN，避免持 broker
锁后经 IOCTL 代理递归锁。

callback 安装由 GUI 所属 timer 执行并发布 drivers、四个 callback slot 和 ready。
旧图片实验版和 86V1 自定义固件的 bootstrap pthread 等待 ready 后成为常驻网络 worker；旧 drawer
bootstrap 安装后退出是历史版本行为。原 GUI timer 会重新注册自身，proxy 返回后仅
CAS 原 callback 到 proxy，并检查
closing/type/fbfd；不重新启动已关闭 timer。原 PAN 包含 SMP spin/WFE 和潜在调度，
不能承诺严格的固定毫秒上限。所有其他原 mmap 写者都已串行尚未证明，背景快照撕裂
仍属于观察边界。

## Flash 写入与失败处理

图片持久保存版另审查 NOR `0x932000` 页，只借用 `monkey` 单函数尾部
`0x38052000..0x38052bf0`（3056B），完整 stock 页 SHA 为
`6874cd0d613150d2c71c70bbf5513f83f72214304e2891f092d50e6e87d84c71`。
保留页头 4B、尾 1036B 和实际 payload 外字节，入口页 `+0xe6c` 从 `0x38051fd1`
改为禁用 stub `0x3804b109`，相邻 `0x38052bf0` helper 保留。
原启动脚本只有启用持久化 monkey 调试开关才运行此触摸压力诊断，本版放弃该诊断；
`mkgpt` 属于正常启动和恢复使用的 MMC 分区命令，已排除，不能借用。
六页始终整体核对，必须先由当前版本自身 restore 返回精确基线，再由新版本自身 install。
历史五页及更早 writer 不认识第六页，不得直接覆盖六页版。

图片记录只写 `/data/86v1-image.0` 和 `.1`，不写 NOR、原厂身份或 Wi-Fi 文件。
启动读取与保存由单一网络 worker 串行执行，16B store 状态属于 worker 栈，broker 仍为 224B。
实际成功解码或保存确认的槽被保护；上传同步、关闭及完整字节读回后才更新 state/pending。
坏新图回退旧图后也不能覆盖已知有效旧槽。非 202 可能已保存，不能自动重试。
小于四字节的文件无法确认项目归属，返回 409 并保留；双槽不证明真实 FAT/MMC 任意掉电安全。
细节见 [图片持久保存](persistent-images.md)。

本地原厂 NOR 备份为 16 MiB，SHA-256：
`777de42c53a1c95495c55b3a9a0c27f907f68ab87a9512bee6b5f4356acb695b`。
自定义固件的四页及旧图片实验版的三页边界见 [架构](architecture.md)，精确回退见
[开发流程](development.md)。新增网络页 `0x92d000` 经过独立 ownership 审查，运行段限定
`0x3804d000..0x3804dff0`；页头 4B、尾 12B 和 payload 外原字节保留。它位于被禁用的
单个 `uorb_unit_test` 命令内部，不是从全 FF 模式推断出来的空闲区。

PNG/JPEG 后继版本另审查 NOR 页 `0x927000` 中的
`0x38047098..0x38047dac`（3348B），借用 `filldisk/fillcpu/fillmem` 诊断组。
完整 stock 页 SHA 为 `21c40d397e6ec14f61011544f736962470f623c91ba3bbf7a6d89d120ba23c02`；
保留页头 156B、页尾 592B 和实际 payload 外的字节，禁用入口页 `+0xd68/+0xd7c/+0xca0`
三个 builtin。相邻 `0x38047dac` helper 仍有其他调用者，不能覆盖。新五页安装必须从
精确旧图片实验三页加两个 stock 依赖页开始，先恢复当前 release，不能叠加。

原厂 PNG/JPEG 逐行解码使用每请求私有状态，只写备用 RGB565 槽，完整收尾后才交给 GUI。
JPEG 初始化使用本映像固定的 LTO 内部片段，而非公共导出 API；其私有 frame、返回地址、
回调和 native setjmp ABI 都要绑定精确字节。不得调用共享 FILE/GUI wrapper 或重新初始化
原界面图像/字库 cache。网络 worker 使用已审查的 16KiB pthread 栈属性。

实际 ARM 模型加载 stock 后，只覆盖 ELF 的 allocated PROGBITS sections，不能平铺
PT_LOAD 中的零填空隙。堆与栈的模型数字属于观察，不保证设备上所有调用路径的上界。

- **logical NOR controller 0 为 `0x40148000`**，访问前核对本映像 live pointer table。
  不访问未使用的 `0x40140000`，它曾造成调试总线锁死并需要完全断电。
- 硬件操作串行，只有一个负责人持有 OpenOCD/native call；离线分析可并行。
- 擦除粒度 4KiB，必须保留并核对页面中全部其余字节，不能只验证代码修改范围。
- 写入借助不可变 BOOT 的新鲜 MCU 停点，A7/WF/BT 保持复位，采用已审查的 SRAM 调用
  闭包。不能在从 NOR 执行的活动上下文中随意擦写代码。
- BOOT 的 SP805 看门狗约 4 秒；按已审核流程停止并核对 CTRL=0。延长 shell 等待时间
  不能解决硬件看门狗。
- 仅借用当前 SP 下方 1KiB SRAM，保存并闭合 core/SRAM/BSS 状态，不修改 SP/limit。
  原始 NOR SR1=`0x7c`、SR2=`0x02`；恢复 BP、QE 与稳定状态位并核对 WIP/WEL。
- 不回放 FIFO、旧 command/address 或不确定调用后的锁、计数器、CPU 上下文。
  超时、fault、reset、posted transport 失败后保留停止状态和证据，不盲目重试、resume
  或 reset；部分写入需另行监督恢复，不能绕过未知基线检查。
- 仅当整次 `app_complete=1` **且** `safe_to_resume=1` 才允许最终 GLOBAL。
  中间一次安全返回不等于整个安装完成。
- 四页维护版安装固定为 net→aux→code→entry，恢复固定为 entry→code→aux→net。
  各中间阶段 A7/WF/BT 保持复位；四页、保护状态和 native context 都闭合后才运行。
  维护版先完整恢复旧图片实验版三页加原厂网络页，才允许进入旧三页回退链。
- GLOBAL 后特定 IDR 暂时不可读，仅允许全新的只读连接重试；不重放 writer 或 native call。
- 历史写入/恢复是在健康 MAIN 状态实测；d 的四页 restore 在 d→g 升级中通过，
  g 自身 restore 在 g→a 迁移中通过，a 四页安装与暖读回已通过；a 自身 restore 随后在
  五页图片版迁移中通过，记录在新版本结果，原 a 结果保持当时字节。
  没有故意破坏 MAIN 后验证冷恢复。
  不宣称已具备任意故障状态的救砖能力。
- OpenOCD `-l` 路径用正斜杠避免 Tcl 转义；日志分类应精确锚定顶层状态字段，不能把
  `pre_global_debug_cleanup_error 0` 当作失败后重复写设备。
- 私有 OpenOCD 包须包含 exe、DLL 和精确 CMSIS-DAP 接口配置。`-s diagnostics` 所用
  `diagnostics/interface/cmsis-dap.cfg` 必须与冻结的 vendor 副本完全相同。离线 mock
  禁止 adapter/init，不能据 mock 通过承诺实际连接依赖完整。
- a 的 Windows/Jim 长路径会使完整 mock 失败。完整材料逐项核对后使用短根目录
  `C:\p86-idle-a`，93/93 mock 通过；冻结 executor/验证器必须相邻且保持原字节。
  这不是不确定 native 调用后自动更换路径重试的许可。

## 空白 Flash 及字库

[精确映像容量统计](../analysis/flash-capacity-summary-1.50.10.json)显示：16MiB 中非 FF
约 13.29MiB（83.06%），659 个完整空白 4KiB 页约 2.574MiB。这是字节模式统计，
不是声明可用的空间；OTA、身份或其他保留范围可能全 FF。

主要连续空白为 AP `0x825000..0x8e0000`（748KiB）和 A7 `0xe5d000..0xfe0000`
（1548KiB）。A7 启动只复制 `0x8e0004..0xdd3fe4` 的 `0x4f3fe0` 字节到 RAM，
末端 `0x384f3fe0`，BSS 从 `0x384f4000` 开始；直接在空白尾部放函数不会自动加载。
现有几 KiB 限制来自受控函数容器，不能据此说整颗 Flash 已满，也不能盲目扩大复制
长度跨越 BSS/堆。新代码/资源空间须一起确认 OTA、装载、重定位、缓存和恢复边界。

读取/执行 NOR 不修改阵列，绘图状态在 RAM；但未穷尽证明原系统所有路径都不写 NOR。
BOOT 改保护状态寄存器与修改固件/数据阵列不是同一操作。

原应用静态使用 MMC 上 `/font/MiSansW_Regular.ttf`，它不在 NOR 备份中。字体文件可读性、
字形 ABI 与 canvas 适配未实机验证；FreeType/LVGL 的 currentglyph/cache 与原 GUI 共享，
禁止重新初始化或销毁全局缓存。当前上传图片已光栅化，地址使用私有小数字字形。
