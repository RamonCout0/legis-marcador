# Legis Marcador

Programa que **assiste ao vídeo de uma Sessão Ordinária e sugere os marcadores** do Legis Vídeos:
quem abriu a sessão, quem leu a mensagem bíblica e a ata, quem falou na tribuna, quem deu aparte,
e **o minuto exato** em que cada um começou a falar.

Você confere, corrige o que precisar, envia — e **quem publica é você**, no próprio Legis Vídeos.

> Feito por **Ramon Couto**, com a colaboração do **Claude** (Anthropic).

---

## 1. Como usar (passo a passo)

1. Dê **dois cliques em `iniciar.bat`**. Uma janela preta abre e, em seguida, o navegador abre sozinho.
   *Mantenha a janela preta aberta enquanto usa. Para encerrar, feche-a.*
2. Entre com o **mesmo CPF e senha do Legis Vídeos**.
3. **Escolha a sessão.** Use os botões de cima para filtrar:
   - **Precisa marcar** – sessões sem nenhum marcador;
   - **Falta publicar** – sessões com marcadores que ainda não estão públicos;
   - **Já publicadas** e **Todas**;
   - e escolha o **período** (últimos 30 dias, este mês, este ano, ou datas de/até) ou busque por "117ª" / "05/11".
   A tela lembra o filtro da última vez e **se atualiza sozinha**: ao voltar para a janela, ao voltar para a lista
   e a cada minuto, ela confere de novo no Legis Vídeos (por isso uma sessão que você acabou de publicar sai da lista
   de pendentes). O botão **↻ Atualizar agora** força a conferência.
4. Clique em **Marcar**. O programa baixa o vídeo e escreve a fala (isso pode levar vários minutos; pode deixar a página aberta).
   **Várias sessões de uma vez:** marque as caixinhas à esquerda das sessões e clique em **Preparar em segundo plano**.
   Elas são transcritas uma de cada vez e ficam como "✔ Pronta para conferir" — você confere as prontas enquanto as outras andam.
5. **Confira os marcadores.** Clique em **▶** para ouvir cada momento.
   - Linhas em **amarelo** precisam que você escolha o vereador.
   - Escolha **quem presidia** a sessão (o áudio não diz isso) para preencher a Abertura.
   - Desmarque a caixinha dos que não quiser enviar, ou use **✕** para remover. **+ Adicionar marcador** cria um no ponto atual do vídeo.
6. Clique em **Enviar para o Legis Vídeos**. Os marcadores entram **sem ficar públicos**.
7. Clique em **Abrir no Legis Vídeos**, confira e aperte **Publicar**. Na tela final há também um botão
   **"Marcar a próxima"**, que já abre a próxima sessão pendente.

**Se o vídeo já tem marcadores**, a tela pergunta o que fazer:
- **Completar** – adiciona só o que falta e mantém o que já existe;
- **Substituir** – coloca os novos e **remove os antigos**. Antes de apagar, uma cópia dos antigos é guardada em `data/backups/`.

Dica de acessibilidade: os botões **A−** e **A+** no topo mudam o tamanho das letras.

### Instalação (só na primeira vez)
É preciso ter o **Python 3.10 ou mais novo** instalado (python.org, marcando "Add Python to PATH") e internet.
Na primeira execução o `iniciar.bat` prepara tudo sozinho (alguns minutos). Na primeira transcrição, o modelo de
voz (centenas de MB) também é baixado uma vez.

### Configuração (o endereço do SEU Legis Vídeos)
Este projeto **não traz nenhum endereço de servidor**. Na primeira vez o `iniciar.bat` copia `.env.exemplo` para `.env`
e abre o Bloco de Notas: troque os endereços de exemplo (`LEGIS_API` e `LEGIS_ADMIN_URL`) pelos do Legis Vídeos da sua
instituição. O arquivo `.env` fica só no seu computador (está no `.gitignore`) — **nunca o envie ao GitHub**.

---

## 2. Como funciona por dentro

```
 vídeo (.mp4)                                   lista de vereadores
     │                                                  │
     ▼                                                  │
 Whisper (faster-whisper)                               │
 transcreve em português COM o tempo de cada palavra    │
     │                                                  │
     ▼                                                  ▼
 Detector de falas (regras sobre o que o presidente anuncia)
   "convido a vereadora X para fazer a leitura da mensagem bíblica"
   "passaremos à leitura da ata pelo secretário, vereador Y"
   "convido o vereador Z para fazer uso da tribuna"
   "concedo o aparte ao vereador W"
   "em discussão, vereador V"
     │   casa o nome falado com a lista oficial (tolera erros de escrita)
     │   marca o instante em que a pessoa chamada COMEÇA a falar
     ▼
 (opcional) Ollama – modelo pequeno, só nos trechos duvidosos que as regras não pegaram
     │   sua resposta é sempre validada contra a lista de fases e de vereadores
     ▼
 Tela de revisão  ──►  você confere  ──►  envio como NÃO público  ──►  você publica no Legis Vídeos
```

**Por que assim?** O Legis Vídeos guarda só o texto da transcrição, sem horários. O "quando" só existe no áudio,
por isso o programa transcreve o vídeo de novo, desta vez guardando o tempo de cada palavra. O "quem" vem
das frases do presidente, que anuncia quase tudo pelo nome.

**Roda em qualquer PC.** Sem placa de vídeo usa o processador (modelo `small`, mais lento). Com placa NVIDIA
(testado conceito com a GTX 1650) pode usar o modelo `medium`, mais preciso: veja "Placa de vídeo" abaixo.
O Ollama é opcional; sem ele o programa funciona só com as regras.

### Usando o Ollama (IA do seu computador)
Com o Ollama ligado, a caixinha **"Usar a IA do meu computador"** vem marcada. Ele faz duas coisas, sempre com o resultado
conferido contra a lista oficial (**nunca inventa vereador nem fase**):
1. descobre **nomes que o Whisper escreveu errado** ("Mara Cabales" → Marina Cavalcanti), nos marcadores que ficariam sem vereador;
2. olha trechos duvidosos em que alguém recebe a palavra e as regras não pegaram.
Os nomes sugeridos pela IA aparecem marcados como **"nome sugerido pela IA — confira"**. Nos testes da sessão 435
(1h40), a IA acertou 5 dos 6 nomes que preencheu; a nota "tudo certo" foi de 11 para 16 de 29.

### Marcadores que o programa gera
Abertura · Mensagem Bíblica · Leitura da ata · Leitura de expediente · Uso da tribuna · Aparte ·
**retorno à tribuna** (quando quem estava na tribuna volta a falar depois de um aparte) · **Em Discussão**.
"Ordem do dia" não é gerada (a equipe não usa). "Questão de Ordem", votações e moções ainda não são geradas.

---

## 3. Quão certo ele acerta? (leia antes de confiar)

Foi comparado com os marcadores que a equipe já tinha feito, em sessões reais
(`python tests\avaliar.py <id>`). Resumo honesto:

"Momento encontrado" = existe um marcador do programa a até 45 s do da equipe (a equipe marca "a olho", com folga).
"Tudo certo" = além do momento, a fase e o vereador também batem. A Abertura fica de fora, porque o presidente
não aparece no áudio.

| Sessão | Momento encontrado | Tudo certo (sem a Abertura) |
|---|---|---|
| 441, 439, 432 (curtas) | 20 de 20 | 17 de 17 |
| 438 (1h09, com discussões) | 11 de 11 | 9 de 10 (falta o nome de 1 "Em Discussão") |
| 435 (1h40, 30 marcadores, muita discussão) | **22 de 30** | **11 de 29** (16 de 29 com a IA do Ollama) |
| 444 | sem gabarito (a equipe ainda não marcou); conferida à mão na transcrição | — |

*Atenção: as regras foram ajustadas olhando 441, 439, 432 e 438, então essas notas são otimistas. A 435 é a mais
honesta: é longa, tem muitas discussões e o Whisper erra bastante.*

**O que isso significa:** o programa é um **assistente que adianta o trabalho**, não um substituto da conferência.
Nas sessões curtas e "limpas" ele acerta quase tudo. Nas longas, com muitas discussões, ele acha **a maior parte dos
momentos** (22 de 30 na 435), mas **muitas vezes sem saber o nome** — essas linhas ficam em amarelo para você escolher
o vereador ouvindo o trecho. Para a lista de discussões, ele usa duas pistas: a presidente dizendo o nome
("em discussão, vereador X") e a pessoa abrindo a fala com "Obrigado, senhor presidente".

### Limites conhecidos
- **Quem fala nas discussões:** o áudio só diz o nome quando a presidente chama ("em discussão, vereador X") e o Whisper
  nem sempre escreve o nome certo. Nos demais casos o marcador sai **sem vereador** (linha amarela, "escolher vereador").
  Identificar pela **voz** resolveria, mas ainda não foi feito.
- **Alguns momentos não aparecem na transcrição:** quando o Whisper "engole" a frase da presidente, o programa não tem
  como achar o ponto (8 dos 30 marcadores da 435 ficaram de fora).
- **Mensagem Bíblica:** na 435 saiu 23 s adiantada, porque o Whisper inventou frases na pausa antes da leitura.
- **Questão de Ordem, votações e moções:** ainda não são geradas.
- **Presidente da Abertura:** não dá para saber pelo áudio; escolha na tela.
- **Erros do Whisper:** ele escreve "veriador", "Atta", "declara Berta"... As regras toleram vários desses erros, mas
  nem todos. Nomes errados de vereadores podem ser corrigidos em `data/apelidos.json`.
- **Retorno à tribuna:** a equipe, nas sessões que marcou, **não** marca a volta do orador após o aparte; o programa marca
  (pedido seu). Pode sobrar marcador a mais para apagar.
- **Velocidade:** não foi cronometrada; depende do computador. A transcrição no processador de um vídeo de ~1 hora
  leva vários minutos.

---

## 4. Segurança e privacidade
- **Nada é publicado pelo programa.** Ele não tem a função de publicar; só cria marcadores não públicos.
- A **senha** vai direto para o Legis Vídeos e **não é gravada**. O programa só roda no seu computador
  (`http://localhost:8765`), não fica exposto na internet.
- **Substituir** guarda cópia dos marcadores antigos em `data/backups/` e só apaga depois de criar os novos
  (se algo falhar, nada é apagado).
- Os vídeos baixados ficam em `data/videos/` e as transcrições em `data/transcripts/` (podem ser apagados para liberar espaço;
  serão baixados/gerados de novo se precisar).

---

### Proteções do programa
O servidor local aceita **somente** `localhost`/`127.0.0.1` e só obedece pedidos que alteram algo (enviar, apagar)
quando vêm da própria página do programa. Isso impede que outro site aberto no navegador use a sua sessão do Legis
Vídeos (ataques tipo CSRF e *DNS rebinding*). Há também cabeçalhos de segurança (CSP, anti-iframe) e as respostas da
API não ficam em cache. **Não exponha a porta do programa na rede nem na internet.**

### Uso responsável e aviso
- Use **só com uma conta autorizada** e com a permissão da instituição responsável pelo Legis Vídeos.
- Este é um projeto **independente**: não tem vínculo, apoio nem aprovação do Legis Vídeos, de seus desenvolvedores ou de
  qualquer câmara/assembleia. "Legis Vídeos" é nome do respectivo sistema.
- Os vídeos e as falas das sessões pertencem à instituição; o programa os baixa e guarda **no seu computador** para o
  processamento. Respeite as regras de uso e de privacidade do seu órgão.
- O resultado é **sugestão**: confira sempre antes de publicar. Sem garantias (veja a licença).
- Para relatar uma falha de segurança, use a aba **Security** deste repositório no GitHub (relato privado).

## 5. Pastas e arquivos

```
iniciar.bat              ← abre o programa (dois cliques)
requirements.txt         ← bibliotecas Python
app/
  __main__.py            ← inicia o servidor e abre o navegador
  server.py              ← servidor local (FastAPI) e rotas da tela
  legis_api.py           ← conversa com a API do Legis Vídeos (entrar, ler, criar/apagar marcadores)
  transcribe.py          ← Whisper: transcrição com tempo por palavra (GPU se houver, senão CPU)
  detector.py            ← as regras: quem fala, quando, e casamento do nome
  llm.py                 ← Ollama (opcional) para trechos duvidosos
  pipeline.py            ← baixar → transcrever → detectar, com progresso e fila de preparo
  envio.py               ← envio: novo / completar / substituir, com backup
static/index.html        ← a tela (HTML + JavaScript, sem instalar nada)
data/
  apelidos.exemplo.json  ← modelo do arquivo de correção de nomes (o seu é o apelidos.json, fora do Git)
  fixtures/              ← (só no seu PC) gabaritos de sessões já marcadas, usados nos testes
  backups/ videos/ transcripts/   ← criadas conforme o uso
tests/avaliar.py         ← compara o resultado com os marcadores da equipe
```

### Ajustes opcionais
- **Corrigir nomes:** copie `data/apelidos.exemplo.json` para `data/apelidos.json` e edite (como a transcrição escreve →
  número do vereador no Legis Vídeos). Esse arquivo fica só no seu computador.
- **Modelo de voz:** variável `WHISPER_MODEL` (`tiny`, `base`, `small`, `medium`). Padrão: `small` no processador, `medium` com placa.
- **Placa de vídeo NVIDIA (opcional):** no `.venv`, `pip install nvidia-cublas-cu12 nvidia-cudnn-cu12`. Se algo falhar, o programa volta sozinho ao processador.
- **Ollama:** usa o modelo `qwen2.5:3b-instruct` se o Ollama estiver rodando (`OLLAMA_MODEL` muda o modelo).

### Testar a precisão
```
.venv\Scripts\python.exe tests\avaliar.py 441
```
Baixa o vídeo (se preciso), transcreve e compara com os marcadores da sua equipe, cadastrados em `data/fixtures/ref.json`
(arquivo **seu, fora do Git**). O formato está em `tests/exemplo/ref.exemplo.json` (dados fictícios); para testar o
formato sem dados reais use `--ref tests/exemplo/ref.exemplo.json`.

---

## 6. Problemas comuns

| Sintoma | O que fazer |
|---|---|
| O navegador não abriu | Acesse `http://localhost:8765` |
| "Não encontrei este CPF" ao entrar | Confira os 11 números; é o mesmo CPF do Legis Vídeos |
| A tela parece antiga depois de atualizar | Feche a janela preta, abra o `iniciar.bat` de novo e aperte **Ctrl+F5** |
| "Este vídeo já tem marcadores" | Na tela de revisão escolha **Completar** ou **Substituir** |
| Demora muito na transcrição | É normal sem placa de vídeo; deixe rodando, ou use "Preparar em segundo plano" |
| "Perdi a conexão com o Legis Vídeos" | A internet, o antivírus ou uma VPN derrubou a conexão. O programa já tenta de novo sozinho e retoma o download; o que foi baixado/transcrito fica guardado. Clique em Voltar e depois em Marcar |
| A IA aparece como "Ollama desligado" | Abra o Ollama (ou rode `ollama serve`) e recarregue a página |
| Erro ao instalar | Verifique a internet e se o Python está instalado com "Add Python to PATH" |

---

## 7. Como foi feito

Este programa nasceu de uma conversa entre **Ramon Couto** (quem conhece o trabalho e o Legis Vídeos) e o **Claude**
(IA da Anthropic, que escreveu e testou o código).

1. **Entender o sistema.** O Claude explorou o painel do Legis Vídeos (só leitura, com a conta de quem usa) para
   entender como os marcadores são guardados e quais dados precisava ler e gravar.
2. **Descobrir o que faltava.** A transcrição guardada no sistema não tem horários. Daí a decisão de transcrever o
   áudio de novo, com tempo por palavra.
3. **Usar o trabalho da equipe como gabarito.** Centenas de sessões já têm marcadores feitos à mão. O programa foi
   ajustado e **medido** contra elas (veja a seção 3), mostrando também onde ainda erra.
4. **Interface.** Pensada para quem não é do ramo: passos numerados, letras grandes e ajustáveis, linguagem simples,
   avisos antes de qualquer ação que apague algo, e nada é publicado sem você.
5. **Cuidado com o que é irreversível.** O programa nunca publica; "Substituir" faz backup; o Claude nunca digitou
   a senha de ninguém (o login é feito por quem usa).

**Tecnologias:** Python · FastAPI · faster-whisper (Whisper) · rapidfuzz · Ollama (opcional) · HTML/CSS/JavaScript simples.

**Próximos passos possíveis:** reconhecer vereadores pela voz (resolveria os "Em Discussão" sem nome); marcar
Questão de Ordem; empacotar como programa `.exe` com janela própria (sem navegador).

---

## 8. Licença

[MIT](LICENSE) — você pode usar, copiar, modificar e distribuir, mantendo o aviso de copyright. O software é fornecido
"como está", sem garantias. Contribuições são bem-vindas (abra uma *issue* ou *pull request*).

---

*Feito por Ramon Couto, com a colaboração do Claude (Anthropic).*
