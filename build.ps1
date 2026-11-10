$ErrorActionPreference='Stop'
Push-Location $PSScriptRoot
try {
    foreach ($name in @('个人工具中心新版','宝可梦小镇新版')) {
        Push-Location (Join-Path $PSScriptRoot "components/$name/frontend")
        try { pnpm install --frozen-lockfile; if ($LASTEXITCODE -ne 0) { throw '安装依赖失败' }; node scripts/build.mjs; if ($LASTEXITCODE -ne 0) { throw '构建失败' } } finally { Pop-Location }
    }
    node components/Agent工作台/frontend/build.mjs
    if ($LASTEXITCODE -ne 0) { throw '工作站构建失败' }
    python -B components/远程服务/app/build_mobile_ui.py
    if ($LASTEXITCODE -ne 0) { throw '手机页面构建失败' }
} finally { Pop-Location }
