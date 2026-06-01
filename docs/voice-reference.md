# 参照音声の作り方

Sarashina2.2-TTS は、参照音声と文字起こしを使って声質を寄せます。

## 推奨

- 長さは3〜10秒ほど
- ノイズが少ない音声を使う
- 1人の声だけにする
- BGMや効果音を入れない
- `prompt_text` には、実際に話している文章を入れる

## 避けること

- 本人や権利者の許諾がない声を使う
- 公開リポジトリへ実音声を入れる
- サンプル音声の人物名や契約情報を README に書く
- 参照音声と違う文章を `prompt_text` に入れる

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

