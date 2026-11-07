-- =====================================================================
-- Ecotroca — 08: exclusão da própria conta (LGPD)
--   excluir_minha_conta() → apaga a conta de quem está logado
-- Idempotente. Depende de 02 a 04 (e de 07, se já aplicado).
--
-- Como nada fica órfão: a função apaga a linha de auth.users e o banco apaga o resto em CASCATA:
--   auth.users ─(on delete cascade)→ public.profiles          (02)
--   public.profiles ─(on delete cascade)→ public.descartes    (04)
--   public.profiles ─(on delete cascade)→ public.usuario_medalhas (07)
-- O Supabase Auth também remove as sessões e identidades da pessoa (cascata do próprio Auth).
-- Não sobra e-mail, apelido, cidade, pontos, descartes nem medalhas.
--
-- Só apaga a conta de QUEM CHAMA (auth.uid()): não recebe parâmetro, então ninguém apaga a de outra pessoa.
-- Erros de regra levantam exceção com HINT estável: nao_logado
-- =====================================================================

create or replace function public.excluir_minha_conta()
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_uid uuid := auth.uid();
begin
  if v_uid is null then
    raise exception 'Entre na sua conta para excluí-la.' using hint = 'nao_logado';
  end if;

  delete from auth.users where id = v_uid;
end;
$$;

revoke all on function public.excluir_minha_conta() from public, anon, authenticated;
grant execute on function public.excluir_minha_conta() to authenticated;
