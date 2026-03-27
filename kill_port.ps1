$pids = @(18300, 30496, 18664, 17540, 27764, 38124)
foreach ($pid in $pids) {
    try {
        Stop-Process -Id $pid -Force -ErrorAction Stop
        Write-Host "Killed PID $pid"
    } catch {
        Write-Host "Could not kill PID $pid"
    }
}
