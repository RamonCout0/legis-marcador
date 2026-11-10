# Segurança

## Como relatar uma vulnerabilidade
Não abra uma *issue* pública com detalhes de falhas. Use **Security → Report a vulnerability** neste repositório
(relato privado do GitHub). Descreva o problema, como reproduzir e o impacto.

## O que não deve ir para o repositório
- Senhas, tokens e o arquivo `.env`.
- Endereços de servidores de uma instituição específica, listas de pessoas com IDs internos, links diretos de vídeos
  e gabaritos de sessões reais (ficam em `.env`, `data/apelidos.json` e `data/fixtures/`, todos no `.gitignore`).
- Vídeos e transcrições de sessões.

## Modelo de segurança
O programa roda localmente (127.0.0.1) e usa a sessão de quem fez login. Não foi feito para ser exposto na rede.
