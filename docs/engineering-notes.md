# 工程经验与检查点

记录更新日期：2026-10-05。适用设备：小米智能家庭面板 `xiaomi.controller.86v1`。
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

ease版用户反馈手感改善，但向上收起仍偏突然。完整断电后自动计数器、上下滑、
三击及米家在线控制均正常。随后的独立只读核对确认两页完整SHA、MCU运行、
reset catch/临时断点清零、GUI活跃，最终stock owner/count3/toggles29。
当前缓出只用于松手后的剩余行程，不使用松手速度，前30ms已走完约58%；
速度衔接与收起曲线仍是可继续优化的体验项，不是未完成的输入交接验证。

后续针对用户“上滑停住再松手，仍有时突然收起”的只读采样保存1000条UI状态。
两次首次计算分别从上次提交233/220跳到114/91；旧起点已过25/30ms，缓出前段
很陡。样本非原子，shown表示PAN已接收，不代表LCD已扫描；不能把本次证据
写成已证明整段120ms在首帧前过期，也不能说手指未松开便启动了自动动画。
新优化独立命名native-drawer-smooth，不能改写现有ease冻结源码/ELF。
起点应来自有效的已提交位置，先呈现起点，再使用新时钟；帧间延迟不能无限
吞掉中间位置。进度只在安全呈现路径推进，同时处理小距离整数取整不动、
PAN/CLOCK失败、中途改目标及单次时钟回绕。墙钟耗时与曲线逻辑进度分别说明。

smooth版3368B已安装，结束于3804be30，距共享helper还有64B。
22组实际ARM模型、41项写入器mock、独立源码/安装器审查通过，新冻结47项。
松手从有效shown开始，pending清零前提交phase0并取PAN返回后的新CLOCK；
后续phase使用提交前的时间作锚点，让下一帧计入渲染耗时，再限制最多推进30ms。
失败不提交进度；即使整数取整位置相同也执行安全提交，避免1px剩余行程卡死。
新增context字段pending/phase为byte168/172，旧animation_from仍是byte164。
实机写入闭包、两页完整读回及暖启动custom owner、pending0/phase150通过。
用户手感及完整断电结果仍单独记录，不借用上一个ease版本的冷启动结论。

用户随后确认 smooth 新版手感良好，并明确跳过完整断电测试。接着将计数文字
替换为独立 `native-github-card` 信息卡：官方白色 GitHub 标志、用户名、完整项目名，
以及金色五角星和 `Star on GitHub` 提示；显示时没有电脑绘图循环。

卡片 BIN3432B，ELF allocated3428B加4B地址空隙，恰好用满既有容器；末端是
3804be70 exclusive，共享 helper 保留原字节。官方 PNG 的 alpha 边界裁切、LANCZOS
缩到24×24后 threshold128，按2倍显示。packed5列字形与私有 Thumb 绘图节省空间，
两个私有函数都用40B保存帧保持8B栈对齐；它们没有引入新的原固件ABI。
context176B、begin/clock及pan之后的核心与smooth一致，唯一调用变化是绘图函数
改为 `paint(pixels,cover)`，不再使用计数来决定文字。

新模型27组通过：保留22组smooth行为，另外核对全部321个cover的完整画布、
独立原始行位图参考、前后红区、R4–R11/SP恢复和逐指令栈对齐。43项Jim写入器
路径、独立源码容量/安装器审查通过，51项输入另行冻结，旧四套集合保持原字节。
新安装基线和回退目标都是精确smooth两页；入口页仍字节相同，仅代码页指定范围变化。

实机安装闭包、两页完整SHA读回及正常重启后custom owner/ready、GUI活跃、
cover320/pending0/phase150通过。实屏排版、颜色和手势另见
native-github-card-hardware-result.json；用户确认显示及三种手势均正常。
当前及smooth的完整断电测试按用户要求跳过，
不能借用更早ease或broker的断电/米家控制结果作为这两版的通过证明。

## Flash 容量与扩展路线

对精确 1.50.10 原厂备份的统计见 `analysis/flash-capacity-summary-1.50.10.json`。
16 MiB 中非 FF 字节约13.29 MiB（83.06%），完整全 FF 的4 KiB页共659页、
约2.574 MiB。这是内容模式统计，不等于链接器声明的已用/可用空间；
全 FF 也可能属于 OTA 元数据、身份分区或其他保留范围。

主要连续空白为 AP 分区 `0x825000..0x8e0000`（748 KiB）和 A7 分区
`0xe5d000..0xfe0000`（1548 KiB）。MCU 的 NOR XIP 与 A7 的载入方式不同：
A7 正常启动只复制 `0x8e0004..0xdd3fe4` 的 `0x4f3fe0` 字节，目标末端
为 `0x384f3fe0`，BSS 从 `0x384f4000` 开始。A7 空白尾部在复制范围之外，
直接写入 A7 函数不会被加载；盲目扩大长度会跨进既有 BSS/堆布局，且复制范围
之外还有非 FF 数据。现有几 KB 上限来自被借用的函数容器，并非全芯片容量上限。

后续可在明确保留、核对 OTA 和回退范围的 NOR 页中存放程序或资源，再增加
受控读取/装载入口。代码还需解决 owned RAM、重定位、执行权限和缓存同步；
扩展原主映像则要一起修改链接、加载长度和 BSS/堆布局并验证启动。
读取或执行 NOR 本身不改变阵列；当前绘图/点击状态只在 RAM 中变化。
没有穷尽证明原系统所有运行路径都不写 NOR。BOOT 已确认会改保护状态寄存器，
这与改写备份中的固件/数据字节是不同的操作。

## GitHub 卡片的临时累加反馈

独立 `native-github-tap` 已安装。主 BIN3392B，辅助 BIN291B，共3683B（含主段4B空隙）。
主段末端3804be48，40B旧卡片尾部和be70共享helper保持原值；辅助范围
3807a764..3807a887，位于原工厂socket worker的444B容器内，a920后的背光回调和
ae28 JSON helper保留。新的引用审查和只读实页哈希已确认第三页95a000基线；
旧整个工厂线程候选未获准使用，不能据这291B实验扩大覆盖范围。

原physical-only DRAWER_TAP在UP时累计；新pending字段等待有效CLOCK样本设起点，
避免旧UP时间把刚收到的点击立即判为过期。800ms无点击后只提议恢复星标，
真正PAN接受恢复帧才清零。队列阻塞或PAN失败时不改画布、不清序列；期间的新
点按继续累加并续期。clock回绕和失败、u32饱和、多位数居中均有当前实际ARM模型。
显示、触摸、计时完全在设备上运行，触摸不写Flash。context184B，+176/+180是
feedback_ms/feedback_pending；动画pending/+168和phase/+172保持原偏移。

40组实际ARM模型、65项三页Jim写入器测试、独立程序/辅助槽和writer peer review
通过，61项输入独立冻结。168B native caller和完整BOOT外层按命名替换保留原字节，
新的三页公共编排单独审查，不能称为整个writer只改名。
安装aux→code→entry，每页完整验证和状态检查后才走下一阶段；回退entry→code→aux，
先去除新主代码引用，再返回原辅助页。回退目标是精确card，之后用各版本自己的入口。

实机正常重启后三页完整SHA、MCU运行/resetcatch及临时FPB清理通过；GUI活跃、
custom owner/ready、cover320/pending0/phase150、count0/feedback_pending0通过。
真实点击与手势观察单独记录在native-github-tap-hardware-result.json；完整断电
仍按用户要求跳过，未新验证米家控制，不能挪用旧版结果。

用户确认tap版整体正常，但连续点击间歇响应慢、跳过点击甚至直接恢复星标；
随后一次复现感觉顺畅。两轮非原子的MEM-AP采样没有记录到count变化，不能用它们
证明实际绘制延迟或队列溢出。离线实指令复核确认物理subscriber仅8×32B，满后覆盖
旧样本，不保护DOWN/UP配对；GUI先读取输入后再绘图。模型中缺UP可合并点击、
误作移动，甚至触发关闭，但尚未证明这次实机问题就是溢出。

当前一次普通计数的软件画布写量626460B，包含全帧填充及整卡重画，不含原PAN
旋转。计时锚取自绘制前；900ms模拟PAN后下一轮便开始恢复，而实际可见时间还取决于
星标那帧的提交/扫描，不能直接称LCD只显示20ms。第二个DOWN按住时，旧超时逻辑
也会清序列、下一UP重回+1。这些独立复现的缺口将用另一个版本修正，不能更改tap
已经冻结的源码/模型来掩盖结果。真实fresh sample总置continue/+0x13为1，
缓存DOWN的continue为0，因此不能移除fresh门作为漏点修复。
