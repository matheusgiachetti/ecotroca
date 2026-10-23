# Ecotroca

**O caminho para um futuro sustentável.**

Plataforma web que ajuda quem descarta lixo eletrônico (REEE) a encontrar rapidamente o ponto de coleta correto mais próximo. Projeto da Usina de Projetos Experimentais (UPx) da Facens.

**No ar:** <https://ecotroca-xi.vercel.app> (deploy automático a cada push na `main`).

Site estático: HTML + CSS + JavaScript puro (ES modules), sem build e sem framework. Dados no Supabase, mapa no Google Maps.

---

## Estrutura

```
index.html              página única (Início, Mapa, Como funciona, O que descartar, Dúvidas, Sobre)
css/styles.css          estilos (mobile-first)
js/config.js            chaves e configurações públicas (placeholders começam com "COLE_")
js/main.js              interface: lista, filtros, detalhes, menu, animações
js/map.js               tudo do Google Maps (isolado: trocar de mapa = reescrever só este arquivo)
js/data.js              leitura dos pontos no Supabase (ou JSON de exemplo no modo demonstração)
js/geo.js               geolocalização, distância (Haversine) e link "Como chegar"
data/pontos-exemplo.json   pontos fictícios do modo demonstração
supabase/schema.sql     tabela pontos_coleta + RLS
supabase/seed.sql       5 pontos de EXEMPLO (fictícios)
assets/                 logo, ícones e fotos otimizadas
vercel.json             cabeçalhos para a hospedagem estática
```

## Rodar localmente

Qualquer servidor estático serve. Com Python (já vem no Windows com o instalador oficial):

```bash
python -m http.server 5173
```

Abra <http://localhost:5173>. A geolocalização só funciona em `localhost` ou HTTPS.

> Abrir o `index.html` direto pelo explorador de arquivos (`file://`) não funciona: os módulos JS precisam de um servidor.

## Configuração (`js/config.js`)

| Constante | Situação | O que é |
|---|---|---|
| `SUPABASE_URL` | ✅ preenchida | URL do projeto Supabase "ecotroca" |
| `SUPABASE_ANON_KEY` | ✅ preenchida | chave **pública** (publishable). Pode ficar no navegador |
| `GOOGLE_MAPS_API_KEY` | ⏳ placeholder | chave da Maps JavaScript API (veja abaixo) |
| `GOOGLE_MAPS_MAP_ID` | `DEMO_MAP_ID` | Map ID; opcional trocar por um seu |
| `FEEDBACK_FORM_URL` | ✅ preenchida | formulário "Ecotroca — Dê sua opinião" no Google Forms (conta do projeto). Se voltar a ser placeholder, o botão "Dê sua opinião" some |

Comportamento automático:
- **Supabase não configurado** → carrega `data/pontos-exemplo.json` e mostra o aviso "Modo demonstração".
- **Google Maps não configurado** → no lugar do mapa aparece uma mensagem explicando o que falta; a lista, os filtros e a localização continuam funcionando.

**Nunca** coloque a chave `service_role` do Supabase no projeto.

## Supabase

O projeto `ecotroca` (organização "ecotroca") já está criado, com a tabela e os 5 pontos de exemplo aplicados.

Para recriar do zero em outro projeto:
1. Crie um projeto em <https://supabase.com/dashboard> (plano gratuito; região São Paulo `sa-east-1`, se quiser).
2. Abra **SQL Editor**, cole e rode `supabase/schema.sql`, depois `supabase/seed.sql`.
3. Em **Project Settings → API Keys**, copie a URL e a chave **publishable** (ou a `anon` legada) para `js/config.js`.

Segurança: RLS ativo, política de `SELECT` para `anon`/`authenticated` e nenhuma política de escrita. Ou seja, com a chave pública só é possível ler. Alterações são feitas pelo painel do Supabase.

> Observação: projetos do plano gratuito pausam depois de um período sem uso. Se o site mostrar "Não foi possível carregar os pontos", abra o painel do Supabase e clique em **Restore project**.

## Chave do Google Maps (passo a passo)

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

Se a chave for recusada (domínio fora da lista, API não ativada), o site mostra "Não foi possível exibir o mapa" e a lista continua funcionando.

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
- **Repositório GitHub:** criado público, como o repositório `UPX` original. O remoto antigo ficou com o nome `upx`.
- **Logo:** `assets/logo.png` foi extraída da imagem enviada (fundo quadriculado removido). `assets/logo-original.png` guarda a imagem original.
- **Domínio:** `ecotroca.vercel.app` já pertence a outra conta; o projeto ficou com `ecotroca-xi.vercel.app`. As tags `og:url`, `og:image` e `canonical` usam esse domínio — troque se configurar um domínio próprio.
- O arquivo `UPX_S2.html` (estrutura inicial do grupo) foi mantido sem alterações.

## Próximos passos (fora do escopo atual)

Login, cadastro, pontuação/recompensas, ranking, métricas de impacto e painel administrativo. O código já está separado para isso: `data.js` concentra o acesso ao banco (novas tabelas e Supabase Auth entram aqui), `map.js` isola o mapa e `main.js` cuida só da interface.

## Créditos

- Foto do topo: [Chris Ried](https://unsplash.com/@cdr6934?utm_source=ecotroca&utm_medium=referral) no [Unsplash](https://unsplash.com/?utm_source=ecotroca&utm_medium=referral).
- Foto de cabos: [Eugenia Pan'kiv](https://unsplash.com/@eugenivy_now?utm_source=ecotroca&utm_medium=referral) no [Unsplash](https://unsplash.com/?utm_source=ecotroca&utm_medium=referral).
- Fontes: Bricolage Grotesque e Instrument Sans (Google Fonts); título do topo em Times New Roman.
