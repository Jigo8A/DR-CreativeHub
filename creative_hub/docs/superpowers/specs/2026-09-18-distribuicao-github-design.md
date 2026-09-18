# Distribuicao do Creative Hub pelo GitHub

## Objetivo

Permitir que outra pessoa em Windows instale e execute o Creative Hub a partir
de um repositorio privado do GitHub, sem depender de caminhos, midias, estado
ou credenciais da maquina de origem.

## Escopo

O repositorio privado `DR-CreativeHub` reunira o aplicativo e o motor
`video_edit_mvp` que ele usa para renderizar. A distribuicao tera scripts de
instalacao e inicializacao para Windows e documentacao que o Codex do
destinatario possa seguir sem conhecimento previo do ambiente local atual.

## Estrutura do repositorio

```text
DR-CreativeHub/
  creative_hub/        Aplicacao, frontend, fontes permitidas e testes
  video_edit_mvp/      Motor de video utilizado pelo Creative Hub
  scripts/             Instalacao, diagnostico e inicializacao no Windows
  requirements.txt     Dependencias Python reproduziveis
  README.md            Guia de instalacao, uso e resolucao de problemas
  .gitignore           Estado, segredos, artefatos e dependencias locais
```

O `video_bridge.py` passa a resolver o motor a partir da raiz do repositorio,
sem referencias a diretorios pessoais ou a `C:\FabricaDeVideos`.

A pasta `DR-CreativeHub` sera criada separadamente do workspace de
desenvolvimento atual. Ela recebera somente uma copia permitida e operacional
dos dois modulos, fontes em uso, scripts, testes, manifestos e documentacao.
Os diretorios de trabalho atuais permanecem intactos.

## Instalacao e execucao

1. O usuario clona o repositorio privado.
2. Executa `scripts\install.ps1` uma unica vez.
3. O script verifica Python, Node.js e FFmpeg; instala dependencias Python e
   do Headline Studio; compila o bundle web quando necessario.
4. O usuario executa `scripts\abrir-hub.ps1` ou o comando equivalente
   documentado. O script inicia o servidor local e abre o navegador.
5. O Hub inicia com estado vazio, e o usuario escolhe a pasta central das
   ofertas e configura suas proprias chaves de API no painel.

O diagnostico informara de forma direta os requisitos ausentes e os comandos
necessarios para corrigi-los. O instalador nao tenta instalar silenciosamente
programas de sistema, nem modifica configuracoes globais do Windows.

## Dados e seguranca

Nao entram no Git:

- `creative_hub/data/`, incluindo `state.json`;
- chaves de API, caminhos locais e configuracoes pessoais;
- ofertas, audios, takes, B-rolls, musicas e videos gerados;
- logs, caches, arquivos temporarios, `__pycache__` e `node_modules`;
- videos, imagens e testes manuais gerados durante o desenvolvimento.

O `.gitignore` bloqueara esses itens. Um arquivo de exemplo sem segredos pode
ser usado somente quando necessario para explicar a estrutura inicial.

## Dependencias e ativos

As dependencias Python serao registradas com versoes compativeis. O Headline
Studio manterá `package.json` e `package-lock.json`, permitindo `npm ci` na
maquina de destino. Fontes em uso normal ficarao em `creative_hub/assets/fonts`.
O experimento de emoji Apple permanece desligado e seus caches ou artefatos de
teste nao serao distribuidos.

FFmpeg continua sendo um pre-requisito externo. O diagnostico procurara uma
instalacao disponivel no `PATH` e mostrara como apontar ou instalar uma versao
compativel quando ela estiver ausente.

## Verificacao

Antes do primeiro push:

1. A suite Python completa deve passar.
2. O build do Headline Studio deve passar com `npm ci` seguido de `npm run build`.
3. O diagnostico deve identificar corretamente ambiente pronto e requisitos
   ausentes em cenarios controlados.
4. Uma copia limpa do repositorio deve iniciar sem os dados atuais e exibir o
   Hub no navegador.
5. Uma verificacao de segredos confirma que os arquivos ignorados nao entram
   no indice Git.

## Publicacao

Depois das verificacoes, sera criado um repositorio privado `DR-CreativeHub`
na conta GitHub autenticada e o primeiro commit sera enviado por HTTPS. O
usuario podera convidar o amigo ao repositorio pelo GitHub; o amigo usara o
link privado com o Codex na propria maquina.
