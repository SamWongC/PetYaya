param([string]$OutputPath = '')
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
# Speech is stdin data, never executable PowerShell or SSML.
$text = [Console]::In.ReadToEnd()
$speaker = New-Object -ComObject SAPI.SpVoice
$selected = $null
foreach ($voice in $speaker.GetVoices()) {
    if ($voice.GetAttribute('Language') -match '(^|;)804(;|$)') { $selected = $voice; break }
}
if ($null -eq $selected) { throw 'No Simplified Chinese SAPI voice installed.' }
$speaker.Voice = $selected
$stream = $null
try {
    if ($OutputPath) {
        $stream = New-Object -ComObject SAPI.SpFileStream
        $stream.Open($OutputPath, 3, $false)
        $speaker.AudioOutputStream = $stream
    }
    # SVSFIsNotXML=16 prevents markup interpretation.
    [void]$speaker.Speak($text, 16)
} finally {
    if ($null -ne $stream) { $stream.Close() }
}

