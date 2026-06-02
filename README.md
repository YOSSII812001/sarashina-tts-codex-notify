# sarashina-tts-codex-notify

Codex の通知音声を Microsoft Edge TTS から Sarashina2.2-TTS に切り替えるための、Windows 向けセットアップです。

このリポジトリは glue code だけを含みます。Sarashina2.2-TTS 本体、モデル、実在人物の音声素材、生成音声は同梱しません。

## できること

- Codex の `notify` を Sarashina2.2-TTS へ転送します
- 1回目はモデルを読み込み、2回目以降は常駐デーモンで高速化します
- 参照音声を差し替えると、好みの声に寄せられます
- 旧 Edge TTS フックが残っている環境では、任意で Sarashina へ転送できます

## 注意

- Sarashina2.2-TTS とモデルのライセンスは、上流の条件に従ってください。
- Sarashina2.2-TTS は非商用ライセンスで公開されています。商用利用では権利者へ確認してください。
- 第三者の声を参照音声に使う場合は、本人または権利者の許諾を取ってください。
- 公開リポジトリに、声優、ナレーター、顧客などの実音声を入れないでください。

## クイックスタート

PowerShell で実行します。

```powershell
Set-Location $env:USERPROFILE
git clone https://github.com/YOSSII812001/sarashina-tts-codex-notify.git
Set-Location .\sarashina-tts-codex-notify
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -ConfigureCodex
```

インストール後、Codex を再起動してください。

## 動作確認

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test_notify.ps1
```

音声が鳴り、`%TEMP%\sarashina_tts_outputs` に WAV が作られれば成功です。

## 読み上げ文字数

既定では、1回の通知につき750文字まで読み上げます。
これは以前の Edge TTS 設定の `MaxLength = 750` と同じです。

Sarashina2.2-TTS には、内部で45文字前後に分割して渡します。
長文を1本で渡すと、本文を省略したり崩したりすることがあるためです。

変更したい場合は、環境変数 `SARASHINA_TTS_MAX_CHARS` を設定してください。
長文で音声が途中で切れる場合は、`SARASHINA_TTS_TOKENS_PER_CHAR` を少し増やしてください。
分割単位を変えたい場合は、`SARASHINA_TTS_CHUNK_CHARS` を設定してください。

## 参照音声を変える

### 長めの参照音声を作る

話し方や抑揚を安定させたい場合は、5秒以上の参照音声を使ってください。
声色だけなら3秒前後でも動きますが、スタイルの安定には長めの音声が効きます。

ただし、長ければ何でも良いわけではありません。
参照音声と `prompt_text` がズレると、読み上げ品質が落ちます。

許諾済みのWAVから参照音声を作る例です。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\create_voice_reference.ps1 `
  -SourceWav "C:\path\to\your_private_voice.wav" `
  -StartSeconds 3 `
  -DurationSeconds 12 `
  -PromptText "この参照音声で実際に話している文章です。"
```

このスクリプトは、次の処理をします。

- 指定区間を切り出す
- 24kHz / mono に変換する
- 音量をそろえる
- 不要なメタデータを削除する
- `settings.json` を更新する

長い素材を使う場合でも、冒頭の名乗り、権利者名、契約情報などは
公開repoに入れないでください。

### 手動で設定する

インストール後、次のファイルを編集します。

```text
%USERPROFILE%\.codex\skills\sarashina-tts\settings.json
```

例:

```json
{
  "prompt_name": "my private voice sample",
  "prompt_file": "C:/path/to/my_voice_sample.wav",
  "prompt_text": "この音声で実際に話している文章です。"
}
```

`prompt_text` は、参照音声で話している文章と一致させてください。
差が大きいと、声質や話し方が崩れやすくなります。
目安として、話し方の安定まで狙う場合は5〜20秒ほどの明瞭な音声を使ってください。

変更後は、デーモンを再起動します。

```powershell
Get-CimInstance Win32_Process |
  Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*sarashina_tts_daemon.py*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

次の通知時に、自動で新しい設定を読み込みます。

## 旧 Edge TTS が二重再生される場合

起動中の Codex や Claude Code が、古い Edge TTS フックを握っている場合があります。
その場合は、次を実行してください。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -DisableLegacyEdgeTts
```

既存ファイルは `.bak-YYYYMMDDHHMMSS` としてバックアップします。

## アンインストール

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\uninstall.ps1 -RemoveCodexNotify
```

Sarashina2.2-TTS 本体も消す場合だけ、次を追加します。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\uninstall.ps1 -RemoveCodexNotify -RemoveUpstreamRepo
```

## 構成

| パス | 役割 |
|---|---|
| `install.ps1` | セットアップ本体 |
| `uninstall.ps1` | アンインストール |
| `scripts/codex_notify_sarashina_tts.py` | Codex `notify` からキューへ入れる入口 |
| `scripts/sarashina_tts_daemon.py` | Sarashina2.2-TTS の常駐生成プロセス |
| `scripts/test_notify.ps1` | 短文の動作確認 |
| `scripts/create_voice_reference.ps1` | 許諾済みWAVから長めの参照音声を作る補助スクリプト |
| `templates/settings.example.json` | 参照音声設定の例 |
| `templates/settings.long-reference.example.json` | 長め参照音声設定の例 |

## 上流

- Sarashina2.2-TTS: https://github.com/sbintuitions/sarashina2.2-tts
- Hugging Face: https://huggingface.co/sbintuitions/sarashina2.2-tts
