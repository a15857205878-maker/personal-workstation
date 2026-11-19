# 个人工作站

Windows 本地桌面工作站，包含搭档聊天、任务分工、成果、工具、休闲、手机连接与设置。主程序位于 `components/Agent工作台`，运行资料从空状态创建。

## Windows x64 便携版

下载后完整解压，双击 `PersonalWorkstation.exe`。包内自带 Python 和 Tcl/Tk，使用系统的 WebView2 Evergreen Runtime。缺少 WebView2 时，包内 README 提供微软下载入口。

[下载便携 ZIP](https://github.com/a15857205878-maker/personal-workstation/releases/download/v2026.11.20.1/PersonalWorkstation-2026.11.20.1-portable-win-x64-evergreen.zip) · [查看发布页](https://github.com/a15857205878-maker/personal-workstation/releases/tag/v2026.11.20.1)

## 2026.11.20

- 搭档群聊支持最多三名模型成员、按会话保存草稿和明确分工。任务先形成待确认计划，确认后运行，并可单独重试失败项。
- 成果按群聊会话和任务归组，可查看登记文件、回到原轮次，以及导出可编辑的 Word 文档和表格。
- 工作站重整搭档、成果、工具与休闲入口。手机配对页面提供聊天、成果、文件和更多四个入口，旧任务记录仍可访问。
- 工具页保留资料与打包、图标换装台等原有功能，休闲页整合书房和小镇专注入口。

## 源码安装与启动

需要 Windows 10/11、Python 3.12、Microsoft Edge WebView2 Runtime。开发构建另需 Node.js 22.8+、pnpm 11.25.0。依赖不会随源码包附带。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-lock.txt
python -B launch.py --check
python -B launch.py
```

激活环境后也可以运行 `start.cmd`。预检缺依赖或缺构建时返回 2；不会启动模型或写配对。`requirements-lock.txt` 是本次 Windows/Python 3.12 实际安装版本快照；`requirements.txt` 记录直接依赖及兼容范围，不表示其他平台也已验证。

已有生产前端构建。修改前端、人格或手机模块后，在包根用 PowerShell 7 执行：

```powershell
pwsh -NoProfile -File build.ps1
```

构建按共享工具中心→小镇→工作站→手机页面的顺序执行，使用各前端自己的锁文件，不读取安装目录的 `vendor` 或 `node_modules`。工作站 `frontend/build.mjs` 复用本包工具中心原组件与依赖；请保持 `components` 下目录之间的相邻关系。

## 组件与数据

| 目录 | 职责 |
| --- | --- |
| `components/Agent工作台` | 桌面外壳、聊天、任务、成果、有限协作及适配器 |
| `components/个人工具中心新版` | 原工具页面及固定 Bridge |
| `components/个人工具中心` | 打包、资料、轮盘、图标服务 |
| `components/游戏管家` | 游戏资料与修改器管理实现；不含游戏清单或游戏本体 |
| `components/宝可梦小镇新版` | 小镇计时、收藏、规则及存档所有者 |
| `components/远程服务` | 原手机会话、传输、配对及只读文件票据实现 |

工作站与工具组件在各自 `data`/`logs` 目录保存新资料。远程服务会在自己的目录创建配对、数据库、任务附件和收到的图片。公开包未带入任何已有聊天、记忆、密钥、密文、令牌、配对、文件共享目录或导航配置。发布后再次导出时仍需白名单，不能把自己的使用目录整体上传。

默认协作文件房间位于 `Agent工作台/examples/collab`，含通用空房间与原有 `next/card/bake/status/--check` 脚本；可以用 `--room` 指定自己独立的兼容房间。两个人格保留兼容 ID `lele`/`jingshui`，公开文本改为协作助手/审阅助手；编辑、风格快照和导出流程保留。旧的用户会话不会自动导入本包。

## 可选程序与素材

- 模型需要用户自行配置 API 或已登录 Codex CLI / DeepSeek Harness。普通启动和本次回归不调用真实模型；外部客户端交接仍需用户操作。
- 桌宠是单独组件。设置环境变量 `AGENT_PET_ROOT` 指向自己的桌宠源码/安装根，并在工具中心选择合法启动入口。缺失时显示未连接，不自动扫描或启动另一份角色。
- 本机联动可设置 `WORKSTATION_INTEGRATION_ROOT`；不随包附带私人导航索引或应用注册表。
- Tailscale 自行安装与连接。远程服务首次启动创建新的配对；本包没有原用户配对。
- PDF 栅格预览另需 Poppler `pdftoppm`，加入 PATH 或设置 `PDFTOPPM_PATH`。Office 转换另需 LibreOffice。缺少时保留清晰的下载原件提示；未附带第三方二进制。
- 原有历史会话读取使用本机 Node，支持 PATH 或 `WORKSTATION_NODE`；不会复制外部产品的登录和历史。相关功能需安装匹配的外部产品。
- 本包的角色、图标、原画、手机示意图和 GLB 均换为新绘制的中性示例。宝可梦品牌图像、个人图标库、Live2D、SDK 与未经确认的素材未附带。美术呈现不同，计时/收藏/加载/切区及业务调用流程仍保留。可以替换为自己有权使用的素材。

## 验证范围

生产前端与手机内联页面已根据本包源码重建，使用版本与锁文件相符的本地依赖。自动检查使用空数据目录、临时文件和测试模型响应。真实模型、实体手机跨网和可选外部应用需要各自配置并测试。解压时建议选用较短的路径，以适配 Windows 长路径设置。

自有代码按各组件 MIT 许可发布，第三方详见 `THIRD_PARTY_NOTICES.md`。安装与验证范围见本文及各组件说明。
