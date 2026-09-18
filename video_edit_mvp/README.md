# Video Edit MVP

MVP isolado para detectar fala, cortar o começo e o fim de takes, juntar tudo em ordem e exportar um novo MP4.

## Como rodar

```powershell
cd video_edit_mvp
python -m pip install -r requirements.txt
python app.py
```

A interface abre em `http://127.0.0.1:8091`.

## Segurança dos arquivos

- A pasta original `C:\FabricaDeVideos` não é modificada.
- Os takes de entrada não são apagados, movidos ou renomeados.
- Os vídeos finais são salvos em `video_edit_mvp\output` por padrão.

## Modos de corte

- `Fala (Whisper/VAD)`: usa os timestamps das palavras para cortar mesmo quando existe música de fundo.
- `Volume/silêncio`: usa apenas volume do áudio, útil como fallback rápido.
