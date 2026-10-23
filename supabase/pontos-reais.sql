-- =====================================================================
-- Ecotroca — pontos de coleta REAIS de Sorocaba/SP (levantamento inicial)
-- Fontes públicas, conferidas em 23/10/2026. Todos ficam com
-- verificado = false ("Em verificação") até alguém confirmar por telefone
-- (Prefeitura: 156) ou no local.
-- Coordenadas: OpenStreetMap (ponto do próprio local quando existe;
-- senão, a rua). Pontos sem coordenada confiável estão no README.
-- =====================================================================

-- Remove os pontos fictícios do seed.sql
delete from public.pontos_coleta where nome like 'Ponto de exemplo %';

-- Evita duplicar se o arquivo for rodado de novo
delete from public.pontos_coleta
 where nome in ('Ecoponto Vila Helena', 'Ecoponto Brigadeiro Tobias', 'Ecoponto Vila Hortência',
                'Coletor de eletrônicos e pilhas — Sema');

insert into public.pontos_coleta
  (nome, endereco, latitude, longitude, horario, residuos_aceitos, telefone, fonte, verificado)
values
  ('Ecoponto Vila Helena',
   'Rua Roque Sampaio, 100, Vila Helena — Sorocaba/SP',
   -23.4775296, -47.4928463,
   'Seg. a sex., 7h às 17h; sáb., 7h às 12h. Fechado em feriados. Até 1 m³ por entrega.',
   array['Celulares', 'Cabos e carregadores', 'Computadores e periféricos', 'Eletrodomésticos pequenos'],
   null,
   'Prefeitura de Sorocaba (notícia de 01/09/2026). Local no OpenStreetMap.',
   false),

  ('Ecoponto Brigadeiro Tobias',
   'Rua José Sarti, 636, Brigadeiro Tobias — Sorocaba/SP',
   -23.5133866, -47.3641622,
   'Seg. a sex., 7h às 17h; sáb., 7h às 12h. Fechado em feriados. Até 1 m³ por entrega.',
   array['Celulares', 'Cabos e carregadores', 'Computadores e periféricos', 'Eletrodomésticos pequenos'],
   null,
   'Prefeitura de Sorocaba (notícia de 01/09/2026). Local no OpenStreetMap.',
   false),

  ('Ecoponto Vila Hortência',
   'Rua Lourenço Molineiro, 100, Vila Hortência — Sorocaba/SP',
   -23.5035496, -47.4382499,
   'Seg. a sex., 7h às 17h; sáb., 7h às 12h. Fechado em feriados. Até 1 m³ por entrega.',
   array['Celulares', 'Cabos e carregadores', 'Computadores e periféricos', 'Eletrodomésticos pequenos'],
   null,
   'Prefeitura de Sorocaba (notícia de 01/09/2026). Posição aproximada (rua) pelo OpenStreetMap.',
   false),

  ('Coletor de eletrônicos e pilhas — Sema',
   'Rua Santa Maria, 197, Vila Hortência — Sorocaba/SP (sede da Secretaria do Meio Ambiente)',
   -23.5053825, -47.4488290,
   'Seg. a sex., 8h às 17h. Itens de até 30 cm de altura e 60 cm de largura.',
   array['Pilhas e baterias', 'Celulares', 'Cabos e carregadores', 'Computadores e periféricos', 'Eletrodomésticos pequenos'],
   null,
   'Jornal Cruzeiro do Sul (24/01/2024) e Green Eletron. Local no OpenStreetMap.',
   false);
