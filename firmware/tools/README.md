# 离线发布材料

`release.ts` 用 Node 24 的原生 TypeScript strip-types 运行，不需要 npm 依赖。
它只准备、检查及绑定独立审查材料，**没有设备连接、live read 或 execute 命令**。
当前版本采用本机 1.50.10 的独立六页方案，名称为
`maintained-persistent-images-six-page-20261008-a`，candidate/freeze 已完成并已安装。
主 3432B、辅助 444B 的既有边界不变，
网络段限 `0x3804d000..0x3804dff0`（4080B），图片解码段限
`0x38047098..0x38047dac`（3348B），图片存储段限
`0x38052000..0x38052bf0`（3056B）。三个额外区域分别审查 `uorb_unit_test`、
`filldisk/fillcpu/fillmem` 和可选 `monkey` 单函数尾部的引用及入口，不能凭空白字节认定可写。
`monkey` 可由持久调试开关启动，本版放弃该诊断；正常启动和恢复使用的 `mkgpt` 已排除。
任何段溢出立即拒绝。旧五页及四页 release 继续使用各自的冻结执行器和相邻验证器，
canonical 工具仅接受 schema4 `six-page-store-v1`，不代替旧快照。

当前五段BIN main/aux/net/codec/store为3368/396/3940/3012/1676B。程序审查须覆盖
网络worker私有16B图片状态与不变的224B broker、两个`/data/86v1-image.*`槽、20B
`VPI1` header、实际解码后的启动回退，以及已知可恢复槽保护和完整独立读回确认。
202表示已确认保存并排队；非202或无响应也可能已经持久保存，不自动重试。
文件I/O不持GUI锁；NOR恢复不删除MMC文件，真实文件系统掉电耐久性不由离线模型证明。
实现与接口语义见[固件开发](../README.md#图片持久保存)和[当前架构](../../docs/architecture.md)。

完整 ELF SHA 为 `f7e4d2bbeff500ac997e694846523ddc025f94d88d1bccf7306419233ae6fcd3`；
522-input candidate SHA 为 `e061db87d2e4e4aa1e2836a89fa1dd1f47215826914b5b492b59b9bce7388591`，
528-input freeze SHA 为 `9a3f4d7e39a1451d7bef16672415d4183f516234a3741d986d3c721b6d39a801`。
本轮 139 项当前候选 writer、12 项 release、566 组实际 ARM、7 项 ABI、299 项 host HTTP
及30项网页检查通过；这些离线结果本身不证明实机行为。另行记录的五页自身恢复、
六页original检查后安装、完整native/cache/context、outer GLOBAL、暖读回和fresh patched
均通过。真实三格式保存、错误图保护、JPEG及浏览器默认PNG的独立暖重载和完整RGB565
读回通过，见[六页发布结果](../releases/maintained-persistent-images-20261008-a.json)。
六页自身硬件restore未测试，完整断电按用户要求跳过；不证明真实FAT/MMC掉电耐久性。

## 流程

在仓库根目录运行：

```powershell
node firmware/tools/release.ts baseline
node --test firmware/tools/release.test.ts
```

`baseline` 检查旧图片实验版（`native-image-drawer`）已冻结的精确 93 项输入、递归的
317 项历史集合、完整三页布局、168B caller，以及从完整 stock backup 提取的精确网络、
解码和存储页。它不生成或改写旧文件，
也不启动 OpenOCD。原冻结目录的 SHA 固定为
`fa99d95a98b3abd4f3e76ce304a4d6a12623f50338d0240a6aba4b91f0a0cf61`。

维护源码通过 `firmware/build.sh` 编译到 `build/panel/`。构建器用 `build-record.ts` 在编译
前记录源文件/工具链，在成功后核对输入未变化并记录 ELF/BIN/map SHA；只有
`build-inputs.json` 的 `completed: true` 才能 prepare。缺材料、旧 BIN 与新源码错配、
容器溢出、可写 ELF 段或入口变化均先拒绝。
实际使用的 compiler headers 在构建前后保持相同，完整副本保存为
`build/panel/compiler-headers/`；release 要求非空 `headers`/`headerCopies` hash 多重集
相同，并逐项把副本纳入私有 snapshot。不会把 Clang 标准头文件提交 Git。

```powershell
node firmware/tools/release.ts prepare my-first-candidate build/reviews/storage-ownership-review.json
node firmware/tools/release.ts verify my-first-candidate
```

名称须唯一，已有目录绝不覆盖。材料写入私有 `build/releases/<name>/`：

| 路径 | 内容 |
| --- | --- |
| `candidate.json` | schema4 `six-page-store-v1` 六页布局、来源、snapshot SHA、固定顺序，状态 candidate |
| `snapshot/firmware/` | 可维护源码、头文件、端口链接/入口、构建记录器、release 和单独审查的 hardware 工具快照 |
| `snapshot/build/panel/` | config、完成的 build 记录、五段 BIN（main/aux/net/codec/store）、ELF、map |
| `snapshot/reviews/storage-ownership.json` | 网络页、解码页和存储页分别绑定的 ownership 材料 |
| `snapshot/firmware/tests/` | 当前维护版 ARM/model/host 测试源码；作为审查输入，不冒充编译依赖或已通过结果 |
| `ownership-inputs/` | ownership review 引用的逐项来源快照 |
| `workspace/` | 原冻结依赖的原字节副本、新六页及私有 writer/stage/session/mock |

旧图片实验程序的 patched 三页与精确 stock 网络、解码、存储页共同成为新 release 的
**original**。新代码只覆盖各容器内自己的字节；网络页头 4B、尾 12B 以及所有其他
尾部字节保留。入口页仅将 `+0xc3c` 的 `uorb_unit_test` 函数指针从 `0x3804cf3d`
改成禁用 stub `0x3804b109`，并禁用 `+0xd68/+0xd7c/+0xca0` 的三个 fill 诊断入口。
存储页借用 NOR `0x932000` 的 `+4..+0xbf4`，入口页 `+0xe6c` 的 `monkey` 指针
`0x38051fd1` 同样改成禁用 stub。解码页前156B/后592B、存储页前4B/后1036B保留，
所有段仅替换实际 BIN 的长度。restore 返回精确旧图片实验程序三页和三个原厂依赖页；
再回更早版本必须使用原版本自己的链。它不读取、删除或回退 MMC 图片及设置文件。

Tcl writer、完整 stages 的 foreach/proc、outer 两 session 与 Python mock 从冻结原文
生成到私有 workspace。168B caller 和原 `execute_call` 原样保留；stage 白名单仅增加
同一 erase/program/cache callee 对固定网络、解码、存储页的入口，每页仍是 16 个 256B program
单元及完整 4KiB 读回。六页基线必须在首次 mutation 前一起匹配；install 固定
store→codec→net→aux→code→entry，restore 固定 entry→code→aux→net→codec→store，阶段之间验证完整页及状态。
A7/WF/BT 持续保持复位；六页最终字节、保护/QE/WIP、I/D cache、native return/context
都闭合后才允许完成 gate。session 前有 candidate gate；设备入口须由另行审查的
`hardware.ts` 验证完整 freeze 后开放。本工具自身不执行它，也不能直接运行 candidate
session。新 writer 必须另做独立审查，旧三页通过结果不能替代。

Python 仅用于私有生成的独立 mock，TypeScript 管理准备和冻结；没有新增 Python 业务
生成器。mock 的 rollback fixture 为旧图片实验三页加 stock net/codec/store，保留70个原有故障
场景，并增加网络、解码、存储页各23个场景，共139项。旧 case 标签中的 fast-tap/image 命名属于历史名称，私有
fixture 的明确含义以六页原始/补丁数据为准。OpenOCD exe 沿用冻结值，两份 DLL 和
CMSIS-DAP 接口配置作为新的 snapshot 输入绑定，不能声称它们属于旧 93 项冻结。
Windows xPack 的原配置位于 `tools/xpack-openocd-0.12.0-7/openocd/scripts/interface/cmsis-dap.cfg`；
release 保留这个路径的原字节副本，同时为 `-s diagnostics` 提供
`diagnostics/interface/cmsis-dap.cfg`。两个副本必须 hash/字节完全相同。离线 mock 会
禁止 adapter/init，因此 writer mock 通过本身不能证明设备连接所需包装依赖完整。
所有包含原厂字节的 release 材料都保持 ignored，不能提交 Git。

## 运行私有 writer mock

在 Windows PowerShell 切入该 release 的 `workspace/`：

```powershell
python -X utf8 analysis/persistence/test_panel_maintained_runner_offline.py
```

mock 使用复制的 exe/Jim 引擎，harness 屏蔽 init、adapter、reset、halt、resume 等真实
硬件入口，只模拟读取/调用，不连设备。输出留在独立 run 目录，不更新旧研究结果。
新 payload 的完整结果须单独检查，不能沿用原型的70/70或五页116/116标签。三个依赖页验证包括原始/
补丁混合拒绝，erase/program/native error/timeout，完整读回错误，QE/WIP/保护变化，
closed-return/posted transport，reset/fault，cache 闭合，错误来源/页号/任意 stage 拒绝，
以及安装/回滚依赖顺序。离线通过不证明实机时序或掉电恢复。

## 网络、解码及存储页 ownership 输入

`prepare` 必须显式传入已经完成的 `storage-ownership-review` JSON；缺省拒绝。字段为
`role`、`passed: true`、`firmware: "1.50.10"`、`baseline_freeze_sha256`、
`stock_backup_sha256`、`net_page_sha256`、`net_offset`、`runtime_start`、
`runtime_end_exclusive`、`builtin_entry_offset`、`builtin_original_word`、
`builtin_disabled_word`；解码页另有 `codec_page_sha256`、`codec_offset`、
`codec_runtime_start`、`codec_runtime_end_exclusive` 和三个 `codec_builtin_entries`
（`offset` / `original_word` / `disabled_word`）；存储页另有 `store_page_sha256`、`store_offset`、
`store_runtime_start`、`store_runtime_end_exclusive`、`store_builtin_entry_offset`、
`store_builtin_original_word`、`store_builtin_disabled_word`。另须 `net_review`、`codec_review`、
`store_review` 分别指向不同的实际审查文件（`path` / `sha256`），三者都在非空 `evidence_sha256` 中绑定。
地址接受十六进制字符串或数字，
但必须精确匹配上述布局。

stock backup SHA 是 `777de42c53a1c95495c55b3a9a0c27f907f68ab87a9512bee6b5f4356acb695b`；
net 页 SHA 是 `76a994fbd3892960f43db969b4744fbb726d23feac5c24df86041398ee5d299d`。
codec 页 SHA 是 `21c40d397e6ec14f61011544f736962470f623c91ba3bbf7a6d89d120ba23c02`。
store 页 SHA 是 `6874cd0d613150d2c71c70bbf5513f83f72214304e2891f092d50e6e87d84c71`，
NOR offset `0x932000`、runtime `0x38052000..0x38052bf0`，builtin entry offset `0xe6c`，
原指针 `0x38051fd1`、禁用指针 `0x3804b109`。审查的是可选诊断，不借用分区启动代码。
`evidence_sha256` 必须包含完整 backup 路径/上述 hash，并绑定实际 ownership 审查来源。
工具验证已提供审查材料与字节，不会自动把扫描结果标成 approved。

## 独立证据与 freeze

准备和验证不会把 candidate 自动标成已审核。先独立完成 storage ownership review、
program review、writer review、当前 actual ARM ELF model 和当前 writer mock。
`freeze` 接收一个引用表：

```json
{
  "storage-ownership-review": { "path": "build/reviews/storage-final.json", "sha256": "..." },
  "program-review": { "path": "build/reviews/program.json", "sha256": "..." },
  "writer-review": { "path": "build/reviews/writer.json", "sha256": "..." },
  "arm-model": { "path": "build/reviews/arm.json", "sha256": "..." },
  "writer-mock": { "path": "build/reviews/mock.json", "sha256": "..." }
}
```

每份证据必须是不同的 JSON artifact，并明确包含 `role`、`passed: true`、
`release_manifest_sha256`（candidate.json 完整 hash）、`reviewed_inputs`（candidate
全部 inputs 的逐项 hash）。ARM artifact 另须 `scope: "actual-arm"`、正数 `check_count`
和当前 `elf_sha256`；mock artifact 须 `all_passed: true` 及139个全通过、名称不重复、
精确覆盖继承和新增场景的 `cases`（`case`/`passed`）。storage artifact 另须
`ownership_sha256` 绑定 candidate 的 ownership JSON。不能给旧 result 补字段冒充审查。

```powershell
node firmware/tools/release.ts freeze my-first-candidate build/reviews/evidence.json
node firmware/tools/release.ts verify my-first-candidate
```

freeze 把五份 evidence 复制到私有快照，再写不可覆盖的 `freeze.json`。之后改动
canonical `firmware/src/` 不影响这个 release；verify 仍核对冻结旧基线、snapshot、
完整页重构及证据覆盖。freeze 记录已经完成的审查，不提供硬件授权，也不声称实机
安装、显示、触摸、HTTP、米家或完整断电已经验证。
