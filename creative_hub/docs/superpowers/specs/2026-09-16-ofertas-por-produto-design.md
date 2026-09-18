# Ofertas por Produto - Design

## Objetivo

Permitir que o Creative Hub produza criativos para varios produtos em um unico lote, mantendo copies, midias e artefatos de cada produto completamente isolados.

## Conceitos

- **Oferta** e a unidade principal do workspace. No contexto do usuario, uma oferta representa um produto vendido.
- Uma oferta possui suas proprias copies, takes, B-roll, audios, transcricoes e videos finais.
- Os ajustes de estilo e comportamento de edicao continuam globais: legenda, headline base, Safe Zone, fonte, tratamento de audio e velocidade.
- Headlines por copy serao um modulo futuro. O modelo de copies deve permanecer identificavel dentro da oferta para receber essa associacao depois.

## Estrutura Persistida

`HubState` passa a conter uma lista de `Offer` e um `active_offer_id`. O campo legado `copies` deixa de ser a fonte de verdade; estados antigos sao migrados na leitura para uma oferta inicial, preservando todas as copies existentes.

Cada `Offer` possui:

- `id`: identificador estavel;
- `name`: nome exibido e base do nome de pasta;
- `slug`: nome seguro para pasta, unico entre ofertas;
- `takes_folder`, `broll_path`, `audio_folder`, `output_folder`: caminhos efetivos daquela oferta;
- `copies`: lista de `CopyCard` daquela oferta.

Os caminhos sao persistidos como valores absolutos para respeitar uma estrutura existente do usuario. A pasta central e um padrao configuravel, nao uma obrigacao para usar a oferta.

## Organizacao de Arquivos

Ao criar uma oferta com pasta central configurada, o Hub sugere e cria somente diretorios vazios:

```text
<pasta-central>/
  ofertas/
    <slug-da-oferta>/
      takes/
      broll/
      audios/
      output/
      transcricoes/
```

Nenhum take, B-roll ou arquivo existente e movido, renomeado ou apagado. A interface permite trocar cada caminho da oferta depois da criacao.

`audios`, `transcricoes` e `output` sao usados pelo cache de producao. Os nomes continuam baseados no titulo da copy, com sufixo estavel para evitar colisao no Windows.

## Fluxos de Interface

A navegacao recebe uma secao `Ofertas`. Ela exibe as ofertas em lista lateral e permite criar, renomear, selecionar e remover uma oferta vazia.

Na tela de Criativos, a oferta ativa aparece acima dos cards. Criar, duplicar, editar, anexar audio e apagar uma copy afetam apenas essa oferta.

Na tela de Edicao, o bloco de arquivos passa a editar os caminhos da oferta ativa. Os demais blocos continuam gravando `HubSettings` globais.

O seletor de arquivos parte do caminho da oferta ativa. A barra superior e os estados de processamento identificam qual oferta esta sendo processada.

## Producao em Lote

- `Testar selecionado` processa exatamente uma copy da oferta ativa.
- `Gerar lote` coleta todas as copies com texto de todas as ofertas.
- Antes de cada renderizacao, o coordenador recebe uma combinacao dos ajustes globais com os caminhos da respectiva oferta.
- A geracao de audio permanece concorrente, com no maximo tres tarefas de voz em paralelo.
- Cache, transcricao e renderizacao usam os caminhos da oferta da copy atual.
- Falha em uma copy ou oferta nao cancela as demais. O resultado identifica a oferta e a copy afetadas.

## Compatibilidade e Erros

Na ausencia de ofertas no arquivo de estado, o Hub cria uma oferta de migracao com as copies e caminhos atuais. Nenhuma copy, audio ou output existente e descartado.

Uma oferta sem takes ou sem pasta de saida gera erro apenas para as copies daquela oferta, com mensagem que inclui o nome da oferta. O lote segue com as demais ofertas validas.

## Testes

Os testes devem cobrir migracao de estado antigo, isolamento de copies, criacao segura de diretorios, atualizacao de caminhos por oferta, lote atraves de duas ofertas, cache em diretorios separados e os controles da interface.
