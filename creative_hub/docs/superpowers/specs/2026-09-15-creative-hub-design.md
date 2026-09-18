# Creative Hub - Design da primeira versao

## Objetivo

Criar uma central local, separada de `video_edit_mvp` e de `C:\FabricaDeVideos`, para transformar copies escritas em criativos verticais para Meta Ads. O fluxo final sera: copy -> audio gerado por API ou inserido manualmente -> edicao automatica -> video com legenda e B-roll.

Nesta primeira etapa, a API de voz ainda nao sera chamada porque a documentacao do provedor sera entregue depois. A interface, o armazenamento local e o contrato do backend devem ficar prontos para receber essa integracao sem alterar o motor de video.

## Limites e seguranca

- Novo projeto em `creative_hub`, como pasta irma de `video_edit_mvp`.
- `C:\FabricaDeVideos` permanece intocada.
- `video_edit_mvp` permanece intocado; a central o utiliza como dependencia local somente de leitura/importacao.
- Arquivos de entrada nunca sao apagados, movidos ou renomeados.
- Videos e audios gerados sao gravados exclusivamente na pasta de saida configurada pelo usuario.

## Arquitetura

### Aplicacao local

Um servidor HTTP Python independente hospeda o painel e fornece uma API local. O frontend sera uma aplicacao web sem dependencia de framework pesado, para manter a inicializacao rapida e compatibilidade com o MVP atual.

O backend tera modulos separados para:

- `storage`: leitura e escrita atomica de configuracoes e cards de copy em JSON local.
- `projects`: modelo e operacoes CRUD de cards, selecao e estados de execucao.
- `video_bridge`: adaptador que transforma a configuracao do painel no contrato de `creative_engine.process_creative_batch` do MVP.
- `voice_provider`: interface de geracao de voz. Inicialmente fornece estado `nao configurado`; depois recebe um adaptador para a API escolhida.
- `app`: rotas HTTP, fila de trabalho e servicos de arquivos locais.

O projeto tera dependencia explicita do diretorio irmao `../video_edit_mvp` apenas por importacao. Nenhum arquivo do MVP sera editado.

### Persistencia

O arquivo local `creative_hub/data/state.json` armazena:

- Preferencias de edicao: pastas, B-roll, palavras-chave, velocidade, corte de silencio e configuracao de legenda.
- Preferencias de voz: nome do provedor, voz/modelo selecionados e chave de API quando fornecida.
- Cards de copy: id, titulo, texto, fonte de audio, caminho do audio manual/gerado, estado, resultados e erro mais recente.

A chave de API nao sera exibida novamente depois de salva. Nesta primeira versao ela ficara armazenada localmente; uma camada de armazenamento seguro do Windows pode substitui-la sem alterar o frontend.

## Interface

### Estrutura

O painel usa fundo escuro, barra lateral fixa, bordas discretas, superficie de trabalho ampla e acento verde-lima. A referencia enviada determina a densidade e a organizacao, mas nao sera copiada como marca ou layout literal.

- Sidebar: marca `Creative Hub`, navegacao `Criativos`, `Edicao` e `Configuracoes`, e status do motor no rodape.
- Barra superior: nome da area, indicador de salvamento e acao principal contextual.
- Conteudo: no maximo duas colunas de trabalho; sem cards dentro de cards e sem elementos decorativos soltos.

### Criativos

Area principal com lista vertical de cards bem espacados. Cada card apresenta:

- titulo editavel opcional;
- texto da copy;
- seletor de origem `Gerar por API` ou `Audio manual`;
- estado visual (`Rascunho`, `Pronto para gerar`, `Audio pronto`, `Renderizado` ou `Erro`);
- player de audio e link para o video quando esses recursos existirem;
- acoes para editar, duplicar e remover.

Ha comandos para criar card, selecionar cards e iniciar o fluxo para os selecionados. Enquanto a API de voz nao estiver configurada, o fluxo mostra claramente que o audio manual pode ser anexado e impede a tentativa de geracao por API com uma mensagem objetiva.

### Edicao

Formulario organizado em grupos:

- Origem e destino: pasta de takes, pasta de audios manuais, pasta de saida e seletor de pasta nativo existente no MVP.
- Montagem: duracao de segmento, velocidade de fundo e opcao de aplicar velocidade ao B-roll.
- B-roll: caminho e lista de variacoes da palavra-chave.
- Audio: cortar silencio nas bordas, reduzir silencios internos, limite e duracao minima.
- Legendas: modo normal/destaque, palavras por linha, caixa alta, tamanho e posicao.

A pre-visualizacao da legenda e 9:16 e usa as mesmas proporcoes de posicao/tamanho que o renderizador. Arrastar e redimensionar na previa atualiza os campos e persiste no estado.

### Configuracoes

Campos para provedor de voz, chave de API e identificador de voz/modelo. Enquanto nao houver documentacao, o botao de validar responde que o conector ainda nao foi configurado. O contrato para o futuro conector recebe uma copy e retorna o caminho de um arquivo de audio salvo na pasta de trabalho.

## Fluxos

### Audio manual

1. Usuario cria e seleciona cards.
2. Usuario associa audios locais aos cards, ou escolhe a pasta de audios ja pronta.
3. Usuario inicia teste ou lote.
4. `video_bridge` cria um diretorio temporario de entrada contendo referencias/copies dos audios selecionados e chama o motor do MVP.
5. O painel acompanha progresso, atualiza cada card e disponibiliza abrir video/pasta.

### Geracao de voz por API (posterior)

1. Usuario seleciona cards de origem `Gerar por API`.
2. `voice_provider` gera e salva um audio por card.
3. Os caminhos retornados entram no mesmo fluxo de edicao em lote, sem caminho paralelo.
4. Falha de um card nao interrompe os demais; cards mostram erro individual e podem ser reexecutados.

### Teste

O usuario pode renderizar apenas o primeiro card selecionado. O resultado respeita todas as configuracoes de legenda, B-roll, audio e velocidade salvas, permitindo validar antes do lote.

## Endpoints iniciais

- `GET /api/state`: estado completo para inicializar a interface.
- `PUT /api/settings`: persiste preferencias de edicao e voz.
- `POST /api/copies`: cria card.
- `PUT /api/copies/:id`: edita card.
- `DELETE /api/copies/:id`: remove card.
- `POST /api/copies/:id/audio`: associa um arquivo de audio manual.
- `POST /api/select-folder`: usa o seletor moderno do Windows.
- `POST /api/render/test`: processa o primeiro card selecionado com audio pronto.
- `POST /api/render/batch`: processa todos os cards selecionados com audio pronto.
- `GET /api/job`: retorna progresso global e resultados por card.
- `POST /api/open-output` e `POST /api/open-video`: abrem resultado no Windows.

O endpoint de geracao de voz sera adicionado depois da documentacao da API, seguindo `POST /api/voice/generate` e reutilizando o mesmo modelo de job.

## Tratamento de erros

- Pastas inexistentes, nenhum take, nenhum audio ou configuracao de legenda invalida retornam erro amigavel antes do job iniciar.
- O motor de video retorna progresso e falha por item; o backend preserva os detalhes no card sem apagar resultados anteriores.
- Acoes simultaneas de renderizacao sao bloqueadas enquanto ha um lote ativo.
- Falhas de API de voz, quando implementada, ficam isoladas por copy e nao iniciam a etapa de video para aquele card.

## Testes e verificacao

- Testes unitarios para armazenamento, validacao de cards, conversao de configuracoes e isolamento do `video_bridge` por injecao do motor.
- Testes de API para CRUD, persistencia, selecao de pasta e inicio de jobs.
- Teste de interface para navegacao, criacao/edicao de card, configuracao persistida e estados de bloqueio da API de voz.
- Verificacao visual em desktop e viewport vertical, incluindo previa 9:16, ausencia de overflow e acoes principais acessiveis sem rolagem excessiva.

## Fora de escopo desta primeira entrega

- Chamadas reais para a API de voz e AssemblyAI, aguardando documentacao e credenciais.
- Login, usuarios, sincronizacao em nuvem e compartilhamento de projetos.
- Refatoracao ou modificacao da Fabrica original e do MVP existente.
