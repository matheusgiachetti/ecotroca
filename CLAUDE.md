# CLAUDE.md — Ecotroca

Guia de referência para quem (pessoa ou agente) for mexer neste repositório. Leia antes de qualquer tarefa. Detalhes operacionais (chaves, Supabase, Google Cloud, Vercel, pontos pendentes) estão no [README.md](README.md); este arquivo registra **o que não pode ser quebrado**.

---

## 1. Produto

**Ecotroca — "O caminho para um futuro sustentável."** Projeto da UPx (Usina de Projetos Experimentais) da Facens.

- **Problema:** quem tem lixo eletrônico (REEE: celulares, pilhas, cabos, computadores, eletrodomésticos pequenos) não sabe onde descartar.
- **Solução:** página única que mostra no mapa o ponto de coleta correto mais próximo, sem cadastro, em poucos segundos.
- **Região:** Sorocaba/SP (centro padrão do mapa `-23.5015, -47.4526`). Fora de ~60 km o site avisa que, por enquanto, só cobre Sorocaba.
- **Fluxo principal:** "Encontrar ponto de coleta" → permitir localização → lista ordenada por distância, primeiro item com selo "Mais próximo" → detalhes (horário, resíduos aceitos, telefone, status, fonte) → "Como chegar" (abre rota no Google Maps).
- **Confiabilidade dos dados é parte do produto:** cada ponto mostra "Verificado" ou "Em verificação" e a fonte. Não se cadastra ponto sem coordenada confiável ("para não levar ninguém ao lugar errado"). `verificado = true` só depois de confirmar com a fonte (telefone 156 da Prefeitura ou visita).
- **Feedback:** link "Dê sua opinião" para um Google Forms (abaixo da lista e no rodapé).
- **Conta e pontos (banco, `data.js` e interface na própria página única):** cadastro/login por e-mail e senha com apelido único, descartes registrados por proximidade, pontos, níveis (Semente 0–49, Broto 50–149, Muda 150–349, Árvore 350–699, Floresta 700+). Quem não entra na conta usa o mapa e a lista normalmente: **o fluxo sem login nunca pode depender de conta**.
- **Limitação conhecida da confirmação do descarte:** sem foto ou QR code, o descarte é aceito só por **proximidade** (até 200 m do ponto, pela posição que o navegador informa, que dá para falsear) e pelos **limites diários** (5 registros e 30 itens por dia). É dissuasão, não prova. Qualquer recompensa real ou ranking público precisa de uma confirmação mais forte (QR no ponto, foto ou validação do responsável) antes de valer algo.
- **Interface de conta (`js/conta.js`):** botão "Entrar" no menu (vira o apelido + "Sair"), painel de entrar/criar conta/minha conta (nível com barra, pontos, descartes, itens, kg com o rótulo "estimativa") e, no cartão de cada ponto, "Registrar descarte" (tipo → quantidade 1 a 10 → confirmar). **A localização só é pedida depois do clique em "Confirmar descarte".** Sem login o botão abre o painel de entrada e, depois de entrar, volta para o descarte. Painéis são `<dialog>` nativos: Esc fecha e o foco volta a quem abriu.
- **Ranking (`js/ranking.js`, `supabase/06-ranking.sql`):** seção na página com top 10 por período (Semana, Mês, Geral, no fuso de Brasília; a semana vai de segunda a domingo) e por cidade (Todas ou Minha cidade, esta só para quem está logado). Quem está logado e fora do top 10 vê a própria posição abaixo da lista (`minha_posicao`). O ranking é **público**.
- **REGRA DE PRIVACIDADE DO RANKING:** o ranking mostra **só apelido, cidade, pontos do período e posição**. Nunca id, e-mail, nem dados de descarte (ponto, tipo, hora, peso). Qualquer coluna nova nas funções `ranking` ou `minha_posicao` precisa de decisão explícita. As funções são `SECURITY DEFINER` para somar sem abrir as tabelas: `anon` e `authenticated` continuam sem ler `profiles` nem `descartes` diretamente.
- **Medalhas (`supabase/07-medalhas.sql`):** `primeiro_descarte`, `dez_itens`, `tres_tipos`, `cem_pontos`. **Quem concede é o banco, dentro de `registrar_descarte`** (via `conceder_medalhas`, interna, `on conflict do nothing`); o cliente nunca concede. **Medalha não dá pontos.** `registrar_descarte` devolve `medalhas_novas` e `minhas_medalhas()` lista as da pessoa logada. `usuario_medalhas`: cada pessoa lê só as próprias, `anon` não lê nada, ninguém escreve direto. Na interface: aviso "Nova medalha: …" no resultado do descarte e seção "Medalhas" em Minha conta (lista tipográfica, sem cards).
- **Fonte única das regras:** raio, limites diários, quantidade máxima, fuso e níveis vivem **só** em `regras_limites()` (`05-rpc-pontos.sql`). `registrar_descarte`, `nivel_por_pontos` e `regras_pontos()` (pública) leem dela, e o site (`js/regras.js`, `conta.js`) mostra o que `regras_pontos()` devolve. **Não repita esses números no JavaScript nem no HTML.** Mudou uma regra: mude em `regras_limites()` e reaplique o SQL.
- **Impacto sem equivalências:** o site mostra só o kg **estimado** (sempre com o rótulo "estimativa" e a frase "peso médio por item, por tipo de resíduo"). **Não exibir equivalências ambientais** (CO2, árvores etc.): nenhum fator tem fonte verificada. Só com fonte citável e decisão explícita.
- **Seção "Como os pontos funcionam" (`#pontos`, link "Pontos" no menu):** pontos por tipo, níveis, medalhas e limites, lidos de `regras_pontos()`; some no modo demonstração; erro com "Tentar de novo".
- **Fora do escopo atual:** histórico de descartes, recompensas, métricas de impacto, painel administrativo.

Seções da página (`index.html`): Início (hero) · Mapa · Ranking · Pontos (como os pontos funcionam) · Como funciona · O que descartar · Dúvidas · Sobre · Rodapé.

---

## 2. Stack

- **HTML + CSS + JavaScript puro** (ES modules nativos). **Sem build, sem framework, sem `package.json`, sem bundler.** Não introduza nenhum deles sem pedido explícito.
- **Google Maps JavaScript API**, carregada via bootstrap de `importLibrary` (reescrito em `js/map.js`) com `AdvancedMarkerElement` (exige Map ID; hoje `DEMO_MAP_ID`).
- **Supabase** (Postgres + RLS) via `@supabase/supabase-js@2.115.0` importado de `cdn.jsdelivr.net` sob demanda, com `persistSession: true` (sessão no `localStorage`, renovada sozinha). A confirmação de e-mail do Auth está **desligada** por enquanto (o envio padrão do Supabase é muito limitado); para religar: Dashboard → Authentication → Sign In / Providers → Email → ligar *Confirm email*. Com ela ligada, `cadastrar()` devolve `precisaConfirmar: true` e o site precisa avisar a pessoa para abrir o e-mail.
- **Vercel**, hospedagem estática (Framework Preset: Other, sem build command, raiz como saída).
- **Fontes (Google Fonts):** Bricolage Grotesque (títulos), Instrument Sans (texto). Times New Roman (fonte do sistema) só no título do hero.
- **Idioma:** pt-BR em tudo: interface, nomes de variáveis/funções/classes CSS, comentários e mensagens de commit.

## 3. Estrutura de pastas

```
index.html                 página única (todas as seções)
404.html                   página "não encontrada" (hero + links); caminhos SEMPRE absolutos (/css, /assets)
css/styles.css             todos os estilos, mobile-first, tokens em :root
js/config.js               valores PÚBLICOS: URL/chave publishable do Supabase, chave do Maps, Map ID,
                           link do Forms, centro/zoom padrão. Placeholder = começa com "COLE_"
js/main.js                 interface: estado, lista, filtros, detalhes, localização, menu, animações
js/map.js                  TUDO do Google Maps, isolado atrás de um "controlador"
js/data.js                 acesso a dados (Supabase ou JSON de demonstração) + normalização + conta e pontos (cadastrar, entrar, registrarDescarte…)
js/conta.js                interface dos painéis de conta e de registrar descarte (<dialog>); só usa funções do data.js
js/ranking.js              seção Ranking; conta.js avisa as mudanças de sessão e de pontos por eventos ('ecotroca:sessao', 'ecotroca:pontos')
js/regras.js               seção "Como os pontos funcionam" e cache de regras_pontos() (conta.js usa para níveis e limites)
js/geo.js                  geolocalização, Haversine, formatação de distância, link "Como chegar"
data/pontos-exemplo.json   pontos fictícios do modo demonstração
supabase/schema.sql        tabela pontos_coleta + constraints + RLS (idempotente)
supabase/seed.sql          5 pontos FICTÍCIOS ("Ponto de exemplo N …")
supabase/02-perfis.sql     profiles (apelido único) + trigger em auth.users + RLS
supabase/03-tipos-residuo.sql  tipos_residuo: pontos e kg estimado por item (mesmos nomes dos filtros)
supabase/04-descartes.sql  descartes (só leitura do próprio usuário)
supabase/05-rpc-pontos.sql regras_limites (fonte única dos números), registrar_descarte (SECURITY DEFINER), meu_resumo, nivel_por_pontos
supabase/06-ranking.sql    ranking (público), minha_posicao (logado) e a auxiliar interna ranking_linhas
supabase/07-medalhas.sql   medalhas, usuario_medalhas, conceder_medalhas (interna), minhas_medalhas, regras_pontos (pública)
supabase/pontos-reais.sql  4 pontos reais de Sorocaba, verificado = false
assets/                    logo, favicons, fotos em .webp + .jpg em vários tamanhos, og.jpg
vercel.json                cleanUrls + cabeçalhos de segurança + cache de /assets
tests/                     testes Playwright + pytest em Python (sem Node, sem package.json)
.github/workflows/         manter-supabase-ativo.yml: leitura diária para o plano gratuito não pausar
UPX_S2.html                estrutura inicial do grupo. NÃO alterar (mantido como registro)
```

### Fronteiras entre módulos (respeitar)

- `main.js` só fala com o mapa pelo controlador devolvido por `iniciarMapa()` (`definirPontos`, `filtrar`, `marcarProximo`, `selecionar`, `definirUsuario`, `enquadrar`, `centralizarPadrao`). Trocar de provedor de mapa = reescrever só `map.js`.
- Todo acesso ao banco passa por `data.js` (novas tabelas e Supabase Auth entram lá). `normalizar()` garante tipos previsíveis e descarta linhas sem coordenadas válidas.
- `geo.js` não depende do Google Maps: lista, filtros e distância funcionam sem o mapa.
- **Degradação elegante é obrigatória:** Supabase não configurado → modo demonstração com aviso; chave do Maps ausente/recusada (`gm_authFailure`) ou timeout (15 s) → aviso *sobreposto* ao mapa (não apagar o container), lista continua funcionando; erro ao carregar pontos → mensagem + botão "Tentar de novo".
- Categorias de resíduo (`CATEGORIAS` em `main.js`) usam exatamente os mesmos nomes do banco: `Celulares`, `Pilhas e baterias`, `Cabos e carregadores`, `Computadores e periféricos`, `Eletrodomésticos pequenos`. Nomes novos no banco viram filtros extras automaticamente.

---

## 4. Rodar localmente e testar

Node **não** está instalado nesta máquina; Python 3.12 está. Não crie `package.json`: os testes são em Python.

```bash
# servidor estático (porta 5173 é a liberada na chave do Google Maps)
python -m http.server 5173
# abrir http://localhost:5173  (ou http://127.0.0.1:5173)

# testes (uma vez: pip install -r tests/requirements.txt && python -m playwright install chromium)
python -m pytest tests                                  # contra o servidor local
BASE_URL=https://ecotroca-xi.vercel.app python -m pytest tests   # contra produção
```

- A suíte (`tests/test_01…test_10`) segue os itens da auditoria: mapa, localização, cartão, filtros, seções/feedback, layout, head/404, segurança, desempenho/acessibilidade. Ela lê os pontos reais do Supabase e falha se o projeto estiver pausado.
- `test_14_ranking.py` testa a seção Ranking (interface com um banco falso que repete as regras do SQL, em 375 e 1280 px, com axe e alvos de 44 px) e, contra o banco real, o contrato do ranking (pulado se o `06-ranking.sql` não estiver aplicado). `test_14_ranking_sql_local.py` roda `schema.sql` e `02` a `06` (duas vezes) num **Postgres local descartável** (`pip install pgserver "psycopg[binary]" tzdata`; pulado sem essas bibliotecas) e testa ordem, empate, fronteiras de semana e mês em Brasília, cidade, limite, privacidade e permissões, sem tocar no banco do projeto. Mudou o SQL do ranking? Rode esse arquivo antes de pedir para aplicar.
- `test_15_medalhas_sql_local.py` (Postgres local, `05` a `07` duas vezes): concessão só na hora certa, sem repetir, medalha sem alterar pontos, RLS, permissões, `regras_pontos` batendo com `tipos_residuo` e com as regras do `05`. `test_16_interface_medalhas.py`: aviso de medalha, seção de medalhas e "Como os pontos funcionam" em 375 e 1280 px (RPCs simulados) e, **pulado se o `07` não estiver aplicado**, o contrato e um descarte real ponta a ponta.
- Por padrão o `abrir()` simula os RPCs `ranking`, `minha_posicao`, `regras_pontos` e `minhas_medalhas` (lista vazia e valores fixos), para os outros testes não dependerem do banco real; use `ranking_real=True` / `regras_reais=True` para falar com o banco.
- **Limite do Auth:** criar muitos usuários de teste em poucos minutos dá `429 over_request_rate_limit`. Não rode a suíte em sequência; espere uns 5 minutos.
- `test_13_interface_conta.py` testa a interface de conta (cadastro, sair, entrar, registrar descarte com a posição simulada, erros de distância, limite e permissão, e o site sem login) em 375 e 1280 px.
- `test_11_pontos_banco.py` e `test_12_data_js.py` cobrem conta e pontos (RLS, isolamento entre usuários, 200 m, quantidade, 5 registros e 30 itens por dia, apelido inválido). Eles **criam usuários reais** `teste-ecotroca-*@example.com` pela API de Auth (precisa da confirmação de e-mail desligada). A chave pública não apaga usuário: depois de rodar, apague com `delete from auth.users where email like 'teste-ecotroca-%@example.com';` (SQL Editor ou MCP). Nunca deixe usuário de teste no banco de produção.
- **Cota do Google Maps:** o projeto do Google Cloud não tem faturamento, então a chave é uma *demo key* com cota diária pequena, compartilhada com o site em produção. Teste novo só usa `abrir(..., mapa=True)` se precisar mesmo do mapa real; não rode a suíte em loop nem crie scripts que recarregam a página com o mapa. `SEM_MAPA=1` pula os testes de mapa.
- Rode a suíte inteira antes de qualquer push na `main`. Funcionalidade nova ganha teste novo no arquivo do item correspondente.
- Dados controlados (telefone, HTML malicioso, filtro sem resultado) são simulados com `responder_supabase()` em `tests/conftest.py`, sem tocar no banco.
- Geolocalização é emulada pelo Playwright; GPS real só dá para conferir num celular.
- Não há Lighthouse local (precisa de Node). Use o PageSpeed Insights na URL publicada.

- Abrir `index.html` por `file://` **não funciona** (ES modules precisam de servidor).
- Geolocalização só funciona em `localhost` ou HTTPS.
- Outra porta que não 5173 → o Google Maps recusa a chave (restrição por referrer) e aparece o aviso de erro. É o comportamento esperado, não um bug.

Conferência manual complementar no navegador (DevTools aberto, console sem erros):

1. Largura de 320–390 px primeiro, depois ≥ 900 px (o layout muda de verdade em 768 px e 900 px).
2. Lista carrega do Supabase; mapa mostra os marcadores; clicar na lista abre o balão no mapa e vice-versa.
3. "Usar minha localização": permitir → ordena por distância + selo "Mais próximo"; negar → mensagem amigável e pontos de Sorocaba.
4. Filtros: cada um filtra lista e marcadores; filtro sem resultado mostra a mensagem de vazio.
5. Navegação só por teclado (Tab, Enter, Esc no menu), foco visível, link "Pular para o mapa".
6. Para testar o modo demonstração, troque temporariamente `SUPABASE_URL` por `'COLE_...'` **e não commite isso**.
7. Para testar sem mapa, idem com `GOOGLE_MAPS_API_KEY`.
8. Movimento reduzido (`prefers-reduced-motion`) desliga as animações de entrada.

Se aparecer "Não foi possível carregar os pontos": o projeto Supabase do plano gratuito pode ter pausado (painel → Restore project).

---

## 5. Deploy

- Repositório `matheusgiachetti/ecotroca` (GitHub), projeto `ecotroca` no time Vercel `teste-611a`.
- **Cada push na `main` publica em produção automaticamente** em <https://ecotroca-xi.vercel.app>. Portanto: push na `main` = site no ar. Não fazer push sem pedido explícito.
- Branches/PRs geram pré-visualizações `*-teste-611a.vercel.app`, protegidas por login da Vercel. A chave do Maps aceita `https://*.vercel.app/*`.
- Não há build: a Vercel serve os arquivos da raiz. `vercel.json` define `cleanUrls`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy` (só geolocalização, só do próprio site) e cache de 7 dias em `/assets/*`.
- Como `/assets/*` fica em cache por 7 dias, ao **substituir** uma imagem use um nome de arquivo novo em vez de sobrescrever.
- Domínio de produção está fixo em `canonical`, `og:url` e `og:image` no `index.html`; se mudar o domínio, atualize os três e as restrições da chave do Maps.
- `404.html` na raiz é servido pela Vercel, com status 404, para qualquer caminho inexistente.
- O Supabase gratuito pausa com pouca consulta em 7 dias. O workflow diário evita isso; se o site ficar sem pontos, confira o status do projeto antes de procurar bug no código.
- Mudanças no banco **não** passam pelo deploy: são feitas no painel do Supabase (SQL Editor/Table Editor) e os scripts em `supabase/` devem ser atualizados junto.

---

## 6. Regras de design (já adotadas, obrigatórias)

Antes de criar qualquer componente, reutilize os tokens de `:root` em `css/styles.css`. Não crie cores, fontes ou raios soltos.

**Identidade**
- **Hero com foto de fundo** (placa de circuito, `<picture>` com webp + jpg e `srcset`), escurecimento uniforme e sutil (`rgb(10 22 12 / 0.58)`) para contraste, e **título em Times New Roman** (`--fonte-hero`, peso 400, grande, `line-height` ~0.95). Times New Roman aparece **só** no título do hero.
- Demais títulos em Bricolage Grotesque (`--fonte-titulo`); texto corrido em Instrument Sans (`--fonte-texto`). Sobretítulos pequenos, em caixa alta, com espaçamento entre letras (`.sobretitulo`).
- **Verde natural sobre off-white:** fundo `--papel #FAF8F3`, texto `--tinta #1F1B16` (quase preto, quente), verde principal `--verde-700 #2E7D32`. `--verde-400` só decorativo ou sobre fundo escuro. Fundos de seção alternam entre papel, `--verde-900` (Como funciona) e `--verde-100` (Dúvidas).

**Forma**
- **Pouquíssimas bordas.** Blocos se separam por espaço e por fundos alternados. Quando houver linha, é fina (1px, `--linha`) e separa itens de lista (lista de pontos, "O que descartar", FAQ, menu, fatos do Sobre).
- **Sem cards com contorno + raio + sombra.** Nunca combine os três num bloco de conteúdo. Raio padrão é mínimo (`--raio: 3px`); pílula (`999px`) só nos filtros. A única sombra existente é a dos marcadores do mapa (precisam aparecer sobre o mapa) e não deve se espalhar para o layout.
- **Sem gradientes chamativos.** Overlays, se precisar, são cor sólida translúcida.
- **Sem emojis no layout.** Ícones, quando necessários, são SVG inline com `aria-hidden="true"` (como no botão de localização) ou desenhados em CSS (o +/− do FAQ).
- **Sem grade de 3 cards iguais.** O "Como funciona" usa 3 passos com numeração grande, linha fina no topo e deslocamento em escada no desktop, sem caixas. Não transforme isso em três cards, nem crie outra grade assim.
- **Texto alinhado à esquerda** em todo o site, inclusive hero e títulos. Não centralize blocos de texto. Larguras de leitura limitadas em `ch` (títulos ~14–22ch, parágrafos ~32–62ch).
- Layouts assimétricos no desktop (ex.: `5fr 6fr`, `4fr 7fr`, `7fr 5fr`), colunas laterais `sticky`.

**Texto (tom de voz)**
- Próximo, direto, em "você", frases curtas. Sem gírias, sem jargão desnecessário, sem exclamações de marketing. Termos técnicos explicados (ex.: "REEE: resíduos de equipamentos eletroeletrônicos").
- Erros e estados vazios são acolhedores e dizem o que fazer ("Tudo bem: mostramos os pontos de Sorocaba/SP…").
- Nunca prometer o que o dado não garante: horários e itens aceitos "podem mudar, confirme com o local".

**Mobile-first**
- CSS base é para celular; ampliações em `@media (min-width: 768px)` e `(min-width: 900px)`. Não escreva regras `max-width` como base.
- Largura mínima suportada: 320px. Margens laterais por `--margem` (`clamp`), espaçamento de seção por `--secao`. Imagens e mapa podem sangrar até a borda no celular (margem negativa).
- Alvos de toque ≥ 44×44 px para tudo que é clicável, exceto links no meio de uma frase (botões 48px, filtros e links soltos 44px via `inline-flex` + `min-height`). O teste `test_07_layout.py` confere em 320/375/768/1280 px. Menu vira botão "Menu" abaixo de 900px. Mapa com `gestureHandling: 'cooperative'` para não prender a rolagem.
- Imagens com `width`/`height`, `srcset`/`sizes`, webp + jpg, `loading="lazy"` fora da primeira dobra; hero com `preload` e `fetchpriority="high"`.

**Acessibilidade (WCAG AA)**
- Contraste mínimo AA (4,5:1 texto normal, 3:1 texto grande), conferido pelo axe-core e, no hero, medindo os pixels da foto atrás do texto (`test_10`). Verde de texto sobre papel é `--verde-700` ou mais escuro; não use `--verde-400` para texto sobre fundo claro. Ao criar combinação nova de cores, confira o contraste.
- HTML semântico: `section` com `aria-labelledby`, um único `h1` (hero), hierarquia de títulos sem saltos, `ol`/`ul`/`dl` para listas e dados, `details/summary` no FAQ, `button` para ações e `a` para navegação.
- Foco sempre visível (`:focus-visible` com contorno verde de 3px). Nunca `outline: none` sem substituto. Link "Pular para o mapa".
- Estados dinâmicos anunciados: `role="status"`/`aria-live="polite"` no status de localização e na contagem, `aria-busy` durante carregamento, `aria-expanded`/`aria-controls` nos itens recolhíveis e no menu, `aria-pressed` nos filtros.
- Textos alternativos descritivos em português; SVG decorativo com `aria-hidden`. Links que abrem nova aba avisam no `aria-label`, que começa pelo texto visível (ex.: "Como chegar a … (abre o Google Maps em nova aba)").
- Respeitar `prefers-reduced-motion` (já desliga transições e a entrada das seções). Esc fecha o menu e devolve o foco.
- `lang="pt-BR"` no documento.

---

## 7. Regras de segurança (obrigatórias)

1. **Nunca usar a chave `service_role` do Supabase no front-end** (nem em `js/config.js`, nem em nenhum arquivo versionado, nem em variável da Vercel exposta ao navegador). O site usa só a chave **publishable/anon**, que é pública por design. Escritas administrativas acontecem pelo painel do Supabase. Se um dia precisar de operação privilegiada, ela vai para uma Edge Function ou backend, nunca para o navegador.
2. **Ordem de deploy com SQL novo:** aplique o script no banco ANTES do push que o usa (hoje: `05` e depois `07`, na mesma execução); a página chama as funções assim que carrega e sem o SQL a seção mostra erro (e o console registra o 404).
3. **Toda tabela com RLS ativo.** Tabelas atuais: `pontos_coleta` e `tipos_residuo` (leitura pública), `profiles` (o usuário lê só a própria linha e altera só `apelido` e `cidade`, por *grant* de coluna), `descartes` (o usuário lê só os próprios; **sem** INSERT/UPDATE/DELETE para ninguém além da função), `medalhas` (leitura só para logado) e `usuario_medalhas` (o usuário lê só as próprias; só `conceder_medalhas` grava). `pontos_total` e `descartes` só mudam por `registrar_descarte()`; pontos e peso são calculados no banco a partir de `tipos_residuo`, **nunca** de valores do cliente. A função é `SECURITY DEFINER` com `search_path` fixo, exige login, confere a distância (Haversine, 200 m, coordenadas do ponto lidas no banco) e **não grava a posição do usuário**. Funções novas: `revoke all … from public, anon, authenticated` e `grant execute` só a quem precisa. Ao criar tabela nova: `enable row level security`, `revoke all … from anon, authenticated`, `grant` só o necessário e políticas explícitas e mínimas (padrão atual: `pontos_coleta` tem apenas `SELECT` para `anon`/`authenticated` e nenhuma política de escrita). Scripts SQL ficam em `supabase/`, idempotentes (`if not exists`, `drop policy if exists`), com constraints de validação. Depois de qualquer mudança de schema, rodar os advisors de segurança do Supabase.
4. **Textos vindos do banco sempre escapados.** Inserir no DOM só via `textContent` / `createElement` (o helper `criar()` existe em `main.js` e `map.js`). **Nunca** `innerHTML`, `insertAdjacentHTML`, `outerHTML` ou template string com dado do banco. Isso vale também para o conteúdo do `InfoWindow` do Maps (passar nós DOM, não string HTML).
   - URLs montadas com dados: coordenadas passam por `Number()` (`urlComoChegar`), telefone é filtrado para `[\d+]` antes de ir para `tel:`. Qualquer link novo vindo do banco deve validar o esquema (`https:` apenas), como `iniciarFeedback()` faz.
   - Links externos com `target="_blank"` levam `rel="noopener"`.
5. Outros cuidados já em vigor:
   - Chave do Google Maps é pública mas **restrita** por referrer (produção, `*.vercel.app`, `localhost:5173`, `127.0.0.1:5173`) e só para a Maps JavaScript API. Não remover essas restrições.
   - Segredos nunca versionados (`.env`, `.env.*`, `*.local` estão no `.gitignore`).
   - A localização do usuário fica só no navegador: não enviar para o banco nem para terceiros (além do próprio Google Maps ao desenhar o mapa). O site só pede a localização após clique, salvo se a permissão já foi dada.
   - Dependências de CDN com versão exata fixada (ex.: `supabase-js@2.115.0`), nunca `@latest`.
   - Não afrouxar os cabeçalhos do `vercel.json`.
   - Automação (GitHub Actions) só usa a chave publishable, lida de `js/config.js`. Se um dia precisar de segredo, ele vai em *GitHub Secrets*, nunca no YAML.

---

## 8. Convenções de trabalho

- Commits em português no estilo Conventional Commits, como no histórico: `feat(mapa): …`, `fix(mapa): …`, `feat(dados): …`, `docs: …`, `chore: …`.
- Nomes em português no código (`estado`, `pontosVisiveis`, `.ponto__cabeca`). CSS em BEM aportuguesado (`bloco__elemento--modificador`) com estados `is-*` (`is-aberto`, `is-proximo`, `is-rolado`).
- Comentários explicam o *porquê* e seguem o cabeçalho `// ====` de cada arquivo.
- Dados de pontos: incluir `fonte` com data; usar os nomes de categoria oficiais; `verificado = false` até confirmar. Manter `supabase/*.sql` e a tabela do README em sincronia com o banco.
- Atualizar o README quando mudar configuração, deploy ou dados; atualizar este CLAUDE.md quando mudar uma regra.
