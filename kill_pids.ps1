param([int[]]$pids)
foreach ($pid in $pids) {
    try {
        Stop-Process -Id $pid -Force -ErrorAction Stop
        Write-Host "Killed PID $pid"
    } catch {
        Write-Host "Could not kill PID $pid : $_"
    }
}
