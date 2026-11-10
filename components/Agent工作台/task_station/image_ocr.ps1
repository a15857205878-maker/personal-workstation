param([string]$ImagePath)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding($false)
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime] > $null
[Windows.Graphics.Imaging.BitmapDecoder,Windows.Graphics.Imaging,ContentType=WindowsRuntime] > $null
[Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime] > $null
[Windows.Media.Ocr.OcrResult,Windows.Foundation,ContentType=WindowsRuntime] > $null
$asTask=([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 })[0]
function AwaitOp($operation,$resultType){$task=$asTask.MakeGenericMethod($resultType).Invoke($null,@($operation));$task.Wait();$task.Result}
$file=AwaitOp ([Windows.Storage.StorageFile]::GetFileFromPathAsync($ImagePath)) ([Windows.Storage.StorageFile])
$stream=AwaitOp ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
try{
$decoder=AwaitOp ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
if($decoder.PixelWidth -gt 4096 -or $decoder.PixelHeight -gt 4096){throw '图片边长超过4096，请缩小副本后识别'}
$bitmap=AwaitOp ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
try{$engine=[Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages();if($null -eq $engine){throw '未配置本机OCR语言'}
$result=AwaitOp ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult]);[Console]::Write($result.Text)
}finally{if($bitmap){$bitmap.Dispose()}}
}finally{$stream.Dispose()}
