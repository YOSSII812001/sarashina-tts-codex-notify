# 参照音声の作り方

Sarashina2.2-TTS は、参照音声と文字起こしを使って声質を寄せます。

## 推奨

- 声色だけなら3秒前後を目安にする
- 話し方や抑揚を安定させたい場合は5秒以上を目安にする
- 長めに使う場合も、まずは5〜20秒ほどの明瞭な区間を選ぶ
- ノイズが少ない音声を使う
- 1人の声だけにする
- BGMや効果音を入れない
- `prompt_text` には、実際に話している文章を入れる
- 長めの素材では、音声全体を一度に使う前に、発話内容を区間ごとに確認する
- 参照WAVを作るときは、人物名や制作情報などのメタデータを削除する

## 避けること

- 本人や権利者の許諾がない声を使う
- 公開リポジトリへ実音声を入れる
- サンプル音声の人物名や契約情報を README に書く
- 参照音声と違う文章を `prompt_text` に入れる
- 長い音声を、文字起こしを確認せずにそのまま使う

## 長めの参照音声を作る

このリポジトリには、許諾済みWAVから参照音声を作る補助スクリプトがあります。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\create_voice_reference.ps1 `
  -SourceWav "C:\path\to\your_private_voice.wav" `
  -StartSeconds 3 `
  -DurationSeconds 12 `
  -PromptText "この参照音声で実際に話している文章です。"
```

このスクリプトは、指定区間の切り出し、24kHz / mono 変換、音量補正、
メタデータ削除、`settings.json` 更新をまとめて行います。

すでに Sarashina デーモンが動いている場合は、設定変更後に停止してください。
次の通知時に新しい参照音声を読み込みます。

## 例

```json
{
  "prompt_name": "private sample",
  "prompt_file": "C:/Users/me/voices/private_sample.wav",
  "prompt_text": "これは自分で録音した参照音声です。"
}
```

設定を変えたあとは、`sarashina_tts_daemon.py` の Python プロセスを停止してください。
次の通知時に、自動で再起動します。
