-- =====================================================================
-- Ecotroca — dados de EXEMPLO
-- ATENÇÃO: estes pontos são fictícios. Servem apenas para testar o mapa.
-- Substitua por pontos reais conferidos no SINIR ou com os responsáveis
-- (veja o README, seção "Trocar os pontos de exemplo por pontos reais").
-- =====================================================================

-- Remove apenas linhas de exemplo anteriores (não toca em pontos reais)
delete from public.pontos_coleta where nome like 'Ponto de exemplo %';

insert into public.pontos_coleta
  (nome, endereco, latitude, longitude, horario, residuos_aceitos, telefone, fonte, verificado)
values
  ('Ponto de exemplo 1 — substituir por ponto verificado',
   'Endereço de exemplo, Centro — Sorocaba/SP',
   -23.5008, -47.4581,
   'Seg. a sex., 8h às 17h (exemplo)',
   array['Celulares', 'Pilhas e baterias', 'Cabos e carregadores'],
   null, 'Dado fictício para demonstração', false),

  ('Ponto de exemplo 2 — substituir por ponto verificado',
   'Endereço de exemplo, Zona Norte — Sorocaba/SP',
   -23.4862, -47.4415,
   'Seg. a sáb., 9h às 18h (exemplo)',
   array['Computadores e periféricos', 'Cabos e carregadores'],
   null, 'Dado fictício para demonstração', false),

  ('Ponto de exemplo 3 — substituir por ponto verificado',
   'Endereço de exemplo, Zona Oeste — Sorocaba/SP',
   -23.5168, -47.4688,
   'Seg. a sex., 8h às 16h (exemplo)',
   array['Pilhas e baterias'],
   null, 'Dado fictício para demonstração', false),

  ('Ponto de exemplo 4 — substituir por ponto verificado',
   'Endereço de exemplo, Zona Leste — Sorocaba/SP',
   -23.5254, -47.4362,
   'Ter. a sáb., 10h às 19h (exemplo)',
   array['Celulares', 'Eletrodomésticos pequenos', 'Computadores e periféricos'],
   null, 'Dado fictício para demonstração', false),

  ('Ponto de exemplo 5 — substituir por ponto verificado',
   'Endereço de exemplo, Zona Norte — Sorocaba/SP',
   -23.4771, -47.4733,
   'Seg. a sex., 9h às 17h (exemplo)',
   array['Celulares', 'Pilhas e baterias', 'Cabos e carregadores', 'Eletrodomésticos pequenos'],
   null, 'Dado fictício para demonstração', false);
