# 许可与素材边界

`LICENSE` 与工作站/工具中心/游戏资料组件的许可保留已确认署名 `2026 23te472-gif and contributors`。小镇与远程服务的自有代码经用户明确授权采用 MIT，各自 LICENSE 使用中性的 `Personal Workstation contributors`；没有推断或填入待确认的新 GitHub 账号。

第三方文件不因根目录 MIT 而重新授权：

| 第三方 | 使用位置 | 原许可 |
| --- | --- | --- |
| React / React DOM | 生产前端 bundle | `licenses/react-LICENSE`、`react-dom-LICENSE` |
| Lucide React | 原工具和小镇界面图标 | `licenses/lucide-react-LICENSE` |
| esbuild | 开发构建工具 | `licenses/esbuild-LICENSE.md` |
| Phosphor | 工作站与手机内联 SVG 图标 | `licenses/PHOSPHOR-LICENSE.txt` |
| Three.js 0.187.0 | 小镇 yard 内联三维运行代码 | `licenses/Three-LICENSE.txt` |

这些条款从现存依赖的原许可文件逐字节保留。依赖包通过 pnpm/pip 安装；本包不附带 Python site-packages、WebView2、Poppler、LibreOffice、Codex、DeepSeek Harness、Tailscale 或其他二进制。安装后仍须遵守各自条款。

不包含原宝可梦 PNG/ICO、私人桌面图标收藏、Live2D 角色/SDK、未经核实的原画/手机角色图和原 GLB。源码内原始 raster data URI 与 GLB 已替换为本公开副本新绘制的中性几何示例；通用人格与词库也重新编写后重建，不从真实设定摘取。保留的原名称/兼容 ID 是接口兼容标识，不表示获得商标或品牌素材授权。
