# Creative Hub

Central local para organizar copies de Meta Ads e renderizar criativos verticais pelo motor isolado do `video_edit_mvp`.

## Desenvolvimento local

```powershell
cd creative_hub
python app.py
```

Abra `http://127.0.0.1:8092`.

## Fluxo atual

1. Crie cards na aba `Criativos` e escreva as copies.
2. Em `Edicao`, selecione pasta de takes, destino, B-roll, tratamento de audio e legenda.
3. Para o modo manual, vincule um arquivo de audio a cada card.
4. Selecione os cards e use `Testar selecionado` ou `Gerar lote`.

As configuracoes e os cards sao salvos em `data/state.json`. A chave da API de voz, quando preenchida, permanece local e nunca e devolvida para o navegador.

## Estrutura distribuida

Na distribuicao, este diretorio fica ao lado de `../video_edit_mvp`. O backend
resolve esse motor pelo layout do repositorio, sem depender de caminhos
pessoais. Para instalar e abrir a aplicacao, use os scripts e o guia na raiz
do repositorio.

## Seguranca dos arquivos

- `C:\FabricaDeVideos` nao e modificada.
- `video_edit_mvp` nao e modificado e so e reutilizado como motor local.
- Os takes e os audios de entrada nunca sao apagados, movidos ou renomeados.
- Cada render cria uma area temporaria de audios dentro da pasta de saida configurada.

## API de voz

O painel e o backend ja possuem o contrato para um provedor de texto para fala, mas nenhuma chamada externa e feita nesta versao. Quando a documentacao do provedor chegar, o adaptador entra em `voice_provider.py` sem alterar o fluxo de cards ou o motor de video.
