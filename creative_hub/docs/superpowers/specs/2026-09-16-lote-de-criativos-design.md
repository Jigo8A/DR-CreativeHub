# Lote De Criativos Com Reaproveitamento

## Objetivo

Transformar o comando `Gerar lote` em uma producao completa para todas as
copies com texto: gerar narracoes por API quando necessario, transcrever,
renderizar os videos e manter os arquivos finais organizados pelo titulo da
copy. A selecao de cards fica reservada ao teste individual.

## Escopo

- `Gerar lote` processa todas as copies que tenham texto, independente da
  selecao visual.
- `Testar selecionado` exige exatamente uma copy selecionada.
- Narracoes pendentes sao geradas em paralelo, com um limite interno de
  concorrencia configurado pelo servico para proteger a API e a maquina.
- Cada copy segue para transcricao e renderizacao assim que a narracao dela
  estiver disponivel; o lote nao espera todas as narracoes terminarem.
- O sistema reaproveita audio, transcricao e video quando o arquivo existe e
  a assinatura da etapa continua valida.
- Arquivos apagados manualmente sao detectados como ausentes e recriados na
  proxima execucao.

## Estado Persistido

`CopyCard` passa a guardar metadados de producao por etapa:

- assinatura da narracao: texto, voz efetiva e provedor de voz;
- assinatura da transcricao: assinatura da narracao e provedor de
  transcricao;
- assinatura de renderizacao: assinatura da transcricao e configuracoes que
  alteram o video, como takes, B-roll, legenda, headline e velocidade;
- caminhos do audio, da transcricao e do video final.

As assinaturas sao hashes de um payload JSON deterministico. O arquivo so e
reutilizado quando a assinatura coincide e o caminho persistido aponta para
um arquivo existente. Mudar um insumo invalida apenas as etapas dependentes.

## Organização De Arquivos

Na pasta de saida configurada:

- `audios/<titulo-normalizado>.mp3`
- `transcricoes/<titulo-normalizado>.json`
- `<titulo-normalizado>.mp4`

O titulo e normalizado para nomes validos no Windows. Titulos iguais recebem
um sufixo estavel baseado no id curto da copy, evitando sobrescrita sem tornar
o nome imprevisivel.

## Execucao

Um novo coordenador de producao recebe cards e um modo (`batch` ou `test`).
Ele monta uma fila de trabalho por copy, atualiza o estado do job de forma
segura entre threads e produz resultados individuais mesmo quando alguma copy
falha. No lote, a fase de audio usa um executor com limite de trabalhadores;
as fases seguintes sao iniciadas por copy assim que sua narracao fica pronta.

O renderizador existente continua sendo a fonte de verdade para juntar takes,
inserir B-roll, legenda e headline. A mudanca cria uma camada de orquestracao
acima dele, sem alterar a fabrica original.

## Interface E API

- Barra dos criativos recebe `Selecionar todas` e `Limpar selecao`.
- `Gerar lote` chama uma rota unica de producao completa para todas as copies.
- `Testar selecionado` usa a mesma rota com o id da unica copy selecionada.
- O job exposto ao frontend inclui etapa atual, progresso geral e resultado
  por copy.
- O frontend continua consultando `/api/job`, exibindo mensagens que tornam
  claro se uma etapa foi reaproveitada ou produzida novamente.

## Falhas E Recuperacao

Uma falha em uma copy nao cancela as demais. O resultado da copy guarda a
mensagem de erro e o proximo lote tenta novamente apenas o que estiver ausente
ou invalidado. Se o titulo estiver vazio, a copy recebe um nome de fallback
baseado no seu id.

## Testes

- Testes unitarios para assinaturas e normalizacao de nomes.
- Testes de servico para reutilizar artefatos validos e recriar arquivos
  apagados.
- Teste de lote que verifica paralelismo limitado, progresso e continuidade
  apos falha individual.
- Testes de API para lote completo, teste selecionado e regras de selecao.
- Teste de interface para os controles de selecionar todas e o contrato do
  novo endpoint.
