# DR Creative Hub

Aplicacao local para organizar copies, narracoes, headlines, musicas e renders
de criativos verticais. O repositorio inclui o Creative Hub e o motor de video
necessario para gerar os arquivos finais.

## Antes de instalar

Use Windows 10 ou 11 e instale estes pre-requisitos:

- Python 3.12 ou superior, disponivel como `python` no terminal;
- Node.js LTS, que inclui `node` e `npm`;
- FFmpeg, com a pasta `bin` adicionada ao `PATH`.

O script de diagnostico verifica os tres requisitos. Ele nao instala programas
de sistema nem altera configuracoes globais do Windows.

## Instalacao

Abra o PowerShell na raiz deste repositorio e execute:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\install.ps1
```

O processo cria um ambiente Python isolado em `.venv`, instala o motor de
video e compila a interface auxiliar de headlines. Execute uma unica vez por
clone, ou novamente depois de atualizar dependencias.

## Abrir o Hub

```powershell
.\scripts\abrir-hub.ps1
```

O script inicia o servidor local em `http://127.0.0.1:8092` e abre o navegador.
Para conferir a maquina antes de instalar, rode:

```powershell
.\scripts\diagnostico.ps1
```

## Primeiro uso

Cada instalacao inicia sem ofertas, midias ou credenciais. No Hub, escolha a
pasta central das ofertas e configure as suas proprias chaves da OpenSpeaker e,
se for usar transcricao remota, da AssemblyAI. Essas chaves, seus caminhos,
audios, takes, B-rolls e videos renderizados ficam somente no computador local
e nunca devem ser enviados ao Git.

## Compartilhamento

Este repositorio e privado. O dono precisa conceder acesso no GitHub antes de
enviar o link. Quem receber o link pode pedir ao Codex para ler este README e
seguir a instalacao, reportando qualquer pre-requisito ausente sem modificar
configuracoes globais do Windows.

