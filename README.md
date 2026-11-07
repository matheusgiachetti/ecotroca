# Ecotroca

**O caminho para um futuro sustentável.**

Plataforma web que ajuda quem descarta lixo eletrônico (REEE) a encontrar rapidamente o ponto de coleta correto mais próximo. Projeto da Usina de Projetos Experimentais (UPx) da Facens.

**No ar:** <https://ecotroca-xi.vercel.app> (deploy automático a cada push na `main`).

Site estático: HTML + CSS + JavaScript puro (ES modules), sem build e sem framework. Dados no Supabase, mapa no Google Maps.

---

## Estrutura

```
index.html              página única (Início, Mapa, Como funciona, O que descartar, Dúvidas, Sobre)
404.html                página "não encontrada" (a Vercel serve em qualquer endereço inexistente)
css/styles.css          estilos (mobile-first)
js/config.js            chaves e configurações públicas (placeholders começam com "COLE_")
js/main.js              interface: lista, filtros, detalhes, menu, animações
js/map.js               tudo do Google Maps (isolado: trocar de mapa = reescrever só este arquivo)
js/data.js              pontos de coleta no Supabase (ou JSON de exemplo no modo demonstração), conta e pontos
js/conta.js             painéis de conta e de registrar descarte (<dialog>)
js/ranking.js           seção Ranking (top 10 por período e cidade)
js/regras.js            seção "Como os pontos funcionam" (lê regras_pontos() do banco)
js/tema.js              tema claro, escuro e automático (botão no menu)
privacidade.html, termos.html  Política de Privacidade e Termos de uso (versão para revisão)
js/geo.js               geolocalização, distância (Haversine) e link "Como chegar"
data/pontos-exemplo.json   pontos fictícios do modo demonstração
supabase/schema.sql     tabela pontos_coleta + RLS
supabase/seed.sql       5 pontos de EXEMPLO (fictícios)
supabase/02-perfis.sql, 03-tipos-residuo.sql, 04-descartes.sql, 05-rpc-pontos.sql, 06-ranking.sql, 07-medalhas.sql, 08-excluir-conta.sql
                        conta, pontos, descartes, ranking, medalhas e exclusão de conta (rodar nesta ordem, 02 a 08, depois do schema.sql)
supabase/pontos-reais.sql  4 pontos reais de Sorocaba (em verificação)
assets/                 logo, ícones e fotos otimizadas
vercel.json             cabeçalhos para a hospedagem estática
tests/                  testes automáticos (Playwright em Python)
.github/workflows/      leitura diária para o Supabase gratuito não pausar
```

## Rodar localmente

Qualquer servidor estático serve. Com Python (já vem no Windows com o instalador oficial):

```bash
python -m http.server 5173
```

Abra <http://localhost:5173>. A geolocalização só funciona em `localhost` ou HTTPS.

> Abrir o `index.html` direto pelo explorador de arquivos (`file://`) não funciona: os módulos JS precisam de um servidor.

> Use a porta **5173**: é a única liberada na chave do Google Maps. Em outra porta o mapa mostra "O mapa está indisponível agora" (a lista continua funcionando).

## Testes

Testes automáticos com Playwright em Python (não precisa de Node nem de `package.json`):

```bash
python -m pip install -r tests/requirements.txt
python -m playwright install chromium
python -m http.server 5173          # em outro terminal
python -m pytest tests              # testa http://localhost:5173
```

Para testar o site publicado: `BASE_URL=https://ecotroca-xi.vercel.app python -m pytest tests` (no PowerShell: `$env:BASE_URL="https://ecotroca-xi.vercel.app"; python -m pytest tests`).

O SQL do ranking e o das medalhas também são testados num Postgres local descartável (`test_14_ranking_sql_local.py` e `test_15_medalhas_sql_local.py`, precisa de `python -m pip install pgserver "psycopg[binary]" tzdata`; sem isso o teste é pulado). Criar muitos usuários de teste em poucos minutos esbarra no limite do Auth (`429`): espere uns 5 minutos entre as rodadas.

Para poupar a cota do Google Maps (veja "Chave do Google Maps"), só ~7 testes carregam o mapa de verdade; nos outros o script do Maps é bloqueado. Com `SEM_MAPA=1` esses também são pulados.

Os testes leem os pontos direto do Supabase e conferem: mapa e marcadores, aviso de chave recusada, localização (emulada), detalhes do ponto, filtros, seções, feedback, layout em 320/375/768/1280 px, alvos de toque, `<head>`, página 404, permissões do banco (a chave pública só lê), segredos no histórico do git, `innerHTML`, imagens, teclado, contraste e WCAG AA (axe-core). Precisam de internet.

## Configuração (`js/config.js`)

| Constante | Situação | O que é |
|---|---|---|
| `SUPABASE_URL` | ✅ preenchida | URL do projeto Supabase "ecotroca" |
| `SUPABASE_ANON_KEY` | ✅ preenchida | chave **pública** (publishable). Pode ficar no navegador |
| `GOOGLE_MAPS_API_KEY` | ✅ preenchida | chave do projeto Google Cloud `ecotroca-512512`, restrita por site e só para a Maps JavaScript API |
| `GOOGLE_MAPS_MAP_ID` | `DEMO_MAP_ID` | Map ID; opcional trocar por um seu |
| `FEEDBACK_FORM_URL` | ✅ preenchida | formulário "Ecotroca — Dê sua opinião" no Google Forms (conta do projeto). Se voltar a ser placeholder, o botão "Dê sua opinião" some |

Comportamento automático:
- **Supabase não configurado** → carrega `data/pontos-exemplo.json` e mostra o aviso "Modo demonstração".
- **Google Maps não configurado** → no lugar do mapa aparece uma mensagem explicando o que falta; a lista, os filtros e a localização continuam funcionando.

**Nunca** coloque a chave `service_role` do Supabase no projeto.

## Supabase

O projeto `ecotroca` (organização "ecotroca") já está criado, com a tabela e os 4 pontos reais de `supabase/pontos-reais.sql` (os de exemplo foram removidos).

Para recriar do zero em outro projeto:
1. Crie um projeto em <https://supabase.com/dashboard> (plano gratuito; região São Paulo `sa-east-1`, se quiser).
2. Abra **SQL Editor**, cole e rode `supabase/schema.sql`, depois `supabase/seed.sql`.
3. Em **Project Settings → API Keys**, copie a URL e a chave **publishable** (ou a `anon` legada) para `js/config.js`.

Segurança: RLS ativo, política de `SELECT` para `anon`/`authenticated` e nenhuma política de escrita. Ou seja, com a chave pública só é possível ler. Alterações são feitas pelo painel do Supabase.

> **Pausa por inatividade:** projetos do plano gratuito pausam quando recebem poucas consultas em 7 dias. Isso aconteceu (o projeto foi reativado em 07/11/2026). Para evitar, o workflow `.github/workflows/manter-supabase-ativo.yml` faz uma leitura por dia com a chave pública; se a leitura falhar, o GitHub manda um e-mail. O GitHub desliga workflows agendados depois de 60 dias sem commits no repositório: se isso acontecer, reative em **Actions → Manter o Supabase ativo → Enable workflow**. Se o site mostrar "Não foi possível carregar os pontos", abra o painel do Supabase e clique em **Restore project**.

## Chave do Google Maps (passo a passo)

**Situação atual:** projeto `ecotroca-512512` criado no Google Cloud (conta do projeto), Maps JavaScript API ativada e chave "Ecotroca site (Maps JavaScript)" criada com:
- restrição de API: só Maps JavaScript API;
- restrição de sites: `https://ecotroca-xi.vercel.app/*`, `https://*.vercel.app/*`, `http://localhost:5173/*`, `http://127.0.0.1:5173/*`.

**Faturamento (pendente):** o projeto **não tem conta de faturamento vinculada**. Sem ela, o Google trata a chave como *demo key*, com uma **cota diária pequena** para o mapa inteiro (produção, testes e desenvolvimento somados). Em 07/11/2026 essa cota acabou durante uma rodada de testes e o mapa ficou indisponível até a virada do dia (meia-noite no horário do Pacífico, 5h em Brasília); no console aparece `Maps Demo Key limit reached`. O site continua funcionando sem o mapa (lista, distâncias e "Como chegar"). Para resolver de vez: **Faturamento → Vincular conta de faturamento** no projeto `ecotroca-512512`. A cota gratuita mensal do Google Maps Platform cobre com folga um projeto acadêmico; crie um alerta de orçamento para garantir.

Para refazer em outra conta:

> A ativação da Maps JavaScript API exige uma **conta de faturamento** no Google Cloud (cartão cadastrado). Existe uma cota gratuita mensal que costuma cobrir um projeto acadêmico, mas confira os valores atuais na página de preços do Google Maps Platform e, se quiser, crie um alerta de orçamento.

1. Acesse <https://console.cloud.google.com> e faça login.
2. No seletor de projetos (topo), clique em **Novo projeto**, dê o nome `ecotroca` e crie.
3. Menu **Faturamento** → vincule (ou crie) uma conta de faturamento a esse projeto.
4. Menu **APIs e serviços → Biblioteca** → procure **Maps JavaScript API** → **Ativar**.
5. **APIs e serviços → Credenciais → Criar credenciais → Chave de API**. Copie a chave.
6. Clique na chave para editar e restrinja:
   - **Restrições de aplicativo → Sites (referenciadores HTTP)**, adicione:
     - `http://localhost:*/*` (se o console não aceitar porta curinga, use `http://localhost:5173/*`)
     - `http://127.0.0.1:5173/*`
     - `https://ecotroca-xi.vercel.app/*` (domínio de produção do projeto)
     - `https://*.vercel.app/*` (pré-visualizações; isso libera a chave para qualquer subdomínio vercel.app — se preferir, troque por `https://ecotroca-*-teste-611a.vercel.app/*`)
   - **Restrições de API → Restringir chave → Maps JavaScript API**.
   - Salve.
7. Cole a chave em `js/config.js` (`GOOGLE_MAPS_API_KEY`), faça commit e push. A Vercel publica sozinha.
8. (Opcional, recomendado para produção) **Google Maps Platform → Gerenciamento de mapas → Criar ID do mapa** (tipo JavaScript, vetorial) e cole em `GOOGLE_MAPS_MAP_ID`.

Se a chave for recusada (domínio fora da lista, API não ativada, cota esgotada), o site mostra "O mapa está indisponível agora" sobre o mapa e a lista continua funcionando. O motivo técnico aparece no console do navegador.

## Publicar na Vercel

Já publicado: projeto `ecotroca` no time `teste-611a`, ligado ao GitHub. Cada push na `main` gera um deploy de produção em <https://ecotroca-xi.vercel.app>. As URLs de pré-visualização (`*-teste-611a.vercel.app`) ficam protegidas por login da Vercel (padrão do plano); a URL de produção é pública.

Para recriar em outra conta:

1. Acesse <https://vercel.com/new> com sua conta.
2. Em **Import Git Repository**, escolha `matheusgiachetti/ecotroca` (se não aparecer, clique em **Adjust GitHub App Permissions** e libere o repositório).
3. **Framework Preset: Other**. Deixe Build Command e Output Directory vazios (site estático na raiz).
4. Clique em **Deploy**. Se `ecotroca.vercel.app` já estiver em uso, a Vercel cria outro nome (aqui ficou `ecotroca-xi.vercel.app`).
5. Adicione essa URL nas restrições da chave do Google Maps (passo 6 acima).

## Feedback (Google Forms)

Já criado e publicado (qualquer pessoa com o link responde, sem login e sem coletar e-mail). Perguntas: encontrou o ponto mais próximo? (obrigatória) · quanto tempo levou · facilidade de 1 a 5 (obrigatória) · aparelho usado · o que atrapalhou (texto livre) · usaria de verdade? As respostas ficam na aba **Respostas** do formulário, no Google Drive da conta.

Para trocar por outro formulário: crie o formulário, clique em **Enviar → link**, copie a URL (`https://docs.google.com/forms/...` ou `https://forms.gle/...`) e cole em `FEEDBACK_FORM_URL`. O link "Dê sua opinião" aparece abaixo da lista do mapa e no rodapé.

## Pontos de coleta

### Situação atual (23/10/2026)

Os pontos fictícios foram removidos do banco. Estão cadastrados 4 pontos **reais**, levantados em fontes públicas e marcados como **Em verificação** (`verificado = false`). O script está em `supabase/pontos-reais.sql`.

| Ponto | Endereço | Fonte |
|---|---|---|
| Ecoponto Vila Helena | Rua Roque Sampaio, 100 | Prefeitura de Sorocaba, 01/09/2026 |
| Ecoponto Brigadeiro Tobias | Rua José Sarti, 636 | Prefeitura de Sorocaba, 01/09/2026 |
| Ecoponto Vila Hortência | Rua Lourenço Molineiro, 100 (posição aproximada) | Prefeitura de Sorocaba, 01/09/2026 |
| Coletor da Sema (pilhas e pequenos eletrônicos) | Rua Santa Maria, 197 | Jornal Cruzeiro do Sul, 24/01/2024 |

Os tipos aceitos nos Ecopontos foram traduzidos de "resíduos eletrônicos e eletrodomésticos" (texto da Prefeitura) para as categorias do site; pilhas não foram incluídas porque a fonte não cita.

**Pendentes (fonte confiável, mas sem coordenada exata — não cadastrados para não levar ninguém ao lugar errado):**
- Ecoponto Cajuru — Avenida Paraná, 3.200 (Prefeitura, 01/09/2026)
- Ecoponto Júlio de Mesquita Filho — Avenida Domingues Martins, 100 (Prefeitura, 01/09/2026)
- Ecoponto Aparecidinha — Estrada do Barreiro, 90 (Prefeitura, 01/09/2026)
- Metareciclagem (computadores e informática) — Av. Dr. Armando Salles de Oliveira, 762, Trujillo · (15) 3417-3825 · seg. a sex., 8h às 16h (Jornal Cruzeiro do Sul, 24/01/2024)

Para cadastrar: abra o endereço no Google Maps, clique com o botão direito no portão do local, copie as coordenadas e use o modelo de SQL abaixo. Depois de ligar para o 156 (Prefeitura) ou ir ao local, mude `verificado` para `true`.

Fontes: [Prefeitura — Ecopontos](https://noticias.sorocaba.sp.gov.br/ecopontos-dao-destinacao-correta-a-aproximadamente-215-mil-metros-cubicos-de-residuos/), [Jornal Cruzeiro do Sul — eletrônicos](https://www.jornalcruzeiro.com.br/sorocaba/noticias/2024/01/728031-eletronicos-exigem-descarte-adequado.html), [Green Eletron — Sorocaba](https://greeneletron.org.br/blog/mora-em-sorocaba-saiba-onde-descartar-seus-eletroeletronicos-sem-uso/) (lista de 2020, não usada por estar desatualizada).

### Como adicionar ou corrigir pontos

1. Levante pontos reais no SINIR (<https://sinir.gov.br>), na prefeitura ou com os responsáveis pelos locais.
2. Confira endereço, horário e o que cada ponto aceita. Pegue as coordenadas no Google Maps (clique com o botão direito no local → copie os números).
3. No painel do Supabase → **Table Editor → pontos_coleta**, edite as linhas de exemplo ou insira novas. Ou rode no SQL Editor:

```sql
insert into public.pontos_coleta
  (nome, endereco, latitude, longitude, horario, residuos_aceitos, telefone, fonte, verificado)
values
  ('Nome do local', 'Rua, número, bairro — Sorocaba/SP', -23.50, -47.45,
   'Seg. a sex., 8h às 17h', array['Pilhas e baterias', 'Celulares'],
   '(15) 0000-0000', 'SINIR, consultado em 10/2026', true);

-- quando os reais estiverem cadastrados:
delete from public.pontos_coleta where nome like 'Ponto de exemplo %';
```

Use em `residuos_aceitos` os mesmos nomes dos filtros: `Celulares`, `Pilhas e baterias`, `Cabos e carregadores`, `Computadores e periféricos`, `Eletrodomésticos pequenos`. Outros nomes viram filtros extras automaticamente.

Marque `verificado = true` só depois de confirmar com a fonte; o site mostra "Verificado" ou "Em verificação" e a fonte de cada ponto.

## Suposições registradas

- **Supabase:** já existia um projeto pausado chamado `ecotroca` (região `us-east-1`). Ele foi reativado e usado, em vez de criar um segundo projeto em `sa-east-1`. A latência é baixa o bastante para este uso.
- **`residuos_aceitos`** foi criado como `text[] not null default '{}'` (lista vazia em vez de nulo) e a tabela ganhou validações simples (nome/endereço preenchidos, latitude/longitude válidas).
- **Map ID:** os marcadores avançados (`AdvancedMarkerElement`) exigem um Map ID; usamos `DEMO_MAP_ID` até existir um próprio.
- **Localização automática:** o site só pede a localização quando a pessoa clica em "Encontrar ponto de coleta" ou "Usar minha localização". Se a permissão já foi dada antes, localiza sozinho ao abrir.
- **Repositório GitHub:** criado público, como o repositório `UPX` original.
- **Logo:** `assets/logo.png` foi extraída da imagem enviada (fundo quadriculado removido). `assets/logo-original.png` guarda a imagem original.
- **Domínio:** `ecotroca.vercel.app` já pertence a outra conta; o projeto ficou com `ecotroca-xi.vercel.app`. As tags `og:url`, `og:image` e `canonical` usam esse domínio — troque se configurar um domínio próprio.
- O arquivo `UPX_S2.html` (estrutura inicial do grupo) foi mantido sem alterações.

## Conta e pontos

O banco, o `js/data.js` e a interface (`js/conta.js`, painéis na própria página) têm: cadastro e login por e-mail e senha (com apelido único de 3 a 20 caracteres: letras, números e `_`), registro de descartes por proximidade, pontos e níveis. Quem não entra na conta usa o site exatamente como antes.

**Na página:** botão **Entrar** no menu (depois vira o apelido e **Sair**); no cartão de cada ponto, **Registrar descarte** (escolher o tipo, a quantidade de 1 a 10 e confirmar; só então o site pede a localização); **Minha conta** (nível com barra até o próximo, pontos, descartes, itens, kg estimados e **Medalhas**). O histórico de descartes fica para a próxima etapa. O apelido mostrado no menu vem do cadastro; se ele for alterado direto no banco, a página só atualiza depois de sair e entrar de novo.

**Como funciona o descarte:** a função `registrar_descarte` (SQL, `supabase/05-rpc-pontos.sql`) exige login, confere que a pessoa está a até **200 m** do ponto (a posição não é guardada), aceita **5 registros e 30 itens por dia** (dia de Brasília) e calcula pontos e peso no banco. Níveis: Semente 0–49, Broto 50–149, Muda 150–349, Árvore 350–699, Floresta 700+.

**Fonte única dos números:** raio, limites diários, quantidade máxima por registro, fuso e níveis ficam **só** na função `regras_limites()` (`05-rpc-pontos.sql`). `registrar_descarte`, `nivel_por_pontos` e a função pública `regras_pontos()` leem dela, e o site mostra o que `regras_pontos()` devolve (seção **Pontos** da página, barra de nível, limites do formulário). Para mudar uma regra, mude lá e reaplique o SQL: o site acompanha sozinho. Os pontos por tipo vêm de `tipos_residuo`.

| Tipo de resíduo | Pontos por item | Peso estimado por item |
|---|---|---|
| Pilhas e baterias | 5 | 0,025 kg |
| Cabos e carregadores | 5 | 0,150 kg |
| Celulares | 20 | 0,170 kg |
| Computadores e periféricos | 50 | 2,000 kg |
| Eletrodomésticos pequenos | 30 | 1,200 kg |

> **Os pesos em kg são "estimativa do grupo - revisar"**: ainda não têm fonte verificada (a coluna `fonte` de `tipos_residuo` diz isso). Revise antes de divulgar qualquer número de impacto. Para corrigir, edite a tabela `tipos_residuo` no painel do Supabase (não precisa mexer no código).

> **Limitação:** sem foto ou QR code no ponto, o descarte é confirmado só pela proximidade (a posição vem do navegador e pode ser falseada) e pelos limites diários. Serve para desestimular abuso, não para provar o descarte. Antes de haver recompensa real ou ranking público, é preciso uma confirmação mais forte.

**Confirmação de e-mail do Auth: desligada** por enquanto, porque o envio padrão do Supabase tem limite muito baixo de e-mails por hora. Para religar: Dashboard → **Authentication → Sign In / Providers → Email → Confirm email**. Com ela ligada, o cadastro só vale depois de a pessoa abrir o e-mail (e convém configurar um SMTP próprio). Aviso do Supabase ainda aberto: *Leaked password protection* (checagem de senhas vazadas) está desligada; ela fica em **Authentication → Sign In / Providers → Password** e, segundo o Supabase, depende de plano pago.

**Apagar pontos:** não rode `pontos-reais.sql` (ele apaga e reinsere pontos) depois que houver descartes: o histórico fica com `ponto_id` vazio. Para corrigir um ponto, use `update`.

**Usuários de teste:** a suíte cria contas `teste-ecotroca-*@example.com` pela API de Auth. A chave pública não consegue apagá-las; depois de rodar `tests/test_11`, `test_12`, `test_13`, `test_14`, `test_16` e `test_18`, remova-as no SQL Editor: `delete from auth.users where email like 'teste-ecotroca-%@example.com';` (perfis e descartes saem junto).

## Ranking

Seção **Ranking** na página: top 10 por **Semana** (segunda a domingo), **Mês** ou **Geral** (fuso de Brasília), para **Todas as cidades** ou **Minha cidade** (só para quem está logado). Quem está logado e fora do top 10 vê a própria posição abaixo da lista. Sem pontuação no período: "Ninguém pontuou ainda neste período."

**Privacidade:** o ranking é público e mostra **só apelido, cidade, pontos do período e posição**. Não expõe id, e-mail nem dados de descarte. Desempate: pontos do período e, depois, o apelido (ordem alfabética). O limite é de no máximo 50 posições; valor inválido vira 10. As funções (`ranking`, `minha_posicao`) estão em `supabase/06-ranking.sql` e somam os descartes no banco; `anon` e `authenticated` continuam sem ler `profiles` nem `descartes` diretamente.

> **Aplicar o `06-ranking.sql` no SQL Editor ANTES de publicar:** sem ele a seção mostra "Não foi possível carregar o ranking agora" (o site continua funcionando, e o mapa e a lista não são afetados). O arquivo é idempotente.

## Medalhas e impacto

**Medalhas** (`supabase/07-medalhas.sql`): Primeiro descarte, 10 itens descartados (somando os registros), 3 tipos de resíduo diferentes e 100 pontos. Quem concede é **o banco, dentro de `registrar_descarte`**, depois de gravar o descarte (`on conflict do nothing`: nunca duas vezes); o navegador nunca concede. **Medalha não dá pontos** (`pontos_total` só muda pelo valor do descarte). `registrar_descarte` devolve `medalhas_novas` (os nomes ganhos naquela chamada) e `minhas_medalhas()` lista todas, com `conquistada` verdadeiro ou falso. As tabelas `medalhas` e `usuario_medalhas` têm RLS: cada pessoa lê só as próprias conquistas, `anon` não lê nada e ninguém escreve direto. Os limiares (10 itens, 3 tipos, 100 pontos) estão em `conceder_medalhas()` e repetidos no texto das descrições da tabela `medalhas`; se mudar um, mude o outro.

**Impacto:** o site mostra só o **peso estimado** (kg), sempre com o rótulo "estimativa" e a frase "peso médio por item, por tipo de resíduo". **Não há equivalências ambientais** (CO2, árvores etc.): nenhum fator tem fonte verificada no projeto, então nenhuma é exibida. Só acrescente uma com fonte citável.

**Seção "Como os pontos funcionam"** (link **Pontos** no menu): pontos por tipo, níveis, medalhas e limites diários, tudo lido de `regras_pontos()`.

> **Ordem de aplicação:** no SQL Editor, rode `05-rpc-pontos.sql` e depois `07-medalhas.sql` (os dois são idempotentes e podem ir na mesma execução). Só depois faça o push. O `05` sozinho continua registrando descartes (só não há medalhas até o `07`); sem o `07` a seção Pontos e a lista de medalhas mostram erro com "Tentar de novo".

## Privacidade, termos e exclusão de conta

- **Páginas:** `privacidade.html` e `termos.html`, linkadas no rodapé. Estão marcadas **"Versão para revisão"**: o texto foi escrito a partir do que o código faz e **ainda precisa de revisão jurídica** antes de ser tratado como final. Controlador: *Grupo Ecotroca, UPx Facens*; contato (e-mail e o link do formulário de opinião, `FEEDBACK_FORM_URL`) no texto das duas páginas; como são HTML estático, o link do formulário está escrito nelas e precisa ser atualizado junto se `js/config.js` mudar. Se mudar o que o site guarda, atualize as páginas.
- **O que o site guarda de cada pessoa:** e-mail e senha (Supabase Auth), apelido, cidade (padrão "Sorocaba"), pontos, descartes (ponto, tipo, quantidade, pontos, peso estimado, data e hora) e medalhas com a data. **A localização não é guardada**: vai ao banco só como argumento de `registrar_descarte`, para conferir a distância.
- **Aceite no cadastro:** a caixa "Li e aceito os Termos de uso e a Política de Privacidade" é obrigatória. A checagem é feita no navegador (o banco não registra o aceite).
- **Excluir minha conta:** em Minha conta, exige digitar o apelido. Chama `excluir_minha_conta()` (`supabase/08-excluir-conta.sql`, `SECURITY DEFINER`, só logado, sem parâmetros: só apaga a própria conta). A linha de `auth.users` é apagada e `profiles`, `descartes` e `usuario_medalhas` saem em **cascata**; a exclusão não deixa dado órfão. Depois a pessoa sai da sessão e vê a mensagem de conta excluída.

> **Ordem de aplicação:** rode `supabase/08-excluir-conta.sql` no SQL Editor ANTES de publicar. Sem ele, o botão "Excluir minha conta" mostra "Não foi possível excluir a conta agora".

## Tema claro, escuro e automático

O menu tem três botões: **Automático** (segue o aparelho), **Claro** e **Escuro**. A escolha fica no navegador (`localStorage`, chave `ecotroca-tema`); se o navegador bloquear o armazenamento, o site funciona do mesmo jeito e só não lembra a escolha. As cores estão todas em variáveis no topo de `css/styles.css` (claro em `:root`; escuro em `:root[data-theme="dark"]` e no `@media (prefers-color-scheme: dark)`, com os mesmos valores nos dois). O hero mantém texto claro sobre a foto nos dois temas, e o mapa do Google continua claro. Ao criar uma cor nova, defina-a nos dois temas e confira o contraste (o `tests/test_20_tema.py` falha se algum par cair abaixo de 4,5:1).

## Próximos passos (fora do escopo atual)

Histórico de descartes, recompensas, métricas de impacto e painel administrativo. O código já está separado para isso: `data.js` concentra o acesso ao banco (novas tabelas e Supabase Auth entram aqui), `map.js` isola o mapa e `main.js` cuida só da interface.

## Créditos

- Foto do topo (também usada na página 404): [Chris Ried](https://unsplash.com/@cdr6934?utm_source=ecotroca&utm_medium=referral) no [Unsplash](https://unsplash.com/?utm_source=ecotroca&utm_medium=referral).
- Foto de cabos: [Eugenia Pan'kiv](https://unsplash.com/@eugenivy_now?utm_source=ecotroca&utm_medium=referral) no [Unsplash](https://unsplash.com/?utm_source=ecotroca&utm_medium=referral).
- Fontes: Bricolage Grotesque e Instrument Sans (Google Fonts); título do topo em Times New Roman.
