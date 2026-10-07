# Starts the freshly built Sare.exe on the runner and checks that it really works.
$ErrorActionPreference = "Stop"

$port = 8765
$base = "http://127.0.0.1:$port"
$tmp  = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { $env:TEMP }
$data = Join-Path $tmp "sare-data"
$out  = Join-Path $tmp "sare_out.log"
$err  = Join-Path $tmp "sare_err.log"
Remove-Item $data, $out, $err -Recurse -Force -ErrorAction SilentlyContinue

# Settings the program reads (a fresh data folder = a true first run)
$env:SARE_DATA_DIR       = $data
$env:SARE_PORT           = "$port"
$env:SARE_NO_BROWSER     = "1"
$env:SARE_ADMIN_USER     = "ci"
$env:SARE_ADMIN_PASSWORD = "Ci-" + [guid]::NewGuid().ToString("N")

$exe = Join-Path (Get-Location) "dist\Sare\Sare.exe"
if (-not (Test-Path $exe)) { Write-Host "FAIL  $exe was not built"; exit 1 }

$script:failures = @()
function Check([string]$name, [bool]$ok) {
    if ($ok) { Write-Host "PASS  $name" }
    else     { Write-Host "FAIL  $name"; $script:failures += $name }
}

$proc = Start-Process -FilePath $exe -PassThru -NoNewWindow `
        -RedirectStandardOutput $out -RedirectStandardError $err

try {
    # wait up to 90 seconds for the program to answer
    $up = $false
    for ($i = 0; $i -lt 90; $i++) {
        if ($proc.HasExited) { break }
        try {
            $r = Invoke-WebRequest "$base/" -UseBasicParsing -TimeoutSec 3
            if ($r.StatusCode -eq 200) { $up = $true; break }
        } catch { }
        Start-Sleep -Seconds 1
    }
    Check "program starts and answers on port $port" $up

    if ($up) {
        $s = New-Object Microsoft.PowerShell.Commands.WebRequestSession

        $landing = Invoke-WebRequest "$base/" -WebSession $s -UseBasicParsing -SkipHttpErrorCheck
        Check "sign-in page loads" ($landing.Content -match "Sign in")
        $token = [regex]::Match($landing.Content, 'name="csrfmiddlewaretoken" value="([^"]+)"').Groups[1].Value
        Check "sign-in form has a security token" ($token.Length -gt 10)

        $css = Invoke-WebRequest "$base/static/admin/css/base.css" -UseBasicParsing -SkipHttpErrorCheck
        Check "built-in styling files are served" ($css.StatusCode -eq 200)
        $logo = Invoke-WebRequest "$base/static/logo.png" -UseBasicParsing -SkipHttpErrorCheck
        Check "your logo file is served" ($logo.StatusCode -eq 200)

        $login = Invoke-WebRequest "$base/" -Method Post -WebSession $s -UseBasicParsing -SkipHttpErrorCheck `
                 -Headers @{ Referer = "$base/" } `
                 -Body @{ csrfmiddlewaretoken = $token; username = $env:SARE_ADMIN_USER; password = $env:SARE_ADMIN_PASSWORD }
        Check "administrator can sign in" ($login.Content -match "Inventory overview")

        $dash = Invoke-WebRequest "$base/admin/" -WebSession $s -UseBasicParsing -SkipHttpErrorCheck
        Check "dashboard opens" ($dash.Content -match "Inventory overview")
        Check "quick stock entry is on the dashboard" ($dash.Content -match "Quick stock entry")

        foreach ($k in "stock", "movements", "holdings") {
            $r = Invoke-WebRequest "$base/inventory/reports/$k/" -WebSession $s -UseBasicParsing -SkipHttpErrorCheck
            Check "report '$k' opens" ($r.StatusCode -eq 200)
        }

        $x = Invoke-WebRequest "$base/inventory/reports/stock/?format=xlsx" -WebSession $s -UseBasicParsing -SkipHttpErrorCheck
        $b = $x.RawContentStream.ToArray()
        Check "Excel export is a real .xlsx file" ($b.Length -gt 4 -and $b[0] -eq 0x50 -and $b[1] -eq 0x4B)

        $g = Invoke-WebRequest "$base/admin/auth/group/" -WebSession $s -UseBasicParsing -SkipHttpErrorCheck
        Check "access roles were created on first run" ($g.Content -match "Store Manager" -and $g.Content -match "Issuing Clerk")

        $m = Invoke-WebRequest "$base/admin/inventory/stockmovement/add/" -WebSession $s -UseBasicParsing -SkipHttpErrorCheck
        Check "add-movement form opens" ($m.StatusCode -eq 200)
    }
}
catch {
    Write-Host "FAIL  unexpected error: $($_.Exception.Message)"
    $script:failures += "unexpected error"
}
finally {
    if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force }
    Write-Host "`n----- what the program printed -----"
    Get-Content $out, $err -ErrorAction SilentlyContinue
}

if ($script:failures.Count -gt 0) {
    Write-Host "`n$($script:failures.Count) check(s) FAILED"
    exit 1
}
Write-Host "`nAll checks passed - this build works."
