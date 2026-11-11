# ハーネス v2 の見張り（HARNESS_V2.md）。係の心拍（harness/hb.py）が止まっていないかを 5 分ごとに外から見る。
# 登録は店長がタスク スケジューラで（このファイルは登録しない）：
# （このファイルは BOM 付き UTF-8：Windows PowerShell 5.1 は BOM が無いと日本語を読み違えて構文エラーになる。BOM を消さない）
#   schtasks /Create /TN "HarnessWatchdog" /SC MINUTE /MO 5 /TR "powershell -NoProfile -ExecutionPolicy Bypass -File D:\Claude\Wishlist\harness\watchdog.ps1"
# すること：hb.py stale（N 分 心拍のない係）→ 新しい止まりだけ D:/Claude/hf/state/alerts.jsonl に 1 行 → hb.py summary（summary.json）。
# 係は止めない・消さない（止める・起こし直すのは主の会話が summary.json と alerts.jsonl を見て決める）。
param(
  [string]$Repo = "D:\Claude\Wishlist",
  [string]$State = $(if ($env:HF_STATE) { $env:HF_STATE } else { "D:\Claude\hf\state" }),
  [string]$Python = "",
  [double]$Minutes = 20
)
$ErrorActionPreference = "Continue"
if (-not $Python) { $Python = Join-Path $Repo ".venv\Scripts\python.exe" }
if (-not (Test-Path $Python)) { $Python = "python" }
$env:PYTHONIOENCODING = "utf-8"; $env:PYTHONUTF8 = "1"; $env:HF_STATE = $State; $env:HF_ROOT = $Repo
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$hb = Join-Path $Repo "harness\hb.py"
$alerts = Join-Path $State "alerts.jsonl"
$utf8 = New-Object System.Text.UTF8Encoding($false)
New-Item -ItemType Directory -Force $State | Out-Null

$raw = & $Python $hb stale --minutes $Minutes --json
$stale = @()
if ($raw) { try { $stale = @(($raw -join "") | ConvertFrom-Json) } catch { $stale = @() } }

# 同じ止まり（同じ係・同じ最後の心拍）は 1 回だけ書く
$seen = @{}
if (Test-Path $alerts) {
  Get-Content $alerts -Encoding UTF8 -Tail 200 | ForEach-Object { try { $o = $_ | ConvertFrom-Json; $seen["$($o.role)|$($o.task)|$($o.beat)"] = 1 } catch {} }
}
$now = (Get-Date).ToString("yyyy-MM-ddTHH:mm:sszzz")
foreach ($a in $stale) {
  if (-not $a) { continue }
  $key = "$($a.role)|$($a.task)|$($a.at)"
  if ($seen.ContainsKey($key)) { continue }
  $rec = [ordered]@{ t = $now; kind = "stale"; role = $a.role; task = $a.task; beat = $a.at; quiet = $a.quiet; note = $a.note
                     text = "$($a.role) $($a.task)：$($a.quiet) 分 心拍なし" }
  [System.IO.File]::AppendAllText($alerts, (($rec | ConvertTo-Json -Compress) + "`n"), $utf8)
}
& $Python $hb summary --minutes $Minutes
exit 0
