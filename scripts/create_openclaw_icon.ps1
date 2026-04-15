param(
    [Parameter(Mandatory = $true)]
    [string]$OutputPath
)

$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Drawing

$dir = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Force -Path $dir | Out-Null

$bitmap = New-Object System.Drawing.Bitmap 256, 256
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$graphics.Clear([System.Drawing.Color]::FromArgb(18, 28, 45))

$brush1 = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(51, 184, 255))
$brush2 = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(0, 230, 179))
$brush3 = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(245, 246, 250))
$pen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(245, 246, 250), 10)

$graphics.FillEllipse($brush1, 28, 28, 200, 200)
$graphics.FillEllipse($brush2, 92, 92, 136, 136)
$graphics.DrawEllipse($pen, 44, 44, 168, 168)
$graphics.FillRectangle($brush3, 108, 82, 40, 92)
$graphics.FillEllipse($brush3, 96, 146, 64, 64)

$ms = New-Object System.IO.MemoryStream
$bitmap.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png)
$pngBytes = $ms.ToArray()

$fs = [System.IO.File]::Open($OutputPath, [System.IO.FileMode]::Create)
$writer = New-Object System.IO.BinaryWriter($fs)
$writer.Write([byte[]](0,0,1,0,1,0))
$writer.Write([byte]0)
$writer.Write([byte]0)
$writer.Write([byte]0)
$writer.Write([byte]0)
$writer.Write([UInt16]1)
$writer.Write([UInt16]32)
$writer.Write([UInt32]$pngBytes.Length)
$writer.Write([UInt32]22)
$writer.Write($pngBytes)
$writer.Flush()
$writer.Close()
$fs.Close()

$graphics.Dispose()
$bitmap.Dispose()
$brush1.Dispose()
$brush2.Dispose()
$brush3.Dispose()
$pen.Dispose()
$ms.Dispose()
