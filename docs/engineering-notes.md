# 工程经验与检查点

记录日期：2026-10-04。适用设备：小米智能家庭面板 `xiaomi.controller.86v1`。
除明确标注的历史配网诊断外，地址和接口均对应本机官方固件 **1.50.10**。
之后的设备状态以新实验记录为准，不把这份检查点当作实时检测结果。

## 已验证的进展

| 项目 | 结果与范围 |
| --- | --- |
| 调试接口 | nanoDAP 通过 SWD、通用 MEM-AP 读取内存；不是已验证的 JTAG 链 |
| 原固件配网恢复 | 1.48.5 的身份缓存异常经限定 RAM 验证后恢复；完全断电后原身份、云连接及控制正常 |
| 官方升级 | 用户已完成升级到 1.50.10，并保存该版本 16 MiB NOR 备份 |
| 显示与触摸 | 设备端 A7 程序直接使用 `/dev/fb0` 和 `/dev/input0`；点击加一，长按/拖动只计一次 |
| 持久化 | 粉色旧计数器与当前 broker 均完成完全断电自动启动、触摸正常 |
| 白色文字 | 旧966B版通过暖启动与颜色核对；当前2652B broker已通过完整断电启动 |
| 回退 | 安装白色版之前，两个扇区成功恢复成精确原值并读回验证 |
| 原界面热切换 | 第三键三击不重启切换，用户反复往返及冷启动后米家控制均正常 |

旧966字节白色counter的独立全断电观察仍未补做；当前broker的冷启动结果单独记录。
旧结果见 `native-counter-hardware-result.json`，新结果见 `native-ui-broker-hardware-result.json`。

## 硬件与供电

- 板上主芯片丝印为 BES2600WM，代码与寄存器对应 BEST2003/BES2003 家族；
  A7 负责应用和显示，另有 STAR-MC1 MCU 及其他服务核。
- 用户给主板原电源连接点输入 3.3 V 时没有启动；输入 5 V 后正常启动。
  **这不表示芯片或调试引脚允许 5 V**：主板电源输入和调试逻辑电压要分开判断。
- 当前实测能用的调试连接是 GND、JTMS/SWDIO、JTCK/SWCLK；JTDI/JTDO
  是最初接线的一部分，但本项目实际成功的协议为 SWD。
- DPIDR 为 `0x1be12aeb`，AP0 IDR 为 `0x1aeb0015`，MCU CPUID 为 `0x630f1321`。
  `swd-memory.cfg` 使用通用 MEM-AP，避免未审核的 CPU 自动探测或 Flash 驱动动作。
- 使用外部低压供电进行调试；完整断电时必须同时拔掉 nanoDAP USB，避免残余供电。
  读到引脚电压不能代替电源轨识别，也不要靠裸露市电供电来猜测引脚。
- 针脚表见 `analysis/pinout/panel-pinmap-1.50.10.json`。GPIO 功能候选、触摸驱动
  家族名和物理器件型号不是同一层证据；未确认的实体连线仍标为待验证。

## 配网故障的教训

1. Wi-Fi 认证、关联和获取 IP 已完成，故障实际发生在后续 OTS/TLS/米家云登录。
   日志里的其他 SSID 可能只是扫描记录，不能据此认定有错误 Wi-Fi 配置残留。
2. 1.48.5 的 `device.info` 创建失败路径没有继续读取出厂身份，却返回成功；RAM
   缓存保留编译预置值，初始化标志为 0。文件打开失败的底层原因尚未确定。
3. 当时只修改 DID 和 key 两个 32 字节 RAM 缓冲区，并在每轮前保存、写后读回。
   这不是清空 Flash；RAM 修改在重启后可能丢失，也可能与其他身份缓存暂时不一致。
4. 配网成功后，原固件自行加载真实出厂身份；没有进一步 RAM 修改的完全断电
   验证确认在线和控制正常。BLE 身份不一致造成首次授权失败仍只是未证实的假设。
5. 16 MiB NOR 备份不包含通过音频侧 MMC/RPMsgFS 提供的可写 `/data`。
   不能把“备份了 Flash”当成已经备份所有配置，更不要为清 Wi-Fi 擦除整个 NOR。

历史原始记录见 `analysis/recovery-summary.md`，其中旧状态以本检查点补充更新。

## 设备端显示与触摸 ABI

- 原生计数程序是正常的 NuttX A7 任务，沿用原任务 128 KiB 栈。原 OS 调度、
  vblank、板级驱动和 MCU 服务继续工作；替换的是 UI 启动入口，不是整个系统。
- 屏幕逻辑尺寸 **480×320**，RGB32 格式 13，stride 1920，单帧 614400 字节。
  驱动进行旋转处理，逻辑尺寸不要与实际竖屏方向混淆。
- framebuffer ioctl：GETVIDEO `0x2801`，GETPLANE `0x2802`，PAN `0x2816`。
  这里的 vendor PAN 源指针位于 plane **+24 字节**，不是 `fbmem` 的 +0 字段。
- 最初直接改 LCDC 背景或 DSI 测试图案没有可见变化；经真正像素源提交的测试
  成功。不能把一个寄存器写入成功当作完整的显示接管证据。
- PAN 同步旋转到 staging 缓冲区，但全局双槽队列仍保留源指针 token。
  切换或释放画布之前必须确认旧源已不再被使用，不能只关闭文件就立刻 free。
- `/dev/input0` 以 `0x41` 打开：read-only 1 加 nonblocking `0x40`。
  `GETFILE` 后的 `file_read` 是已验证接口，勿误用未确认的文件描述符 read ABI。
- 单次触摸样本 32 字节：npoints u32@0、flags byte@9、x/y i16@10/12、timestamp
  u64@24；DOWN=1、MOVE=2、UP=4。现有设备证据为单点输入。
- 计数通过 released→pressed 状态转换；每 20 ms 轮询，长按和拖动不重复计数。
  切换后要丢弃跨界面的未释放按压，避免同一根手指触发新界面。
- 白色文字和固定深灰背景没有呼吸动画。用户观察到的短暂呼吸效果来源仍未确定。
  系统 `panel_apps` 继续控制背光和息屏；原固件设置仍可能影响原生 UI。

## 持久化范围与恢复闭包

基线 NOR：`backups/mi-panel-flash-16m-1.50.10-20261004.bin`，16 MiB。
SHA-256：`777de42c53a1c95495c55b3a9a0c27f907f68ab87a9512bee6b5f4356acb695b`。

| 对象 | 位置 |
| --- | --- |
| 原生代码扇区 | NOR `0x92b000`，4096 字节 |
| 入口表扇区 | NOR `0xccd000`，4096 字节 |
| 程序起始文件偏移 | `0x92b2f8`，当前程序 966 字节 |
| 程序运行地址 | `0x3804b2f4`，Thumb 入口 `0x3804b2f5` |
| 原 vapp 入口表项 | 文件 `0xccdcc8`，运行地址 `0x383edcc4` |
| 原入口值 | `0x3818f9fd` |

借用的 `faclvgl_main` 函数容器共 1416 字节，因此该工厂 demo 同时被替换。
原 vapp 主体及应用包仍保留；镜像复制长度、初始化数据和 BSS 边界未改变。
擦除以 4 KiB 为单位，整个扇区其余字节必须保留，不只验证修改的 970 字节。

- 安装先完整写入并验证代码扇区，再改入口表；回退先恢复入口表，再恢复代码。
  公共回退只接受精确已知的原始/补丁扇区，拒绝未知的半写入状态。
- 原始链接曾因 8 字节对齐偏移 4 字节。现用 4 字节 Thumb B.W 包装固定地址，
  并核对 ELF 段、加载地址、入口及 raw BIN 一致，错误已在写设备前发现。
- 原程序可在初始化失败且尚未第一次 PAN 提交时作为 fallback；这不是已经证明
  原界面与计数器能随意反复进入的热切换机制。
- 恢复借助不可变 BOOT 的新鲜 MCU 停点，A7/WF/BT 保持复位，使用完整审核的
  BOOT SRAM 调用闭包。不要在正在从 NOR 执行的上下文里随意擦写代码。
  此路线及擦写回退是在健康 MAIN 状态下实测的；没有故意损坏 MAIN 后验证冷恢复，
  因此不能宣称已经获得任意故障状态的救砖能力。
- **logical SPI0 实际地址是 `0x40148000`**；先读取本固件 live table 核实。
  `0x40140000` 是另一控制器，之前访问它造成调试总线锁死，必须完全断电恢复。
- BOOT 的 SP805 看门狗约 4 秒，调用前先按已审核流程停止并核对 CTRL=0。
  延长 shell 等待时间不能解决正在运行的硬件看门狗。
- 仅借用当前 SP 下方 1 KiB SRAM，保存恢复代码、输出及全部 core/SRAM/BSS 状态，
  不修改 SP/limit。明确区分正常返回、错误比较与无法确认闭合的 fault/reset/timeout。
- 原始 NOR SR1=`0x7c`、SR2=`0x02`；恢复 BP、QE 及全部稳定状态位，核对 WIP/WEL。
  不回放 FIFO、历史 command/address 或不确定调用后的旧锁/计数器/CPU 状态。
- 外层仅当 **app_complete=1 且 safe_to_resume=1** 时才允许最终 GLOBAL。
  中间一次安全返回不等于整个刷写成功。
- 超时、fault、reset 或 posted transport 失败后，不自动推进、重试或恢复旧上下文。
  部分入口表恢复是独立监督下的固定原表流程，不能绕过未知基线检查。
- GLOBAL 后调试口可能短暂无法读取 IDR。当前 wrapper 只对这一特定错误重试全新
  **只读**进程；从不重放安装、native call 或 reset。
- 结果分类曾误把 `pre_global_debug_cleanup_error 0` 当作顶层失败；修正为行首
  精确匹配后，用新只读验证确认成功，没有重复刷写。
- OpenOCD `-l` 路径使用正斜杠，避免 Tcl 对 Windows 反斜杠的转义。

## 不重启切换：设备端 broker

第三物理键通过用户三次按下/释放采样确认为 P3_1，bit25、低电平按下；当前
没有米家动作绑定。GPIO watcher 不过滤原 MCU key 服务通知，因此后续绑定动作
需要单独做路由过滤。三击窗口以原固件的 monotonic clock 计算，不能把“每次
sleep20ms”当作真实经过时间；调度延迟可能使长按被误判为短按。

新原型只进入原 vapp 一次，保留其 GUI/render 和 App/JS 线程，切换显示/触摸
owner。避免原 Framework 退出后 signal2 handler 悬挂和重复初始化问题。原界面
照常在后台绘图，但自定义模式阻止 PAN 与 UPDATEAREA 两条提交路径。
UPDATEAREA 内部直接调用原 PAN，所以仅替换 PAN 的 vtable slot 不完整。

两原 GUI 输入均照常读取并排空，替换输出 state 为 release，而不阻断读取。
mode 交接在 GUI 定时器回调内执行：释放两 GUI 输入和自有输入、排空旧显示帧，
锁两 touch upper 的 publisher mutex 后核对三条 ring，再提交新源并改 owner。
subscriber mutex 不锁 publisher；只看原始 pressed=0 也不能证明 ring 没有隐藏
期间的 DOWN/UP。不要从 watcher 线程追半初始化或已经释放的 GUI 节点。

原界面的板级 mmap 为50000000，在 live 对象及新程序启动 guard 中核对。返回
原界面用 zero-plane PAN 重提交该持久缓冲，不保存临时绘图 source。不释放仍在
队列/回调中的画布；直接调用原 PAN 避免持 broker 锁又 IOCTL 进入代理导致递归锁。
原 PAN 含 SMP spin/WFE 和可能调度，不能保证固定毫秒的严格执行上界。

具体易错 ABI：LVGL data 的 state/continue 是 **+0x12/+0x13（18/19字节）**；
list 数据节点大小0x80，prev +0x80，next **+0x84**。初次仅按head非NULL读取会
撞到 allocator先发布、后初始化的窗口；现由 GUI 线程内安装并持 broker mutex
发布 drivers/四个回调slot/ready。原 GUI 定时器会重新注册自身，proxy返回后仅
CAS原callback到proxy，并检查closing/type/fbfd，不重启已关闭的timer。

2652字节的新程序借用ntpcstatus/faclvgl/showlogo容器，仍只改92b000/ccd000两扇区。
原showlogo的open/query/mmap/绘图不是板初始化；省略它后仍保留boardinit及rcS
中的panel_fb_switch迁移。faclvgl/showlogo入口改为成功stub，防止工厂命令再次启动
broker；ntpcstatus表值不变但命令返回-38，NTPdaemon主代码保留。

新freeze绑定36项，和旧counter的21项完全分离；公共回退拒绝混合、未知及旧counter
基线。手势host/ASan/UBSan、9项实际ARM ELF模拟、33项Jim写入故障路径通过。
硬件安装读回、customowner状态、用户反复往返、完整断电自动启动及米家控制
均通过。冷启动后再次核对两个完整扇区和运行状态，结果见
native-ui-broker-hardware-result.json。模拟结果和这些实测分别记录。

## 下拉覆盖层新版本

3224B 的 native drawer 独立冻结，安装基线和回退目标为上面的 broker v1。
它增加顶边 20px 起手、80px 展开/收起阈值、跟手合成及按时间回弹。
计数改为无明显位移的 UP 时加一，避免上滑退出也计数。默认仍展开计数器。

仅保留启动安装代理的小 bootstrap pthread，ready 后退出。稳态的按键、触摸、
合成均在原 GUI 线程；不再增加第三触摸订阅。实体 input0 必须通过 upper 指针
匹配，不能假定 LVGL 列表第一个就是物理输入。GUI 输出坐标是 int32 @+0/+4，
不能把 raw sample 的 i16 @+10/+12 用到 read callback 输出上。

顶边从第一 DOWN 起截获完整接触。另一虚拟输入已有按下时不截取新的顶边手势；
动画中新接触全部消费到释放。结束时仍锁两 upper publisher，核对两个 ring、
原始释放和显示队列后才提交 owner。队列为空才改合成源。原缓冲区快照在 GUI
回调返回后的边界获取，但所有其他 mmap 写者均串行尚未证明，需观察背景撕裂。

借用额外 wifi_recorder worker 472B（3804bc98..3804be70），并将 builtin NOR
ccdd2c 改为 -38 stub，防止启动已替换代码；它不是 Wi-Fi 驱动或启动服务。
be70 起共享消息 helper 及其他扇区字节保留。完整容器3432B，目前余208B。

12项手势 host/ASan/UBSan、16组真实ARM ELF模型及38项写入器Jim mock通过，
源码/容量及安装器两份独立审查闭合，46项新输入冻结。硬件安装、两页完整读回、
暖启动 custom owner 和 GUI 活跃检查通过。用户手势及全断电结果独立记录在
native-drawer-hardware-result.json，不能引用旧 broker 结果替代。

用户已验证首版下拉、收起、取消、点击和三击均正常，反馈速度稍慢且缺少缓动。
后续3264B ease版仅改松手曲线为名义120ms cubic ease-out，手指按住时直接跟随。
它另有45项冻结输入，19组ARM模型与39项写入器mock及两份独立审查通过。
两版本共用相同入口页，ease回退目标为首版drawer；不能跨版本套用安装器。
ease暖启动完整页读回、GUI活跃/已展开通过，其用户观察和冷启动另见
native-drawer-ease-hardware-result.json。
