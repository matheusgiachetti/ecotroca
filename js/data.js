// =====================================================================
// Ecotroca — dados: pontos de coleta, conta (Supabase Auth) e pontos do usuário
// Pontos de coleta: Supabase (tabela pontos_coleta). Se o Supabase não estiver
// configurado, usa data/pontos-exemplo.json (modo demonstração).
// Conta e pontos: só com o Supabase configurado. Quem não entra na conta
// continua usando o mapa e a lista normalmente.
// =====================================================================

import { SUPABASE_URL, SUPABASE_ANON_KEY, naoConfigurado } from './config.js';

const SUPABASE_CDN = 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.115.0/+esm';
const COLUNAS = 'id, nome, endereco, latitude, longitude, horario, residuos_aceitos, telefone, fonte, verificado';

export const modoDemonstracao = () => naoConfigurado(SUPABASE_URL) || naoConfigurado(SUPABASE_ANON_KEY);

let clienteSupabase = null;

/** Cria o cliente do Supabase sob demanda (só baixa a biblioteca se for usar). */
async function obterCliente() {
  if (!clienteSupabase) {
    const { createClient } = await import(SUPABASE_CDN);
    // A sessão fica no localStorage do navegador e é renovada sozinha.
    // Só a chave PÚBLICA (publishable) é usada aqui; a service_role nunca entra no front-end.
    clienteSupabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
      auth: { persistSession: true, autoRefreshToken: true },
    });
  }
  return clienteSupabase;
}

/** Garante tipos e valores previsíveis, descartando linhas sem coordenadas válidas. */
function normalizar(linha) {
  const lat = Number(linha.latitude);
  const lng = Number(linha.longitude);
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
  const texto = (v) => (typeof v === 'string' && v.trim() ? v.trim() : null);
  return {
    id: String(linha.id),
    nome: texto(linha.nome) || 'Ponto de coleta',
    endereco: texto(linha.endereco) || '',
    lat,
    lng,
    horario: texto(linha.horario),
    residuos: Array.isArray(linha.residuos_aceitos)
      ? linha.residuos_aceitos.map(texto).filter(Boolean)
      : [],
    telefone: texto(linha.telefone),
    fonte: texto(linha.fonte),
    verificado: linha.verificado === true,
  };
}

/**
 * Carrega os pontos de coleta.
 * @returns {Promise<{pontos: Array, demonstracao: boolean}>}
 */
export async function carregarPontos() {
  if (modoDemonstracao()) {
    const resposta = await fetch('data/pontos-exemplo.json', { cache: 'no-cache' });
    if (!resposta.ok) throw new Error(`Falha ao ler dados de exemplo (${resposta.status})`);
    const linhas = await resposta.json();
    return { pontos: linhas.map(normalizar).filter(Boolean), demonstracao: true };
  }

  const cliente = await obterCliente();
  const { data, error } = await cliente.from('pontos_coleta').select(COLUNAS).order('nome');
  if (error) throw new Error(error.message);
  return { pontos: (data || []).map(normalizar).filter(Boolean), demonstracao: false };
}

// =====================================================================
// Conta e pontos
// As regras de negócio (distância, limites, pontos) vivem no banco, em
// registrar_descarte(). Aqui só chamamos a função e traduzimos os erros.
// =====================================================================

/** Erro com mensagem em português pronta para mostrar e um código estável. */
export class ErroEcotroca extends Error {
  constructor(codigo, mensagem) {
    super(mensagem);
    this.name = 'ErroEcotroca';
    this.codigo = codigo;
  }
}

export const MENSAGEM_APELIDO = 'Esse apelido não é válido ou já está em uso.';
export const SENHA_MINIMA = 6;

// Chave = HINT que o banco devolve nas regras de registrar_descarte() e meu_resumo()
const MENSAGENS_DO_BANCO = {
  nao_logado: 'Entre na sua conta para continuar.',
  longe_do_ponto: 'Você precisa estar a até 200 m do ponto de coleta para registrar o descarte.',
  limite_registros: 'Você já fez 5 registros hoje. Volte amanhã.',
  limite_itens: 'O limite é de 30 itens por dia. Registre uma quantidade menor ou volte amanhã.',
  quantidade_invalida: 'A quantidade deve ser de 1 a 10 itens.',
  ponto_inexistente: 'Não encontramos esse ponto de coleta.',
  tipo_inexistente: 'Não encontramos esse tipo de resíduo.',
  coordenadas_invalidas: 'Não foi possível ler a sua localização.',
  perfil_inexistente: 'Não encontramos o seu perfil. Saia e entre de novo.',
  periodo_invalido: 'Período inválido. Escolha semana, mês ou geral.',
};
const ERRO_GENERICO = 'Algo deu errado. Verifique sua conexão e tente de novo.';

const REGRA_APELIDO = /^[A-Za-z0-9_]{3,20}$/;
const REGRA_EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Devolve a mensagem de erro do apelido, ou null se ele for válido. */
export function validarApelido(apelido) {
  return typeof apelido === 'string' && REGRA_APELIDO.test(apelido)
    ? null
    : 'O apelido deve ter de 3 a 20 caracteres, só letras, números e _.';
}

/** Cliente do Supabase para as funções de conta; no modo demonstração não há conta. */
async function clienteDeConta() {
  if (modoDemonstracao()) {
    throw new ErroEcotroca('sem_supabase', 'A conta não está disponível no modo demonstração.');
  }
  return obterCliente();
}

/** Traduz erro do banco (pelo HINT) ou do Auth para uma ErroEcotroca em português. */
function traduzirErro(erro, padrao = ERRO_GENERICO) {
  if (erro instanceof ErroEcotroca) return erro;
  const hint = erro && erro.hint;
  if (hint && MENSAGENS_DO_BANCO[hint]) return new ErroEcotroca(hint, MENSAGENS_DO_BANCO[hint]);
  // Limite de requisições do Auth (muitas tentativas de cadastro ou login em pouco tempo)
  if (erro && (erro.status === 429 || erro.code === 'over_request_rate_limit' || erro.code === 'over_email_send_rate_limit')) {
    return new ErroEcotroca('muitas_tentativas', 'Muitas tentativas em pouco tempo. Espere alguns minutos e tente de novo.');
  }
  // Sem sessão, o banco nem deixa o papel anônimo executar a função (permission denied, sem HINT)
  if (erro && erro.code === '42501') return new ErroEcotroca('nao_logado', MENSAGENS_DO_BANCO.nao_logado);
  console.error('[Ecotroca] Erro não mapeado:', erro);
  return new ErroEcotroca('desconhecido', padrao);
}

/** Cria a conta. Devolve { usuario, sessao, precisaConfirmar }. */
export async function cadastrar(email, senha, apelido) {
  const problemaApelido = validarApelido(apelido);
  if (problemaApelido) throw new ErroEcotroca('apelido_invalido', problemaApelido);
  if (typeof email !== 'string' || !REGRA_EMAIL.test(email.trim())) {
    throw new ErroEcotroca('email_invalido', 'Informe um e-mail válido.');
  }
  if (typeof senha !== 'string' || senha.length < SENHA_MINIMA) {
    throw new ErroEcotroca('senha_curta', `A senha precisa ter pelo menos ${SENHA_MINIMA} caracteres.`);
  }

  const cliente = await clienteDeConta();
  const { data, error } = await cliente.auth.signUp({
    email: email.trim(),
    password: senha,
    options: { data: { apelido } },
  });
  if (error) {
    if (error.code === 'user_already_exists') {
      throw new ErroEcotroca('email_em_uso', 'Esse e-mail já tem uma conta. Tente entrar.');
    }
    if (error.code === 'weak_password') {
      throw new ErroEcotroca('senha_fraca', 'Essa senha é fraca demais. Escolha uma senha mais longa.');
    }
    // O trigger recusa apelido inválido ou repetido, e o Auth devolve só "Database error saving new user".
    if (error.status === 500 || error.code === 'unexpected_failure' || /database error/i.test(error.message || '')) {
      throw new ErroEcotroca('apelido_invalido_ou_em_uso', MENSAGEM_APELIDO);
    }
    throw traduzirErro(error, 'Não foi possível criar a conta agora. Tente de novo.');
  }
  return { usuario: data.user, sessao: data.session, precisaConfirmar: !data.session };
}

/** Entra com e-mail e senha. Devolve { usuario, sessao }. */
export async function entrar(email, senha) {
  if (typeof email !== 'string' || !email.trim() || typeof senha !== 'string' || !senha) {
    throw new ErroEcotroca('credenciais_invalidas', 'Informe o e-mail e a senha.');
  }
  const cliente = await clienteDeConta();
  const { data, error } = await cliente.auth.signInWithPassword({ email: email.trim(), password: senha });
  if (error) {
    if (error.code === 'invalid_credentials') {
      throw new ErroEcotroca('credenciais_invalidas', 'E-mail ou senha incorretos.');
    }
    if (error.code === 'email_not_confirmed') {
      throw new ErroEcotroca('email_nao_confirmado', 'Confirme seu e-mail antes de entrar.');
    }
    throw traduzirErro(error, 'Não foi possível entrar agora. Tente de novo.');
  }
  return { usuario: data.user, sessao: data.session };
}

/** Sai da conta neste navegador. */
export async function sair() {
  const cliente = await clienteDeConta();
  const { error } = await cliente.auth.signOut();
  if (error) throw traduzirErro(error);
}

/** Sessão atual ou null. Sem Supabase configurado (modo demonstração) é sempre null. */
export async function sessaoAtual() {
  if (modoDemonstracao()) return null;
  const cliente = await obterCliente();
  const { data, error } = await cliente.auth.getSession();
  if (error) return null;
  return data.session || null;
}

/** Tipos de resíduo com pontos e peso estimado: [{ id, nome, pontos, pesoKg, fonte }]. */
export async function listarTiposResiduo() {
  const cliente = await clienteDeConta();
  const { data, error } = await cliente
    .from('tipos_residuo')
    .select('id, nome, pontos, peso_estimado_kg, fonte')
    .order('id');
  if (error) throw traduzirErro(error);
  return (data || []).map((t) => ({
    id: t.id,
    nome: t.nome,
    pontos: t.pontos,
    pesoKg: Number(t.peso_estimado_kg),
    fonte: t.fonte,
  }));
}

/**
 * Registra um descarte. lat/lng servem só para o banco conferir a distância (até 200 m)
 * e NÃO são guardados. Devolve { descarteId, pontosGanhos, pontosTotal, nivel, pesoKgEstimado }.
 */
export async function registrarDescarte(pontoId, tipoId, quantidade, lat, lng) {
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
    throw new ErroEcotroca('coordenadas_invalidas', MENSAGENS_DO_BANCO.coordenadas_invalidas);
  }
  const cliente = await clienteDeConta();
  const { data, error } = await cliente.rpc('registrar_descarte', {
    p_ponto_id: pontoId,
    p_tipo_id: tipoId,
    p_quantidade: quantidade,
    p_lat: lat,
    p_lng: lng,
  });
  if (error) throw traduzirErro(error);
  return {
    descarteId: data.descarte_id,
    pontosGanhos: data.pontos_ganhos,
    pontosTotal: data.pontos_total,
    nivel: data.nivel,
    pesoKgEstimado: Number(data.peso_kg_estimado),
  };
}

/** Resumo do usuário: { pontosTotal, nivel, descartes, itens, kgEstimados }. */
export async function meuResumo() {
  const cliente = await clienteDeConta();
  const { data, error } = await cliente.rpc('meu_resumo');
  if (error) throw traduzirErro(error);
  return {
    pontosTotal: data.pontos_total,
    nivel: data.nivel,
    descartes: data.descartes,
    itens: data.itens,
    kgEstimados: Number(data.kg_estimados),
  };
}

// =====================================================================
// Ranking
// Público: só apelido, cidade, pontos do período e posição (nunca id, e-mail
// nem dados de descarte). A soma e a ordem são feitas no banco, em
// supabase/06-ranking.sql.
// =====================================================================

export const PERIODOS_RANKING = ['semana', 'mes', 'geral'];
export const LIMITE_RANKING = 10;

function validarPeriodo(periodo) {
  if (!PERIODOS_RANKING.includes(periodo)) {
    throw new ErroEcotroca('periodo_invalido', MENSAGENS_DO_BANCO.periodo_invalido);
  }
}

/**
 * Top do ranking: [{ posicao, apelido, cidade, pontos }].
 * `cidade` nula = todas as cidades. Não exige login.
 */
export async function ranking(periodo = 'geral', cidade = null, limite = LIMITE_RANKING) {
  validarPeriodo(periodo);
  const cliente = await clienteDeConta();
  const { data, error } = await cliente.rpc('ranking', {
    p_periodo: periodo,
    p_cidade: cidade || null,
    p_limite: limite,
  });
  if (error) throw traduzirErro(error, 'Não foi possível carregar o ranking agora. Tente de novo.');
  return (data || []).map((l) => ({ posicao: l.posicao, apelido: l.apelido, cidade: l.cidade, pontos: l.pontos }));
}

/** A posição da pessoa logada no período: { posicao, pontos }, ou null se ela não pontuou. */
export async function minhaPosicao(periodo = 'geral', cidade = null) {
  validarPeriodo(periodo);
  const cliente = await clienteDeConta();
  const { data, error } = await cliente.rpc('minha_posicao', { p_periodo: periodo, p_cidade: cidade || null });
  if (error) throw traduzirErro(error, 'Não foi possível ver a sua posição agora.');
  const linha = Array.isArray(data) ? data[0] : null;
  return linha ? { posicao: linha.posicao, pontos: linha.pontos } : null;
}

/** Apelido e cidade da pessoa logada (a RLS só deixa ler a própria linha), ou null. */
export async function meuPerfil() {
  const cliente = await clienteDeConta();
  const { data, error } = await cliente.from('profiles').select('apelido, cidade').limit(1).maybeSingle();
  if (error) throw traduzirErro(error);
  return data ? { apelido: data.apelido, cidade: data.cidade } : null;
}
