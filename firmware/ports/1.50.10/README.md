# 本机 1.50.10 端口

这些地址只适用于已备份并审核的这台 `xiaomi.controller.86v1`。完整原厂 16MiB NOR
SHA-256 为 `777de42c53a1c95495c55b3a9a0c27f907f68ab87a9512bee6b5f4356acb695b`。
维护版使用旧图片实验程序的精确三页作为基线；新增网络页与图片解码页分别核对原厂字节。

| 用途 | A7 运行地址，末端不含 | NOR 页 | 约束 |
| --- | --- | --- | --- |
| UI 主段 | `0x3804b108..0x3804be70` | `0x92b000` | 保留 `be70` 起的共享 helper |
| UI 辅助段 | `0x3807a764..0x3807a920` | `0x95a000` | 保留相邻背光 callback 和 JSON helper |
| HTTP 网络段 | `0x3804d000..0x3804dff0` | `0x92d000` | 位于被禁用的单个 `uorb_unit_test` 命令内部 |
| 图片解码段 | `0x38047098..0x38047dac` | `0x927000` | 借用 `filldisk/fillcpu/fillmem` 诊断群，保留 `47dac` 起的共享 helper |
| builtin 入口表 | 不作代码段 | `0xccd000` | 禁用借用的诊断入口，保留其他字节 |

A7 装载映射为 runtime `0x38000000` 对应 NOR `0x8e0004`。网络页的运行映射实际起于
`0x3804cffc`；可借区段避开首 4B、末 12B，以保留边界处完整原厂指令。
整页原始 SHA-256 为 `76a994fbd3892960f43db969b4744fbb726d23feac5c24df86041398ee5d299d`。
新 BIN 只替换自身长度，其余原字节均保留，写入与读回仍按完整 4KiB 页处理。

## 新网络区段的静态依据

原厂 builtin `uorb_unit_test` 的入口字位于 NOR `0xccdc3c`，值为 `0x3804cf3d`。
从 `0x3804cf3c` 的函数序言到下个 `pns` 序言 `0x3804e120` 是这个测试命令的单个函数；
新增区段完全位于其中。维护版将这个 builtin 的入口改为已有的 `-ENOSYS` stub
`0x3804b109`，因此该诊断命令不能再使用。

全 NOR 的 aligned address-like word 扫描只找到 builtin 表入口及一处指令字巧合；
全 A7 的外部 Thumb32 direct branch/call 扫描没有进入这个函数的引用。NSH help 的
`0x3801a8a0/0x3801a8a4` 构造这个入口地址，仅检查非零并统计命令名，不调用它。
完整外部引用审查和方法限制记录在私有 ownership review，并随 release 原字节冻结。
静态扫描不能证明任意未知间接调用或真实启动行为；安装前仍需 live 四页基线核对，
安装后单独记录暖启动、原界面及网络行为，不能挪用历史结果。

## 入口与恢复

主入口 Thumb 地址固定为 `0x3804b2f5`，入口的 4B `B.W` 固定。段内函数可重新链接，
原厂 ABI 地址和硬编码 glyph 的 context 偏移需重新验证。所有状态仍位于 owned heap，
allocated `.data/.bss` 不允许进入这些原厂代码槽位。

后继图片解码候选采用五页：安装 codec → network → aux → main → entry，
恢复 entry → main → aux → network → codec。完整页面、保护状态及 caller cleanup
全闭合后才允许 MCU GLOBAL 重启；A7/WF/BT 在各中间阶段保持 reset。
回退目标为旧图片实验程序的精确三页、原厂网络页与原厂解码页；仅在完整集合恢复后，
才可以使用历史三页回退器。当前四页 release 仍使用它自己的冻结工具，不套用新工具。

解码页运行映射起于 `0x38046ffc`。仅借用页内 `+0x9c..+0xdb0` 的 3348B，
保留前 156B、后 592B；页面原 SHA-256 为
`21c40d397e6ec14f61011544f736962470f623c91ba3bbf7a6d89d120ba23c02`。
入口页的 `+0xd68/+0xd7c/+0xca0` 分别是 `filldisk/fillcpu/fillmem`，
原指针 `0x38047099/0x38047849/0x38047b3d` 都改为已有 `-ENOSYS` stub。
完整 A7 引用扫描、指令影子分类及启动脚本检查单列在私有解码页 ownership 证据中。
页内尾部共享 helper 有真实外部调用，不能扩大覆盖范围。
