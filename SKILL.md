---
name: sarashina-tts
description: |
  Sarashina2.2-TTS を使い、Codex の notify 出力を日本語音声で読み上げる。
  Windows、PowerShell、常駐デーモン、参照音声、ffplay 再生を扱う。
---

# Sarashina2.2-TTS Codex Notify

Codex の `notify` payload を受け取り、Sarashina2.2-TTS で音声合成する。

## 使い方

1. `install.ps1 -ConfigureCodex` を実行する。
2. Codex を再起動する。
3. `scripts/test_notify.ps1` で音声生成を確認する。

## 参照音声

`settings.json` の `prompt_file` と `prompt_text` を使う。
第三者の声を使う場合は、本人または権利者の許諾を確認する。

話し方を安定させたい場合は、5秒以上の明瞭な参照音声を使う。
許諾済みWAVから作る場合は、`scripts/create_voice_reference.ps1` を使う。
実音声、人物名、元ファイルパスは public repo に入れない。

## 注意

Sarashina2.2-TTS とモデルのライセンスは上流に従う。
商用利用では、必ずライセンス条件を確認する。
