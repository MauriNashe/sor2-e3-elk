#Requires -RunAsAdministrator
<#
  Crea en Hyper-V la red del laboratorio y la VM monitoreada (Tarea 1).
  LEERLO ANTES DE EJECUTARLO. Requiere Hyper-V habilitado y PowerShell como administrador:

      powershell -ExecutionPolicy Bypass -File .\scripts\hyperv_crear_vm.ps1

  Hace:
    1. Switch virtual INTERNO "LabSwitch" (solo anfitrión <-> VM).
    2. IP 192.168.56.1/24 para Windows en ese switch (la VM usa .10).
    3. NAT de Windows para 192.168.56.0/24, para que la VM salga a internet a través del anfitrión.
    4. VM de generación 2: 8 GB de RAM fija, 4 vCPU, disco VHDX dinámico de 40 GB,
       arranque seguro con la plantilla de Microsoft UEFI CA (necesaria para Ubuntu), ISO cargada,
       sin puntos de control automáticos.
  No arranca la VM. Es idempotente para la red: si el switch, la IP o la NAT ya existen, los reutiliza.
#>
param(
    [string]$VmName     = 'sor2-lab',
    [string]$IsoPath    = "$env:USERPROFILE\Downloads\ubuntu-24.04.5-live-server-amd64.iso",
    [int64] $MemoryBytes = 8GB,   # fija; con 10 GB Hyper-V no arrancó en un anfitrión de 16 GB (~9,9 GB libres)
    [int]   $Cpus       = 4,
    [int64] $DiskBytes  = 40GB,
    [string]$SwitchName = 'LabSwitch',
    [string]$HostIp     = '192.168.56.1',
    [int]   $PrefixLen  = 24,
    [string]$NatName    = 'LabNAT',
    [string]$NatPrefix  = '192.168.56.0/24'
)
$ErrorActionPreference = 'Stop'

function Paso($t) { Write-Host "`n== $t" -ForegroundColor Cyan }

Paso 'Comprobaciones'
if (-not (Get-Module -ListAvailable Hyper-V)) {
    throw 'Hyper-V no está habilitado. Ejecutar: Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V -All  y reiniciar.'
}
if (-not (Test-Path $IsoPath)) { throw "No encuentro la ISO en $IsoPath (usar -IsoPath <ruta>)." }
if (Get-VM -Name $VmName -ErrorAction SilentlyContinue) { throw "Ya existe una VM llamada '$VmName'." }
$alias = "vEthernet ($SwitchName)"
$ipEnUso = Get-NetIPAddress -IPAddress $HostIp -ErrorAction SilentlyContinue | Where-Object InterfaceAlias -ne $alias
if ($ipEnUso) {
    throw "La IP $HostIp ya la usa '$($ipEnUso.InterfaceAlias)' (probablemente la red host-only de VirtualBox). " +
          "Eliminarla en VirtualBox: Archivo > Herramientas > Administrador de red > seleccionar > Eliminar."
}
Write-Host "OK: Hyper-V disponible, ISO encontrada, sin conflicto de IP."

Paso "1. Switch interno '$SwitchName'"
if (-not (Get-VMSwitch -Name $SwitchName -ErrorAction SilentlyContinue)) {
    New-VMSwitch -Name $SwitchName -SwitchType Internal | Out-Null
    Write-Host "Creado."
} else { Write-Host "Ya existía." }

Paso "2. IP del anfitrión $HostIp/$PrefixLen en '$alias'"
if (-not (Get-NetIPAddress -InterfaceAlias $alias -IPAddress $HostIp -ErrorAction SilentlyContinue)) {
    New-NetIPAddress -InterfaceAlias $alias -IPAddress $HostIp -PrefixLength $PrefixLen | Out-Null
    Write-Host "Asignada."
} else { Write-Host "Ya estaba asignada." }

Paso "3. NAT '$NatName' para $NatPrefix"
$nat = Get-NetNat -ErrorAction SilentlyContinue
if ($nat | Where-Object InternalIPInterfaceAddressPrefix -eq $NatPrefix) {
    Write-Host "Ya existía."
} elseif ($nat) {
    throw "Ya hay otra NAT de Windows ($($nat.Name), $($nat.InternalIPInterfaceAddressPrefix)); Windows admite una sola. Revisarla antes de seguir."
} else {
    New-NetNat -Name $NatName -InternalIPInterfaceAddressPrefix $NatPrefix | Out-Null
    Write-Host "Creada."
}

Paso "4. VM '$VmName'"
$vhd = Join-Path (Get-VMHost).VirtualHardDiskPath "$VmName.vhdx"
New-VM -Name $VmName -Generation 2 -MemoryStartupBytes $MemoryBytes `
       -NewVHDPath $vhd -NewVHDSizeBytes $DiskBytes -SwitchName $SwitchName | Out-Null
Set-VMMemory    -VMName $VmName -DynamicMemoryEnabled $false      # RAM fija: mediciones estables y memory_lock de ES
Set-VMProcessor -VMName $VmName -Count $Cpus
Set-VM          -Name $VmName -AutomaticCheckpointsEnabled $false -AutomaticStopAction ShutDown
Set-VMFirmware  -VMName $VmName -EnableSecureBoot On -SecureBootTemplate MicrosoftUEFICertificateAuthority
Add-VMDvdDrive  -VMName $VmName -Path $IsoPath
Set-VMFirmware  -VMName $VmName -FirstBootDevice (Get-VMDvdDrive -VMName $VmName)
Write-Host "Creada. Disco: $vhd (dinámico, $([math]::Round($DiskBytes/1GB)) GB)"

Paso 'Resumen'
Get-VM -Name $VmName | Select-Object Name, State, Generation, ProcessorCount,
    @{n='MemoriaGB';e={$_.MemoryStartup/1GB}}, @{n='RAMDinamica';e={$_.DynamicMemoryEnabled}} | Format-List
Get-VMNetworkAdapter -VMName $VmName | Select-Object SwitchName, MacAddress | Format-List
Write-Host "Siguiente paso: Start-VM $VmName ; vmconnect.exe localhost $VmName" -ForegroundColor Green
