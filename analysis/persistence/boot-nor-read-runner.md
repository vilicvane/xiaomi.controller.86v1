# BOOT 只读 NOR RAM 执行器

`diagnostics/boot-nor-read-runner.cfg` 只定义函数，载入文件不会连接调试器、初始化 adapter、复位或执行设备代码。根代理负责既有 OpenOCD 会话、成功到达新鲜 BOOT 停点和外层恢复流程。

2026-10-04 状态更新：下文包含该执行器准备阶段的历史约束。后续原生 NOR 读取和固定扇区安装/回退已实机执行，见 `native-read-hardware-result.json` 和 `native-counter-hardware-result.json`。这些结果是在健康 MAIN 状态下进入独立 BOOT 路线验证的；没有故意损坏 MAIN 后做冷恢复实验，不能据此承诺任意状态救砖。离线 mock 本身仍不是硬件证明。

入口：`bnor_run_read_probe capture_dir a7_policy remove_fpb_command`。capture_dir 必须不存在，以免覆盖已有恢复证据；remove_fpb_command 由外层提供，例如 `boot_remove_fpb`。外层必须显式检查结果及 `bnor_safe_to_resume`，并在任何错误时跳过原有无条件 resume 的 finally。执行器成功后也保持暂停，恢复 PC=`0x0c0104c6`，由外层最终恢复其 DCRDR/FP_CTRL/debug ownership 后继续原始 BOOT。

`a7_policy=halted` 要求两次 PRSR/DSCR 一致显示供电、暂停且无新 reset/power 事件；先看 PU，PU=0 时不读 DSCR。`powerdown-verified` 只能由外层在独立 CMU/供电证据证明 A7 停止后选择，并再次要求 PRSR.PU=0；此模式从不访问已断电的 DSCR。若 A7 供电但被 CMU 保持复位，现有两种模式会拒绝，需要根据实际硬件证据单独审核，不能把它标成断电。

执行器保存原有 1 KiB 栈尾和 R0..12、SP、LR、PC、xPSR、MSP/PSP 及 Secure bank、MSPLIM/PSPLIM、当前与 Secure packed special、DCRDR；SP 和 limit 从不修改。只读 stub 放在 `originalSP-1024`，全部 code/output 位于 SP-852 以下，原 SP 以下顶端512B 留给 HAL 栈。此读流程最大 HAL 栈64B。原生9f、05、35与pre/post在完整匹配的 BOOT SRAM 调用闭包中执行；不包含 WREN、状态写、擦除或 program。

运行前后比较原始 BOOT SRAM 静态块（排除已证明初始化可变的 guard、bootmode cache、PMU/sysfreq 初始化配置两字、slow timer frequency、fast timer frequency 六个字，再分别比较它们未变）、完整 HAL BSS（正常路径仅 saved-lock 可变，确认 post 后恢复）、uncached NOR 首256B以及 controller +04/+14/+34/+3c 元数据。bootmode cache20003acc来自BOOT system_init调用0c001e40读取40080038并清低4位，source初值0不一定等于运行值。slow timer frequency20003ad8由20002de8测量后在20002e46/2e4e写入，source初值16000不一定等于运行值。其他初始化差异尚需实际BOOT捕获核对；首个未解释差异会在执行RAM代码前安全中止。+04只忽略已识别的 bits12..24事务字段，+3c只记录动态状态；不读取 RX/TX FIFO，不回放历史 command/address 寄存器。所有返回值、ID、输出 guard和精确 BKPT 都必须符合预期。

复位、fault/exception/security变化、未到达预期 BKPT或无法确认 post 结束时，不回放原来的 RAM/PC；请求维持 halt，保留当前状态供根代理恢复。普通比较错误即使已恢复调用者也将 `bnor_safe_to_resume` 保持0。不会用“恢复了寄存器”代替“控制器与执行上下文仍可安全继续”的证据。

离线 Jim 模拟已通过正常恢复、断电 A7 不访问 DSCR、运行途中 reset、运行途中 fault 四条路径。模拟测试没有 adapter/init 或设备连接；具体元数据见 `boot-nor-read-runner-review.json`。旧mock采用错误controller mapping，已保留为被替代的离线证据；修正后新mock再次通过。先前 mock 发现并修复了多行 Tcl list 与 read_memory 列表的文本表示差异；期望数据现在显式转换为同一数值列表。

寄存器编号证据来自本机 OpenOCD `src/target/armv7m.h:53-64`：26=MSP_S、27=PSP_S、28=MSPLIM_S、29=PSPLIM_S、34=Secure packed special；34不是 PSP_S。

2026-10-04 地址纠正：此前版本错误地把公开默认controller名字当作本镜像logical id0，标成40140000。实际BOOT table20003300/file5378和main table20003948/file155858的raw2words均为 {40148000,40140000}，HAL按table[id]索引，所以id0为40148000。根代理也捕获main live同序。旧标注不是已验证硬件证据；所有后续SPI寄存器访问必须先读并核对live SRAM指针表。 runner先验证liveBOOTtable20003300，再使用table[0]的动态base+offset读取SPI；不会访问未用id1的40140000块。+14仅比较divider bits16..23，+34仅比较已识别lock/reset300；+04忽略已识别transaction bits12..24；+3c仅记录动态状态，所有原始元数据仍保留。

新策略 `held-reset-cmu-verified` 要求外层已经验证 DSP isolation 和全新 BOOT 入口。它只读取 AON400800a4、MCU CMU40000044/114/160/34，两轮 masked 状态一致且每次 A7CPU bit1 为0；末尾再查一次 bit1。BOOT0c012a84已释放外围bank和AONbit0，所以不要求原先isolation masks继续为0。该策略完全不读取A7 PRSR/DSCR/CoreSight。成功的完整会话以 GLOBAL reset结束，失败保留暂停供root检查，不恢复旧MAIN/A7。

首次source校验前，在已验证BOOT暂停状态下保存 `boot-hal-context-preflight.bin`（200001a8，14968B）；这样一次捕获即可离线查看所有初始化差异，校验失败仍先于SPI寄存器访问和RAM代码执行。13种纯Jim mock覆盖既有策略、新策略及入口／执行前／读取后释放A7CPU、bank变化和source差异；mock捕获文件是明确标注的模拟占位文件，不是设备内存。

新发现的20003ad0/3ad4由原生PMU配置和sysfreq requester代码写入，现仅排除这两个已证明初始化字；每次保存独立8B before/after捕获并比较两个整字完全一致。第13种mock故意改变其中一个字，必须拒绝并保持safe_to_resume=0。其他未解释source差异仍在SPI/RAM执行前拒绝。
